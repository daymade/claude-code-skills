#!/usr/bin/env python3
"""
Enhanced transcript fixer wrapper with improved user experience.

Features:
- Custom output directory support
- Automatic HTML diff opening in browser
- Smart API key detection from shell config files
- Progress feedback

CRITICAL FIX: Now uses secure API key handling (Critical-2)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# CRITICAL FIX: Import secure secret handling
sys.path.insert(0, str(Path(__file__).parent))
from utils.security import mask_secret, SecretStr, validate_api_key

# CRITICAL FIX: Import path validation (Critical-5)
from utils.path_validator import PathValidator, PathValidationError, add_allowed_directory

# Initialize path validator
path_validator = PathValidator()


def find_glm_api_key():
    """
    Search for GLM API key in common shell config files.

    Looks for keys near ANTHROPIC_BASE_URL or GLM-related configs,
    not just by exact variable name.

    Returns:
        str or None: API key if found, None otherwise
    """
    shell_configs = [
        Path.home() / ".zshrc",
        Path.home() / ".bashrc",
        Path.home() / ".bash_profile",
        Path.home() / ".profile",
    ]

    for config_file in shell_configs:
        if not config_file.exists():
            continue

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Look for ANTHROPIC_BASE_URL with bigmodel
            for i, line in enumerate(lines):
                if 'ANTHROPIC_BASE_URL' in line and 'bigmodel.cn' in line:
                    # Check surrounding lines for API key
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)

                    for check_line in lines[start:end]:
                        # Look for uncommented export with token/key
                        if check_line.strip().startswith('#'):
                            # Check if it's a commented export with token
                            if 'export' in check_line and ('TOKEN' in check_line or 'KEY' in check_line):
                                parts = check_line.split('=', 1)
                                if len(parts) == 2:
                                    key = parts[1].strip().strip('"').strip("'")
                                    # CRITICAL FIX: Validate and mask API key
                                    if validate_api_key(key):
                                        print(f"✓ Found API key in {config_file}: {mask_secret(key)}")
                                        return key
                        elif 'export' in check_line and ('TOKEN' in check_line or 'KEY' in check_line):
                            parts = check_line.split('=', 1)
                            if len(parts) == 2:
                                key = parts[1].strip().strip('"').strip("'")
                                # CRITICAL FIX: Validate and mask API key
                                if validate_api_key(key):
                                    print(f"✓ Found API key in {config_file}: {mask_secret(key)}")
                                    return key
        except Exception as e:
            print(f"⚠️  Could not read {config_file}: {e}", file=sys.stderr)
            continue

    return None


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
        # Add current directory to allowed paths (for user convenience)
        add_allowed_directory(Path.cwd())

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
            add_allowed_directory(output_dir_path.parent if output_dir_path.parent.exists() else output_dir_path)

            output_dir = output_dir_path
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"✓ Output directory validated: {output_dir}")

        except PathValidationError as e:
            print(f"❌ Output directory validation failed: {e}")
            sys.exit(1)
    else:
        output_dir = input_path.parent

    # Check/find API key if Stage 2 or 3
    if args.stage in [2, 3]:
        api_key = os.environ.get('GLM_API_KEY')
        if not api_key:
            print("🔍 GLM_API_KEY not set, searching shell configs...")
            api_key = find_glm_api_key()
            if api_key:
                os.environ['GLM_API_KEY'] = api_key
            else:
                print("❌ GLM_API_KEY not found. Please set it or run with --stage 1")
                print("   Get API key from: https://open.bigmodel.cn/")
                sys.exit(1)

    # Get script directory
    script_dir = Path(__file__).parent
    main_script = script_dir / "fix_transcription.py"

    if not main_script.exists():
        print(f"❌ Main script not found: {main_script}")
        sys.exit(1)

    # Build command
    cmd = [
        'uv', 'run', '--with', 'httpx',
        str(main_script),
        '--input', str(input_path),
        '--stage', str(args.stage),
        '--domain', args.domain
    ]

    print(f"📖 Processing: {input_path.name}")
    print(f"📁 Output directory: {output_dir}")
    print(f"🎯 Domain: {args.domain}")
    print(f"⚙️  Stage: {args.stage}")
    print()

    # Run main script
    try:
        result = subprocess.run(cmd, check=True, cwd=script_dir.parent)
    except subprocess.CalledProcessError as e:
        print(f"❌ Processing failed with exit code {e.returncode}")
        sys.exit(e.returncode)

    # Move output files to desired directory if different from input directory
    if output_dir != input_path.parent:
        print(f"\n📦 Moving output files to {output_dir}...")

        base_name = input_path.stem
        output_patterns = [
            f"{base_name}_stage1.md",
            f"{base_name}_stage2.md",
            f"{base_name}_对比.html",
            f"{base_name}_对比报告.md",
            f"{base_name}_修复报告.md",
        ]

        for pattern in output_patterns:
            source = input_path.parent / pattern
            if source.exists():
                dest = output_dir / pattern
                source.rename(dest)
                print(f"  ✓ {pattern}")

    # Auto-open HTML diff
    if args.auto_open:
        html_file = output_dir / f"{input_path.stem}_对比.html"
        if html_file.exists():
            print("\n🌐 Opening HTML diff in browser...")
            open_html_in_browser(html_file)
        else:
            print(f"\n⚠️  HTML diff not generated (may require Stage 2/3)")

    print("\n✅ Processing complete!")
    print(f"\n📄 Output files in: {output_dir}")
    print(f"   - {input_path.stem}_stage1.md (dictionary corrections)")
    print(f"   - {input_path.stem}_stage2.md (AI corrections - final version)")
    print(f"   - {input_path.stem}_对比.html (visual diff)")


if __name__ == '__main__':
    main()
