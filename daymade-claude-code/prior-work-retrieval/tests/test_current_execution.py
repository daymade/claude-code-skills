from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import prior_work

spec = importlib.util.spec_from_file_location("current_execution_hook", SCRIPTS / "prior_work_hook.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

# Invented execution-control wording preserves the triggering grammar. The
# original prompt is used only by the private calibration outside this bundle.
CURRENT_PROMPT = (
    "沿用本次原生会话、工作目录以及只读限制。"
    "请检查本次进程与 cwd；给出只读执行状态。"
)


class CurrentExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "known.md").write_text("known provider contract\n")
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text(json.dumps({
            "schema_version": 1, "state_dir": str(self.root / "state"),
            "sources": [{"id": "docs", "carrier": "docs", "mode": "filesystem",
                         "root": str(self.source), "includes": ["**/*.md"],
                         "authority": "project_ssot", "required": True}],
        }))
        patcher = mock.patch.dict(os.environ, {"PRIOR_WORK_MANIFEST": str(self.manifest_path)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.manifest = hook._manifest()
        self.event = {"hook_event_name": "UserPromptSubmit", "session_id": "synthetic-child",
                      "prompt": CURRENT_PROMPT}
        self.stop = {"hook_event_name": "Stop", "session_id": self.event["session_id"],
                     "stop_hook_active": False}

    def mark_old(self, prompt=CURRENT_PROMPT):
        return prior_work.mark_requirement(self.manifest, self.event["session_id"],
            prompt=prompt, trigger="required_prior_signal", required=True)

    def read_state(self):
        return prior_work.load_requirement(self.manifest, self.event["session_id"])

    def run_reclassification(self, requirement_id, event=None):
        return subprocess.run([sys.executable, str(SCRIPTS / "prior_work_hook.py"),
                               "--reclassify-requirement", requirement_id],
            input=json.dumps(self.event if event is None else event), text=True,
            capture_output=True, env=os.environ)

    def test_current_execution_objects_do_not_arm(self):
        prompts = [CURRENT_PROMPT, "沿用当前会话、cwd 和只读范围。",
                   "沿用本次执行身份。", "沿用当前工作目录和只读范围。",
                   "沿用当前 read-only 范围。", "沿用本次原生会话。",
                   "沿用本次原生会话、cwd与只读限制；请只做当前核对。"]
        self.assertEqual(len(prompts), 7)
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(hook.classify_prompt(prompt), "none")
                self.assertIsNone(hook.handle_user_prompt({**self.event, "prompt": prompt}))
                self.assertIsNone(self.read_state())
                self.assertIsNone(hook.handle_stop(self.stop))

    def test_local_excision_preserves_real_history_requests(self):
        prompts = [
            "已有脚本可以直接沿用", "直接沿用现有实现，不要重写",
            "沿用之前的脚本。", "沿用当前 child 的历史方案。",
            "沿用当前会话和之前的代码。", CURRENT_PROMPT + "请查我们之前的方案。",
            "沿用当前 child、工作目录；复用已有代码。",
            "沿用当前 cwd。上次那个脚本叫什么？",
            "沿用当前会话和当前目录里的历史脚本。",
            "沿用当前 child、历史方案。",
            "沿用当前 child，历史方案。",
            "沿用当前会话与工作目录以及旧脚本。",
            "沿用当前 cwd、上次产物。",
            "沿用当前会话、工作目录和只读范围里的历史方案。",
            "沿用当前cwd与历史脚本。",
        ]
        self.assertEqual(len(prompts), 15)
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(hook.classify_prompt(prompt), "required_prior_signal")
                hook.handle_user_prompt({**self.event, "prompt": prompt})
                self.assertEqual(hook.handle_stop(self.stop)["decision"], "block")
                self.assertIsNone(hook.handle_stop({**self.stop, "stop_hook_active": True}))

    def test_coordinated_asset_replay_never_retires_a_history_obligation(self):
        for prompt in ["沿用当前会话和当前目录里的历史脚本。", "沿用当前 child、历史方案。"]:
            before = self.mark_old(prompt)
            with self.subTest(prompt=prompt):
                result = self.run_reclassification(before["requirement_id"], {**self.event, "prompt": prompt})
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.read_state(), before)
                self.assertEqual(hook.handle_stop(self.stop)["decision"], "block")

    def test_ordinary_and_same_prompt_replay_do_not_implicitly_release(self):
        before = self.mark_old()
        for prompt in ["继续", "现在只查当前状态", CURRENT_PROMPT]:
            with self.subTest(prompt=prompt):
                hook.handle_user_prompt({**self.event, "prompt": prompt})
                self.assertEqual(self.read_state(), before)
                self.assertEqual(hook.handle_stop(self.stop)["decision"], "block")

    def test_exact_controlled_replay_retires_scope_without_receipt_or_optout(self):
        before = self.mark_old()
        result = self.run_reclassification(before["requirement_id"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "reclassified")
        after = self.read_state()
        for key, value in before.items():
            self.assertEqual(after[key], value, key)
        self.assertIs(after["active_for_prompt"], False)
        audit = after["scope_reclassification"]
        self.assertEqual(audit["reason"], "current_execution_continuity")
        self.assertEqual(audit["classification"], "none")
        self.assertEqual(audit["classifier_sha256"],
                         "sha256:" + hashlib.sha256((SCRIPTS / "prior_work_hook.py").read_bytes()).hexdigest())
        self.assertTrue(audit["reclassified_at"].endswith("Z"))
        self.assertIsNone(hook.handle_stop(self.stop))
        with self.assertRaises(prior_work.PriorWorkError):
            prior_work.check_receipt(self.manifest, self.event["session_id"], None)
        self.assertFalse((self.root / "state" / "receipts").exists())
        repeated = self.run_reclassification(before["requirement_id"])
        self.assertEqual(repeated.returncode, 2)
        self.assertEqual(self.read_state(), after)
        # A real new obligation still arms after correcting the old false one.
        hook.handle_user_prompt({**self.event, "prompt": "请查我们之前的脚本。"})
        self.assertNotEqual(self.read_state()["requirement_id"], before["requirement_id"])
        self.assertEqual(hook.handle_stop(self.stop)["decision"], "block")

    def test_documented_wrapper_command_uses_the_original_event(self):
        before = self.mark_old()
        original_event = self.root / "original-event.json"
        original_event.write_text(json.dumps(self.event))
        environment = {**os.environ, "REQUIREMENT_ID": before["requirement_id"],
                       "ORIGINAL_EVENT_JSON": str(original_event),
                       "PRIOR_WORK_PYTHON_BIN": sys.executable}
        result = subprocess.run(["bash", "-c",
            'scripts/prior-work-retrieval.sh --reclassify-requirement "$REQUIREMENT_ID" < "$ORIGINAL_EVENT_JSON"'],
            cwd=SCRIPTS.parent, text=True, capture_output=True, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["requirement_id"], before["requirement_id"])
        self.assertIs(self.read_state()["active_for_prompt"], False)
        self.assertIsNone(hook.handle_stop(self.stop))

    def test_missing_null_blank_or_drifted_event_cannot_reclassify(self):
        before = self.mark_old()
        for key in ["hook_event_name", "session_id", "prompt"]:
            for value in [None, "", " ", "different"]:
                event = {**self.event, key: value}
                with self.subTest(key=key, value=value):
                    result = self.run_reclassification(before["requirement_id"], event)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(self.read_state(), before)
            event = dict(self.event)
            del event[key]
            with self.subTest(key=key, missing=True):
                self.assertEqual(self.run_reclassification(before["requirement_id"], event).returncode, 2)
                self.assertEqual(self.read_state(), before)
        for value in [None, "", " ", "0" * 20]:
            with self.subTest(requirement_id=value):
                with self.assertRaises(prior_work.PriorWorkError):
                    hook.reclassify_requirement(self.event, value)
                self.assertEqual(self.read_state(), before)

    def test_missing_null_blank_or_drifted_stored_identity_cannot_reclassify(self):
        before = self.mark_old()
        path = prior_work.requirement_path(self.manifest, self.event["session_id"])
        cases = {
            "schema_version": [None, "", 2, True], "kind": [None, "", "other"],
            "session_id": [None, "", "other"], "requirement_id": [None, "", "0" * 20],
            "prompt_sha256": [None, "", "sha256:" + "0" * 64],
            "prompt_preview": [None, "", "other prompt"],
            "manifest_sha256": [None, "", "sha256:" + "0" * 64],
            "required": [None, "", False, 1], "trigger": [None, "", "opt_out"],
            "created_at": [None, "", " ", "invalid", "2026-01-01T00:00:00"],
        }
        for key, values in cases.items():
            for value in values + ["MISSING"]:
                modified = copy.deepcopy(before)
                if value == "MISSING":
                    del modified[key]
                else:
                    modified[key] = value
                prior_work._atomic_json(path, modified)
                with self.subTest(key=key, value=value):
                    with self.assertRaises(prior_work.PriorWorkError):
                        hook.reclassify_requirement(self.event, before["requirement_id"])
                    self.assertEqual(json.loads(path.read_text()), modified)
        for value in [None, "", False, 1]:
            modified = {**before, "active_for_prompt": value}
            prior_work._atomic_json(path, modified)
            with self.subTest(active_for_prompt=value):
                with self.assertRaises(prior_work.PriorWorkError):
                    hook.reclassify_requirement(self.event, before["requirement_id"])
                self.assertEqual(json.loads(path.read_text()), modified)

    def test_genuine_prior_or_other_none_reclassifications_are_rejected(self):
        prompts = ["请复用以前的脚本。", "继续", CURRENT_PROMPT + "请复用以前的脚本。",
                   "<task-notification>沿用当前 child。</task-notification>"]
        for prompt in prompts:
            before = self.mark_old(prompt)
            with self.subTest(prompt=prompt):
                result = self.run_reclassification(before["requirement_id"], {**self.event, "prompt": prompt})
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.read_state(), before)

    def test_changed_requirement_during_classification_cannot_be_overwritten(self):
        before = self.mark_old()
        newer = {**before, "requirement_id": "0" * 20}
        path = prior_work.requirement_path(self.manifest, self.event["session_id"])
        real_classify = hook.classify_prompt
        def replace_then_classify(prompt, receipt_valid=False):
            prior_work._atomic_json(path, newer)
            return real_classify(prompt, receipt_valid)
        with mock.patch.object(hook, "classify_prompt", side_effect=replace_then_classify):
            with self.assertRaisesRegex(prior_work.PriorWorkError, "changed during"):
                hook.reclassify_requirement(self.event, before["requirement_id"])
        self.assertEqual(self.read_state(), newer)


if __name__ == "__main__":
    unittest.main()
