#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx>=0.24.0",
#     "filelock>=3.13.0",
# ]
# ///
"""
Enhanced transcript fixer wrapper with improved user experience.

Features:
- Custom output directory support
- Automatic HTML diff opening in browser
- Progress feedback

CRITICAL FIX: Reads API key from the canonical config directory
(~/.transcript-fixer/config.json) with optional env-var overrides;
does not scan shell config files for secrets.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# CRITICAL FIX: Import path validation (Critical-5)
sys.path.insert(0, str(Path(__file__).parent))
from cli.commands import cmd_run_correction
from utils.path_validator import PathValidator, PathValidationError
from utils.config import get_config

# Initialize path validator (allow symlinks because macOS /tmp is a symlink)
path_validator = PathValidator(allow_symlinks=True)


def open_html_in_browser(html_path):
    """
    Open HTML file in default browser.

    Args:
        html_path: Path to HTML file
    """
    if not Path(html_path).exists():
        print(f"⚠️  HTML file not found: {html_path}")
        return

    try:
        if sys.platform == 'darwin':  # macOS
            subprocess.run(['open', html_path], check=True)
        elif sys.platform == 'win32':  # Windows
            # Use os.startfile for safer Windows file opening
            import os
            os.startfile(html_path)
        else:  # Linux
            subprocess.run(['xdg-open', html_path], check=True)
        print(f"✓ Opened HTML diff in browser: {html_path}")
    except Exception as e:
        print(f"⚠️  Could not open browser: {e}")
        print(f"   Please manually open: {html_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Enhanced transcript fixer with auto-open HTML diff",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fix transcript and save to custom output directory
  %(prog)s input.md --output ./corrected --auto-open

  # Fix without opening browser
  %(prog)s input.md --output ./corrected --no-auto-open

  # Use specific domain
  %(prog)s input.md --output ./corrected --domain embodied_ai
        """
    )

    parser.add_argument('input', help='Input transcript file (.md or .txt)')
    parser.add_argument('--output', '-o', help='Output directory (default: same as input file)')
    parser.add_argument('--domain', default='general',
                       choices=['general', 'embodied_ai', 'finance', 'medical'],
                       help='Domain for corrections (default: general)')
    parser.add_argument('--stage', type=int, default=3, choices=[1, 2, 3],
                       help='Processing stage: 1=dict, 2=AI, 3=both (default: 3)')
    parser.add_argument('--auto-open', action='store_true', default=True,
                       help='Automatically open HTML diff in browser (default: True)')
    parser.add_argument('--no-auto-open', dest='auto_open', action='store_false',
                       help='Do not open HTML diff automatically')

    args = parser.parse_args()

    # CRITICAL FIX: Validate input file with security checks
    try:
        # Allow the input file's own directory (handles absolute paths outside cwd)
        input_path_to_validate = Path(args.input).expanduser().absolute()
        path_validator.add_allowed_directory(input_path_to_validate.parent)
        path_validator.add_allowed_directory(Path.cwd())

        input_path = path_validator.validate_input_path(args.input)
        print(f"✓ Input file validated: {input_path}")

    except PathValidationError as e:
        print(f"❌ Input file validation failed: {e}")
        sys.exit(1)

    # CRITICAL FIX: Validate output directory
    if args.output:
        try:
            # Add output directory to allowed paths
            output_dir_path = Path(args.output).expanduser().absolute()
            path_validator.add_allowed_directory(output_dir_path.parent if output_dir_path.parent.exists() else output_dir_path)

            output_dir = output_dir_path
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"✓ Output directory validated: {output_dir}")

        except PathValidationError as e:
            print(f"❌ Output directory validation failed: {e}")
            sys.exit(1)
    else:
        output_dir = input_path.parent

    # Check API key if Stage 2 or 3 (canonical source: config directory)
    if args.stage in [2, 3]:
        config = get_config()
        api_key = config.api.api_key
        if not api_key:
            config_dir = Path(os.getenv("TRANSCRIPT_FIXER_CONFIG_DIR", str(Path.home() / ".transcript-fixer")))
            print("❌ API key not configured. Please add it to the config file:")
            print(f'   {config_dir}/config.json')
            print('   { "api": { "api_key": "your-key" } }')
            print("   Or set GLM_API_KEY / ANTHROPIC_API_KEY environment variable.")
            print("   Config directory can be changed with TRANSCRIPT_FIXER_CONFIG_DIR.")
            print("   Get API key from: https://open.bigmodel.cn/")
            sys.exit(1)

    # Run correction pipeline directly (no subprocess indirection)
    print(f"📖 Processing: {input_path.name}")
    print(f"📁 Output directory: {output_dir}")
    print(f"🎯 Domain: {args.domain}")
    print(f"⚙️  Stage: {args.stage}")
    print()

    run_args = argparse.Namespace(
        input=str(input_path),
        output=str(output_dir) if args.output else None,
        stage=args.stage,
        domain=args.domain,
        dry_run=False,
        # apply_all=True preserves this entry point's historical "apply every
        # correction" semantics. Stage 1's CLI default flipped to safe mode
        # (review_mode = not apply_all), but this automation/batch path predates
        # that flip and callers rely on full dictionary application before the AI
        # pass. Without this the flip would silently downgrade it to
        # low-risk-only with no way to opt back in (this script exposes no flag).
        apply_all=True,
        review=False,  # dead no-op; review_mode is now driven by apply_all
        changes_file=False,
    )

    try:
        cmd_run_correction(run_args)
    except SystemExit as e:
        if e.code != 0:
            print(f"❌ Processing failed with exit code {e.code}")
            sys.exit(e.code)

    # Auto-open HTML diff
    if args.auto_open:
        html_file = output_dir / f"{input_path.stem}_对比.html"
        if html_file.exists():
            print("\n🌐 Opening HTML diff in browser...")
            open_html_in_browser(html_file)
        else:
            print(f"\n⚠️  HTML diff not generated (may require Stage 2/3)")

    # List output files that were actually generated
    output_files = [
        (f"{input_path.stem}_stage1.md", "dictionary corrections"),
        (f"{input_path.stem}_stage2.md", "AI corrections - final version"),
        (f"{input_path.stem}_对比.html", "visual diff"),
    ]

    print("\n✅ Processing complete!")
    print(f"\n📄 Output files in: {output_dir}")
    for name, description in output_files:
        if (output_dir / name).exists():
            print(f"   - {name} ({description})")


if __name__ == '__main__':
    main()
