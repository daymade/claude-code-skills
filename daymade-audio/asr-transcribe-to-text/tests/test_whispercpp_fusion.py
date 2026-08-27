import importlib.util
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = SKILL_ROOT / "scripts" / "fuse_whispercpp_diarization.py"
    spec = importlib.util.spec_from_file_location("whispercpp_fusion_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


fusion = load_module()


class WhisperCppFusionTests(unittest.TestCase):
    def make_contract_fixture(self, root):
        source = root / "fixture.wav"
        with wave.open(str(source), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\0\0" * 16000)
        source_contract = fusion.source_identity(source)
        runner = SKILL_ROOT / "scripts" / "transcribe_long_whispercpp.py"
        diarizer = SKILL_ROOT / "scripts" / "diarize_speakers.py"
        diarizer_lock = SKILL_ROOT / "scripts" / "diarize_speakers.py.lock"
        whisper_json = root / "fixture.whispercpp.json"
        whisper_payload = {
            "source_audio": source_contract,
            "producer": {
                "script": runner.name,
                "sha256": fusion.sha256_file(runner),
            },
            "runtime": {"fixture": True},
            "parameters": {"processing_end_s": 1.0},
            "transcription": [
                {
                    "offsets": {"from": 0, "to": 800},
                    "text": "真实发言",
                }
            ],
        }
        whisper_json.write_text(json.dumps(whisper_payload), encoding="utf-8")
        outputs = {
            "json": {
                "file": whisper_json.name,
                "sha256": fusion.sha256_file(whisper_json),
            }
        }
        manifest = root / "checkpoint-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": "whispercpp-long-audio-checkpoint-v1",
                    "status": "complete",
                    "source_audio": source_contract,
                    "producer": whisper_payload["producer"],
                    "runtime": whisper_payload["runtime"],
                    "parameters": whisper_payload["parameters"],
                    "outputs": outputs,
                }
            ),
            encoding="utf-8",
        )
        (root / "fixture.whispercpp.receipt.json").write_text(
            json.dumps(
                {
                    "schema": "whispercpp-long-audio-v1-receipt",
                    "source_audio": source_contract,
                    "outputs": outputs,
                    "checkpoint_manifest": {
                        "path": str(manifest.resolve()),
                        "sha256": fusion.sha256_file(manifest),
                    },
                }
            ),
            encoding="utf-8",
        )
        diarization_json = root / "diarization.json"
        diarization_json.write_text(
            json.dumps(
                {
                    "source_audio": source_contract,
                    "producer": {
                        "script": diarizer.name,
                        "sha256": fusion.sha256_file(diarizer),
                        "lock": diarizer_lock.name,
                        "lock_sha256": fusion.sha256_file(diarizer_lock),
                    },
                    "model_contract": {
                        "id": "pyannote/speaker-diarization-3.1",
                        "revision": "fixture",
                    },
                    "decoder": {"fixture": True},
                    "num_segments": 1,
                    "num_speakers": 1,
                    "segments": [
                        {"start": 0.0, "end": 0.9, "speaker": "SPEAKER_00"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        return source, whisper_json, diarization_json

    def test_no_speech_segments_are_removed_and_speaker_uses_max_overlap(self):
        whisper = [
            {"index": 0, "start": 0.0, "end": 2.0, "text": "real A"},
            {"index": 1, "start": 4.0, "end": 5.0, "text": "silence hallucination"},
            {"index": 2, "start": 5.0, "end": 7.0, "text": "real B"},
        ]
        diarization = [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_A"},
            {"start": 5.0, "end": 8.0, "speaker": "SPEAKER_B"},
        ]

        grounded, discarded = fusion.ground_segments(
            whisper, diarization, min_overlap=0.05
        )

        self.assertEqual([item["speaker"] for item in grounded], ["SPEAKER_A", "SPEAKER_B"])
        self.assertEqual([item["text"] for item in discarded], ["silence hallucination"])

    def test_three_adjacent_exact_repeats_collapse_but_two_are_preserved(self):
        repeated = [
            {
                "index": index,
                "start": float(index * 2),
                "end": float(index * 2 + 2),
                "text": "同一句话",
                "speaker": "SPEAKER_A",
                "speech_overlap_s": 2.0,
            }
            for index in range(3)
        ]
        collapsed, removed = fusion.collapse_repeat_runs(repeated)
        preserved, preserved_removed = fusion.collapse_repeat_runs(repeated[:2])

        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]["collapsed_repeat_count"], 3)
        self.assertEqual(len(removed), 2)
        self.assertEqual(len(preserved), 2)
        self.assertEqual(preserved_removed, [])

    def test_invalid_utf8_is_visible_in_the_input_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "fixture.json"
            source.write_bytes(b'{"value":"\xff"}')

            payload, replacements, contract = fusion.read_json(source)

        self.assertEqual(payload["value"], "\ufffd")
        self.assertEqual(replacements, 1)
        self.assertEqual(contract["size"], len(b'{"value":"\xff"}'))
        self.assertEqual(len(contract["sha256"]), 64)

    def test_long_timestamp_uses_total_minutes_for_existing_bundle_parser(self):
        self.assertEqual(fusion.format_timestamp(3 * 3600 + 22 * 60 + 4.55), "202:04.550")

    def test_main_emits_the_existing_speaker_bundle_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, whisper_json, diarization_json = self.make_contract_fixture(root)
            output = root / "output"
            with mock.patch.object(
                sys,
                "argv",
                [
                    str(SKILL_ROOT / "scripts" / "fuse_whispercpp_diarization.py"),
                    str(whisper_json),
                    str(diarization_json),
                    str(source),
                    str(output),
                    "--end-at",
                    "1.0",
                ],
            ):
                fusion.main()

            receipt = json.loads(
                (output / "fixture.receipt.json").read_text(encoding="utf-8")
            )
            alignment = json.loads(
                (output / "fixture.alignment.json").read_text(encoding="utf-8")
            )

        self.assertEqual(receipt["schema"], "speaker-bundle-receipt-v1")
        self.assertEqual(alignment["parameters"]["processing_end_s"], 1.0)
        self.assertEqual(alignment["report"]["num_turns"], 1)
        self.assertIn("diarize_speakers.py.lock", receipt["pipeline"])
        self.assertEqual(
            receipt["model_contract"]["diarization"]["id"],
            "pyannote/speaker-diarization-3.1",
        )

    def test_main_rejects_diarization_from_different_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, whisper_json, diarization_json = self.make_contract_fixture(root)
            payload = json.loads(diarization_json.read_text(encoding="utf-8"))
            payload["source_audio"]["sha256"] = "0" * 64
            diarization_json.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(
                sys,
                "argv",
                [
                    "fuse_whispercpp_diarization.py",
                    str(whisper_json),
                    str(diarization_json),
                    str(source),
                    str(root / "output"),
                ],
            ), self.assertRaisesRegex(ValueError, "diarization source identity"):
                fusion.main()


if __name__ == "__main__":
    unittest.main()
