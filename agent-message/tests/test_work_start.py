"""Work entry must catch the same resource before two independent tasks edit it."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("work_entry_peer", ROOT / "scripts/peer.py")
peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(peer)
A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"


class WorkStartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="peer work entry ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "shared state"
        self.one, self.two = self.root / "clone one", self.root / "clone two"
        for directory, remote in ((self.one, "https://code.example.test/team/sample.git"),
                                  (self.two, "git@code.example.test:team/sample.git")):
            directory.mkdir()
            subprocess.run(["git", "-C", str(directory), "init", "--quiet"], check=True)
            subprocess.run(["git", "-C", str(directory), "remote", "add", "origin", remote], check=True)

    def env(self, actor=A):
        return {**{key: value for key, value in os.environ.items()
                   if key not in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_SESSION_NAME")},
                "CODEX_THREAD_ID": actor, "CODEX_SESSION_ID": actor}

    def call(self, repo=None, actor=A, task="case-a", path="src/interpret.py", entry=None, extra=()):
        tail = ["--repo", str(repo or self.one), "--path", path, "--task", task,
                "--actor", "codex:" + actor, *extra]
        if entry:
            command = [sys.executable, str(entry), "--peer-skill", str(ROOT),
                       "--state-dir", str(self.state), "--", *tail]
        else:
            command = [sys.executable, str(ROOT / "scripts/peer.py"), "--state-dir", str(self.state),
                       "coord", "start", *tail]
        result = subprocess.run(command, capture_output=True, text=True, env=self.env(actor))
        return result.returncode, json.loads(result.stdout) if result.stdout else None, result.stderr

    def board(self):
        return peer.coordination.Board(self.state)

    def test_cross_clone_takeover_entry_contacts_existing_owner_before_edit(self):
        self.assertEqual(self.call()[1]["status"], "registered")
        entry = ROOT.parent / "daymade-claude-code/continue-codex-work/scripts/start_work.py"
        if not entry.is_file():
            self.skipTest("separately shipped continuation Skill not present")
        code, result, _ = self.call(self.two, B, "fork-b", entry=entry)
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["active_total"], 1)
        self.assertEqual(result["active"][0]["owner"], "codex:" + A)
        self.assertFalse(result["registered"])
        with contextlib.closing(self.board()) as board:
            self.assertEqual(len(board.status()["owners"]), 1)

    def test_independent_resource_is_not_blocked_and_empty_is_unknown(self):
        first = self.call()[1]
        self.assertEqual(first["active_total"], 0)
        self.assertEqual(first["occupancy"], "unknown")
        self.assertIn("empty does not mean unoccupied", first["coverage"])
        code, result, _ = self.call(self.two, B, "independent", "src/other.py")
        self.assertEqual((code, result["status"], result["active_total"]), (0, "registered", 0))
        with contextlib.closing(self.board()) as board:
            self.assertEqual(len(board.status()["owners"]), 2)

    @unittest.skipUnless(os.environ.get("PEER_OUTCOME_ENTRY"), "private dispatch owner supplied only for cross-owner acceptance")
    def test_dispatch_entry_consumes_the_same_transaction_as_takeover(self):
        entry = Path(os.environ["PEER_OUTCOME_ENTRY"])
        alias = self.root / "loaded peer alias"
        alias.symlink_to(ROOT, target_is_directory=True)
        command = [sys.executable, str(entry), "start", "--peer-skill", str(alias),
                   "--state-dir", str(self.state), "--", "--repo", str(self.one),
                   "--path", "src/interpret.py", "--task", "original", "--actor", "codex:" + A]
        first = subprocess.run(command, capture_output=True, text=True, env=self.env(A))
        self.assertEqual((first.returncode, json.loads(first.stdout)["status"]), (0, "registered"))
        takeover = ROOT.parent / "daymade-claude-code/continue-codex-work/scripts/start_work.py"
        code, result, _ = self.call(self.two, B, "fork", entry=takeover)
        self.assertEqual((code, result["status"], result["active_total"]), (3, "conflict", 1))
        self.assertEqual(result["active"][0]["task"], "original")
        command[command.index("src/interpret.py")] = "src/independent.py"
        command[command.index("original")] = "independent"
        command[command.index("codex:" + A)] = "codex:" + B
        independent = subprocess.run(command, capture_output=True, text=True, env=self.env(B))
        self.assertEqual((independent.returncode, json.loads(independent.stdout)["status"]), (0, "registered"))
        missing = subprocess.run([sys.executable, str(entry), "start", "--peer-skill", str(self.root / "missing"),
                                  "--state-dir", str(self.root / "never-created"), "--", "--mode", "native-task"],
                                 capture_output=True, text=True, env=self.env(A))
        self.assertEqual(missing.returncode, 2)
        self.assertFalse((self.root / "never-created").exists())

    def test_directory_overlap_is_symmetric_but_path_prefix_alone_is_not(self):
        self.assertEqual(self.call(path="src/package")[0], 0)
        self.assertEqual(self.call(self.two, B, "child", "src/package/file.py")[1]["status"], "conflict")
        self.assertEqual(self.call(self.two, B, "neighbor", "src/package-other/file.py")[1]["status"], "registered")
        w = peer.work_start
        self.assertTrue(w.overlaps("git-path:x#src/package/file.py", "git-path:x#src/package"))
        self.assertFalse(w.overlaps("git-path:x#src/package", "git-path:y#src/package"))

    def test_released_owner_is_a_result_lead_not_completion_or_takeover(self):
        self.call()
        with contextlib.closing(self.board()) as board:
            board.release("git:code.example.test/team/sample", "case-a", "codex:" + A)
        code, result, _ = self.call(self.two, B, "fork-b")
        self.assertEqual((code, result["status"], result["previous_total"]), (3, "reconciliation_required", 1))
        self.assertIn("released is not delivered", result["next_action"])
        declaration = result["previous"][0]["declaration_id"]
        self.assertEqual(self.call(self.two, B, "fork-b", extra=["--reconciled-declaration", "f" * 64])[0], 3)
        code, current, _ = self.call(self.two, B, "fork-b", extra=["--reconciled-declaration", declaration])
        self.assertEqual((code, current["status"]), (0, "registered"))

    def test_stale_declaration_is_not_automatic_takeover(self):
        self.call()
        with contextlib.closing(self.board()) as board:
            board.db.execute("UPDATE owners SET updated=0")
        code, result, _ = self.call(self.two, B, "fork")
        self.assertEqual((code, result["status"], result["active_total"]), (3, "conflict", 1))
        self.assertEqual(result["active"][0]["freshness"], "stale")

    def test_new_entry_keeps_the_existing_owner_table_wire_format(self):
        self.call()
        with sqlite3.connect(self.state / "coordination.sqlite3") as db:
            self.assertEqual([row[1] for row in db.execute("PRAGMA table_info(owners)")],
                             ["scope", "task", "owner", "resources", "updated", "released"])
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
        with contextlib.closing(self.board()) as board:
            before = board.status()["owners"]
            board.claim("legacy", "legacy-task", "codex:" + A, ["desktop:another"])
            self.assertEqual(len(board.status()["owners"]), len(before) + 1)
        self.assertEqual(self.call(self.two, B, "fork")[1]["status"], "conflict")

    def test_claim_check_and_registration_are_atomic_for_competing_entries(self):
        def command(actor, repo, task):
            return subprocess.Popen([sys.executable, str(ROOT / "scripts/peer.py"), "--state-dir", str(self.state),
                                     "coord", "start", "--repo", str(repo), "--path", "src/interpret.py",
                                     "--task", task, "--actor", "codex:" + actor], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, env=self.env(actor))
        calls = [command(A, self.one, "one"), command(B, self.two, "two")]
        results = []
        for call in calls:
            stdout, stderr = call.communicate(timeout=15)
            self.assertFalse(stderr)
            results.append((call.returncode, json.loads(stdout)["status"]))
        self.assertEqual(sorted(results), [(0, "registered"), (3, "conflict")])

    def test_wrong_inherited_actor_and_missing_empty_identity_do_not_register(self):
        for actor, env in (("codex:" + B, self.env(A)), ("", self.env(A)),
                           ("codex:" + A, {**self.env(A), "CODEX_SESSION_ID": B}),
                           ("codex:" + A, {**self.env(A), "CODEX_SESSION_ID": ""})):
            with self.subTest(actor=actor, env=env.get("CODEX_SESSION_ID")):
                result = subprocess.run([sys.executable, str(ROOT / "scripts/peer.py"), "--state-dir", str(self.state),
                                         "coord", "start", "--repo", str(self.one), "--path", "src/interpret.py",
                                         "--task", "wrong", "--actor", actor], capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 3)
                self.assertFalse((self.state / "coordination.sqlite3").exists())

    def test_native_task_mode_has_no_independent_registration_or_actor_lookup(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/peer.py"), "--state-dir", str(self.state),
                                 "coord", "start", "--mode", "native-task"], capture_output=True, text=True,
                                env={**self.env(A), "CODEX_SESSION_ID": B})
        self.assertEqual((result.returncode, json.loads(result.stdout)["status"]), (0, "native_task_tree"))
        self.assertFalse(self.state.exists())

    def test_resource_origin_aliases_are_equal_and_userinfo_is_not_serialized(self):
        w = peer.work_start
        a = w.origin_identity("https://synthetic-user:synthetic-password@github.com/EXAMPLE/Sample.git?credential=synthetic", self.one)
        b = w.origin_identity("ssh://git@github.com:22/example/sample.git", self.two)
        self.assertEqual(a, b)
        self.assertNotIn("synthetic", a)
        self.assertNotEqual(w.origin_identity("https://gitlab.com/Team/Sample.git", self.one),
                            w.origin_identity("https://gitlab.com/team/sample.git", self.one))
        self.assertRaises(ValueError, w.resource_identity, self.one, ["../outside.py"])

    def test_missing_null_and_empty_contract_values_are_rejected(self):
        with contextlib.closing(self.board()) as board:
            for resources in (None, [], [None], [""], [" "]):
                with self.subTest(resources=resources), self.assertRaises(ValueError):
                    peer.work_start.start(board, "sample", "task", "codex:" + A, resources)
            for index in range(3):
                for field in (None, "", " ", "x" * 161):
                    values = ["sample", "task", "codex:" + A]
                    values[index] = field
                    with self.subTest(field_index=index, value=field), self.assertRaises(ValueError):
                        peer.work_start.start(board, *values, ["desktop:test"])
            for reconciled in (None, [None], [""], ["not-a-digest"]):
                with self.subTest(reconciled=reconciled), self.assertRaises(ValueError):
                    peer.work_start.start(board, "sample", "task", "codex:" + A, ["desktop:test"], reconciled=reconciled)
            self.assertEqual(len(board.status()["owners"]), 0)

    def test_recall_assertion_detects_removing_the_overlap_mechanism(self):
        self.call()
        scope, resources = peer.work_start.resource_identity(self.two, ["src/interpret.py"])
        with contextlib.closing(self.board()) as board, mock.patch.object(peer.work_start, "overlaps", return_value=False):
            mutated = peer.work_start.start(board, scope, "different-task", "codex:" + B, resources)
        with self.assertRaises(AssertionError):
            self.assertEqual(mutated["status"], "conflict")


if __name__ == "__main__":
    unittest.main()
