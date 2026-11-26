"""Calibration through real Git objects and the actual pre-push dispatcher."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "daymade-skill/skill-creator/scripts"))
sys.path.insert(0, str(ROOT / "scripts/ci"))
import release_readiness as rr
from skill_read_plan import plan
from check_skill_release import affected
from test_git_mainline_guard import MainlineGuardTests, init_repo, run


class ReadPlanTests(unittest.TestCase):
    def test_actual_skill_reassembles_with_native_sed(self):
        source = ROOT / "daymade-skill/skill-creator/SKILL.md"
        data = plan(source, 12000)
        actual = b"".join(subprocess.check_output(["/usr/bin/sed", "-n", f"{c['start_line']},{c['end_line']}p", str(source)]) for c in data["chunks"])
        self.assertEqual(actual, source.read_bytes())
        self.assertTrue(all(c["bytes"] <= 12000 for c in data["chunks"]))

    def test_utf8_and_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "input"
            p.write_text("中文\nmore\n")
            self.assertEqual(len(plan(p, 7)["chunks"]), 2)
            for value in (None, "", 0, -1):
                with self.assertRaises(ValueError):
                    plan(p, value)
            with self.assertRaises(ValueError):
                plan(p, 2)
            p.write_bytes(b"")
            with self.assertRaises(ValueError):
                plan(p, 7)
            p.write_bytes(b"\xff")
            with self.assertRaises(ValueError):
                plan(p, 7)


class ReleaseTests(MainlineGuardTests):
    def setUp(self):
        super().setUp()
        self.review = self.root / "private"
        self.review.mkdir()
        init_repo(self.review)
        run(self.review, "git", "config", "user.email", "test@example.invalid")
        run(self.review, "git", "config", "user.name", "Test")
        run(self.review, "git", "config", "core.hooksPath", "/dev/null")
        run(self.review, "git", "commit", "--allow-empty", "-qm", "private archive baseline")
        self.base = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        self.skill = "daymade-audio/transcript-fixer"
        p = self.repo / self.skill / "SKILL.md"
        p.write_text(p.read_text() + "\nNew runtime behavior.\n")
        manifest = self.repo / ".claude-plugin/marketplace.json"
        data = json.loads(manifest.read_text())
        data["plugins"][0]["version"] = "1.1.0"
        manifest.write_text(json.dumps(data))
        (self.repo / "CHANGELOG.md").write_text("# Changelog\n\n- audio v1.0.0 → v1.1.0: runtime change.\n")
        run(self.repo, "git", "switch", "-qc", "feature")
        run(self.repo, "git", "add", "--", self.skill, ".claude-plugin/marketplace.json", "CHANGELOG.md")
        run(self.repo, "git", "commit", "-qm", "runtime change")
        self.head = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        self.path = "reviews/[current]/independent-review.md"
        file = self.review / self.path
        file.parent.mkdir(parents=True)
        file.write_text("# Independent review\n\n<!-- skill-release-review\n" + json.dumps(dict(schema=1, candidate=self.head, skill_paths=[self.skill], result="passed")) + "\n-->\n")

    # Do not inherit the parent cases under the modified fixture.
    def test_archive_and_actual_dispatcher(self):
        paths = affected(self.repo, self.base, self.head)
        self.assertEqual(paths, [self.skill])
        stdin = f"refs/heads/feature {self.head} refs/heads/feature {'0'*40}\n"
        env = self.env.copy()
        blocked = run(self.repo, "bash", ".githooks/pre-push", "origin", str(self.remote), input_text=stdin, env=env, check=False)
        self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
        self.assertIn("skill release blocked", blocked.stderr)
        with self.assertRaises(rr.ReleaseError):
            rr.attest(self.repo, self.head, paths, self.review, run(self.review, "git", "rev-parse", "HEAD").stdout.strip(), self.path)
        run(self.review, "git", "add", "--", self.path)
        run(self.review, "git", "commit", "-qm", "review exact candidate")
        commit = run(self.review, "git", "rev-parse", "HEAD").stdout.strip()
        rr.attest(self.repo, self.head, paths, self.review, commit, self.path)
        self.assertEqual(rr.verify(self.repo, self.head, paths)["review_commit"], commit)
        passed = run(self.repo, "bash", ".githooks/pre-push", "origin", str(self.remote), input_text=stdin, env=env, check=False)
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        file = self.review / self.path
        file.write_text(file.read_text() + "dirty\n")
        with self.assertRaises(rr.ReleaseError):
            rr.verify(self.repo, self.head, paths)
        blocked = run(self.repo, "bash", ".githooks/pre-push", "origin", str(self.remote), input_text=stdin, env=env, check=False)
        self.assertNotEqual(blocked.returncode, 0)

    def test_exact_commit_and_exemption(self):
        rr.attest(self.repo, self.head, [self.skill], review_not_required="typo-only", reason="fixture spelling-only classification")
        rr.verify(self.repo, self.head, [self.skill])
        with self.assertRaises(rr.ReleaseError):
            rr.verify(self.repo, self.head, ["other"])
        for value in (None, "", "main", self.head[:8]):
            with self.assertRaises(rr.ReleaseError):
                rr.attest(self.repo, value, [self.skill], review_not_required="format-only", reason="fixture")
        for reason in (None, "", " "):
            with self.assertRaises(rr.ReleaseError):
                rr.attest(self.repo, self.head, [self.skill], review_not_required="format-only", reason=reason)
        run(self.repo, "git", "commit", "--allow-empty", "-qm", "new head")
        with self.assertRaises(OSError):
            rr.verify(self.repo, run(self.repo, "git", "rev-parse", "HEAD").stdout.strip(), [self.skill])

    def test_lightweight_annotated_and_published_tags(self):
        env = self.env.copy()
        run(self.repo, "git", "tag", "-a", "review-probe", "-m", "fixture", self.head)
        annotated = run(self.repo, "git", "rev-parse", "refs/tags/review-probe").stdout.strip()
        for sha in (self.head, annotated):
            stdin = f"refs/tags/review-probe {sha} refs/tags/review-probe {'0'*40}\n"
            blocked = run(self.repo, "bash", ".githooks/pre-push", "origin", str(self.remote), input_text=stdin, env=env, check=False)
            self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
            self.assertIn("skill release blocked", blocked.stderr)
        stdin = f"refs/tags/old {self.base} refs/tags/old {'0'*40}\n"
        passed = run(self.repo, "bash", ".githooks/pre-push", "origin", str(self.remote), input_text=stdin, env=env, check=False)
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        run(self.review, "git", "add", "--", self.path)
        run(self.review, "git", "commit", "-qm", "review tags")
        rr.attest(self.repo, self.head, [self.skill], self.review, run(self.review, "git", "rev-parse", "HEAD").stdout.strip(), self.path)
        for sha in (self.head, annotated):
            stdin = f"refs/tags/review-probe {sha} refs/tags/review-probe {'0'*40}\n"
            passed = run(self.repo, "bash", ".githooks/pre-push", "origin", str(self.remote), input_text=stdin, env=env, check=False)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)

    def test_committed_metadata_rejects_missing_empty_stale_and_failed(self):
        original = (self.review / self.path).read_text()
        metadata = dict(schema=1, candidate=self.head, skill_paths=[self.skill], result="passed")
        variants = [{k:v for k,v in metadata.items() if k != key} for key in ("candidate", "skill_paths", "result")]
        variants += [dict(metadata, candidate=""), dict(metadata, skill_paths=[]), dict(metadata, result=""),
                     dict(metadata, candidate=self.base), dict(metadata, result="failed")]
        for variant in variants:
            with self.subTest(variant=variant):
                file = self.review / self.path
                file.write_text("<!-- skill-release-review\n" + json.dumps(variant) + "\n-->\n")
                run(self.review, "git", "add", "--", self.path)
                run(self.review, "git", "commit", "-qm", "metadata variant")
                commit = run(self.review, "git", "rev-parse", "HEAD").stdout.strip()
                with self.assertRaises(rr.ReleaseError):
                    rr.attest(self.repo, self.head, [self.skill], self.review, commit, self.path)
        (self.review / self.path).write_text(original)
        run(self.review, "git", "add", "--", self.path)
        run(self.review, "git", "commit", "-qm", "valid metadata")
        commit = run(self.review, "git", "rev-parse", "HEAD").stdout.strip()
        rr.attest(self.repo, self.head, [self.skill], self.review, commit, self.path)
        file = self.review / self.path
        file.write_text(file.read_text() + "changed review\n")
        run(self.review, "git", "add", "--", self.path)
        run(self.review, "git", "commit", "-qm", "replaced artifact")
        with self.assertRaises(rr.ReleaseError):
            rr.verify(self.repo, self.head, [self.skill])

    def test_tests_only_do_not_trigger(self):
        file = self.repo / self.skill / "tests/input.md"
        file.parent.mkdir()
        file.write_text("test fixture\n")
        run(self.repo, "git", "add", "--", self.skill + "/tests")
        run(self.repo, "git", "commit", "-qm", "tests only")
        head = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(affected(self.repo, self.head, head), [])

    def test_unpublished_tag_also_requires_version_progression(self):
        manifest = self.repo / ".claude-plugin/marketplace.json"
        data = json.loads(manifest.read_text())
        data["plugins"][0]["version"] = "1.0.0"
        manifest.write_text(json.dumps(data))
        run(self.repo, "git", "add", "--", ".claude-plugin/marketplace.json")
        run(self.repo, "git", "commit", "-qm", "unbumped tag fixture")
        head = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        rr.attest(self.repo, head, [self.skill], review_not_required="format-only", reason="fixture")
        stdin = f"refs/heads/feature {head} refs/tags/new {'0'*40}\n"
        result = self.guard("pre-push", stdin, "origin", str(self.remote))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("version did not strictly increase", result.stderr)

    def test_branch_destination_rejects_tag_object_even_with_reviewed_commit(self):
        rr.attest(self.repo, self.head, [self.skill], review_not_required="format-only", reason="fixture")
        run(self.repo, "git", "tag", "-a", "annotated-source", "-m", "fixture", self.head)
        tag = run(self.repo, "git", "rev-parse", "annotated-source").stdout.strip()
        stdin = f"refs/tags/annotated-source {tag} refs/heads/feature {'0'*40}\n"
        result = self.guard("pre-push", stdin, "origin", str(self.remote))
        self.assertEqual(result.returncode, 2)
        self.assertIn("exact commit object", result.stderr)

    def test_projected_branch_keeps_exact_review_after_unrelated_advance(self):
        rr.attest(self.repo, self.head, [self.skill], review_not_required="format-only", reason="fixture exact source")
        run(self.repo, "git", "switch", "-qc", "advanced-main", self.base)
        (self.repo / "unrelated.txt").write_text("advance\n")
        run(self.repo, "git", "add", "unrelated.txt")
        run(self.repo, "git", "commit", "-qm", "advance")
        run(self.repo, "git", "push", "origin", "HEAD:main")
        run(self.repo, "git", "switch", "feature")
        branch = f"refs/tags/local-name {self.head} refs/heads/feature {'0'*40}\n"
        result = self.guard("pre-push", branch, "origin", str(self.remote))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tag = f"refs/heads/feature {self.head} refs/tags/new {'0'*40}\n"
        for updates in (branch + tag, tag + branch):
            result = self.guard("pre-push", updates, "origin", str(self.remote))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("integration drift", result.stderr)

    def test_mixed_branch_and_tag_execute_both_modes_with_one_frozen_base(self):
        rr.attest(self.repo, self.head, [self.skill], review_not_required="format-only", reason="fixture")
        log = self.root / "calls.jsonl"
        for name in ("check_version_progression", "check_skill_release"):
            file = self.repo / "scripts/ci" / (name + ".py")
            actual = file.with_name(name + "_actual.py")
            file.rename(actual)
            move_tracking_ref = (
                f"import subprocess; subprocess.run(['git','update-ref','refs/remotes/origin/main',{self.head!r}],check=True)\n"
                if name == "check_version_progression" else ""
            )
            file.write_text(
                "import json,runpy,sys\n"
                f"with open({str(log)!r},'a') as out: out.write(json.dumps([sys.argv[0],sys.argv[1:]])+'\\n')\n"
                + move_tracking_ref +
                f"runpy.run_path({str(actual)!r},run_name='__main__')\n"
            )
        branch = f"refs/tags/local-name {self.head} refs/heads/feature {'0'*40}\n"
        tag = f"refs/heads/feature {self.head} refs/tags/new {'0'*40}\n"
        for updates in (branch + tag, tag + branch):
            log.write_text("")
            run(self.repo, "git", "update-ref", "refs/remotes/origin/main", self.base)
            result = self.guard("pre-push", updates, "origin", str(self.remote))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(len(calls), 4)
            for checker in ("check_version_progression.py", "check_skill_release.py"):
                args = [a for file, a in calls if file.endswith(checker)]
                self.assertEqual(sorted("--projected-merge" in a for a in args), [False, True])
                self.assertEqual({a[a.index("--base") + 1] for a in args}, {self.base})

    def test_projected_scope_subset_still_verifies_entire_original_receipt(self):
        docs = "daymade-docs"
        (self.repo / docs).mkdir()
        (self.repo / docs / "SKILL.md").write_text("---\nname: docs\ndescription: fixture\n---\n")
        manifest = self.repo / ".claude-plugin/marketplace.json"
        data = json.loads(manifest.read_text())
        data["metadata"]["version"] = "1.1.0"
        data["plugins"].append(dict(name="docs", source="./daymade-docs", description="docs", version="1.0.0"))
        manifest.write_text(json.dumps(data, indent=2))
        run(self.repo, "git", "add", ".claude-plugin/marketplace.json", docs)
        run(self.repo, "git", "commit", "-qm", "two source roots")
        source = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        file = self.review / self.path
        file.write_text("<!-- skill-release-review\n" + json.dumps(dict(schema=1, candidate=source, skill_paths=[self.skill, docs], result="passed")) + "\n-->\n")
        run(self.review, "git", "add", "--", self.path)
        run(self.review, "git", "commit", "-qm", "full review")
        rr.attest(self.repo, source, [self.skill, docs], self.review, run(self.review, "git", "rev-parse", "HEAD").stdout.strip(), self.path)
        run(self.repo, "git", "switch", "-qc", "advanced", self.base)
        run(self.repo, "git", "restore", "--source", source, "--", docs)
        data["plugins"][0]["version"] = "1.0.0"
        manifest.write_text(json.dumps(data, indent=2))
        run(self.repo, "git", "add", ".claude-plugin/marketplace.json", docs)
        run(self.repo, "git", "commit", "-qm", "docs already published")
        base = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        def check():
            return run(self.repo, sys.executable, "scripts/ci/check_skill_release.py", "--repo", str(self.repo), "--base", base, "--candidate", source, "--projected-merge", check=False)
        result = check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.skill, result.stdout)
        self.assertNotIn("daymade-docs", result.stdout)
        file.write_text(file.read_text() + "dirty\n")
        self.assertEqual(check().returncode, 2)
        run(self.review, "git", "add", "--", self.path)
        run(self.review, "git", "commit", "-qm", "changed evidence")
        self.assertEqual(check().returncode, 2)
        receipt = rr.receipt_path(self.repo, source)
        record = json.loads(receipt.read_text())
        record["skill_paths"] = [self.skill]
        receipt.write_text(json.dumps(record))
        self.assertEqual(check().returncode, 2)
        rr.attest(self.repo, source, [docs], review_not_required="format-only", reason="insufficient scope fixture")
        result = check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not cover all projected", result.stderr)
        for invalid in [None, [], {}, {"skill_paths": None}, {"skill_paths": []}]:
            with self.subTest(invalid=invalid):
                receipt.write_text(json.dumps(invalid))
                result = check()
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)

    def test_stale_main_is_diagnosed_before_review_scope_and_new_head_rebinds(self):
        rr.attest(self.repo, self.head, [self.skill], review_not_required="format-only", reason="fixture exact-head binding")
        run(self.repo, "git", "switch", "-qc", "advanced-main", self.base)
        (self.repo / "unrelated.txt").write_text("another publisher advanced main\n")
        run(self.repo, "git", "add", "--", "unrelated.txt")
        run(self.repo, "git", "commit", "-qm", "main advance")
        fresh_base = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()

        def check(candidate):
            return run(self.repo, sys.executable, "scripts/ci/check_skill_release.py",
                       "--repo", str(self.repo), "--base", fresh_base, "--candidate", candidate, check=False)

        stale = check(self.head)
        self.assertEqual(stale.returncode, 2)
        self.assertIn("integration drift", stale.stderr)
        self.assertNotIn("receipt does not cover", stale.stderr)
        run(self.repo, "git", "switch", "feature")
        run(self.repo, "git", "merge", "--no-edit", fresh_base)
        integrated = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(affected(self.repo, fresh_base, integrated), [self.skill])
        self.assertEqual(check(integrated).returncode, 2)  # old receipt never covers a new SHA
        rr.attest(self.repo, integrated, [self.skill], review_not_required="format-only", reason="fixture unchanged content, new exact head")
        self.assertEqual(check(integrated).returncode, 0)


# Inheritance supplies fixture setup only; avoid rerunning parent cases with a new baseline.
for _name in list(vars(MainlineGuardTests)):
    if _name.startswith("test_") and _name not in vars(ReleaseTests):
        setattr(ReleaseTests, _name, None)

if __name__ == "__main__":
    unittest.main()
