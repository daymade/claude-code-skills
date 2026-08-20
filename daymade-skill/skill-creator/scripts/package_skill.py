#!/usr/bin/env python3
"""
Skill Packager - Creates a distributable .skill file of a skill folder

Usage:
    uv run --with PyYAML python -m scripts.package_skill \
      <path/to/skill-folder> [output-directory] \
      [--regression-review <review.json>] [--new-skill]

Example:
    uv run --with PyYAML python -m scripts.package_skill skills/public/my-skill
    uv run --with PyYAML python -m scripts.package_skill skills/public/my-skill ./dist

Notes:
    - The skill SOURCE OF TRUTH is the skill folder itself (e.g. skills/public/my-skill).
    - The .skill file produced by this script is a DISTRIBUTION ARTIFACT (zip bundle).
    - By default the artifact is written to <skill-folder>/dist/ so it stays next to
      its source and is easy to find and clean up. It is NOT the canonical skill location.
    - A skill that already exists in Git HEAD requires its current, fully
      classified old-vs-new regression review on every package attempt. The local
      marker is informational and never authorizes packaging by itself.
"""

import argparse
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from scripts.quick_validate import validate_skill
from scripts.security_scan import calculate_skill_hash
from scripts.packaging_policy import should_exclude
from scripts.audit_skill_regression import (
    create_regression_marker,
    requires_regression_review,
    verify_review_for_after,
)


def validate_security_marker(skill_path: Path) -> Tuple[bool, str]:
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
        hash_lines = [
            line for line in marker_content.splitlines() if line.startswith("Content hash:")
        ]
        if len(hash_lines) != 1:
            return False, "Security marker must contain exactly one content hash"
        hash_match = re.fullmatch(r'Content hash: ([a-f0-9]{64})', hash_lines[0])
        if not hash_match:
            return False, "Security marker content hash is malformed"
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


def _stage_attested_snapshot(skill_path: Path, staged_skill: Path) -> None:
    """Copy the package superset plus its marker into an isolated snapshot."""
    staged_skill.mkdir()
    for file_path in skill_path.rglob('*'):
        if not file_path.is_file():
            continue
        arcname = file_path.relative_to(skill_path.parent)
        if should_exclude(arcname, include_evals=True):
            continue
        relative = file_path.relative_to(skill_path)
        destination = staged_skill / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, destination)

    marker = skill_path / ".security-scan-passed"
    if marker.is_file():
        shutil.copy2(marker, staged_skill / marker.name)


