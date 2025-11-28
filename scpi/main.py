"""Main entry point for SCPI."""

import argparse
import re
from dataclasses import dataclass
from typing import Optional
from rich.console import Console

console = Console()


@dataclass
class RemotePath:
    """Parsed remote path in user@host:path format."""
    user: str
    host: str
    path: str
    port: int = 22


@dataclass
class TransferConfig:
    """Transfer configuration."""
    source: str
    target: str
    remote: RemotePath
    is_upload: bool
    identity_file: Optional[str] = None
    password: Optional[str] = None
    port: int = 22
    recursive: bool = False
    verbose: bool = False
    debug: bool = False
    interactive_side: str = "source"  # "source" or "target"


def parse_remote_path(path: str) -> Optional[RemotePath]:
    """Parse remote path in format: [user@]host[:port]:path

    Supports both formats:
    - user@host:path
    - user@host:port:path (custom port)

    Args:
        path: Path string to parse

    Returns:
        RemotePath if path is remote, None if local
    """
    # Pattern: [user@]host[:port]:path
    # Matches: user@example.com:2222:/path or user@example.com:/path
    pattern = r'^(?:([^@]+)@)?([^:]+)(?::(\d+))?:(.*)$'
    match = re.match(pattern, path)

    if not match:
        return None

    user, host, port, remote_path = match.groups()

    return RemotePath(
        user=user or None,
        host=host,
        path=remote_path,
        port=int(port) if port else 22
    )


