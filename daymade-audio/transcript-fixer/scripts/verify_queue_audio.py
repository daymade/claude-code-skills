#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""verify_queue_audio.py — 批量 pending 音频交叉核验（第二引擎双窗口识别）。

对某转写文件在 review queue 里的 pending 项，逐项从源音频剪 tight/medium
双片段，送已授权的第二识别引擎交叉识别，输出对照表供裁决。

典型场景：Native pass 后积压的 pending（实体/疑词）——本地检索阶梯已尽，
用第二引擎补充音证，再通过独立的裁定路径处理队列。

用法（已核准媒体位置和邻接词）：
  uv run scripts/verify_queue_audio.py \
    --transcript /abs/path/meeting.md \
    --audio /abs/path/source.wav \
    --time-overrides /abs/path/verified-times.json \
    --engine-script /abs/path/stdout_recognizer.py \
    --outdir /abs/path/audio-evidence

输出：<outdir>/results.json；相同音频片段不调用 ASR，结果标记 same_clip。
未核准邻接词或切片未覆盖它们时不附音证，退出 1；核准位置通过
--time-overrides JSON 指定，seconds 使用源媒体轴，不再乘 --speed。
脚本只附加符合条件的音证，不写裁决；逐项裁决见 references/advanced_correction_evidence.md。
依赖：ffmpeg/ffprobe；stdout 引擎，或 asr-transcribe-to-text 的本地 MLX 文件输出引擎。
"""
import argparse, datetime, hashlib, json, math, os, re, subprocess, sys, tempfile
from pathlib import Path

TS_RE = re.compile(r'^(\S+) (\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*$')
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(SKILL_DIR, "fix_transcription.py")
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)
from fetch_minute_audio import audio_duration_seconds


def parse_turns(lines):
    """解析转写为 turns: [(start_line, ts_seconds, speaker, text)]"""
    turns, cur_start, cur_ts, cur_spk, cur_text = [], None, None, None, []
    for i, line in enumerate(lines, start=1):
        m = TS_RE.match(line)
        if m:
            if cur_start is not None:
                turns.append((cur_start, cur_ts, cur_spk, " ".join(cur_text)))
            cur_start = i
            cur_spk = m.group(1)
            cur_ts = int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4)) + int(m.group(5)) / 1000
            cur_text = []
        elif cur_start is not None and line.strip():
            cur_text.append(line.strip())
    if cur_start is not None:
        turns.append((cur_start, cur_ts, cur_spk, " ".join(cur_text)))
    return turns


def _selected_position(text, original, context, context_offset):
    """Identify one verbatim slot; an offset is relative to its recorded context."""
    if not original:
        raise ValueError("empty original cannot identify an audio anchor")
    if context_offset is not None:
        if not isinstance(context, str) or not context \
                or not isinstance(context_offset, int) or isinstance(context_offset, bool) \
                or context_offset < 0 \
                or context[context_offset:context_offset + len(original)] != original:
            raise ValueError("recorded context_offset does not identify the original token")

    def positions(needle, haystack):
        return [m.start() for m in re.finditer(f"(?={re.escape(needle)})", haystack)]

    if context:
        if not isinstance(context, str):
            raise ValueError("recorded context must be text")
        slots = [context_offset] if context_offset is not None else positions(original, context)
        candidates = {start + slot for start in positions(context, text) for slot in slots}
    else:
        candidates = set(positions(original, text))
    if len(candidates) != 1:
        raise ValueError("audio anchor is missing or ambiguous; re-anchor the queue item first")
    return candidates.pop()


def token_offset(turns, line_no, original, transcript_duration=None, *, context=None, context_offset=None, lines=None):
    """Estimate the selected slot's time; never choose the first repeated token."""
    indices = [j for j, t in enumerate(turns) if t[0] < line_no]
    if not indices:
        raise ValueError("audio anchor does not point into a speaker turn")
    idx = indices[-1]
    start_line, ts, spk, text = turns[idx]
    if lines is None:
        pos = _selected_position(text, original, context, context_offset)
    else:
        if line_no > len(lines) or not lines[line_no - 1].strip() \
                or TS_RE.match(lines[line_no - 1]):
            raise ValueError("audio anchor is not a transcript body line")
        line = lines[line_no - 1]
        local = _selected_position(line, original, context, context_offset)
        prefix = sum(len(value.strip()) + 1 for value in lines[start_line:line_no - 1]
                     if value.strip())
        pos = prefix + local - (len(line) - len(line.lstrip()))
    if idx + 1 < len(turns):
        dur = turns[idx + 1][1] - ts
    else:
        if transcript_duration is None:
            return None
        dur = transcript_duration - ts
    if not math.isfinite(dur) or dur <= 0:
        return None
    return ts + (pos / max(len(text), 1)) * dur


