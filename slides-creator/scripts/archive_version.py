#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Archive current slide version to _archive/v{N}/."""

import argparse
import shutil
from pathlib import Path


def get_next_version(archive_dir: Path) -> int:
    """Find the next version number (v1, v2, ...)."""
    if not archive_dir.exists():
        return 1
    versions = []
    for d in archive_dir.iterdir():
        if d.is_dir() and d.name.startswith("v"):
            try:
                versions.append(int(d.name[1:]))
            except ValueError:
                pass
    return max(versions, default=0) + 1


def archive_version(project_dir: str):
    """Archive 02-slides/ and 03-prompts/ to _archive/v{N}/."""
    project_path = Path(project_dir)
    slides_dir = project_path / "02-slides"
    prompts_dir = project_path / "03-prompts"

    if not slides_dir.exists():
        print(f"No slides to archive: {slides_dir}")
        return False

    archive_dir = project_path / "_archive"
    next_ver = get_next_version(archive_dir)
    target_dir = archive_dir / f"v{next_ver}"

    print(f"Archiving to: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=False)

    # Copy slides
    target_slides = target_dir / "02-slides"
    shutil.copytree(slides_dir, target_slides)
    print(f"  Copied slides: {len(list(target_slides.glob('*.png')))} files")

    # Copy prompts if exist
    if prompts_dir.exists():
        target_prompts = target_dir / "03-prompts"
        shutil.copytree(prompts_dir, target_prompts)
        prompt_count = sum(1 for _ in target_prompts.rglob("*.md"))
        print(f"  Copied prompts: {prompt_count} files")

    print(f"Archive v{next_ver} complete.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archive slide version")
    parser.add_argument("--project", required=True, help="Project directory")
    args = parser.parse_args()

    archive_version(args.project)
