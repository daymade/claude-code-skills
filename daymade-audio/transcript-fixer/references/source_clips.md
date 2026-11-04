# Verified source clips

Use `scripts/source_clip.py` when a correction batch needs bounded windows from a
known local original or an already authorized SSH host. It supplies the existing
`verify_queue_audio.py` pipeline; it does not create a new transcription or
adjudication route. Existing `--audio` local-file/ffmpeg-URL calls remain valid.

## Prepare the actual source

Obtain the expected full SHA-256 from the owning source manifest. Bind its physical
absolute path and, for SSH, the exact existing alias, expected hostname and account.
The saved login does not authorize a new host, key, transfer or paid recognizer.

```bash
python3 scripts/source_clip.py prepare \
  --path /abs/source/original.mp4 --sha256 <expected-full-sha256> \
  --ssh-host <authorized-alias> \
  --expected-hostname <verified-hostname> --expected-user <verified-user> \
  --output /abs/runtime/source.json
```

For a local source omit the SSH arguments. Python 3, ffmpeg and ffprobe must
already work on the source host. A noninteractive SSH PATH can differ from the
interactive shell; when required, add `--ffmpeg <verified-absolute-path>` and
`--ffprobe <verified-absolute-path>` from that host. Missing tools fail visibly;
the adapter does not install or change the environment.

Preparation streams the whole source once to verify the expected hash, probes
duration and binds inode, size and change clocks. Source path and SSH identity
are private runtime metadata; keep the resulting spec outside the Skill bundle.
Quiesce the task's source producer before preparation. The spec is an operator-owned
receipt, not an authenticated authorization document; do not hand-edit its hash
or version to bypass a mismatch. A changed source is prepared again against its
real source manifest, never silently adopted by a cached clip.

## Reuse the existing two-window consumer

```bash
uv run scripts/verify_queue_audio.py \
  --transcript /abs/transcript.md \
  --source-spec /abs/runtime/source.json \
  --clip-cache /abs/runtime/source-clips \
  --time-overrides /abs/runtime/verified-times.json \
  --engine-script /abs/authorized-recognizer.py \
  --outdir /abs/runtime/audio-evidence
```

Keep the existing [timestamp, anchor and engine contract](script_parameters.md#verify_queue_audiopy).
Overrides use source-media seconds. Derive `--speed` only from independent
transcript-to-source timing evidence; the adapter's output itself runs at speed 1
and does not infer that mapping. Do not repair a timing mismatch by choosing a
plausible nearby utterance.

For a separately inspected window:

```bash
python3 scripts/source_clip.py fetch \
  --source-spec /abs/runtime/source.json --cache-dir /abs/runtime/source-clips \
  --start 12 --end 16 --output /abs/runtime/check.wav
```

Windows are finite source-clock intervals within the prepared duration and the
bound in `MAX_WINDOW` in `source_clip.py`. Remote extraction happens on that
source; only mono 16 kHz PCM WAV bytes return. The transport checks complete size,
SHA-256 and duration; `<clip>.source.json` records source hash, window, speed and
clip hash. A missing/truncated transfer cannot become evidence.

Cache identity includes the source version, host/path, window and audio format.
Each fetch checks the current source version before and after use and rehashes
cached bytes. Repreparing the unchanged source can reuse the same clip; modified
source or broken identity refuses, while damaged cached bytes are reacquired.
An exclusive per-key lock rejects concurrent writers; inspect a leftover lock
after an interrupted task rather than deleting it on a timer. Preserve evidence
clips and results while a pending row still references them.

Preparation and version checks assume an owned, quiescent source. They do not
provide a filesystem-wide lock against an adversarial writer or establish the
identity of speakers. Two agreeing windows remain acoustic evidence under the
existing correction policy; they never force an uncertain spelling or name.
