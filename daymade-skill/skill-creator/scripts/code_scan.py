#!/usr/bin/env python3
"""Run the bundled, local Python archive-path rules through Semgrep CE."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "security_rules" / "python-archive-paths.yaml"
SEMGREP_VERSION = "1.185.0"


@dataclass(frozen=True)
class CodeScanResult:
    findings: list[dict]
    content_hash: str
    python_files: tuple[str, ...]
    engine_version: str
    python_hash: str
    policy_hash: str


def python_content_hash(root: Path, files: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(path for path in files if path.suffix == ".py"):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def policy_hash() -> str:
    """Invalidate old receipts when the detector, rules or dependency pin changes."""
    digest = hashlib.sha256()
    for source in (
        Path(__file__), RULES, ROOT / "pyproject.toml", ROOT / "uv.lock",
        ROOT / "scripts" / "security_scan.py", ROOT / "scripts" / "packaging_policy.py",
    ):
        digest.update(source.name.encode())
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run_code_scan(
    root: Path, files: Iterable[Path], content_hash: str,
    *, timeout: float = 300,
) -> CodeScanResult:
    """Require a completed scan of every selected Python file; never execute it."""
    root = root.resolve()
    selected = sorted(path for path in files if path.suffix == ".py")
    relative = tuple(path.relative_to(root).as_posix() for path in selected)
    policy = policy_hash()
    if not selected:
        return CodeScanResult([], content_hash, relative, "not-applicable", python_content_hash(root, []), policy)
    with tempfile.TemporaryDirectory(prefix="skill-code-scan-") as scratch:
        stage = Path(scratch).resolve()
        # Override Semgrep's default ignore list; the caller already selected the
        # exact packaging superset, including optional eval files.
        (stage / ".semgrepignore").write_text("", encoding="utf-8")
        for source, rel in zip(selected, relative):
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            try:
                ast.parse(target.read_bytes(), filename=rel)
            except (SyntaxError, ValueError) as error:
                raise RuntimeError(f"Python analysis error: {rel}: invalid Python syntax") from error
        staged_hash = python_content_hash(stage, (stage / rel for rel in relative))
        environment = os.environ.copy()
        environment.pop("SEMGREP_APP_TOKEN", None)
        environment["SEMGREP_SETTINGS_FILE"] = str(stage / ".semgrep-settings.yml")
        sibling = Path(sys.executable).parent / ("semgrep.exe" if os.name == "nt" else "semgrep")
        executable = str(sibling) if sibling.is_file() else shutil.which("semgrep")
        if not executable:
            raise RuntimeError("Semgrep is unavailable; use this Skill Creator's locked uv entry")
        command = [
            executable, "scan", "--config", str(RULES),
            "--metrics=off", "--disable-version-check", "--no-git-ignore",
            "--strict", "--error", "--json", "--no-rewrite-rule-ids", "--disable-nosem",
            "--max-target-bytes=0", "--jobs=4", "--timeout=30", str(stage),
        ]
        try:
            completed = subprocess.run(
                command, cwd=stage, env=environment, capture_output=True, text=True, timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"Python code scan did not complete: {error}") from error
        if completed.returncode not in (0, 1):
            raise RuntimeError(
                "Python code scan failed; use this Skill Creator's locked uv entry. "
                f"Engine exit: {completed.returncode}."
            )
        try:
            report = json.loads(completed.stdout)
        except (ValueError, TypeError) as error:
            raise RuntimeError("Python code scan returned no valid JSON report") from error
        if not isinstance(report, dict):
            raise RuntimeError("Python code scan report is not an object")
        findings = report.get("results")
        errors = report.get("errors")
        paths = report.get("paths")
        if not isinstance(findings, list) or not isinstance(errors, list) or not isinstance(paths, dict):
            raise RuntimeError("Python code scan report is incomplete")
        if errors:
            locations = []
            for error in errors:
                if isinstance(error, dict):
                    path = error.get("path")
                    if isinstance(path, str):
                        try:
                            path = str(Path(path).resolve().relative_to(stage))
                        except ValueError:
                            path = "<unknown file>"
                        locations.append(f"{path}: {error.get('type', 'analysis error')}")
            detail = "; ".join(locations[:10]) or "no file location reported"
            raise RuntimeError(f"Python code scan left {len(errors)} analysis error(s): {detail}")
        if report.get("version") != SEMGREP_VERSION:
            raise RuntimeError(f"Python code scan requires Semgrep {SEMGREP_VERSION}")
        scanned = paths.get("scanned")
        if not isinstance(scanned, list) or not all(isinstance(path, str) for path in scanned):
            raise RuntimeError("Python code scan has no examined-file inventory")
        observed = {Path(path).resolve().relative_to(stage).as_posix() for path in scanned}
        if observed != set(relative):
            raise RuntimeError("Python code scan skipped or added selected files")
        if (completed.returncode == 0 and findings) or (completed.returncode == 1 and not findings):
            raise RuntimeError("Python code scan exit status disagrees with its findings")
        remapped = []
        for finding in findings:
            if not isinstance(finding, dict):
                raise RuntimeError("Python code scan contains an invalid finding")
            try:
                location = Path(finding["path"]).resolve().relative_to(stage).as_posix()
                line = finding["start"]["line"]
                rule = finding["check_id"]
                message = finding["extra"]["message"]
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError("Python code scan finding is incomplete") from error
            if location not in relative or type(line) is not int or line < 1:
                raise RuntimeError("Python code scan finding has an invalid location")
            if not isinstance(rule, str) or not isinstance(message, str):
                raise RuntimeError("Python code scan finding has invalid text")
            remapped.append({"path": location, "line": line, "rule": rule, "message": message})
        if policy_hash() != policy:
            raise RuntimeError("Python code scan policy changed during analysis")
        return CodeScanResult(remapped, content_hash, relative, report["version"], staged_hash, policy)


def marketplace_python_files(root: Path) -> list[Path]:
    """Select registered Skill packaging supersets and repository maintenance scripts."""
    from scripts.security_scan import iter_security_relevant_files

    manifest = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
    selected = set()
    for plugin in manifest["plugins"]:
        source = root / plugin["source"]
        members = plugin.get("skills") or ["."]
        for member in members:
            skill = (source / member).resolve()
            skill.relative_to(root)
            if not (skill / "SKILL.md").is_file():
                raise ValueError(f"Registered Skill entry is missing: {skill.relative_to(root)}")
            selected.update(path for path in iter_security_relevant_files(skill) if path.suffix == ".py")
    selected.update(path for path in iter_security_relevant_files(root / "scripts") if path.suffix == ".py")
    return sorted(selected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--marketplace", action="store_true", help="Scan registered Skills and repository scripts")
    args = parser.parse_args()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.security_scan import calculate_skill_hash, iter_security_relevant_files

    if not args.root.is_dir():
        parser.error("root must be an existing directory")
    try:
        root = args.root.resolve()
        def select():
            return marketplace_python_files(root) if args.marketplace else list(iter_security_relevant_files(root))

        def digest_for(files):
            return python_content_hash(root, files) if args.marketplace else calculate_skill_hash(root)

        files = select()
        digest = digest_for(files)
        result = run_code_scan(root, files, digest)
        if digest_for(select()) != digest:
            raise RuntimeError("Code scan inputs changed during analysis")
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Code scan incomplete: {error}", file=sys.stderr)
        return 4
    print(json.dumps({
        "check": "python-archive-paths", "python_file_count": len(result.python_files),
        "engine_version": result.engine_version, "findings": result.findings,
        "scope": "Python intraprocedural archive-path writes; other vulnerabilities are not assessed",
    }))
    return 1 if result.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
