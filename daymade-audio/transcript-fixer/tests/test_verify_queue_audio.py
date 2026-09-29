"""Regression for conflicting clip readings gaining review authority."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_queue_audio.py"
spec = importlib.util.spec_from_file_location("verify_queue_audio", SCRIPT)
verify_queue_audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_queue_audio)


class WindowEvidenceTests(unittest.TestCase):
    def test_identical_windows_are_rejected(self):
        with patch.object(sys, "argv", [str(SCRIPT), "--transcript", "t",
                                        "--audio", "a", "--engine-script", "e",
                                        "--tight", "5", "--medium", "5"]):
            with self.assertRaises(SystemExit) as stopped:
                verify_queue_audio.main()
        self.assertEqual(stopped.exception.code, 2)

    def test_only_two_successful_matching_windows_support_suggestion(self):
        base = {
            "suggested": "李甲乙", "original": "李甲丙",
            "tight_exit": 0, "medium_exit": 0,
            "tight": "李甲乙的话", "medium": "刚才李甲乙的话",
        }
        self.assertTrue(verify_queue_audio.both_windows_support_suggestion(base))
        for changed in (
            {"tight": "李甲丙的话"},
            {"medium": "李甲丙的话"},
            {"tight": ""},
            {"medium_exit": 1},
            {"suggested": ""},
            {"original": ""},
            {"medium": "李甲乙丙的话"},
            {"medium": "李甲乙的话，李甲乙丙的话"},
            {"medium": "李甲丙的话，李甲乙的话"},
        ):
            with self.subTest(changed=changed):
                self.assertFalse(verify_queue_audio.both_windows_support_suggestion(
                    {**base, **changed}))

    def _run_case(self, tight_text, medium_text):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            transcript = root / "meeting.md"
            transcript.write_text(
                "甲 00:00:01.000\n你讲话这件事。\n乙 00:00:10.000\n好。\n",
                encoding="utf-8",
            )
            calls = []

            def run(args, **kwargs):
                calls.append(args)
                if args[0] == "ffmpeg":
                    return CompletedProcess(args, 0, stdout="", stderr="")
                if args[0] == "python3":
                    text = tight_text if "-tight.wav" in args[-1] else medium_text
                    return CompletedProcess(args, 0, stdout=text, stderr="")
                if args[0] == "uv" and "--attach-authority" in args:
                    return CompletedProcess(args, 0, stdout="{}", stderr="")
                self.fail(f"unexpected subprocess: {args}")

            item = {
                "id": 1, "line_number": 2,
                "original_text": "你讲话", "suggested_text": "李甲乙",
            }
            argv = [
                str(SCRIPT), "--transcript", str(transcript),
                "--audio", str(root / "source.wav"),
                "--engine-script", str(root / "engine.py"),
                "--outdir", str(root / "results"),
            ]
            with patch.object(verify_queue_audio, "list_pending", return_value=[item]), \
                    patch.object(verify_queue_audio.subprocess, "run", side_effect=run), \
                    patch.object(sys, "argv", argv):
                verify_queue_audio.main()

            result = json.loads((root / "results" / "results.json").read_text())
            return result[0], calls

    def test_disagreement_does_not_attach_authority(self):
        result, calls = self._run_case("李甲丙这件事", "李甲乙这件事")
        self.assertEqual(result["tight"], "李甲丙这件事")
        self.assertEqual(result["medium"], "李甲乙这件事")
        self.assertFalse(any(args[0] == "uv" for args in calls))

    def test_name_boundary_disagreement_does_not_attach_authority(self):
        _, calls = self._run_case("李甲乙说过", "李甲乙丙说过")
        self.assertFalse(any(args[0] == "uv" for args in calls))

    def test_two_matching_windows_attach_without_deciding(self):
        _, calls = self._run_case("李甲乙这件事", "刚才李甲乙这件事")
        authority_calls = [args for args in calls if args[0] == "uv"]
        self.assertEqual(len(authority_calls), 1)
        self.assertIn("--attach-authority", authority_calls[0])
        self.assertNotIn("--resolve-review", authority_calls[0])


if __name__ == "__main__":
    unittest.main()
