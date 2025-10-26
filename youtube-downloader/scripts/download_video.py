#!/usr/bin/env python3
"""
YouTube video downloader using yt-dlp with robust error handling.

This script handles common issues like nsig extraction failures and network problems,
especially useful for users behind proxies or in regions with YouTube access issues.

Requirements:
    - yt-dlp: Install via `brew install yt-dlp` (macOS) or `pip install yt-dlp` (cross-platform)
    - For high-quality downloads (1080p+): Install PO token provider
      See ../references/po-token-setup.md for setup instructions

Usage:
    scripts/download_video.py "https://youtu.be/VIDEO_ID"
    scripts/download_video.py "https://youtu.be/VIDEO_ID" --audio-only
    scripts/download_video.py "https://youtu.be/VIDEO_ID" -o ~/Downloads

Note:
    This script uses Android client workaround, which provides 360p quality only.
    For 1080p/4K quality, use yt-dlp directly with PO token provider installed.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def download_video(
    url: str,
    output_dir: str = ".",
    format_spec: str = None,
    use_android_client: bool = True,
    audio_only: bool = False,
    list_formats: bool = False,
) -> int:
    """
    Download a YouTube video using yt-dlp.

    Args:
        url: YouTube video URL
        output_dir: Directory to save the downloaded file
        format_spec: Format specification (e.g., "bestvideo+bestaudio/best")
        use_android_client: Use Android client to avoid nsig extraction issues
        audio_only: Download audio only
        list_formats: List available formats instead of downloading

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Check if yt-dlp is installed
    check_result = subprocess.run(
        ["which", "yt-dlp"], capture_output=True, text=True
    )
    if check_result.returncode != 0:
        print("✗ Error: yt-dlp is not installed")
        print("  Install via: brew install yt-dlp  # or: pip install yt-dlp")
        return 1

    # Build yt-dlp command
    cmd = ["yt-dlp"]

    # Use Android client by default to avoid nsig extraction issues
    if use_android_client:
        cmd.extend(["--extractor-args", "youtube:player_client=android"])

    # List formats if requested
    if list_formats:
        cmd.extend(["-F", url])
        result = subprocess.run(cmd)

        # Check if PO token provider might be needed
        if result.returncode == 0 and use_android_client:
            print("\n💡 Tip: Using Android client (360p only).")
            print("   For 1080p/4K, install PO token provider:")
            print("   See ../references/po-token-setup.md for instructions")

        return result.returncode

    # Set output directory
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    cmd.extend(["-P", str(output_path)])

    # Handle audio-only downloads
    if audio_only:
        cmd.extend(["-x", "--audio-format", "mp3"])
    elif format_spec:
        cmd.extend(["-f", format_spec])

    # Add URL
    cmd.append(url)

    # Execute download
    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print(f"\n✓ Download completed successfully!")
        print(f"  Location: {output_path}")
    else:
        print(f"\n✗ Download failed with exit code {result.returncode}")

    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Download YouTube videos using yt-dlp with robust error handling"
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "-f", "--format", help="Format specification (e.g., 'bestvideo+bestaudio/best')"
    )
    parser.add_argument(
        "--no-android-client",
        action="store_true",
        help="Disable Android client workaround",
    )
    parser.add_argument(
        "-a", "--audio-only", action="store_true", help="Download audio only (as MP3)"
    )
    parser.add_argument(
        "-F", "--list-formats", action="store_true", help="List available formats"
    )

    args = parser.parse_args()

    exit_code = download_video(
        url=args.url,
        output_dir=args.output_dir,
        format_spec=args.format,
        use_android_client=not args.no_android_client,
        audio_only=args.audio_only,
        list_formats=args.list_formats,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