def media_duration(audio):
    """Read the media clock; unavailable duration remains unknown."""
    duration, _ = audio_duration_seconds(Path(audio))
    return duration


def load_time_overrides(path):
    """Media seconds and independently checked neighbouring words, keyed by row ID."""
    if not path:
        return {}
    with open(path, encoding="utf-8") as stream:
        records = json.load(stream)
    if not isinstance(records, dict):
        raise ValueError("time overrides must be an object keyed by queue ID")
    for key, value in records.items():
        if not key.isdecimal() or not isinstance(value, dict):
            raise ValueError("each override must bind a queue ID to an object")
        seconds, anchors = value.get("seconds"), value.get("anchors")
        if (isinstance(seconds, bool) or not isinstance(seconds, (float, int))
                or not math.isfinite(seconds) or seconds < 0):
            raise ValueError(f"override {key}: seconds must be finite media seconds >= 0")
        if (not isinstance(anchors, list) or not anchors
                or any(not isinstance(word, str) or not normalize(word) for word in anchors)):
            raise ValueError(f"override {key}: nonempty neighbouring-word anchors are required")
    return records


def normalize(value):
    return "".join(char for char in (value or "") if char.isalnum())


def evidence_status(result):
    """Observe coverage separately from disagreements; never record a verdict."""
    if result.get("same_clip"):
        return "same_clip"
    if result.get("tight_exit") or result.get("medium_exit"):
        return "engine_failed"
    anchors = result.get("anchors") or []
    if not anchors:
        return "coverage_unknown"
    texts = [normalize(result.get(window)) for window in ("tight", "medium")]
    if any(not all(normalize(anchor) in text for anchor in anchors) for text in texts):
        return "needs_reanchor"
    if both_windows_support_suggestion(result):
        return "suggestion_supported"
    original = normalize(result.get("original"))
    if original and all(original in text for text in texts):
        return "original_supported"
    suggestion = normalize(result.get("suggested"))
    readings = [(bool(original and original in text), bool(suggestion and suggestion in text))
                for text in texts]
    return "recognizer_disagreement" if readings[0] != readings[1] else "unsettled_reading"


def list_pending(transcript, queue_ids):
    r = subprocess.run(
        ["uv", "run", FIX, "--list-review", "--review-file", transcript,
         "--review-status", "pending", "--json"],
        capture_output=True, text=True, cwd=SKILL_DIR)
    if r.returncode != 0:
        sys.exit(f"list-review failed: {r.stderr[:300]}")
    items = json.loads(r.stdout)["items"]
    if queue_ids:
        items = [it for it in items if it["id"] in queue_ids]
    return items


def both_windows_support_suggestion(result):
    """Require a delimited candidate with the same following context in both cuts."""
    normalize = lambda value: "".join(
        char for char in (value or "") if char.isalnum())
    suggestion = normalize(result.get("suggested"))
    original = normalize(result.get("original"))
    if result.get("same_clip") or not suggestion or not original or suggestion == original \
            or result.get("tight_exit") or result.get("medium_exit"):
        return False
    boundaries = []
    for window in ("tight", "medium"):
        raw = result.get(window) or ""
        recognized = normalize(raw)
        if original in recognized:
            return False
        if all("\u3400" <= char <= "\u9fff" for char in suggestion):
            raw_hits = list(re.finditer(re.escape(suggestion), raw))
            if not raw_hits or any(
                    raw[match.end():].lstrip()
                    and "\u3400" <= raw[match.end():].lstrip()[0] <= "\u9fff"
                    for match in raw_hits):
                return False
        matches = {
            recognized[pos + len(suggestion):pos + len(suggestion) + 1]
            for pos in range(len(recognized))
            if recognized.startswith(suggestion, pos)
        }
        if len(matches) != 1:
            return False
        boundaries.append(matches.pop())
    return boundaries[0] == boundaries[1]


def same_clip_bytes(first, second):
    if os.path.getsize(first) != os.path.getsize(second):
        return False
    def digest(path):
        with open(path, "rb") as stream:
            return hashlib.sha256(stream.read()).digest()
    return digest(first) == digest(second)


def file_sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") \
            else hashlib.sha256(stream.read()).hexdigest()


