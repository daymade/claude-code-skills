# Acoustic diagnostics

Use this route to measure waveform-related evidence, inspect a proposed speech
cut, or compare tail energy. Keep the original recording, proposed edit points
and final render distinct. daudio owns the acoustic implementation; the editing
application owns its timeline, wording, case thresholds and adoption decision.

## Select and verify the runtime

1. Read the calling project's current audio/runtime contract. Keep its selected
   local or service execution mode; a thin client being installed does not prove
   a server operation exists. Do not migrate an application's runtime as part of
   diagnosing one clip.
2. For an already selected operator CLI, run `daudio acoustics --help` and the
   selected subcommand's `--help` in that environment. Confirm the actual command
   and dependency requirements. The examples below cover the local native CLI;
   service-backed calls must use and verify their own current service contract.
3. If readiness fails, inspect the selected owner's installation and model setup
   instructions. Complete authorized preparation, read it back, and resume at the
   first unmet prerequisite. Do not guess a package source, borrow another
   environment's configuration, or substitute an ASR result. If the owner or
   required environment is unavailable, report the missing prerequisite and
   recovery action; keep that measurement unverified.

CLI discovery alone proves neither native dependencies nor an executed result.
For example, `boundaries` also needs the optional TextGridTools (`tgt`)
dependency; successful `--help` does not establish that it is installed.
Praat and wavelet DSP may run on CPU. Neural quality, emotion, alignment or
speaker metrics require their prepared assets and supported GPU environment;
installing daudio does not install those models. Do not auto-download models,
change the engine, or fall back to CPU neural inference.

When the `daudio` CLI runtime and its isolated acoustics environment (Praat/
`parselmouth` and `tgt`) run different Python minor versions, do not prepend
the CLI runtime's `site-packages` via `PYTHONPATH`: compiled C-extensions
(such as `numpy`) from the wrong minor version shadow the acoustics environment
and fail with an `ImportError`. Invoke the acoustics interpreter directly and
append only the pure-Python `daudio` package path after the acoustics
environment's `site-packages`.

## Bind the audio and coordinates

Retain the original source and measure an identified PCM WAV. Record its actual
SHA256, channel, sample rate and sample count. When decoding or extracting a
context window, retain the parent source identity and offset. Map movie cuts,
speed changes and excerpt times back into that PCM's source coordinates before
using them. Unknown mappings stay unknown; an ASR timestamp is not that mapping.

Keep native artifacts and their identities with each report. For exact level
windows, preserve integer sample coordinates when available rather than making
a seconds-to-samples round trip. Never overwrite the source or an input report.
When preparing the measured PCM WAV for `boundaries`, decode the full exact
clip being cut rather than applying a fixed `-t` duration cap; even a small
container-vs-audio tail mismatch (for example, a few milliseconds) causes
`boundaries` to fail closed with `Cut must be inside the measured PCM`.

## Choose the observation

| Question | daudio operation | Required distinction |
|---|---|---|
| What happens acoustically near this point? | `praat` | Native pitch, intensity, RMS and silence measurements; no perceptual verdict |
| Does this proposed cut lie inside measured sounding material? | `boundaries` after `praat` | Review candidates at explicit source cutpoints; no automatic trimming |
| Does the selected tail lose energy? | `levels` | Explicit PCM16 windows, dBFS/P90, frame coverage and missing frames; caller supplies the comparison and threshold |
| Where are prominence or phrasing candidates? | `prominence` | Prepared Wavelet toolkit output; not safe word boundaries |
| Is there existing evidence for wording, voice similarity, predicted quality or emotion? | `align-zh`, `metrics`, `quality`, `emotion`; then optionally `compose` | Each observation retains its own input, execution status and limits |

For the local native CLI, use verified real inputs and new output locations:

```sh
daudio acoustics praat --audio "$PCM_WAV" --sha256 "$PCM_SHA256" \
  --out-dir "$NEW_PRAAT_DIR"
daudio acoustics boundaries --native-result "$PRAAT_RESULT_JSON" \
  --sha256 "$PRAAT_RESULT_SHA256" --cuts "$SOURCE_CUTS_JSON" \
  --out "$NEW_BOUNDARY_REPORT"
daudio acoustics levels --audio "$PCM16_WAV" --sha256 "$PCM16_SHA256" \
  --windows "$SOURCE_WINDOWS_JSON" --out "$NEW_LEVEL_REPORT"
```

These variables name caller-selected absolute paths and observed hashes, not
defaults. Praat reports its `result.json` path; hash that result for the boundary
inspector, rather than passing the WAV hash as the result hash. Preserve the
referenced native artifacts. `SOURCE_CUTS_JSON` is an array such as
`[{"id":"segment-1","start_s":0.1,"end_s":3.6}]` in measured PCM seconds.
Level windows may use `[{"id":"tail","intervals_samples":[[48000,62400]]}]`
when those are the intended sample indices. Check the command's current schema
and choose windows within the actual source coverage; example numbers are not
recommended cutpoints or durations.

## Report the result and its limit

Inspect the actual output, source bindings, execution status and coverage.
Missing dependencies, changed artifacts, incomplete coverage or failed inference
remain visible failures or unknowns. Keep waveform/acoustic observations, ASR or
known-text alignment, voice similarity, predicted naturalness and human adoption
separate; do not combine them into an overall “quality passed”.

A cut inside a sounding interval is a review candidate. A silence interval may
contain quiet consonants or noise; neither label certifies a safe word boundary.
A low-energy tail does not establish that words were lost. Keep `word_loss`
unknown unless separate source-linked content evidence establishes it. Do not
approve a cut from a waveform, an ASR pass, or a listening impression alone.

For a proposed repair, hand the source-bound finding and unresolved boundary
back to the editing owner. Preserve the original audio; re-measure the affected
output window after the authorized edit and verify its source-to-render mapping.
Report the actual evidence and remaining uncertainty before declaring the repair
complete.
