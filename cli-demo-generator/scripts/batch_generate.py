#!/usr/bin/env python3
"""
Batch generate multiple CLI demos from a configuration file.

Supports YAML and JSON formats for defining multiple demos.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


def load_config(config_file: Path) -> Dict:
    """Load demo configuration from YAML or JSON file."""
    suffix = config_file.suffix.lower()

    with open(config_file) as f:
        if suffix in ['.yaml', '.yml']:
            if not YAML_AVAILABLE:
                print("Error: PyYAML not installed. Install with: pip install pyyaml", file=sys.stderr)
                sys.exit(1)
            return yaml.safe_load(f)
        elif suffix == '.json':
            return json.load(f)
        else:
            print(f"Error: Unsupported config format: {suffix}", file=sys.stderr)
            print("Supported formats: .yaml, .yml, .json", file=sys.stderr)
            sys.exit(1)


def generate_demo(demo_config: Dict, base_path: Path, script_path: Path) -> bool:
    """Generate a single demo from configuration."""
    name = demo_config.get('name', 'unnamed')
    output = demo_config.get('output')
    commands = demo_config.get('commands', [])

    if not output or not commands:
        print(f"✗ Skipping '{name}': missing output or commands", file=sys.stderr)
        return False

    # Build command
    cmd = [sys.executable, str(script_path)]

    for command in commands:
        cmd.extend(['-c', command])

    cmd.extend(['-o', str(base_path / output)])

    # Optional parameters
    if 'title' in demo_config:
        cmd.extend(['--title', demo_config['title']])
    if 'theme' in demo_config:
        cmd.extend(['--theme', demo_config['theme']])
    if 'width' in demo_config:
        cmd.extend(['--width', str(demo_config['width'])])
    if 'height' in demo_config:
        cmd.extend(['--height', str(demo_config['height'])])

    print(f"\n{'='*60}")
    print(f"Generating: {name}")
    print(f"Output: {output}")
    print(f"Commands: {len(commands)}")
    print(f"{'='*60}")

    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to generate '{name}': {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Batch generate CLI demos from configuration file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Configuration file format (YAML):
  demos:
    - name: "Install Demo"
      output: "install.gif"
      title: "Installation"
      theme: "Dracula"
      commands:
        - "npm install my-package"
        - "npm run build"

    - name: "Usage Demo"
      output: "usage.gif"
      commands:
        - "my-package --help"
        - "my-package run"

Configuration file format (JSON):
  {
    "demos": [
      {
        "name": "Install Demo",
        "output": "install.gif",
        "commands": ["npm install"]
      }
    ]
  }
        '''
    )

    parser.add_argument('config', type=Path,
                        help='Configuration file (.yaml, .yml, or .json)')
    parser.add_argument('--output-dir', type=Path, default=Path.cwd(),
                        help='Output directory for generated demos')

    args = parser.parse_args()

    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        return 1

    # Load configuration
    config = load_config(args.config)
    demos = config.get('demos', [])

    if not demos:
        print("Error: No demos defined in configuration", file=sys.stderr)
        return 1

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Find auto_generate_demo.py script
    script_path = Path(__file__).parent / 'auto_generate_demo.py'
    if not script_path.exists():
        print(f"Error: auto_generate_demo.py not found at {script_path}", file=sys.stderr)
        return 1

    # Generate demos
    total = len(demos)
    successful = 0
    failed = 0

    print(f"\n{'='*60}")
    print(f"Starting batch generation: {total} demos")
    print(f"Output directory: {args.output_dir}")
    print(f"{'='*60}\n")

    for i, demo in enumerate(demos, 1):
        print(f"\n[{i}/{total}] Processing: {demo.get('name', 'unnamed')}")
        if generate_demo(demo, args.output_dir, script_path):
            successful += 1
        else:
            failed += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"Batch generation complete!")
    print(f"{'='*60}")
    print(f"✓ Successful: {successful}")
    if failed > 0:
        print(f"✗ Failed: {failed}")
    print(f"Total: {total}")
    print(f"{'='*60}\n")

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
