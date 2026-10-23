#!/usr/bin/env python3
"""Exercise import boundaries and the real CSV → audio → workbench handoff."""

import array
import copy
import csv
import http.client
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave


SCRIPT = Path(__file__).resolve().parents[1] / "prepare_project.py"
SPEC = importlib.util.spec_from_file_location("prepare_audio_review_project", SCRIPT)
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)
SERVER_SPEC = importlib.util.spec_from_file_location("prepared_project_server", SCRIPT.with_name("server.py"))
workbench = importlib.util.module_from_spec(SERVER_SPEC)
SERVER_SPEC.loader.exec_module(workbench)
HAVE_MEDIA_TOOLS = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


class PrepareProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.csv_path = self.root / "turns.csv"
        self.audio_path = self.root / "recording.wav"
        self.output = self.root / "private" / "project.json"
        self.audio_path.write_bytes(b"synthetic-source")
        self.row = {"file": "recording.wav", "start": "0.2", "end": "0.8",
                    "duration": "0.6", "speaker": "候选甲", "text": "合成测试句。"}
        self.write_csv([self.row])
        self.patchers = [
            patch.object(prepare, "_required_tool", side_effect=lambda name: name),
            patch.object(prepare, "_probe_duration", return_value=1.0),
            patch.object(prepare, "_waveform", return_value=[0.0, 0.6, 0.2]),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_csv(self, rows, fields=prepare.CSV_FIELDS):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
        self.csv_path.write_bytes(b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8"))

    def build(self, **options):
        return prepare.build_project(self.csv_path, self.audio_path, **options)

    def test_preserves_text_and_speaker_and_distinguishes_duplicate_occurrences(self):
        original = {**self.row, "speaker": " 候选甲 ", "text": '  原样空格，"引号"，逗号,\r\n第二行\n尾部  '}
        self.write_csv([original, original, {**self.row, "text": "另一句"}])
        project = self.build()
        self.assertEqual([item["text"] for item in project["items"]], [original["text"], original["text"], "另一句"])
        self.assertEqual(project["items"][0]["speaker"], original["speaker"])
        ids = [item["id"] for item in project["items"]]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(ids[0].rsplit("-", 1)[0], ids[1].rsplit("-", 1)[0])
        self.assertTrue(ids[0].endswith("-1"))
        self.assertTrue(ids[1].endswith("-2"))
        self.assertEqual(self.build()["items"], project["items"])

    def test_anonymous_labels_are_unknown_and_only_names_are_candidates(self):
        unknowns = ["Speaker_0", "speaker_012", "Speaker_N", "Speaker A", "说话人1", "说话人N", "unknown", " UNKNOWN ", "待核", "未知", ""]
        self.write_csv([{**self.row, "speaker": label} for label in unknowns + ["候选甲", "候选乙"]])
        project = self.build()
        self.assertEqual([item["identity_status"] for item in project["items"]], ["unknown"] * len(unknowns) + ["candidate", "candidate"])
        self.assertEqual([person["name"] for person in project["people"]], ["候选甲", "候选乙"])
        self.assertNotIn("human_confirmed", json.dumps(project))

    def test_explicit_roster_does_not_assign_or_confirm_identities(self):
        self.write_csv([self.row, {**self.row, "speaker": "Speaker_1"}])
        project = self.build(people=["候选乙", "候选乙", "候选丙"])
        self.assertEqual([person["name"] for person in project["people"]], ["候选乙", "候选丙"])
        self.assertEqual([item["speaker"] for item in project["items"]], ["候选甲", "Speaker_1"])
        self.assertEqual([item["identity_status"] for item in project["items"]], ["candidate", "unknown"])
        self.assertEqual(self.build(people=[])["people"], [])

    def test_project_identity_is_stable_for_content_independent_of_paths_and_presentation(self):
        project = self.build()
        moved_csv = self.root / "copy.csv"
        moved_audio = self.root / "copy.wav"
        moved_csv.write_bytes(self.csv_path.read_bytes())
        moved_audio.write_bytes(self.audio_path.read_bytes())
        moved = prepare.build_project(moved_csv, moved_audio, title="另一个标题", people=["候选乙"])
        self.assertEqual(moved["project_id"], project["project_id"])
        self.assertEqual(moved["items"], project["items"])
        self.audio_path.write_bytes(b"different-synthetic-source")
        self.assertNotEqual(self.build()["project_id"], project["project_id"])
        self.audio_path.write_bytes(b"synthetic-source")
        self.write_csv([{**self.row, "text": "不同原文"}])
        self.assertNotEqual(self.build()["project_id"], project["project_id"])
        self.assertEqual(self.build(project_id="explicit-project")["project_id"], "explicit-project")

    def test_source_clock_and_labels_are_explicit_and_generic(self):
        source = self.build()["sources"][0]
        self.assertEqual(source["id"], "main")
        self.assertEqual(source["clock"], {"offset": 0, "scale": 1})
        self.assertEqual(source["label"], "录音")
        self.assertEqual(source["audio_path"], str(self.audio_path))

    def test_rejects_empty_missing_duplicate_and_incomplete_csv_fields(self):
        bad_inputs = [
            b"", b"file,start,end,duration,speaker,text\n",
            b"file,start,end,speaker,text\na,0,1,x,text\n",
            b"file,start,end,duration,speaker,speaker,text\na,0,1,1,x,x,text\n",
            b"file,start,end,duration,speaker,text\na,0,1,1,x\n",
            b"file,start,end,duration,speaker,text\na,0,1,1,x,text,extra\n",
            b"file,start,end,duration,speaker,text\na,0,1,1,x,\xff\n",
        ]
        for raw in bad_inputs:
            with self.subTest(raw=raw):
                self.csv_path.write_bytes(raw)
                with self.assertRaises(prepare.PrepareError):
                    self.build()

    def test_rejects_multiple_file_values_and_unidentified_source(self):
        for rows in ([self.row, {**self.row, "file": "other.wav"}], [{**self.row, "file": ""}]):
            with self.subTest(rows=rows):
                self.write_csv(rows)
                with self.assertRaises(prepare.PrepareError):
                    self.build()

    def test_nonfinite_and_invalid_intervals_are_rejected(self):
        invalid = [(field, value) for field in ("start", "end", "duration") for value in ("nan", "inf", "-inf", "", "word")]
        invalid += [("start", "-0.01"), ("start", "0.8"), ("start", "0.9"), ("end", "1.101"), ("duration", "0"), ("duration", "-1")]
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                self.write_csv([{**self.row, field: value}])
                with self.assertRaises(prepare.PrepareError):
                    self.build()
        self.write_csv([{**self.row, "end": "1.1"}])
        self.assertEqual(self.build()["items"][0]["end"], 1.1)

    def test_rejects_relative_missing_and_directory_paths(self):
        for csv_path, audio_path in ((Path("turns.csv"), self.audio_path), (self.csv_path, Path("recording.wav")),
                                     (self.root / "absent.csv", self.audio_path), (self.csv_path, self.root / "absent.wav"),
                                     (self.root, self.audio_path), (self.csv_path, self.root)):
            with self.subTest(csv=csv_path, audio=audio_path):
                with self.assertRaises(prepare.PrepareError):
                    prepare.build_project(csv_path, audio_path)
        with self.assertRaisesRegex(prepare.PrepareError, "--output must be an absolute"):
            prepare.prepare_project(self.csv_path, self.audio_path, "project.json")

    def test_empty_options_are_not_silently_defaulted(self):
        for options in ({"title": " "}, {"project_id": ""}, {"project_id": "x\ny"}, {"project_id": "x" * 129}, {"people": [""]}, {"people": ["x\ny"]}):
            with self.subTest(options=options):
                with self.assertRaises(prepare.PrepareError):
                    self.build(**options)

    def test_default_does_not_overwrite_and_overwrite_never_replaces_a_source(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"existing private output")
        with self.assertRaisesRegex(prepare.PrepareError, "already exists"):
            prepare.prepare_project(self.csv_path, self.audio_path, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing private output")
        with patch.object(prepare, "_validate_project") as validator:
            project = prepare.prepare_project(self.csv_path, self.audio_path, self.output, overwrite=True)
            validator.assert_called_once()
        self.assertEqual(json.loads(self.output.read_text()), project)
        self.assertEqual(os.stat(self.output).st_mode & 0o777, 0o600)
        for source in (self.csv_path, self.audio_path):
            before = source.read_bytes()
            with self.assertRaisesRegex(prepare.PrepareError, "separate from"):
                prepare.prepare_project(self.csv_path, self.audio_path, source, overwrite=True)
            self.assertEqual(source.read_bytes(), before)

    def test_output_symlinks_are_not_followed(self):
        target = self.root / "existing.json"
        target.write_text("preserve me")
        link = self.root / "linked.json"
        link.symlink_to(target)
        with self.assertRaisesRegex(prepare.PrepareError, "symbolic link"):
            prepare.prepare_project(self.csv_path, self.audio_path, link, overwrite=True)
        self.assertEqual(target.read_text(), "preserve me")
        link.unlink()
        link.symlink_to(self.root / "absent.json")
        with self.assertRaisesRegex(prepare.PrepareError, "symbolic link"):
            prepare.prepare_project(self.csv_path, self.audio_path, link)

    def test_reader_validation_failure_does_not_publish_partial_output_or_state(self):
        with patch.object(prepare, "_validate_project", side_effect=prepare.PrepareError("invalid project")):
            with self.assertRaisesRegex(prepare.PrepareError, "invalid project"):
                prepare.prepare_project(self.csv_path, self.audio_path, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.iterdir()), [])
        self.assertFalse((self.root / "state.json").exists())

    def test_audio_changed_during_decode_is_rejected(self):
        def changed(*args):
            self.audio_path.write_bytes(b"changed-source-after-hashing")
            return [0.1]
        with patch.object(prepare, "_waveform", side_effect=changed):
            with self.assertRaisesRegex(prepare.PrepareError, "changed during import"):
                self.build()

    def test_missing_media_tools_fail_explicitly(self):
        self.patchers[0].stop()
        available = shutil.which
        for missing in ("ffmpeg", "ffprobe"):
            with self.subTest(missing=missing):
                with patch.object(prepare.shutil, "which", side_effect=lambda name: None if name == missing else available(name) or name):
                    with self.assertRaisesRegex(prepare.PrepareError, f"{missing} is required"):
                        self.build()

    def test_peak_rebinning_keeps_extremes_when_metadata_understates_duration(self):
        collector = prepare._PeakCollector(window_samples=2, max_points=4)
        samples = array.array("h", [0, 0, 100, -200, 300, -400, 500, -600, 700, -800, 900, -1000, 1100])
        collector.feed(samples[:5])
        collector.feed(samples[5:])
        self.assertEqual(collector.sample_count, len(samples))
        peaks = collector.finish()
        self.assertLessEqual(len(peaks), 4)
        self.assertEqual(peaks, [round(value / 32768, 6) for value in (200, 600, 1000, 1100)])


@unittest.skipUnless(HAVE_MEDIA_TOOLS, "ffmpeg and ffprobe are required for the real audio handoff")
class RealMediaImportTests(unittest.TestCase):
    def test_cli_decodes_from_zero_and_project_is_readable_through_the_server(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            audio = root / "source.wav"
            with wave.open(str(audio), "wb") as stream:
                stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                samples = [0 if index < 3200 else int(19660 * math.sin(2 * math.pi * 400 * index / 16000)) for index in range(16000)]
                stream.writeframes(struct.pack("<" + "h" * len(samples), *samples))
            source_csv = root / "source.csv"
            original_text = '  合成,原文"保真"\r\n第二行  '
            with source_csv.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=prepare.CSV_FIELDS)
                writer.writeheader()
                writer.writerow({"file": "source.wav", "start": "0.2", "end": "0.8", "duration": "0.6", "speaker": "候选甲", "text": original_text})
                writer.writerow({"file": "source.wav", "start": "0.8", "end": "1.0", "duration": "0.2", "speaker": "Speaker_1", "text": "未知标签测试"})
            project_path = root / "private" / "project.json"
            state_path = root / "state.json"
            state_path.write_bytes(b"existing-state-is-untouched")
            before_audio, before_csv = audio.read_bytes(), source_csv.read_bytes()
            result = subprocess.run([sys.executable, str(SCRIPT), "--csv", str(source_csv), "--audio", str(audio),
                                     "--output", str(project_path), "--title", "合成录音校勘", "--person", "候选甲", "--person", "候选乙"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("2 transcript items; 2 candidate people", result.stdout)
            self.assertEqual(audio.read_bytes(), before_audio)
            self.assertEqual(source_csv.read_bytes(), before_csv)
            self.assertEqual(state_path.read_bytes(), b"existing-state-is-untouched")
            self.assertFalse((project_path.parent / "state.json").exists())
            data = json.loads(project_path.read_text())
            self.assertEqual(data["items"][0]["text"], original_text)
            self.assertEqual([item["identity_status"] for item in data["items"]], ["candidate", "unknown"])
            peaks = data["sources"][0]["peaks"]
            self.assertEqual(len(peaks), 10)
            self.assertEqual(peaks[:2], [0.0, 0.0])
            self.assertGreater(min(peaks[2:]), 0.55)
            self.assertAlmostEqual(data["sources"][0]["duration"], 1.0, places=3)
            project = workbench.Project(project_path)
            server = workbench.WorkbenchServer(("127.0.0.1", 0), project, None)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                connection.request("GET", "/api/project")
                response = connection.getresponse()
                public = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(public["items"][0]["text"], original_text)
                self.assertEqual(public["sources"][0]["media_url"], "/media/main?project_fingerprint=" + public["fingerprint"])
                self.assertNotIn(str(root), json.dumps(public))
                connection.request("GET", public["sources"][0]["media_url"], headers={"Range": "bytes=0-15"})
                response = connection.getresponse()
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), before_audio[:16])
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_unreadable_audio_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            audio = root / "bad.wav"
            audio.write_bytes(b"not a media file")
            source_csv = root / "turns.csv"
            source_csv.write_text("file,start,end,duration,speaker,text\nbad.wav,0,1,1,Speaker_1,synthetic text\n")
            output = root / "project.json"
            result = subprocess.run([sys.executable, str(SCRIPT), "--csv", str(source_csv), "--audio", str(audio), "--output", str(output)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 2)
            self.assertIn("ffprobe", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
