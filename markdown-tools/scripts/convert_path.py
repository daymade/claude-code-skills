#!/usr/bin/env python3
"""
Convert Windows paths to WSL format.

Usage:
    python convert_path.py "C:\\Users\\username\\Downloads\\file.doc"

Output:
    /mnt/c/Users/username/Downloads/file.doc
"""

import sys
import re


def convert_windows_to_wsl(windows_path: str) -> str:
    """
    Convert a Windows path to WSL format.

    Args:
        windows_path: Windows path (e.g., "C:\\Users\\username\\file.doc")

    Returns:
        WSL path (e.g., "/mnt/c/Users/username/file.doc")
    """
    # Remove quotes if present
    path = windows_path.strip('"').strip("'")

    # Handle drive letter (C:\ or C:/)
    drive_pattern = r'^([A-Za-z]):[\\\/]'
    match = re.match(drive_pattern, path)

    if not match:
        # Already a WSL path or relative path
        return path

    drive_letter = match.group(1).lower()
    path_without_drive = path[3:]  # Remove "C:\"

    # Replace backslashes with forward slashes
    path_without_drive = path_without_drive.replace('\\', '/')

    # Construct WSL path
    wsl_path = f"/mnt/{drive_letter}/{path_without_drive}"

    return wsl_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_path.py <windows_path>")
        print('Example: python convert_path.py "C:\\Users\\username\\Downloads\\file.doc"')
        sys.exit(1)

    windows_path = sys.argv[1]
    wsl_path = convert_windows_to_wsl(windows_path)
    print(wsl_path)


if __name__ == "__main__":
    main()