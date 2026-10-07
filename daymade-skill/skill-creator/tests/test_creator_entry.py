"""Caller-level checks for the fixed entry; no network or uv installation needed."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "scripts/creator.py"
OWNERS = (
    "audit_skill_regression", "release_readiness", "source_contract", "materialize", "delivery_identity",
)


class CreatorEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.caller = self.workspace / "caller with spaces"
        self.caller.mkdir()
        self.bin_dir = self.workspace / "bin"
        self.bin_dir.mkdir()
        self.trace = self.workspace / "uv-calls.jsonl"
        uv = self.bin_dir / "uv"
        # Execute the real owners under the test interpreter. The shim records
        # invocation boundaries without preparing an environment or using a cache.
        uv.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "with open(os.environ['CREATOR_TEST_TRACE'], 'a') as out:\n"
            "    out.write(json.dumps({'cwd': os.getcwd(), 'args': args}) + '\\n')\n"
            "if os.environ.get('CREATOR_TEST_CHILD_FAILURE'):\n"
            "    print('child stdout')\n"
            "    print('child stderr', file=sys.stderr)\n"
            "    sys.exit(23)\n"
            "if args[:3] != ['run', '--frozen', '--project'] or args[4:6] != ['python', '-m']:\n"
            "    sys.exit('unexpected runtime invocation')\n"
            "if pathlib.Path(args[3]).resolve() != pathlib.Path.cwd().resolve():\n"
            "    sys.exit('wrong owner working directory')\n"
            "os.execv(sys.executable, [sys.executable, '-m', *args[6:]])\n",
            encoding="utf-8",
        )
        uv.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = str(self.bin_dir) + os.pathsep + self.env.get("PATH", "")
        self.env["CREATOR_TEST_TRACE"] = str(self.trace)

    def invoke(self, *args, entry=ENTRY, env=None):
        return subprocess.run(
            [sys.executable, str(entry), *args], cwd=self.caller,
            env=self.env if env is None else env, capture_output=True,
        )

    def direct(self, owner, *args):
        return subprocess.run(
            [sys.executable, "-m", "scripts." + owner, *args],
            cwd=ROOT, env=self.env, capture_output=True,
        )

    def assert_same_result(self, actual, expected):
        self.assertEqual(actual.returncode, expected.returncode)
        self.assertEqual(actual.stdout, expected.stdout)
        self.assertEqual(actual.stderr, expected.stderr)

    def calls(self):
        if not self.trace.exists():
            return []
        return [json.loads(line) for line in self.trace.read_text().splitlines()]

    def test_all_registered_owner_helps_match_direct_invocation_from_other_cwd(self):
        for owner in OWNERS:
            with self.subTest(owner=owner):
                actual = self.invoke(owner, "--help")
                expected = self.direct(owner, "--help")
                self.assertEqual(expected.returncode, 0)
                self.assertIn(b"usage:", expected.stdout)
                self.assert_same_result(actual, expected)
        self.assertEqual(len(self.calls()), len(OWNERS))

    def test_missing_owner_required_inputs_match_real_parser_and_do_not_write(self):
        output = self.workspace / "requested output"
        cases = (
            ("audit_skill_regression", "snapshot", "--output", str(output)),
            ("release_readiness", "attest", "--repo", str(output)),
            ("source_contract", "check-path"),
            ("delivery_identity", "prepare", "--output", str(output)),
            ("materialize", "prepare", "--root", str(output)),
        )
        for owner, *args in cases:
            with self.subTest(owner=owner):
                expected = self.direct(owner, *args)
                self.assertEqual(expected.returncode, 2)
                self.assert_same_result(self.invoke(owner, *args), expected)
                self.assertFalse(output.exists())

    def test_missing_unknown_and_blank_inputs_never_start_runtime(self):
        output = self.workspace / "must not be created"
        cases = [(), ("unknown", "--output", str(output)), ("--help", "extra")]
        cases.extend((owner,) for owner in OWNERS)
        for blank in ("", " ", "\t\n"):
            cases.extend((
                ("audit_skill_regression", "snapshot", "--source", blank,
                 "--output", str(output)),
                ("audit_skill_regression", "snapshot", "--source=" + blank,
                 "--output", str(output)),
                ("source_contract", "check-path", blank),
                ("release_readiness", "attest", "--repo=" + blank),
                ("materialize", "prepare", "--root", blank),
            ))
        for args in cases:
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"creator:", result.stderr)
                self.assertFalse(output.exists())
        self.assertEqual(self.calls(), [])

    def test_real_snapshot_preserves_paths_with_spaces(self):
        source = self.workspace / "source with spaces"
        source.mkdir()
        text = "---\nname: sample\ndescription: sample\n---\n\n# Sample\n"
        (source / "SKILL.md").write_text(text, encoding="utf-8")
        output = self.workspace / "snapshot with spaces"
        result = self.invoke(
            "audit_skill_regression", "snapshot", "--source", str(source),
            "--output", str(output),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((output / "SKILL.md").read_text(), text)
        manifest = json.loads((output / ".skill-regression-baseline.json").read_text())
        self.assertEqual(
            manifest["source_path_hash"],
            hashlib.sha256(str(source).encode("utf-8")).hexdigest(),
        )
        self.assertEqual(self.calls()[0]["args"][-1], str(output))

    def test_symlink_resolves_owner_instead_of_using_link_directory(self):
        link = self.caller / "creator-link.py"
        link.symlink_to(ENTRY)
        self.assert_same_result(
            self.invoke("source_contract", "--help", entry=link),
            self.direct("source_contract", "--help"),
        )
        self.assertEqual(Path(self.calls()[0]["cwd"]), ROOT)

    def test_relative_paths_keep_owner_cwd_semantics(self):
        owner = self.workspace / "isolated owner"
        (owner / "scripts").mkdir(parents=True)
        for name in ("creator.py", "audit_skill_regression.py", "packaging_policy.py"):
            shutil.copyfile(ROOT / "scripts" / name, owner / "scripts" / name)
        for directory, name in ((owner, "owner-source"), (self.caller, "caller-source")):
            source = directory / "sample"
            source.mkdir()
            (source / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: sample\n---\n", encoding="utf-8",
            )
        result = self.invoke(
            "audit_skill_regression", "snapshot", "--source", "sample",
            "--output", "snapshot", entry=owner / "scripts/creator.py",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("owner-source", (owner / "snapshot/SKILL.md").read_text())
        self.assertFalse((self.caller / "snapshot").exists())

    def test_child_exit_23_and_both_streams_are_retained_without_retry(self):
        env = dict(self.env, CREATOR_TEST_CHILD_FAILURE="1")
        result = self.invoke("materialize", "--help", env=env)
        self.assertEqual(result.returncode, 23)
        self.assertEqual(result.stdout, b"child stdout\n")
        self.assertEqual(result.stderr, b"child stderr\n")
        self.assertEqual(len(self.calls()), 1)

    def test_missing_uv_fails_explicitly_without_fallback(self):
        empty_bin = self.workspace / "empty-bin"
        empty_bin.mkdir()
        env = dict(self.env, PATH=str(empty_bin))
        result = self.invoke("materialize", "--help", env=env)
        self.assertEqual(result.returncode, 127)
        self.assertIn(b"cannot start uv", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_owner_module_fails_before_runtime(self):
        owner = self.workspace / "incomplete owner"
        (owner / "scripts").mkdir(parents=True)
        copied = owner / "scripts/creator.py"
        shutil.copyfile(ENTRY, copied)
        result = self.invoke("materialize", "--help", entry=copied)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"owner module is missing", result.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