def package_skill(
    skill_path,
    output_dir=None,
    include_evals=False,
    regression_review=None,
    new_skill=False,
):
    """
    Package a skill folder into a .skill file.

    Args:
        skill_path: Path to the skill folder (source of truth)
        output_dir: Optional output directory for the .skill artifact.
                    Defaults to <skill-folder>/dist/.
        include_evals: Ship the root evals/ directory too (excluded by default).
        regression_review: Completed old-vs-new review JSON for an existing
                           Git-tracked skill. It is re-verified during packaging.
        new_skill: Explicit declaration for a genuinely new skill outside Git.

    Returns:
        Path to the created .skill file, or None if error
    """
    skill_path = Path(skill_path).resolve()

    # Validate skill folder exists
    if not skill_path.exists():
        print(f"Error: Skill folder not found: {skill_path}")
        return None

    if not skill_path.is_dir():
        print(f"Error: Path is not a directory: {skill_path}")
        return None

    # Validate SKILL.md exists
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"Error: SKILL.md not found in {skill_path}")
        return None

    # Step 1: Validate skill structure and metadata
    print("Step 1: Validating skill structure...")
    valid, message = validate_skill(skill_path)
    if not valid:
        print(f"FAILED: {message}")
        print("   Fix validation errors before packaging.")
        return None
    print(f"PASSED: {message}\n")

    # Step 2: Existing-skill capability regression gate.
    review_required, review_reason = requires_regression_review(skill_path, new_skill=new_skill)
    print("Step 2: Validating existing-skill regression review...")
    if review_required and not regression_review:
        print(f"BLOCKED: {review_reason}")
        print("   Existing skills require their completed old-vs-new capability review.")
        print("   Run scripts.audit_skill_regression compare/verify, then pass")
        print("   --regression-review <review.json>.")
        return None
    if regression_review:
        ok, errors = verify_review_for_after(Path(regression_review), skill_path)
        if not ok:
            print("BLOCKED: Skill regression review is missing, stale, or incomplete")
            for error in errors[:20]:
                print(f"   - {error}")
            if len(errors) > 20:
                print(f"   - ... {len(errors) - 20} more")
            return None
        create_regression_marker(skill_path, Path(regression_review))
        print("PASSED: Skill regression review is current and fully classified\n")
    else:
        print(f"PASSED: Regression review not required ({review_reason})\n")

    # Step 3: Validate security scan (HARD REQUIREMENT)
    print("Step 3: Validating security scan...")
    is_valid, message = validate_security_marker(skill_path)

    if not is_valid:
        print(f"BLOCKED: {message}")
        print(f"   You MUST run: uv run --with PyYAML python -m scripts.security_scan {skill_path.name}")
        print("   Security review is MANDATORY before packaging.")
        return None
    print(f"PASSED: {message}\n")

    # Step 4: Package an attested immutable snapshot. Revalidating the marker
    # against the staged superset closes the live-source race between Step 3
    # and zip creation; later edits to the working tree cannot enter this zip.
    print("Step 4: Creating package...")

    # Determine output location
    skill_name = skill_path.name
    if output_dir:
        output_path = Path(output_dir).resolve()
        if output_path.is_relative_to(skill_path) and not output_path.is_relative_to(
            skill_path / "dist"
        ):
            print("Error: an in-skill output directory must be under the excluded dist/ root")
            return None
    else:
        # Default: place artifact next to source in a dedicated dist/ folder
        output_path = skill_path / "dist"
    output_path.mkdir(parents=True, exist_ok=True)

    skill_filename = output_path / f"{skill_name}.skill"

    # Create the .skill file (zip format). Build to a temp path and os.replace()
    # on success (methodology §4.5): a failure mid-write must not leave a
    # half-written .skill at the final path where it looks distributable.
    zip_tmp = skill_filename.with_name(skill_filename.name + ".tmp")
    try:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_package_snapshot_") as stage_dir:
            staged_skill = Path(stage_dir) / skill_name
            _stage_attested_snapshot(skill_path, staged_skill)
            staged_valid, staged_message = validate_security_marker(staged_skill)
            if not staged_valid:
                print(f"BLOCKED: staged snapshot is not attested: {staged_message}")
                return None

            with zipfile.ZipFile(zip_tmp, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in staged_skill.rglob('*'):
                    if not file_path.is_file():
                        continue
                    arcname = file_path.relative_to(staged_skill.parent)
                    if should_exclude(arcname, include_evals=include_evals):
                        print(f"  Skipped: {arcname}")
                        continue
                    zipf.write(file_path, arcname)
                    print(f"  Added: {arcname}")

            os.replace(zip_tmp, skill_filename)
            print(f"\nDistribution artifact created: {skill_filename}")
            print(f"  Source of truth (kept in git): {skill_path}")
            print(f"  The .skill file is a disposable zip bundle; delete it after distribution if desired.")
            return skill_filename

    except Exception as e:
        zip_tmp.unlink(missing_ok=True)
        print(f"Error creating .skill file: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Validate and package a skill directory")
    parser.add_argument("skill_path")
    parser.add_argument("output_dir", nargs="?")
    parser.add_argument("--include-evals", action="store_true")
    parser.add_argument(
        "--new-skill",
        action="store_true",
        help="Declare a genuinely new skill when Git cannot prove that status",
    )
    parser.add_argument(
        "--regression-review",
        help="Completed audit_skill_regression review JSON for an existing skill",
    )
    args = parser.parse_args()

    skill_path = args.skill_path
    output_dir = args.output_dir

    print(f"Packaging skill source: {skill_path}")
    if output_dir:
        print(f"   Artifact output directory: {output_dir}")
    else:
        print(f"   Artifact output directory: {Path(skill_path).resolve() / 'dist'}")
    print()

    result = package_skill(
        skill_path,
        output_dir,
        include_evals=args.include_evals,
        regression_review=args.regression_review,
        new_skill=args.new_skill,
    )

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
