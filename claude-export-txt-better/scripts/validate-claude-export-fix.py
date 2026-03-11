#!/usr/bin/env python3
"""Automated validation for fix-claude-export.py output.

Runs a comprehensive suite of checks against a fixed file and its original,
reporting PASS/FAIL for each with evidence. Designed to be run after every
fix iteration as a quality gate.

Usage:
    uv run scripts/validate-claude-export-fix.py <original.txt> <fixed.txt>
    uv run scripts/validate-claude-export-fix.py <original.txt> <fixed.txt> --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def display_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def is_cjk_ideograph(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F") and unicodedata.category(ch) == "Lo"


# ---------------------------------------------------------------------------
# Check infrastructure
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    category: str = ""


@dataclass
class ValidationReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str, category: str = ""):
        self.results.append(CheckResult(name, passed, detail, category))

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def print_report(self, verbose: bool = False):
        cats = {}
        for r in self.results:
            cats.setdefault(r.category or "General", []).append(r)

        for cat, checks in cats.items():
            print(f"\n{'=' * 60}")
            print(f"  {cat}")
            print(f"{'=' * 60}")
            for r in checks:
                icon = "✓" if r.passed else "✗"
                print(f"  {icon} {r.name}")
                if verbose or not r.passed:
                    for line in r.detail.split("\n"):
                        print(f"    {line}")

        total = len(self.results)
        print(f"\n{'=' * 60}")
        print(f"  TOTAL: {self.passed}/{total} passed, {self.failed} failed")
        print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------

def check_marker_counts(orig: str, fixed: str, report: ValidationReport):
    """Verify structural markers are preserved exactly."""
    markers = [
        ("❯", "User prompts"),
        ("●", "Claude actions"),
        ("✻", "Stars/crunched"),
        ("⎿", "Tool results"),
        ("…", "Expansion indicators"),
    ]
    for marker, name in markers:
        orig_count = orig.count(marker)
        fixed_count = fixed.count(marker)
        report.add(
            f"Marker {marker} ({name}): {orig_count}",
            orig_count == fixed_count,
            f"orig={orig_count} fixed={fixed_count}",
            "Structural Integrity",
        )


def check_table_borders(fixed: str, report: ValidationReport):
    """Verify table border corners are balanced."""
    for ch, name in [("┌", "top-left"), ("┐", "top-right"), ("┘", "bottom-right")]:
        count = fixed.count(ch)
        report.add(
            f"Table corner {ch} ({name}): {count}",
            True,  # Just record the count
            f"count={count}",
            "Structural Integrity",
        )
    tl = fixed.count("┌")
    tr = fixed.count("┐")
    br = fixed.count("┘")
    report.add(
        "Table corners balanced (┌ = ┐ = ┘)",
        tl == tr == br,
        f"┌={tl} ┐={tr} ┘={br}",
        "Structural Integrity",
    )


def check_line_reduction(orig: str, fixed: str, report: ValidationReport):
    """Output should have fewer lines than input (joins happened)."""
    orig_lines = orig.count("\n")
    fixed_lines = fixed.count("\n")
    report.add(
        f"Line reduction: {orig_lines} → {fixed_lines}",
        fixed_lines < orig_lines,
        f"delta={orig_lines - fixed_lines} ({(orig_lines - fixed_lines) / orig_lines * 100:.1f}% reduction)",
        "Structural Integrity",
    )


def check_table_border_completeness(fixed: str, report: ValidationReport):
    """Verify table border lines have matching left and right ends."""
    lines = fixed.split("\n")
    broken = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Lines starting with a left border char should have a right border char
        if stripped[0] == "┌" and "┐" not in stripped:
            broken.append((i + 1, "┌ without ┐", stripped[:80]))
        elif stripped[0] == "├" and "┤" not in stripped:
            broken.append((i + 1, "├ without ┤", stripped[:80]))
        elif stripped[0] == "└" and "┘" not in stripped:
            broken.append((i + 1, "└ without ┘", stripped[:80]))

    report.add(
        f"Table borders complete: {len(broken)} broken",
        len(broken) == 0,
        "\n".join(f"  L{ln}: {desc}" for ln, desc, _ in broken[:5])
        if broken else "all borders have matching ends",
        "Structural Integrity",
    )


def check_phase_separation(fixed: str, report: ValidationReport):
    """Verify Phase N: items are on separate lines."""
    lines = fixed.split("\n")
    multi_phase_lines = []
    for i, line in enumerate(lines):
        # Count "Phase N:" occurrences on this line
        matches = re.findall(r"Phase \d+:", line)
        if len(matches) >= 2:
            # Allow pipeline diagrams with arrows (legitimate multi-phase)
            if "→" in line:
                continue
            # Allow status updates like "Phase 3 进度: 3/5"
            if line.strip().startswith("●"):
                continue
            multi_phase_lines.append((i + 1, matches, line[:80]))

    report.add(
        "Phase items on separate lines",
        len(multi_phase_lines) == 0,
        f"{len(multi_phase_lines)} violations" + (
            "\n" + "\n".join(f"  L{ln}: {m}" for ln, m, _ in multi_phase_lines[:5])
            if multi_phase_lines else ""
        ),
        "Over-Join Prevention",
    )


def check_runaway_joins(fixed: str, report: ValidationReport):
    """Flag lines with very high display width that might be runaway joins."""
    lines = fixed.split("\n")
    runaways = []
    for i, line in enumerate(lines):
        dw = display_width(line)
        if dw > 500:
            # Check if it's a legitimate long line (user prompt)
            if line.startswith("❯ "):
                continue
            runaways.append((i + 1, dw, line[:60]))

    report.add(
        f"No runaway joins (dw > 500): {len(runaways)} found",
        len(runaways) == 0,
        "\n".join(f"  L{ln}: dw={dw} [{preview}...]" for ln, dw, preview in runaways[:5])
        if runaways else "none",
        "Over-Join Prevention",
    )


def check_en_cjk_no_space(fixed: str, report: ValidationReport):
    """Count remaining EN-CJK adjacency without space (potential pangu misses)."""
    # Only check at join boundaries (lines that were modified), not all text
    pattern_alnum_cjk = re.compile(r"[a-zA-Z0-9][一-龥]")
    pattern_cjk_alnum = re.compile(r"[一-龥][a-zA-Z0-9]")

    violations_ac = len(pattern_alnum_cjk.findall(fixed))
    violations_ca = len(pattern_cjk_alnum.findall(fixed))
    total = violations_ac + violations_ca

    # This is informational — some violations are in original content, code, etc.
    report.add(
        f"EN-CJK adjacency count: {total}",
        True,  # Informational
        f"ASCII→CJK: {violations_ac}, CJK→ASCII: {violations_ca} (includes original content)",
        "Pangu Spacing",
    )


def check_diff_lines_separate(fixed: str, report: ValidationReport):
    """Verify diff output lines aren't merged (line numbers should be separate)."""
    lines = fixed.split("\n")
    merged_diffs = []
    for i, line in enumerate(lines):
        # Look for two diff line numbers on the same line
        matches = re.findall(r"\b(\d{3})\s{2,}[-+]?\s", line)
        if len(matches) >= 2:
            merged_diffs.append((i + 1, matches, line[:80]))

    report.add(
        "Diff lines separate",
        len(merged_diffs) == 0,
        f"{len(merged_diffs)} violations" + (
            "\n" + "\n".join(f"  L{ln}: numbers={m}" for ln, m, _ in merged_diffs[:5])
            if merged_diffs else ""
        ),
        "Over-Join Prevention",
    )


