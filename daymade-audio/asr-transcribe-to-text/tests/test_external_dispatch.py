"""Exercise actual producer entry points without running audio inference."""
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1]
SUITE = SKILL.parent
MODULE_PATH = SKILL / "scripts/external_dispatch.py"
spec = importlib.util.spec_from_file_location("audio_dispatch_under_test", MODULE_PATH)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="audio dispatch test ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.profile = self.root / "profile.json"
        self.capture = self.root / "captured.json"
        self.dispatcher = self.root / "fake dispatcher.py"
        self.dispatcher.write_text(
            "import json, os, stat, sys\nfrom pathlib import Path\n"
            "path=Path(sys.argv[sys.argv.index('--request')+1])\n"
            "request=json.loads(path.read_text())\n"
            "request['_permissions']=stat.S_IMODE(path.stat().st_mode)\n"
            "request['_request_path']=str(path)\n"
            "Path(os.environ['AUDIO_CAPTURE']).write_text(json.dumps(request))\n"
            "path.unlink()\n"
            "sys.stdout.write('dispatcher stdout\\n')\n"
            "sys.stderr.write('dispatcher stderr\\n')\n"
            "sys.exit(23)\n", encoding="utf-8")
        # The protocol smoke never performs NumPy work. The original voiceprint
        # producer imports this declared inference dependency before parsing CLI
        # flags; isolate it explicitly so the registered suite stays stdlib-only.
        self.model_stubs = self.root / "protocol-only-model-stubs"
        self.model_stubs.mkdir()
        (self.model_stubs / "numpy.py").write_text(
            "def __getattr__(name):\n"
            " raise AssertionError('NumPy computation forbidden in protocol smoke: '+name)\n")
        self.profile.write_text(json.dumps({"external_dispatch": {
            "protocol": 1, "argv": [sys.executable, str(self.dispatcher)]}}))

    def environment(self):
        env = {**os.environ, "DAYMADE_AUDIO_CONFIG": str(self.profile),
               "AUDIO_CAPTURE": str(self.capture), "HOME": str(self.root),
               "XDG_CONFIG_HOME": str(self.root / "config"), "TMPDIR": str(self.root),
               "TRANSCRIPT_FIXER_CONFIG_DIR": str(self.root / "fixer"),
               "CLAUDE_PLUGIN_DATA": str(self.root / "plugin-data"), "HF_HOME": str(self.root / "huggingface"),
               "PYTHONPATH": str(self.model_stubs)}
        env.pop(bridge.BYPASS, None)
        env.pop(bridge.NONCE, None)
        env.pop("STEPFUN_API_KEY", None)
        env.pop("STEPFUN_PLAN_TOKEN", None)
        for key in ("HF_TOKEN", "HF_HUB_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
            env.pop(key, None)
        return env

    def test_protocol_numpy_stub_refuses_computation(self):
        result = subprocess.run([sys.executable, "-c", "import numpy as np; np.asarray([1])"],
                                env=self.environment(), capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NumPy computation forbidden in protocol smoke: asarray", result.stderr)

    def test_both_independently_installable_skills_ship_the_same_module(self):
        for skill in ("transcript-fixer", "stepfun-asr", "stepfun-tts"):
            other = SUITE / skill / "scripts/external_dispatch.py"
            self.assertEqual(MODULE_PATH.read_bytes(), other.read_bytes())

    def test_five_real_cli_entries_reach_dispatch_with_original_arguments(self):
        source = self.root / "sample call.wav"
        source.write_bytes(b"synthetic fixture; never decoded")
        text = self.root / "input notes.md"
        text.write_text("Synthetic original transcript\n")
        out = self.root / "result files"
        fixtures = [
            ("asr.speaker", SKILL / "scripts/speaker_transcribe.py",
             [str(source), str(out), "--no-diarization"], source),
            ("asr.mlx", SKILL / "scripts/transcribe_local_mlx.py",
             [str(source), "--output-dir", str(out)], source),
            ("asr.long", SKILL / "scripts/transcribe_long_whispercpp.py",
             [str(source), str(out), *sum(([flag, str(self.root / flag[2:])] for flag in
              ("--ffmpeg-path", "--whisper-bin", "--gpu-runtime-manifest", "--whisper-model", "--vad-model")), [])], source),
            ("asr.remote", SKILL / "scripts/transcribe_remote.py",
             [str(source), str(out / "remote.txt"), "--config", str(self.root / "remote.json")], source),
            ("transcript.correct", SUITE / "transcript-fixer/scripts/fix_transcription.py",
             ["--input", str(text), "--stage", "1", "--output", str(out), "--json"], text),
        ]
        for producer, script, argv, original in fixtures:
            with self.subTest(producer=producer):
                before = original.read_bytes()
                result = subprocess.run([sys.executable, str(script), *argv], cwd=self.root,
                                        env=self.environment(), capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 23, result.stderr)
                self.assertEqual(result.stdout, "dispatcher stdout\n")
                self.assertEqual(result.stderr, "dispatcher stderr\n")
                request = json.loads(self.capture.read_text())
                self.assertEqual(request["protocol"], 1)
                self.assertEqual(request["producer_id"], producer)
                self.assertEqual(request["argv"], argv)
                self.assertEqual(request["script"], str(script.resolve()))
                self.assertEqual(request["executable"], sys.executable)
                self.assertEqual(request["cwd"], str(self.root))
                self.assertEqual(request["_permissions"], 0o600)
                self.assertFalse(Path(request["_request_path"]).exists())
                self.assertTrue(request["nonce"])
                self.assertEqual(request["inputs"][0]["path"], str(original))
                self.assertGreater(len(request["outputs"]), 0)
                self.assertTrue(all(set(item) == {"path", "kind", "role"}
                                    for item in request["inputs"] + request["outputs"]))
                self.assertEqual(original.read_bytes(), before)
                self.assertFalse(out.exists(), "producer ran instead of dispatcher")

    def test_unconfigured_users_keep_standalone_execution(self):
        with patch.dict(os.environ, {"HOME": str(self.root)}, clear=True), patch.object(bridge.os, "execvpe") as execute:
            bridge.dispatch_cli("not-a-producer", __file__, Namespace())
            execute.assert_not_called()

    def test_new_inference_entries_use_the_same_dispatch_without_loading_models_or_credentials(self):
        source, output = self.root / "source.wav", self.root / "results"
        source.write_bytes(b"synthetic audio; must not be decoded")
        fixtures = [
            ("asr.diarize", SKILL / "scripts/diarize_speakers.py", [str(source), str(output / "diar.json")]),
            ("voiceprint.match", SKILL / "scripts/voiceprint_id.py", ["match", "--refs", str(self.root / "refs.json"),
             "--audio", str(source), "--diar", str(self.root / "diar.json"), "--csv", str(output / "speaker.csv")]),
            ("voiceprint.enroll", SKILL / "scripts/voiceprint_id.py", ["enroll", "--refs", str(self.root / "refs.json"),
             "--audio", str(source), "--name", "Synthetic Person", "--spans", "0-2"]),
            ("asr.stepfun_sse", SUITE / "stepfun-asr/scripts/asr_transcribe.py", [str(source), "--json", "--key-env", "STEPFUN_PLAN_TOKEN"]),
            ("asr.stepfun_file", SUITE / "stepfun-asr/scripts/asr_file.py", ["https://audio.example.test/clip.mp3", "--json"]),
            ("tts.stepfun", SUITE / "stepfun-tts/scripts/tts_generate.py", ["--text", "Synthetic (softly) voice 原文", "--voice", "voice-fixture", "--out", str(output / "take.wav")]),
        ]
        for producer, script, argv in fixtures:
            with self.subTest(producer=producer):
                result = subprocess.run([sys.executable, str(script), *argv], cwd=self.root, env=self.environment(),
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 23, result.stderr)
                self.assertEqual(result.stdout, "dispatcher stdout\n")
                self.assertEqual(result.stderr, "dispatcher stderr\n")
                request = json.loads(self.capture.read_text())
                self.assertEqual(request["producer_id"], producer)
                self.assertEqual(request["argv"], argv)
                if producer == "asr.stepfun_file":
                    self.assertEqual(request["inputs"][0]["uri"], argv[0])
                    self.assertNotIn("path", request["inputs"][0])
                elif producer == "tts.stepfun":
                    self.assertEqual(request["inputs"][0]["text"], argv[1])
                    self.assertTrue(any(item["path"].endswith("take.wav.response.json") for item in request["outputs"]))
                else:
                    self.assertEqual(request["inputs"][0]["path"], str(source))
                if producer in {"asr.stepfun_sse", "asr.stepfun_file"}:
                    self.assertEqual(request["stdout"], {"kind": "transcript", "role": "raw_transcript"})
                if producer == "voiceprint.match":
                    self.assertEqual(request["stdout"]["role"], "raw_voiceprint_candidate_mapping")
                    self.assertEqual(request["stdout"]["kind"], "context")
                self.assertFalse(output.exists())
        self.assertEqual(source.read_bytes(), b"synthetic audio; must not be decoded")

    def test_tts_batch_keeps_row_formats_records_and_later_invalid_row_order(self):
        batch = self.root / "batch.jsonl"
        batch.write_text(json.dumps({"id": "first", "text": "one", "response_format": "wav"}) + "\n" +
                         json.dumps({"id": "second", "request": {"model": "stepaudio-3-tts", "input": "two", "voice": "voice-fixture", "response_format": "ogg"}}) +
                         "\nnot valid JSON\n")
        output = self.root / "batch output"
        script = SUITE / "stepfun-tts/scripts/tts_generate.py"
        result = subprocess.run([sys.executable, str(script), "--batch", str(batch), "--out-dir", str(output)],
                                cwd=self.root, env=self.environment(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 23, result.stderr)
        request = json.loads(self.capture.read_text())
        names = {Path(item["path"]).name for item in request["outputs"]}
        self.assertIn("first.wav", names)
        self.assertIn("second.ogg", names)
        self.assertIn("first.wav.response.json", names)
        self.assertIn("second.ogg.response-body", names)
        self.assertFalse(output.exists())

    def test_tts_dry_run_does_not_dispatch_or_generate_audio(self):
        script = SUITE / "stepfun-tts/scripts/tts_generate.py"
        result = subprocess.run([sys.executable, str(script), "--text", "原文 (softly)", "--dry-run"],
                                cwd=self.root, env=self.environment(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("原文", json.loads(result.stdout)["input"])
        self.assertFalse(self.capture.exists())

    def test_missing_or_empty_or_malformed_configured_dispatch_never_falls_back(self):
        cases = [[], {"external_dispatch": None}, {"external_dispatch": {}},
                 {"external_dispatch": {"protocol": True, "argv": ["tool"]}},
                 {"external_dispatch": {"protocol": 1, "argv": []}},
                 {"external_dispatch": {"protocol": 1, "argv": [""]}}]
        for value in cases:
            with self.subTest(value=value):
                self.profile.write_text(json.dumps(value))
                with patch.dict(os.environ, self.environment(), clear=True), self.assertRaises(SystemExit) as error:
                    bridge.dispatch_cli("asr.mlx", __file__, Namespace())
                self.assertEqual(error.exception.code, 78)
        self.profile.unlink()
        with patch.dict(os.environ, self.environment(), clear=True), self.assertRaises(SystemExit):
            bridge.dispatch_cli("asr.mlx", __file__, Namespace())

    def test_missing_dispatch_executable_reports_failure_without_running_the_engine(self):
        self.profile.write_text(json.dumps({"external_dispatch": {
            "protocol": 1, "argv": [str(self.root / "missing executable")]}}))
        script = SKILL / "scripts/transcribe_remote.py"
        result = subprocess.run([sys.executable, str(script), "source.wav", "out.txt", "--config", "remote.json"],
                                cwd=self.root, env=self.environment(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 78)
        self.assertIn("producer was not run", result.stderr)
        self.assertFalse((self.root / "out.txt").exists())
        self.assertEqual(list(self.root.glob("daymade-audio-dispatch-*.json")), [])

    def test_matching_bypass_is_consumed_once_and_not_inherited_by_child_producers(self):
        script = str(Path(__file__).resolve())
        env = {**self.environment(), bridge.NONCE: "fresh-nonce", bridge.BYPASS: json.dumps({
            "producer_id": "asr.mlx", "script": script, "nonce": "fresh-nonce"})}
        with patch.dict(os.environ, env, clear=True), patch.object(bridge.os, "execvpe") as execute:
            bridge.dispatch_cli("asr.mlx", script, Namespace())
            execute.assert_not_called()
            self.assertNotIn(bridge.BYPASS, os.environ)
            self.assertNotIn(bridge.NONCE, os.environ)
            args = Namespace(inputs=["source.wav"], output_dir="out")
            bridge.dispatch_cli("asr.mlx", script, args)
            execute.assert_called_once()
            request_path = Path(execute.call_args.args[1][-1])
            self.addCleanup(request_path.unlink, missing_ok=True)

    def test_cross_producer_cross_script_or_stale_nonce_bypass_is_rejected(self):
        script = str(Path(__file__).resolve())
        for field, wrong in (("producer_id", "asr.other"), ("script", script + "other"), ("nonce", "stale")):
            token = {"producer_id": "asr.mlx", "script": script, "nonce": "fresh"}
            token[field] = wrong
            env = {**self.environment(), bridge.BYPASS: json.dumps(token), bridge.NONCE: "fresh"}
            with self.subTest(field=field), patch.dict(os.environ, env, clear=True), self.assertRaises(SystemExit):
                bridge.dispatch_cli("asr.mlx", script, Namespace())

    def test_help_and_dictionary_management_do_not_dispatch(self):
        script = SUITE / "transcript-fixer/scripts/fix_transcription.py"
        for argv in (["--help"], ["--list", "--json"]):
            result = subprocess.run([sys.executable, str(script), *argv], env=self.environment(),
                                    cwd=self.root, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 23)
            self.assertFalse(self.capture.exists())

    @unittest.skipUnless(os.name == "posix", "POSIX exec signal semantics")
    def test_exec_preserves_sigint_delivery_to_the_dispatcher(self):
        self.dispatcher.write_text(
            "import os, signal, sys, time\n"
            "signal.signal(signal.SIGINT, signal.SIG_DFL)\n"
            "print('dispatcher ready', flush=True)\n"
            "time.sleep(30)\n")
        script = SKILL / "scripts/transcribe_remote.py"
        process = subprocess.Popen([sys.executable, str(script), "source.wav", "out.txt", "--config", "remote.json"],
                                   env=self.environment(), cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        self.assertEqual(process.stdout.readline(), "dispatcher ready\n")
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, -signal.SIGINT)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main()
