#!/usr/bin/env python3
"""Voiceprint matching: retain speaker-name candidates without relabeling audio.

Uses CAM++ (iic/speech_campplus_sv_zh-cn_16k-common, 192-dim) speaker embeddings.
funasr auto-downloads the model from ModelScope on first run.

Two modes:
  enroll  Build a reference centroid for a named person from clean audio spans,
          and add/update it in a reference JSON.
  match   For a diarized recording, embed each SPEAKER_xx (from its longest turns)
          and match against the reference set. A candidate clears the old gates when
          cosine >= --threshold AND (best - second_best) >= --margin, so an
          unknown person stays anonymous instead of being forced onto the
          nearest name. These gates are not calibrated identity confirmation.
          Save a source-bound candidate report; never rewrite speaker labels.

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

match also accepts --refs daudio://context/BANK/versions/N --refs-scope DOMAIN.
The user profile selected by DAYMADE_AUDIO_CONFIG, or otherwise
$XDG_CONFIG_HOME/daymade-audio/config.json (default ~/.config), must declare
identity_bank_reader={"protocol":1,"argv":["your-reader","identity-read"]}.
The reader receives URI, --scope, --model-fingerprint and --embedding-dim;
it must validate the pinned bank and return a JSON view containing native.
There is no local-file fallback for a failed reader. Native legacy names and
similarity gates remain candidate evidence, not calibrated identity confirmation.
"""
# /// script
# requires-python = ">=3.10,<3.12"
# dependencies = ["funasr", "numba>=0.60", "torch", "torchaudio", "soundfile", "numpy", "scipy"]
# ///
# NOTE: requires-python is pinned <3.12 on purpose. funasr pulls
# umap-learn -> pynndescent -> numba/llvmlite; on Python 3.13 uv backtracks to an
# ancient llvmlite (0.36.0, source-build, fails), while 3.10/3.11 resolve modern
# llvmlite (0.47) from wheels. `numba>=0.60` forces that modern, wheel-backed stack.
# Verified: on 3.11 uv resolves llvmlite 0.47 / numba 0.65 from wheels (no source build).
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
import urllib.request
import urllib.parse
from pathlib import Path

os.environ.setdefault("TQDM_DISABLE", "1")
import numpy as np

MODEL = "iic/speech_campplus_sv_zh-cn_16k-common"
FINGERPRINT = "campplus_sv_zh-cn_16k-common"
DIM = 192
MAX_CHUNK_S = 10.0
MIN_CHUNK_S = 0.5


def log(m):
    print(m, file=sys.stderr, flush=True)


def load_audio_16k(path):
    """Decode any format to 16k mono float32 via ffmpeg (robust to wav/ogg/opus)."""
    import soundfile as sf
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


def _bank_uri(value):
    return str(value).startswith("daudio:")


def _check_bank_reference(uri, scope):
    if not re.fullmatch(r"daudio://context/[A-Za-z0-9][A-Za-z0-9._~-]{0,127}/versions/[1-9][0-9]*", uri):
        raise ValueError("--refs requires a pinned daudio context bank URI (.../versions/N)")
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError("--refs-scope is required with a daudio bank URI")


class ReferenceBank(dict):
    """Keep the reader's source claims alongside its unchanged native matcher shape."""

    def __init__(self, native, evidence):
        super().__init__(native)
        self.evidence = evidence


def _profile():
    explicit = os.environ.get("DAYMADE_AUDIO_CONFIG")
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = Path(explicit).expanduser() if explicit is not None else root / "daymade-audio/config.json"
    if not path.exists() and explicit is None:
        return {}
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("audio profile must be an object")
    return config


def _file_evidence(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"uri": path.as_uri(), "sha256": digest.hexdigest(), "size_bytes": path.stat().st_size}


