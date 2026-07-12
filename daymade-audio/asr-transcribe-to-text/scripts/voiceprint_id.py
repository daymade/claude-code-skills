#!/usr/bin/env python3
"""Voiceprint speaker identification: map anonymous SPEAKER_xx to real names.

Uses CAM++ (iic/speech_campplus_sv_zh-cn_16k-common, 192-dim) speaker embeddings.
funasr auto-downloads the model from ModelScope on first run.

Two modes:
  enroll  Build a reference centroid for a named person from clean audio spans,
          and add/update it in a reference JSON.
  match   For a diarized recording, embed each SPEAKER_xx (from its longest turns)
          and match against the reference set. A speaker is named only when
          cosine >= --threshold AND (best - second_best) >= --margin, so an
          unknown person stays anonymous instead of being forced onto the
          nearest name. Optionally rewrites the `speaker` column of a CSV.

Reference JSON:
  {"model_fingerprint":"campplus_sv_zh-cn_16k-common","embedding_dim":192,
   "centroids":{"<name>":[192 floats], ...}}

Read references/voiceprint_speaker_id.md first — especially the acoustic-domain
caveat: a voiceprint built from one recording environment (room mic) matches the
SAME person in a different environment (lapel mic / video) far less well, so build
references from the SAME kind of audio you'll identify.

Usage:
  uv run voiceprint_id.py enroll --refs refs.json --name Alice \
      --audio alice.wav --spans "0-30,45-62"
  uv run voiceprint_id.py match --refs refs.json --audio rec.wav \
      --diar rec.diarization.json [--csv rec.csv] [--threshold 0.45] [--margin 0.05]
"""
# /// script
# dependencies = ["funasr", "torch", "torchaudio", "soundfile", "numpy", "scipy"]
# ///
import argparse
import csv as csvmod
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("TQDM_DISABLE", "1")
import numpy as np
import soundfile as sf
from funasr import AutoModel

MODEL = "iic/speech_campplus_sv_zh-cn_16k-common"
FINGERPRINT = "campplus_sv_zh-cn_16k-common"
DIM = 192
MAX_CHUNK_S = 10.0
MIN_CHUNK_S = 0.5


def log(m):
    print(m, file=sys.stderr, flush=True)


