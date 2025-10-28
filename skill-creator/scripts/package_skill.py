#!/usr/bin/env python3
"""
Skill Packager - Creates a distributable zip file of a skill folder

Usage:
    python utils/package_skill.py <path/to/skill-folder> [output-directory]

Example:
    python utils/package_skill.py skills/public/my-skill
    python utils/package_skill.py skills/public/my-skill ./dist
"""

import sys
import zipfile
import re
from pathlib import Path
from quick_validate import validate_skill
from security_scan import calculate_skill_hash


def validate_security_marker(skill_path: Path) -> tuple[bool, str]:
    """
    Validate security marker file exists and hash matches current content

    Returns:
        (is_valid, message) - True if valid, False if re-scan needed
    """
    security_marker = skill_path / ".security-scan-passed"

    # Check existence
    if not security_marker.exists():
        return False, "Security scan not completed"

    # Read stored hash
    try:
        marker_content = security_marker.read_text()
        hash_match = re.search(r'Content hash:\s*([a-f0-9]{64})', marker_content)

        if not hash_match:
            return False, "Security marker missing content hash (old format)"

        stored_hash = hash_match.group(1)
    except Exception as e:
        return False, f"Cannot read security marker: {e}"

    # Calculate current hash
    try:
        current_hash = calculate_skill_hash(skill_path)
    except Exception as e:
        return False, f"Cannot calculate content hash: {e}"

    # Compare hashes
    if stored_hash != current_hash:
        return False, "Skill content changed since last security scan"

    return True, "Security scan valid"


def package_skill(skill_path, output_dir=None):
    """
    Package a skill folder into a zip file.

    Args:
        skill_path: Path to the skill folder
        output_dir: Optional output directory for the zip file (defaults to current directory)

    Returns:
        Path to the created zip file, or None if error
    """
    skill_path = Path(skill_path).resolve()

    # Validate skill folder exists
    if not skill_path.exists():
        print(f"❌ Error: Skill folder not found: {skill_path}")
        return None

    if not skill_path.is_dir():
        print(f"❌ Error: Path is not a directory: {skill_path}")
        return None

    # Validate SKILL.md exists
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"❌ Error: SKILL.md not found in {skill_path}")
        return None

    # Step 1: Validate skill structure and metadata
    print("🔍 Step 1: Validating skill structure...")
    valid, message = validate_skill(skill_path)
    if not valid:
        print(f"❌ FAILED: {message}")
        print("   Fix validation errors before packaging.")
        return None
    print(f"✅ PASSED: {message}\n")

    # Step 2: Validate security scan (HARD REQUIREMENT)
    print("🔍 Step 2: Validating security scan...")
    is_valid, message = validate_security_marker(skill_path)

    if not is_valid:
        print(f"❌ BLOCKED: {message}")
        print(f"   You MUST run: python scripts/security_scan.py {skill_path.name}")
        print("   Security review is MANDATORY before packaging.")
        return None
    print(f"✅ PASSED: {message}\n")

    # Step 3: Package the skill
    print("📦 Step 3: Creating package...")

    # Determine output location
    skill_name = skill_path.name
    if output_dir:
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = Path.cwd()

    zip_filename = output_path / f"{skill_name}.zip"

    # Create the zip file
    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Walk through the skill directory
            for file_path in skill_path.rglob('*'):
                if file_path.is_file():
                    # Calculate the relative path within the zip
                    arcname = file_path.relative_to(skill_path.parent)
                    zipf.write(file_path, arcname)
                    print(f"  Added: {arcname}")

        print(f"\n✅ Successfully packaged skill to: {zip_filename}")
        return zip_filename

    except Exception as e:
        print(f"❌ Error creating zip file: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python utils/package_skill.py <path/to/skill-folder> [output-directory]")
        print("\nExample:")
        print("  python utils/package_skill.py skills/public/my-skill")
        print("  python utils/package_skill.py skills/public/my-skill ./dist")
        sys.exit(1)

    skill_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"📦 Packaging skill: {skill_path}")
    if output_dir:
        print(f"   Output directory: {output_dir}")
    print()

    result = package_skill(skill_path, output_dir)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
