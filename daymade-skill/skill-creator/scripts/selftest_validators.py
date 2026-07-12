#!/usr/bin/env python3
"""Falsifiability self-test for skill-creator's own validators.

A green checker only means something if the checker itself is verified against
known-bad inputs. This suite constructs throwaway fixture skills in a temp dir
(never static fixture files — those would trip the very scanners they test) and
asserts each validator actually catches what it claims to catch.

Born from a real incident: the security marker's "Content hash" was the SHA-256
of the EMPTY STRING for every skill living under a dot-directory (e.g. the
standard project-skill location .claude/skills/), because the hidden-dir check
ran against the ABSOLUTE path. The attestation looked present, well-formed, and
green — and had never hashed a single byte. Test 1 is the direct regression.

Run from the skill-creator root:
    uv run --with PyYAML python -m scripts.selftest_validators
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import sys
import tempfile
from pathlib import Path

from scripts.package_skill import should_exclude, validate_security_marker
from scripts.audit_skill_regression import build_report
from scripts.quick_validate import validate_skill
from scripts.security_scan import calculate_skill_hash, create_security_marker, scan_skill_patterns

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}: {name}" + (f" — {detail}" if detail and not cond else ""))


def make_skill(root: Path, name: str = "fixture-skill") -> Path:
    skill = root / name
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: fixture-skill\ndescription: A fixture skill for validator self-tests.\n---\n\n"
        "# Fixture\n\nSee references/guide.md for details.\n",
        encoding="utf-8")
    (skill / "references" / "guide.md").write_text("# Guide\n\nAll good here.\n", encoding="utf-8")
    return skill


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        print("[1] content hash must hash real bytes — even under a dot-directory parent")
        # Reproduce the incident layout: skill under .claude/skills/
        hidden_skill = make_skill(tmp / ".claude" / "skills")
        h = calculate_skill_hash(hidden_skill)
        check("hash under .claude/skills/ is NOT the empty-string SHA-256", h != EMPTY_SHA256, h)
        original_cwd = Path.cwd()
        try:
            os.chdir(hidden_skill)
            relative_hash = calculate_skill_hash(Path("."))
        finally:
            os.chdir(original_cwd)
        check("relative and resolved skill paths produce the same hash", relative_hash == h)

        print("[2] hash is content-sensitive and deterministic")
        h1 = calculate_skill_hash(hidden_skill)
        f = hidden_skill / "SKILL.md"
        orig = f.read_bytes()
        f.write_bytes(orig + b"\ntampered\n")
        h2 = calculate_skill_hash(hidden_skill)
        f.write_bytes(orig)
        h3 = calculate_skill_hash(hidden_skill)
        check("changed byte changes hash", h1 != h2)
        check("restored content restores hash", h1 == h3)

        transcript = hidden_skill / "fixtures.jsonl"
        transcript.write_text('{"text":"first"}\n', encoding="utf-8")
        jsonl_hash_1 = calculate_skill_hash(hidden_skill)
        transcript.write_text('{"text":"second"}\n', encoding="utf-8")
        jsonl_hash_2 = calculate_skill_hash(hidden_skill)
        check("changed JSONL content changes hash", jsonl_hash_1 != jsonl_hash_2)

        template = hidden_skill / "assets" / "hook.template"
        template.parent.mkdir()
        template.write_text("first template\n", encoding="utf-8")
        template_hash_1 = calculate_skill_hash(hidden_skill)
        template.write_text("second template\n", encoding="utf-8")
        template_hash_2 = calculate_skill_hash(hidden_skill)
        check("changed template content changes hash", template_hash_1 != template_hash_2)

        html = hidden_skill / "assets" / "viewer.html"
        html.write_text("<p>first</p>\n", encoding="utf-8")
        html_hash_1 = calculate_skill_hash(hidden_skill)
        html.write_text("<p>second</p>\n", encoding="utf-8")
        html_hash_2 = calculate_skill_hash(hidden_skill)
        check("changed HTML content changes hash", html_hash_1 != html_hash_2)

        print("[3] tampering after a scan must be caught by marker validation")
        create_security_marker(hidden_skill)
        ok_before, _ = validate_security_marker(hidden_skill)
        f.write_bytes(orig + b"\nevil edit\n")
        ok_after, msg = validate_security_marker(hidden_skill)
        f.write_bytes(orig)
        check("marker validates right after scan", ok_before)
        check("marker validation fails after tamper", not ok_after, msg)

        print("[4] quick_validate flags absolute user paths inside references/ (not just SKILL.md)")
        leaky = make_skill(tmp, "leaky-skill")
        # Assemble the bad path at runtime so static scanners never match this
        # test fixture inside selftest_validators.py itself.
        bad_path = "/" + "Users" + "/someuser/workspace/project/scripts"
        (leaky / "references" / "cli.md").write_text(
            f"# CLI\n\nRun this first:\n\n    cd {bad_path}\n",
            encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            valid, _ = validate_skill(leaky)
        out = buf.getvalue()
        check("skill still validates (warning, not failure)", valid)
        check("absolute path in references/cli.md is flagged",
              "cli.md" in out and bad_path[:14] in out, out[:200])

        hidden_leaky = make_skill(tmp / ".claude" / "skills", "hidden-leaky-skill")
        (hidden_leaky / "references" / "cli.md").write_text(
            f"# CLI\n\nRun this first:\n\n    cd {bad_path}\n",
            encoding="utf-8")
        hidden_issues, _ = scan_skill_patterns(hidden_leaky)
        check("verbose scan inspects skills below hidden parent directories",
              any(issue.pattern_name == "Absolute User Paths" for issue in hidden_issues))

        hidden_output_skill = make_skill(tmp, "hidden-output-skill")
        (hidden_output_skill / ".enrich").mkdir()
        (hidden_output_skill / ".enrich" / "leak.md").write_text(
            f"# Local artifact\n\n{bad_path}\n",
            encoding="utf-8")
        hidden_output_issues, _ = scan_skill_patterns(hidden_output_skill)
        check("verbose scan still skips hidden directories inside a skill",
              not any(issue.pattern_name == "Absolute User Paths" for issue in hidden_output_issues))

        print("[5] quick_validate flags broken internal refs inside references/")
        broken = make_skill(tmp, "broken-ref-skill")
        (broken / "references" / "index.md").write_text(
            "# Index\n\nDetails live in references/does_not_exist.md and scripts/missing.py.\n",
            encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            valid, _ = validate_skill(broken)
        out = buf.getvalue()
        check("broken internal reference is flagged", "does_not_exist.md" in out, out[:200])

        print("[6] quick_validate rejects known-bad frontmatter")
        bad = tmp / "bad-skill"
        bad.mkdir()
        (bad / "SKILL.md").write_text("---\nname: bad-skill\n---\n\n# No description\n", encoding="utf-8")
        valid, msg = validate_skill(bad)
        check("missing description is rejected", not valid, msg)

        print("[7] packager exclusion rules")
        check("evals/ excluded by default", should_exclude(Path("skill/evals/evals.json")))
        check("evals/ included with opt-in flag",
              not should_exclude(Path("skill/evals/evals.json"), include_evals=True))
        check("tests/ never ships", should_exclude(Path("skill/tests/test_runtime.py")))
        check(".enrich/ never ships", should_exclude(Path("skill/.enrich/run/manifest.json")))
        check("__pycache__ always excluded even with opt-in",
              should_exclude(Path("skill/scripts/__pycache__/m.pyc"), include_evals=True))
        check("scan marker never ships", should_exclude(Path("skill/.security-scan-passed")))
        check("regression marker never ships", should_exclude(Path("skill/.skill-regression-reviewed")))
        check("normal script ships", not should_exclude(Path("skill/scripts/tool.py")))

        print("[8] existing-skill regression audit must surface a deleted capability")
        before = make_skill(tmp, "regression-before")
        after = make_skill(tmp, "regression-after")
        with (before / "SKILL.md").open("a", encoding="utf-8") as handle:
            handle.write("\n- Verify a signed-in role-less account sees a no-access state.\n")
        report = build_report(before, after)
        check(
            "deleted capability becomes an unclassified regression candidate",
            any("role-less" in item["text"] for item in report["candidates"]),
        )

    print()
    print(f"selftest_validators: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
