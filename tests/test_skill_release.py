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
from test_git_mainline_guard import MainlineGuardTests, run


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
        run(self.review, "git", "init", "-q")
        run(self.review, "git", "config", "user.email", "test@example.invalid")
        run(self.review, "git", "config", "user.name", "Test")
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
        env = dict(self.env, GIT_PII_GUARD_DIR=str(self.root / "absent"))
        blocked = run(self.repo, "bash", ".githooks/pre-push", "origin", str(self.remote), input_text=stdin, env=env, check=False)
        self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
        self.assertIn("skill release blocked", blocked.stderr)
        with self.assertRaises(rr.ReleaseError):
            rr.attest(self.repo, self.head, paths, self.review, run(self.repo, "git", "rev-parse", "HEAD").stdout.strip(), self.path)
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


# Inheritance supplies fixture setup only; avoid rerunning parent cases with a new baseline.
for _name in list(vars(MainlineGuardTests)):
    if _name.startswith("test_") and _name not in vars(ReleaseTests):
        setattr(ReleaseTests, _name, None)

if __name__ == "__main__":
    unittest.main()
