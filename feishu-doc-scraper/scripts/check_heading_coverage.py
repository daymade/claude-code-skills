#!/usr/bin/env python3
"""
Check that expected Feishu headings are present in the final Markdown output.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NOISE_PATTERNS = (
    "you may also ask",
    "recommended content",
    "upload logs",
    "contact support",
    "comments",
)


def normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"\s+", "", text)
    # Remove punctuation and special characters.  Using a set avoids the
    # regex escaping trap (the previous character class terminated early
    # because \\] was interpreted as a literal backslash followed by ]).
    _REMOVE_CHARS = set(
        chr(c) for c in (
            0x60, 0x7E, 0x7C, 0x2C, 0x2E, 0x21, 0x3F, 0x28, 0x29,
            0x5B, 0x5D, 0x3C, 0x3E, 0x300A, 0x300B,
            0x22, 0x27, 0x201C, 0x201D, 0x2018, 0x2019,
            0x5C, 0x2D, 0x2B,
            0x3A, 0xFF1A,
            0x3002, 0xFF0C,
            0xFF01, 0xFF1F,
            0xFF08, 0xFF09,
            0x2014, 0x2013,
        )
    )
    text = "".join(c for c in text if c not in _REMOVE_CHARS)
    return text


def load_expected(headings_file: Path) -> list[str]:
    return [line.strip() for line in headings_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_headings(markdown_text: str) -> list[str]:
    headings = []
    for line in markdown_text.splitlines():
        if re.match(r"^#{1,6}\s+\S", line):
            headings.append(line.strip())
    return headings


def detect_noise(markdown_text: str) -> list[str]:
    lowered = markdown_text.lower()
    return [pattern for pattern in NOISE_PATTERNS if pattern in lowered]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown-file", required=True, help="Generated markdown file")
    parser.add_argument("--headings-file", required=True, help="Plain text file with one expected heading per line")
    return parser.parse_args()


def main():
    args = parse_args()
    markdown_path = Path(args.markdown_file)
    headings_path = Path(args.headings_file)

    markdown_text = markdown_path.read_text(encoding="utf-8")
    expected = load_expected(headings_path)
    found = extract_headings(markdown_text)

    found_index = {normalize(item): item for item in found}
    missing = [item for item in expected if normalize(item) not in found_index]
    noise_hits = detect_noise(markdown_text)

    print(f"Expected headings: {len(expected)}")
    print(f"Found markdown headings: {len(found)}")

    if missing:
        print("Missing headings:")
        for item in missing:
            print(f"  - {item}")

    if noise_hits:
        print("Noise patterns detected:")
        for item in noise_hits:
            print(f"  - {item}")

    if missing or noise_hits:
        sys.exit(1)

    print("Heading coverage check passed.")


if __name__ == "__main__":
    main()
