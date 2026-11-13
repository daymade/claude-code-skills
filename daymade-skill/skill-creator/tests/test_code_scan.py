"""Calibrate the real rule against #1499 and gate incomplete engine receipts."""

import json
import hashlib
from pathlib import Path
import shutil
import secrets
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import code_scan, security_scan
from scripts.package_skill import package_skill, validate_security_marker


def make_skill(tmp_path):
    root = tmp_path / "sample skill"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: Test archive extraction\n---\n# Extract\n"
    )
    (root / "extract.py").write_text("print('ok')\n")
    return root


def scan(root):
    return code_scan.run_code_scan(
        root, security_scan.iter_security_relevant_files(root),
        security_scan.calculate_skill_hash(root),
    )


def engine_report(command, **kwargs):
    stage = Path(command[-1])
    assert kwargs["cwd"] == stage
    assert (stage / ".semgrepignore").read_text() == ""
    assert "SEMGREP_APP_TOKEN" not in kwargs["env"]
    assert "--metrics=off" in command and "--no-rewrite-rule-ids" in command
    return {
        "version": code_scan.SEMGREP_VERSION, "results": [], "errors": [],
        "paths": {"scanned": [str(stage / "extract.py")]},
    }


@pytest.mark.parametrize("key,value", [
    ("results", None), ("results", {}), ("errors", None), ("errors", {}),
    ("paths", None), ("paths", []), ("paths", {}),
    ("paths", {"scanned": None}), ("paths", {"scanned": []}),
    ("paths", {"scanned": [1]}), ("version", "old"),
    ("errors", [{"type": "ParseError", "path": "unknown.py"}]),
])
def test_incomplete_report_never_passes(tmp_path, monkeypatch, key, value):
    root = make_skill(tmp_path)
    def fake(command, **kwargs):
        report = engine_report(command, **kwargs)
        report[key] = value
        return SimpleNamespace(returncode=0, stdout=json.dumps(report))
    monkeypatch.setattr(code_scan.subprocess, "run", fake)
    with pytest.raises((RuntimeError, ValueError)):
        scan(root)


@pytest.mark.parametrize("key", ["results", "errors", "paths", "version"])
def test_missing_report_field_never_passes(tmp_path, monkeypatch, key):
    root = make_skill(tmp_path)
    def fake(command, **kwargs):
        report = engine_report(command, **kwargs)
        del report[key]
        return SimpleNamespace(returncode=0, stdout=json.dumps(report))
    monkeypatch.setattr(code_scan.subprocess, "run", fake)
    with pytest.raises(RuntimeError):
        scan(root)


@pytest.mark.parametrize("exit_code,findings", [(0, True), (1, False), (2, False)])
def test_exit_status_is_not_a_verdict(tmp_path, monkeypatch, exit_code, findings):
    root = make_skill(tmp_path)
    def fake(command, **kwargs):
        report = engine_report(command, **kwargs)
        report["results"] = [{}] if findings else []
        return SimpleNamespace(returncode=exit_code, stdout=json.dumps(report))
    monkeypatch.setattr(code_scan.subprocess, "run", fake)
    with pytest.raises(RuntimeError):
        scan(root)


@pytest.mark.parametrize("output", ["", "null", "[]", "not JSON"])
def test_invalid_json_never_passes(tmp_path, monkeypatch, output):
    root = make_skill(tmp_path)
    monkeypatch.setattr(code_scan.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=output))
    with pytest.raises(RuntimeError):
        scan(root)


@pytest.mark.parametrize("error", [OSError("engine missing"), subprocess.TimeoutExpired("semgrep", 1)])
def test_engine_failure_never_passes(tmp_path, monkeypatch, error):
    root = make_skill(tmp_path)
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(code_scan.subprocess, "run", fail)
    with pytest.raises(RuntimeError):
        scan(root)


def test_missing_engine_fails_closed(tmp_path, monkeypatch):
    root = make_skill(tmp_path)
    monkeypatch.setattr(code_scan.sys, "executable", str(tmp_path / "missing" / "python"))
    monkeypatch.setattr(code_scan.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="unavailable"):
        scan(root)


def test_no_python_reports_not_applicable_without_engine(tmp_path, monkeypatch):
    root = make_skill(tmp_path)
    (root / "extract.py").unlink()
    monkeypatch.setattr(code_scan.subprocess, "run", lambda *a, **k: pytest.fail("unnecessary engine"))
    result = scan(root)
    assert result.engine_version == "not-applicable"
    assert result.python_files == ()