def _evaluate_candidates(voice):
    """Use the common evaluator for diagnostics, never as trusted decision readback."""
    try:
        api = _profile().get("api")
        if api is None:
            return {"status": "unavailable", "reasons": ["identity_evaluator_not_configured"]}
        if not isinstance(api, dict):
            raise ValueError("invalid api configuration")
        endpoint = api.get("endpoint")
        parsed = urllib.parse.urlsplit(endpoint if isinstance(endpoint, str) else "")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("invalid api.endpoint")
        headers = {"Content-Type": "application/json"}
        token_env = api.get("token_env", "DAUDIO_API_TOKEN")
        if not isinstance(token_env, str) or not token_env:
            raise ValueError("invalid api.token_env")
        token = os.environ.get("DAUDIO_API_TOKEN") or os.environ.get(token_env)
        if token:
            headers["Authorization"] = "Bearer " + token
        body = json.dumps({"voice_evidence": voice, "policy": None}).encode("utf-8")
        request = urllib.request.Request(endpoint.rstrip("/") + "/v1/identity/evaluate", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ValueError("invalid evaluator response")
        return {"status": "evaluated", "result": result, "trusted_decision_readback": False}
    except (OSError, ValueError, TypeError):
        # A diagnostic service outage must not lose the native candidates or trigger inference again.
        return {"status": "unavailable", "reasons": ["identity_evaluator_failed"]}


def _read_bank(uri, scope):
    """Delegate bank validation to the user's reader; retain native legacy labels."""
    _check_bank_reference(uri, scope)
    try:
        config = _profile()
        reader = config.get("identity_bank_reader") if isinstance(config, dict) else None
    except (OSError, ValueError) as error:
        raise ValueError("Configure identity_bank_reader in the audio user profile to read daudio refs") from error
    if (not isinstance(reader, dict) or type(reader.get("protocol")) is not int
            or reader["protocol"] != 1 or not isinstance(reader.get("argv"), list)
            or not reader["argv"] or any(not isinstance(arg, str) or not arg or "\0" in arg
                                         for arg in reader["argv"])):
        raise ValueError("identity_bank_reader requires protocol=1 and a nonempty literal argv array")
    command = [*reader["argv"], uri, "--scope", scope,
               "--model-fingerprint", FINGERPRINT, "--embedding-dim", str(DIM)]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, check=False)
    except OSError as error:
        raise ValueError("Configured identity bank reader could not execute") from error
    if result.returncode != 0:
        raise ValueError(f"Identity bank reader failed (exit {result.returncode}); no local-file fallback")
    try:
        view = json.loads(result.stdout)
        native = view["native"]
        if not isinstance(native, dict) or not isinstance(native.get("centroids"), dict):
            raise ValueError("native bank lacks centroids")
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("Identity bank reader returned no native voiceprint bank") from error
    return ReferenceBank(native, {"uri": uri, "scope": scope, "reader_view": view,
                                 "reader_sha256": hashlib.sha256(result.stdout).hexdigest()})


def load_refs(path, *, scope=None):
    if _bank_uri(path):
        return _read_bank(str(path), scope)
    p = Path(path)
    if p.exists():
        return ReferenceBank(json.loads(p.read_text(encoding="utf-8")), _file_evidence(p))
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
    Path(args.refs).parent.mkdir(parents=True, exist_ok=True)
    Path(args.refs).write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Enrolled '{args.name}' from {len(embs)} spans -> {args.refs} "
        f"(now: {list(refs['centroids'])})")


