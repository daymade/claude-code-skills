#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build a pinned, isolated Metal whisper.cpp runtime without downloading models.

Supply an existing official v1.9.1 Git checkout. Only its immutable commit is
archived; working-tree edits are never copied. Output must be outside the Skill
and the source checkout. System binaries, services and model files are untouched.
"""

import argparse
import hashlib
import io
import json
import platform
import subprocess
import sys
import tarfile
from pathlib import Path

import transcribe_long_whispercpp as asr


CONTRACT = {"schema": asr.GPU_SCHEMA, "upstream_commit": asr.GPU_UPSTREAM_COMMIT,
            "version": "1.9.1"}


def checked(argv, cwd=None, log_path=None):
    if log_path:
        with log_path.open("ab") as stream:
            result = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                    stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"command exited {result.returncode}; inspect {log_path}")
        return b""
    result = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): "
                           + result.stderr.decode("utf-8", errors="replace")[-1500:])
    return result.stdout


def check_destination(source, output):
    skill = Path(__file__).resolve().parents[1]
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("build output must be separate from the upstream checkout")
    if output == skill or output.is_relative_to(skill):
        raise ValueError("build output belongs in user cache, outside the update-owned Skill")


def build(source, output, cmake, jobs):
    check_destination(source, output)
    if checked(["git", "-C", str(source), "rev-parse", "HEAD"]).decode().strip() != asr.GPU_UPSTREAM_COMMIT:
        raise ValueError("source must be the official pinned whisper.cpp v1.9.1 commit")
    if checked(["git", "-C", str(source), "rev-parse", "HEAD:src/whisper.cpp"]).decode().strip() != "5ffc70af00e76fc121b961613259c7c179a4d2d4":
        raise ValueError("upstream source blob is unknown")
    if sys.platform != "darwin" or platform.machine() not in {"arm64", "aarch64"}:
        raise ValueError("this build route supports Apple Silicon Metal only; no CPU build fallback")
    if jobs < 1 or jobs > 16:
        raise ValueError("--jobs must be within 1..16")
    receipt = output / "gpu-runtime.json"
    if output.exists():
        # A finished build can be reused, but an interrupted/unknown directory is
        # preserved rather than overwritten or silently adopted.
        asr.validate_gpu_runtime(output / "build/bin/whisper-cli", receipt)
        manifest = json.loads(receipt.read_text())
        if manifest["binaries"]["whisper-vad-speech-segments"] != asr.file_contract(output / "build/bin/whisper-vad-speech-segments"):
            raise ValueError("cached VAD binary changed")
        return receipt
    archive = checked(["git", "-C", str(source), "archive", "--format=tar", asr.GPU_UPSTREAM_COMMIT])
    output.mkdir(parents=True)
    native_source = output / "source"
    native_source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        tar.extractall(native_source, filter="data")
    checked(["git", "-C", str(native_source), "apply", "--unidiff-zero", "--check", str(asr.GPU_PATCH)])
    checked(["git", "-C", str(native_source), "apply", "--unidiff-zero", str(asr.GPU_PATCH)])
    log_path = output / "build.log"
    build_dir = output / "build"
    # Static libraries plus an embedded Metal shader keep the runtime identity
    # in the executable hashes rather than untracked adjacent shared libraries.
    checked([str(cmake), "-S", str(native_source), "-B", str(build_dir),
             "-DBUILD_SHARED_LIBS=OFF", "-DWHISPER_BUILD_TESTS=OFF",
             "-DGGML_METAL=ON", "-DGGML_METAL_EMBED_LIBRARY=ON",
             "-DGGML_BLAS=OFF", "-DGGML_CPU_ALL_VARIANTS=OFF",
             "-DCMAKE_BUILD_TYPE=Release"], log_path=log_path)
    checked([str(cmake), "--build", str(build_dir), "--target", "whisper-cli",
             "whisper-vad-speech-segments", "-j", str(jobs)], log_path=log_path)
    binaries = {}
    for name in ("whisper-cli", "whisper-vad-speech-segments"):
        binary = build_dir / "bin" / name
        if json.loads(checked([str(binary), "--asr-gpu-contract"])) != CONTRACT:
            raise RuntimeError(f"built {name} does not expose the required native policy")
        binaries[name] = asr.file_contract(binary)
    asr.atomic_write_json(receipt, {"contract": CONTRACT,
        "patch_sha256": asr.sha256_file(asr.GPU_PATCH), "binaries": binaries,
        "producer_sha256": asr.sha256_file(__file__),
        "source_archive_sha256": hashlib.sha256(archive).hexdigest()})
    asr.validate_gpu_runtime(build_dir / "bin/whisper-cli", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cmake-path", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    result = build(args.source_dir.resolve(), args.output_dir.resolve(),
                   args.cmake_path.resolve(), args.jobs)
    print(json.dumps({"gpu_runtime_manifest": str(result),
        "whisper_bin": str(result.parent / "build/bin/whisper-cli"),
        "vad_bin": str(result.parent / "build/bin/whisper-vad-speech-segments")}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"GPU_BUILD_BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(5)
