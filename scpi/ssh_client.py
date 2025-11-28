"""SSH/SCP client implementation using paramiko."""

import os
import stat
import socket
import time
from pathlib import Path
from typing import List, Optional, Tuple

import paramiko
from paramiko import SSHClient, AutoAddPolicy
from rich.console import Console

console = Console()


class SCPClient:
    """SCP client wrapper for file transfers."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = None,
        password: str = None,
        key_filename: str = None
    ):
        """Initialize SCP client.

        Args:
            host: Remote host address
            port: SSH port
            username: SSH username
            password: SSH password
            key_filename: Path to SSH private key
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self.client: Optional[SSHClient] = None
        self.sftp = None

    def connect(self) -> bool:
        """Establish SSH connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client = SSHClient()
            self.client.set_missing_host_key_policy(AutoAddPolicy())

            console.print(f"🔌 Connecting to {self.username}@{self.host}:{self.port}")

            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                key_filename=self.key_filename,
                timeout=10
            )

            self.sftp = self.client.open_sftp()
            console.print("✅ [green]Connected successfully[/green]")
            return True

        except Exception as e:
            console.print(f"❌ [red]Connection failed: {e}[/red]")
            return False

    def disconnect(self):
        """Close SSH connection."""
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()
        console.print("🔌 [yellow]Disconnected[/yellow]")

    def is_remote_dir(self, remote_path: str) -> bool:
        """Check if remote path is a directory.

        Args:
            remote_path: Remote path to check

        Returns:
            True if path is a directory, False otherwise
        """
        if not self.sftp:
            console.print("⚠️  [yellow]Warning: SFTP not connected[/yellow]")
            return False

        try:
            file_stat = self.sftp.stat(remote_path)
            is_dir = stat.S_ISDIR(file_stat.st_mode)
            return is_dir
        except FileNotFoundError:
            console.print(f"⚠️  [yellow]Path not found: {remote_path}[/yellow]")
            return False
        except Exception as e:
            console.print(f"⚠️  [yellow]Error checking if path is directory: {e}[/yellow]")
            return False

    def remote_exists(self, remote_path: str) -> bool:
        """Check if remote path exists.

        Args:
            remote_path: Remote path to check

        Returns:
            True if path exists, False otherwise
        """
        if not self.sftp:
            return False

        try:
            self.sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            console.print(f"⚠️  [yellow]Error checking if path exists: {e}[/yellow]")
            return False

    def expand_remote_path(self, remote_path: str) -> str:
        """Expand remote path (resolve ~ to home directory).

        Args:
            remote_path: Remote path to expand

        Returns:
            Expanded path
        """
        if not remote_path or not self.client:
            return remote_path

        # If path starts with ~, expand it
        if remote_path.startswith('~'):
            try:
                # Get home directory by executing pwd in home dir
                stdin, stdout, stderr = self.client.exec_command('echo $HOME')
                home_dir = stdout.read().decode('utf-8').strip()

                if home_dir:
                    if remote_path == '~':
                        return home_dir
                    elif remote_path.startswith('~/'):
                        return home_dir + remote_path[1:]

            except Exception as e:
                console.print(f"⚠️  [yellow]Warning: Could not expand ~: {e}[/yellow]")
                return remote_path

        return remote_path

    def normalize_remote_path(self, remote_path: str) -> str:
        """Normalize remote path (resolve .. and .).

        Args:
            remote_path: Remote path to normalize

        Returns:
            Normalized path
        """
        if not self.sftp:
            return remote_path

        try:
            return self.sftp.normalize(remote_path)
        except:
            return remote_path

    def list_remote_files(self, remote_path: str = ".") -> List[Tuple[str, bool, int, bool, str, bool]]:
        """List files in remote directory.

        Args:
            remote_path: Remote directory path

        Returns:
            List of tuples (filename, is_directory, size, is_symlink, symlink_target, target_is_dir)
        """
        import logging
        logging.debug(f"list_remote_files called for path: {remote_path}")

        # Helper function to ensure connection
        def ensure_connection():
            if not self.client or not self.client.get_transport() or not self.client.get_transport().is_active():
                logging.debug("list_remote_files: SSH transport is dead. Reconnecting...")
                return self.connect()
            
            if not self.sftp or self.sftp.sock is None or (self.sftp.sock.closed if hasattr(self.sftp.sock, 'closed') else False):
                logging.debug("list_remote_files: SFTP session is dead. Re-opening...")
                try:
                    self.sftp = self.client.open_sftp()
                    return True
                except Exception as e:
                    logging.error(f"list_remote_files: Failed to re-open SFTP: {e}")
                    return False
            return True

        # First attempt to ensure connection
        if not ensure_connection():
            logging.error("list_remote_files: Could not establish connection.")
            return []
        
        for attempt in range(2):
            try:
                logging.debug(f"list_remote_files: Calling sftp.listdir_attr (attempt {attempt+1})...")
                items = []
                for entry in self.sftp.listdir_attr(remote_path):
                    is_symlink = stat.S_ISLNK(entry.st_mode)
                    is_dir = stat.S_ISDIR(entry.st_mode)
                    size = entry.st_size if not is_dir else 0
                    symlink_target = ""
                    target_is_dir = False

                    # Get modification time (SFTP doesn't provide creation time)
                    mtime = entry.st_mtime if hasattr(entry, 'st_mtime') else 0
                    ctime = mtime  # Use mtime as ctime for remote files

                    # Resolve symlink if it is one
                    if is_symlink:
                        try:
                            full_path = f"{remote_path.rstrip('/')}/{entry.filename}"
                            # Get symlink target
                            symlink_target = self.sftp.readlink(full_path)

                            # If target is relative, make it absolute
                            if not symlink_target.startswith('/'):
                                symlink_target = f"{remote_path.rstrip('/')}/{symlink_target}"

                            # Check if target is a directory
                            target_stat = self.sftp.stat(full_path)  # stat follows symlinks
                            target_is_dir = stat.S_ISDIR(target_stat.st_mode)
                            # Update is_dir to reflect the target's type
                            is_dir = target_is_dir
                            # Update size to reflect the target's size
                            size = target_stat.st_size if not target_is_dir else 0
                            # Update mtime to reflect the target's mtime
                            if hasattr(target_stat, 'st_mtime'):
                                mtime = target_stat.st_mtime
                                ctime = mtime
                        except Exception as e:
                            # Symlink is broken or we can't access it
                            # logging.debug(f"Warning: Cannot resolve symlink {entry.filename}: {e}")
                            symlink_target = f"(broken link)"

                    items.append((entry.filename, is_dir, size, is_symlink, symlink_target, target_is_dir, ctime, mtime))
                
                logging.debug(f"list_remote_files: Found {len(items)} items")
                return sorted(items, key=lambda x: (not x[1], x[0].lower()))

            except (OSError, EOFError, paramiko.SSHException, socket.error) as e:
                logging.warning(f"list_remote_files: Attempt {attempt+1} failed with error: {e}")
                if attempt == 0:
                    logging.info("list_remote_files: Retrying after reconnecting...")
                    # Force close and reconnect
                    try:
                        if self.sftp: self.sftp.close()
                        if self.client: self.client.close()
                    except:
                        pass
                    
                    if not self.connect():
                        logging.error("list_remote_files: Reconnection failed.")
                        return []
                else:
                     logging.error("list_remote_files: All attempts failed.")
                     console.print(f"❌ [red]Failed to list remote files: {e}[/red]")
                     return []
            except Exception as e:
                logging.error(f"list_remote_files: Failed with unexpected error: {e}", exc_info=True)
                console.print(f"❌ [red]Failed to list remote files: {e}[/red]")
                return []
        
        return []

    def upload_file(self, local_path: str, remote_path: str, progress_callback=None, cancel_check=None) -> bool:
        """Upload a single file.

        Args:
            local_path: Local file path
            remote_path: Remote file path
            progress_callback: Optional callback for progress updates
            cancel_check: Optional callable that returns True if operation should be cancelled

        Returns:
            True if upload successful, False otherwise
        """
        import logging

        logging.debug(f"=== upload_file called ===")
        logging.debug(f"  local_path: {local_path}")
        logging.debug(f"  remote_path: {remote_path}")

        # 🛑 Check for cancellation before starting
        if cancel_check and cancel_check():
            logging.debug("  Upload cancelled before starting")
            return False

        if not self.sftp:
            logging.error("  SFTP connection not available")
            return False

        try:
            # Check if local file exists
            if not os.path.exists(local_path):
                logging.error(f"  Local file does not exist: {local_path}")
                return False

            file_size = os.path.getsize(local_path)
            logging.debug(f"  Local file size: {file_size} bytes")

            # Check remote directory exists
            remote_dir = os.path.dirname(remote_path)
            if remote_dir:
                logging.debug(f"  Remote directory: {remote_dir}")
                try:
                    self.sftp.stat(remote_dir)
                    logging.debug(f"  Remote directory exists")
                except FileNotFoundError:
                    logging.debug(f"  Creating remote directory: {remote_dir}")
                    self._create_remote_directory(remote_dir)

            logging.debug(f"  Starting SFTP put operation...")

            # Format file size for display
            def format_size(size_bytes):
                """Format bytes to human readable string."""
                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if size_bytes < 1024.0:
                        return f"{size_bytes:.1f} {unit}"
                    size_bytes /= 1024.0
                return f"{size_bytes:.1f} PB"

            file_name = Path(local_path).name
            start_time = time.time()

            # Use callback-based progress reporting and cancellation check
            try:
                # Define callback that enforces cancellation
                def check_cancel_and_report(transferred, total):
                    # Check for cancellation during transfer
                    if cancel_check and cancel_check():
                        # 🛑 FORCE STOP: Close SFTP session to break blocking I/O immediately
                        if self.sftp:
                            try:
                                self.sftp.close()
                            except:
                                pass
                        raise Exception("Transfer cancelled by user")

                    if progress_callback:
                        # Report every 1% or at completion (more frequent updates for smoother UI)
                        progress_percent = (transferred / total * 100) if total > 0 else 0
                        last_percent = (last_reported[0] / total * 100) if total > 0 else 0

                        if transferred == total or progress_percent - last_percent >= 1:
                            # Calculate speed
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                speed = transferred / elapsed
                                speed_str = f"{format_size(speed)}/s"
                            else:
                                speed_str = "..."

                            transferred_str = format_size(transferred)
                            total_str = format_size(total)
                            progress_msg = f"📄 {file_name}: {transferred_str} / {total_str} ({progress_percent:.0f}%) - {speed_str}"
                            progress_callback(progress_msg)
                            last_reported[0] = transferred

                if progress_callback:
                    last_reported = [0]  # Use list to allow modification in nested function
                    self.sftp.put(local_path, remote_path, callback=check_cancel_and_report)
                else:
                    self.sftp.put(local_path, remote_path, callback=check_cancel_and_report)

            except Exception as e:
                # If cancelled, we might get various exceptions
                is_cancelled = (cancel_check and cancel_check()) or "Transfer cancelled by user" in str(e) or "Session is closed" in str(e)

                if is_cancelled:
                    logging.debug(f"  Transfer cancelled by user (caught {type(e).__name__}: {e})")
                    
                    # 🔄 Try to restore SFTP session/connection
                    try:
                        transport_active = self.client and self.client.get_transport() and self.client.get_transport().is_active()
                        
                        if not transport_active:
                             logging.debug("  SSH transport is dead. Reconnecting...")
                             # Re-connect
                             if self.connect():
                                 logging.debug("  Reconnection successful.")
                             else:
                                 logging.error("  Reconnection failed.")
                        
                        elif self.client and (not self.sftp or self.sftp.sock is None):
                            logging.debug("  Restoring SFTP session after forced close...")
                            self.sftp = self.client.open_sftp()
                            logging.debug("  SFTP session restored.")
                    except Exception as restore_err:
                        logging.error(f"  Failed to restore connection/session: {restore_err}")
                        
                    return False

                raise e

            logging.debug(f"  SFTP put completed")

            # Verify file was actually uploaded
            try:
                uploaded_stat = self.sftp.stat(remote_path)
                uploaded_size = uploaded_stat.st_size
                logging.debug(f"  Uploaded file exists: {remote_path}")
                logging.debug(f"  Uploaded file size: {uploaded_size} bytes")
                if uploaded_size == file_size:
                    logging.debug(f"  File size matches! Upload successful.")
                else:
                    logging.warning(f"  File size mismatch! Expected {file_size}, got {uploaded_size}")
            except Exception as verify_error:
                logging.error(f"  Could not verify uploaded file: {verify_error}")

            console.print(f"✅ [green]Uploaded: {local_path} → {remote_path}[/green]")
            logging.debug("=== upload_file completed successfully ===")
            return True

        except Exception as e:
            logging.error(f"  Upload failed with exception: {type(e).__name__}: {e}", exc_info=True)
            console.print(f"❌ [red]Upload failed: {e}[/red]")
            return False

    def download_file(self, remote_path: str, local_path: str, progress_callback=None, cancel_check=None) -> bool:
        """Download a single file.

        Args:
            remote_path: Remote file path
            local_path: Local file path
            progress_callback: Optional callback for progress updates
            cancel_check: Optional callable that returns True if operation should be cancelled

        Returns:
            True if download successful, False otherwise
        """
        import logging

        logging.debug(f"=== download_file called ===")
        logging.debug(f"  remote_path: {remote_path}")
        logging.debug(f"  local_path: {local_path}")

        # 🛑 Check for cancellation before starting
        if cancel_check and cancel_check():
            logging.debug("  Download cancelled before starting")
            return False

        if not self.sftp:
            logging.error("  SFTP connection not available")
            return False

        try:
            # Check if remote file exists
            logging.debug(f"  Checking if remote file exists...")
            file_stat = self.sftp.stat(remote_path)
            file_size = file_stat.st_size
            logging.debug(f"  Remote file size: {file_size} bytes")

            # Check local directory exists
            local_dir = os.path.dirname(local_path)
            logging.debug(f"  Local directory: {local_dir}")
            if local_dir and not os.path.exists(local_dir):
                logging.debug(f"  Creating local directory: {local_dir}")
                os.makedirs(local_dir, exist_ok=True)

            logging.debug(f"  Starting SFTP get operation...")

            # Format file size for display
            def format_size(size_bytes):
                """Format bytes to human readable string."""
                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if size_bytes < 1024.0:
                        return f"{size_bytes:.1f} {unit}"
                    size_bytes /= 1024.0
                return f"{size_bytes:.1f} PB"

            file_name = Path(remote_path).name
            start_time = time.time()

            # Use callback-based progress reporting and cancellation check
            try:
                # Define callback that enforces cancellation
                def check_cancel_and_report(transferred, total):
                    # Check for cancellation during transfer
                    if cancel_check and cancel_check():
                        # 🛑 FORCE STOP: Close SFTP session to break blocking I/O immediately
                        if self.sftp:
                            try:
                                self.sftp.close()
                            except:
                                pass
                        raise Exception("Transfer cancelled by user")

                    if progress_callback:
                        # Report every 1% or at completion
                        progress_percent = (transferred / total * 100) if total > 0 else 0
                        last_percent = (last_reported[0] / total * 100) if total > 0 else 0

                        if transferred == total or progress_percent - last_percent >= 1:
                            # Calculate speed
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                speed = transferred / elapsed
                                speed_str = f"{format_size(speed)}/s"
                            else:
                                speed_str = "..."

                            transferred_str = format_size(transferred)
                            total_str = format_size(total)
                            progress_msg = f"📄 {file_name}: {transferred_str} / {total_str} ({progress_percent:.0f}%) - {speed_str}"
                            progress_callback(progress_msg)
                            last_reported[0] = transferred

                if progress_callback:
                    last_reported = [0]  # Use list to allow modification in nested function
                    self.sftp.get(remote_path, local_path, callback=check_cancel_and_report)
                else:
                    self.sftp.get(remote_path, local_path, callback=check_cancel_and_report)

            except Exception as e:
                # If cancelled, we might get various exceptions
                is_cancelled = (cancel_check and cancel_check()) or "Transfer cancelled by user" in str(e) or "Session is closed" in str(e)
                
                if is_cancelled:
                    logging.debug(f"  Transfer cancelled by user (caught {type(e).__name__}: {e})")
                    
                    # Clean up partial file
                    if os.path.exists(local_path):
                        try:
                            os.remove(local_path)
                            logging.debug(f"  Removed partial file: {local_path}")
                        except Exception as rm_err:
                            logging.error(f"  Failed to remove partial file: {rm_err}")

                    # 🔄 Try to restore SFTP session/connection
                    try:
                        transport_active = self.client and self.client.get_transport() and self.client.get_transport().is_active()
                        
                        if not transport_active:
                             logging.debug("  SSH transport is dead. Reconnecting...")
                             # Re-connect
                             if self.connect():
                                 logging.debug("  Reconnection successful.")
                             else:
                                 logging.error("  Reconnection failed.")
                        
                        elif self.client and (not self.sftp or self.sftp.sock is None):
                            logging.debug("  Restoring SFTP session after forced close...")
                            self.sftp = self.client.open_sftp()
                            logging.debug("  SFTP session restored.")
                    except Exception as restore_err:
                        logging.error(f"  Failed to restore connection/session: {restore_err}")

                    return False
                
                raise e

            logging.debug(f"  SFTP get completed")

            # Verify file was actually downloaded
            if os.path.exists(local_path):
                downloaded_size = os.path.getsize(local_path)
                logging.debug(f"  Downloaded file exists: {local_path}")
                logging.debug(f"  Downloaded file size: {downloaded_size} bytes")
                if downloaded_size == file_size:
                    logging.debug(f"  File size matches! Download successful.")
                else:
                    logging.warning(f"  File size mismatch! Expected {file_size}, got {downloaded_size}")
            else:
                logging.error(f"  Downloaded file does not exist: {local_path}")
                return False

            console.print(f"✅ [green]Downloaded: {remote_path} → {local_path}[/green]")
            logging.debug("=== download_file completed successfully ===")
            return True

        except Exception as e:
            logging.error(f"  Download failed with exception: {type(e).__name__}: {e}", exc_info=True)
            console.print(f"❌ [red]Download failed: {e}[/red]")
            return False

    def _create_remote_directory(self, remote_dir: str):
        """Create remote directory recursively.

        Args:
            remote_dir: Remote directory path
        """
        import logging

        if not remote_dir or remote_dir == '/':
            return

        try:
            self.sftp.stat(remote_dir)
            logging.debug(f"  Directory already exists: {remote_dir}")
        except FileNotFoundError:
            # Directory doesn't exist, create parent first
            parent = os.path.dirname(remote_dir)
            if parent and parent != remote_dir:
                self._create_remote_directory(parent)

            logging.debug(f"  Creating directory: {remote_dir}")
            self.sftp.mkdir(remote_dir)

    def upload_directory(self, local_dir: str, remote_dir: str, progress_callback=None, cancel_check=None) -> bool:
        """Upload directory recursively.

        Args:
            local_dir: Local directory path
            remote_dir: Remote directory path
            progress_callback: Optional callback for progress updates
            cancel_check: Optional callable that returns True if operation should be cancelled

        Returns:
            True if upload successful, False otherwise
        """
        import logging

        logging.debug(f"=== upload_directory called ===")
        logging.debug(f"  local_dir: {local_dir}")
        logging.debug(f"  remote_dir: {remote_dir}")

        # 🛑 Check for cancellation before starting
        if cancel_check and cancel_check():
            logging.debug("  Upload directory cancelled before starting")
            return False

        if not self.sftp:
            logging.error("  SFTP connection not available")
            return False

        try:
            # Create remote directory
            self._create_remote_directory(remote_dir)

            local_path = Path(local_dir)
            all_success = True

            for item in local_path.iterdir():
                # 🛑 Check for cancellation before each item
                if cancel_check and cancel_check():
                    logging.debug("  Upload directory cancelled during iteration")
                    return False

                local_item = str(item)
                remote_item = f"{remote_dir}/{item.name}"
                logging.debug(f"  Processing: {item.name} (is_dir={item.is_dir()})")

                if item.is_dir():
                    result = self.upload_directory(local_item, remote_item, progress_callback=progress_callback, cancel_check=cancel_check)
                    if not result:
                        logging.error(f"  Failed to upload directory: {item.name}")
                        all_success = False
                else:
                    result = self.upload_file(local_item, remote_item, progress_callback=progress_callback, cancel_check=cancel_check)
                    if not result:
                        logging.error(f"  Failed to upload file: {item.name}")
                        all_success = False

            logging.debug(f"=== upload_directory completed, success={all_success} ===")
            return all_success

        except Exception as e:
            logging.error(f"  Directory upload failed with exception: {type(e).__name__}: {e}", exc_info=True)
            console.print(f"❌ [red]Directory upload failed: {e}[/red]")
            return False

    def download_directory(self, remote_dir: str, local_dir: str, progress_callback=None, cancel_check=None) -> bool:
        """Download directory recursively.

        Args:
            remote_dir: Remote directory path
            local_dir: Local directory path
            progress_callback: Optional callback for progress updates
            cancel_check: Optional callable that returns True if operation should be cancelled

        Returns:
            True if download successful, False otherwise
        """
        import logging

        logging.debug(f"=== download_directory called ===")
        logging.debug(f"  remote_dir: {remote_dir}")
        logging.debug(f"  local_dir: {local_dir}")

        # 🛑 Check for cancellation before starting
        if cancel_check and cancel_check():
            logging.debug("  Download directory cancelled before starting")
            return False

        if not self.sftp:
            logging.error("  SFTP connection not available")
            return False

        try:
            # Create local directory
            logging.debug(f"  Creating local directory: {local_dir}")
            Path(local_dir).mkdir(parents=True, exist_ok=True)

            all_success = True

            for entry in self.sftp.listdir_attr(remote_dir):
                # 🛑 Check for cancellation before each item
                if cancel_check and cancel_check():
                    logging.debug("  Download directory cancelled during iteration")
                    return False

                remote_item = f"{remote_dir}/{entry.filename}"
                local_item = os.path.join(local_dir, entry.filename)
                is_dir = stat.S_ISDIR(entry.st_mode)
                logging.debug(f"  Processing: {entry.filename} (is_dir={is_dir})")

                if is_dir:
                    result = self.download_directory(remote_item, local_item, progress_callback=progress_callback, cancel_check=cancel_check)
                    if not result:
                        logging.error(f"  Failed to download directory: {entry.filename}")
                        all_success = False
                else:
                    result = self.download_file(remote_item, local_item, progress_callback=progress_callback, cancel_check=cancel_check)
                    if not result:
                        logging.error(f"  Failed to download file: {entry.filename}")
                        all_success = False

            logging.debug(f"=== download_directory completed, success={all_success} ===")
            return all_success

        except Exception as e:
            logging.error(f"  Directory download failed with exception: {type(e).__name__}: {e}", exc_info=True)
            console.print(f"❌ [red]Directory download failed: {e}[/red]")
            return False
