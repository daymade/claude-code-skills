# GPU-only whisper.cpp runtime for Path L

Use the existing Whisper and Silero model files. The build helper does not
download models, replace Homebrew executables or restart services. The source
checkout and build directory are explicit inputs; keep the build in user cache,
outside the update-owned Skill.

The upstream v1.9.1 source forces VAD onto CPU even when `--use-gpu` is requested,
and integrated VAD does not inherit the ASR context's GPU selection. Its help or
a Metal initialization line therefore cannot establish GPU VAD execution.

When an eligible build is missing, the agent performs authorized preparation:
obtain an official checkout of tag `v1.9.1`, verify commit
`f049fff95a089aa9969deb009cdd4892b3e74916`, then run:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/build_whispercpp_gpu.py \
  --source-dir /absolute/path/to/whisper.cpp-v1.9.1 \
  --output-dir /absolute/path/to/user-cache/whispercpp-gpu-v1.9.1 \
  --cmake-path /absolute/path/to/cmake
```

The helper archives that immutable commit, applies the bundled patch and makes
an independent static Metal build. It prints `gpu_runtime_manifest`,
`whisper_bin` and `vad_bin`. The manifest binds the patch and executable hashes;
the runner verifies it and the binary's native policy before loading a model.
Unknown versions and changed binaries are rejected. A finished build is reused;
an interrupted build is preserved, and preparation resumes in a new cache
directory rather than overwriting it. Model preparation remains separately
authorized; missing model files never trigger an implicit download.

The native patch inherits GPU/device selection for VAD and checks the actual
scheduler assignment of every compute node before executing each graph. A CPU
or unknown assignment fails before that graph runs. Metadata-only views and
reshapes are not model computation; registration of a CPU backend is not a
failure. Successful graphs emit `ASR_GPU_GRAPH` evidence for VAD and ASR.
A genuine all-silence block emits `ASR_GPU_NO_SPEECH` and requires VAD evidence
only. This is computation evidence, not a recognition-accuracy claim. The
isolated build rejects direct CPU auxiliary graphs, including the CPU DTW leg.

Before a batch, run a short known speech-plus-silence clip through the ordinary
Path L runner, inspect its restored source timestamps and text, then rerun the
same command and require cached blocks. Inspect the persisted block
`gpu_execution` records, not just provider availability or elapsed time.
The native guard enforces GPU computation; the agent still checks source-time
and recognition quality. The default 20-minute blocks, overlap ownership,
no-speech filtering and speaker late-fusion remain with their existing owners.

Old checkpoint directories are retained. Runtime and producer hashes give the
fixed route a new identity, so pre-fix unchecked blocks are not silently reused.
This build route is verified on Apple Silicon Metal; it does not claim a CUDA
build or a whole-recording quality benchmark.

Primary source: [whisper.cpp v1.9.1](https://github.com/ggml-org/whisper.cpp/blob/v1.9.1/src/whisper.cpp).
