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
  3. pyannote diarization               (in-process, MPS/CUDA)
  4. align_speakers.py attaches speakers to the Layer-1 text by mapping it
     onto the timed word lattice and the diarization segments.

Outputs per input (flat under OUTPUT_DIR — same contract downstream tools read):
  <stem>.diarization.json   raw pyannote segments
  <stem>.txt                [MM:SS - MM:SS] SPEAKER_xx + text
  <stem>.csv                file,start,end,duration,speaker,text
  <stem>.alignment.json     alignment provenance + anchored_ratio trust signal
Intermediate legs live in OUTPUT_DIR/<stem>.align/ and are reused on re-run
(pass --force to redo them).

Speaker labels are anonymous (SPEAKER_00...). Map them to real names with
voiceprint_id.py — references/voiceprint_speaker_id.md.

Prerequisite: HuggingFace token for pyannote (gated model). On failure this
script prints the exact setup steps and exits non-zero — SKILL.md decides
whether the session continues plain-text.

Usage:
  uv run speaker_transcribe.py INPUT.wav [INPUT2.wav ...] OUTPUT_DIR [options]
  --no-diarization   plain-text fast path (old default): Qwen3 full text only
  --text-file PATH   skip leg 1; align this pre-made transcript (remote ASR text)
  --force            redo intermediate legs even if present
"""
import argparse
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


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def run(cmd, timeout=None):
    log("+ " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, timeout=timeout)


def plain_text_path(args):
    """Old default behavior: full-audio Qwen3 text, no speakers."""
    if args.text_file:
        for wav in args.inputs:
            out = args.out_dir / f"{wav.stem}.txt"
            out.write_text(Path(args.text_file).read_text(encoding="utf-8"), encoding="utf-8")
            log(f"Wrote {out} (from --text-file)")
        return
    cmd = ["uv", "run", str(HERE / "transcribe_local_mlx.py"),
           "--output-dir", str(args.out_dir), "--language", args.language]
    cmd += [str(w) for w in args.inputs]
    run(cmd)


def diarize_all(wavs, out_dir, device, force):
    """Leg 3, in-process: pyannote once for the whole batch."""
    try:
        from diarize_speakers import diarize
    except Exception as e:
        log(f"ERROR importing pyannote stack: {e}")
        log(PYANNOTE_SETUP_HINT)
        sys.exit(3)
    pending = []
    for wav in wavs:
        diar_json = out_dir / f"{wav.stem}.diarization.json"
        if diar_json.exists() and not force:
            log(f"SKIP diarization (exists): {diar_json.name}")
            continue
        pending.append((wav, diar_json))
    for wav, diar_json in pending:
        try:
            diarize(wav, diar_json, device)
        except Exception as e:
            msg = str(e)
            if any(k in msg.lower() for k in ("token", "gated", "401", "403", "unauthorized", "accept")):
                log(f"pyannote access error: {e}")
                log(PYANNOTE_SETUP_HINT)
                sys.exit(3)
            raise


def leg_text(wavs, work_root, language, force):
    """Leg 1: full-audio Qwen3 transcript per file (one model load for the batch)."""
    todo = []
    for wav in wavs:
        tpath = work_root / wav.stem / f"{wav.stem}.qwen.txt"
        if tpath.exists() and not force:
            continue
        todo.append((wav, tpath))
    if not todo:
        log("Leg 1 (Qwen3 full text): all cached")
        return
    # transcribe_local_mlx.py loads the model once for all inputs and writes
    # flat <stem>.txt into --output-dir; stage then move to per-file dirs.
    staging = work_root / "_qwen"
    run(["uv", "run", str(HERE / "transcribe_local_mlx.py"),
         "--output-dir", str(staging), "--language", language]
        + [str(w) for w, _ in todo])
    for wav, tpath in todo:
        staged = staging / f"{wav.stem}.txt"
        if not staged.exists():
            log(f"WARNING: no Qwen3 transcript for {wav.name} — alignment will fail for this file")
            continue
        tpath.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(tpath)


def leg_words(wavs, work_root, language, initial_prompt, force):
    """Leg 2: whisper word lattice, one model load for the whole batch."""
    zh = "zh" if language.lower().startswith("chin") else None
    todo = []
    for wav in wavs:
        wpath = work_root / wav.stem / f"{wav.stem}.words.json"
        if wpath.exists() and not force:
            continue
        todo.append((wav, wpath))
    if not todo:
        log("Leg 2 (whisper word lattice): all cached")
        return
    # word_timestamps_whisper.py writes to a flat --output-dir; stage per-file
    # dirs via a shared staging dir then move.
    staging = work_root / "_words"
    cmd = ["uv", "run", str(HERE / "word_timestamps_whisper.py"),
           "--output-dir", str(staging)]
    if zh:
        cmd += ["--language", zh]
    if initial_prompt:
        cmd += ["--initial-prompt", initial_prompt]
    cmd += [str(w) for w, _ in todo]
    run(cmd)
    for wav, wpath in todo:
        staged = staging / f"{wav.stem}.words.json"
        if not staged.exists():
            log(f"WARNING: no word lattice for {wav.name} — alignment will fail for this file")
            continue
        wpath.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(wpath)


def leg_align(wavs, out_dir, work_root, max_gap, text_file=None):
    """Leg 4: attach speakers to full text, write the output contract."""
    import json
    from align_speakers import align, write_outputs, MIN_ANCHOR_RATIO

    failed = []
    for wav in wavs:
        stem = wav.stem
        diar_json = out_dir / f"{stem}.diarization.json"
        wpath = work_root / stem / f"{stem}.words.json"
        tpath = Path(text_file) if text_file else work_root / stem / f"{stem}.qwen.txt"
        for need in (diar_json, wpath, tpath):
            if not need.exists():
                log(f"ERROR: missing {need} — cannot align {stem}")
                failed.append(stem)
                break
        else:
            qwen_text = tpath.read_text(encoding="utf-8")
            words = json.loads(wpath.read_text(encoding="utf-8"))["words"]
            segments = json.loads(diar_json.read_text(encoding="utf-8"))["segments"]
            turns, report = align(qwen_text, words, segments, max_gap)
            log(f"{stem}: {report['num_turns']} turns, speakers={report['speakers']}, "
                f"anchored_ratio={report['anchored_ratio']}")
            if not report["trustworthy"]:
                log(f"WARNING {stem}: anchored_ratio {report['anchored_ratio']} < "
                    f"{MIN_ANCHOR_RATIO} — transcripts diverge heavily; verify speaker "
                    "labels against the audio before trusting them")
            write_outputs(turns, report, wav.name, out_dir, stem)
    if failed:
        log(f"FAILED files: {failed}")
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
                    help="skip leg 1; align this pre-made transcript (e.g. remote ASR text)")
    ap.add_argument("--force", action="store_true", help="redo cached intermediate legs")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.no_diarization:
        plain_text_path(args)
        log("Done (plain-text fast path, no speaker labels).")
        return

    work_root = args.out_dir / "_align"
    work_root.mkdir(parents=True, exist_ok=True)

    diarize_all(args.inputs, args.out_dir, args.device, args.force)
    if args.text_file:
        log("Leg 1 skipped (--text-file)")
    else:
        leg_text(args.inputs, work_root, args.language, args.force)
    leg_words(args.inputs, work_root, args.language, args.initial_prompt, args.force)
    leg_align(args.inputs, args.out_dir, work_root, args.max_gap, args.text_file)
    log("Done.")


if __name__ == "__main__":
    main()
