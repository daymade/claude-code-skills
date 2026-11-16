from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts/ci/check_version_progression.py"


# A developer machine may set core.hooksPath or init.templateDir globally, and a
# fixture repository created by `git init` inherits both -- so the suite would
# run the developer's own hooks against its throwaway repos.  Measured: a local
# hook waiting for input on a terminal this suite does not have hung a run
# indefinitely, while the same suite passed in CI, whose git has no global
# config at all.  Neutralising it here keeps the result a property of the
# checker rather than of whoever runs it, and honours the registry's own
# admission rule that a suite touch nothing outside its temp directory.
HERMETIC_GIT = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [*args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **HERMETIC_GIT},
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result


def manifest(audio: str = "1.0.0", docs: str = "2.0.0", metadata: str = "3.0.0") -> dict:
    return {
        "name": "fixture",
        "owner": {"name": "fixture"},
        "metadata": {"version": metadata, "description": "fixture"},
        "plugins": [
            {
                "name": "audio",
                "source": "./daymade-audio",
                "description": "audio",
                "version": audio,
                "skills": ["./transcript-fixer"],
            },
            {
                "name": "docs",
                "source": "./daymade-docs",
                "description": "docs",
                "version": docs,
            },
        ],
    }


class VersionProgressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        run(self.repo, "git", "init", "-q")
        run(self.repo, "git", "config", "user.email", "test@example.invalid")
        run(self.repo, "git", "config", "user.name", "Test")
        (self.repo / ".claude-plugin").mkdir()
        (self.repo / "scripts/ci").mkdir(parents=True)
        (self.repo / "daymade-audio/transcript-fixer").mkdir(parents=True)
        (self.repo / "daymade-docs").mkdir()
        shutil.copy2(CHECKER, self.repo / "scripts/ci/check_version_progression.py")
        self.write_manifest(manifest())
        (self.repo / "daymade-audio/transcript-fixer/SKILL.md").write_text(
            "---\nname: transcript-fixer\ndescription: fixture\n---\n",
            encoding="utf-8",
        )
        (self.repo / "daymade-docs/SKILL.md").write_text(
            "---\nname: docs\ndescription: fixture\n---\n", encoding="utf-8"
        )
        run(self.repo, "git", "add", ".")
        run(self.repo, "git", "commit", "-qm", "base")
        self.base = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()

    def write_manifest(self, value: dict) -> None:
        (self.repo / ".claude-plugin/marketplace.json").write_text(
            json.dumps(value, indent=2) + "\n", encoding="utf-8"
        )

    def commit(self, message: str = "candidate") -> str:
        run(self.repo, "git", "add", ".")
        run(self.repo, "git", "commit", "-qm", message)
        return run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()

    def check(self, candidate: str) -> subprocess.CompletedProcess[str]:
        return run(
            self.repo,
            sys.executable,
            str(CHECKER),
            "--repo",
            str(self.repo),
            "--base",
            self.base,
            "--candidate",
            candidate,
            check=False,
        )

    def test_root_docs_change_needs_no_plugin_bump(self) -> None:
        (self.repo / "README.md").write_text("docs\n", encoding="utf-8")
        self.assertEqual(self.check(self.commit()).returncode, 0)

    def test_changed_skill_without_bump_fails(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 1)
        self.assertIn("content changed but version did not strictly increase", result.stderr)

    def test_changed_skill_with_bump_passes(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        self.write_manifest(manifest(audio="1.1.0"))
        self.assertEqual(self.check(self.commit()).returncode, 0)

    def test_unrelated_plugin_regression_fails(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        self.write_manifest(manifest(audio="1.1.0", docs="1.9.9"))
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 1)
        self.assertIn("plugin 'docs' regresses", result.stderr)

    def test_plugin_metadata_change_requires_plugin_bump(self) -> None:
        value = manifest()
        value["plugins"][1]["description"] = "changed docs description"
        value["plugins"][1]["keywords"] = ["new-keyword"]
        self.write_manifest(value)
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 1)
        self.assertIn("manifest metadata changed without a strict", result.stderr)

    def test_marketplace_metadata_change_requires_catalog_bump(self) -> None:
        value = manifest()
        value["metadata"]["description"] = "changed catalog description"
        self.write_manifest(value)
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 1)
        self.assertIn("metadata fields changed without a strict", result.stderr)

    def test_plugin_order_change_requires_catalog_bump(self) -> None:
        value = manifest()
        value["plugins"].reverse()
        self.write_manifest(value)
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 1)
        self.assertIn("metadata fields changed without a strict", result.stderr)

    def test_reusing_version_after_base_moves_fails(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "first\n", encoding="utf-8")
        self.write_manifest(manifest(audio="1.1.0"))
        first = self.commit("first release")

        run(self.repo, "git", "switch", "-qc", "parallel", self.base)
        skill.write_text(skill.read_text() + "parallel\n", encoding="utf-8")
        self.write_manifest(manifest(audio="1.1.0"))
        second = self.commit("parallel release")

        result = run(
            self.repo,
            sys.executable,
            str(CHECKER),
            "--repo",
            str(self.repo),
            "--base",
            first,
            "--candidate",
            second,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("did not strictly increase", result.stderr)

    def test_layout_change_requires_metadata_bump(self) -> None:
        value = manifest()
        value["plugins"][0]["skills"].append("./new-member")
        self.write_manifest(value)
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 1)
        self.assertIn("layout changed without a strict", result.stderr)

    def test_index_mode_with_nothing_staged_is_not_a_verdict(self) -> None:
        # 2026-09-20, twice in one afternoon: `--candidate-index` run with an empty
        # index reads HEAD's manifest back and reports "no regression" about the
        # working tree it never looked at. The form is correct before a commit; the
        # state where it cannot answer the question is exactly "nothing is staged".
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "unstaged\n", encoding="utf-8")
        result = run(
            self.repo,
            sys.executable,
            str(CHECKER),
            "--repo",
            str(self.repo),
            "--base",
            self.base,
            "--candidate-index",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("nothing is staged", result.stderr)

    def test_candidate_head_is_unaffected_by_the_staged_guard(self) -> None:
        # The guard must not bleed into the form CI uses.
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "unstaged\n", encoding="utf-8")
        result = run(
            self.repo,
            sys.executable,
            str(CHECKER),
            "--repo",
            str(self.repo),
            "--base",
            self.base,
            "--candidate",
            "HEAD",
            check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_index_mode_reads_staged_tree_only(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "staged\n", encoding="utf-8")
        run(self.repo, "git", "add", str(skill.relative_to(self.repo)))
        result = run(
            self.repo,
            sys.executable,
            str(CHECKER),
            "--repo",
            str(self.repo),
            "--base",
            self.base,
            "--candidate-index",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("content changed but version did not strictly increase", result.stderr)

    def test_candidate_cannot_replace_the_checker_that_judges_it(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        (self.repo / "scripts/ci/check_version_progression.py").write_text(
            "raise SystemExit(0)\n", encoding="utf-8"
        )
        candidate = self.commit("candidate replaces its own judge")

        candidate_result = run(
            self.repo,
            sys.executable,
            "scripts/ci/check_version_progression.py",
            check=False,
        )
        self.assertEqual(candidate_result.returncode, 0)

        trusted_checker = self.repo / "trusted-checker.py"
        trusted_checker.write_text(
            run(
                self.repo,
                "git",
                "show",
                f"{self.base}:scripts/ci/check_version_progression.py",
            ).stdout,
            encoding="utf-8",
        )
        trusted_result = run(
            self.repo,
            sys.executable,
            str(trusted_checker),
            "--repo",
            str(self.repo),
            "--base",
            self.base,
            "--candidate",
            candidate,
            check=False,
        )
        self.assertEqual(trusted_result.returncode, 1)
        self.assertIn("version did not strictly increase", trusted_result.stderr)


class CiVersionContextTests(unittest.TestCase):
    setUp = VersionProgressionTests.setUp
    write_manifest = VersionProgressionTests.write_manifest
    commit = VersionProgressionTests.commit

    def workflow_check(self, event: dict[str, str], *, unset: str | None = None):
        workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text()
        step = workflow.split(
            "      - name: Reject stale or reused marketplace versions\n", 1
        )[1].splitlines()
        env = {**os.environ, **HERMETIC_GIT, "TMPDIR": str(self.repo)}
        body = []
        in_run = False
        for line in step:
            if line == "        run: |":
                in_run = True
            elif in_run:
                if line and not line.startswith("          "):
                    break
                body.append(line[10:] if line else "")
            else:
                binding = re.fullmatch(r"          (\w+): \$\{\{ (.*?) \}\}", line)
                if binding:
                    env[binding[1]] = event.get(binding[2], "")
        self.assertTrue(body, "version workflow run block not found")
        if unset is not None:
            env.pop(unset, None)
        return subprocess.run(
            ["bash", "-c", "\n".join(body)], cwd=self.repo, env=env,
            text=True, capture_output=True, check=False,
        )

    def make_pr(self, head: str) -> dict[str, str]:
        run(self.repo, "git", "switch", "-qc", "event-merge", self.base)
        run(self.repo, "git", "merge", "--no-ff", "--no-edit", head)
        merge = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        return {
            "github.event_name": "pull_request",
            "github.base_ref": "main",
            "github.event.repository.default_branch": "main",
            "github.event.pull_request.base.sha": self.base,
            "github.event.pull_request.head.sha": head,
            "github.sha": merge,
        }

    def healthy_pr(self) -> dict[str, str]:
        (self.repo / "README.md").write_text("docs\n", encoding="utf-8")
        return self.make_pr(self.commit())

    def test_pr_uses_event_pair_after_remote_main_advances(self) -> None:
        event = self.healthy_pr()
        run(self.repo, "git", "update-ref", "refs/heads/main", self.base)
        run(self.repo, "git", "remote", "add", "origin", str(self.repo))
        run(self.repo, "git", "switch", "main")
        self.write_manifest(manifest(docs="2.1.0"))
        advanced = self.commit("unrelated later release")
        run(self.repo, "git", "switch", "event-merge")
        wrong_pair = run(
            self.repo, sys.executable, str(CHECKER), "--repo", str(self.repo),
            "--base", advanced, "--candidate", event["github.sha"], check=False,
        )
        self.assertEqual(wrong_pair.returncode, 1)
        self.assertIn("plugin 'docs' regresses", wrong_pair.stderr)
        result = self.workflow_check(event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(event["github.sha"], result.stdout)

    def test_pr_payload_base_may_lag_tested_merge_and_live_main(self) -> None:
        checker = self.repo / "scripts/ci/check_version_progression.py"
        checker.write_text("raise SystemExit(0)\n")
        self.base = self.commit("old payload base has a permissive checker")
        (self.repo / "README.md").write_text("candidate docs\n", encoding="utf-8")
        head = self.commit("PR source")
        run(self.repo, "git", "switch", "-qc", "tested-main", self.base)
        self.write_manifest(manifest(docs="2.1.0"))
        checker.write_text("print('ACTUAL_BASE_CHECKER')\nexec(" + repr(CHECKER.read_text()) + ")\n")
        tested_base = self.commit("main advanced before test merge")
        run(self.repo, "git", "switch", "-qc", "event-merge")
        run(self.repo, "git", "merge", "--no-ff", "--no-edit", head)
        merge = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        event = {
            "github.event_name": "pull_request",
            "github.event.pull_request.base.sha": self.base,
            "github.event.pull_request.head.sha": head,
            "github.sha": merge,
        }
        run(self.repo, "git", "switch", "tested-main")
        self.write_manifest(manifest(docs="2.2.0"))
        live_main = self.commit("main advanced after test merge")
        run(self.repo, "git", "update-ref", "refs/remotes/origin/main", live_main)
        run(self.repo, "git", "switch", "event-merge")
        result = self.workflow_check(event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ACTUAL_BASE_CHECKER", result.stdout)
        self.assertIn(merge, result.stdout)
        # A real release check, not a marker-only stub, must still reject a
        # new payload under the actual main's already-published version.
        run(self.repo, "git", "switch", "-qc", "invalid-head", tested_base)
        skill = self.repo / "daymade-docs/SKILL.md"
        skill.write_text(skill.read_text() + "unbumped payload\n")
        invalid = self.commit("unbumped change")
        run(self.repo, "git", "switch", "-qc", "invalid-merge", tested_base)
        run(self.repo, "git", "merge", "--no-ff", "--no-edit", invalid)
        invalid_merge = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        result = self.workflow_check({**event, "github.event.pull_request.head.sha": invalid, "github.sha": invalid_merge})
        self.assertEqual(result.returncode, 1)
        self.assertIn("ACTUAL_BASE_CHECKER", result.stdout)
        self.assertIn("version did not strictly increase", result.stderr)

    def test_pr_rejects_payload_base_outside_tested_base_history(self) -> None:
        event = self.healthy_pr()
        run(self.repo, "git", "switch", "-qc", "other-base", self.base)
        (self.repo / "other.md").write_text("unrelated base advance\n")
        other = self.commit("not an ancestor of tested base")
        run(self.repo, "git", "switch", "event-merge")
        result = self.workflow_check({**event, "github.event.pull_request.base.sha": other})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL: PR event", result.stderr)

    def test_pr_still_rejects_real_regression(self) -> None:
        self.write_manifest(manifest(docs="1.9.9"))
        result = self.workflow_check(self.make_pr(self.commit()))
        self.assertEqual(result.returncode, 1)
        self.assertIn("plugin 'docs' regresses", result.stderr)

    def test_pr_still_rejects_unbumped_content_using_base_checker(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        (self.repo / "scripts/ci/check_version_progression.py").write_text(
            "raise SystemExit(0)\n", encoding="utf-8"
        )
        result = self.workflow_check(self.make_pr(self.commit()))
        self.assertEqual(result.returncode, 1)
        self.assertIn("version did not strictly increase", result.stderr)

    def test_pr_rejects_missing_empty_and_invalid_event_identity(self) -> None:
        event = self.healthy_pr()
        for expression, name in [
            ("github.event.pull_request.base.sha", "PR_BASE_SHA"),
            ("github.event.pull_request.head.sha", "PR_HEAD_SHA"),
            ("github.sha", "EVENT_SHA"),
        ]:
            for value in [None, "", " ", "0" * 40, "HEAD"]:
                with self.subTest(field=name, value=value):
                    changed = {**event, expression: value or ""}
                    result = self.workflow_check(
                        changed, unset=name if value is None else None
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("FAIL: PR event", result.stderr)

    def test_pr_rejects_head_and_parent_mismatches(self) -> None:
        event = self.healthy_pr()
        for expression in [
            "github.sha", "github.event.pull_request.base.sha",
            "github.event.pull_request.head.sha",
        ]:
            with self.subTest(field=expression):
                result = self.workflow_check({**event, expression: "f" * 40})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL: PR event", result.stderr)

    def test_pr_requires_a_test_merge_with_two_parents(self) -> None:
        event = self.healthy_pr()
        head = event["github.event.pull_request.head.sha"]
        run(self.repo, "git", "switch", "--detach", head)
        result = self.workflow_check({**event, "github.sha": head})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL: PR event", result.stderr)
        tree = run(self.repo, "git", "rev-parse", event["github.sha"] + "^{tree}").stdout.strip()
        octopus = run(
            self.repo, "git", "commit-tree", tree, "-p", self.base, "-p", head,
            "-p", event["github.sha"], "-m", "three parents",
        ).stdout.strip()
        run(self.repo, "git", "switch", "--detach", octopus)
        result = self.workflow_check({**event, "github.sha": octopus})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL: PR event", result.stderr)

    def test_push_uses_before_without_pr_context(self) -> None:
        (self.repo / "README.md").write_text("docs\n", encoding="utf-8")
        self.commit()
        event = {"github.event_name": "push", "github.event.before": self.base}
        result = self.workflow_check(event)
        self.assertEqual(result.returncode, 0, result.stderr)
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        self.commit()
        result = self.workflow_check(event)
        self.assertEqual(result.returncode, 1)
        self.assertIn("version did not strictly increase", result.stderr)

    def test_push_rejects_missing_or_zero_before(self) -> None:
        for before in ["", "0" * 40]:
            with self.subTest(before=before):
                result = self.workflow_check(
                    {"github.event_name": "push", "github.event.before": before}
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn("push event has no usable before SHA", result.stderr)


if __name__ == "__main__":
    unittest.main()


class ChangelogCoverageTests(unittest.TestCase):
    """Both directions between a plugin release and its CHANGELOG entry.

    Its own base, carrying a CHANGELOG.md, because the checker treats a missing
    one as "nothing to adjudicate" and returns early -- the suite above relies
    on that to stay about version progression alone.
    """

    ENTRY = "- **transcript-fixer** (`audio` v0.9.0 -> v1.0.0): shipped earlier.\n"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        run(self.repo, "git", "init", "-q")
        run(self.repo, "git", "config", "user.email", "test@example.invalid")
        run(self.repo, "git", "config", "user.name", "Test")
        (self.repo / ".claude-plugin").mkdir()
        (self.repo / "scripts/ci").mkdir(parents=True)
        (self.repo / "daymade-audio/transcript-fixer").mkdir(parents=True)
        (self.repo / "daymade-docs").mkdir()
        shutil.copy2(CHECKER, self.repo / "scripts/ci/check_version_progression.py")
        self.write_manifest(manifest())
        (self.repo / "daymade-audio/transcript-fixer/SKILL.md").write_text(
            "---\nname: transcript-fixer\ndescription: fixture\n---\n", encoding="utf-8"
        )
        (self.repo / "daymade-docs/SKILL.md").write_text(
            "---\nname: docs\ndescription: fixture\n---\n", encoding="utf-8"
        )
        self.write_changelog(self.ENTRY)
        run(self.repo, "git", "add", ".")
        run(self.repo, "git", "commit", "-qm", "base")
        self.base = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()

    def write_manifest(self, value: dict) -> None:
        (self.repo / ".claude-plugin/marketplace.json").write_text(
            json.dumps(value, indent=2) + "\n", encoding="utf-8"
        )

    def write_changelog(self, body: str) -> None:
        (self.repo / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [Unreleased]\n\n" + body, encoding="utf-8"
        )

    def touch_skill(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")

    def commit(self) -> str:
        run(self.repo, "git", "add", "-A")
        run(self.repo, "git", "commit", "-qm", "candidate")
        return run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()

    def check(self, candidate: str) -> subprocess.CompletedProcess[str]:
        return run(
            self.repo, sys.executable, str(CHECKER), "--repo", str(self.repo),
            "--base", self.base, "--candidate", candidate, check=False,
        )

    def release_audio(self, entry: str | None, version: str = "1.1.0") -> subprocess.CompletedProcess[str]:
        """Ship `version` of the audio plugin, optionally writing an entry."""
        self.touch_skill()
        self.write_manifest(manifest(audio=version))
        if entry is not None:
            self.write_changelog(entry + self.ENTRY)
        return self.check(self.commit())

    # --- BACKWARD: a release must be written down -------------------------

    def test_bump_without_any_changelog_edit_fails(self) -> None:
        result = self.release_audio(None)
        self.assertEqual(result.returncode, 1)
        self.assertIn("'audio' bumps v1.0.0 -> v1.1.0 with no CHANGELOG entry", result.stderr)

    def test_bump_with_unrelated_changelog_edit_fails(self) -> None:
        result = self.release_audio("- **docs**: an edit that names no version.\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no CHANGELOG entry", result.stderr)

    def test_entry_naming_another_plugin_does_not_count(self) -> None:
        result = self.release_audio("- **docs** (v2.0.0 -> v1.1.0): wrong plugin.\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("'audio' bumps", result.stderr)

    def test_entry_ending_at_another_version_does_not_count(self) -> None:
        result = self.release_audio("- **audio** (v1.0.0 -> v1.0.5): wrong target.\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no CHANGELOG entry", result.stderr)

    def test_preexisting_line_does_not_count_as_this_releases_entry(self) -> None:
        """The base already carries the line, so this change added nothing."""
        line = "- **audio** (v1.0.0 -> v1.1.0): written before this change.\n"
        self.write_changelog(line + self.ENTRY)
        run(self.repo, "git", "add", "-A")
        run(self.repo, "git", "commit", "-qm", "pre-existing entry")
        self.base = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        result = self.release_audio(line)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no CHANGELOG entry", result.stderr)

    def test_unbumped_plugin_is_never_asked_for_an_entry(self) -> None:
        self.touch_skill()
        self.write_manifest(manifest(audio="1.1.0"))
        self.write_changelog("- **audio** (v1.0.0 -> v1.1.0): shipped.\n" + self.ENTRY)
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 0, result.stderr)

    # Every shape found in live use.  Each is a separate release of the same
    # plugin, so a shape that stops being recognised fails on its own line.

    def test_shape_qualified(self) -> None:
        r = self.release_audio("- **transcript-fixer** (`audio` v1.0.0 -> v1.1.0): x.\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_shape_unquoted(self) -> None:
        r = self.release_audio("- **transcript-fixer** (audio v1.0.0 -> v1.1.0): x.\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_shape_bare(self) -> None:
        r = self.release_audio("- **audio** (v1.0.0 -> v1.1.0): x.\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_shape_unwrapped(self) -> None:
        r = self.release_audio("- **audio** v1.0.0 -> v1.1.0: x.\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_shape_version_only_without_an_arrow(self) -> None:
        r = self.release_audio("- **audio** 1.1.0: the convention before arrows.\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_shape_unicode_arrow(self) -> None:
        r = self.release_audio("- **audio** (v1.0.0 → v1.1.0): x.\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_shape_two_plugins_share_one_parenthetical(self) -> None:
        self.touch_skill()
        (self.repo / "daymade-docs/SKILL.md").write_text("---\nname: docs\nd: x\n---\n", encoding="utf-8")
        self.write_manifest(manifest(audio="1.1.0", docs="2.1.0"))
        self.write_changelog(
            "- **De-identified fixtures** (`audio` v1.0.0 → v1.1.0, "
            "`docs` v2.0.0 → v2.1.0): x.\n" + self.ENTRY
        )
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 0, result.stderr)

    # --- FORWARD: an arrow this change adds must name real endpoints ------

    def test_wrong_from_on_this_releases_own_arrow_fails(self) -> None:
        result = self.release_audio("- **x** (`audio` v0.1.0 -> v1.1.0): bad FROM.\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bumps FROM v0.1.0 but base", result.stderr)

    def test_wrong_from_in_the_bare_shape_also_fails(self) -> None:
        """The majority shape was unreadable to the forward check, so every
        bare entry's FROM went unvalidated."""
        result = self.release_audio("- **audio** (v0.1.0 -> v1.1.0): bad FROM.\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bumps FROM v0.1.0 but base", result.stderr)

    def test_wrong_from_in_the_unwrapped_shape_also_fails(self) -> None:
        result = self.release_audio("- **audio** v0.1.0 -> v1.1.0: bad FROM.\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bumps FROM v0.1.0 but base", result.stderr)

    def test_wrong_from_on_the_first_of_two_shared_plugins_fails(self) -> None:
        """A comma, not a paren, closes the first arrow of a shared entry, so
        reading only up to `)` validated the last plugin and skipped the rest."""
        self.touch_skill()
        (self.repo / "daymade-docs/SKILL.md").write_text("---\nname: docs\nd: x\n---\n", encoding="utf-8")
        self.write_manifest(manifest(audio="1.1.0", docs="2.1.0"))
        self.write_changelog(
            "- **Both** (`audio` v0.1.0 -> v1.1.0, `docs` v2.0.0 -> v2.1.0): x.\n" + self.ENTRY
        )
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 1)
        self.assertIn("'audio' bumps FROM v0.1.0", result.stderr)

    def test_a_skills_own_version_is_not_read_as_a_plugins(self) -> None:
        """`transcript-fixer` is a Skill, not a plugin; the manifest carries no
        version for it, so an arrow bolding it claims nothing this can judge."""
        result = self.release_audio(
            "- **transcript-fixer** (v9.9.9 -> v9.9.10): a Skill's own version.\n"
            "- **audio** (v1.0.0 -> v1.1.0): the plugin release.\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_longer_version_is_not_read_as_the_shipped_one(self) -> None:
        """`1.1.0` occurs inside `11.1.0`; a substring test would accept it."""
        result = self.release_audio("- **audio** (v11.0.0 -> v11.1.0): not ours.\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no CHANGELOG entry", result.stderr)

    def test_a_prose_edit_to_an_older_entry_is_not_judged_as_this_release(self) -> None:
        """One change can both release a plugin and rewrite an older entry for
        it -- a rename, a de-identification pass.  An added-lines diff cannot
        tell the rewritten old line from a new one, so the arrow that does not
        end at what this tree ships is the one to leave alone."""
        result = self.release_audio(
            "- **audio** (v1.0.0 -> v1.1.0): this release.\n"
            "- **audio** (v0.5.0 -> v0.6.0): an old entry, reworded just now.\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_entry_written_after_the_release_already_landed_passes(self) -> None:
        """The live 2026-09-22 failure: the omission the backward check finds
        must stay fixable.  Nothing is bumped here -- the version shipped in an
        earlier change -- so today's base is not this arrow's FROM."""
        self.write_changelog(
            "- **audio** (v0.9.0 -> v1.0.0): written after the fact.\n" + self.ENTRY
        )
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 0, result.stderr)
