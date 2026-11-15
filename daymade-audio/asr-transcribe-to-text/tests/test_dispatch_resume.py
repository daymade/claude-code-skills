"""Pinned dispatch-only migration preserves completed native ASR work."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
import dispatch_compat as compat
import speaker_transcribe as speaker
import transcribe_local_mlx as mlx
import transcribe_long_whispercpp as long_asr


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class DispatchResumeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.wav = self.root / "synthetic.wav"
        self.wav.write_bytes(b"Synthetic input; never decoded or sent to any model")
        self.transitions = json.loads((SCRIPTS / "dispatch_compatibility.json").read_text())["transitions"]

    def test_only_exact_reviewed_entry_bytes_allow_old_producer(self):
        name = "transcribe_local_mlx.py"
        previous = self.transitions[name]["previous_sha256"]
        self.assertEqual(compat.old_hash(SCRIPTS / name), previous)
        source = self.root / name
        source.write_bytes((SCRIPTS / name).read_bytes())
        shutil.copyfile(SCRIPTS / "dispatch_compatibility.json", self.root / "dispatch_compatibility.json")
        source.write_bytes(source.read_bytes() + b"\n# unreviewed producer change\n")
        self.assertIsNone(compat.old_hash(source))
        self.assertFalse(compat.producer_matches({"script": name, "sha256": previous},
                                               {"script": name, "sha256": sha(source)}, source))
        self.assertFalse(compat.pipeline_matches({name: None}, {name: sha(source)}, self.root))

    def test_leg_cache_keeps_source_parameter_and_artifact_checks(self):
        artifact = self.root / "synthetic.qwen.txt"
        artifact.write_text("Synthetic transcript\n")
        contract = speaker._cache_contract(self.wav, "transcribe_local_mlx.py", {"language": "Chinese"})
        contract["producer"]["sha256"] = self.transitions["transcribe_local_mlx.py"]["previous_sha256"]
        speaker._write_artifact_provenance(artifact, contract)
        provenance = speaker._artifact_provenance_path(artifact)
        before = provenance.read_bytes()
        self.assertTrue(speaker._artifact_cache_valid(self.wav, artifact, "transcribe_local_mlx.py", {"language": "Chinese"}))
        self.assertFalse(speaker._artifact_cache_valid(self.wav, artifact, "transcribe_local_mlx.py", {"language": "English"}))
        artifact.write_text("Changed cached result\n")
        self.assertFalse(speaker._artifact_cache_valid(self.wav, artifact, "transcribe_local_mlx.py", {"language": "Chinese"}))
        artifact.write_text("Synthetic transcript\n")
        self.wav.write_bytes(b"Different input bytes")
        self.assertFalse(speaker._artifact_cache_valid(self.wav, artifact, "transcribe_local_mlx.py", {"language": "Chinese"}))
        self.assertEqual(provenance.read_bytes(), before)

    def test_complete_mlx_checkpoint_resumes_without_generate_or_old_manifest_write(self):
        identity, digest = mlx._checkpoint_identity(self.wav, "synthetic/model", "a" * 40, "Chinese",
                                                    1200.0, 8192, 16000, {"fixture": "1"}, execution_device="fixture-gpu")
        old = copy.deepcopy(identity)
        old["producer"]["sha256"] = self.transitions["transcribe_local_mlx.py"]["previous_sha256"]
        old_digest = mlx._sha256_text(json.dumps(old, ensure_ascii=False, sort_keys=True))
        root = self.root / "checkpoints"
        old_dir = root / f"synthetic-{old_digest[:16]}"
        output = self.root / "synthetic.txt"
        model = Mock()
        model.generate.return_value = argparse.Namespace(text="Synthetic reusable transcript", generation_tokens=3)
        mlx.transcribe_chunks(model, [(None, 0)], output, old_dir, old, 8192, "Chinese", 1200)
        manifest = old_dir / "manifest.json"
        before = manifest.read_bytes()
        model.generate.reset_mock()
        text, reused = mlx.transcribe_chunks(model, [(None, 0)], output, root / f"synthetic-{digest[:16]}",
                                             identity, 8192, "Chinese", 1200)
        self.assertEqual(text, "Synthetic reusable transcript")
        model.generate.assert_not_called()
        self.assertEqual(manifest.read_bytes(), before)
        record = json.loads(manifest.with_name("manifest.json.dispatch-reuse.json").read_text())
        self.assertEqual(record["entrypoints"]["transcribe_local_mlx.py"], sha(SCRIPTS / "transcribe_local_mlx.py"))
        self.assertEqual(reused["producer"]["sha256"], old["producer"]["sha256"])
        for field, value in (("language", "English"), ("model_revision", "b" * 40), ("source_sha256", "0" * 64),
                             ("producer", {**identity["producer"], "sha256": "f" * 64})):
            changed = {**identity, field: value}
            self.assertIsNone(compat.previous_checkpoint(root, "synthetic", changed,
                lambda v: mlx._sha256_text(json.dumps(v, ensure_ascii=False, sort_keys=True)), SCRIPTS / "transcribe_local_mlx.py"))
        payload = json.loads(before); payload["status"] = "running"; manifest.write_text(json.dumps(payload))
        self.assertIsNone(compat.previous_checkpoint(root, "synthetic", identity,
            lambda v: mlx._sha256_text(json.dumps(v, ensure_ascii=False, sort_keys=True)), SCRIPTS / "transcribe_local_mlx.py"))

    def test_long_cli_reuses_complete_checkpoint_without_decoding_and_preserves_receipt(self):
        with wave.open(str(self.wav), "wb") as handle:
            handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * 16000)
        out = self.root / "long-out"
        out.mkdir()
        marker = self.root / "decoder-calls"
        binary = self.root / "fixture-whisper"
        gpu = {"schema": long_asr.GPU_SCHEMA, "upstream_commit": long_asr.GPU_UPSTREAM_COMMIT, "version": "1.9.1"}
        binary.write_text("#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
                          f"p=Path({str(marker)!r})\n"
                          "if sys.argv[1:]==['--asr-gpu-contract']:\n"
                          " p.write_text(p.read_text()+'policy\\n' if p.exists() else 'policy\\n')\n"
                          f" print({json.dumps(gpu)!r})\n"
                          "else:\n raise AssertionError('Model decoding forbidden in completed-cache probe')\n")
        binary.chmod(0o700)
        assets = {}
        for name in ("ffmpeg", "whisper-model", "vad-model"):
            path = self.root / name; path.write_bytes(b"synthetic-runtime-asset")
            assets[name] = path
        gpu_manifest = self.root / "gpu.json"
        gpu_manifest.write_text(json.dumps({"contract": gpu, "patch_sha256": sha(long_asr.GPU_PATCH),
                                           "binaries": {"whisper-cli": long_asr.file_contract(binary)}}))
        runtime = {"ffmpeg": long_asr.file_contract(assets["ffmpeg"]), "whisper_bin": long_asr.file_contract(binary),
                   "whisper_model": long_asr.file_contract(assets["whisper-model"]), "vad_model": long_asr.file_contract(assets["vad-model"]),
                   "gpu_runtime": {"contract": gpu, "patch_sha256": sha(long_asr.GPU_PATCH), "manifest": long_asr.file_contract(gpu_manifest)}}
        args = argparse.Namespace(chunk_duration=1200.0, overlap=2.0, language="zh", prompt="以下是简体中文普通话:",
                                  vad_threshold=0.5, vad_min_speech_ms=250, vad_min_silence_ms=500,
                                  vad_max_speech_s=30.0, vad_speech_pad_ms=200, vad_overlap=0.25)
        source = long_asr.wav_contract(self.wav)
        old = long_asr.checkpoint_identity(args, source, runtime, 1.0)
        old["producer"]["sha256"] = self.transitions["transcribe_long_whispercpp.py"]["previous_sha256"]
        directory = out / "_whispercpp_checkpoints" / ("synthetic-" + long_asr.manifest_digest(old)[:16])
        directory.mkdir(parents=True)
        blocks = long_asr.plan_blocks(1.0, 1.0, 1200.0, 2.0)
        entry = blocks[0]
        payload = {**entry, "schema": long_asr.SCHEMA, "transcription": [], "utf8_replacement_count": 0,
                   "gpu_execution": {"vad": {"device": "synthetic-fixture-gpu", "compute_nodes": 1, "cpu_compute": 0}}}
        artifact = directory / "block-0000.json"; artifact.write_text(json.dumps(payload))
        entry.update(status="done", artifact=artifact.name, sha256=sha(artifact), utf8_replacement_count=0, segment_count=0)
        outputs = {}
        for kind, data in (("json", "{}\n"), ("txt", "\n")):
            path = out / f"synthetic.whispercpp.{kind}"; path.write_text(data)
            outputs[kind] = {"file": path.name, "sha256": sha(path)}
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps({**old, "status": "complete", "block_count": 1, "blocks": blocks, "outputs": outputs}))
        receipt = out / "synthetic.whispercpp.receipt.json"
        receipt.write_text(json.dumps({"schema": long_asr.SCHEMA + "-receipt", "source_audio": source,
                                      "checkpoint_manifest": {"path": str(manifest), "sha256": sha(manifest)}, "outputs": outputs}))
        before = {p: p.read_bytes() for p in (manifest, receipt, artifact)}
        profile = self.root / "unconfigured.json"; profile.write_text("{}")
        command = ["uv", "run", "--no-project", "python", str(SCRIPTS / "transcribe_long_whispercpp.py"),
                   str(self.wav), str(out), "--ffmpeg-path", str(assets["ffmpeg"]), "--whisper-bin", str(binary),
                   "--gpu-runtime-manifest", str(gpu_manifest), "--whisper-model", str(assets["whisper-model"]),
                   "--vad-model", str(assets["vad-model"])]
        env = {**os.environ, "HOME": str(self.root), "DAYMADE_AUDIO_CONFIG": str(profile)}
        for key in ("DAYMADE_AUDIO_DISPATCH_BYPASS", "DAYMADE_AUDIO_DISPATCH_NONCE"):
            env.pop(key, None)
        result = subprocess.run(command, env=env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"Complete checkpoint reused; no audio inference", result.stderr)
        self.assertEqual(marker.read_text(), "policy\n")
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertTrue(receipt.with_name(receipt.name + ".dispatch-reuse.json").exists())

    def make_bundle(self):
        out = self.root / "output"
        out.mkdir()
        decoder = self.root / "fixture-ffmpeg"
        decoder.write_text("#!/bin/sh\nprintf 'ffmpeg synthetic-fixture-v1\\n'\n")
        decoder.chmod(0o700)
        from diarize_speakers import ffmpeg_contract
        contract = ffmpeg_contract(decoder)
        (out / "synthetic.txt").write_text("[00:00.000 - 00:01.000] SPEAKER_00\nSynthetic words\n")
        (out / "synthetic.csv").write_text("file,start,end,duration,speaker,text\nsynthetic.wav,0,1,1,SPEAKER_00,Synthetic words\n")
        (out / "synthetic.diarization.json").write_text(json.dumps({"segments": [{"start": 0, "end": 1, "speaker": "SPEAKER_00"}]}))
        (out / "synthetic.alignment.json").write_text(json.dumps({"report": {"trustworthy": True, "anchored_ratio": 1.0}}))
        # Full baseline writer is used in the separate immutable-f9 probe. Here
        # the public regression needs no historical Git objects in a shallow CI.
        pipeline = speaker._pipeline_contract()
        for name, transition in self.transitions.items():
            if name in pipeline:
                pipeline[name] = transition["previous_sha256"]
        params = {"language": "Chinese", "initial_prompt": None, "device": None,
                  "decoder": contract, "max_gap": 2.0, "text_file": None}
        speaker._write_final_receipt(self.wav, out, "synthetic", params, pipeline)
        return out, decoder

    def test_normal_uv_cli_reuses_completed_receipt_without_model_or_credentials(self):
        out, decoder = self.make_bundle()
        before = {p.name: p.read_bytes() for p in out.iterdir()}
        (self.root / "unconfigured.json").write_text("{}")
        env = {**os.environ, "HOME": str(self.root), "DAYMADE_AUDIO_CONFIG": str(self.root / "unconfigured.json"),
               "HF_HOME": str(self.root / "no-hf"), "XDG_CONFIG_HOME": str(self.root / "config")}
        for key in ("HF_TOKEN", "HF_HUB_TOKEN", "HUGGING_FACE_HUB_TOKEN", "DAYMADE_AUDIO_DISPATCH_BYPASS", "DAYMADE_AUDIO_DISPATCH_NONCE"):
            env.pop(key, None)
        guard = self.root / "sitecustomize.py"
        guard.write_text("import sys\nclass Guard:\n def find_spec(self,fullname,*args):\n  if fullname.split('.')[0] in {'torch','mlx','mlx_audio','pyannote','numpy'}:\n   raise AssertionError('Model runtime forbidden in completed-cache probe: '+fullname)\nsys.meta_path.insert(0,Guard())\n")
        env["PYTHONPATH"] = str(self.root)
        command = ["uv", "run", "--no-project", "python", str(SCRIPTS / "speaker_transcribe.py"),
                   str(self.wav), str(out), "--ffmpeg-path", str(decoder)]
        result = subprocess.run(command, env=env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"complete receipt reused; no audio inference", result.stderr)
        for name, data in before.items():
            self.assertEqual((out / name).read_bytes(), data)
        record = json.loads((out / "synthetic.receipt.json.dispatch-reuse.json").read_text())
        self.assertEqual(record["origin_sha256"], hashlib.sha256(before["synthetic.receipt.json"]).hexdigest())
        self.assertEqual(record["entrypoints"]["speaker_transcribe.py"], sha(SCRIPTS / "speaker_transcribe.py"))
        # A real parameter change cannot reuse the receipt, nor reach a model
        # without the original prerequisite. No fallback confirmation is made.
        changed = subprocess.run(command + ["--language", "English"], env=env, capture_output=True, timeout=30)
        self.assertEqual(changed.returncode, 3, changed.stderr)
        self.assertNotIn(b"complete receipt reused", changed.stderr)
        self.assertEqual((out / "synthetic.receipt.json").read_bytes(), before["synthetic.receipt.json"])

    def test_completed_bundle_rejects_native_pipeline_model_source_and_content_drift(self):
        out, decoder = self.make_bundle()
        args = argparse.Namespace(inputs=[self.wav], out_dir=out, ffmpeg_path=decoder, language="Chinese",
                                  initial_prompt=None, device=None, max_gap=2.0, text_file=None)
        receipt = out / "synthetic.receipt.json"
        original = json.loads(receipt.read_text())
        self.assertEqual(speaker._reuse_completed_bundles(args), [])
        for field, value in (("pipeline", {**original["pipeline"], "align_speakers.py": "f" * 64}),
                             ("model_contract", {**original["model_contract"], "revision": "b" * 40}),
                             ("source_audio", {**original["source_audio"], "sha256": "f" * 64})):
            receipt.write_text(json.dumps({**original, field: value}))
            self.assertEqual(speaker._reuse_completed_bundles(args), [self.wav])
        receipt.write_text(json.dumps(original))
        (out / "synthetic.txt").write_text("Overwritten content")
        self.assertEqual(speaker._reuse_completed_bundles(args), [self.wav])


if __name__ == "__main__":
    unittest.main()
