#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""verify_queue_audio.py — 批量 pending 音频交叉核验（双引擎片段识别）。

对某转写文件在 review queue 里的 pending 项，逐项从源音频剪 tight/medium
双片段，送第二识别引擎（默认 StepFun）交叉识别，输出对照表供裁决。

典型场景：Native pass 后积压的 pending（实体/疑词）——本地检索阶梯已尽，
用第二引擎的耳朵裁决，而不是把队列推给用户。

用法：
  uv run scripts/verify_queue_audio.py \
    --transcript /abs/path/meeting.md \
    --audio /abs/path/source.wav \
    [--speed 1.3]            # 转写时间轴→音频轴倍速（加速上传的妙记=原始/加速比；反推法：源音频时长/妙记时长）
    [--queue-ids 1817,1818]  # 默认该文件全部 pending
    [--engine-script /abs/stepfun-asr/scripts/asr_transcribe.py]
    [--outdir /tmp/asr-verify]

输出：<outdir>/results.json（每项：id/line/original/suggested/token_wav_time/tight/medium 识别文本）
判读（裁决矩阵，详 references/advanced_correction_evidence.md §批量 pending 音频核验）：
  - 双窗一致且与候选同 → accepted
  - 双窗一致但与候选不同 → 按引擎输出 overridden（或 kept_original 若证明原词无误）
  - 双窗矛盾/空 → 保留 pending，不换方法重复（两窗不一致本身是信号）
依赖：ffmpeg/ffprobe；识别引擎脚本（stdout 出文本）。
"""
import argparse, json, os, re, subprocess, sys

TS_RE = re.compile(r'^(\S+) (\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*$')
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(SKILL_DIR, "fix_transcription.py")


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


def token_offset(turns, line_no, original):
    """行号→turn→token 字符比例偏移（转写轴秒）。turn 时长=下一 turn 起点差。"""
    idx = max(j for j, t in enumerate(turns) if t[0] <= line_no)
    start_line, ts, spk, text = turns[idx]
    if idx + 1 < len(turns):
        dur = turns[idx + 1][1] - ts
    else:
        dur = 120.0
    if dur <= 0 or dur > 600:
        dur = min(max(dur, 10), 600)
    pos = text.find(original)
    if pos < 0:
        pos = 0
    return ts + (pos / max(len(text), 1)) * dur


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


def main():
    ap = argparse.ArgumentParser(description="批量 pending 音频交叉核验（双引擎片段识别）")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--speed", type=float, default=1.0,
                    help="转写时间轴→音频轴倍速（加速上传的妙记=源时长/妙记时长，如 1.3）")
    ap.add_argument("--queue-ids", default="", help="逗号分隔；默认该文件全部 pending")
    ap.add_argument("--engine-script", required=True,
                    help="第二识别引擎脚本（stdin 音频路径，stdout 文本），如 stepfun-asr/scripts/asr_transcribe.py")
    ap.add_argument("--outdir", default="/tmp/asr-verify")
    ap.add_argument("--tight", type=float, default=5.0, help="tight 窗 ±秒（默认 5）")
    ap.add_argument("--medium", type=float, default=20.0, help="medium 窗 ±秒（默认 20）")
    a = ap.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    lines = open(a.transcript, encoding="utf-8").read().splitlines()
    turns = parse_turns(lines)
    if not turns:
        sys.exit("no speaker turns parsed — 转写需含「说话人 HH:MM:SS.mmm」行")
    ids = {int(x) for x in a.queue_ids.split(",") if x.strip()} if a.queue_ids else None
    items = list_pending(a.transcript, ids)
    if not items:
        sys.exit("no pending items for this file")

    results = []
    for it in items:
        tok_t = token_offset(turns, it["line_number"], it["original_text"]) * a.speed
        tid = it["id"]
        tight = os.path.join(a.outdir, f"{tid}-tight.wav")
        med = os.path.join(a.outdir, f"{tid}-med.wav")
        for clip, start, dur in ((tight, tok_t - a.tight, a.tight * 2),
                                 (med, tok_t - a.medium, a.medium * 2)):
            subprocess.run(["ffmpeg", "-y", "-ss", f"{max(start, 0):.3f}", "-t", f"{dur:.0f}",
                            "-i", a.audio, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", clip],
                           capture_output=True, check=True)
        r1 = subprocess.run(["python3", a.engine_script, tight], capture_output=True, text=True)
        r2 = subprocess.run(["python3", a.engine_script, med], capture_output=True, text=True)
        results.append({
            "id": tid, "line": it["line_number"],
            "original": it["original_text"], "suggested": it.get("suggested_text") or "",
            "token_wav_time": round(tok_t, 2),
            "tight": r1.stdout.strip()[:300], "medium": r2.stdout.strip()[:500],
            "err": (r1.stderr + r2.stderr)[:200],
        })
        print(f"done {tid}: {it['original_text']}", flush=True)

    out = os.path.join(a.outdir, "results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\n{len(results)} items -> {out}")


if __name__ == "__main__":
    main()
