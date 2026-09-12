#!/usr/bin/env python3
"""Rebuild the local Codex weekly-quota curve from rollout snapshots (Python 3.10+, macOS/Linux).

Scans <codex-home>/sessions/<Y>/<M>/<D>/rollout-*.jsonl for rate_limits snapshots and
prints anchor back-jumps (step 1) followed by zeroing intervals (step 2). No network,
no account credentials. Snapshots carry no account id: the shapes reported here are
leads for the attribution checks documented in SKILL.md, never proof of account count.

The four traps documented in SKILL.md are built in:
  trap 1  the weekly window is selected by window_minutes == 10080, not by slot name;
  trap 2  only limit_id == "codex" rows are used (decoy buckets read constant zero);
  trap 3  resets_at drifts by seconds between snapshots, so resets are judged by a
          used_percent drop > 20 points, never by anchor movement alone;
  trap 4  directory date != timestamp range (long sessions write past midnight into
          the previous day's directory), so scan days+2 directories, then clip by
          timestamp.
"""

import argparse
from datetime import datetime, timedelta, timezone
import glob
import json
import os
from pathlib import Path
import sys

BJ = timezone(timedelta(hours=8))
WEEK_MINUTES = 10080
DROP_THRESHOLD = 20.0
BACKJUMP_MIN_SECONDS = 300
CLEAN_ANCHOR_TOLERANCE_SECONDS = 600


def find_rl(node):
    if isinstance(node, dict):
        if node.get("rate_limits"):
            return node["rate_limits"]
        for value in node.values():
            found = find_rl(value)
            if found is not None:
                return found
    if isinstance(node, list):
        for value in node:
            found = find_rl(value)
            if found is not None:
                return found
    return None


def parse_ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(BJ)


def anchor_text(epoch):
    return datetime.fromtimestamp(epoch, BJ)


def collect_rows(sessions_root, days, now):
    rows = []
    scan = days + 2  # trap 4
    now_local = now.astimezone()
    cutoff = now.astimezone(BJ) - timedelta(days=days)
    for i in range(scan):
        day = (now_local - timedelta(days=i)).strftime("%Y/%m/%d")
        for path in glob.glob(str(sessions_root / day / "rollout-*.jsonl")):
            with open(path, encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if "rate_limits" not in line:
                        continue
                    try:
                        doc = json.loads(line)
                    except ValueError:
                        continue
                    rl = find_rl(doc)
                    ts = doc.get("timestamp")
                    if not rl or not ts or rl.get("limit_id") != "codex":  # trap 2
                        continue
                    for slot in ("primary", "secondary"):
                        p = rl.get(slot)
                        if not p or p.get("window_minutes") != WEEK_MINUTES:  # trap 1
                            continue
                        rows.append((ts, p["used_percent"], p["resets_at"],
                                     (rl.get("credits") or {}).get("balance")))
    rows = [r for r in rows if parse_ts(r[0]) >= cutoff]  # trap 4: clip by timestamp
    rows.sort(key=lambda r: r[0])
    return rows, scan


def find_backjumps(rows):
    """Compare strictly adjacent raw snapshots; a used% rise alone is normal consumption."""
    jumps = []
    prev = None
    for ts, used, resets_at, _ in rows:
        if prev is not None:
            pa = anchor_text(prev[2]).replace(second=0, microsecond=0)
            ca = anchor_text(resets_at).replace(second=0, microsecond=0)
            rose = used > prev[1]
            # Sub-minute resets_at drift across a minute boundary fakes a -0.0h jump;
            # the 5-minute floor filters that, rows with rising used% stay as leads.
            if ca < pa and ((pa - ca).total_seconds() >= BACKJUMP_MIN_SECONDS or rose):
                jumps.append({"ts": ts, "from": pa, "to": ca, "rose": rose,
                              "used_from": prev[1], "used_to": used})
        prev = (ts, used, resets_at)
    return jumps


def find_zeroings(rows):
    zeroings = []
    prev = None
    for row in rows:
        if prev and prev[1] - row[1] > DROP_THRESHOLD:  # trap 3
            anchor = anchor_text(row[2])
            clean = abs((anchor - (parse_ts(row[0]) + timedelta(days=7))).total_seconds()) \
                < CLEAN_ANCHOR_TOLERANCE_SECONDS
            zeroings.append({"prev_ts": prev[0], "prev_used": prev[1],
                             "ts": row[0], "used": row[1], "anchor": anchor,
                             "clean": clean, "full": prev[1] >= 99})
        prev = row
    return zeroings


def format_report(rows, scan, backjumps, zeroings):
    lines = [f"采样 {len(rows)} 行 | 最早 {parse_ts(rows[0][0]):%m-%d %H:%M}"
             f" | 扫了 {scan} 个日期目录", ""]
    for j in backjumps:
        up = " ⚠ 已用量上升且锚点回退：需核对身份与窗口配置" if j["rose"] else ""
        lines.append(
            f"回跳 {parse_ts(j['ts']):%m-%d %H:%M:%S} 锚点 {j['from']:%m-%d %H:%M} → "
            f"{j['to']:%m-%d %H:%M} (-{(j['from'] - j['to']).total_seconds() / 3600:.1f}h)"
            f" used {j['used_from']:.0f}%→{j['used_to']:.0f}%{up}")
    lines.append(f"回跳次数: {len(backjumps)}  （形状检查不证明账号数量；命中项需核对身份与窗口配置）")
    lines.append("")
    for z in zeroings:
        shape = "干净+7d" if z["clean"] else "锚点回拨"
        peak = "打满触发" if z["full"] else "非打满(平台推送先验)"
        lines.append(
            f"归零区间 {parse_ts(z['prev_ts']):%m-%d %H:%M:%S} {z['prev_used']:.0f}% → "
            f"{parse_ts(z['ts']):%m-%d %H:%M:%S} {z['used']:.0f}%"
            f" | 新锚点 {z['anchor']:%m-%d %H:%M} {shape} | {peak}")
    last = rows[-1]
    lines.append("")
    lines.append(f"最新快照 {parse_ts(last[0]):%F %H:%M:%S} 北京 | 已用 {last[1]:.0f}%"
                 f" | 窗口重置于 {anchor_text(last[2]):%F %H:%M}"
                 f" | purchased_credits={last[3]} | banked=unknown")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=7,
                        help="how many trailing days to keep after timestamp clipping (default 7)")
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex",
                        help="authorized Codex home; never mix snapshots across homes")
    parser.add_argument("--as-of",
                        help="ISO timestamp with timezone used as 'now', for reproducible slices")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be >= 1")
    if args.as_of:
        now = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        if now.tzinfo is None:
            parser.error("--as-of requires a timezone")
    else:
        now = datetime.now(BJ)
    sessions_root = Path(os.path.expanduser(str(args.codex_home))) / "sessions"
    rows, scan = collect_rows(sessions_root, args.days, now)
    if not rows:
        # Empty is not an anomaly but a state that must be reported: the window is a blind spot.
        raise SystemExit("没有可用快照：该窗口内没跑过 Codex，或 sessions 目录为空。\n"
                         "这不构成「没有重置」，只说明该区间无观测。")
    print(format_report(rows, scan, find_backjumps(rows), find_zeroings(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
