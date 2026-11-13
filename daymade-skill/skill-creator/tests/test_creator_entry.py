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
    "audit_skill_regression", "release_readiness", "source_contract", "materialize", "materialize_agent",
    "delivery_identity",
    "quick_validate", "skill_read_plan", "capture_command", "code_scan",
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
        module = "materialize" if owner == "materialize_agent" else owner
        return subprocess.run(
            [sys.executable, "-m", "scripts." + module, *args],
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
            ("materialize_agent", "prepare", "--root", str(output)),
            ("quick_validate", "--audience", "public"),
            ("skill_read_plan", "--max-chunk-bytes", "100"),
            ("capture_command", "--cwd", str(self.caller)),
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
        cases.extend((name, "--help") for name in (
            "scripts.quick_validate", "quick_validate.py", "python",
        ))
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
                ("materialize_agent", "prepare", "--root", blank),
                ("materialize_agent", blank),
                ("quick_validate", blank),
                ("skill_read_plan", blank, "--max-chunk-bytes", "100"),
            ))
        for args in cases:
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"creator:", result.stderr)
                self.assertFalse(output.exists())
        self.assertEqual(self.calls(), [])

    def test_quick_validate_matches_direct_valid_invalid_and_parser_results(self):
        source = self.workspace / "skill with spaces"
        source.mkdir()
        (source / "SKILL.md").write_text(
            "---\nname: entry-example\ndescription: Validate an example skill.\n---\n"
            "\n# Entry example\n\nValidate an example.\n",
            encoding="utf-8",
        )
        cases = (
            ((str(source), "--audience", "public"), 0),
            ((str(source), "--audience=public", "--format", "json"), 0),
            ((str(source / "missing"), "--audience", "public", "--format", "json"), 1),
            ((str(source), "--audience"), 2),
            ((str(source), "--audience", "unknown"), 2),
            ((str(source), "--unknown"), 2),
        )
        for args, code in cases:
            with self.subTest(args=args):
                direct = self.direct("quick_validate", *args)
                self.assertEqual(direct.returncode, code, direct.stderr)
                actual = self.invoke("quick_validate", *args)
                self.assert_same_result(actual, direct)
                if "--format" in args:
                    self.assertEqual(json.loads(actual.stdout)["valid"], code == 0)
        self.assertEqual(len(self.calls()), len(cases))

    def test_read_plan_matches_direct_from_other_cwd(self):
        source = self.workspace / "source with spaces.txt"
        source.write_text("first line\nsecond line\nthird line\n", encoding="utf-8")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        cases = (
            (str(source), "--max-chunk-bytes", "20"),
            (str(source), "--lines", "1:2", "--expect-sha256", digest),
            (str(source), "--lines", "1:2"),
            (str(source), "--unknown"),
        )
        for index, args in enumerate(cases):
            with self.subTest(args=args):
                direct = self.direct("skill_read_plan", *args)
                self.assertEqual(direct.returncode, 0 if index < 2 else 2, direct.stderr)
                actual = self.invoke("skill_read_plan", *args)
                self.assert_same_result(actual, direct)
                if index == 1:
                    report = json.loads(actual.stdout)
                    self.assertEqual(report["content"], "first line\nsecond line\n")
                    self.assertEqual(report["sha256"], digest)
                    self.assertTrue(report["requested_range_complete"])
        self.assertEqual(len(self.calls()), len(cases))

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

    def test_materialize_agent_uses_summary_while_default_keeps_full_receipt(self):
        repo = self.workspace / "tiny source"
        repo.mkdir()
        home = self.workspace / "fixture-home"
        home.mkdir()
        git_env = dict(self.env, HOME=str(home), GIT_CONFIG_NOSYSTEM="1",
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_GUARD_OSASCRIPT="/usr/bin/false",
                       GIT_GUARD_TTY=os.devnull)
        (repo / "input.txt").write_text("fixture\n")
        for args in (("init", "-q"), ("add", "input.txt"),
                     ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                      "commit", "-qm", "fixture")):
            subprocess.run(["git", "-C", str(repo), *args], env=git_env, check=True,
                           capture_output=True)
        ref = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], env=git_env, text=True,
        ).strip()
        manifest = self.workspace / "materialization.json"
        manifest.write_text(json.dumps({
            "source_repo": str(repo), "source_ref": ref, "paths": ["input.txt"],
            "arms": ["with"], "max_total_bytes": 1024 * 1024,
            "minimum_free_bytes": 1, "owner": "entry-fixture",
        }))
        for command in ("materialize", "materialize_agent"):
            with self.subTest(command=command):
                root = self.workspace / command
                result = self.invoke(command, "prepare", "--manifest", str(manifest),
                                     "--root", str(root))
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)
                receipt_path = root / ".materialization.json"
                full = json.loads(receipt_path.read_text())
                self.assertEqual(output["state"], "prepared")
                self.assertEqual(len(full["inputs"]), 1)
                if command == "materialize":
                    self.assertEqual(output["inputs"], full["inputs"])
                    self.assertNotIn("--summary", self.calls()[-1]["args"])
                else:
                    self.assertNotIn("inputs", output)
                    self.assertEqual(Path(output["receipt_path"]), receipt_path)
                    result = self.invoke(
                        command, "run", "--root", str(root), "--owner", "entry-fixture",
                        "--arm", "with", "--", sys.executable, "-c",
                        "import sys;print('child stdout');print('child stderr', file=sys.stderr);sys.exit(7)",
                        "--summary",
                    )
                    self.assertEqual(result.returncode, 23, result.stderr)
                    self.assertEqual(json.loads(result.stdout)["last_run"]["returncode"], 7)
                    self.assertEqual((root / "artifacts/run-0001/stdout.log").read_text(), "child stdout\n")
                    self.assertEqual((root / "artifacts/run-0001/stderr.log").read_text(), "child stderr\n")
                    self.assertEqual(json.loads(receipt_path.read_text())["runs"][-1]["returncode"], 7)
                finished = self.invoke(command, "finish", "--root", str(root), "--owner", "entry-fixture")
                self.assertEqual(finished.returncode, 0, finished.stderr)

    def test_materialize_agent_injects_summary_for_each_supported_operation(self):
        operations = ("prepare", "run", "finish", "recover", "register-output", "retire")
        for operation in operations:
            with self.subTest(operation=operation):
                self.assert_same_result(
                    self.invoke("materialize_agent", operation, "--help"),
                    self.direct("materialize", operation, "--summary", "--help"),
                )
                self.assertEqual(self.calls()[-1]["args"][6:],
                                 ["scripts.materialize", operation, "--summary", "--help"])
                self.assert_same_result(
                    self.invoke("materialize", operation, "--help"),
                    self.direct("materialize", operation, "--help"),
                )
                self.assertEqual(self.calls()[-1]["args"][6:],
                                 ["scripts.materialize", operation, "--help"])
                self.assert_same_result(
                    self.invoke("materialize_agent", operation, "--summary", "--help"),
                    self.direct("materialize", operation, "--summary", "--help"),
                )
                self.assertEqual(self.calls()[-1]["args"][6:],
                                 ["scripts.materialize", operation, "--summary", "--help"])
        self.assertEqual(len(self.calls()), 3 * len(operations))

    def test_materialize_agent_preserves_child_separator_and_existing_summary(self):
        missing = str(self.workspace / "missing root")
        options = ["--root", missing, "--owner", "fixture", "--arm", "with"]
        child = [sys.executable, "-c", "pass", "--summary"]
        for summary in ([], ["--summary"]):
            with self.subTest(summary=summary):
                args = ["run", *options, *summary, "--", *child]
                result = self.invoke("materialize_agent", *args)
                expected = (["run", *options, *summary] if summary
                            else ["run", "--summary", *options])
                expected += ["--", *child]
                self.assert_same_result(result, self.direct("materialize", *expected))
                forwarded = self.calls()[-1]["args"][7:]
                self.assertEqual(forwarded, expected)
                separator = forwarded.index("--")
                self.assertEqual(forwarded[:separator].count("--summary"), 1)
                self.assertEqual(forwarded[separator + 1:], child)
        self.assertEqual(len(self.calls()), 2)

    def test_materialize_agent_keeps_operation_and_parser_errors(self):
        cases = (("not-an-operation",), ("--summary",),
                 ("prepare",), ("run", "--unknown"))
        for args in cases:
            with self.subTest(args=args):
                expected = self.direct("materialize", *args)
                self.assertEqual(expected.returncode, 2)
                self.assert_same_result(self.invoke("materialize_agent", *args), expected)
                forwarded = self.calls()[-1]["args"][7:]
                if args[0] in ("prepare", "run"):
                    self.assertEqual(forwarded, [args[0], "--summary", *args[1:]])
                else:
                    self.assertEqual(forwarded, list(args))
        self.assertEqual(len(self.calls()), len(cases))

    def test_symlink_resolves_owner_instead_of_using_link_directory(self):
        link = self.caller / "creator-link.py"
        link.symlink_to(ENTRY)
        for owner in OWNERS:
            with self.subTest(owner=owner):
                self.assert_same_result(
                    self.invoke(owner, "--help", entry=link),
                    self.direct(owner, "--help"),
                )
        self.assertEqual(len(self.calls()), len(OWNERS))
        self.assertTrue(all(Path(call["cwd"]) == ROOT for call in self.calls()))

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
        for owner in OWNERS:
            with self.subTest(owner=owner):
                args = ("run", "--help") if owner == "materialize_agent" else ("--help",)
                result = self.invoke(owner, *args, env=env)
                self.assertEqual(result.returncode, 23)
                self.assertEqual(result.stdout, b"child stdout\n")
                self.assertEqual(result.stderr, b"child stderr\n")
        self.assertEqual(len(self.calls()), len(OWNERS))

    def test_missing_uv_fails_explicitly_without_fallback(self):
        empty_bin = self.workspace / "empty-bin"
        empty_bin.mkdir()
        env = dict(self.env, PATH=str(empty_bin))
        for owner in OWNERS:
            with self.subTest(owner=owner):
                args = ("run", "--help") if owner == "materialize_agent" else ("--help",)
                result = self.invoke(owner, *args, env=env)
                self.assertEqual(result.returncode, 127)
                self.assertIn(b"cannot start uv", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_owner_module_fails_before_runtime(self):
        owner = self.workspace / "incomplete owner"
        (owner / "scripts").mkdir(parents=True)
        copied = owner / "scripts/creator.py"
        shutil.copyfile(ENTRY, copied)
        for name in OWNERS:
            with self.subTest(owner=name):
                result = self.invoke(name, "--help", entry=copied)
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"owner module is missing", result.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
