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
        "language": "Chinese",
        "chunk_duration_s": 1200.0,
        "max_tokens_per_chunk": 8192,
        "quality_policy": local_mlx.QUALITY_POLICY_ID,
    }


class LongAudioSafetyTests(unittest.TestCase):
    def test_default_budget_is_per_chunk_and_bounded(self):
        parser = local_mlx.build_parser()
        args = parser.parse_args(["--smoke-test"])
        self.assertEqual(args.max_tokens, 8192)
        self.assertEqual(args.chunk_duration, 1200.0)
        local_mlx.validate_args(parser, args)

        unsafe = parser.parse_args(["--smoke-test", "--max-tokens", "200000"])
        with self.assertRaises(SystemExit):
            local_mlx.validate_args(parser, unsafe)

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

    def test_checkpoint_identity_changes_when_same_size_audio_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "audio.wav"
            fixed_mtime_ns = 1_700_000_000_123_456_789
            audio.write_bytes(b"first-audio")
            os.utime(audio, ns=(fixed_mtime_ns, fixed_mtime_ns))
            first_identity, first_digest = local_mlx._checkpoint_identity(
                audio, "example/model", "Chinese", 1200.0, 8192
            )

            audio.write_bytes(b"other-audio")
            os.utime(audio, ns=(fixed_mtime_ns, fixed_mtime_ns))
            second_identity, second_digest = local_mlx._checkpoint_identity(
                audio, "example/model", "Chinese", 1200.0, 8192
            )

            self.assertEqual(first_identity["source_size"], second_identity["source_size"])
            self.assertEqual(first_identity["source_mtime_ns"], second_identity["source_mtime_ns"])
            self.assertNotEqual(first_identity["source_sha256"], second_identity["source_sha256"])
            self.assertNotEqual(first_digest, second_digest)

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
