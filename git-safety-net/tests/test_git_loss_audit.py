#!/usr/bin/env python3
"""Regression tests for the at-risk-work audit and, above all, its exit-code boundary.

Mode B routes "what could I lose?" here, and Mode D requires this evidence path before
any rebase or branch-delete. Its design splits two kinds of state:

  exit 1 — surprising and actionable: commits that exist on no remote (reachable from HEAD,
           a worktree HEAD, a branch, a tag, or ANY other local ref that holds a commit),
           dirty or unavailable worktrees, or incomplete content scans (unreadable ref,
           failed enumeration, Git scan diagnostics) — an incomplete audit is not clean.
  exit 0 — known and recoverable: stashes and dangling commits. These get an advisory
           line, not an alarm.

That boundary is the thing worth pinning. Widening exit 1 to cover a routine stash
would make the audit cry wolf on healthy repositories, and this Skill's own guidance
says a check that misfires on healthy input is worse than no check, because it trains
people to bypass it. Narrowing exit 1 would silently drop the warning that matters.

Every expectation was calibrated by running the script against the fixture first.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_loss_audit.sh"


class LossAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="git-loss-audit-", dir=temp_parent
        )
        self.root = Path(self.temp_dir.name)
        fixture_home = self.root / "home"
        fixture_home.mkdir()
        self.env = dict(os.environ, HOME=str(fixture_home), GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
        self.remote = self.root / "remote.git"
        self.repo = self.root / "repo"
        self.git("init", "-q", "-b", "main", "--bare", str(self.remote))
        self.git("init", "-q", "-b", "main", str(self.repo))
        self.in_repo("config", "user.email", "fixture@example.invalid")
        self.in_repo("config", "user.name", "Fixture")
        # Fixture repositories must be hermetic: a machine-global core.hooksPath (for
        # example a pre-push scanner) would otherwise fire on fixture commits/pushes and
        # fail setUp for reasons unrelated to the script under test.
        no_hooks = self.root / "no-hooks"
        no_hooks.mkdir()
        self.in_repo("config", "core.hooksPath", str(no_hooks))
        self.git("-C", str(self.remote), "config", "core.hooksPath", str(no_hooks))
        self.in_repo("remote", "add", "origin", str(self.remote))
        self.write("a.txt", "a\n")
        self.commit("base")
        self.in_repo("push", "-q", "origin", "main")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # ---- helpers -------------------------------------------------------------

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True, env=self.env)

    def in_repo(self, *args: str) -> subprocess.CompletedProcess:
        return self.git("-C", str(self.repo), *args)

    def write(self, relative: str, text: str) -> None:
        (self.repo / relative).write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.in_repo("add", "-A")
        self.in_repo("commit", "-q", "-m", message)

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
            env=self.env,
        )

    # ---- the exit-code boundary ---------------------------------------------

    def test_fully_pushed_repository_is_quiet(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("local-only: 0", result.stdout)
        self.assertIn("Zero loss risk", result.stdout)

    def test_commit_on_no_remote_is_actionable(self) -> None:
        self.write("b.txt", "b\n")
        self.commit("local only")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("local only", result.stdout)

    def test_a_stash_alone_does_not_raise_an_alarm(self) -> None:
        """Routine state must stay exit 0, or the audit trains people to ignore it."""
        self.write("a.txt", "dirty\n")
        self.in_repo("stash", "-q")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("stashes: 1", result.stdout)

    def test_a_dangling_commit_alone_does_not_raise_an_alarm(self) -> None:
        """Recoverable-now, gc-eligible-later earns advice, not an alarm."""
        self.in_repo("switch", "-qc", "tmp")
        self.write("x.txt", "orphan\n")
        self.commit("orphan work")
        self.in_repo("switch", "-q", "main")
        self.in_repo("branch", "-qD", "tmp")
        # A deleted branch is still reflog-reachable; expiry is what makes it dangle.
        self.in_repo(
            "reflog", "expire", "--expire=now", "--expire-unreachable=now", "--all"
        )

        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dangling: 1", result.stdout)
        # And it must point at the tool that makes them gc-proof, not just count them.
        self.assertIn("git_preserve_danglers.sh", result.stdout)

    # ---- non-standard refs (commits hidden from a branch/tag scan) ------------

    def check_reflog_only_commit(self, linked: bool) -> None:
        checkout = self.repo
        base = self.in_repo("rev-parse", "HEAD").stdout.strip()
        if linked:
            checkout = self.root / "reflog-worktree"
            self.in_repo("worktree", "add", "--detach", str(checkout), base)
        else:
            self.in_repo("switch", "--detach", base)
        (checkout / "recovery.txt").write_text("recoverable work\n", encoding="utf-8")
        self.git("-C", str(checkout), "add", "recovery.txt")
        self.git("-C", str(checkout), "commit", "-q", "-m", "reflog recovery work")
        sha = self.git("-C", str(checkout), "rev-parse", "HEAD").stdout.strip()
        self.git("-C", str(checkout), "switch", "--detach", base)
        self.assertNotIn(sha, self.in_repo("rev-list", "--all").stdout)
        self.assertNotIn(sha, self.in_repo("fsck", "--dangling").stdout)
        def user_refs() -> list[str]:
            refs = self.in_repo("for-each-ref", "--format=%(refname) %(objectname)").stdout
            return [line for line in refs.splitlines() if not line.startswith("refs/remotes/")]
        refs_before = user_refs()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("reflog-only: 1", result.stdout)
        self.assertIn("reflog recovery work", result.stdout)
        self.assertNotIn("Zero loss risk", result.stdout)
        self.assertIn("does not pin reflog-only commits", result.stdout)
        self.assertEqual(refs_before, user_refs())

    def test_primary_reflog_only_work_is_reported_without_alarm(self) -> None:
        self.check_reflog_only_commit(linked=False)

    def test_linked_worktree_reflog_only_work_is_reported_without_alarm(self) -> None:
        self.check_reflog_only_commit(linked=True)

    def hide_a_commit(self, refname: str = "refs/queued/work", subject: str = "hidden work") -> str:
        """Create a commit reachable from no branch/tag/HEAD and pin it under a
        non-standard ref. The ref keeps it out of the dangling section too, so this
        is exactly the double blind spot the audit must close."""
        self.in_repo("switch", "-qc", "tmp")
        self.write("h.txt", "hidden\n")
        self.commit(subject)
        sha = self.in_repo("rev-parse", "HEAD").stdout.strip()
        self.in_repo("switch", "-q", "main")
        self.in_repo("update-ref", refname, sha)
        self.in_repo("branch", "-qD", "tmp")
        return sha

    def test_commit_held_only_by_a_nonstandard_ref_is_actionable(self) -> None:
        """Reachable from no branch/tag/HEAD/remote: must be enumerated as local-only."""
        self.hide_a_commit()
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("hidden work", result.stdout)
        self.assertIn("refs/queued/work", result.stdout)
        self.assertIn("local-only: 1", result.stdout)

    def test_nonstandard_ref_to_a_pushed_commit_stays_quiet(self) -> None:
        """Healthy contrast: the namespace alone is not the alarm — the commit is
        already on the remote, so there is nothing local-only."""
        sha = self.in_repo("rev-parse", "HEAD").stdout.strip()
        self.in_repo("update-ref", "refs/queued/already-upstream", sha)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("refs/queued/already-upstream", result.stdout)
        self.assertIn("local-only: 0", result.stdout)

    def test_non_commit_ref_is_listed_without_an_alarm(self) -> None:
        """A ref holding a tree (or blob) cannot carry commits: report it separately,
        do not fold it into the commit scan, and do not fail a healthy repo."""
        tree = self.in_repo("rev-parse", "HEAD^{tree}").stdout.strip()
        self.in_repo("update-ref", "refs/queued/tree-pin", tree)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("refs/queued/tree-pin", result.stdout)
        self.assertIn("non-commit", result.stdout)
        self.assertIn("1 non-commit ref(s) need manual review", result.stdout)
        self.assertNotIn("Zero loss risk", result.stdout)

    def test_blob_ref_requires_manual_review_without_an_alarm(self) -> None:
        blob = self.in_repo("rev-parse", "HEAD:a.txt").stdout.strip()
        self.in_repo("update-ref", "refs/queued/blob-pin", blob)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("refs/queued/blob-pin -> blob", result.stdout)
        self.assertIn("1 non-commit ref(s) need manual review", result.stdout)
        self.assertNotIn("Zero loss risk", result.stdout)

    def test_blob_tag_is_not_silently_skipped_by_the_commit_walk(self) -> None:
        blob = self.in_repo("rev-parse", "HEAD:a.txt").stdout.strip()
        self.in_repo("update-ref", "refs/tags/blob-pin", blob)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("refs/tags/blob-pin -> blob", result.stdout)
        self.assertIn("1 non-commit ref(s) need manual review", result.stdout)
        self.assertNotIn("Zero loss risk", result.stdout)

    def test_malformed_ref_warns_even_when_enumeration_exits_zero(self) -> None:
        broken = self.repo / ".git" / "refs" / "queued" / "broken"
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_text("not-an-object\n", encoding="utf-8")
        listing = self.in_repo("for-each-ref", "--format=%(refname)")
        self.assertEqual(listing.returncode, 0)
        self.assertIn("ignoring broken ref refs/queued/broken", listing.stderr)
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("local ref enumeration is INCOMPLETE", result.stdout)
        self.assertIn("ignoring broken ref refs/queued/broken", result.stderr)
        self.assertNotIn("Zero loss risk", result.stdout)

    def test_corrupt_unreferenced_object_fails_the_object_scan(self) -> None:
        # No ref points at this object; only the fsck stage can discover its damage.
        # Use a distinct file so the corrupted blob is not part of the base commit.
        self.write("orphan.txt", "unreferenced object\n")
        blob = self.in_repo("hash-object", "-w", "orphan.txt").stdout.strip()
        (self.repo / "orphan.txt").unlink()
        obj = self.repo / ".git" / "objects" / blob[:2] / blob[2:]
        obj.chmod(0o600)
        obj.write_bytes(b"broken fixture object\n")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("object scan is INCOMPLETE", result.stdout)
        self.assertIn("object corrupt or missing", result.stderr)
        self.assertNotIn("Zero loss risk", result.stdout)

    def test_unreadable_ref_fails_the_audit_loudly(self) -> None:
        """Error injection: a ref resolving to no object must not pass as clean."""
        broken_dir = self.repo / ".git" / "refs" / "queued"
        broken_dir.mkdir(parents=True, exist_ok=True)
        (broken_dir / "broken").write_text("f" * 40 + "\n", encoding="utf-8")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("refs/queued/broken", result.stdout)
        self.assertIn("UNREADABLE", result.stdout)
        self.assertNotIn("Zero loss risk", result.stdout)

    def test_unborn_head_does_not_hide_ref_held_commits(self) -> None:
        """With an unborn HEAD, `git log HEAD ...` fails outright; the old `|| true`
        swallow printed '(none)' over real ref-held commits. The scan must run on the
        remaining roots and still find them."""
        self.hide_a_commit()
        self.in_repo("symbolic-ref", "HEAD", "refs/heads/unborn")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("hidden work", result.stdout)
        self.assertIn("unborn", result.stdout)

    def test_a_failed_local_only_log_is_not_reported_as_clean(self) -> None:
        """Error injection at the enumeration step itself: a failing `git log` must
        surface as UNKNOWN + exit 1, never as the zero-risk verdict."""
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git, "tests require git on PATH")
        stub_dir = self.root / "stubbin"
        stub_dir.mkdir()
        stub = stub_dir / "git"
        stub.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "log" ]; then\n'
            '  echo "fatal: injected git log failure" >&2\n'
            "  exit 128\n"
            "fi\n"
            f'exec "{real_git}" "$@"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
        env = dict(self.env, PATH=f"{stub_dir}{os.pathsep}{os.environ['PATH']}")
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=str(self.repo), capture_output=True, text=True, env=env
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("UNKNOWN", result.stdout)
        self.assertNotIn("Zero loss risk", result.stdout)
        self.assertIn("injected git log failure", result.stderr)

    def run_with_scan_fault(self, command: tuple[str, ...], exit_code: int) -> subprocess.CompletedProcess:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        stub_dir = self.root / ("stub-" + "-".join(command) + str(exit_code))
        stub_dir.mkdir()
        condition = " && ".join(f'[ "${i}" = "{arg}" ]' for i, arg in enumerate(command, 1))
        if command == ("status",):
            condition = '[ "$1" = "-C" ] && [ "$3" = "status" ]'
        stub = stub_dir / "git"
        stub.write_text(
            "#!/bin/sh\n"
            f"if {condition}; then\n"
            '  echo "warning: injected incomplete scan" >&2\n'
            f"  exit {exit_code}\n"
            "fi\n"
            f'exec "{real_git}" "$@"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
        return subprocess.run(
            ["bash", str(SCRIPT)], cwd=str(self.repo), capture_output=True, text=True,
            env=dict(self.env, PATH=f"{stub_dir}{os.pathsep}{os.environ['PATH']}"),
        )

    def test_content_scan_failures_cannot_report_clean(self) -> None:
        for command in (("for-each-ref",), ("worktree", "list"), ("rev-list",), ("stash", "list"), ("fsck",), ("status",)):
            with self.subTest(command=command):
                result = self.run_with_scan_fault(command, 128)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("INCOMPLETE", result.stdout)
                self.assertIn("injected incomplete scan", result.stderr)
                self.assertNotIn("Zero loss risk", result.stdout)

    def test_content_scan_diagnostics_cannot_report_clean_with_exit_zero(self) -> None:
        for command in (("for-each-ref",), ("worktree", "list"), ("log",), ("rev-list",), ("stash", "list"), ("fsck",), ("status",)):
            with self.subTest(command=command):
                result = self.run_with_scan_fault(command, 0)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("INCOMPLETE", result.stdout)
                self.assertIn("injected incomplete scan", result.stderr)
                self.assertNotIn("Zero loss risk", result.stdout)

    # ---- report shape --------------------------------------------------------

    def test_every_section_and_the_verdict_are_present(self) -> None:
        """The sections are the audit's scope claim; a silently dropped one narrows
        what 'clean' means without anything looking wrong."""
        result = self.run_script()
        for heading in (
            "Other local refs",
            "Local-only commits",
            "Worktrees",
            "Reflog-only commits",
            "Stashes",
            "Dangling commits",
            "Verdict",
        ):
            self.assertIn(heading, result.stdout, f"missing section: {heading}")

    def test_outside_a_repository_is_an_error(self) -> None:
        outside = self.root / "not-a-repo"
        outside.mkdir()
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=str(outside), capture_output=True, text=True, env=self.env
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