def parse_arguments() -> TransferConfig:
    """Parse command-line arguments in SCP style.

    Returns:
        TransferConfig with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="📁 SCP Interactive tool with terminal UI",
        usage="scpi [-P port] [-i identity_file] [-r] [-v] [-R] source target"
    )

    parser.add_argument(
        "source",
        help="Source file/directory (local path or user@host:path)"
    )
    parser.add_argument(
        "target",
        help="Target file/directory (local path or user@host:path)"
    )
    parser.add_argument(
        "-P",
        "--port",
        type=int,
        default=22,
        metavar="port",
        help="Port to connect to on the remote host (default: 22)"
    )
    parser.add_argument(
        "-i",
        "--identity-file",
        dest="identity_file",
        metavar="identity_file",
        help="Identity file (private key) for public key authentication"
    )
    parser.add_argument(
        "-p",
        "--password",
        help="Password for authentication"
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively copy entire directories"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose mode"
    )
    parser.add_argument(
        "-R",
        "--interactive-right",
        action="store_true",
        dest="interactive_right",
        help="Browse local directory (reverse default behavior of browsing remote)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging to debug.log"
    )

    args = parser.parse_args()

    # Parse source and target
    source_remote = parse_remote_path(args.source)
    target_remote = parse_remote_path(args.target)

    # Validate: exactly one should be remote
    if source_remote and target_remote:
        parser.error("❌ Cannot copy between two remote locations")

    if not source_remote and not target_remote:
        parser.error("❌ At least one of source or target must be remote (user@host:path)")

    # Determine upload or download
    is_upload = target_remote is not None
    remote = target_remote if is_upload else source_remote

    # If user not specified in path, it's required
    if remote.user is None:
        parser.error(f"❌ Username required in remote path: user@{remote.host}:{remote.path}")

    # Port priority: path > -P flag > default(22)
    # Only use -P flag if port wasn't specified in path
    if remote.port == 22 and args.port != 22:
        remote.port = args.port

    # Determine interactive side
    # Default: Remote side
    if is_upload:
        interactive_side = "target"
    else:
        interactive_side = "source"

    # If -R is passed, reverse to Local side
    if args.interactive_right:
        interactive_side = "source" if interactive_side == "target" else "target"

    return TransferConfig(
        source=args.source,
        target=args.target,
        remote=remote,
        is_upload=is_upload,
        identity_file=args.identity_file,
        password=args.password,
        port=args.port,
        recursive=args.recursive,
        verbose=args.verbose,
        debug=args.debug,
        interactive_side=interactive_side
    )


def list_local_files(path: str):
    """List local files.

    Args:
        path: Local directory path

    Returns:
        List of tuples (filename, is_directory, size, is_symlink, symlink_target, target_is_dir)
    """
    try:
        from pathlib import Path
        import os

        path_obj = Path(path)
        if not path_obj.exists():
            return []

        items = []
        for item in path_obj.iterdir():
            is_symlink = item.is_symlink()
            is_dir = item.is_dir()  # This follows symlinks by default
            symlink_target = ""
            target_is_dir = False

            # Resolve symlink if it is one
            if is_symlink:
                try:
                    # Get symlink target
                    target = item.readlink()
                    # Make absolute if relative
                    if not target.is_absolute():
                        target = (item.parent / target).resolve()
                    symlink_target = str(target)

                    # Check if target exists and is a directory
                    if target.exists():
                        target_is_dir = target.is_dir()
                        is_dir = target_is_dir
                    else:
                        symlink_target = f"{symlink_target} (broken link)"
                except Exception as e:
                    # Symlink is broken or we can't access it
                    console.print(f"⚠️  [yellow]Warning: Cannot resolve symlink {item.name}: {e}[/yellow]")
                    symlink_target = "(broken link)"

            stat_info = item.stat()
            size = stat_info.st_size if not is_dir else 0
            ctime = stat_info.st_birthtime if hasattr(stat_info, 'st_birthtime') else stat_info.st_ctime
            mtime = stat_info.st_mtime
            items.append((item.name, is_dir, size, is_symlink, symlink_target, target_is_dir, ctime, mtime))

        return sorted(items, key=lambda x: (not x[1], x[0].lower()))
    except Exception as e:
        console.print(f"❌ [red]Failed to list local files: {e}[/red]")
        return []


def perform_copy(
    selected_items,
    source_base,
    target_base,
    is_upload: bool,
    scp_client,
    config: TransferConfig,
    progress_callback=None,
    cancel_check=None
):
    """Perform the actual file copy operation.

    Args:
        selected_items: List of (path, is_dir) tuples
        source_base: Base source path
        target_base: Base target path
        is_upload: True for upload, False for download
        scp_client: SCPClient instance
        config: Transfer configuration
        progress_callback: Optional callback for progress updates
        cancel_check: Optional callable that returns True if operation should be cancelled
    """
    import logging
    from pathlib import Path

    logging.debug(f"=== perform_copy called ===")
    logging.debug(f"  selected_items: {selected_items}")
    logging.debug(f"  source_base: {source_base}")
    logging.debug(f"  target_base: {target_base}")
    logging.debug(f"  is_upload: {is_upload}")

    def report_progress(message: str):
        """Report progress via callback or console."""
        logging.debug(f"  Progress: {message}")
        if progress_callback:
            progress_callback(message)
        else:
            console.print(message)

    report_progress(f"📦 Copying {len(selected_items)} item(s)...")

    all_success = True
    for item_path, is_dir in selected_items:
        # 🛑 Check for cancellation before each item
        if cancel_check and cancel_check():
            logging.debug("  perform_copy cancelled during iteration")
            report_progress("🛑 Copy operation cancelled")
            return False

        # Get relative path for creating target structure
        item_name = Path(item_path).name
        logging.debug(f"  Processing item: {item_name} (is_dir={is_dir})")

        if is_upload:
            local_path = item_path
            remote_path = f"{target_base.rstrip('/')}/{item_name}"
            logging.debug(f"  Upload: {local_path} -> {remote_path}")

            if is_dir:
                report_progress(f"📁 Uploading directory: {item_name}")
                result = scp_client.upload_directory(local_path, remote_path, progress_callback=progress_callback, cancel_check=cancel_check)
                logging.debug(f"  Upload directory result: {result}")
            else:
                report_progress(f"📄 Uploading file: {item_name}")
                result = scp_client.upload_file(local_path, remote_path, progress_callback=progress_callback, cancel_check=cancel_check)
                logging.debug(f"  Upload file result: {result}")

            if not result:
                logging.error(f"  Failed to upload {item_name}")
                all_success = False
        else:
            remote_path = item_path
            local_path = str(Path(target_base) / item_name)
            logging.debug(f"  Download: {remote_path} -> {local_path}")

            if is_dir:
                report_progress(f"📁 Downloading directory: {item_name}")
                result = scp_client.download_directory(remote_path, local_path, progress_callback=progress_callback, cancel_check=cancel_check)
                logging.debug(f"  Download directory result: {result}")
            else:
                report_progress(f"📄 Downloading file: {item_name}")
                result = scp_client.download_file(remote_path, local_path, progress_callback=progress_callback, cancel_check=cancel_check)
                logging.debug(f"  Download file result: {result}")

            if not result:
                logging.error(f"  Failed to download {item_name}")
                all_success = False

    if all_success:
        report_progress("✨ All transfers completed!")
        logging.debug("=== perform_copy completed, returning True ===")
    else:
        report_progress("❌ Some transfers failed!")
        logging.debug("=== perform_copy completed with failures, returning False ===")

    return all_success


def main():
    """Main entry point."""
    from pathlib import Path
    from scpi.ssh_client import SCPClient
    from scpi.ui import FileBrowser

    try:
        config = parse_arguments()
    except SystemExit:
        return

    # Configure logging based on --debug flag
    import logging
    if config.debug:
        logging.basicConfig(
            filename='debug.log',
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            force=True  # Force reconfiguration if it was already configured
        )
    else:
        # Disable logging or set to critical only to avoid output
        logging.basicConfig(level=logging.CRITICAL)

    console.print("🔐 [bold green]SCPI - SCP Interactive Tool[/bold green]")

    mode = "⬆️  Upload" if config.is_upload else "⬇️  Download"
    console.print(f"{mode}: [cyan]{config.source}[/cyan] → [cyan]{config.target}[/cyan]")

    # Show interactive side
    interactive_path = config.target if config.interactive_side == "target" else config.source
    interactive_location = "remote" if (config.interactive_side == "target" and config.is_upload) or (config.interactive_side == "source" and not config.is_upload) else "local"
    console.print(f"🎯 Interactive: [yellow]{config.interactive_side}[/yellow] ({interactive_location}: {interactive_path})")

    if config.verbose:
        console.print(f"🔑 Auth: {'Key' if config.identity_file else 'Password'}")
        if config.identity_file:
            console.print(f"   Identity file: {config.identity_file}")
        console.print(f"📂 Recursive: {config.recursive}")

    # Initialize SSH client
    scp_client = SCPClient(
        host=config.remote.host,
        port=config.remote.port,
        username=config.remote.user,
        password=config.password,
        key_filename=config.identity_file
    )

    # Connect to remote
    if not scp_client.connect():
        console.print("❌ [red]Failed to connect. Exiting.[/red]")
        return

    try:
        # Expand remote path (resolve ~ to home directory)
        original_path = config.remote.path
        expanded_path = scp_client.expand_remote_path(config.remote.path)

        if expanded_path != original_path:
            console.print(f"🏠 [cyan]Expanded path: {original_path} → {expanded_path}[/cyan]")
            config.remote.path = expanded_path

        # Determine if interactive side is remote
        is_interactive_remote = (config.interactive_side == "target" and config.is_upload) or \
                               (config.interactive_side == "source" and not config.is_upload)

        # Parse the interactive path
        if is_interactive_remote:
            # Remote path
            interactive_full_path = config.remote.path

            # Check if path exists
            if not scp_client.remote_exists(interactive_full_path):
                console.print(f"❌ [red]Remote path does not exist: {interactive_full_path}[/red]")
                return

            # Check if it's a directory or file
            is_directory = scp_client.is_remote_dir(interactive_full_path)

            if config.verbose:
                path_type = "directory" if is_directory else "file"
                console.print(f"🔍 [dim]Detected remote path type: {path_type}[/dim]")

            if is_directory:
                # It's a directory - show file browser
                console.print(f"\n🗂️  [cyan]Browsing remote directory: {interactive_full_path}[/cyan]\n")

                # Determine if we are selecting destination (browsing target) or source items
                browsing_target = config.is_upload  # If upload, remote is target

                # Pre-calculate source items if we are browsing target
                source_items = []
                if browsing_target:
                    # Source is local
                    import os
                    from pathlib import Path
                    local_source = Path(config.source)
                    if local_source.is_dir():
                         # For upload directory, we usually copy the directory itself, not contents?
                         # SCP recursive behavior: 'scp -r src_dir target_dir' -> target_dir/src_dir
                         # So source item is just the directory itself
                         source_items.append((str(local_source.absolute()), True))
                    elif local_source.exists():
                         source_items.append((str(local_source.absolute()), False))
                    else:
                         console.print(f"❌ [red]Source not found: {config.source}[/red]")
                         return

                # Get target base path for copy callback
                if config.is_upload:
                    target_base = interactive_full_path
                    source_base = str(Path(config.source).parent.absolute())
                else:
                    source_base = interactive_full_path
                    target_base = config.target

                # Create copy callback
                def copy_files(selected_items, progress_callback=None, cancel_check=None):
                    """Copy selected files."""
                    if browsing_target:
                        # In this mode, selected_items is [(target_dir, is_dir)]
                        target_dir = selected_items[0][0]
                        # We copy FROM source_items TO target_dir
                        return perform_copy(source_items, source_base, target_dir, config.is_upload, scp_client, config, progress_callback, cancel_check)
                    else:
                        return perform_copy(selected_items, source_base, target_base, config.is_upload, scp_client, config, progress_callback, cancel_check)

                # Build remote title with user@host[:port]
                remote_title = f"🌐 Remote ({config.remote.user}@{config.remote.host}"
                if config.remote.port != 22:
                    remote_title += f":{config.remote.port}"
                remote_title += ")"

                browser = FileBrowser(
                    title=remote_title,
                    current_path=interactive_full_path,
                    list_files_func=scp_client.list_remote_files,
                    is_remote=True,
                    copy_callback=copy_files,
                    target_path=f"💻 {target_base}" if not browsing_target else f"📥 Source: {config.source}",
                    select_destination_mode=browsing_target
                )
                browser.run()

            else:
                # It's a file - direct copy
                console.print(f"\n📄 [cyan]Transferring single file...[/cyan]\n")

                if config.is_upload:
                    # This shouldn't happen (upload with remote target file)
                    console.print("❌ [red]Error: Target is a file, not a directory[/red]")
                    return
                else:
                    # Download single file
                    remote_file = interactive_full_path
                    local_file = config.target

                    console.print(f"📥 Downloading: {remote_file} → {local_file}")
                    if scp_client.download_file(remote_file, local_file):
                        console.print("✨ [bold green]Transfer completed![/bold green]")
                    else:
                        console.print("❌ [red]Transfer failed[/red]")

        else:
            # Local path
            local_path = config.source if config.interactive_side == "source" else config.target
            local_path_obj = Path(local_path)

            if local_path_obj.is_dir():
                # It's a directory - show file browser
                console.print(f"\n🗂️  [cyan]Browsing local directory: {local_path}[/cyan]\n")

                # Determine if we are selecting destination (browsing target) or source items
                browsing_target = not config.is_upload  # If download, local is target

                # Pre-calculate source items if we are browsing target
                source_items = []
                if browsing_target:
                    # Source is remote
                    # We need to check if remote source is a file or dir
                    # But we have scp_client
                    if scp_client.is_remote_dir(config.remote.path):
                         source_items.append((config.remote.path, True))
                    elif scp_client.remote_exists(config.remote.path):
                         source_items.append((config.remote.path, False))
                    else:
                         console.print(f"❌ [red]Remote source not found: {config.remote.path}[/red]")
                         return

                # Get target base path for copy callback
                if config.is_upload:
                    source_base = str(local_path_obj.absolute())
                    target_base = config.remote.path
                else:
                    target_base = str(local_path_obj.absolute())
                    source_base = str(Path(config.remote.path).parent) # Parent of remote file/dir

                # Create copy callback
                def copy_files(selected_items, progress_callback=None, cancel_check=None):
                    """Copy selected files."""
                    if browsing_target:
                         # In this mode, selected_items is [(target_dir, is_dir)]
                        target_dir = selected_items[0][0]
                        return perform_copy(source_items, source_base, target_dir, config.is_upload, scp_client, config, progress_callback, cancel_check)
                    else:
                        return perform_copy(selected_items, source_base, target_base, config.is_upload, scp_client, config, progress_callback, cancel_check)

                # Build local title with hostname
                import socket
                local_hostname = socket.gethostname()
                local_title = f"💻 Local ({local_hostname})"

                browser = FileBrowser(
                    title=local_title,
                    current_path=str(local_path_obj.absolute()),
                    list_files_func=list_local_files,
                    is_remote=False,
                    copy_callback=copy_files,
                    target_path=f"🌐 {target_base}" if not browsing_target else f"📥 Source: {config.source}",
                    select_destination_mode=browsing_target
                )
                browser.run()

            else:
                # It's a file - direct copy
                console.print(f"\n📄 [cyan]Transferring single file...[/cyan]\n")

                if config.is_upload:
                    # Upload single file
                    local_file = local_path
                    remote_file = config.remote.path

                    console.print(f"📤 Uploading: {local_file} → {remote_file}")
                    if scp_client.upload_file(local_file, remote_file):
                        console.print("✨ [bold green]Transfer completed![/bold green]")
                    else:
                        console.print("❌ [red]Transfer failed[/red]")
                else:
                    # This shouldn't happen (download with local source file)
                    console.print("❌ [red]Error: Source is a file, not a directory[/red]")
                    return

    finally:
        # Disconnect
        scp_client.disconnect()


if __name__ == "__main__":
    main()