def test_snapshot_covers_evals_but_excludes_local_tests(tmp_path, monkeypatch):
    root = make_skill(tmp_path)
    (root / "evals").mkdir()
    (root / "evals" / "case.py").write_text("pass\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_case.py").write_text("not Python syntax\n")
    monkeypatch.setenv("SEMGREP_APP_TOKEN", "synthetic-unused-token")
    def fake(command, **kwargs):
        report = engine_report(command, **kwargs)
        stage = Path(command[-1])
        assert (stage / "evals" / "case.py").is_file()
        assert not (stage / "tests").exists()
        report["paths"]["scanned"].append(str(stage / "evals" / "case.py"))
        return SimpleNamespace(returncode=0, stdout=json.dumps(report))
    monkeypatch.setattr(code_scan.subprocess, "run", fake)
    assert scan(root).python_files == ("evals/case.py", "extract.py")


def test_policy_change_during_analysis_never_passes(tmp_path, monkeypatch):
    root = make_skill(tmp_path)
    policies = iter(["before", "after"])
    monkeypatch.setattr(code_scan, "policy_hash", lambda: next(policies))
    def fake(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(engine_report(command, **kwargs)))
    monkeypatch.setattr(code_scan.subprocess, "run", fake)
    with pytest.raises(RuntimeError, match="policy changed"):
        scan(root)


def test_real_rule_calibration(tmp_path):
    """Run the shipped engine, not a mock or a test that merely counts rules."""
    root = make_skill(tmp_path)
    fixture = Path(__file__).parent / "fixtures" / "repomix_1499.py"
    # Preserve the public source shape at 8f055dd91083ef003d41c510b136081840a0bb0b,
    # repomix-unmixer/scripts/unmix_repomix.py (before the #1499 repair).
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == "aecb7b9e6a8a843fccd58bae0447e53e4e3a9151e2c02fd1501aec3951a594b4"
    shutil.copyfile(fixture, root / "original.py")
    cases = {
        "renamed": ("p = item.get('path')\nq = Path(base) / p\nq.write_text('data')", True),
        "subscript": ("p = item['path']\nopen(Path(base) / p, 'wb').write(b'data')", True),
        "xml": ("item = ET.fromstring(text)\np = item.attrib['path']\n(Path(base) / p).write_bytes(b'data')", True),
        "resolve_only": ("p = item.get('path')\nq = (Path(base) / p).resolve()\nq.write_text('data')", True),
        "late_guard": ("p = item.get('path')\nq = (Path(base) / p).resolve()\nq.write_text('data')\nif not q.is_relative_to(base):\n    raise ValueError()", True),
        "no_rejection": ("p = item.get('path')\nq = (Path(base) / p).resolve()\nif not q.is_relative_to(base):\n    print('bad')\nq.write_text('data')", True),
        "safe_guard": ("p = item.get('path')\nq = (Path(base) / p).resolve()\nif not q.is_relative_to(base):\n    raise ValueError()\nq.write_text('data')", False),
        "constant": ("q = Path(base) / 'known.txt'\nq.write_text('data')", False),
        "read": ("p = item.get('path')\nopen(Path(base) / p, 'r').read()", False),
        "keyword_mode": ("p = item.get('path')\nopen(Path(base) / p, mode='w').write('data')", True),
        "suppression": ("p = item.get('path')\n(Path(base) / p).write_text('data')  # nosemgrep", True),
        "explicit_target": ("item = {'path': 'chosen.txt'}\nPath(item['path']).write_text('data')", False),
        "aliases": ("from pathlib import Path as Destination\nimport json as parser\nitem = parser.loads(text)\nDestination(base, item['path']).write_text('data')", True),
        "inverted_guard": ("p = item.get('path')\nq = (Path(base) / p).resolve()\nif q.is_relative_to(base):\n    raise ValueError()\nq.write_text('data')", True),
        "io_alias": ("from io import open as write_file\np = item.get('path')\nwrite_file(Path(base) / p, 'a').write('data')", True),
    }
    for name, (body, _) in cases.items():
        (root / f"{name}.py").write_text(
            "from pathlib import Path\nimport json\nimport xml.etree.ElementTree as ET\n"
            "def extract(text, base):\n    item = json.loads(text)\n" +
            "\n".join("    " + line for line in body.splitlines()) + "\n"
        )
    result = scan(root)
    assert sorted(f["line"] for f in result.findings if f["path"] == "original.py") == [30, 55, 83]
    assert {f["path"] for f in result.findings} == {
        "original.py", *(f"{name}.py" for name, (_, unsafe) in cases.items() if unsafe),
    }
    assert {f["rule"] for f in result.findings} == {"python-uncontrolled-archive-path-write"}


