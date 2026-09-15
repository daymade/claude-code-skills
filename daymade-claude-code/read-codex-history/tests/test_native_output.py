import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("native_search_test", ROOT / "scripts/analyze_sessions.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def event(identity="command-1", text="native-output-only-marker"):
    return {"timestamp": "2026-08-12T03:08:29Z", "type": "event_msg", "payload": {
        "type": "item_completed", "item": {"type": "CommandExecution", "id": identity,
        "stdout": text, "stderr": "", "aggregated_output": text, "formatted_output": text}}}


class NativeOutputTests(unittest.TestCase):
    def test_native_output_aliases_are_searched_once(self):
        segments = module.codex_searchable_segments(event())
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].text, "native-output-only-marker")

    def test_empty_streams_fall_back_to_aggregate(self):
        row = event(); row["payload"]["item"]["stdout"] = ""
        self.assertEqual(len(module.codex_searchable_segments(row)), 1)

    def test_message_mirrors_are_still_skipped(self):
        self.assertEqual(module.codex_searchable_segments({"type": "event_msg", "payload": {
            "type": "agent_message", "message": "native-output-only-marker"}}), [])

    def test_identity_bound_mirror_dedup_keeps_distinct_commands(self):
        seen = set()
        row = event()
        self.assertEqual(len(module.distinct_result_segments(row, module.codex_searchable_segments(row), seen)), 1)
        mirror = {"type": "response_item", "payload": {"type": "function_call_output",
            "call_id": "command-1", "output": "native-output-only-marker"}}
        self.assertEqual(module.distinct_result_segments(mirror, module.codex_searchable_segments(mirror), seen), [])
        other = event("command-2")
        self.assertEqual(len(module.distinct_result_segments(other, module.codex_searchable_segments(other), seen)), 1)

    def test_full_search_finds_native_result_not_command_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout.jsonl"
            row = event(); row["payload"]["item"]["command"] = ["echo", "metadata-only-marker"]
            meta = {"type": "session_meta", "payload": {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "cwd": "/tmp/example"}}
            path.write_text("\n".join(json.dumps(x) for x in [meta, row, row]))
            result = module.search_codex_rollouts([path], ["native-output-only-marker"], use_prefilter=False)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["total_mentions"], 1)
            self.assertEqual(module.search_codex_rollouts([path], ["absent-marker"], use_prefilter=False), [])


if __name__ == "__main__":
    unittest.main()
