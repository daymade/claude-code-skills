"""Regression tests for run_eval.py's per-probe directory isolation.

Covers the concurrency-pollution bug where run_single_query() used to write its
synthetic command file into the shared project directory returned by
find_project_root(). run_eval() fans a query set out across up to num_workers
(default 10) concurrent calls; when they all wrote into the same
.claude/commands/, every claude -p subprocess would see every other in-flight
worker's candidate too, diluting triggering into a systematically depressed,
noisy trigger rate that had nothing to do with the description under test.

These tests replace the `claude` subprocess with a fake executable (a small
shell/python script on PATH via a temp dir prepended to PATH) rather than
mocking subprocess.Popen's internals, so the real select()/os.read() code path
in run_single_query() is exercised end-to-end — only what's on the other end
of the pipe is fake, not the plumbing that reads it. No real `claude -p` calls,
no network, no API costs.

NOTE: this directory is not currently wired into scripts/ci/test-suites.txt (see
that file's admission criteria) — run locally with:
    uv run --frozen python -m pytest tests/test_run_eval_isolation.py -q
"""

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.run_eval import run_single_query

# A single stream-json "result" event is the earliest thing run_single_query()
# accepts as a terminal, non-triggering signal (see the `elif event.get("type")
# == "result": return triggered` branch) — cheapest possible fake response.
_FAKE_RESULT_LINE = json.dumps({"type": "result"})


def _install_fake_claude(bin_dir: Path, on_invoke_dir_file: Path) -> None:
    """Writes a fake `claude` executable onto bin_dir that records its own cwd
    and the contents of ./.claude/commands/ into on_invoke_dir_file, then prints
    one stream-json result event and exits — enough for run_single_query() to
    finish its read loop and return False (not triggered) without ever
    executing a real Claude Code subprocess."""
    fake_claude = bin_dir / "claude"
    script = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import json
        import os
        from pathlib import Path

        cwd = os.getcwd()
        commands_dir = Path(cwd) / ".claude" / "commands"
        names = sorted(p.name for p in commands_dir.glob("*.md")) if commands_dir.is_dir() else []
        Path({str(on_invoke_dir_file)!r}).write_text(json.dumps({{"cwd": cwd, "command_files": names}}))
        print(json.dumps({{"type": "result"}}))
        """)
    fake_claude.write_text(script)
    fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def fake_claude_on_path(tmp_path, monkeypatch):
    """Prepends a directory containing a fake `claude` executable onto PATH, and
    returns a factory that gives each call its own recording file so concurrent
    calls in the same test don't clobber each other's cwd/command-file capture."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    counter = {"n": 0}

    def _make_recorder() -> Path:
        counter["n"] += 1
        record_file = tmp_path / f"invocation-{counter['n']}.json"
        _install_fake_claude(bin_dir, record_file)
        return record_file

    return _make_recorder


def test_probe_runs_in_its_own_temp_directory_not_the_shared_project_root(fake_claude_on_path, tmp_path):
    """The regression this bug fix targets: cwd passed to the claude subprocess
    must NOT be the shared project_root — it must be a fresh directory unique to
    this call, so a concurrent sibling call's candidate never lands in the same
    .claude/commands/."""
    shared_project_root = str(tmp_path / "shared-project-root")
    record_file = fake_claude_on_path()

    run_single_query(
        query="does this trigger?",
        skill_name="demo-skill",
        skill_description="A demo skill description.",
        timeout=10,
        project_root=shared_project_root,
    )

    recorded = json.loads(record_file.read_text())
    assert recorded["cwd"] != shared_project_root
    assert recorded["cwd"] != str(tmp_path)


def test_probe_directory_contains_only_its_own_candidate_file(fake_claude_on_path, tmp_path):
    """While the probe subprocess is running, its .claude/commands/ must contain
    exactly the one synthetic command file for this call — not files left behind
    by any concurrently-running sibling probe (simulated here by pre-seeding a
    second, unrelated command file directly in the probe's own directory would be
    circular; instead we assert the directory the fake claude actually saw had
    exactly one .md file, proving run_single_query() never points cwd at a
    directory anyone else could have written into)."""
    record_file = fake_claude_on_path()

    run_single_query(
        query="does this trigger?",
        skill_name="demo-skill",
        skill_description="A demo skill description.",
        timeout=10,
        project_root=str(tmp_path / "shared-project-root"),
    )

    recorded = json.loads(record_file.read_text())
    assert len(recorded["command_files"]) == 1
    assert recorded["command_files"][0].startswith("demo-skill-skill-")
    assert recorded["command_files"][0].endswith(".md")


def test_concurrent_calls_get_distinct_isolated_directories(fake_claude_on_path, tmp_path):
    """Two separate calls given the same project_root — standing in for what
    run_eval()'s ProcessPoolExecutor actually fans out concurrently, run here
    sequentially since the fixture's fake `claude` script is a single shared
    file on PATH — must land in two different directories, each seeing only its
    own candidate file. This is a structural property, not a timing-dependent
    one: under the old code (cwd=project_root for every call) both calls would
    report the *same* cwd even run sequentially, so this still catches the
    regression without needing genuine OS-level concurrency in the test."""
    # fake_claude_on_path() overwrites the single `claude` script on the fake
    # PATH the moment it's called, so each recorder must be installed
    # immediately before the run_single_query() call it belongs to — installing
    # both upfront would let the second install silently clobber the first
    # before it's ever invoked.
    shared_project_root = str(tmp_path / "shared-project-root")

    record_a = fake_claude_on_path()
    run_single_query(
        query="query A", skill_name="skill-a", skill_description="desc A",
        timeout=10, project_root=shared_project_root,
    )

    record_b = fake_claude_on_path()
    run_single_query(
        query="query B", skill_name="skill-b", skill_description="desc B",
        timeout=10, project_root=shared_project_root,
    )

    recorded_a = json.loads(record_a.read_text())
    recorded_b = json.loads(record_b.read_text())

    assert recorded_a["cwd"] != recorded_b["cwd"]
    assert recorded_a["command_files"] == [f for f in recorded_a["command_files"] if f.startswith("skill-a-skill-")]
    assert recorded_b["command_files"] == [f for f in recorded_b["command_files"] if f.startswith("skill-b-skill-")]


def test_probe_directory_is_removed_after_the_call_returns(fake_claude_on_path, tmp_path):
    """The old code only unlinked the single command file; the probe now owns a
    whole throwaway directory tree, so cleanup must remove the entire tree (not
    just the .md file) and must not leak temp directories across repeated runs."""
    record_file = fake_claude_on_path()

    run_single_query(
        query="does this trigger?",
        skill_name="demo-skill",
        skill_description="A demo skill description.",
        timeout=10,
        project_root=str(tmp_path / "shared-project-root"),
    )

    recorded = json.loads(record_file.read_text())
    assert not Path(recorded["cwd"]).exists()


def test_shared_project_root_is_left_untouched(fake_claude_on_path, tmp_path):
    """Secondary, more visible symptom of the original bug: a live Claude Code
    session working in the real project directory being evaluated would see a
    flood of <skill>-skill-<hash> junk entries appear in its own available_skills
    while an eval was running, because the probe wrote into that same shared
    .claude/commands/. The real project directory must never be touched at all."""
    shared_project_root = tmp_path / "shared-project-root"
    shared_project_root.mkdir()
    fake_claude_on_path()

    run_single_query(
        query="does this trigger?",
        skill_name="demo-skill",
        skill_description="A demo skill description.",
        timeout=10,
        project_root=str(shared_project_root),
    )

    assert not (shared_project_root / ".claude").exists()
