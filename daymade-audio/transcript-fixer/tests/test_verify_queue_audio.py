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
            "tight": "李甲乙，的话", "medium": "刚才李甲乙，的话",
        }
        self.assertTrue(verify_queue_audio.both_windows_support_suggestion(base))
        for changed in (
            {"tight": "李甲丙的话"},
            {"medium": "李甲丙的话"},
            {"tight": "李甲乙的话"},
            {"tight": ""},
            {"medium_exit": 1},
            {"same_clip": True},
            {"suggested": ""},
            {"original": ""},
            {"medium": "李甲乙丙的话"},
            {"medium": "李甲乙的话，李甲乙丙的话"},
            {"medium": "李甲丙的话，李甲乙的话"},
            {"tight": "李甲乙丙说过", "medium": "李甲乙丙说过"},
            {"tight": "李甲乙 丙说过", "medium": "李甲乙 丙说过"},
            {"tight": "李甲乙\n丙说过", "medium": "李甲乙\n丙说过"},
        ):
            with self.subTest(changed=changed):
                self.assertFalse(verify_queue_audio.both_windows_support_suggestion(
                    {**base, **changed}))

    def _run_case(self, tight_text, medium_text, same_clips=False,
                  tight_seconds=5, medium_seconds=20, override=True):
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
                    Path(args[-1]).write_bytes(
                        b"same" if same_clips else
                        (b"tight" if "-tight.wav" in args[-1] else b"medium"))
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
            overrides = root / "times.json"
            overrides.write_text(json.dumps({
                "1": {"seconds": 1, "anchors": ["这件事"]}
            }))
            argv = [
                str(SCRIPT), "--transcript", str(transcript),
                "--audio", str(root / "source.wav"),
                "--engine-script", str(root / "engine.py"),
                "--outdir", str(root / "results"),
                "--tight", str(tight_seconds), "--medium", str(medium_seconds),
            ]
            if override:
                argv += ["--time-overrides", str(overrides)]
            with patch.object(verify_queue_audio, "list_pending", return_value=[item]), \
                    patch.object(verify_queue_audio, "media_duration", return_value=60), \
                    patch.object(verify_queue_audio.subprocess, "run", side_effect=run), \
                    patch.object(sys, "argv", argv):
                exit_code = verify_queue_audio.main()

            result = json.loads((root / "results" / "results.json").read_text())
            return {**result[0], "_exit_code": exit_code}, calls

    def test_disagreement_does_not_attach_authority(self):
        result, calls = self._run_case("李甲丙这件事", "李甲乙这件事")
        self.assertEqual(result["tight"], "李甲丙这件事")
        self.assertEqual(result["medium"], "李甲乙这件事")
        self.assertFalse(any(args[0] == "uv" for args in calls))

    def test_name_boundary_disagreement_does_not_attach_authority(self):
        _, calls = self._run_case("李甲乙，这件事", "李甲乙丙，这件事")
        self.assertFalse(any(args[0] == "uv" for args in calls))

    def test_same_longer_name_cannot_authorize_its_prefix(self):
        _, calls = self._run_case("李甲乙丙，这件事", "李甲乙丙，这件事")
        self.assertFalse(any(args[0] == "uv" for args in calls))

    def test_identical_clips_do_not_call_asr_or_attach_authority(self):
        result, calls = self._run_case("李甲乙，说过", "李甲乙，说过",
                                       same_clips=True, tight_seconds=5.01,
                                       medium_seconds=5.02)
        ffmpeg_calls = [args for args in calls if args[0] == "ffmpeg"]
        self.assertEqual([(args[args.index("-ss") + 1],
                           args[args.index("-t") + 1]) for args in ffmpeg_calls],
                         [("0.000", "6.010"), ("0.000", "6.020")])
        self.assertTrue(result["same_clip"])
        self.assertFalse(any(args[0] in ("python3", "uv") for args in calls))

    def test_two_matching_windows_attach_without_deciding(self):
        _, calls = self._run_case("李甲乙，这件事", "刚才李甲乙，这件事")
        authority_calls = [args for args in calls if args[0] == "uv"]
        self.assertEqual(len(authority_calls), 1)
        self.assertIn("--attach-authority", authority_calls[0])
        self.assertNotIn("--resolve-review", authority_calls[0])

    def test_off_target_text_is_reanchoring_not_disagreement(self):
        result, calls = self._run_case("完全另一话题", "刚才李甲乙，这件事")
        self.assertEqual(result["status"], "needs_reanchor")
        self.assertEqual(result["_exit_code"], 1)
        self.assertFalse(any(args[0] == "uv" for args in calls))

    def test_matching_token_without_neighbours_cannot_attach(self):
        result, calls = self._run_case("李甲乙，别的内容", "李甲乙，别的内容")
        self.assertEqual(result["status"], "needs_reanchor")
        self.assertFalse(any(args[0] == "uv" for args in calls))

    def test_estimate_without_verified_neighbours_is_explicit_unknown(self):
        result, calls = self._run_case("李甲乙，这件事", "李甲乙，这件事", override=False)
        self.assertEqual(result["status"], "coverage_unknown")
        self.assertEqual(result["_exit_code"], 1)
        self.assertFalse(any(args[0] == "uv" for args in calls))

    def test_original_can_be_supported_without_a_suggestion(self):
        result, calls = self._run_case("你讲话这件事", "刚才你讲话这件事")
        self.assertEqual(result["status"], "original_supported")
        self.assertEqual(result["_exit_code"], 0)
        self.assertFalse(any(args[0] == "uv" for args in calls))

    def test_last_turn_uses_real_media_duration_on_transcript_clock(self):
        turns = [(1, 10.0, "甲", "前半目标")]
        self.assertEqual(verify_queue_audio.token_offset(turns, 2, "目标", 20), 15)
        self.assertIsNone(verify_queue_audio.token_offset(turns, 2, "目标"))
        self.assertIsNone(verify_queue_audio.token_offset(turns, 2, "不在正文", 20))
        self.assertIsNone(verify_queue_audio.token_offset(turns, 0, "目标", 20))

    def test_overrides_reject_missing_empty_null_and_invalid_fields(self):
        with tempfile.TemporaryDirectory() as work:
            file = Path(work) / "override.json"
            bad = [None, [], {"x": {"seconds": 1, "anchors": ["邻接词"]}}]
            for seconds in (None, "", True, -1, float("nan"), float("inf")):
                bad.append({"1": {"seconds": seconds, "anchors": ["邻接词"]}})
            for anchors in (None, [], [""], ["，"], "邻接词", [1]):
                bad.append({"1": {"seconds": 1, "anchors": anchors}})
            bad += [{"1": {"anchors": ["邻接词"]}}, {"1": {"seconds": 1}}]
            for value in bad:
                with self.subTest(value=value):
                    file.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        verify_queue_audio.load_time_overrides(file)
            file.write_text('{"1": {"seconds": 0, "anchors": ["邻接词"]}}')
            self.assertEqual(verify_queue_audio.load_time_overrides(file)["1"]["seconds"], 0)

    def test_unavailable_media_duration_is_not_a_guess(self):
        for value, code in (("", 1), ("N/A", 0), ("nan", 0), ("-1", 0)):
            with self.subTest(value=value), patch.object(
                    verify_queue_audio.subprocess, "run",
                    return_value=CompletedProcess([], code, stdout=value)):
                self.assertIsNone(verify_queue_audio.media_duration("audio"))


if __name__ == "__main__":
    unittest.main()