@pytest.mark.parametrize("verbose", [False, True])
def test_real_default_and_verbose_cli_reject_original_vulnerability(tmp_path, verbose):
    root = make_skill(tmp_path)
    shutil.copyfile(Path(__file__).parent / "fixtures" / "repomix_1499.py", root / "extract.py")
    argv = [sys.executable, str(code_scan.ROOT / "scripts" / "security_scan.py"), str(root)]
    if verbose:
        argv.append("--verbose")
    result = subprocess.run(argv, capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "3 finding(s)" in result.stdout
    assert not (root / ".security-scan-passed").exists()
    assert package_skill(root, new_skill=True) is None


def test_real_scan_receipt_and_packaging_consumer(tmp_path):
    root = make_skill(tmp_path)
    result = subprocess.run(
        [sys.executable, str(code_scan.ROOT / "scripts" / "security_scan.py"), str(root)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert validate_security_marker(root)[0]
    assert package_skill(root, new_skill=True).is_file()
    marker = root / ".security-scan-passed"
    receipt = marker.read_text()
    for prefix in ("Checks:", "Code policy hash:", "Python files:", "Semgrep version:"):
        lines = receipt.splitlines()
        for variant in ("missing", "empty", "duplicate", "changed"):
            altered = [line for line in lines if not line.startswith(prefix)]
            if variant == "empty":
                altered.append(prefix)
            elif variant == "duplicate":
                altered = lines + [next(line for line in lines if line.startswith(prefix))]
            elif variant == "changed":
                altered.append(prefix + " stale")
            marker.write_text("\n".join(altered) + "\n")
            assert not validate_security_marker(root)[0], (prefix, variant)
    marker.write_text(f"Security scan passed\nContent hash: {security_scan.calculate_skill_hash(root)}\n")
    assert not validate_security_marker(root)[0]
    marker.write_text(receipt)
    (root / "extract.py").write_text("print('changed')\n")
    assert not validate_security_marker(root)[0]


def test_real_parse_error_does_not_produce_receipt(tmp_path):
    root = make_skill(tmp_path)
    (root / "extract.py").write_text("def invalid(:\n")
    with pytest.raises(RuntimeError, match="analysis error"):
        scan(root)
    result = subprocess.run(
        [sys.executable, str(code_scan.ROOT / "scripts" / "security_scan.py"), str(root)],
        capture_output=True, text=True,
    )
    assert result.returncode == 4, result.stdout + result.stderr
    assert not (root / ".security-scan-passed").exists()


def test_real_secret_gate_is_preserved(tmp_path):
    root = make_skill(tmp_path)
    value = "sk-" + "ant-" + "api03-" + secrets.token_hex(48)[:93] + "AA"
    (root / "key.txt").write_text(f'ANTHROPIC_API_KEY = "{value}"\n')
    result = subprocess.run(
        [sys.executable, str(code_scan.ROOT / "scripts" / "security_scan.py"), str(root)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert not (root / ".security-scan-passed").exists()


@pytest.mark.parametrize("field,value", [
    ("findings", [{"path": "extract.py"}]), ("python_hash", "stale"),
    ("policy_hash", "stale"), ("content_hash", "stale"),
])
def test_marker_rejects_incompatible_code_evidence(tmp_path, field, value):
    from dataclasses import replace
    root = make_skill(tmp_path)
    digest = security_scan.calculate_skill_hash(root)
    clean = code_scan.CodeScanResult(
        [], digest, ("extract.py",), code_scan.SEMGREP_VERSION,
        code_scan.python_content_hash(root, [root / "extract.py"]), code_scan.policy_hash(),
    )
    secret_result = security_scan.GitleaksScanResult([], digest)
    with pytest.raises(ValueError):
        security_scan._create_security_marker(root, secret_result, replace(clean, **{field: value}))
    assert not (root / ".security-scan-passed").exists()


def test_marketplace_inventory_uses_each_registered_skill_policy(tmp_path):
    root = tmp_path.resolve()
    skill = make_skill(tmp_path)
    (skill / "tests").mkdir()
    (skill / "tests" / "unsafe.py").write_text("excluded development fixture\n")
    (skill / "evals").mkdir()
    (skill / "evals" / "case.py").write_text("pass\n")
    (root / "scripts").mkdir()
    (root / "scripts" / "tool.py").write_text("pass\n")
    (root / ".claude-plugin").mkdir()
    manifest = root / ".claude-plugin" / "marketplace.json"
    manifest.write_text(json.dumps({"plugins": [{"source": ".", "skills": [skill.name]}]}))
    assert {p.relative_to(root).as_posix() for p in code_scan.marketplace_python_files(root)} == {
        "sample skill/extract.py", "sample skill/evals/case.py", "scripts/tool.py",
    }
    for source in ("missing-skill", "../outside"):
        manifest.write_text(json.dumps({"plugins": [{"source": source}]}))
        with pytest.raises(ValueError):
            code_scan.marketplace_python_files(root)


def test_engine_pin_matches_locked_project():
    assert f'"semgrep=={code_scan.SEMGREP_VERSION}"' in (code_scan.ROOT / "pyproject.toml").read_text()
