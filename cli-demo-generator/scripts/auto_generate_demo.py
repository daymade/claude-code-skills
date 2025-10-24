#!/usr/bin/env python3
"""
Auto-generate CLI demos from command descriptions.

This script creates VHS tape files and generates GIF demos automatically.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def create_tape_file(
    commands: List[str],
    output_gif: str,
    title: Optional[str] = None,
    theme: str = "Dracula",
    font_size: int = 16,
    width: int = 1400,
    height: int = 700,
    padding: int = 20,
) -> str:
    """Generate a VHS tape file from commands."""

    tape_lines = [
        f'Output {output_gif}',
        '',
        f'Set FontSize {font_size}',
        f'Set Width {width}',
        f'Set Height {height}',
        f'Set Theme "{theme}"',
        f'Set Padding {padding}',
        '',
    ]

    # Add title if provided
    if title:
        tape_lines.extend([
            f'Type "# {title}" Sleep 500ms Enter',
            'Sleep 1s',
            '',
        ])

    # Add commands with smart timing
    for i, cmd in enumerate(commands, 1):
        # Type the command
        tape_lines.append(f'Type "{cmd}" Sleep 500ms')
        tape_lines.append('Enter')

        # Smart sleep based on command complexity
        if any(keyword in cmd.lower() for keyword in ['install', 'build', 'test', 'deploy']):
            sleep_time = '3s'
        elif any(keyword in cmd.lower() for keyword in ['ls', 'pwd', 'echo', 'cat']):
            sleep_time = '1s'
        else:
            sleep_time = '2s'

        tape_lines.append(f'Sleep {sleep_time}')

        # Add spacing between commands
        if i < len(commands):
            tape_lines.append('')

    return '\n'.join(tape_lines)


def main():
    parser = argparse.ArgumentParser(
        description='Auto-generate CLI demos from commands',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Generate demo from single command
  %(prog)s -c "npm install" -o demo.gif

  # Generate demo with multiple commands
  %(prog)s -c "git clone repo" -c "cd repo" -c "npm install" -o setup.gif

  # Custom theme and size
  %(prog)s -c "ls -la" -o demo.gif --theme Monokai --width 1200

  # With title
  %(prog)s -c "echo Hello" -o demo.gif --title "My Demo"
        '''
    )

    parser.add_argument('-c', '--command', action='append', required=True,
                        help='Command to include in demo (can be specified multiple times)')
    parser.add_argument('-o', '--output', required=True,
                        help='Output GIF file path')
    parser.add_argument('--title', help='Demo title (optional)')
    parser.add_argument('--theme', default='Dracula',
                        help='VHS theme (default: Dracula)')
    parser.add_argument('--font-size', type=int, default=16,
                        help='Font size (default: 16)')
    parser.add_argument('--width', type=int, default=1400,
                        help='Terminal width (default: 1400)')
    parser.add_argument('--height', type=int, default=700,
                        help='Terminal height (default: 700)')
    parser.add_argument('--no-execute', action='store_true',
                        help='Generate tape file only, do not execute VHS')

    args = parser.parse_args()

    # Generate tape file content
    tape_content = create_tape_file(
        commands=args.command,
        output_gif=args.output,
        title=args.title,
        theme=args.theme,
        font_size=args.font_size,
        width=args.width,
        height=args.height,
    )

    # Write tape file
    output_path = Path(args.output)
    tape_file = output_path.with_suffix('.tape')

    with open(tape_file, 'w') as f:
        f.write(tape_content)

    print(f"✓ Generated tape file: {tape_file}")

    if not args.no_execute:
        # Check if VHS is installed
        try:
            subprocess.run(['vhs', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("✗ VHS is not installed!", file=sys.stderr)
            print("Install it with: brew install vhs", file=sys.stderr)
            print(f"✓ You can manually run: vhs < {tape_file}", file=sys.stderr)
            return 1

        # Execute VHS
        print(f"Generating GIF: {args.output}")
        try:
            subprocess.run(['vhs', str(tape_file)], check=True)
            print(f"✓ Demo generated: {args.output}")
            print(f"  Size: {output_path.stat().st_size / 1024:.1f} KB")
        except subprocess.CalledProcessError as e:
            print(f"✗ VHS execution failed: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
