import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gpu_asr_under_test", ROOT / "scripts/transcribe_long_whispercpp.py")
asr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(asr)

# Sanitized lines from the real pinned Metal run. A loaded CPU backend is a
# registration/init event, while the native markers follow successful compute.
GPU_LOG = b"""ggml_backend_load_all: loaded CPU backend
ASR_GPU_GRAPH role=vad device=MTL0 compute_nodes=44 cpu_compute=0 status=complete
ASR_GPU_GRAPH role=asr device=MTL0 compute_nodes=8 cpu_compute=0 status=complete
"""


class GpuWhisperCppTests(unittest.TestCase):
    def test_real_gpu_compute_is_accepted_despite_cpu_backend_registration(self):
        result = asr.gpu_execution_evidence(GPU_LOG, [{"text": "speech"}])
        self.assertEqual(set(result), {"asr", "vad"})
        self.assertEqual(result["vad"]["compute_nodes"], 44)

    def test_initialization_or_use_gpu_flag_alone_is_not_execution(self):
        for log in (b"", b"whisper_vad_init_context: use_gpu=1\nusing Metal backend",
                    b"whisper_vad_init_context: using CPU backend"):
            with self.subTest(log=log), self.assertRaises(asr.DeterministicTranscriptionError):
                asr.gpu_execution_evidence(log, [{"text": "speech"}])

    def test_every_required_role_must_have_successful_nonempty_compute(self):
        for mutated in (GPU_LOG.replace(b"role=vad", b"role=other"),
                        GPU_LOG.replace(b"role=asr", b"role=other"),
                        GPU_LOG.replace(b"compute_nodes=44", b"compute_nodes=0"),
                        GPU_LOG.replace(b"status=complete", b"status=scheduled"),
                        GPU_LOG.replace(b"cpu_compute=0", b"cpu_compute=1"),
                        GPU_LOG.replace(b"device=MTL0", b"device=CPU"),
                        GPU_LOG + b"ASR_GPU_BLOCKED role=vad op=MUL_MAT backend=CPU"):
            with self.subTest(log=mutated), self.assertRaises(asr.DeterministicTranscriptionError):
                asr.gpu_execution_evidence(mutated, [{"text": "speech"}])

    def test_verified_silence_needs_vad_but_does_not_run_asr(self):
        log = GPU_LOG.split(b"ASR_GPU_GRAPH role=asr")[0]
        with self.assertRaises(asr.DeterministicTranscriptionError):
            asr.gpu_execution_evidence(log, [])
        result = asr.gpu_execution_evidence(log + b"ASR_GPU_NO_SPEECH status=complete", [])
        self.assertEqual(set(result), {"vad"})

    def test_cached_gpu_records_reject_missing_empty_null_cpu_and_boolean_counts(self):
        healthy = asr.gpu_execution_evidence(GPU_LOG, [{"text": "speech"}])
        asr.validate_gpu_records(healthy, True)
        asr.validate_gpu_records({"vad": healthy["vad"]}, False)
        for records in (None, {}, {"vad": None}, {"vad": {}},
                        {"vad": healthy["vad"]},
                        {"vad": {"device": "CPU", "compute_nodes": 44, "cpu_compute": 0}, "asr": healthy["asr"]},
                        {"vad": {"device": "MTL0", "compute_nodes": True, "cpu_compute": False}, "asr": healthy["asr"]}):
            with self.subTest(records=records), self.assertRaises(asr.CheckpointIntegrityError):
                asr.validate_gpu_records(records, True)

    def test_manifest_missing_empty_null_and_wrong_patch_stop_before_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            for payload in (None, {}, {"contract": None}, {"contract": {}},
                            {"contract": {"schema": "other"}, "binaries": {"whisper-cli": {}}}):
                manifest.write_text(json.dumps(payload))
                with self.subTest(payload=payload), mock.patch.object(asr, "run_checked") as probe:
                    with self.assertRaises(asr.DeterministicTranscriptionError):
                        asr.validate_gpu_runtime(Path(tmp) / "never-run", manifest)
                    probe.assert_not_called()
            manifest.unlink()
            with mock.patch.object(asr, "run_checked") as probe:
                with self.assertRaises(asr.DeterministicTranscriptionError):
                    asr.validate_gpu_runtime(Path(tmp) / "never-run", manifest)
                probe.assert_not_called()

    def test_native_contract_and_binary_hash_are_both_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary, manifest = Path(tmp) / "binary", Path(tmp) / "manifest.json"
            binary.write_bytes(b"fixture executable")
            contract = {"schema": asr.GPU_SCHEMA, "upstream_commit": asr.GPU_UPSTREAM_COMMIT, "version": "1.9.1"}
            payload = {"contract": contract, "patch_sha256": asr.sha256_file(asr.GPU_PATCH),
                       "binaries": {"whisper-cli": asr.file_contract(binary)}}
            manifest.write_text(json.dumps(payload))
            response = subprocess.CompletedProcess([], 0, json.dumps(contract).encode(), b"")
            with mock.patch.object(asr, "run_checked", return_value=response) as probe:
                self.assertEqual(asr.validate_gpu_runtime(binary, manifest)["contract"], contract)
                probe.assert_called_once()
            with mock.patch.object(asr, "run_checked", return_value=subprocess.CompletedProcess([], 0, b"{}", b"")):
                with self.assertRaises(asr.DeterministicTranscriptionError):
                    asr.validate_gpu_runtime(binary, manifest)
            binary.write_bytes(b"changed executable")
            with mock.patch.object(asr, "run_checked") as probe:
                with self.assertRaises(asr.DeterministicTranscriptionError):
                    asr.validate_gpu_runtime(binary, manifest)
                probe.assert_not_called()

    def test_verbose_child_does_not_deadlock_checkpoint_worker(self):
        result = asr.run_checked([sys.executable, "-c",
            "import sys; sys.stdout.write('x'*200000); sys.stderr.write('y'*200000)"],
            5, "verbose fixture")
        self.assertEqual(len(result.stdout), 200000)
        self.assertEqual(len(result.stderr), 200000)

    def test_real_done_block_can_be_reopened_and_reused(self):
        # Exercise the normal checkpoint reader, where the old missing math
        # import crashed as soon as a valid speech segment was encountered.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "block-0000.json"
            payload = {"schema": asr.SCHEMA, "index": 0,
                "base_start_s": 0.0, "base_end_s": 20.0,
                "extract_start_s": 0.0, "extract_end_s": 20.0,
                "utf8_replacement_count": 0,
                "gpu_execution": asr.gpu_execution_evidence(GPU_LOG, [{"text": "speech"}]),
                "transcription": [{"block_index": 0, "offsets": {"from": 3000, "to": 12000}, "text": "speech"}]}
            asr.atomic_write_json(artifact, payload)
            entry = {k: payload[k] for k in ("index", "base_start_s", "base_end_s", "extract_start_s", "extract_end_s", "utf8_replacement_count")}
            entry.update(status="done", artifact=artifact.name, sha256=asr.sha256_file(artifact), segment_count=1)
            self.assertEqual(asr.validate_done_block(root, entry)["transcription"], payload["transcription"])


if __name__ == "__main__":
    unittest.main()
