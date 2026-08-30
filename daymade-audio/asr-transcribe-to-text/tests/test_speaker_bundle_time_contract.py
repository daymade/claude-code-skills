import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"


def load_module(name):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_contract_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


align = load_module("align_speakers")
fusion = load_module("fuse_whispercpp_diarization")
speaker = load_module("speaker_transcribe")


def csv_contract(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    contract = [
        {field: row.get(field) for field in fusion.CSV_FIELDS}
        for row in rows
    ]
    digest = hashlib.sha256(
        json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return rows, digest


class SpeakerBundleTimeContractTests(unittest.TestCase):
    def test_qwen_and_fusion_emit_the_same_half_millisecond_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.wav"
            source.write_bytes(b"synthetic wav bytes")
            qwen_dir = root / "qwen"
            fusion_dir = root / "fusion"
            qwen_dir.mkdir()
            fusion_dir.mkdir()

            _chars, lattice = align.whisper_char_lattice([
                {"word": "甲", "start": 59.997, "end": 60.0},
            ])
            qwen_turns = align.build_turns(
                "甲", [0], lattice, ["SPEAKER_00"], max_gap=2.0
            )
            report = {
                "trustworthy": True,
                "anchored_ratio": 1.0,
                "num_turns": 1,
                "speakers": ["SPEAKER_00"],
            }
            align.write_outputs(
                qwen_turns,
                report,
                source.name,
                qwen_dir,
                "fixture",
            )
            (qwen_dir / "fixture.diarization.json").write_text(
                json.dumps({
                    "segments": [
                        {
                            "start": 59.9,
                            "end": 60.1,
                            "speaker": "SPEAKER_00",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            speaker._stamp_alignment_source(
                source,
                qwen_dir,
                "fixture",
                speaker._source_audio_identity(source),
            )

            fusion_turns = fusion.canonicalize_turns([
                {
                    "start": 59.9985,
                    "end": 59.9995,
                    "speaker": "SPEAKER_00",
                    "text": "甲",
                }
            ])
            (fusion_dir / "fixture.txt").write_text(
                fusion.render_txt(source.name, fusion_turns),
                encoding="utf-8",
            )
            (fusion_dir / "fixture.csv").write_text(
                fusion.render_csv(source.name, fusion_turns),
                encoding="utf-8",
            )

            qwen_rows, qwen_hash = csv_contract(qwen_dir / "fixture.csv")
            fusion_rows, fusion_hash = csv_contract(fusion_dir / "fixture.csv")
            qwen_alignment = json.loads(
                (qwen_dir / "fixture.alignment.json").read_text(encoding="utf-8")
            )

            self.assertEqual(qwen_rows, fusion_rows)
            self.assertEqual(
                (qwen_rows[0]["start"], qwen_rows[0]["end"], qwen_rows[0]["duration"]),
                ("59.999", "60.0", "0.001"),
            )
            self.assertIn(
                "[00:59.999 - 01:00.000] SPEAKER_00",
                (qwen_dir / "fixture.txt").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "[00:59.999 - 01:00.000] SPEAKER_00",
                (fusion_dir / "fixture.txt").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                qwen_alignment["turn_contract"]["sha256"],
                qwen_hash,
            )
            self.assertEqual(
                fusion.csv_turn_contract_sha256(fusion_turns, source.name),
                fusion_hash,
            )
            self.assertEqual(
                speaker._validation_contract(),
                {"speaker_edge_tolerance_s": 1.0},
            )
            self.assertEqual(
                fusion.SPEAKER_VALIDATION_CONTRACT,
                {"speaker_edge_tolerance_s": 0.0},
            )


if __name__ == "__main__":
    unittest.main()
