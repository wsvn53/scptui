"""Terminal UI components using Textual."""

import os
import logging
from pathlib import Path
from typing import List, Optional, Callable

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Button, Label, ListView, ListItem, ProgressBar, Input
from textual.binding import Binding
from textual.message import Message
from textual.screen import ModalScreen
from rich.text import Text

# Logging will be configured in main.py based on --debug flag


class FileListItem(ListItem):
    """Custom list item for file/folder display."""

    def __init__(self, name: str, is_dir: bool, size: int = 0, is_symlink: bool = False,
                 symlink_target: str = "", target_is_dir: bool = False,
                 ctime: float = 0, mtime: float = 0, *args, **kwargs):
        """Initialize file list item.

        Args:
            name: File/folder name
            is_dir: Whether this is a directory (or symlink to directory)
            size: File size in bytes
            is_symlink: Whether this is a symbolic link
            symlink_target: Target path if this is a symlink
            target_is_dir: Whether the symlink target is a directory
            ctime: Creation time (timestamp)
            mtime: Modification time (timestamp)
        """
        super().__init__(*args, **kwargs)
        self.file_name = name
        self.is_directory = is_dir
        self.file_size = size
        self.is_selected = False
        self.is_symlink = is_symlink
        self.symlink_target = symlink_target
        self.target_is_dir = target_is_dir
        self.ctime = ctime
        self.mtime = mtime

    def compose(self) -> ComposeResult:
        """Compose the list item."""
        # Format display and calculate display width
        if self.file_name == "..":
            icon = "⬆️ "
            display = f"{icon} [bold yellow]{self.file_name}[/bold yellow] [dim](Parent Directory)[/dim]"
            display_width = len(self.file_name) + len(" (Parent Directory)") + 3  # icon(2) + space(1)
        elif self.is_symlink:
            # Symlink - show with arrow to target
            if self.target_is_dir:
                icon = "📁🔗"
                display = f"{icon} [bold cyan]{self.file_name}/[/bold cyan] [dim]→ {self.symlink_target}[/dim]"
                display_width = len(self.file_name) + len(self.symlink_target) + 9  # icons(4) + " / → "(5)
            else:
                icon = "📄🔗"
                size_str = self._format_size(self.file_size)
                display = f"{icon} {self.file_name} [dim]({size_str}) → {self.symlink_target}[/dim]"
                display_width = len(self.file_name) + len(size_str) + len(self.symlink_target) + 13  # icons(4) + " () → "(9)
        elif self.is_directory:
            icon = "📁"
            display = f"{icon} [bold cyan]{self.file_name}/[/bold cyan]"
            display_width = len(self.file_name) + 4  # icon(2) + space(1) + /(1)
        else:
            icon = "📄"
            size_str = self._format_size(self.file_size)
            display = f"{icon} {self.file_name} [dim]({size_str})[/dim]"
            display_width = len(self.file_name) + len(size_str) + 7  # icon(2) + space(1) + " ()"(4)

        # Add time information with dynamic spacing for alignment
        if self.ctime > 0 and self.mtime > 0:
            from datetime import datetime
            ctime_str = datetime.fromtimestamp(self.ctime).strftime('%Y-%m-%d %H:%M:%S')
            mtime_str = datetime.fromtimestamp(self.mtime).strftime('%Y-%m-%d %H:%M:%S')

            # Calculate spaces needed to align at target column (50)
            target_column = 50
            spaces_needed = max(2, target_column - display_width)
            spaces = " " * spaces_needed

            display += f"{spaces}[dim]ctime: {ctime_str}  mtime: {mtime_str}[/dim]"

        yield Label(display)

    def _format_size(self, size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    def toggle_selection(self):
        """Toggle selection state."""
        if self.file_name == "..":
            return  # Cannot select parent directory

        self.is_selected = not self.is_selected
        if self.is_selected:
            self.add_class("selected")
        else:
            self.remove_class("selected")


class ConfirmModal(ModalScreen[bool]):
    """Modal screen for confirmation dialogs."""

    CSS = """
    ConfirmModal {
        align: center middle;
    }

    #confirm-dialog {
        width: 80;
        height: auto;
        max-height: 20;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }

    #confirm-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #confirm-message {
        width: 100%;
        height: auto;
        color: $text;
        padding: 1 2;
        margin-bottom: 1;
    }

    #confirm-buttons {
        height: 3;
        layout: horizontal;
        align: center middle;
    }

    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, title: str, message: str):
        """Initialize confirm modal.

        Args:
            title: Modal title
            message: Confirmation message
        """
        super().__init__()
        self.modal_title = title
        self.modal_message = message

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Container(id="confirm-dialog"):
            yield Static(self.modal_title, id="confirm-title")
            yield Static(self.modal_message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("✅ Yes", variant="success", id="yes")
                yield Button("❌ No", variant="error", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "yes":
            self.dismiss(True)
        elif event.button.id == "no":
            self.dismiss(False)


class ProgressModal(ModalScreen):
    """Modal screen for showing copy progress."""

    CSS = """
    ProgressModal {
        align: center middle;
        max-height: 80;
    }

    #progress-dialog {
        width: 90;
        height: auto;
        max-height: 80;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #progress-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #progress-content {
        width: 100%;
        height: auto;
        padding: 1;
        layout: vertical;
    }

    #progress-status {
        width: 100%;
        color: $text;
    }

    ProgressBar {
        width: 1fr;
        max-width: 100%;
        margin-top: 1;
        margin-bottom: 1;
    }

    #progress-bar {
        width: 1fr;
        max-width: 100%;
    }

    #progress-stats {
        width: 100%;
        color: $text-muted;
        margin-top: 1;
    }

    #progress-buttons {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin-top: 1;
    }

    #progress-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, title: str = "📦 Copying Files", total_items: int = 0, cancel_callback: Optional[Callable] = None):
        """Initialize progress modal.

        Args:
            title: Modal title
            total_items: Total number of items to copy
            cancel_callback: Optional callback to cancel the operation
        """
        super().__init__()
        self.title = title
        self.status_messages: List[str] = []
        self.current_progress = 0.0
        self.start_time = None
        self.total_items = total_items
        self.completed_items = 0
        self.cancel_callback = cancel_callback
        self.cancelled = False

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        from datetime import datetime

        # Record start time when modal is created
        self.start_time = datetime.now()

        logging.debug("=== ProgressModal compose() ===")

        with Container(id="progress-dialog"):
            yield Static(self.title, id="progress-title")
            with Vertical(id="progress-content"):
                yield Static("", id="progress-status")
                yield ProgressBar(total=100, show_eta=False, id="progress-bar")
                yield Static("", id="progress-stats")
            with Horizontal(id="progress-buttons"):
                yield Button("❌ Cancel", variant="error", id="cancel-copy")

    def on_mount(self) -> None:
        """Start the stats update timer when modal is mounted."""
        logging.debug("=== ProgressModal on_mount() ===")

        try:
            # Make dialog focusable and focus it to prevent focusing the cancel button
            dialog = self.query_one("#progress-dialog")
            dialog.can_focus = True
            dialog.focus()

            # Log widget sizes
            content = self.query_one("#progress-content")
            progress_bar = self.query_one("#progress-bar")

            logging.debug(f"Dialog size: {dialog.size}, region: {dialog.region}")
            logging.debug(f"Content size: {content.size}, region: {content.region}")
            logging.debug(f"ProgressBar size: {progress_bar.size}, region: {progress_bar.region}")
            logging.debug(f"ProgressBar styles - width: {progress_bar.styles.width}, min_width: {progress_bar.styles.min_width}")
        except Exception as e:
            logging.debug(f"Error logging sizes or setting focus: {e}")

        self.set_interval(0.5, self.update_stats)
        self.update_stats()

    def update_total_items(self, total: int) -> None:
        """Update the total items count.

        Args:
            total: New total items count
        """
        self.total_items = total
        # Force update stats display
        self.update_stats()

    def update_stats(self) -> None:
        """Update statistics display."""
        from datetime import datetime, timedelta

        if not self.start_time:
            return

        try:
            stats_widget = self.query_one("#progress-stats", Static)

            # Calculate elapsed time
            elapsed = datetime.now() - self.start_time
            elapsed_str = str(timedelta(seconds=int(elapsed.total_seconds())))

            # Calculate ETA
            if self.current_progress > 0:
                total_seconds = elapsed.total_seconds() / (self.current_progress / 100)
                remaining_seconds = total_seconds - elapsed.total_seconds()
                eta_str = str(timedelta(seconds=int(remaining_seconds)))
            else:
                eta_str = "calculating..."

            # Build stats display - show times and file count in one line
            time_info = f"🕐 {self.start_time.strftime('%H:%M:%S')} | ⏱️ {elapsed_str} | ⏳ {eta_str}"

            # Add file count to the same line if available
            if self.total_items > 0:
                time_info += f" | 📊 {self.completed_items}/{self.total_items} files"
            else:
                time_info += f" | 📊 calculating..."

            stats_widget.update(time_info)
        except:
            # Widget not mounted yet
            pass

    def update_status(self, message: str, replace_last: bool = False) -> None:
        """Update progress status message.

        Args:
            message: Message to display
            replace_last: If True, replace the last message instead of appending
        """
        import re

        # Check if this is a progress update (contains percentage)
        percentage_match = re.search(r'\((\d+)%\)', message)
        
        if replace_last and self.status_messages:
            self.status_messages[-1] = message
        elif percentage_match:
            percentage = int(percentage_match.group(1))
            
            # Extract filename from message
            # Assuming format: "📄 filename: size / total (50%)"
            filename_match = re.search(r'📄 (.+?):', message)
            
            if filename_match and self.status_messages:
                current_filename = filename_match.group(1)
                last_msg = self.status_messages[-1]
                last_filename_match = re.search(r'📄 (.+?):', last_msg)
                
                if last_filename_match and last_filename_match.group(1) == current_filename:
                    # Replace last message for same file
                    self.status_messages[-1] = message
                else:
                    # New file - append
                    self.status_messages.append(message)
            else:
                # First message - append
                self.status_messages.append(message)

            # Increment counter whenever any file reaches 100%
            if percentage == 100:
                self.completed_items += 1
        else:
            # Not a progress update - append normally
            self.status_messages.append(message)

        # Keep last 50 messages
        if len(self.status_messages) > 50:
            self.status_messages = self.status_messages[-50:]

        try:
            status_widget = self.query_one("#progress-status", Static)
            status_widget.update("\n".join(self.status_messages))

            # Extract percentage from message if present (e.g., "50%")
            if percentage_match:
                percentage = float(percentage_match.group(1))
                self.current_progress = percentage
                progress_bar = self.query_one("#progress-bar", ProgressBar)
                progress_bar.update(progress=percentage)
        except:
            # Widget not mounted yet, will update on next call
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle cancel button press."""
        if event.button.id == "cancel-copy":
            self.cancelled = True
            # Call cancel callback if provided
            if self.cancel_callback:
                self.cancel_callback()
            # Update status to show cancellation
            self.update_status("❌ Cancelling copy operation...")
            # Dismiss the modal
            self.dismiss(False)


class FileBrowser(App):
    """Interactive file browser with multi-selection support."""

    TITLE = "SCP Interactive"
    ENABLE_COMMAND_PALETTE = False

    CSS = """
    Screen {
        background: $surface;
    }

    #current-path {
        height: 3;
        padding: 1 2;
        background: $panel;
        color: $accent;
        text-style: bold;
    }

    #status-bar {
        height: 2;
        padding: 0 2;
        background: $panel;
        color: $success;
    }

    #file-list-container {
        height: 1fr;
        border: solid $primary;
        margin: 0 1;
    }

    ListView {
        height: 100%;
    }

    #search-container {
        height: auto;
        display: none;
        margin: 0 1;
    }

    #search-container.visible {
        display: block;
    }

    #search-input {
        width: 100%;
        border: solid $accent;
    }

    ListItem {
        padding: 0 1;
    }

    ListItem.selected {
        background: $accent 30%;
    }

    ListItem > Label {
        width: 100%;
    }

    #buttons {
        height: auto;
        layout: horizontal;
        align: center middle;
        padding: 0 2;
    }

    Button {
        margin: 0 2;
        min-width: 0;
        width: auto;
        height: auto;
        padding: 0;
        border: heavy transparent;
        background: transparent;
        text-style: bold;
    }

    Button#cancel {
        color: $error;
    }

    Button#copy {
        color: $success;
    }

    Button:hover {
        text-style: bold underline;
    }

    Button:focus {
        text-style: bold reverse;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+a", "select_all", "Select All"),
        Binding("space", "toggle_select", "Toggle Select"),
        Binding("enter", "navigate", "Open/Navigate"),
        Binding("ctrl+enter", "direct_copy", "Direct Copy"),
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+c", "confirm_copy", "Copy Selected"),
        Binding("left", "navigate_parent", "Parent Directory"),
        Binding("/", "start_search", "Search"),
        Binding("n", "next_match", "Next Match"),
        Binding("p", "prev_match", "Previous Match"),
    ]

    def __init__(
        self,
        title: str,
        current_path: str,
        list_files_func: Callable[[str], List[tuple]],
        is_remote: bool = False,
        copy_callback: Optional[Callable[[List[tuple]], bool]] = None,
        target_path: str = "",
        select_destination_mode: bool = False,
        get_dir_size_func: Optional[Callable[[str], int]] = None
    ):
        """Initialize file browser.

        Args:
            title: Browser title
            current_path: Starting directory path
            list_files_func: Function to list files, returns [(name, is_dir, size), ...]
            is_remote: Whether browsing remote filesystem
            copy_callback: Optional callback to copy files, receives [(path, is_dir), ...]
            target_path: Target destination path to display
            select_destination_mode: If True, button says "Copy Here" and callback receives current dir
            get_dir_size_func: Optional function to calculate directory size (remote or local)
        """
        super().__init__()
        self.browser_title = title
        self.current_path = current_path
        self.list_files_func = list_files_func
        self.is_remote = is_remote
        self.copy_callback = copy_callback
        self.target_path = target_path
        self.select_destination_mode = select_destination_mode
        self.get_dir_size_func = get_dir_size_func
        self.selected_files: List[str] = []
        self.all_items: List[FileListItem] = []
        self._last_click_time = 0
        self._last_click_index = None
        self.transfer_records = []  # Track all transfers: [(filename, size, duration), ...]
        # Search state
        self.search_term = ""
        self.search_matches: List[int] = []  # Indices of matching items
        self.current_match_index = 0  # Current position in search_matches list
        self.search_mode = False
        # Worker tracking for cancellation
        self.active_workers = []  # Track all active copy workers

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        path_display = f"{self.browser_title} 📂 {self.current_path}"
        if self.target_path:
            path_display += f" → {self.target_path}"
        yield Static(path_display, id="current-path")
        yield Static("", id="status-bar")

        with Container(id="file-list-container"):
            yield ListView(id="file-list")

        # Search bar (hidden by default)
        with Container(id="search-container"):
            yield Input(placeholder="🔍 Search (type to search keyword, Enter to navigate, Esc to cancel)...", id="search-input")

        with Horizontal(id="buttons"):
            yield Button("⭕ Close Window", id="cancel")
            label = "📋 Copy Here" if self.select_destination_mode else "📋 Copy Selected"
            yield Button(label, id="copy")

        yield Footer()

    def on_mount(self) -> None:
        """Handle mount event."""
        self.refresh_file_list()
        # Show initial tip (stays visible until user takes action)
        self.update_status("💡 Select file(s) to copy.", "info", auto_clear=False)

    def on_unmount(self) -> None:
        """Handle unmount event - cancel workers and display transfer summary."""
        # 🛑 Cancel all active copy workers when unmounting
        logging.debug(f"🛑 on_unmount: Cancelling {len(self.active_workers)} active workers...")
        for worker in self.active_workers:
            try:
                if not worker.is_finished:
                    worker.cancel()
                    logging.debug(f"  Cancelled worker: {worker}")
            except Exception as e:
                logging.debug(f"  Error cancelling worker: {e}")
        self.active_workers.clear()

        # Display transfer summary
        self.display_transfer_summary()

    def display_transfer_summary(self):
        """Display summary of all transfers on console."""
        if not self.transfer_records:
            return

        from rich.console import Console
        from rich.table import Table

        console = Console()
        console.print("\n")
        console.print("📊 Transfer Summary", style="bold green")
        console.print()

        # Create table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("From", style="cyan")
        table.add_column("To", style="cyan")
        table.add_column("Size", justify="right", style="yellow")
        table.add_column("Time", justify="right", style="green")

        total_size = 0
        total_time = 0

        for record in self.transfer_records:
            # Format size
            size_bytes = record['size']
            total_size += size_bytes
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                size_str = f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

            # Format time
            duration = record['duration']
            total_time += duration
            if duration < 1:
                time_str = f"{duration * 1000:.0f}ms"
            elif duration < 60:
                time_str = f"{duration:.2f}s"
            else:
                minutes = int(duration // 60)
                seconds = duration % 60
                time_str = f"{minutes}m {seconds:.0f}s"

            # Use full paths for clickability in terminal
            source = record['source']
            target = record['target']

            table.add_row(source, target, size_str, time_str)

        console.print(table)

        # Display totals
        console.print()
        console.print(f"✨ Total: {len(self.transfer_records)} item(s)", style="bold green")

        # Format total size
        if total_size < 1024 * 1024:
            total_size_str = f"{total_size / 1024:.1f} KB"
        elif total_size < 1024 * 1024 * 1024:
            total_size_str = f"{total_size / (1024 * 1024):.1f} MB"
        else:
            total_size_str = f"{total_size / (1024 * 1024 * 1024):.1f} GB"

        # Format total time
        if total_time < 60:
            total_time_str = f"{total_time:.2f}s"
        else:
            minutes = int(total_time // 60)
            seconds = total_time % 60
            total_time_str = f"{minutes}m {seconds:.0f}s"

        console.print(f"📦 Total size: {total_size_str}", style="bold yellow")
        console.print(f"⏱️  Total time: {total_time_str}", style="bold cyan")
        console.print()

    def count_files_recursive(self, path: str, is_dir: bool) -> int:
        """Count total number of files recursively.

        Args:
            path: File or directory path
            is_dir: Whether the path is a directory

        Returns:
            Total number of files (not directories)
        """
        if not is_dir:
            return 1

        total = 0
        try:
            items = self.list_files_func(path)
            for item in items:
                name = item[0]
                item_is_dir = item[1]
                
                # Skip parent directory entry if present
                if name == "..":
                    continue

                if item_is_dir:
                    # Recursively count files in subdirectory
                    if self.is_remote:
                        subdir_path = f"{path.rstrip('/')}/{name}"
                    else:
                        subdir_path = str(Path(path) / name)
                    total += self.count_files_recursive(subdir_path, True)
                else:
                    # It's a file
                    total += 1
        except Exception as e:
            logging.debug(f"Error counting files in {path}: {e}")
            # Return 1 as fallback if we can't count
            return 1

        return total if total > 0 else 1

    def update_status(self, message: str, status: str = "success", auto_clear: bool = True):
        """Update status bar.

        Args:
            message: Status message to display
            status: Status type (success, error, info)
            auto_clear: Whether to auto-clear the message after 3 seconds
        """
        status_widget = self.query_one("#status-bar", Static)
        if status == "success":
            status_widget.update(f"✅ [green]{message}[/green]")
        elif status == "error":
            status_widget.update(f"❌ [red]{message}[/red]")
        else:
            # For info status, check if message already starts with emoji
            if message.startswith(("💡", "☑️", "ℹ️")):
                status_widget.update(f"[cyan]{message}[/cyan]")
            else:
                status_widget.update(f"ℹ️  [cyan]{message}[/cyan]")

        # Restore selection status after 3 seconds if auto_clear is True
        if auto_clear:
            self.set_timer(3, self.update_selection_status)

    def update_selection_status(self):
        """Update status bar with selection count."""
        # Count selected files and folders separately
        selected_files = sum(1 for item in self.all_items if item.is_selected and not item.is_directory)
        selected_folders = sum(1 for item in self.all_items if item.is_selected and item.is_directory)

        if selected_files > 0 or selected_folders > 0:
            parts = []
            if selected_files > 0:
                parts.append(f"{selected_files} file(s)")
            if selected_folders > 0:
                parts.append(f"{selected_folders} folder(s)")
            selection_text = ", ".join(parts)
            self.update_status(f"☑️ Selected {selection_text}. Press Ctrl+Enter to copy now.", "info", auto_clear=False)
        else:
            self.update_status("💡 Select file(s) or folder(s) to copy.", "info", auto_clear=False)

    def record_transfers(self, items: List[tuple], duration: float):
        """Record transferred files for summary display.

        Args:
            items: List of (path, is_dir) tuples that were transferred
            duration: Total transfer duration in seconds
        """
        for path, is_dir in items:
            from pathlib import Path
            filename = Path(path).name
            # Get size - for directories, calculate total size of all files
            size = 0
            if is_dir:
                # Calculate actual size by recursively summing all files
                size = self._calculate_directory_size(path)
            else:
                # Get size from items list for files
                for item in self.all_items:
                    if item.file_name == filename:
                        size = item.file_size
                        break

            # Determine source and target based on interactive side
            source_path = path
            target_path = str(Path(self.target_path.replace("🌐 ", "").replace("💻 ", "")) / filename)

            self.transfer_records.append({
                'filename': filename,
                'source': source_path,
                'target': target_path,
                'size': size,
                'duration': duration,
                'is_dir': is_dir
            })

    def _calculate_directory_size(self, dir_path: str) -> int:
        """Calculate total size of all files in a directory recursively.

        Args:
            dir_path: Path to the directory

        Returns:
            Total size in bytes
        """
        total_size = 0
        try:
            if self.is_remote:
                # For remote directories, use SFTP to calculate size
                if self.get_dir_size_func:
                    return self.get_dir_size_func(dir_path)
                return 0
            else:
                # For local directories, walk through all files
                from pathlib import Path
                path_obj = Path(dir_path)
                if path_obj.exists() and path_obj.is_dir():
                    for item in path_obj.rglob('*'):
                        if item.is_file():
                            try:
                                total_size += item.stat().st_size
                            except (OSError, PermissionError):
                                # Skip files we can't access
                                pass
        except Exception:
            # If we can't calculate, return 0
            pass

        return total_size

    def refresh_file_list(self):
        """Refresh the file list."""
        logging.debug(f"refresh_file_list called for path: {self.current_path}")
        list_view = self.query_one("#file-list", ListView)
        list_view.clear()
        self.all_items.clear()

        # Add parent directory
        parent_item = FileListItem("..", True, 0)
        self.all_items.append(parent_item)
        list_view.append(parent_item)

        try:
            # Add files and directories
            logging.debug("Calling list_files_func...")
            files = self.list_files_func(self.current_path)
            logging.debug(f"list_files_func returned {len(files)} items")
            
            for file_info in files:
                # Handle both old format (6 elements) and new format (8 elements)
                if len(file_info) >= 8:
                    name, is_dir, size, is_symlink, symlink_target, target_is_dir, ctime, mtime = file_info[:8]
                else:
                    name, is_dir, size, is_symlink, symlink_target, target_is_dir = file_info[:6]
                    ctime, mtime = 0, 0

                item = FileListItem(name, is_dir, size, is_symlink, symlink_target, target_is_dir, ctime, mtime)
                self.all_items.append(item)
                list_view.append(item)
        except Exception as e:
            logging.error(f"Error in refresh_file_list: {e}", exc_info=True)
            self.update_status(f"Error listing files: {e}", "error")

        # Update path label
        path_label = self.query_one("#current-path", Static)
        path_display = f"{self.browser_title} 📂 {self.current_path}"
        if self.target_path:
            path_display += f" → {self.target_path}"
        path_label.update(path_display)

    def action_toggle_select(self):
        """Toggle selection of current item."""
        logging.debug("=== action_toggle_select() called (Space key) ===")
        
        # In destination selection mode, we don't allow selecting files
        if self.select_destination_mode:
            return

        list_view = self.query_one("#file-list", ListView)
        if list_view.index is not None:
            item = self.all_items[list_view.index]
            logging.debug(f"Toggling selection for: {item.file_name}")
            item.toggle_selection()
            self.refresh()
            self.update_selection_status()

    def action_select_all(self):
        """Select all files (except parent dir)."""
        for item in self.all_items:
            if item.file_name != ".." and not item.is_selected:
                item.toggle_selection()
        self.refresh()
        self.update_selection_status()

    def action_navigate_parent(self):
        """Navigate to parent directory using left arrow key."""
        logging.debug("=== action_navigate_parent() called (Left arrow key) ===")

        # Navigate to parent directory
        old_path = self.current_path

        if self.is_remote:
            # For remote, handle path manually
            parts = self.current_path.rstrip('/').split('/')
            if len(parts) > 1:
                self.current_path = '/'.join(parts[:-1]) or '/'
            else:
                self.current_path = '/'
        else:
            parent = Path(self.current_path).parent
            self.current_path = str(parent)

        logging.debug(f"⬅️  Navigated to parent: {old_path} -> {self.current_path}")
        self.refresh_file_list()

    def action_start_search(self):
        """Start search mode - show search input."""
        logging.debug("=== action_start_search() called (/ key) ===")
        search_container = self.query_one("#search-container")
        search_input = self.query_one("#search-input", Input)

        # Show search container
        search_container.add_class("visible")
        self.search_mode = True

        # Focus on search input and clear any previous search
        search_input.value = ""
        search_input.focus()

        # Clear previous search results
        self.search_matches = []
        self.current_match_index = 0

        self.update_status("🔍 Search mode active. Type to search keyword, Enter to navigate, Esc to cancel.", "info", auto_clear=False)

    def action_next_match(self):
        """Navigate to next search match."""
        if not self.search_matches:
            self.update_status("⚠️  No search results. Press / to search.", "info")
            return

        # Move to next match (wrap around)
        self.current_match_index = (self.current_match_index + 1) % len(self.search_matches)
        self.navigate_to_match()

    def action_prev_match(self):
        """Navigate to previous search match."""
        if not self.search_matches:
            self.update_status("⚠️  No search results. Press / to search.", "info")
            return

        # Move to previous match (wrap around)
        self.current_match_index = (self.current_match_index - 1) % len(self.search_matches)
        self.navigate_to_match()

    def navigate_to_match(self):
        """Navigate list view to current search match."""
        if not self.search_matches or self.current_match_index >= len(self.search_matches):
            return

        match_index = self.search_matches[self.current_match_index]
        list_view = self.query_one("#file-list", ListView)
        list_view.index = match_index

        # Update status to show current position
        match_item = self.all_items[match_index]
        self.update_status(
            f"Match {self.current_match_index + 1}/{len(self.search_matches)}: {match_item.file_name}",
            "info",
            auto_clear=False
        )

    def perform_search(self, search_term: str):
        """Search for items matching the search term.

        Args:
            search_term: The search keyword to filter items
        """
        self.search_term = search_term.lower()
        self.search_matches = []
        self.current_match_index = 0

        if not self.search_term:
            # Empty search - show all items
            self.update_status("💡 Select file(s) to copy.", "info", auto_clear=False)
            return

        # Find all matching items (case-insensitive)
        for i, item in enumerate(self.all_items):
            if item.file_name == "..":
                continue  # Skip parent directory
            if self.search_term in item.file_name.lower():
                self.search_matches.append(i)

        # Update status
        if self.search_matches:
            # Navigate to first match
            self.navigate_to_match()
        else:
            self.update_status(f"❌ No matches found for '{search_term}'", "info", auto_clear=False)

    def action_navigate(self):
        """Navigate into directory or select file."""
        logging.debug("=== action_navigate() called ===")
        # Clean up finished workers
        self._cleanup_finished_workers()

        list_view = self.query_one("#file-list", ListView)
        logging.debug(f"ListView index: {list_view.index}")

        if list_view.index is None:
            logging.debug("No item selected, returning")
            return

        item = self.all_items[list_view.index]
        logging.debug(f"Selected item: name='{item.file_name}', is_directory={item.is_directory}")

        # Construct full path
        if self.is_remote:
            full_path = f"{self.current_path.rstrip('/')}/{item.file_name}"
        else:
            full_path = str(Path(self.current_path) / item.file_name)

        if not item.is_directory:
            # If it's a file, ask to copy it immediately
            logging.debug(f"Item '{item.file_name}' is a file")
            
            # In destination selection mode, clicking a file shouldn't do anything 
            # (we are selecting the current folder)
            if self.select_destination_mode:
                self.update_status("Cannot copy into a file. Please select 'Copy Here' to copy to current folder.", "warning")
                return

            def handle_confirm(result: bool):
                if result:
                    # User confirmed - copy immediately
                    # Call copy callback if available
                    if self.copy_callback:
                        # 📊 Calculate file count before starting worker (to avoid thread issues)
                        file_count = self.count_files_recursive(full_path, item.is_directory)

                        # Worker reference for cancellation
                        worker = None

                        # Cancel callback
                        def cancel_copy():
                            """Cancel the copy operation."""
                            if worker:
                                worker.cancel()

                        # Show progress modal with cancel callback
                        progress_modal = ProgressModal(title="📦 Copying File", total_items=file_count, cancel_callback=cancel_copy)
                        
                        def on_modal_close(result=None):
                            self.query_one("#file-list").focus()

                        self.push_screen(progress_modal, on_modal_close)

                        # Create progress callback that updates on main thread
                        def update_progress(message: str):
                            """Update progress modal."""
                            if not progress_modal.cancelled:
                                self.call_from_thread(progress_modal.update_status, message)

                        # Run copy in worker thread
                        def do_copy():
                            """Perform copy operation in background."""
                            import time
                            start_time = time.time()
                            try:
                                logging.debug(f"do_copy: Calling copy_callback with path={full_path}, is_dir=False")
                                # 🛑 Create cancel check function
                                def is_cancelled():
                                    return progress_modal.cancelled
                                success = self.copy_callback([(full_path, False)], update_progress, cancel_check=is_cancelled)
                                duration = time.time() - start_time
                                logging.debug(f"do_copy: copy_callback returned success={success}")
                                # Dismiss modal and show result on main thread
                                if not progress_modal.cancelled:
                                    self.call_from_thread(self.pop_screen)
                                    if success:
                                        logging.debug(f"do_copy: Copy reported as successful")
                                        # Record transfer
                                        self.record_transfers([(full_path, False)], duration)
                                        self.call_from_thread(self.update_status, f"Copied '{item.file_name}' successfully!", "success")
                                        
                                        # Wait 5s with countdown
                                        for i in range(5, 0, -1):
                                            if progress_modal.cancelled:
                                                break
                                            self.call_from_thread(progress_modal.update_status, f"✅ Completed! Closing in {i}s...")
                                            time.sleep(1)

                                    else:
                                        logging.debug(f"do_copy: Copy reported as failed")
                                        self.call_from_thread(self.update_status, f"Failed to copy '{item.file_name}'", "error")
                                    
                                    if not progress_modal.cancelled:
                                        self.call_from_thread(self.pop_screen)
                            except Exception as e:
                                logging.error(f"do_copy: Exception occurred: {e}", exc_info=True)
                                if not progress_modal.cancelled:
                                    self.call_from_thread(self.pop_screen)
                                    self.call_from_thread(self.update_status, f"Error: {str(e)}", "error")

                        worker = self.run_worker(do_copy, thread=True)
                        self.active_workers.append(worker)  # Track worker for cancellation
                    else:
                        # No callback - exit with file (old behavior)
                        self.exit([(full_path, False)])
                else:
                    # User declined - just toggle selection
                    item.toggle_selection()
                    self.refresh()
                    self.query_one("#file-list").focus()

            # Build confirmation message
            size_str = item._format_size(item.file_size)
            message = f"Copy '{item.file_name}' ({size_str}) now?\n"
            if item.is_symlink:
                message += f"\n🔗 This is a symbolic link to:\n   {item.symlink_target}\n"
            message += f"\nSelect 'Yes' to copy the real file immediately,\nor 'No' to add to selection."

            self.push_screen(
                ConfirmModal(
                    title="📄 Copy File Now?",
                    message=message
                ),
                handle_confirm
            )
            return

        # Navigate to directory
        logging.debug("Item is a directory, navigating...")
        old_path = self.current_path

        if item.file_name == "..":
            logging.debug("Navigating to parent directory")
            # Go to parent
            if self.is_remote:
                # For remote, handle path manually
                parts = self.current_path.rstrip('/').split('/')
                if len(parts) > 1:
                    self.current_path = '/'.join(parts[:-1]) or '/'
                else:
                    self.current_path = '/'
            else:
                parent = Path(self.current_path).parent
                self.current_path = str(parent)
        else:
            logging.debug(f"Navigating into subdirectory: {item.file_name}")
            # Go into subdirectory
            if self.is_remote:
                self.current_path = f"{self.current_path.rstrip('/')}/{item.file_name}"
            else:
                self.current_path = str(Path(self.current_path) / item.file_name)

        logging.debug(f"Path changed: {old_path} -> {self.current_path}")
        logging.debug("Calling refresh_file_list()")
        self.refresh_file_list()
        logging.debug("refresh_file_list() completed")

    def _cleanup_finished_workers(self):
        """Remove finished workers from active list."""
        self.active_workers = [w for w in self.active_workers if not w.is_finished]

    def action_cancel(self):
        """Cancel and exit."""
        # 🛑 Cancel all active copy workers before exiting
        logging.debug(f"🛑 Cancelling {len(self.active_workers)} active workers...")
        for worker in self.active_workers:
            try:
                if not worker.is_finished:
                    worker.cancel()
                    logging.debug(f"  Cancelled worker: {worker}")
            except Exception as e:
                logging.debug(f"  Error cancelling worker: {e}")
        self.active_workers.clear()
        self.exit([])

    def action_direct_copy(self):
        """Direct copy current item without confirmation."""
        # Clean up finished workers
        self._cleanup_finished_workers()

        list_view = self.query_one("#file-list", ListView)
        if list_view.index is None:
            return

        item = self.all_items[list_view.index]

        # Skip parent directory
        if item.file_name == "..":
            return

        # Get full path
        if self.is_remote:
            full_path = f"{self.current_path.rstrip('/')}/{item.file_name}"
        else:
            full_path = str(Path(self.current_path) / item.file_name)

        # Call copy callback if available
        if self.copy_callback:
            # 📊 Calculate file count before starting worker (to avoid thread issues)
            file_count = self.count_files_recursive(full_path, item.is_directory)

            # Worker reference for cancellation
            worker = None

            # Cancel callback
            def cancel_copy():
                """Cancel the copy operation."""
                if worker:
                    worker.cancel()

            # Show progress modal with cancel callback
            item_type = "Directory" if item.is_directory else "File"
            progress_modal = ProgressModal(title=f"📦 Copying {item_type}", total_items=file_count, cancel_callback=cancel_copy)
            
            def on_modal_close(result=None):
                self.query_one("#file-list").focus()

            self.push_screen(progress_modal, on_modal_close)

            # Create progress callback that updates on main thread
            def update_progress(message: str):
                """Update progress modal."""
                if not progress_modal.cancelled:
                    self.call_from_thread(progress_modal.update_status, message)

            # Run copy in worker thread
            def do_copy():
                """Perform copy operation in background."""
                import time
                start_time = time.time()
                try:
                    # 🛑 Create cancel check function
                    def is_cancelled():
                        return progress_modal.cancelled
                    # Perform the copy
                    success = self.copy_callback([(full_path, item.is_directory)], update_progress, cancel_check=is_cancelled)
                    duration = time.time() - start_time
                    # Dismiss modal and show result on main thread
                    if not progress_modal.cancelled:
                        if success:
                            # Record transfer
                            self.record_transfers([(full_path, item.is_directory)], duration)
                            self.call_from_thread(self.update_status, f"Copied '{item.file_name}' successfully!", "success")
                            
                            # Wait 5s with countdown
                            # Initial message
                            self.call_from_thread(progress_modal.update_status, f"✅ Completed! Closing in 5s...")
                            time.sleep(1)
                            
                            for i in range(4, 0, -1):
                                if progress_modal.cancelled:
                                    break
                                self.call_from_thread(progress_modal.update_status, f"✅ Completed! Closing in {i}s...", replace_last=True)
                                time.sleep(1)
                            
                            if not progress_modal.cancelled:
                                self.call_from_thread(self.pop_screen)
                        else:
                            self.call_from_thread(self.pop_screen)
                            self.call_from_thread(self.update_status, f"Failed to copy '{item.file_name}'", "error")
                except Exception as e:
                    if not progress_modal.cancelled:
                        self.call_from_thread(self.pop_screen)
                        self.call_from_thread(self.update_status, f"Error: {str(e)}", "error")

            worker = self.run_worker(do_copy, thread=True)
            self.active_workers.append(worker)  # Track worker for cancellation
        else:
            # No callback - exit with item (old behavior)
            self.exit([(full_path, item.is_directory)])

    def action_confirm_copy(self):
        """Confirm copy of selected files."""
        self.confirm_selection()

    def confirm_selection(self):
        """Confirm selected files and copy or exit."""
        # Clean up finished workers
        self._cleanup_finished_workers()

        selected = []

        # If in destination selection mode, use current path
        if self.select_destination_mode:
            # Use current path as target
            # Pass tuple (path, is_dir=True)
            selected.append((self.current_path, True))
        else:
            # Normal mode: gather selected items
            for item in self.all_items:
                if item.is_selected:
                    if self.is_remote:
                        full_path = f"{self.current_path.rstrip('/')}/{item.file_name}"
                    else:
                        full_path = str(Path(self.current_path) / item.file_name)
                    selected.append((full_path, item.is_directory))

            # If no files selected, use current highlighted item
            if not selected:
                list_view = self.query_one("#file-list", ListView)
                if list_view.index is not None and list_view.index < len(self.all_items):
                    item = self.all_items[list_view.index]
                    # Skip parent directory
                    if item.file_name == "..":
                        self.update_status("Cannot copy parent directory", "info")
                        return

                    if self.is_remote:
                        full_path = f"{self.current_path.rstrip('/')}/{item.file_name}"
                    else:
                        full_path = str(Path(self.current_path) / item.file_name)
                    selected.append((full_path, item.is_directory))
                    logging.debug(f"No selection, using highlighted item: {item.file_name}")
                else:
                    self.update_status("No files selected", "info")
                    return

        # Call copy callback if available
        if self.copy_callback:
            # 📊 Calculate total files before starting worker (to avoid thread issues)
            total_files = 0
            
            if self.select_destination_mode:
                # In destination mode, we don't count files here (callback handles source items)
                total_files = 1 # Dummy count
            else:
                for path, is_dir in selected:
                    total_files += self.count_files_recursive(path, is_dir)

            # Worker reference for cancellation
            worker = None

            # Cancel callback
            def cancel_copy():
                """Cancel the copy operation."""
                if worker:
                    worker.cancel()

            # Show progress modal with cancel callback
            count = len(selected)
            if self.select_destination_mode:
                title_str = "📦 Copying to Target..."
            else:
                title_str = f"📦 Copying {count} Item(s)"
            
            progress_modal = ProgressModal(title=title_str, total_items=total_files, cancel_callback=cancel_copy)
            
            def on_modal_close(result=None):
                self.query_one("#file-list").focus()

            self.push_screen(progress_modal, on_modal_close)

            # Create progress callback that updates on main thread
            def update_progress(message: str):
                """Update progress modal."""
                if not progress_modal.cancelled:
                    self.call_from_thread(progress_modal.update_status, message)

            # Run copy in worker thread
            def do_copy():
                """Perform copy operation in background."""
                import time
                start_time = time.time()
                try:
                    # 🛑 Create cancel check function
                    def is_cancelled():
                        return progress_modal.cancelled
                    
                    success = self.copy_callback(selected, update_progress, cancel_check=is_cancelled)
                    
                    duration = time.time() - start_time
                    # Dismiss modal and show result on main thread
                    if not progress_modal.cancelled:
                        if success:
                            if not self.select_destination_mode:
                                self.record_transfers(selected, duration)
                            self.call_from_thread(self.update_status, "Copy completed successfully!", "success")
                            # Refresh list to show new files if we are in the target
                            self.call_from_thread(self.refresh_file_list)
                            
                            # Wait 5s with countdown
                            # Initial message
                            self.call_from_thread(progress_modal.update_status, f"✅ Completed! Closing in 5s...")
                            time.sleep(1)
                            
                            for i in range(4, 0, -1):
                                if progress_modal.cancelled:
                                    break
                                self.call_from_thread(progress_modal.update_status, f"✅ Completed! Closing in {i}s...", replace_last=True)
                                time.sleep(1)
                            
                            if not progress_modal.cancelled:
                                self.call_from_thread(self.pop_screen)

                        else:
                            self.call_from_thread(self.pop_screen)
                            self.call_from_thread(self.update_status, "Copy failed or incomplete", "error")
                except Exception as e:
                    if not progress_modal.cancelled:
                        self.call_from_thread(self.pop_screen)
                        self.call_from_thread(self.update_status, f"Error: {str(e)}", "error")

            worker = self.run_worker(do_copy, thread=True)
            self.active_workers.append(worker)  # Track worker for cancellation
        else:
            # No callback - exit with selected items
            self.exit(selected)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "cancel":
            self.action_cancel()
        elif event.button.id == "copy":
            self.confirm_selection()

    def on_key(self, event) -> None:
        """Handle key press events."""
        # Handle Escape key in search mode
        if event.key == "escape" and self.search_mode:
            logging.debug("Escape pressed in search mode - exiting search")
            # Hide search container
            search_container = self.query_one("#search-container")
            search_container.remove_class("visible")
            self.search_mode = False

            # Refocus on file list
            list_view = self.query_one("#file-list", ListView)
            list_view.focus()

            # Clear search results
            self.search_matches = []
            self.search_term = ""
            self.update_status("💡 Select file(s) to copy.", "info", auto_clear=False)
            event.prevent_default()
            event.stop()
            return

        if event.key == "enter":
            # Check if search input is currently focused
            focused = self.focused
            if isinstance(focused, Input):
                # Let the input handle the Enter key
                logging.debug("Enter key pressed on input, letting input handle it")
                return

            # Check if a button is currently focused
            if isinstance(focused, Button):
                # Let the button handle the Enter key
                logging.debug("Enter key pressed on button, letting button handle it")
                return

            # Enter key pressed - navigate directly
            logging.debug("Enter key pressed! Calling action_navigate()")
            self.action_navigate()
            event.prevent_default()  # Prevent ListView from handling it
            event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes - perform search as user types."""
        if event.input.id == "search-input":
            search_term = event.value
            logging.debug(f"Search input changed: '{search_term}'")
            self.perform_search(search_term)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission - hide search and keep current match."""
        if event.input.id == "search-input":
            logging.debug("Search input submitted (Enter pressed)")
            # Hide search container
            search_container = self.query_one("#search-container")
            search_container.remove_class("visible")
            self.search_mode = False

            # Refocus on file list
            list_view = self.query_one("#file-list", ListView)
            list_view.focus()

            # Keep the current match highlighted
            if self.search_matches:
                self.update_status(
                    f"✅ Found {len(self.search_matches)} match(es). Use 'n' for next, 'p' for previous.",
                    "success",
                    auto_clear=False
                )

            # Prevent event from propagating to other handlers
            event.prevent_default()
            event.stop()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection event (fires on mouse click only)."""
        import time

        logging.debug(f"on_list_view_selected: index={event.list_view.index}")

        current_time = time.time()
        current_index = event.list_view.index

        # Detect double-click: same item selected within 0.5 seconds
        if (current_index == self._last_click_index and
            current_time - self._last_click_time < 0.5):
            # Double-click detected - navigate into folder
            logging.debug("  Double-click detected! Calling action_navigate()")
            self.action_navigate()
            # Reset click tracking
            self._last_click_time = 0
            self._last_click_index = None
        else:
            # Single click - just focus on item (don't navigate)
            logging.debug("  Single click - focusing on item only")
            self._last_click_time = current_time
            self._last_click_index = current_index
