import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "align_speakers.py"


def load_module():
    spec = importlib.util.spec_from_file_location("align_speakers_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PositiveTurnDurationTests(unittest.TestCase):
    def setUp(self):
        self.align = load_module()

    def test_single_character_turns_use_only_the_minimum_tick(self):
        raw = "甲乙"
        _chars, raw_idx = self.align.normalize_stream(raw)

        turns = self.align.build_turns(
            raw,
            raw_idx,
            [14.6, 14.8],
            ["SPEAKER_00", "SPEAKER_01"],
            max_gap=2.0,
        )

        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["start"], 14.6)
        self.assertEqual(turns[0]["end"], 14.601)
        self.assertEqual(turns[0]["duration"], 0.001)
        self.assertEqual(turns[1]["start"], 14.8)
        self.assertEqual(turns[1]["end"], 14.801)
        self.assertEqual(turns[1]["duration"], 0.001)
        for turn in turns:
            self.assertGreater(turn["end"], turn["start"])
            self.assertEqual(
                turn["duration"], round(turn["end"] - turn["start"], 3)
            )

    def test_long_gap_does_not_expand_previous_turn_across_silence(self):
        raw = "甲乙"
        _chars, raw_idx = self.align.normalize_stream(raw)

        turns = self.align.build_turns(
            raw,
            raw_idx,
            [10.0, 30.0],
            ["SPEAKER_00", "SPEAKER_00"],
            max_gap=2.0,
        )

        self.assertEqual(turns[0]["start"], 10.0)
        self.assertEqual(turns[0]["end"], 10.001)
        self.assertEqual(turns[0]["duration"], 0.001)

    def test_long_gap_and_speaker_change_preserve_both_turns(self):
        raw = "甲乙"
        _chars, raw_idx = self.align.normalize_stream(raw)

        turns = self.align.build_turns(
            raw,
            raw_idx,
            [10.0, 30.0],
            ["SPEAKER_00", "SPEAKER_01"],
            max_gap=2.0,
        )

        self.assertEqual(
            [(turn["speaker"], turn["text"]) for turn in turns],
            [("SPEAKER_00", "甲"), ("SPEAKER_01", "乙")],
        )
        self.assertEqual(turns[0]["end"], 10.001)
        self.assertEqual(turns[1]["start"], 30.0)
        self.assertLess(
            self.align.fmt(turns[0]["end"]),
            self.align.fmt(turns[1]["start"]),
        )

    def test_repeated_lattice_times_still_produce_positive_turns(self):
        raw = "甲乙"
        _chars, raw_idx = self.align.normalize_stream(raw)
        turns = self.align.build_turns(
            raw,
            raw_idx,
            [14.8, 14.8],
            ["SPEAKER_00", "SPEAKER_01"],
            max_gap=2.0,
        )
        self.assertTrue(all(turn["duration"] == 0.001 for turn in turns))

    def test_turn_fields_and_formatter_share_half_up_millisecond_rounding(self):
        raw = "甲乙"
        _chars, raw_idx = self.align.normalize_stream(raw)
        turns = self.align.build_turns(
            raw,
            raw_idx,
            [59.9985, 60.0005],
            ["SPEAKER_00", "SPEAKER_01"],
            max_gap=2.0,
        )

        self.assertEqual(turns[0]["start"], 59.999)
        self.assertEqual(turns[0]["end"], 60.0)
        self.assertEqual(turns[1]["start"], 60.001)
        self.assertEqual(turns[1]["end"], 60.002)
        self.assertEqual(self.align.fmt(turns[0]["start"]), "00:59.999")
        self.assertEqual(self.align.fmt(turns[1]["start"]), "01:00.001")

    def test_word_lattice_uses_half_up_before_building_turns(self):
        chars, times = self.align.whisper_char_lattice([
            {"word": "甲", "start": 59.997, "end": 60.0},
        ])
        turns = self.align.build_turns(
            "甲",
            [0],
            times,
            ["SPEAKER_00"],
            max_gap=2.0,
        )

        self.assertEqual(chars, ["甲"])
        self.assertEqual(times, [59.999])
        self.assertEqual(turns[0]["start"], 59.999)
        self.assertEqual(turns[0]["end"], 60.0)
        self.assertEqual(self.align.fmt(turns[0]["start"]), "00:59.999")

    def test_interpolated_anchor_uses_half_up_before_turn_building(self):
        times, ratio = self.align.assign_times(
            ["甲", "乙", "丙"],
            [59.997, 60.0],
            [(0, 0), (2, 1)],
        )
        turns = self.align.build_turns(
            "甲乙丙",
            [0, 1, 2],
            times,
            ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"],
            max_gap=2.0,
        )

        self.assertEqual(ratio, 0.6667)
        self.assertEqual(times, [59.997, 59.999, 60.0])
        self.assertEqual(turns[1]["start"], 59.999)
        self.assertEqual(turns[1]["end"], 60.0)
        self.assertEqual(turns[1]["text"], "乙")
        self.assertEqual(turns[1]["speaker"], "SPEAKER_01")

    def test_formatter_preserves_the_minimum_millisecond_tick(self):
        self.assertEqual(self.align.fmt(14.8), "00:14.800")
        self.assertEqual(self.align.fmt(14.801), "00:14.801")
        self.assertEqual(self.align.fmt(59.9985), "00:59.999")
        self.assertEqual(self.align.fmt(59.9995), "01:00.000")
        self.assertEqual(self.align.fmt(60.0005), "01:00.001")
        self.assertEqual(self.align.fmt(125.6786), "02:05.679")


if __name__ == "__main__":
    unittest.main()
