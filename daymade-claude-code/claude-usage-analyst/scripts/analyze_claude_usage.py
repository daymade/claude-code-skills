#!/usr/bin/env python3
"""Summarize local Claude Code usage from ccusage JSON output."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo


def run_ccusage(args: list[str]) -> dict[str, Any]:
    if not shutil.which("ccusage"):
        raise SystemExit(
            "ccusage not found. Install with: npm install -g ccusage@latest"
        )
    proc = subprocess.run(
        ["ccusage", "claude", *args, "--json"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise SystemExit(f"ccusage failed:\n{proc.stderr or proc.stdout}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Could not parse ccusage JSON: {exc}\n{proc.stdout[:1000]}")


def model_total(model: dict[str, Any]) -> int:
    return int(model.get("inputTokens", 0)) + int(model.get("outputTokens", 0)) + int(
        model.get("cacheCreationTokens", 0)
    ) + int(model.get("cacheReadTokens", 0))


def money(value: float | int | None) -> str:
    return f"${float(value or 0):,.2f}"


def tokens(value: float | int | None) -> str:
    return f"{int(value or 0):,}"


def ratio(a: float, b: float) -> float | None:
    return None if b == 0 else a / b


def pct(part: float, whole: float) -> str:
    if whole == 0:
        return "0.0%"
    return f"{part / whole * 100:.1f}%"


def find_model(day: dict[str, Any], needle: str) -> dict[str, Any] | None:
    needle = needle.lower()
    for model in day.get("modelBreakdowns", []):
        name = str(model.get("modelName", "")).lower()
        if needle in name:
            return model
    return None


def local_time(iso_value: str | None, timezone: str) -> str | None:
    if not iso_value:
        return None
    value = iso_value.replace("Z", "+00:00")
    return (
        dt.datetime.fromisoformat(value)
        .astimezone(ZoneInfo(timezone))
        .strftime("%Y-%m-%d %H:%M")
    )


def summarize(args: argparse.Namespace) -> dict[str, Any]:
    daily = run_ccusage(
        [
            "daily",
            "--since",
            args.since,
            "--until",
            args.until,
            "--timezone",
            args.timezone,
        ]
    ).get("daily", [])
    if not daily:
        raise SystemExit("No Claude usage found for the selected date range.")

    blocks = run_ccusage(
        [
            "blocks",
            "--since",
            args.since,
            "--until",
            args.until,
            "--timezone",
            args.timezone,
        ]
    ).get("blocks", [])

    target = next((d for d in daily if d.get("date") == args.until), daily[-1])
    ranked_cost = sorted(daily, key=lambda d: float(d.get("totalCost", 0)), reverse=True)
    ranked_tokens = sorted(
        daily, key=lambda d: int(d.get("totalTokens", 0)), reverse=True
    )
    before = [d for d in daily if d.get("date") < target.get("date")]

    model_rows = []
    for model in sorted(
        target.get("modelBreakdowns", []),
        key=lambda m: float(m.get("cost", 0)),
        reverse=True,
    ):
        total = model_total(model)
        model_rows.append(
            {
                "model": model.get("modelName"),
                "totalTokens": total,
                "cost": float(model.get("cost", 0)),
                "inputTokens": int(model.get("inputTokens", 0)),
                "outputTokens": int(model.get("outputTokens", 0)),
                "cacheCreationTokens": int(model.get("cacheCreationTokens", 0)),
                "cacheReadTokens": int(model.get("cacheReadTokens", 0)),
                "cacheReadShare": pct(
                    int(model.get("cacheReadTokens", 0)),
                    total,
                ),
            }
        )

    comparison = None
    model_a = find_model(target, args.model_a) if args.model_a else None
    model_b = find_model(target, args.model_b) if args.model_b else None
    if model_a and model_b:
        total_a = model_total(model_a)
        total_b = model_total(model_b)
        cost_a = float(model_a.get("cost", 0))
        cost_b = float(model_b.get("cost", 0))
        comparison = {
            "modelA": model_a.get("modelName"),
            "modelB": model_b.get("modelName"),
            "tokenRatioAtoB": ratio(total_a, total_b),
            "costRatioAtoB": ratio(cost_a, cost_b),
            "tokensA": total_a,
            "tokensB": total_b,
            "costA": cost_a,
            "costB": cost_b,
        }

    block_rows = []
    for block in blocks:
        if block.get("isGap"):
            continue
        start_local = local_time(block.get("startTime"), args.timezone)
        if start_local and start_local[:10] != str(target.get("date")):
            continue
        counts = block.get("tokenCounts", {})
        total = int(block.get("totalTokens", 0))
        block_rows.append(
            {
                "start": start_local,
                "end": local_time(block.get("endTime"), args.timezone),
                "actualEnd": local_time(block.get("actualEndTime"), args.timezone),
                "models": block.get("models", []),
                "entries": block.get("entries", 0),
                "totalTokens": total,
                "cost": float(block.get("costUSD", 0)),
                "inputTokens": int(counts.get("inputTokens", 0)),
                "outputTokens": int(counts.get("outputTokens", 0)),
                "cacheCreationTokens": int(counts.get("cacheCreationInputTokens", 0)),
                "cacheReadTokens": int(counts.get("cacheReadInputTokens", 0)),
                "cacheReadShare": pct(int(counts.get("cacheReadInputTokens", 0)), total),
                "isActive": bool(block.get("isActive")),
            }
        )

    return {
        "scope": {
            "since": args.since,
            "until": args.until,
            "timezone": args.timezone,
            "source": "ccusage claude daily/blocks --json",
        },
        "targetDay": {
            "date": target.get("date"),
            "totalTokens": int(target.get("totalTokens", 0)),
            "cost": float(target.get("totalCost", 0)),
            "inputTokens": int(target.get("inputTokens", 0)),
            "outputTokens": int(target.get("outputTokens", 0)),
            "cacheCreationTokens": int(target.get("cacheCreationTokens", 0)),
            "cacheReadTokens": int(target.get("cacheReadTokens", 0)),
            "cacheReadShare": pct(
                int(target.get("cacheReadTokens", 0)),
                int(target.get("totalTokens", 0)),
            ),
            "costRankInWindow": ranked_cost.index(target) + 1,
            "tokenRankInWindow": ranked_tokens.index(target) + 1,
            "daysInWindow": len(daily),
            "averageCostBeforeTarget": (
                sum(float(d.get("totalCost", 0)) for d in before) / len(before)
                if before
                else None
            ),
            "medianCostBeforeTarget": (
                median(float(d.get("totalCost", 0)) for d in before) if before else None
            ),
            "averageTokensBeforeTarget": (
                sum(int(d.get("totalTokens", 0)) for d in before) / len(before)
                if before
                else None
            ),
            "medianTokensBeforeTarget": (
                median(int(d.get("totalTokens", 0)) for d in before) if before else None
            ),
        },
        "models": model_rows,
        "comparison": comparison,
        "blocks": block_rows,
    }


def print_markdown(summary: dict[str, Any]) -> None:
    target = summary["targetDay"]
    print(f"# Claude usage analysis ({target['date']})")
    print()
    print(f"Source: `{summary['scope']['source']}`")
    print(f"Timezone: `{summary['scope']['timezone']}`")
    print()
    print("## Target day")
    print()
    print("| Metric | Value |")
    print("|---|---:|")
    print(f"| Total tokens | {tokens(target['totalTokens'])} |")
    print(f"| Estimated cost | {money(target['cost'])} |")
    print(f"| Input | {tokens(target['inputTokens'])} |")
    print(f"| Output | {tokens(target['outputTokens'])} |")
    print(f"| Cache create | {tokens(target['cacheCreationTokens'])} |")
    print(f"| Cache read | {tokens(target['cacheReadTokens'])} |")
    print(f"| Cache read share | {target['cacheReadShare']} |")
    print(
        f"| Cost rank in window | {target['costRankInWindow']} / {target['daysInWindow']} |"
    )
    print(
        f"| Token rank in window | {target['tokenRankInWindow']} / {target['daysInWindow']} |"
    )
    if target["medianCostBeforeTarget"] is not None:
        print(f"| Prior median cost | {money(target['medianCostBeforeTarget'])} |")
        print(f"| Prior median tokens | {tokens(target['medianTokensBeforeTarget'])} |")
    print()

    print("## Model breakdown")
    print()
    print("| Model | Tokens | Cost | Cache read | Cache read share |")
    print("|---|---:|---:|---:|---:|")
    for model in summary["models"]:
        print(
            f"| {model['model']} | {tokens(model['totalTokens'])} | "
            f"{money(model['cost'])} | {tokens(model['cacheReadTokens'])} | "
            f"{model['cacheReadShare']} |"
        )
    print()

    if summary["comparison"]:
        comp = summary["comparison"]
        print("## Model comparison")
        print()
        print(
            f"- {comp['modelA']} used {comp['tokenRatioAtoB']:.2f}x the tokens of "
            f"{comp['modelB']}."
        )
        print(
            f"- {comp['modelA']} cost {comp['costRatioAtoB']:.2f}x {comp['modelB']} "
            "in ccusage estimates."
        )
        print()

    if summary["blocks"]:
        print("## 5-hour blocks")
        print()
        print("| Start | End | Models | Entries | Tokens | Cost | Cache read share |")
        print("|---|---|---|---:|---:|---:|---:|")
        for block in summary["blocks"]:
            print(
                f"| {block['start']} | {block['end']} | "
                f"{', '.join(block['models'])} | {block['entries']} | "
                f"{tokens(block['totalTokens'])} | {money(block['cost'])} | "
                f"{block['cacheReadShare']} |"
            )


def main() -> None:
    today = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default=today)
    parser.add_argument("--until", default=today)
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--model-a", default="fable")
    parser.add_argument("--model-b", default="opus-4-8")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args()

    summary = summarize(args)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_markdown(summary)


if __name__ == "__main__":
    main()
