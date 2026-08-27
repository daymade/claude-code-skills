import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = SKILL_ROOT / "scripts" / "transcribe_long_whispercpp.py"
    spec = importlib.util.spec_from_file_location("whispercpp_long_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


long_asr = load_module()


class WhisperCppLongAudioTests(unittest.TestCase):
    def test_block_plan_has_source_overlap_but_contiguous_base_ownership(self):
        blocks = long_asr.plan_blocks(130.0, 130.0, 60.0, 2.0)

        self.assertEqual(
            [
                (
                    block["base_start_s"],
                    block["base_end_s"],
                    block["extract_start_s"],
                    block["extract_end_s"],
                )
                for block in blocks
            ],
            [
                (0.0, 60.0, 0.0, 62.0),
                (60.0, 120.0, 58.0, 122.0),
                (120.0, 130.0, 118.0, 130.0),
            ],
        )

    def test_midpoint_ownership_removes_overlap_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw.json"
            raw.write_text(
                json.dumps(
                    {
                        "transcription": [
                            {
                                "offsets": {"from": 1000, "to": 3000},
                                "text": "owned by block two",
                            },
                            {
                                "offsets": {"from": 0, "to": 1000},
                                "text": "left overlap only",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            block = {
                "index": 1,
                "base_start_s": 60.0,
                "base_end_s": 120.0,
                "extract_start_s": 58.0,
                "extract_end_s": 122.0,
            }

            transcription, replacements = long_asr.normalize_whisper_json(raw, block)

        self.assertEqual(replacements, 0)
        self.assertEqual([item["text"] for item in transcription], ["owned by block two"])
        self.assertEqual(transcription[0]["offsets"], {"from": 59000, "to": 61000})

    def test_completed_checkpoint_rejects_forged_artifact_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entry = {
                "index": 0,
                "status": "done",
                "artifact": "block-9999.json",
                "sha256": "0" * 64,
            }
            with self.assertRaises(long_asr.CheckpointIntegrityError):
                long_asr.validate_done_block(root, entry)

    def test_seam_dedup_keeps_the_more_complete_overlapping_text(self):
        blocks = long_asr.plan_blocks(120.0, 120.0, 60.0, 2.0)
        transcription = [
            {
                "block_index": 0,
                "offsets": {"from": 57000, "to": 59140},
                "text": "宋老師反正從最入門",
            },
            {
                "block_index": 1,
                "offsets": {"from": 58060, "to": 62420},
                "text": "反正从最入门比如说安装Claude Code接入这个模型",
            },
            {
                "block_index": 1,
                "offsets": {"from": 62420, "to": 66000},
                "text": "这是下一句，不应删除",
            },
        ]

        kept, removed = long_asr.deduplicate_block_seams(
            transcription, blocks, overlap_s=2.0
        )

        self.assertEqual(removed, 1)
        self.assertEqual(
            [segment["text"] for segment in kept],
            [
                "反正从最入门比如说安装Claude Code接入这个模型",
                "这是下一句，不应删除",
            ],
        )
        self.assertNotIn("block_index", kept[0])

    def test_owner_loss_stops_the_active_decoder(self):
        with mock.patch.object(long_asr, "owner_is_alive", return_value=False):
            with self.assertRaises(long_asr.OwnerProcessLost):
                long_asr.run_checked(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    timeout=10,
                    label="fixture decoder",
                    owner_pid=424242,
                )


if __name__ == "__main__":
    unittest.main()
