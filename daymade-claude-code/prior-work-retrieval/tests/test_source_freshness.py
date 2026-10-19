"""Exercise freshness through the shipped retrieve/complete/check CLI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prior_work.py"


class SourceFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.source = self.repo / "evidence"
        self.source.mkdir()
        (self.source / "contract.md").write_text("Verified reusable contract.\n")
        (self.source / "other.md").write_text("Another reusable candidate.\n")
        self.env = dict(os.environ, HOME=str(self.root), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=os.devnull)
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "RIPGREP_CONFIG_PATH"):
            self.env.pop(key, None)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.commit()
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({"schema_version": 1, "state_dir": str(self.root / "state"),
            "sources": [{"id": "docs", "carrier": "docs", "mode": "filesystem",
                         "root": str(self.source), "includes": ["**/*.md"],
                         "excludes": ["**/excluded/**"], "required": True}]}))

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env,
                              capture_output=True, text=True, check=True).stdout.strip()

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-qm", "fixture update")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--manifest", str(self.manifest), *args],
                              env=self.env, capture_output=True, text=True)

    def retrieve(self, *extra):
        result = self.cli("retrieve", "--business-outcome", "Reuse the verified provider contract.",
                          "--outcome-term", "reusable", "--query", "reusable", "--term", "reusable",
                          "--session-id", "fixture", "--json", *extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads(result.stdout)
        self.candidate = next(c for c in run["candidates"] if c["path"].endswith("contract.md"))
        return run

    def complete(self, run):
        return self.cli("complete", "--run", run["run_id"], "--session-id", "fixture",
                        "--reuse", self.candidate["candidate_id"] + "=reuse the opened verified contract", "--json")

    def test_unrelated_commit_and_identical_rebase_preserve_verified_evidence(self):
        run = self.retrieve()
        (self.repo / "unrelated.txt").write_text("unrelated change\n")
        self.commit()
        # Rewrite only commit identity, as a pure rebase does; file bytes agree.
        self.git("commit", "--amend", "-qm", "same tree, new identity")
        os.utime(self.source / "contract.md", None)
        result = self.complete(run)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["decisions"][0]["verification"]["git_head"], self.git("rev-parse", "HEAD"))
        self.assertEqual(self.cli("check", "--session-id", "fixture", "--json").returncode, 0)

    def test_source_add_delete_change_and_rename_require_another_search(self):
        operations = {
            "add": lambda: (self.source / "00-better.md").write_text("Better reusable contract.\n"),
            "delete": lambda: (self.source / "other.md").unlink(),
            "change": lambda: (self.source / "other.md").write_text("New reusable authority.\n"),
            "rename": lambda: (self.source / "other.md").rename(self.source / "renamed.md"),
        }
        for name, operation in operations.items():
            with self.subTest(name=name):
                baseline = self.git("rev-parse", "HEAD")
                run = self.retrieve()
                operation()
                self.commit()
                result = self.complete(run)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("source scope changed", result.stderr)
                # These are isolated fixture commits; restore through a new
                # commit rather than discard state or rewrite public history.
                self.git("revert", "--no-edit", "HEAD")
                self.assertEqual(self.git("rev-parse", "HEAD^{tree}"), self.git("rev-parse", baseline + "^{tree}"))

    def test_uncommitted_addition_and_selected_bytes_are_not_hidden_by_same_head(self):
        run = self.retrieve()
        (self.source / "new.md").write_text("New reusable authority.\n")
        self.assertIn("working scope changed", self.complete(run).stderr)
        self.commit()
        run = self.retrieve()
        path = self.source / "contract.md"
        before = path.stat()
        path.write_text("Changed reusable contract.\n")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertIn("changed", self.complete(run).stderr)

    def test_excluded_and_outside_include_changes_do_not_repeat_search(self):
        run = self.retrieve()
        (self.source / "excluded").mkdir()
        (self.source / "excluded/new.md").write_text("Excluded reusable candidate.\n")
        (self.source / "index.json").write_text("{}")
        self.commit()
        result = self.complete(run)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_slash_globs_keep_the_original_invocation_context(self):
        payload = json.loads(self.manifest.read_text())
        # From this test's external cwd, this is not the same exclusion as
        # '**/excluded/**'. Use the real retrieve to prove the new file is seen.
        payload["sources"][0]["excludes"] = ["excluded/**"]
        self.manifest.write_text(json.dumps(payload))
        run = self.retrieve()
        (self.source / "excluded").mkdir()
        (self.source / "excluded/new.md").write_text("A newly reusable candidate.\n")
        self.commit()
        self.assertIn("source scope changed", self.complete(run).stderr)
        self.assertTrue(any(c["path"].endswith("excluded/new.md") for c in self.retrieve()["candidates"]))

    def test_manifest_and_ignore_dependencies_invalidate(self):
        run = self.retrieve()
        payload = json.loads(self.manifest.read_text())
        payload["sources"][0]["includes"].append("**/*.txt")
        self.manifest.write_text(json.dumps(payload))
        self.assertIn("source definitions changed", self.complete(run).stderr)
        payload["sources"][0]["includes"].pop()
        self.manifest.write_text(json.dumps(payload))
        (self.repo / ".gitignore").write_text("evidence/other.md\n")
        self.commit()
        self.assertIn("scope dependencies changed", self.complete(run).stderr)

    def test_explicit_include_can_expose_git_ignored_untracked_candidate(self):
        (self.repo / ".gitignore").write_text("evidence/ignored.md\n")
        self.commit()
        run = self.retrieve()
        (self.source / "ignored.md").write_text("A newly reusable provider contract.\n")
        self.assertIn("working scope changed", self.complete(run).stderr)

    def nested_git(self, path, *args):
        return subprocess.run(["git", "-C", str(path), *args], env=self.env,
                              capture_output=True, text=True, check=True).stdout.strip()

    def make_nested(self, path):
        path.mkdir(parents=True)
        for args in [("init", "-q"), ("config", "user.name", "Fixture"),
                     ("config", "user.email", "fixture@example.invalid")]:
            self.nested_git(path, *args)
        (path / "nested.md").write_text("New authoritative reusable contract.\n")
        self.nested_git(path, "add", "--", "nested.md")
        self.nested_git(path, "commit", "-qm", "nested fixture")

    def test_new_nested_gitlink_cannot_hide_new_candidates_behind_directory_name(self):
        run = self.retrieve()
        self.make_nested(self.source / "vendor")
        self.commit()
        result = self.complete(run)
        self.assertEqual(result.returncode, 2)
        self.assertIn("changed nested Git repository", result.stderr)
        self.assertTrue(any(c["path"].endswith("vendor/nested.md") for c in self.retrieve()["candidates"]))

    def test_new_untracked_nested_repository_requires_new_search(self):
        run = self.retrieve()
        self.make_nested(self.source / "vendor")
        self.assertEqual(self.complete(run).returncode, 2)
        self.assertTrue(any(c["path"].endswith("vendor/nested.md") for c in self.retrieve()["candidates"]))

    def test_tracked_nested_repository_change_delete_and_dirty_content_recheck(self):
        vendor = self.source / "vendor"
        self.make_nested(vendor)
        self.commit()
        run = self.retrieve()
        (vendor / "new.md").write_text("A new reusable decision.\n")
        self.assertEqual(self.complete(run).returncode, 2)
        self.nested_git(vendor, "add", "--", "new.md")
        self.nested_git(vendor, "commit", "-qm", "advance nested source")
        self.commit()
        self.assertIn("changed nested Git repository", self.complete(run).stderr)
        run = self.retrieve()
        # This embedded-repository fixture intentionally has no .gitmodules.
        self.git("update-index", "--force-remove", "--", "evidence/vendor")
        shutil.rmtree(vendor)
        self.commit()
        self.assertIn("changed nested Git repository", self.complete(run).stderr)

    def test_nested_repository_outside_source_remains_unrelated(self):
        run = self.retrieve()
        other = self.repo / "other/vendor"
        self.make_nested(other)
        self.commit()
        self.assertEqual(self.complete(run).returncode, 0)
        (other / "nested.md").write_text("Changed out-of-scope reusable contract.\n")
        self.nested_git(other, "add", "--", "nested.md")
        self.nested_git(other, "commit", "-qm", "advance outside source")
        self.commit()
        self.assertEqual(self.complete(run).returncode, 0)

    def add_optional_source(self):
        optional = self.repo / "optional"
        optional.mkdir()
        (optional / "notes.md").write_text("An optional reusable note.\n")
        self.commit()
        payload = json.loads(self.manifest.read_text())
        payload["sources"].append({"id": "optional", "carrier": "docs", "mode": "filesystem",
                                   "root": str(optional), "includes": ["**/*.md"], "required": False})
        self.manifest.write_text(json.dumps(payload))

    def change_optional_definition(self):
        payload = json.loads(self.manifest.read_text())
        payload["sources"][1]["max_results"] = 9
        self.manifest.write_text(json.dumps(payload))

    def test_unused_optional_definition_keeps_required_completion_valid(self):
        self.add_optional_source()
        run = self.retrieve()
        self.change_optional_definition()
        self.assertEqual(self.complete(run).returncode, 0)

    def test_decided_optional_and_promoted_required_definition_changes_recheck(self):
        self.add_optional_source()
        run = self.retrieve()
        optional = next(c for c in run["candidates"] if c["source_id"] == "optional")
        self.change_optional_definition()
        for decision in ("reuse", "adapt", "reject"):
            with self.subTest(decision=decision):
                result = self.cli("complete", "--run", run["run_id"], "--session-id", "fixture",
                                  "--reuse", self.candidate["candidate_id"] + "=reuse the required opened contract",
                                  "--" + decision, optional["candidate_id"] + "=specific opened optional-source decision", "--json")
                self.assertEqual(result.returncode, 2)
                self.assertIn("source definition changed", result.stderr)
        run = self.retrieve("--require-source", "optional")
        payload = json.loads(self.manifest.read_text())
        payload["sources"][1]["max_results"] = 8
        self.manifest.write_text(json.dumps(payload))
        self.assertIn("source definition changed", self.complete(run).stderr)

    def test_missing_null_empty_scope_dependencies_fail_closed(self):
        run = self.retrieve()
        path = Path(run["run_path"])
        for value in ("missing", None, ""):
            with self.subTest(value=value):
                payload = json.loads(path.read_text())
                candidate = next(c for c in payload["candidates"] if c["candidate_id"] == self.candidate["candidate_id"])
                if value == "missing":
                    candidate["source_git_state"].pop("dependencies_sha256", None)
                else:
                    candidate["source_git_state"]["dependencies_sha256"] = value
                path.write_text(json.dumps(payload))
                result = self.complete(run)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("scope dependencies changed", result.stderr)

    def test_new_requirement_still_invalidates_the_old_run(self):
        run = self.retrieve()
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "fixture",
                 "prompt": "Find our previous deployment decision and reuse the existing code."}
        env = dict(self.env, PRIOR_WORK_MANIFEST=str(self.manifest))
        result = subprocess.run([sys.executable, str(SCRIPT.with_name("prior_work_hook.py"))],
                                input=json.dumps(event), env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Prior Work Retrieval", result.stdout)
        self.assertIn("newer prompt", self.complete(run).stderr)

    def test_source_root_outside_git_preserves_nested_repository_support(self):
        payload = json.loads(self.manifest.read_text())
        payload["sources"][0]["root"] = str(self.root)
        payload["sources"][0]["includes"] = ["**/*.md"]
        self.manifest.write_text(json.dumps(payload))
        run = self.retrieve()
        self.assertEqual(self.candidate["source_scope"], "legacy")
        self.assertEqual(self.complete(run).returncode, 0)
        (self.repo / "unrelated.txt").write_text("outside source root Git proof\n")
        self.commit()
        self.assertIn("repository HEAD changed", self.complete(run).stderr)

    def test_many_decisions_share_scope_checks_in_the_real_cli(self):
        binary = shutil.which("git", path=self.env["PATH"])
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        log = self.root / "git-calls.txt"
        wrapper = bin_dir / "git"
        wrapper.write_text("#!/bin/sh\nprintf 'call\\n' >> " + shlex.quote(str(log)) +
                           "\nexec " + shlex.quote(binary) + " \"$@\"\n")
        wrapper.chmod(0o755)
        self.env["PATH"] = str(bin_dir) + os.pathsep + self.env["PATH"]
        payload = json.loads(self.manifest.read_text())
        payload["sources"][0]["max_results"] = 200
        self.manifest.write_text(json.dumps(payload))
        for index in range(111):
            (self.source / f"contract-{index:03d}.md").write_text("Verified reusable contract.\n")
        self.commit()
        run = self.retrieve()
        self.assertEqual(len(run["candidates"]), 113)
        log.write_text("")
        self.assertEqual(self.complete(run).returncode, 0)
        single = len(log.read_text().splitlines())
        log.write_text("")
        args = ["complete", "--run", run["run_id"], "--session-id", "fixture", "--json"]
        for candidate in run["candidates"]:
            args += ["--reuse", candidate["candidate_id"] + "=reuse the opened verified contract"]
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        many = len(log.read_text().splitlines())
        self.assertGreater(single, 0)
        self.assertEqual(many, single)


if __name__ == "__main__":
    unittest.main()