def load_audio_16k(path):
    """Decode any format to 16k mono float32 via ffmpeg (robust to wav/ogg/opus)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tmp = tf.name
    try:
        subprocess.run(["ffmpeg", "-y", "-i", str(path), "-vn", "-acodec", "pcm_s16le",
                        "-ar", "16000", "-ac", "1", tmp],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        wav, sr = sf.read(tmp)
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        return np.asarray(wav, dtype=np.float32), sr
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def embed_clip(model, clip):
    """One L2-normalized 192-dim CAM++ embedding, or None."""
    if clip.size == 0:
        return None
    try:
        result = model.generate(input=np.asarray(clip, dtype=np.float32))
    except Exception as e:
        log(f"  embed failed: {e}")
        return None
    if not isinstance(result, list) or not result or "spk_embedding" not in result[0]:
        return None
    emb = result[0]["spk_embedding"]
    if hasattr(emb, "detach"):
        emb = emb.detach().cpu().numpy()
    emb = np.asarray(emb, dtype=np.float32).reshape(-1)
    if emb.size != DIM:
        return None
    n = float(np.linalg.norm(emb))
    return emb / n if np.isfinite(n) and n > 0 else None


def embed_span(model, wav, sr, s_idx, e_idx):
    """Embed a [s_idx:e_idx] slice, chunking long spans (>10s) and averaging."""
    clip = wav[s_idx:e_idx]
    if clip.size == 0:
        return None
    if len(clip) / sr <= MAX_CHUNK_S:
        return embed_clip(model, clip)
    chunk, embs = int(MAX_CHUNK_S * sr), []
    for c in range(0, len(clip), chunk):
        piece = clip[c:min(len(clip), c + chunk)]
        if len(piece) >= MIN_CHUNK_S * sr:
            e = embed_clip(model, piece)
            if e is not None:
                embs.append(e)
    if not embs:
        return None
    v = np.mean(np.stack(embs), axis=0)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else None


def centroid(embs):
    v = np.mean(np.stack(embs), axis=0)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else None


def load_refs(path):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"model_fingerprint": FINGERPRINT, "embedding_dim": DIM, "centroids": {}}


def cmd_enroll(model, args):
    wav, sr = load_audio_16k(args.audio)
    embs = []
    for span in args.spans.split(","):
        a, b = span.split("-")
        e = embed_span(model, wav, sr, int(float(a) * sr), int(float(b) * sr))
        if e is not None:
            embs.append(e)
    if not embs:
        sys.exit("No usable embeddings from the given spans.")
    c = centroid(embs)
    refs = load_refs(args.refs)
    refs["centroids"][args.name] = c.tolist()
    Path(args.refs).write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Enrolled '{args.name}' from {len(embs)} spans -> {args.refs} "
        f"(now: {list(refs['centroids'])})")


def cmd_match(model, args):
    refs = load_refs(args.refs)
    names = list(refs["centroids"])
    if not names:
        sys.exit("Reference set is empty — enroll someone first.")
    ref_mat = np.stack([np.asarray(refs["centroids"][n], dtype=np.float32) for n in names])

    diar = json.loads(Path(args.diar).read_text(encoding="utf-8"))
    segs = diar["segments"] if "segments" in diar else diar
    wav, sr = load_audio_16k(args.audio)

    by_spk = {}
    for s in segs:
        by_spk.setdefault(s["speaker"], []).append(s)

    mapping = {}
    for spk, ss in by_spk.items():
        ss = sorted(ss, key=lambda x: -(x["end"] - x["start"]))[:30]
        embs = [embed_span(model, wav, sr, int(s["start"] * sr), int(s["end"] * sr)) for s in ss]
        embs = [e for e in embs if e is not None]
        if not embs:
            continue
        c = centroid(embs)
        sims = ref_mat @ c
        order = np.argsort(sims)
        best, second = float(sims[order[-1]]), (float(sims[order[-2]]) if len(order) > 1 else -1.0)
        name = names[int(order[-1])]
        ok = best >= args.threshold and (best - second) >= args.margin
        log(f"  {spk}: {'-> ' + name if ok else 'ANON'} (sim={best:.3f} margin={best - second:.3f})")
        if ok:
            mapping[spk] = name

    if args.csv and mapping:
        rows = list(csvmod.DictReader(open(args.csv, encoding="utf-8")))
        if rows:
            fields = list(rows[0].keys())
            for r in rows:
                r["speaker"] = mapping.get(r["speaker"], r["speaker"])
            with open(args.csv, "w", encoding="utf-8", newline="") as f:
                w = csvmod.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)
            log(f"Rewrote speaker column in {args.csv}")
    print(json.dumps(mapping, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="CAM++ voiceprint speaker identification")
    ap.add_argument("--device", default="mps", help="mps / cuda / cpu (default mps)")
    sub = ap.add_subparsers(dest="mode", required=True)

    e = sub.add_parser("enroll")
    e.add_argument("--refs", required=True)
    e.add_argument("--name", required=True)
    e.add_argument("--audio", required=True)
    e.add_argument("--spans", required=True, help='seconds, e.g. "0-30,45-62"')

    m = sub.add_parser("match")
    m.add_argument("--refs", required=True)
    m.add_argument("--audio", required=True)
    m.add_argument("--diar", required=True, help="diarization JSON (from diarize_speakers.py)")
    m.add_argument("--csv", default=None, help="optional CSV whose speaker column to rewrite")
    m.add_argument("--threshold", type=float, default=0.45)
    m.add_argument("--margin", type=float, default=0.05)
    args = ap.parse_args()

    model = AutoModel(model=MODEL, device=args.device, disable_update=True)
    (cmd_enroll if args.mode == "enroll" else cmd_match)(model, args)


if __name__ == "__main__":
    main()
