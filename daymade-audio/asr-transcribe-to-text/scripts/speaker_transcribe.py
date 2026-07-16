#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyannote.audio", "torch", "torchaudio"]
# ///
"""Multi-speaker transcription, DECOUPLED (WhisperX-style): full-audio ASR +
word-level timing + diarization, aligned after the fact — the audio is never
cut before transcription, so ASR keeps its full context and Chinese fidelity.

Three legs + one aligner:
  1. Qwen3-ASR MLX full-audio transcript (subprocess: transcribe_local_mlx.py)
  2. mlx-whisper word timestamps        (subprocess: word_timestamps_whisper.py)
  3. pyannote diarization               (in-process, MPS/CUDA; pipeline loaded
                                          ONCE for the whole batch, not per file)
  4. align_speakers.py attaches speakers to the Layer-1 text by mapping it
     onto the timed word lattice and the diarization segments.

Outputs per input (flat under OUTPUT_DIR — same contract downstream tools read):
  <stem>.diarization.json   raw pyannote segments
  <stem>.txt                [MM:SS - MM:SS] SPEAKER_xx + text
  <stem>.csv                file,start,end,duration,speaker,text
  <stem>.alignment.json     alignment provenance + anchored_ratio trust signal
Intermediate legs are cached under OUTPUT_DIR/_align/ and reused on re-run
(pass --force to redo them).

Speaker labels are anonymous (SPEAKER_00...). Map them to real names with
voiceprint_id.py — references/voiceprint_speaker_id.md.

Prerequisite — HuggingFace token for pyannote (gated model). The script
implements the missing-token state machine itself (not just documented):
  - no token + first run            -> fail with setup steps (exit 3)
  - no token + config.diarization_declined -> warn (with setup steps) + fall
                                          back to plain text this run
  - token present                   -> proceed; diarize_all still fails exit 3
                                       authoritatively if the gated model can't load

Usage:
  uv run speaker_transcribe.py INPUT.wav [INPUT2.wav ...] OUTPUT_DIR [options]
  --no-diarization   plain-text fast path: Qwen3 full text only
  --text-file PATH   align ONE pre-made transcript (single input only)
  --force            redo intermediate legs even if present
  --timeout SEC      per-leg subprocess timeout (default 1800)
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PYANNOTE_SETUP_HINT = """
============================================================
pyannote could not load — speaker diarization needs a one-time setup:

  1. Accept the model terms (free account):
       https://hf.co/pyannote/speaker-diarization-3.1
       (also accept https://hf.co/pyannote/segmentation-3.0 if prompted)
  2. Log in from this machine:
       huggingface-cli login        (or: export HF_TOKEN=hf_...)

Then re-run — the token is detected automatically and speaker
diarization becomes permanent for every future run.
============================================================"""

DIARIZATION_DISABLED_BANNER = """⚠️  Speaker diarization is DISABLED for this run (config.diarization_declined is set).
    Output is plain text only — NO speaker labels.
    To enable speaker labels permanently:
      1. Accept terms: https://hf.co/pyannote/speaker-diarization-3.1
      2. huggingface-cli login   (or: export HF_TOKEN=hf_...)
      3. (optional) remove "diarization_declined" from config.json to stop this warning
    Once a token is present, diarization resumes automatically — no other action needed.
"""

# Substrings that indicate a pyannote/HF access problem (token/terms), vs a real
# bug. Broadened beyond the original few so an upstream wording change doesn't
# turn a legit "accept terms" prompt into a raw traceback.
PYANNOTE_ACCESS_KEYWORDS = (
    "token", "gated", "401", "403", "451", "unauthorized", "unauthorised",
    "forbidden", "accept", "license", "agreement", "login", "permission",
    "private repository", "user conditions", "credentials", "not authenticated",
)

# Map the orchestrator's --language to a whisper language code. The whisper leg
# is a TIMING lattice, but it still must decode in the right language or its
# word tokenization is garbage and the difflib anchor ratio collapses.
_WHISPER_LANG_MAP = {
    "chinese": "zh", "zh": "zh", "cn": "zh", "mandarin": "zh",
    "english": "en", "en": "en",
    "japanese": "ja", "ja": "ja",
    "korean": "ko", "ko": "ko",
    "french": "fr", "fr": "fr",
    "german": "de", "de": "de",
    "spanish": "es", "es": "es",
}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def run(cmd, timeout=None):
    log("+ " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, timeout=timeout)


def _whisper_lang(language):
    """Forward the real language to the whisper leg (was: only 'zh' when the
    orchestrator language started with 'chin', silently forcing zh otherwise)."""
    l = (language or "").strip().lower()
    if l in _WHISPER_LANG_MAP:
        return _WHISPER_LANG_MAP[l]
    if not l:
        return "zh"
    return l  # pass through; whisper rejects unsupported codes clearly rather than silently forcing zh


def _is_pyannote_access_error(e):
    return any(k in str(e).lower() for k in PYANNOTE_ACCESS_KEYWORDS)


def _hint_import_error(e):
    log(f"ERROR importing pyannote stack: {e}")
    log(PYANNOTE_SETUP_HINT)
    log("NOTE: if you ran this with plain `python` instead of `uv run`, that is "
        "likely the cause — pyannote/torch are only installed inside the uv env.")
    sys.exit(3)


def _config_path():
    """config.json path (CLAUDE_PLUGIN_DATA when run via the skill). None when
    not under the agent runtime — then we can't persist 'declined' and fall
    back to first-time-fail."""
    pd = os.environ.get("CLAUDE_PLUGIN_DATA")
    return Path(pd) / "config.json" if pd else None


def _read_config():
    p = _config_path()
    if not p or not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _hf_token_present():
    """Cheap pre-check for a HuggingFace token. The authoritative check is
    still load_pipeline() — a token without accepted terms fails there. This
    just decides warn-vs-fail without the expensive model download."""
    if os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"):
        return True
    tok = Path.home() / ".cache" / "huggingface" / "token"
    try:
        return tok.exists() and bool(tok.read_text(encoding="utf-8").strip())
    except Exception:
        return False


def plain_text_path(args, timeout):
    """Plain-text fast path: full-audio Qwen3 text, no speakers."""
    if args.text_file:
        for wav in args.inputs:
            out = args.out_dir / f"{wav.stem}.txt"
            out.write_text(Path(args.text_file).read_text(encoding="utf-8"), encoding="utf-8")
            log(f"Wrote {out} (from --text-file)")
        return
    cmd = ["uv", "run", str(HERE / "transcribe_local_mlx.py"),
           "--output-dir", str(args.out_dir), "--language", args.language]
    cmd += [str(w) for w in args.inputs]
    run(cmd, timeout=timeout)


def diarize_all(wavs, out_dir, device, force):
    """Leg 3: pyannote pipeline loaded ONCE, run per file (cached — not a
    per-wav reload, which the old loop did and which cost 10-30s/file)."""
    try:
        from diarize_speakers import load_pipeline, run_pipeline, write_diarization_json
    except Exception as e:
        _hint_import_error(e)
    pending = [(w, out_dir / f"{w.stem}.diarization.json") for w in wavs
               if force or not (out_dir / f"{w.stem}.diarization.json").exists()]
    if not pending:
        log("Leg 3 (diarization): all cached")
        return
    try:
        pipeline, dev = load_pipeline(device)
    except Exception as e:
        if _is_pyannote_access_error(e):
            log(f"pyannote access error: {e}")
            log(PYANNOTE_SETUP_HINT)
            sys.exit(3)
        raise
    for wav, diar_json in pending:
        try:
            segments = run_pipeline(pipeline, wav, dev)
        except Exception as e:
            if _is_pyannote_access_error(e):
                log(f"pyannote access error on {wav.name}: {e}")
                log(PYANNOTE_SETUP_HINT)
                sys.exit(3)
            log(f"WARNING: diarization failed for {wav.name} ({e}); skipping")
            continue
        write_diarization_json(segments, wav, dev, diar_json)


def _run_batched_leg(wavs, work_root, script, staging_name, staging_suffix,
                     dest_for, extra_args, force, timeout, cache_label, missing_label):
    """Shared staging+move ceremony for legs 1 and 2: run `script` once on all
    uncached inputs (it writes flat <stem><staging_suffix> into a staging dir),
    then move each output to dest_for(stem). One model load per leg, not per file."""
    todo = [w for w in wavs if force or not dest_for(w.stem).exists()]
    if not todo:
        log(f"{cache_label}: all cached")
        return
    staging = work_root / staging_name
    cmd = ["uv", "run", str(HERE / script), "--output-dir", str(staging)] + extra_args + [str(w) for w in todo]
    run(cmd, timeout=timeout)
    for w in todo:
        staged = staging / f"{w.stem}{staging_suffix}"
        if not staged.exists():
            log(f"WARNING: {missing_label} {w.name} — alignment will fail for this file")
            continue
        dest = dest_for(w.stem)
        dest.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(dest)


def leg_text(wavs, work_root, language, force, timeout):
    """Leg 1: full-audio Qwen3 transcript (one model load for the batch)."""
    # transcribe_local_mlx.py writes flat <stem>.txt into --output-dir; stage then
    # move to work_root/<stem>/<stem>.qwen.txt (different name — the .qwen. prefix).
    _run_batched_leg(
        wavs, work_root, "transcribe_local_mlx.py", "_qwen", ".txt",
        dest_for=lambda stem: work_root / stem / f"{stem}.qwen.txt",
        extra_args=["--language", language], force=force, timeout=timeout,
        cache_label="Leg 1 (Qwen3 full text)", missing_label="no Qwen3 transcript for")


def leg_words(wavs, work_root, language, initial_prompt, force, timeout):
    """Leg 2: whisper word lattice, one model load for the whole batch."""
    extra = ["--language", _whisper_lang(language)]  # ALWAYS forward the real language (fixes silent-zh-on-English)
    if initial_prompt:
        extra += ["--initial-prompt", initial_prompt]
    _run_batched_leg(
        wavs, work_root, "word_timestamps_whisper.py", "_words", ".words.json",
        dest_for=lambda stem: work_root / stem / f"{stem}.words.json",
        extra_args=extra, force=force, timeout=timeout,
        cache_label="Leg 2 (whisper word lattice)", missing_label="no word lattice for")


def leg_align(wavs, out_dir, work_root, max_gap, text_file=None):
    """Leg 4: attach speakers to full text, write the output contract.
    Per-file resilient — one bad file is recorded as failed, not a batch crash;
    an untrustworthy alignment is NOT written (would ship fake timestamps)."""
    from align_speakers import align, write_outputs, MIN_ANCHOR_RATIO

    failed = []
    for wav in wavs:
        stem = wav.stem
        diar_json = out_dir / f"{stem}.diarization.json"
        wpath = work_root / stem / f"{stem}.words.json"
        tpath = Path(text_file) if text_file else work_root / stem / f"{stem}.qwen.txt"
        missing = [p for p in (diar_json, wpath, tpath) if not p.exists()]
        if missing:
            log(f"ERROR {stem}: missing {[str(p) for p in missing]} — cannot align")
            failed.append(stem)
            continue
        try:
            qwen_text = tpath.read_text(encoding="utf-8")
            words = json.loads(wpath.read_text(encoding="utf-8"))["words"]
            segments = json.loads(diar_json.read_text(encoding="utf-8"))["segments"]
            turns, report = align(qwen_text, words, segments, max_gap)
        except Exception as e:
            log(f"ERROR {stem}: alignment failed ({e}) — skipped")
            failed.append(stem)
            continue
        log(f"{stem}: {report['num_turns']} turns, speakers={report['speakers']}, "
            f"anchored_ratio={report['anchored_ratio']}")
        if not report["trustworthy"]:
            log(f"SKIP {stem}: anchored_ratio {report['anchored_ratio']} < {MIN_ANCHOR_RATIO} — "
                "transcripts diverge too heavily; NOT writing speaker-labeled output "
                "(it would be garbage). Re-check audio/text pairing or ASR quality.")
            failed.append(stem)
            continue
        write_outputs(turns, report, wav.name, out_dir, stem)
    if failed:
        log(f"FAILED/skipped files: {failed}")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Decoupled multi-speaker transcription")
    ap.add_argument("inputs", nargs="+", type=Path, help="16kHz mono WAV(s)")
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--device", default=None, help="mps / cuda / cpu (default: auto)")
    ap.add_argument("--max-gap", type=float, default=2.0, help="turn split gap (s)")
    ap.add_argument("--language", default="Chinese")
    ap.add_argument("--initial-prompt", default=None,
                    help="Domain terms to prime whisper timing recognition")
    ap.add_argument("--no-diarization", action="store_true",
                    help="plain-text fast path: Qwen3 full text only, no speakers")
    ap.add_argument("--text-file", default=None,
                    help="skip leg 1; align ONE pre-made transcript (single input only)")
    ap.add_argument("--force", action="store_true", help="redo cached intermediate legs")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="per-leg subprocess timeout in seconds (default 1800)")
    args = ap.parse_args()

    # The flat output contract (<stem>.txt/.csv/.diarization.json) keys on stem
    # alone, so duplicate stems can't be disambiguated — refuse rather than
    # silently overwrite one file's output with another's.
    stems = [w.stem for w in args.inputs]
    if len(set(stems)) != len(stems):
        dups = sorted({s for s in stems if stems.count(s) > 1})
        log(f"ERROR: duplicate file stems {dups} — outputs collide on <stem>. "
            "Rename the files to unique names before batching.")
        sys.exit(2)
    # --text-file is one transcript for one wav; with multiple inputs every wav
    # would be aligned against the same text (silent garbage).
    if args.text_file and len(args.inputs) > 1:
        log("ERROR: --text-file aligns ONE pre-made transcript to ONE wav; "
            "pass a single input with it (not a batch).")
        sys.exit(2)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.no_diarization:
        plain_text_path(args, args.timeout)
        log("Done (plain-text fast path, no speaker labels).")
        return

    # pyannote-missing state machine (implemented; see module docstring).
    if not _hf_token_present():
        if _read_config().get("diarization_declined"):
            log(DIARIZATION_DISABLED_BANNER)
            plain_text_path(args, args.timeout)
            log("Done (plain text — diarization disabled; see warning above).")
            return
        log(PYANNOTE_SETUP_HINT)
        sys.exit(3)

    work_root = args.out_dir / "_align"
    work_root.mkdir(parents=True, exist_ok=True)

    diarize_all(args.inputs, args.out_dir, args.device, args.force)
    if args.text_file:
        log("Leg 1 skipped (--text-file)")
    else:
        leg_text(args.inputs, work_root, args.language, args.force, args.timeout)
    leg_words(args.inputs, work_root, args.language, args.initial_prompt, args.force, args.timeout)
    leg_align(args.inputs, args.out_dir, work_root, args.max_gap, args.text_file)
    log("Done.")


if __name__ == "__main__":
    main()
