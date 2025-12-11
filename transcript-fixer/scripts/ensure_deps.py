#!/usr/bin/env python3
"""Initialize shared virtual environment for transcript-fixer.

Handles errors explicitly rather than letting Claude guess (per best practices).
Creates a shared venv at ~/.transcript-fixer/.venv that can be reused across
different working directories.
"""
import subprocess
import sys
from pathlib import Path

DEPS_DIR = Path.home() / ".transcript-fixer"
VENV_DIR = DEPS_DIR / ".venv"
REQUIREMENTS = ["httpx[http2]>=0.24.0", "filelock>=3.13.0", "aiofiles>=23.0.0"]


def main():
    """Initialize shared dependencies for transcript-fixer."""
    # Create base directory
    try:
        DEPS_DIR.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"❌ Cannot create {DEPS_DIR}. Check permissions.")
        sys.exit(1)

    # Create virtual environment if not exists
    if not VENV_DIR.exists():
        print("🔧 Creating virtual environment...")
        result = subprocess.run(
            ["uv", "venv", str(VENV_DIR)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"❌ Failed to create venv: {result.stderr}")
            print("   Install uv first: curl -LsSf https://astral.sh/uv/install.sh | sh")
            sys.exit(1)
    else:
        print(f"✓ Virtual environment exists at {VENV_DIR}")

    # Install dependencies
    print("📦 Installing dependencies...")
    result = subprocess.run(
        ["uv", "pip", "install", "--python", str(VENV_DIR / "bin" / "python")]
        + REQUIREMENTS,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"❌ Failed to install: {result.stderr}")
        sys.exit(1)

    print(f"✅ Dependencies ready at {VENV_DIR}")
    print()
    print("Usage:")
    print(f"  {VENV_DIR}/bin/python scripts/fix_transcription.py --input file.md --stage 3")
    print()
    print("Or add alias to ~/.zshrc:")
    print(f'  alias tf="{VENV_DIR}/bin/python scripts/fix_transcription.py"')


if __name__ == "__main__":
    main()