def check_cjk_label_separation(fixed: str, report: ValidationReport):
    """Verify CJK label fields (模块:, 输出文件:, 状态:) are on separate lines."""
    lines = fixed.split("\n")
    merged_labels = []
    # Pattern: field-label style "Label1: value1 Label2: value2" where
    # each label starts at a position that looks like a separate field.
    # Only flag when labels are at field boundaries (preceded by whitespace
    # or start of line), not mid-sentence.
    cjk_field_re = re.compile(r"(?:^|\s)([\u4e00-\u9fff]{1,4}[:：])\s")
    for i, line in enumerate(lines):
        stripped = line.strip()
        matches = cjk_field_re.findall(stripped)
        if len(matches) >= 3:  # 3+ field labels = likely over-joined fields
            merged_labels.append((i + 1, matches, stripped[:80]))

    report.add(
        "CJK labels on separate lines",
        len(merged_labels) == 0,
        f"{len(merged_labels)} violations" + (
            "\n" + "\n".join(f"  L{ln}: labels={m}" for ln, m, _ in merged_labels[:5])
            if merged_labels else ""
        ),
        "Over-Join Prevention",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path, help="Original exported file")
    parser.add_argument("fixed", type=Path, help="Fixed output file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all details")
    args = parser.parse_args()

    orig = args.original.read_text(encoding="utf-8")
    fixed = args.fixed.read_text(encoding="utf-8")

    report = ValidationReport()

    # Run all checks
    check_marker_counts(orig, fixed, report)
    check_table_borders(fixed, report)
    check_table_border_completeness(fixed, report)
    check_line_reduction(orig, fixed, report)
    check_phase_separation(fixed, report)
    check_runaway_joins(fixed, report)
    check_diff_lines_separate(fixed, report)
    check_cjk_label_separation(fixed, report)
    check_en_cjk_no_space(fixed, report)

    report.print_report(verbose=args.verbose)

    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()