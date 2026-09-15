import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("verify_artifact", Path(__file__).resolve().parents[1] / "scripts/verify_artifact.py")
verify_artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_artifact)


class ArtifactProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidate = self.root / "SKILL.md"
        self.candidate.write_text("# Current prompt\n完整原文\n")
        self.archive = self.root / "request.json"
        self.messages = [
            {"role": "assistant", "content": [{"type": "tool_use", "id": "read-1", "name": "read", "input": {"path": "/agent/skills/title/SKILL.md"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "read-1", "content": self.candidate.read_text()}]},
        ]

    def run_proof(self, candidate=None, member=None, timestamp="2026-09-13T09:55:49Z"):
        self.archive.write_text(json.dumps({"timestamp": timestamp, "request_id": "sample-request", "request": {"body": {"messages": self.messages}}}))
        return verify_artifact.verify(candidate or self.candidate, self.archive, "/agent/skills/title/SKILL.md", member)

    def test_exact_read_matches_and_does_not_claim_current_deployment(self):
        result = self.run_proof()
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["current_deployment"], "not_checked")

    def test_related_old_prompt_does_not_match(self):
        self.candidate.write_text("# Earlier research prompt\n")
        self.assertEqual(self.run_proof()["status"], "not_matched")

    def test_path_mention_without_tool_call_is_not_proof(self):
        self.messages = [{"role": "user", "content": [{"type": "text", "text": self.candidate.read_text()}]}]
        self.assertEqual(self.run_proof()["status"], "not_matched")

    def test_wrong_tool_path_does_not_match(self):
        self.messages[0]["content"][0]["input"]["path"] = "/draft/SKILL.md"
        self.assertEqual(self.run_proof()["status"], "not_matched")

    def test_failed_read_does_not_match_even_if_text_matches(self):
        self.messages[1]["content"][0]["is_error"] = True
        self.assertEqual(self.run_proof()["status"], "not_matched")

    def test_unflagged_error_envelope_is_not_a_read(self):
        error = '{"status":"error","error":"ENOENT"}'
        self.candidate.write_text(error)
        self.messages[1]["content"][0]["content"] = error
        self.assertEqual(self.run_proof()["status"], "not_matched")

    def test_no_whitespace_normalization(self):
        self.candidate.write_bytes(self.candidate.read_bytes().rstrip())
        self.assertEqual(self.run_proof()["status"], "not_matched")

    def test_zip_exact_member_and_duplicate_rejection(self):
        archive = self.root / "backup.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("skills/title/SKILL.md", self.candidate.read_bytes())
        self.assertEqual(self.run_proof(archive, "skills/title/SKILL.md")["status"], "matched")
        with self.assertRaises(verify_artifact.EvidenceError):
            self.run_proof(archive, "other/SKILL.md")

    def test_missing_timezone_rejected(self):
        with self.assertRaises(verify_artifact.EvidenceError):
            self.run_proof(timestamp="2026-09-13T09:55:49")

    def test_ambiguous_call_id_rejected(self):
        self.messages.insert(1, self.messages[0])
        with self.assertRaises(verify_artifact.EvidenceError):
            self.run_proof()


if __name__ == "__main__":
    unittest.main()
