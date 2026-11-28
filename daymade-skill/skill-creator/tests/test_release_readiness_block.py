"""Unit tests for release_readiness._parse_review_block error shapes.

The three input shapes must produce three distinguishable outcomes: a valid
block parses, a missing opener names the absence, and a malformed closer
(`--->`, the shape a real 2026-10-06 receipt carried) names the parse failure
count — not the generic "needs exactly one block" that used to cover both.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import release_readiness as rr  # noqa: E402

CANDIDATE = "a" * 40
VALID_JSON = json.dumps(
    {"schema": 1, "candidate": CANDIDATE, "skill_paths": ["suite/skill"], "result": "passed"}
)


class ParseReviewBlockTest(unittest.TestCase):
    def test_valid_block_parses(self):
        text = f"intro\n<!-- skill-release-review\n{VALID_JSON}\n-->\noutro\n"
        self.assertEqual(rr._parse_review_block(text)["candidate"], CANDIDATE)

    def test_missing_opener_names_absence(self):
        with self.assertRaises(rr.ReleaseError) as ctx:
            rr._parse_review_block("no block here\n")
        self.assertIn("no skill-release-review block", str(ctx.exception))

    def test_malformed_closer_names_parse_count(self):
        # Three-dash closer: the opener exists, nothing parses.
        text = f"<!-- skill-release-review\n{VALID_JSON}\n--->\n"
        with self.assertRaises(rr.ReleaseError) as ctx:
            rr._parse_review_block(text)
        msg = str(ctx.exception)
        self.assertIn("0 parseable", msg)
        self.assertIn("`-->`", msg)

    def test_two_blocks_reports_count(self):
        block = f"<!-- skill-release-review\n{VALID_JSON}\n-->\n"
        with self.assertRaises(rr.ReleaseError) as ctx:
            rr._parse_review_block(block + block)
        self.assertIn("2 parseable", str(ctx.exception))


class ReviewTemplateTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.init_repo("source")
        self.base = self.commit_fixture(self.source)
        for skill_path in ("suite/a", "suite/z"):
            path = self.source / skill_path / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text("# Fixture Skill\n", encoding="utf-8")
        self.candidate = self.commit_fixture(self.source, self.base)

    def git(self, repo, *args):
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def init_repo(self, name):
        repo = self.root / name
        repo.mkdir()
        self.git(repo, "init", "--quiet")
        return repo

    def commit_fixture(self, repo, parent=None):
        self.git(repo, "add", ".")
        tree = self.git(repo, "write-tree")
        parents = ["-p", parent] if parent else []
        commit = self.git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture",
                          "commit-tree", tree, *parents, "-m", "Fixture snapshot")
        self.git(repo, "update-ref", "HEAD", commit)
        return commit

    def run_cli(self, command, candidate, *args):
        return subprocess.run(
            [sys.executable, rr.__file__, command, "--repo", str(self.source),
             "--candidate", candidate, "--skill-path", "suite/z", "--skill-path", "suite/a",
             *args], capture_output=True, text=True,
        )

    def test_stdout_contains_parseable_metadata_and_review_sections(self):
        result = self.run_cli("review-template", "HEAD", "--base", "HEAD^", "--skill-path", "suite/z")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("\n<!-- skill-release-review\n{\n", result.stdout)
        self.assertIn("\n}\n-->\n", result.stdout)
        self.assertEqual(rr._parse_review_block(result.stdout), {
            "schema": 1, "candidate": self.candidate,
            "skill_paths": ["suite/a", "suite/z"], "result": "pending",
        })
        self.assertIn(f"- Review base `{self.base}`\n", result.stdout)
        self.assertIn("- Reviewer [Reviewer name or ID]\n", result.stdout)
        for heading in (
            "Verbatim Reviewer Prompt",
            "Independent Reviewer Findings",
            "Verification Limits",
            "Separate Author / Pre-Commit Checks (Not Performed by Reviewer)",
        ):
            self.assertIn(f"\n## {heading}\n", result.stdout)

    def test_output_file_records_dependencies_and_preserves_existing_file(self):
        path = self.root / "review draft.md"
        args = ("--base", self.base, "--reviewer", "Fixture Reviewer",
                "--rebind-dependency", "tools/z.py", "--rebind-dependency", "tools/a.py",
                "--output", str(path))
        result = self.run_cli("review-template", self.candidate, *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        contents = path.read_text(encoding="utf-8")
        self.assertIn("- Reviewer Fixture Reviewer\n", contents)
        self.assertEqual(rr._parse_review_block(contents)["rebind_dependencies"],
                         ["tools/a.py", "tools/z.py"])

        repeated = self.run_cli("review-template", self.candidate, *args, "--reviewer", "Other Reviewer")
        self.assertEqual(repeated.returncode, 2, repeated.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), contents)

    def test_unresolvable_or_missing_base_does_not_create_file(self):
        path = self.root / "draft.md"
        for base_args in ((), ("--base", "missing-revision")):
            with self.subTest(base_args=base_args):
                result = self.run_cli("review-template", self.candidate, "--output", str(path), *base_args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(path.exists())

    def test_attest_rejects_pending_then_accepts_completed_template(self):
        archive = self.init_repo("archive")
        review_path = archive / "review.md"
        template = self.run_cli("review-template", self.candidate, "--base", self.base)
        self.assertEqual(template.returncode, 0, template.stderr)
        review_path.write_text(template.stdout, encoding="utf-8")
        pending = self.commit_fixture(archive)
        review_args = ("--review-repo", str(archive), "--review-path", review_path.name, "--review-commit")

        rejected = self.run_cli("attest", self.candidate, *review_args, pending)
        self.assertEqual(rejected.returncode, 2, rejected.stderr)
        self.assertIn("review metadata is missing or not passed", rejected.stderr)
        receipt = rr.receipt_path(self.source, self.candidate)
        self.assertFalse(receipt.exists())

        filled = template.stdout.replace('"result": "pending"', '"result": "passed"')
        filled = filled.replace("[Paste the exact prompt sent to the reviewer, including any reader specification.]",
                                "Check both fixture Skills in the candidate.")
        filled = filled.replace("[Record the reviewer's findings and evidence. Include the disposition and reason for each finding.]",
                                "Checked both Skill roots. No findings.")
        filled = filled.replace("[Record what the reviewer could not verify and why.]", "Checked the source only.")
        filled = filled.replace("[Record the commands and results from author checks and pre-commit validation.]",
                                "Author ran the fixture tests.")
        review_path.write_text(filled, encoding="utf-8")
        passed = self.commit_fixture(archive, pending)
        accepted = self.run_cli("attest", self.candidate, *review_args, passed)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(json.loads(receipt.read_text())["review_commit"], passed)
        verified = self.run_cli("verify", self.candidate)
        self.assertEqual(verified.returncode, 0, verified.stderr)


if __name__ == "__main__":
    unittest.main()