def cmd_match(model, args):
    sources = {"audio": _file_evidence(args.audio), "diarization": _file_evidence(args.diar)}
    if args.csv:
        sources["csv"] = _file_evidence(args.csv)
        receipt = Path(args.csv).with_suffix(".receipt.json")
        if receipt.is_file():
            sources["receipt"] = _file_evidence(receipt)
    refs = args._resolved_refs if hasattr(args, "_resolved_refs") else load_refs(args.refs, scope=getattr(args, "refs_scope", None))
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

    bank_evidence = dict(getattr(refs, "evidence", {}))
    # Preserve the complete source view in memory; reports reference it without copying biometric vectors.
    view = bank_evidence.pop("reader_view", {})
    bank = view.get("bank", {}) if isinstance(view, dict) else {}
    bank_evidence["bank_ref"] = {key: bank[key] for key in ("uri", "version", "version_uri") if key in bank}
    bank_metadata = bank.get("metadata", {})
    bank_evidence["source_claims"] = {key: bank_metadata[key] for key in ("identity_status", "source_ref", "model_space") if key in bank_metadata}
    bank_evidence["reader_claims"] = {key: view[key] for key in ("voice_identity_verified", "cross_record_identity", "identity_status") if key in view}
    bank_evidence["member_claims"] = [{key: item[key] for key in ("native_id", "status", "identity_status", "person_ref", "voiceprint_ref") if key in item}
                                      for item in view.get("members", []) if isinstance(item, dict)]
    candidates = []
    for spk, ss in by_spk.items():
        ss = sorted(ss, key=lambda x: -(x["end"] - x["start"]))[:30]
        embs = [embed_span(model, wav, sr, int(s["start"] * sr), int(s["end"] * sr)) for s in ss]
        embs = [e for e in embs if e is not None]
        if not embs:
            candidates.append({"original_speaker": spk, "status": "unknown", "candidates": [],
                               "reasons": ["no_usable_embeddings"]})
            continue
        c = centroid(embs)
        sims = ref_mat @ c
        order = np.argsort(sims)
        best, second = float(sims[order[-1]]), (float(sims[order[-2]]) if len(order) > 1 else None)
        gap = best - second if second is not None else None
        name = names[int(order[-1])]
        ok = best >= args.threshold and (gap is None or gap >= args.margin)
        log(f"  {spk}: candidate only (sim={best:.3f}); labels unchanged")
        ranked = [{"native_label": names[int(i)], "score": float(sims[i])} for i in reversed(order)]
        voice = {"model_fingerprint": refs.get("model_fingerprint"), "embedding_dim": refs.get("embedding_dim"),
                 "acoustic_domain": getattr(args, "refs_scope", None), "candidates": ranked}
        candidates.append({"original_speaker": spk, "status": "candidate", "candidate_label": name,
                           "score": best, "margin": gap, "runner_up_missing": second is None,
                           "passes_native_gates": bool(ok), "candidates": ranked,
                           "spans": [{"start": s["start"], "end": s["end"]} for s in ss],
                           "reasons": ["similarity_is_not_identity_confirmation", "missing_verified_identity_decision"],
                           "common_evaluation": _evaluate_candidates(voice)})

    for source in sources.values():
        if _file_evidence(urllib.request.url2pathname(urllib.parse.urlsplit(source["uri"]).path)) != source:
            raise ValueError("source changed during voiceprint matching; candidates cannot be bound")
    report = {"schema": "voiceprint-candidates/v1", "mapping": {}, "labels_changed": False,
              "bank": bank_evidence, "sources": sources, "candidates": candidates,
              "threshold": args.threshold, "margin": args.margin,
              "identity_confirmation": "unverified"}
    # Separate, exclusive artifact: existing human labels and committed bundle receipts remain byte-identical.
    anchor = Path(args.csv or args.diar)
    destination = anchor.with_name(anchor.stem + ".voiceprint-candidates." + uuid.uuid4().hex + ".json")
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(encoded)
    report["candidate_artifact"] = str(destination.resolve())
    print(json.dumps(report, ensure_ascii=False))


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
    m.add_argument("--refs", required=True, help="Local reference JSON or pinned daudio://context/BANK/versions/N")
    m.add_argument("--refs-scope", help="Required scope for a pinned daudio context bank; local JSON remains unchanged")
    m.add_argument("--audio", required=True)
    m.add_argument("--diar", required=True, help="diarization JSON (from diarize_speakers.py)")
    m.add_argument("--csv", default=None, help="optional unchanged CSV to bind the candidate report to")
    m.add_argument("--threshold", type=float, default=0.45)
    m.add_argument("--margin", type=float, default=0.05)
    args = ap.parse_args()
    if _bank_uri(args.refs):
        if args.mode != "match":
            ap.error("enroll writes a local JSON file; daudio bank URIs are read-only match inputs")
        try:
            _check_bank_reference(args.refs, args.refs_scope)
        except ValueError as error:
            ap.error(str(error))

    from external_dispatch import dispatch_cli
    dispatch_cli(f"voiceprint.{args.mode}", __file__, args,
                 stdout={"kind": "context", "role": "raw_voiceprint_candidate_mapping"} if args.mode == "match" else None)
    if _bank_uri(args.refs):
        try:
            args._resolved_refs = load_refs(args.refs, scope=args.refs_scope)
        except ValueError as error:
            ap.error(str(error))
    from funasr import AutoModel
    model = AutoModel(model=MODEL, device=args.device, disable_update=True)
    (cmd_enroll if args.mode == "enroll" else cmd_match)(model, args)


if __name__ == "__main__":
    main()