def source_fingerprint(path):
    """Bind path, inode, change clocks and bytes; reject changes during hashing."""
    source = Path(path).resolve()
    def state():
        st = source.stat()
        return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]
    before = state()
    digest = file_sha256(source)
    if before != state() or Path(path).resolve() != source:
        raise ValueError("source audio changed while checking its identity")
    return [str(source), *before, digest]


def source_error(path, expected):
    if expected is None:
        return ""
    try:
        if source_fingerprint(path) != expected:
            return "source audio changed during evidence collection; retain pending and retry from the verified source"
    except (OSError, ValueError) as exc:
        return f"source audio identity unavailable: {exc}"
    return ""


def read_mlx_output(clip, output_dir, engine_script):
    """Read a completed producer receipt, never stdout or an old unbound .txt."""
    clip, output_dir = Path(clip).resolve(), Path(output_dir).resolve()
    output = output_dir / (clip.stem + ".txt")
    manifests = list((output_dir / "_mlx_checkpoints").glob(clip.stem + "-*/manifest.json"))
    if len(manifests) != 1:
        raise ValueError("expected exactly one local MLX completion manifest for this clip")
    manifest_path = manifests[0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("MLX manifest must be an object")
    producer = manifest.get("producer")
    chunks = manifest.get("chunks")
    revision, device = manifest.get("model_revision"), manifest.get("execution_device")
    if manifest.get("schema_version") != 2 or manifest.get("status") != "complete" \
            or manifest.get("source") != str(clip) \
            or manifest.get("source_sha256") != file_sha256(clip) \
            or manifest.get("source_size") != clip.stat().st_size \
            or not isinstance(producer, dict) \
            or producer.get("sha256") != file_sha256(engine_script) \
            or not isinstance(manifest.get("model"), str) or not manifest["model"].strip() \
            or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision) \
            or not isinstance(device, str) or "gpu" not in device.lower() \
            or not isinstance(chunks, list) or not chunks \
            or type(manifest.get("chunk_count")) is not int \
            or manifest["chunk_count"] != len(chunks) \
            or any(not isinstance(chunk, dict) or chunk.get("status") != "done" for chunk in chunks) \
            or manifest.get("output") != str(output):
        raise ValueError("MLX result has incomplete or mismatched source/model/GPU/producer identity")
    text = output.read_text(encoding="utf-8")
    if not text.strip() or manifest.get("output_sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest():
        raise ValueError("MLX transcript is empty or does not match its completion manifest")
    return text.strip(), {
        "format": "mlx-file", "text_file": str(output), "manifest": str(manifest_path),
        "source_sha256": manifest["source_sha256"], "output_sha256": manifest["output_sha256"],
        "model": manifest["model"], "model_revision": revision, "execution_device": device,
        "producer_sha256": producer["sha256"],
    }


def recognize_mlx_pair(engine_script, tight, medium, outdir):
    """Run the existing owner once for two cuts, retaining all results and logs."""
    output_dir = Path(tempfile.mkdtemp(prefix="mlx-", dir=outdir)).resolve()
    command = ["uv", "run", str(Path(engine_script).resolve()),
               str(Path(tight).resolve()), str(Path(medium).resolve()),
               "--output-dir", str(output_dir)]
    # This route reuses an available pinned local model; preparation belongs to ASR.
    env = {**os.environ, "HF_HUB_OFFLINE": "1"}
    try:
        run = subprocess.run(command, capture_output=True, text=True, env=env)
    except OSError as exc:
        run = subprocess.CompletedProcess(command, 1, "", str(exc))
    (output_dir / "stdout.log").write_text(run.stdout or "", encoding="utf-8")
    (output_dir / "stderr.log").write_text(run.stderr or "", encoding="utf-8")
    outputs = []
    for clip in (tight, medium):
        try:
            if run.returncode:
                raise ValueError(f"local MLX runner exited {run.returncode}; inspect {output_dir}/stderr.log")
            text, provenance = read_mlx_output(clip, output_dir, engine_script)
            outputs.append((text, 0, provenance, ""))
        except (OSError, UnicodeError, ValueError) as exc:
            outputs.append(("", run.returncode or 1, {"format": "mlx-file", "output_dir": str(output_dir)}, str(exc)))
    return outputs


def main():
    ap = argparse.ArgumentParser(description="批量 pending 音频交叉核验（第二引擎双窗口识别）")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--speed", type=float, default=1.0,
                    help="转写时间轴→音频轴倍速；经证据核准的源时长/平台时长，同一时间轴默认 1")
    ap.add_argument("--queue-ids", default="", help="逗号分隔；默认该文件全部 pending")
    ap.add_argument("--engine-script", required=True,
                    help="已授权的第二识别引擎脚本；格式由 --engine-format 指定")
    ap.add_argument("--engine-format", choices=("stdout", "mlx-file"), default="stdout",
                    help="stdout: 原有纯文本接口；mlx-file: 本地 MLX .txt+完成清单（离线缓存/GPU）")
    ap.add_argument("--outdir", default="/tmp/asr-verify")
    ap.add_argument("--tight", type=float, default=5.0, help="tight 窗 ±秒（默认 5）")
    ap.add_argument("--medium", type=float, default=20.0, help="medium 窗 ±秒（默认 20）")
    ap.add_argument("--time-overrides", help="JSON: queue ID -> {seconds: 媒体轴秒, anchors: [已核准邻接词]}；不再乘 --speed")
    a = ap.parse_args()
    if not all(math.isfinite(x) for x in (a.tight, a.medium, a.speed)) or a.speed <= 0:
        ap.error("speed and window sizes must be finite; --speed must be positive")
    if a.tight <= 0 or a.medium <= a.tight:
        ap.error("--medium must be greater than positive --tight")
    try:
        overrides = load_time_overrides(a.time_overrides)
    except (OSError, ValueError) as error:
        ap.error(str(error))

    os.makedirs(a.outdir, exist_ok=True)
    with open(a.transcript, encoding="utf-8") as transcript_file:
        lines = transcript_file.read().splitlines()
    turns = parse_turns(lines)
    if not turns:
        sys.exit("no speaker turns parsed — 转写需含「说话人 HH:MM:SS.mmm」行")
    ids = {int(x) for x in a.queue_ids.split(",") if x.strip()} if a.queue_ids else None
    items = list_pending(a.transcript, ids)
    if not items:
        sys.exit("no pending items for this file")
    if set(overrides) - {str(item["id"]) for item in items}:
        ap.error("time overrides contain rows outside this file's selected pending items")
    source_before = source_fingerprint(a.audio) if a.engine_format == "mlx-file" else None
    source_identity = ({"source_audio": source_before[0],
                        "source_audio_sha256": source_before[-1]}
                       if source_before is not None else {})
    duration, duration_probed = None, False

    results = []
    for it in items:
        tid = it["id"]
        override = overrides.get(str(tid))
        if override and any(
                normalize(token) and normalize(token) in normalize(anchor)
                for anchor in override["anchors"]
                for token in (it["original_text"], it.get("suggested_text") or "")):
            ap.error(f"override {tid}: anchors must exclude the disputed original/suggestion")
        common = {
            **source_identity,
            "id": tid, "line": it["line_number"], "original": it["original_text"],
            "suggested": it.get("suggested_text") or "", "token_wav_time": None,
            "position_source": "verified_override" if override else "character_estimate",
            "anchors": override["anchors"] if override else [],
        }
        location = {"context": it.get("context_snippet"),
                    "context_offset": it.get("context_offset"), "lines": lines}
        try:
            # Validate the recorded occurrence before probing/cutting any media.
            token_offset(turns, it["line_number"], it["original_text"], **location)
            if not duration_probed:
                duration = media_duration(a.audio)
                duration_probed = True
            estimate = token_offset(
                turns, it["line_number"], it["original_text"],
                duration / a.speed if duration is not None else None, **location)
        except ValueError as exc:
            results.append({**common, "status": "anchor_error", "tight": "", "medium": "",
                            "tight_exit": -1, "medium_exit": -1, "same_clip": False,
                            "anchor_error": str(exc), "err": str(exc)})
            print(f"{tid}: anchor_error, pending", flush=True)
            continue
        tok_t = override["seconds"] if override else (estimate * a.speed if estimate is not None else None)
        common["token_wav_time"] = round(tok_t, 3) if tok_t is not None else None
        if tok_t is None or (duration is not None and tok_t >= duration):
            results.append({**common, "status": "timestamp_unknown", "tight": "", "medium": "",
                            "tight_exit": -1, "medium_exit": -1, "same_clip": False,
                            "err": "no valid media position; provide a verified time override"})
            print(f"{tid}: timestamp_unknown, pending", flush=True)
            continue
        tight = os.path.join(a.outdir, f"{tid}-tight.wav")
        med = os.path.join(a.outdir, f"{tid}-med.wav")
        ranges = {}
        for window, clip, radius in (("tight", tight, a.tight), ("medium", med, a.medium)):
            start = max(tok_t - radius, 0)
            end = min(tok_t + radius, duration) if duration is not None else tok_t + radius
            ranges[window] = [round(start, 3), round(end, 3)]
            subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
                            "-i", a.audio, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", clip],
                           capture_output=True, check=True)
        if same_clip_bytes(tight, med):
            results.append({
                **common, "clip_ranges": ranges, "status": "same_clip",
                "tight": "", "medium": "", "tight_exit": -1, "medium_exit": -1,
                "err": "tight and medium clips have identical bytes; no independent audio evidence",
                "same_clip": True,
            })
            print(f"{tid}: same_clip, pending", flush=True)
            continue
        clip_hashes = {"tight": file_sha256(tight), "medium": file_sha256(med)}
        if a.engine_format == "mlx-file":
            changed_source = source_error(a.audio, source_before)
            readings = ([("", 1, {"format": "mlx-file"}, changed_source)] * 2
                        if changed_source else recognize_mlx_pair(a.engine_script, tight, med, a.outdir))
        else:
            readings = []
            for clip in (tight, med):
                run = subprocess.run(["python3", a.engine_script, clip], capture_output=True, text=True)
                readings.append((run.stdout.strip(), run.returncode or (0 if run.stdout.strip() else 1),
                                 {"format": "stdout"}, run.stderr))
        r1, r2 = readings
        result = {
            **common, "clip_ranges": ranges, "clip_sha256": clip_hashes,
            "tight": r1[0], "medium": r2[0],
            "tight_exit": r1[1], "medium_exit": r2[1],
            "engine_provenance": {"tight": r1[2], "medium": r2[2]},
            "same_clip": False,
            "err": (r1[3] + r2[3])[:400],
        }
        result["status"] = evidence_status(result)
        changed_source = source_error(a.audio, source_before)
        if changed_source:
            result.update(status="engine_failed", source_identity_error=changed_source,
                          tight_exit=1, medium_exit=1)
        results.append(result)
        print(f"{tid}: {result['status']}, pending verdict", flush=True)

    out = os.path.join(a.outdir, "results.json")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=a.outdir, delete=False) as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    os.replace(f.name, out)
    print(f"\n{len(results)} items -> {out}")

    # Different clip bytes and an explicit CJK word boundary are required before
    # agreeing recognizer text can serve as authority.
    # This never records a review verdict.
    attached, unsupported = [], []
    for r in results:
        changed_source = source_error(a.audio, source_before)
        if changed_source:
            r.update(status="engine_failed", source_identity_error=changed_source,
                     tight_exit=1, medium_exit=1)
        sug = (r.get("suggested") or "").strip()
        if not sug:
            continue
        if r["status"] == "suggestion_supported":
            text = (f"音证 {datetime.date.today().isoformat()}：token≈{r['token_wav_time']}s，"
                    f"tight 窗识别「{(r.get('tight') or '')[:80]}」"
                    f"/ medium 窗「{(r.get('medium') or '')[:80]}」均含建议词「{sug[:40]}」"
                    f"（verify_queue_audio 双窗口、邻接词及右边界一致；"
                    f"邻接词：{r['anchors']}；范围：{r['clip_ranges']}；"
                    f"片段 SHA256：{r['clip_sha256']}；证据文件：{os.path.abspath(out)}；"
                    f"引擎：{r['engine_provenance']}）")
            cp = subprocess.run(
                ["uv", "run", FIX, "--attach-authority", str(r["id"]),
                 "--authority-text", text, "--by", "verify_queue_audio", "--json"],
                capture_output=True, text=True, cwd=SKILL_DIR)
            if cp.returncode == 0:
                attached.append(r["id"])
            else:
                print(f"⚠ attach {r['id']} failed: {cp.stderr[:200]}", file=sys.stderr)
                r["authority_attach_failed"] = True
        else:
            unsupported.append(r["id"])
    if attached:
        print(f"音证已回写 evidence（作为后续裁决的权威源）: {attached}")
    if unsupported:
        print(f"双窗口未一致支持建议词、未回写权威（请读 results.json 自行裁决）: {unsupported}")
    if any(r.get("authority_attach_failed") or r.get("source_identity_error") for r in results):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=a.outdir, delete=False) as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        os.replace(f.name, out)
    if any(r["status"] in {"anchor_error", "timestamp_unknown", "same_clip", "engine_failed",
                           "coverage_unknown", "needs_reanchor"} or r.get("authority_attach_failed")
           for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
