#!/usr/bin/env python3
"""List files with creation and modified times in gray text."""

import os
import sys
from pathlib import Path
from datetime import datetime


def format_time(timestamp):
    """Format timestamp to readable string."""
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')


def list_with_times(directory='.'):
    """List files with creation and modified times."""
    path = Path(directory)

    if not path.exists():
        print(f"Error: {directory} does not exist")
        return

    # ANSI color codes
    GRAY = '\033[90m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

    items = sorted(path.iterdir(), key=lambda x: x.name.lower())

    for item in items:
        try:
            stat = item.stat()
            name = item.name

            # Add trailing slash for directories
            if item.is_dir():
                name = f"{BLUE}{name}/{RESET}"

            # Get creation and modification times
            ctime = format_time(stat.st_birthtime if hasattr(stat, 'st_birthtime') else stat.st_ctime)
            mtime = format_time(stat.st_mtime)

            # Print with gray timestamps
            print(f"{name}\t{GRAY}created: {ctime}\tmodified: {mtime}{RESET}")

        except (OSError, PermissionError) as e:
            print(f"{name}\t{GRAY}Error: {e}{RESET}")


if __name__ == '__main__':
    directory = sys.argv[1] if len(sys.argv) > 1 else '.'
    list_with_times(directory)
