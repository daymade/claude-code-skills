import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


class FeishuDeliveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SKILL.read_text(encoding="utf-8")
        cls.upload = cls.text.split(
            "## Option: Upload to Feishu Minutes for transcription", 1
        )[1].split("## Step 3: Transcribe", 1)[0]
        cls.upload_flat = " ".join(cls.upload.split())

    def test_upload_route_distinguishes_all_terminal_outcomes(self):
        for phrase in (
            "Upload-only",
            "Transcript-only",
            "Project delivery",
            "Downstream unspecified",
        ):
            self.assertIn(phrase, self.upload)

    def test_bare_upload_request_enters_resumable_pending_outcome(self):
        self.assertIn("上传到飞书妙记，先转成适合 ASR 的格式", self.upload)
        self.assertIn("outcome_pending", self.upload)
        self.assertIn("next_required_phase=outcome_decision", self.upload)
        self.assertIn("resumes that same", self.upload)

    def test_project_delivery_cannot_end_at_minute_url(self):
        self.assertIn("meeting-ingest", self.upload)
        self.assertIn("next_required_phase=minute_ready", self.upload)
        self.assertIn("pushed delivery receipt", self.upload)
        self.assertNotIn(
            "once the minute is created, this skill's job ends here",
            self.upload,
        )
        self.assertNotIn(
            "do not run `sync-feishu-minutes` ingest/delegate",
            self.upload,
        )

    def test_partial_run_resumes_same_minute_instead_of_reuploading(self):
        self.assertIn("exact last completed phase", self.upload_flat)
        self.assertIn("Resume that same", self.upload_flat)
        self.assertIn("never re-upload", self.upload_flat)


if __name__ == "__main__":
    unittest.main()
