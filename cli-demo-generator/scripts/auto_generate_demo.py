#!/usr/bin/env python3
"""
Auto-generate CLI demos from command descriptions.

Creates VHS tape files and generates GIF demos with support for:
- Hidden bootstrap commands (self-cleaning state)
- Output noise filtering via base64-encoded wrapper
- Post-processing speed-up via gifsicle
"""

import argparse
import base64
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
    bootstrap: Optional[List[str]] = None,
    filter_pattern: Optional[str] = None,
) -> str:
    """Generate a VHS tape file from commands."""

    tape_lines = [
        f'Output {output_gif}',
        f'Set Theme "{theme}"',
        f'Set FontSize {font_size}',
        f'Set Width {width}',
        f'Set Height {height}',
        f'Set Padding {padding}',
        'Set TypingSpeed 10ms',
        'Set Shell zsh',
        '',
    ]

    # Hidden bootstrap: cleanup + optional output filter
    has_hidden = bootstrap or filter_pattern
    if has_hidden:
        tape_lines.append('Hide')

        if bootstrap:
            # Combine all bootstrap commands with semicolons
            combined = "; ".join(
                cmd if "2>/dev/null" in cmd else f"{cmd} 2>/dev/null"
                for cmd in bootstrap
            )
            tape_lines.append(f'Type "{combined}"')
            tape_lines.append('Enter')
            tape_lines.append('Sleep 3s')

        if filter_pattern:
            # Create a wrapper function that filters noisy output
            wrapper = f'_wrap() {{ "$@" 2>&1 | grep -v -E "{filter_pattern}"; }}'
            encoded = base64.b64encode(wrapper.encode()).decode()
            tape_lines.append(f'Type "echo {encoded} | base64 -d > /tmp/cw.sh && source /tmp/cw.sh"')
            tape_lines.append('Enter')
            tape_lines.append('Sleep 500ms')

        # Clear screen before Show to prevent hidden text from leaking
        tape_lines.append('Type "clear"')
        tape_lines.append('Enter')
        tape_lines.append('Sleep 500ms')
        tape_lines.append('Show')
        tape_lines.append('')

    # Title
    if title:
        tape_lines.extend([
            f'Type "# {title}" Sleep 500ms Enter',
            'Sleep 1s',
            '',
        ])

    # Commands with smart timing
    for i, cmd in enumerate(commands, 1):
        # If filter is active, prefix with _wrap
        if filter_pattern:
            tape_lines.append(f'Type "_wrap {cmd}"')
        else:
            tape_lines.append(f'Type "{cmd}"')
        tape_lines.append('Enter')

        # Smart sleep based on command complexity
        if any(kw in cmd.lower() for kw in ['install', 'build', 'test', 'deploy', 'marketplace']):
            sleep_time = '3s'
        elif any(kw in cmd.lower() for kw in ['ls', 'pwd', 'echo', 'cat', 'grep']):
            sleep_time = '1s'
        else:
            sleep_time = '2s'

        tape_lines.append(f'Sleep {sleep_time}')

        # Empty line between stages for readability
        if i < len(commands):
            tape_lines.append('Enter')
            tape_lines.append('Sleep 300ms')
            tape_lines.append('')

    tape_lines.append('')
    tape_lines.append('Sleep 1s')
    return '\n'.join(tape_lines)


def speed_up_gif(gif_path: str, speed: int) -> bool:
    """Speed up GIF using gifsicle. Returns True on success."""
    try:
        subprocess.run(['gifsicle', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠ gifsicle not found, skipping speed-up. Install: brew install gifsicle", file=sys.stderr)
        return False

    # delay = 10 / speed (10 = normal, 5 = 2x, 3 = ~3x)
    delay = max(1, 10 // speed)
    tmp = f"/tmp/demo_raw_{Path(gif_path).stem}.gif"

    subprocess.run(['cp', gif_path, tmp], check=True)
    with open(gif_path, 'wb') as out:
        subprocess.run(['gifsicle', f'-d{delay}', tmp, '#0-'], stdout=out, check=True)
    Path(tmp).unlink(missing_ok=True)
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Auto-generate CLI demos from commands',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Simple demo
  %(prog)s -c "npm install" -o demo.gif

  # With hidden bootstrap (self-cleaning)
  %(prog)s -c "my-tool run" -o demo.gif \\
    --bootstrap "my-tool reset" --speed 2

  # With output noise filtering
  %(prog)s -c "deploy-tool push" -o demo.gif \\
    --filter "cache|progress|downloading"
        '''
    )

    parser.add_argument('-c', '--command', action='append', required=True,
                        help='Command to include (repeatable)')
    parser.add_argument('-o', '--output', required=True,
                        help='Output GIF file path')
    parser.add_argument('--title', help='Demo title')
    parser.add_argument('--theme', default='Dracula', help='VHS theme (default: Dracula)')
    parser.add_argument('--font-size', type=int, default=16, help='Font size (default: 16)')
    parser.add_argument('--width', type=int, default=1400, help='Terminal width (default: 1400)')
    parser.add_argument('--height', type=int, default=700, help='Terminal height (default: 700)')
    parser.add_argument('--bootstrap', action='append',
                        help='Hidden setup command run before demo (repeatable)')
    parser.add_argument('--filter',
                        help='Regex pattern to filter from command output')
    parser.add_argument('--speed', type=int, default=1,
                        help='Playback speed multiplier (default: 1, uses gifsicle)')
    parser.add_argument('--no-execute', action='store_true',
                        help='Generate tape file only')

    args = parser.parse_args()

    tape_content = create_tape_file(
        commands=args.command,
        output_gif=args.output,
        title=args.title,
        theme=args.theme,
        font_size=args.font_size,
        width=args.width,
        height=args.height,
        bootstrap=args.bootstrap,
        filter_pattern=args.filter,
    )

    output_path = Path(args.output)
    tape_file = output_path.with_suffix('.tape')
    tape_file.write_text(tape_content)
    print(f"✓ Generated tape file: {tape_file}")

    if not args.no_execute:
        try:
            subprocess.run(['vhs', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("✗ VHS not installed. Install: brew install charmbracelet/tap/vhs", file=sys.stderr)
            print(f"✓ Run manually: vhs {tape_file}", file=sys.stderr)
            return 1

        print(f"Recording: {args.output}")
        try:
            subprocess.run(['vhs', str(tape_file)], check=True)
        except subprocess.CalledProcessError as e:
            print(f"✗ VHS failed: {e}", file=sys.stderr)
            return 1

        # Post-processing speed-up
        if args.speed > 1:
            print(f"Speeding up {args.speed}x...")
            speed_up_gif(args.output, args.speed)

        size_kb = output_path.stat().st_size / 1024
        print(f"✓ Done: {args.output} ({size_kb:.0f} KB)")

    return 0


if __name__ == '__main__':
    sys.exit(main())
