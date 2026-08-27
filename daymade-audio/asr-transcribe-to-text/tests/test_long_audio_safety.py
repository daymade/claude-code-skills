import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, SKILL_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


local_mlx = load_module("transcribe_local_mlx_under_test", "scripts/transcribe_local_mlx.py")
speaker = load_module("speaker_transcribe_under_test", "scripts/speaker_transcribe.py")


class FakeResult:
    def __init__(self, text, generation_tokens):
        self.text = text
        self.generation_tokens = generation_tokens


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, chunk, **kwargs):
        self.calls.append((chunk, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def identity():
    return {
        "source": "/example/audio.wav",
        "source_size": 123,
        "source_mtime_ns": 456,
        "source_sha256": "example-sha256",
        "model": "example/model",
        "model_revision": "a" * 40,
        "language": "Chinese",
        "chunk_duration_s": 1200.0,
        "max_tokens_per_chunk": 8192,
        "sample_rate": 16000,
        "quality_policy": local_mlx.QUALITY_POLICY_ID,
        "producer": {
            "script": "transcribe_local_mlx.py",
            "sha256": "b" * 64,
        },
        "splitter_contract": local_mlx.SPLITTER_CONTRACT_ID,
        "dependencies": dict(sorted(local_mlx.PINNED_DEPENDENCY_VERSIONS.items())),
    }


def write_receipt_backed_bundle(root, wav):
    stem = wav.stem
    (root / f"{stem}.txt").write_text(
        "[00:00.000 - 00:01.000] SPEAKER_00\nhello\n",
        encoding="utf-8",
    )
    (root / f"{stem}.csv").write_text(
        "file,start,end,duration,speaker,text\n"
        f"{wav.name},0,1,1,SPEAKER_00,hello\n",
        encoding="utf-8",
    )
    (root / f"{stem}.diarization.json").write_text(
        json.dumps({
            "num_segments": 1,
            "num_speakers": 1,
            "segments": [
                {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}
            ],
        }),
        encoding="utf-8",
    )
    (root / f"{stem}.alignment.json").write_text(
        json.dumps({
            "report": {
                "trustworthy": True,
                "anchored_ratio": 1.0,
                "num_turns": 1,
                "speakers": ["SPEAKER_00"],
            }
        }),
        encoding="utf-8",
    )
    speaker._stamp_alignment_source(
        wav, root, stem, speaker._source_audio_identity(wav)
    )
    parameters = {
        "language": "Chinese",
        "initial_prompt": None,
        "device": None,
        "max_gap": 2.0,
        "text_file": None,
    }
    speaker._write_final_receipt(wav, root, stem, parameters)
    return {
        name: root / f"{stem}{suffix}"
        for name, suffix in {
            **speaker.FINAL_ARTIFACT_SUFFIXES,
            "receipt": ".receipt.json",
        }.items()
    }


class LongAudioSafetyTests(unittest.TestCase):
    def test_default_budget_is_per_chunk_and_bounded(self):
        parser = local_mlx.build_parser()
        args = parser.parse_args(["--smoke-test"])
        self.assertEqual(args.max_tokens, 8192)
        self.assertEqual(args.chunk_duration, 1200.0)
        local_mlx.validate_args(parser, args)
        self.assertEqual(args.model_revision, local_mlx.DEFAULT_MODEL_REVISION)

        unsafe = parser.parse_args(["--smoke-test", "--max-tokens", "200000"])
        with self.assertRaises(SystemExit):
            local_mlx.validate_args(parser, unsafe)

        custom = parser.parse_args(["--smoke-test", "--model", "example/custom"])
        with self.assertRaises(SystemExit):
            local_mlx.validate_args(parser, custom)

        mutable = parser.parse_args([
            "--smoke-test",
            "--model",
            "example/custom",
            "--model-revision",
            "main",
        ])
        with self.assertRaises(SystemExit):
            local_mlx.validate_args(parser, mutable)

    def test_each_chunk_commits_and_second_run_resumes_without_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "result.txt"
            checkpoint = root / "checkpoint"
            cache_clears = []
            first = FakeModel([FakeResult("first", 100), FakeResult("second", 120)])

            text, manifest = local_mlx.transcribe_chunks(
                first,
                [("chunk-a", 0.0), ("chunk-b", 1200.0)],
                output,
                checkpoint,
                identity(),
                8192,
                "Chinese",
                1200.0,
                clear_cache=lambda: cache_clears.append(True),
            )

            self.assertEqual(text, "first second")
            self.assertEqual(output.read_text(encoding="utf-8"), "first second")
            self.assertEqual(len(first.calls), 2)
            self.assertEqual(len(cache_clears), 2)
            self.assertEqual(manifest["status"], "complete")
            self.assertTrue((checkpoint / "chunk-0000.txt").is_file())
            self.assertTrue((checkpoint / "chunk-0001.txt").is_file())

            resumed = FakeModel([])
            resumed_text, resumed_manifest = local_mlx.transcribe_chunks(
                resumed,
                [("chunk-a", 0.0), ("chunk-b", 1200.0)],
                output,
                checkpoint,
                identity(),
                8192,
                "Chinese",
                1200.0,
            )
            self.assertEqual(resumed_text, "first second")
            self.assertEqual(resumed.calls, [])
            self.assertEqual(resumed_manifest["status"], "complete")

    def test_token_ceiling_preserves_prior_chunks_and_retries_only_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "result.txt"
            checkpoint = root / "checkpoint"
            first = FakeModel([FakeResult("safe", 100), FakeResult("loop", 8192)])

            with self.assertRaises(local_mlx.ChunkTokenLimitError):
                local_mlx.transcribe_chunks(
                    first,
                    [("chunk-a", 0.0), ("chunk-b", 1200.0)],
                    output,
                    checkpoint,
                    identity(),
                    8192,
                    "Chinese",
                    1200.0,
                )
            self.assertFalse(output.exists())
            state = json.loads((checkpoint / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(state["chunks"][0]["status"], "done")
            self.assertEqual(state["chunks"][1]["status"], "failed")

            retry = FakeModel([FakeResult("recovered", 110)])
            text, state = local_mlx.transcribe_chunks(
                retry,
                [("chunk-a", 0.0), ("chunk-b", 1200.0)],
                output,
                checkpoint,
                identity(),
                8192,
                "Chinese",
                1200.0,
            )
            self.assertEqual(text, "safe recovered")
            self.assertEqual(len(retry.calls), 1)
            self.assertEqual(retry.calls[0][0], "chunk-b")
            self.assertEqual(state["status"], "complete")

    def test_repetition_loop_below_token_ceiling_is_rejected_before_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "result.txt"
            checkpoint = root / "checkpoint"
            loop_text = "谢谢大家收看欢迎继续关注" * 500
            model = FakeModel([FakeResult(loop_text, 3000)])

            with self.assertRaisesRegex(
                local_mlx.TranscriptQualityError,
                "repetition-loop quality gate",
            ):
                local_mlx.transcribe_chunks(
                    model,
                    [("chunk-a", 0.0)],
                    output,
                    checkpoint,
                    identity(),
                    8192,
                    "Chinese",
                    1200.0,
                )

            self.assertFalse(output.exists())
            self.assertFalse((checkpoint / "chunk-0000.txt").exists())
            state = json.loads((checkpoint / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "failed")
            self.assertIn("repetition-loop quality gate", state["error"])

    def test_corrupt_completed_checkpoint_fails_instead_of_silent_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "result.txt"
            checkpoint = root / "checkpoint"
            first = FakeModel([FakeResult("safe", 100)])
            local_mlx.transcribe_chunks(
                first,
                [("chunk-a", 0.0)],
                output,
                checkpoint,
                identity(),
                8192,
                "Chinese",
                1200.0,
            )
            (checkpoint / "chunk-0000.txt").write_text("tampered", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                local_mlx.transcribe_chunks(
                    FakeModel([]),
                    [("chunk-a", 0.0)],
                    output,
                    checkpoint,
                    identity(),
                    8192,
                    "Chinese",
                    1200.0,
                )

    def test_missing_completed_checkpoint_part_is_a_blocking_integrity_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "result.txt"
            checkpoint = root / "checkpoint"
            local_mlx.transcribe_chunks(
                FakeModel([FakeResult("safe", 100)]),
                [("chunk-a", 0.0)],
                output,
                checkpoint,
                identity(),
                8192,
                "Chinese",
                1200.0,
            )
            (checkpoint / "chunk-0000.txt").unlink()

            with self.assertRaisesRegex(
                local_mlx.CheckpointIntegrityError,
                "checkpoint part is missing",
            ):
                local_mlx.transcribe_chunks(
                    FakeModel([]),
                    [("chunk-a", 0.0)],
                    output,
                    checkpoint,
                    identity(),
                    8192,
                    "Chinese",
                    1200.0,
                )

    def test_malformed_checkpoint_root_and_chunk_entry_are_integrity_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.json"
            manifest_path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(
                local_mlx.CheckpointIntegrityError,
                "root must be an object",
            ):
                local_mlx._load_or_create_manifest(
                    manifest_path, identity(), 1
                )

            manifest_path.unlink()
            local_mlx._load_or_create_manifest(manifest_path, identity(), 1)
            unsafe = json.loads(manifest_path.read_text(encoding="utf-8"))
            unsafe["chunks"] = [{
                "index": 0,
                "status": "done",
                "part": "../outside.txt",
                "sha256": "a" * 64,
            }]
            manifest_path.write_text(json.dumps(unsafe), encoding="utf-8")
            with self.assertRaisesRegex(
                local_mlx.CheckpointIntegrityError,
                "unsafe or malformed identity",
            ):
                local_mlx._load_or_create_manifest(
                    manifest_path, identity(), 1
                )

            manifest_path.unlink()
            local_mlx._load_or_create_manifest(manifest_path, identity(), 1)
            malformed = json.loads(manifest_path.read_text(encoding="utf-8"))
            malformed["chunks"] = [None]
            manifest_path.write_text(json.dumps(malformed), encoding="utf-8")
            with self.assertRaisesRegex(
                local_mlx.CheckpointIntegrityError,
                "chunk entries are missing",
            ):
                local_mlx._load_or_create_manifest(
                    manifest_path, identity(), 1
                )

    def test_checkpoint_identity_changes_when_same_size_audio_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "audio.wav"
            fixed_mtime_ns = 1_700_000_000_123_456_789
            audio.write_bytes(b"first-audio")
            os.utime(audio, ns=(fixed_mtime_ns, fixed_mtime_ns))
            first_identity, first_digest = local_mlx._checkpoint_identity(
                audio,
                "example/model",
                "1" * 40,
                "Chinese",
                1200.0,
                8192,
                16000,
                local_mlx.PINNED_DEPENDENCY_VERSIONS,
                producer_sha256="a" * 64,
            )

            audio.write_bytes(b"other-audio")
            os.utime(audio, ns=(fixed_mtime_ns, fixed_mtime_ns))
            second_identity, second_digest = local_mlx._checkpoint_identity(
                audio,
                "example/model",
                "1" * 40,
                "Chinese",
                1200.0,
                8192,
                16000,
                local_mlx.PINNED_DEPENDENCY_VERSIONS,
                producer_sha256="a" * 64,
            )

            self.assertEqual(first_identity["source_size"], second_identity["source_size"])
            self.assertEqual(first_identity["source_mtime_ns"], second_identity["source_mtime_ns"])
            self.assertNotEqual(first_identity["source_sha256"], second_identity["source_sha256"])
            self.assertNotEqual(first_digest, second_digest)

    def test_checkpoint_identity_changes_with_producer_and_model_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "audio.wav"
            audio.write_bytes(b"audio")
            common = (
                audio,
                "example/model",
            )
            first_identity, first_digest = local_mlx._checkpoint_identity(
                *common,
                "1" * 40,
                "Chinese",
                1200.0,
                8192,
                16000,
                local_mlx.PINNED_DEPENDENCY_VERSIONS,
                producer_sha256="a" * 64,
            )
            producer_identity, producer_digest = local_mlx._checkpoint_identity(
                *common,
                "1" * 40,
                "Chinese",
                1200.0,
                8192,
                16000,
                local_mlx.PINNED_DEPENDENCY_VERSIONS,
                producer_sha256="b" * 64,
            )
            revision_identity, revision_digest = local_mlx._checkpoint_identity(
                *common,
                "2" * 40,
                "Chinese",
                1200.0,
                8192,
                16000,
                local_mlx.PINNED_DEPENDENCY_VERSIONS,
                producer_sha256="a" * 64,
            )
            self.assertNotEqual(first_digest, producer_digest)
            self.assertNotEqual(first_digest, revision_digest)
            self.assertNotEqual(
                first_identity["producer"], producer_identity["producer"]
            )
            self.assertNotEqual(
                first_identity["model_revision"],
                revision_identity["model_revision"],
            )

    def test_local_model_revision_is_derived_from_model_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp) / "model"
            model_dir.mkdir()
            weights = model_dir / "weights.safetensors"
            weights.write_bytes(b"first-weights")
            source, kind, first_revision = local_mlx._resolve_model_source(
                model_dir, None
            )
            self.assertEqual(source, str(model_dir.resolve()))
            self.assertEqual(kind, "local-content-addressed")
            self.assertRegex(first_revision, r"^local-sha256:[0-9a-f]{64}$")

            weights.write_bytes(b"other-weights")
            _source, _kind, second_revision = local_mlx._resolve_model_source(
                model_dir, None
            )
            self.assertNotEqual(first_revision, second_revision)

    def test_speaker_timeout_reaps_grandchild_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "grandchild.pid"
            child_program = (
                "import pathlib,subprocess,sys,time; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); "
                "time.sleep(60)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                speaker.run([sys.executable, "-c", child_program], timeout=0.3)
            grandchild_pid = int(pid_file.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    os.kill(grandchild_pid, 0)
                except ProcessLookupError:
                    break
                proc_stat = Path(f"/proc/{grandchild_pid}/stat")
                if proc_stat.exists():
                    fields = proc_stat.read_text(encoding="utf-8").split()
                    if len(fields) > 2 and fields[2] == "Z":
                        # Minimal containers often have no init reaper. A zombie
                        # is already dead and consumes no CPU/GPU; PID 1 will reap
                        # it only when the test process exits.
                        break
                time.sleep(0.05)
            else:
                try:
                    os.kill(grandchild_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.fail(f"grandchild process survived timeout: pid={grandchild_pid}")

    def test_group_cleanup_kills_sigterm_ignoring_child_after_leader_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "grandchild.pid"
            grandchild_program = (
                "import signal,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "time.sleep(60)"
            )
            leader_program = (
                "import pathlib,subprocess,sys; "
                f"p=subprocess.Popen([sys.executable,'-c',{grandchild_program!r}]); "
                f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid))"
            )
            leader = subprocess.Popen(
                [sys.executable, "-c", leader_program],
                start_new_session=True,
            )
            deadline = time.monotonic() + 3
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(pid_file.exists())
            leader.wait(timeout=3)
            grandchild_pid = int(pid_file.read_text(encoding="utf-8"))

            speaker._terminate_process_group(leader, grace_seconds=0.2)

            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    os.kill(grandchild_pid, 0)
                except ProcessLookupError:
                    break
                proc_stat = Path(f"/proc/{grandchild_pid}/stat")
                if proc_stat.exists():
                    fields = proc_stat.read_text(encoding="utf-8").split()
                    if len(fields) > 2 and fields[2] == "Z":
                        break
                time.sleep(0.05)
            else:
                try:
                    os.kill(grandchild_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.fail(
                    "SIGTERM-ignoring grandchild survived leader-first cleanup: "
                    f"pid={grandchild_pid}"
                )

    def test_speaker_leg_rejects_unproven_exists_only_qwen_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav = root / "audio.wav"
            wav.write_bytes(b"first-audio")
            fixed_mtime_ns = 1_700_000_000_123_456_789
            os.utime(wav, ns=(fixed_mtime_ns, fixed_mtime_ns))
            work_root = root / "work"
            destination = work_root / wav.stem / f"{wav.stem}.qwen.txt"
            destination.parent.mkdir(parents=True)
            destination.write_text("stale transcript", encoding="utf-8")
            calls = []

            def fake_run(command, timeout=None):
                calls.append(command)
                staging = Path(command[command.index("--output-dir") + 1])
                staging.mkdir(parents=True, exist_ok=True)
                (staging / f"{wav.stem}.txt").write_text(
                    f"fresh transcript {len(calls)}", encoding="utf-8"
                )

            with mock.patch.object(speaker, "run", side_effect=fake_run):
                speaker.leg_text([wav], work_root, "Chinese", False, 30)
                self.assertEqual(len(calls), 1)
                speaker.leg_text([wav], work_root, "Chinese", False, 30)
                self.assertEqual(len(calls), 1)

                wav.write_bytes(b"other-audio")
                os.utime(wav, ns=(fixed_mtime_ns, fixed_mtime_ns))
                speaker.leg_text([wav], work_root, "Chinese", False, 30)

            self.assertEqual(len(calls), 2)
            self.assertEqual(
                destination.read_text(encoding="utf-8"), "fresh transcript 2"
            )

    def test_alignment_provenance_binds_final_bundle_to_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav = root / "audio.wav"
            wav.write_bytes(b"source-audio")
            alignment = root / "audio.alignment.json"
            alignment.write_text(
                json.dumps({"report": {"trustworthy": True}}),
                encoding="utf-8",
            )
            (root / "audio.csv").write_text(
                "file,start,end,duration,speaker,text\n"
                "audio.wav,0,1,1,SPEAKER_00,hello\n",
                encoding="utf-8",
            )
            (root / "audio.txt").write_text(
                "[00:00.000 - 00:01.000] SPEAKER_00\nhello\n",
                encoding="utf-8",
            )
            (root / "audio.diarization.json").write_text(
                json.dumps(
                    {
                        "num_segments": 1,
                        "num_speakers": 1,
                        "segments": [
                            {
                                "start": 0.0,
                                "end": 1.0,
                                "speaker": "SPEAKER_00",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            speaker._stamp_alignment_source(
                wav,
                root,
                wav.stem,
                speaker._source_audio_identity(wav),
            )

            payload = json.loads(alignment.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_audio"]["path"], str(wav.resolve()))
            self.assertEqual(payload["source_audio"]["size"], wav.stat().st_size)
            self.assertEqual(
                payload["source_audio"]["sha256"],
                local_mlx._sha256_file(wav),
            )
            self.assertEqual(payload["turn_contract"]["schema"], "speaker-csv-v1")
            self.assertEqual(
                payload["component_sha256"]["csv"],
                local_mlx._sha256_file(root / "audio.csv"),
            )
            parameters = {
                "language": "Chinese",
                "initial_prompt": None,
                "device": None,
                "max_gap": 2.0,
                "text_file": None,
            }
            speaker._write_final_receipt(
                wav, root, wav.stem, parameters
            )
            receipt_path = root / "audio.receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema"], speaker.FINAL_RECEIPT_SCHEMA)
            self.assertEqual(receipt["parameters"], parameters)
            self.assertEqual(
                receipt["model_contract"]["revision"],
                local_mlx.DEFAULT_MODEL_REVISION,
            )
            for name in speaker.FINAL_ARTIFACT_SUFFIXES:
                self.assertEqual(
                    receipt["artifacts"][name]["sha256"],
                    local_mlx._sha256_file(
                        root / f"audio{speaker.FINAL_ARTIFACT_SUFFIXES[name]}"
                    ),
                )

    def test_speaker_leg_propagates_machine_readable_checkpoint_exit(self):
        with self.assertRaises(SystemExit) as raised:
            speaker.run(
                [sys.executable, "-c", "raise SystemExit(4)"],
                timeout=3,
            )
        self.assertEqual(raised.exception.code, 4)

    def test_receipt_backed_speaker_mapping_updates_complete_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav = root / "audio.wav"
            wav.write_bytes(b"wav")
            paths = write_receipt_backed_bundle(root, wav)

            speaker.apply_speaker_mapping_transaction(
                root,
                wav.stem,
                {"SPEAKER_00": "Alice"},
                "test mapping",
            )

            self.assertIn(" Alice\n", paths["txt"].read_text(encoding="utf-8"))
            self.assertIn(",Alice,", paths["csv"].read_text(encoding="utf-8"))
            alignment = json.loads(paths["alignment"].read_text(encoding="utf-8"))
            self.assertEqual(alignment["label_mapping"]["SPEAKER_00"], "Alice")
            receipt = json.loads(paths["receipt"].read_text(encoding="utf-8"))
            for name in speaker.FINAL_ARTIFACT_SUFFIXES:
                self.assertEqual(
                    receipt["artifacts"][name]["sha256"],
                    local_mlx._sha256_file(paths[name]),
                )

    def test_receipt_backed_speaker_mapping_rolls_back_partial_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav = root / "audio.wav"
            wav.write_bytes(b"wav")
            paths = write_receipt_backed_bundle(root, wav)
            before = {name: path.read_bytes() for name, path in paths.items()}
            original_atomic_json = speaker.atomic_write_json

            def fail_final_receipt(path, payload):
                if Path(path).name.endswith(".receipt.json"):
                    raise TypeError("injected final receipt failure")
                return original_atomic_json(path, payload)

            with (
                mock.patch.object(
                    speaker, "atomic_write_json", side_effect=fail_final_receipt
                ),
                self.assertRaisesRegex(TypeError, "injected final receipt failure"),
            ):
                speaker.apply_speaker_mapping_transaction(
                    root,
                    wav.stem,
                    {"SPEAKER_00": "Alice"},
                    "test mapping",
                )

            self.assertEqual(
                {name: path.read_bytes() for name, path in paths.items()},
                before,
            )

    def test_required_leg_rerun_without_fresh_output_fails_before_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav = root / "audio.wav"
            wav.write_bytes(b"source-audio")
            work_root = root / "work"
            destination = work_root / wav.stem / f"{wav.stem}.qwen.txt"
            destination.parent.mkdir(parents=True)
            destination.write_text("stale transcript", encoding="utf-8")

            with (
                mock.patch.object(speaker, "run", return_value=None),
                self.assertRaisesRegex(RuntimeError, "produced no fresh artifact"),
            ):
                speaker.leg_text([wav], work_root, "Chinese", False, 30)

            self.assertEqual(
                destination.read_text(encoding="utf-8"), "stale transcript"
            )
            self.assertFalse(
                speaker._artifact_provenance_matches_source(wav, destination)
            )

    def test_persistent_staging_file_cannot_masquerade_as_fresh_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav = root / "audio.wav"
            wav.write_bytes(b"source-b")
            work_root = root / "work"
            persistent_staging = work_root / "_qwen" / f"{wav.stem}.txt"
            persistent_staging.parent.mkdir(parents=True)
            persistent_staging.write_text("old source-a text", encoding="utf-8")
            destination = work_root / wav.stem / f"{wav.stem}.qwen.txt"

            with (
                mock.patch.object(speaker, "run", return_value=None),
                self.assertRaisesRegex(RuntimeError, "produced no fresh artifact"),
            ):
                speaker.leg_text([wav], work_root, "Chinese", False, 30)

            self.assertFalse(destination.exists())
            self.assertEqual(
                persistent_staging.read_text(encoding="utf-8"),
                "old source-a text",
            )

    def test_full_cache_contract_rejects_wrong_parameters_at_consumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav = root / "audio.wav"
            wav.write_bytes(b"source")
            artifact = root / "audio.qwen.txt"
            artifact.write_text("transcript", encoding="utf-8")
            speaker._write_artifact_provenance(
                wav,
                artifact,
                "transcribe_local_mlx.py",
                {"language": "Chinese"},
            )

            self.assertTrue(
                speaker._artifact_cache_valid(
                    wav,
                    artifact,
                    "transcribe_local_mlx.py",
                    {"language": "Chinese"},
                )
            )
            self.assertFalse(
                speaker._artifact_cache_valid(
                    wav,
                    artifact,
                    "transcribe_local_mlx.py",
                    {"language": "English"},
                )
            )

    def test_mlx_worker_exits_when_explicit_owner_disappears(self):
        owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.3)"])
        helper = (
            "import importlib.util,pathlib,time; "
            f"p=pathlib.Path({str(SKILL_ROOT / 'scripts/transcribe_local_mlx.py')!r}); "
            "s=importlib.util.spec_from_file_location('m',p); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            f"m.start_owner_watchdog({owner.pid}, poll_seconds=0.05); time.sleep(60)"
        )
        worker = subprocess.Popen(
            [sys.executable, "-c", helper],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        owner.wait(timeout=2)
        _stdout, stderr = worker.communicate(timeout=3)
        self.assertEqual(worker.returncode, 125)
        self.assertIn("disappeared; aborting orphan worker", stderr)


if __name__ == "__main__":
    unittest.main()
