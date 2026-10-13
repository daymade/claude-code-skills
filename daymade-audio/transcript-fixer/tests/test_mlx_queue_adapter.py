"""File-output intake controls; synthetic producer receipts, no model inference."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_queue_audio.py"
spec = importlib.util.spec_from_file_location("mlx_queue_adapter", SCRIPT)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def write_result(clip, root, engine, text="数据员工，这件事", changed=None):
    output = root / (clip.stem + ".txt")
    output.write_text(text, encoding="utf-8")
    manifest = {
        "schema_version": 2, "status": "complete", "source": str(clip.resolve()),
        "source_size": clip.stat().st_size, "source_sha256": adapter.file_sha256(clip),
        "model": "synthetic-model", "model_revision": "a" * 40,
        "execution_device": "Device(gpu, 0)",
        "producer": {"sha256": adapter.file_sha256(engine)},
        "chunk_count": 1, "chunks": [{"status": "done"}],
        "output": str(output.resolve()), "output_sha256": adapter.file_sha256(output),
    }
    manifest.update(changed or {})
    location = root / "_mlx_checkpoints" / (clip.stem + "-synthetic") / "manifest.json"
    location.parent.mkdir(parents=True, exist_ok=True)
    location.write_text(json.dumps(manifest), encoding="utf-8")
    return location


class FileIntakeTests(unittest.TestCase):
    def test_receipt_requires_complete_exact_source_producer_gpu_and_text(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            clip, engine = root / "clip.wav", root / "engine.py"
            clip.write_bytes(b"synthetic source")
            engine.write_text("# synthetic producer\n")
            output = root / "out"
            output.mkdir()
            write_result(clip, output, engine)
            text, provenance = adapter.read_mlx_output(clip, output, engine)
            self.assertEqual(text, "数据员工，这件事")
            self.assertEqual(provenance["model_revision"], "a" * 40)
            changes = [
                {"status": "running"}, {"status": None}, {"source": "other.wav"},
                {"source_sha256": "b" * 64}, {"source_size": 0},
                {"producer": None}, {"producer": {}},
                {"producer": {"sha256": "c" * 64}}, {"model": ""},
                {"model_revision": None}, {"model_revision": ""}, {"model_revision": "main"},
                {"execution_device": "cpu"}, {"execution_device": None},
                {"chunks": []}, {"chunks": [{"status": "pending"}]},
                {"chunk_count": True}, {"chunk_count": 2},
                {"output": "other.txt"}, {"output_sha256": "d" * 64},
            ]
            for changed in changes:
                with self.subTest(changed=changed):
                    write_result(clip, output, engine, changed=changed)
                    with self.assertRaises(ValueError):
                        adapter.read_mlx_output(clip, output, engine)
            manifest = write_result(clip, output, engine)
            for key in ("source_sha256", "model_revision", "execution_device", "producer", "output_sha256"):
                value = json.loads(manifest.read_text())
                del value[key]
                manifest.write_text(json.dumps(value))
                with self.subTest(missing=key), self.assertRaises(ValueError):
                    adapter.read_mlx_output(clip, output, engine)
                manifest = write_result(clip, output, engine)
            for empty in ("", " \n"):
                write_result(clip, output, engine, text=empty)
                with self.assertRaises(ValueError):
                    adapter.read_mlx_output(clip, output, engine)
            manifest = write_result(clip, output, engine)
            (output / "clip.txt").unlink()
            with self.assertRaises(OSError):
                adapter.read_mlx_output(clip, output, engine)
            manifest.unlink()
            with self.assertRaises(ValueError):
                adapter.read_mlx_output(clip, output, engine)

    def test_pair_ignores_progress_logs_and_retains_failure_evidence(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            clips = [root / "tight.wav", root / "medium.wav"]
            for i, clip in enumerate(clips):
                clip.write_bytes(bytes([i]))
            engine = root / "engine.py"
            engine.write_text("# synthetic producer\n")
            def run(command, **kwargs):
                self.assertEqual(command[:3], ["uv", "run", str(engine)])
                self.assertEqual(command[3:5], [str(p) for p in clips])
                self.assertEqual(kwargs["env"]["HF_HUB_OFFLINE"], "1")
                out = Path(command[-1])
                for clip in clips:
                    write_result(clip, out, engine)
                return CompletedProcess(command, 0, "Loading model, 999 progress tokens", "device log")
            with patch.object(adapter.subprocess, "run", side_effect=run):
                outputs = adapter.recognize_mlx_pair(engine, *clips, root)
            self.assertEqual([v[0] for v in outputs], ["数据员工，这件事"] * 2)
            self.assertEqual([v[1] for v in outputs], [0, 0])
            self.assertEqual(len(list(root.glob("mlx-*/stdout.log"))), 1)
            for cp in (CompletedProcess([], 0, "Done: old.txt", ""),
                       CompletedProcess([], 5, "", "bounded generation failed")):
                with patch.object(adapter.subprocess, "run", return_value=cp):
                    failed = adapter.recognize_mlx_pair(engine, *clips, root)
                self.assertTrue(all(value[1] != 0 and value[0] == "" for value in failed))
            self.assertEqual(len(list(root.glob("mlx-*"))), 3)

    def test_actual_mlx_parser_accepts_adapter_argv(self):
        owner = SCRIPT.parents[2] / "asr-transcribe-to-text/scripts/transcribe_local_mlx.py"
        owner_spec = importlib.util.spec_from_file_location("queue_adapter_asr_owner", owner)
        module = importlib.util.module_from_spec(owner_spec)
        owner_spec.loader.exec_module(module)
        parser = module.build_parser()
        parsed = parser.parse_args(["tight.wav", "medium.wav", "--output-dir", "/tmp/unused"])
        module.validate_args(parser, parsed)
        self.assertEqual(parsed.inputs, ["tight.wav", "medium.wav"])
        self.assertEqual(parsed.output_dir, "/tmp/unused")

    def _run_cli(self, changed_at=None):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            target, source, engine = root / "t.md", root / "a.wav", root / "engine.py"
            target.write_text("甲 00:00:00.000\n数据员工，这件事。\n乙 00:00:30.000\n好。\n")
            before = target.read_bytes()
            source.write_bytes(b"synthetic source")
            engine.write_text("# synthetic producer\n")
            times = root / "times.json"
            times.write_text(json.dumps({"1": {"seconds": 10, "anchors": ["这件事"]}}))
            calls = []
            def mutate_source():
                source.write_bytes(b"different source")
            def duration(_):
                if changed_at == "duration":
                    mutate_source()
                return 40
            def run(command, **kwargs):
                calls.append(command)
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(command[-1].encode())
                    return CompletedProcess(command, 0, "", "")
                if command[:2] == ["uv", "run"] and command[2] == str(engine):
                    for clip in command[3:5]:
                        write_result(Path(clip), Path(command[-1]), engine)
                    if changed_at == "recognition":
                        mutate_source()
                    return CompletedProcess(command, 0, "progress", "")
                self.fail(f"unexpected mutation/handoff: {command}")
            original_replace = adapter.os.replace
            def replace(old, new):
                original_replace(old, new)
                if changed_at == "result_write" and str(new).endswith("results.json"):
                    mutate_source()
            argv = [str(SCRIPT), "--transcript", str(target), "--audio", str(source),
                    "--engine-script", str(engine), "--engine-format", "mlx-file",
                    "--time-overrides", str(times), "--outdir", str(root / "out")]
            item = {"id": 1, "line_number": 2, "original_text": "数据员工", "suggested_text": "数字员工"}
            with patch.object(sys, "argv", argv), \
                    patch.object(adapter, "list_pending", return_value=[item]), \
                    patch.object(adapter, "media_duration", side_effect=duration), \
                    patch.object(adapter.subprocess, "run", side_effect=run), \
                    patch.object(adapter.os, "replace", side_effect=replace):
                exit_code = adapter.main()
            result = json.loads((root / "out/results.json").read_text())[0]
            self.assertEqual(exit_code, 1 if changed_at else 0)
            self.assertEqual(result["status"], "engine_failed" if changed_at else "original_supported")
            self.assertEqual(len(result["clip_sha256"]), 2)
            if changed_at:
                self.assertTrue(result["source_identity_error"])
                self.assertNotEqual(result["source_audio_sha256"], adapter.file_sha256(source))
            else:
                self.assertEqual(result["source_audio_sha256"], adapter.file_sha256(source))
            self.assertEqual(target.read_bytes(), before)
            self.assertFalse(any("--resolve-review" in call or "--attach-authority" in call for call in calls))

    def test_cli_retains_original_and_does_not_resolve_queue(self):
        self._run_cli()

    def test_source_change_at_cut_recognition_or_append_boundary_refuses(self):
        for where in ("duration", "recognition", "result_write"):
            with self.subTest(where=where):
                self._run_cli(where)


if __name__ == "__main__":
    unittest.main()
