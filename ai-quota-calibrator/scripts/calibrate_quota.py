#!/usr/bin/env python3
"""Calibrate black-box AI subscription quotas against local tokscale spend.

Zero-dependency Python 3.9+ stdlib CLI. Reconciles live provider quota
percentages (Antigravity `agy -p /usage --output-format json`, Codex
`tokscale usage --json`, or custom percentage inputs) with local `tokscale`
spend aligned to exact window boundaries.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

WINDOW_DURATIONS = {
    "5h": dt.timedelta(hours=5),
    "five_hour": dt.timedelta(hours=5),
    "24h": dt.timedelta(hours=24),
    "daily": dt.timedelta(days=1),
    "weekly": dt.timedelta(days=7),
    "7d": dt.timedelta(days=7),
    "30d": dt.timedelta(days=30),
    "monthly": dt.timedelta(days=30),
}

# Standard 5-minute prompt-cache write uplift relative to base input rate
# when local logs omit cacheWrite counters (e.g., Anthropic $5/M vs $4/M = +25%).
CACHE_WRITE_UPLIFT_BY_PROVIDER = {
    "anthropic": 0.25,
}

# Fallback base input rates ($/1M tokens) used only when estimating cache-write
# uplift if tokscale does not report a per-model input price separately.
FALLBACK_INPUT_RATE_PER_M = {
    "claude-opus-5-5": 4.0,
    "claude-sonnet-5-5": 3.0,
    "claude-opus-4-6": 5.0,
    "claude-sonnet-4-6": 3.0,
}

STABILITY_TOLERANCE = 0.002  # 0.2 percentage points
RATIO_SHIFT_TOLERANCE = 0.15
DEFAULT_CMD_TIMEOUT = 60.0

_FRAC_SECONDS_RE = re.compile(r"(\d{2}:\d{2}:\d{2})\.(\d+)")


class CalibrationError(RuntimeError):
    """Explicit operational or input failure."""


def local_tz() -> dt.tzinfo:
    return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc


def parse_iso_datetime(value: str, tz: dt.tzinfo) -> dt.datetime:
    """Parse ISO-8601 / RFC3339 timestamps (including 1-9 fractional digits on Py 3.9+)."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Python 3.9/3.10 fromisoformat only accepts 0, 3, or 6 fractional digits.
    text = _FRAC_SECONDS_RE.sub(
        lambda m: f"{m.group(1)}.{m.group(2)[:6].ljust(6, '0')}",
        text,
        count=1,
    )
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def parse_local_hour(value: str, tz: dt.tzinfo) -> dt.datetime:
    """Parse tokscale hourly bucket timestamp ('YYYY-MM-DD HH:00') in local TZ."""
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            naive = dt.datetime.strptime(text, fmt)
            return naive.replace(tzinfo=tz)
        except ValueError:
            continue
    return parse_iso_datetime(text, tz)


def extract_stderr_notices(stderr: str) -> list[str]:
    """Capture actionable tokscale/provider stderr notices emitted on exit 0."""
    notices: list[str] = []
    for raw_line in stderr.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        low = line.lower()
        if any(
            k in low
            for k in (
                "unpriced",
                "stale pricing",
                "partial",
                "warning:",
                "incomplete",
                "tokscale:",
            )
        ):
            if line not in notices:
                notices.append(line)
    return notices


def run_json_cmd(
    argv: list[str],
    binary_hint: str,
    timeout: float = DEFAULT_CMD_TIMEOUT,
) -> tuple[Any, list[str]]:
    if shutil.which(argv[0]) is None:
        raise CalibrationError(
            f"Required CLI '{argv[0]}' not found in PATH. {binary_hint}"
        )
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CalibrationError(
            f"Command timed out after {timeout:.0f}s: {' '.join(argv)}"
        ) from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[:400]
        raise CalibrationError(
            f"Command failed (exit {proc.returncode}): {' '.join(argv)}\n{detail}"
        )
    raw = proc.stdout.strip()
    if not raw:
        raise CalibrationError(f"Command returned empty output: {' '.join(argv)}")
    notices = extract_stderr_notices(proc.stderr or "")
    try:
        return json.loads(raw), notices
    except json.JSONDecodeError as exc:
        for ch in ("{", "["):
            idx = raw.find(ch)
            if idx != -1:
                try:
                    return json.loads(raw[idx:]), notices
                except json.JSONDecodeError:
                    pass
        raise CalibrationError(
            f"Failed to parse JSON from {' '.join(argv)}: {exc}"
        ) from exc


def inspect_tokscale_completeness(
    models_payload: dict[str, Any] | list[dict[str, Any]],
) -> list[str]:
    """Flag unpriced models or undated token balances in tokscale model JSON."""
    warnings: list[str] = []
    entries = (
        models_payload.get("entries", [])
        if isinstance(models_payload, dict)
        else models_payload
    )
    unpriced_models: list[str] = []
    for e in entries:
        cost = float(e.get("cost") or 0.0)
        tokens = sum(
            int(e.get(k) or 0)
            for k in ("input", "output", "reasoning", "cacheRead", "cacheWrite")
        )
        if tokens > 0 and cost <= 0.0:
            unpriced_models.append(str(e.get("model") or "unknown"))
    if unpriced_models:
        warnings.append(
            "UNPRICED_MODELS: tokscale reported $0 cost for non-zero tokens on "
            f"{', '.join(sorted(set(unpriced_models)))}; implied pool size may be underestimated."
        )
    if isinstance(models_payload, dict):
        undated = models_payload.get("undatedTokens") or {}
        if isinstance(undated, dict) and any(int(v or 0) > 0 for v in undated.values()):
            warnings.append(
                "UNDATED_TOKENS: tokscale reported undatedTokens outside date-filtered windows."
            )
    return warnings


def classify_antigravity_model(model: str) -> str:
    """Map a tokscale model ID to its Antigravity quota group key."""
    low = model.lower()
    if "gemini" in low or "orchestrator" in low:
        return "gemini"
    return "3p"


def classify_antigravity_group_name(group_name: str, bucket_id: str) -> str:
    low = f"{group_name} {bucket_id}".lower()
    if "gemini" in low:
        return "gemini"
    return "3p"


def estimate_cache_write_uplift_usd(entries: list[dict[str, Any]]) -> float:
    """Estimate upper-bound extra spend if uncached input was billed as 5m cache write."""
    extra = 0.0
    for e in entries:
        if e.get("cacheWrite", 0):
            continue
        provider = str(e.get("provider") or "").lower()
        model = str(e.get("model") or "").lower()
        uplift = CACHE_WRITE_UPLIFT_BY_PROVIDER.get(provider, 0.0)
        if uplift <= 0.0 and "claude" in model:
            uplift = 0.25
        if uplift <= 0.0:
            continue
        inp = float(e.get("input") or 0.0)
        if inp <= 0.0:
            continue
        input_rate = None
        for prefix, rate in FALLBACK_INPUT_RATE_PER_M.items():
            if model.startswith(prefix):
                input_rate = rate
                break
        if input_rate is None:
            extra += float(e.get("cost") or 0.0) * uplift
        else:
            extra += (inp / 1_000_000.0) * input_rate * uplift
    return extra


def assess_antigravity_stability(
    samples: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str], dict[str, float]]:
    """Compare 1..N usage snapshots for remaining_fraction shifts and 5h/weekly ratio skew."""
    if not samples:
        raise CalibrationError("No Antigravity /usage samples available.")
    if len(samples) == 1:
        return samples[0], [], {}

    first = samples[0]
    last = samples[-1]
    warnings: list[str] = []
    shift_by_bucket: dict[str, float] = {}

    def extract_buckets(payload: dict[str, Any]) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
        by_id: dict[str, float] = {}
        by_group_win: dict[str, dict[str, float]] = {}
        groups = payload.get("command", {}).get("data", {}).get("groups", [])
        for g in groups:
            gname = str(g.get("name", ""))
            for b in g.get("buckets", []):
                bid = str(b.get("id") or b.get("name"))
                rem = float(b.get("remaining_fraction", 1.0))
                win = str(b.get("window") or "").lower()
                gk = classify_antigravity_group_name(gname, bid)
                by_id[bid] = rem
                by_group_win.setdefault(gk, {})[win] = max(0.0, 1.0 - rem)
        return by_id, by_group_win

    m1, gw1 = extract_buckets(first)
    m2, gw2 = extract_buckets(last)
    for bid, v2 in m2.items():
        v1 = m1.get(bid, v2)
        diff = abs(v2 - v1)
        shift_by_bucket[bid] = diff
        if diff > STABILITY_TOLERANCE:
            warnings.append(
                f"Bucket '{bid}' shifted by {diff * 100:.2f}% between consecutive reads "
                f"({v1 * 100:.2f}% -> {v2 * 100:.2f}%), indicating active in-flight "
                f"requests, 1% pre-reservation, or replica sync lag."
            )

    for gk, w2 in gw2.items():
        w1 = gw1.get(gk, {})
        u5_1, uw_1 = w1.get("5h", 0.0), w1.get("weekly", 0.0)
        u5_2, uw_2 = w2.get("5h", 0.0), w2.get("weekly", 0.0)
        if u5_1 > 0.005 and uw_1 > 0.005 and u5_2 > 0.005 and uw_2 > 0.005:
            r1 = u5_1 / uw_1
            r2 = u5_2 / uw_2
            if abs(r2 - r1) > RATIO_SHIFT_TOLERANCE:
                warnings.append(
                    f"Group '{gk}' used_5h/used_weekly ratio shifted between consecutive reads "
                    f"({r1:.2f}x -> {r2:.2f}x), consistent with a flat 1% in-flight reservation "
                    f"affecting both buckets asymmetrically."
                )

    return last, warnings, shift_by_bucket


def compute_group_window_spend(
    group_key: str,
    window_start: dt.datetime,
    models_since_entries: list[dict[str, Any]],
    hourly_entries: list[dict[str, Any]],
    tz: dt.tzinfo,
    model_classifier: Any,
    fresh_window_start: bool = False,
) -> dict[str, Any]:
    """Compute window spend for a model group with exact boundary alignment."""
    warnings: list[str] = []
    start_date_str = window_start.strftime("%Y-%m-%d")
    start_hour_floor = window_start.replace(minute=0, second=0, microsecond=0)
    boundary_elapsed_frac = (
        window_start.minute * 60 + window_start.second
    ) / 3600.0

    group_models = [
        e for e in models_since_entries if model_classifier(str(e.get("model", ""))) == group_key
    ]
    base_since_cost = sum(float(e.get("cost") or 0.0) for e in group_models)
    total_msgs = sum(int(e.get("messageCount") or 0) for e in group_models)
    cache_write_extra = estimate_cache_write_uplift_usd(group_models)

    pre_pure_sub = 0.0
    pre_mixed_cost = 0.0
    any_group_strictly_before = False
    any_group_pre_window = False

    for row in hourly_entries:
        h_dt = parse_local_hour(str(row.get("hour", "")), tz)
        if h_dt.strftime("%Y-%m-%d") < start_date_str:
            continue
        row_models = [str(m) for m in (row.get("models") or [])]
        row_groups = {model_classifier(m) for m in row_models} if row_models else {group_key}
        cost = float(row.get("cost") or 0.0)
        has_group = group_key in row_groups
        has_other = any(g != group_key for g in row_groups)

        if h_dt < start_hour_floor:
            if has_group:
                any_group_strictly_before = True
                any_group_pre_window = True
                if not has_other:
                    pre_pure_sub += cost
                else:
                    pre_mixed_cost += cost
        elif h_dt == start_hour_floor:
            if has_group and boundary_elapsed_frac > 0:
                any_group_pre_window = True
                if not has_other:
                    pre_pure_sub += cost * boundary_elapsed_frac
                else:
                    pre_mixed_cost += cost * boundary_elapsed_frac

    # Case 0: Fresh simultaneous 5h+weekly start with zero prior hours on start_date
    # proves no spend from this group occurred before window_start inside start_hour_floor.
    if fresh_window_start and not any_group_strictly_before:
        spend_base = base_since_cost
        spend_min = base_since_cost
        spend_max = base_since_cost
        method = "exact_fresh_window_start"
    # Case 1: Group never appeared before window_start on start_date -> exact!
    elif not any_group_pre_window:
        spend_base = base_since_cost
        spend_min = base_since_cost
        spend_max = base_since_cost
        method = "exact_models_since"
    # Case 2: Pre-window hours had ONLY this group (no mixed boundary) -> exact + boundary proration!
    elif pre_mixed_cost == 0.0:
        spend_base = max(0.0, base_since_cost - pre_pure_sub)
        spend_min = spend_base
        spend_max = spend_base
        method = "models_since_minus_pure_pre_hours"
    # Case 3: Unresolvable mixed pre-window hours -> transparent [min, max] bounds
    else:
        spend_max = max(0.0, base_since_cost - pre_pure_sub)
        spend_min = max(0.0, base_since_cost - pre_pure_sub - pre_mixed_cost)
        spend_base = (spend_min + spend_max) / 2.0
        method = "bounded_mixed_hour_estimate"
        warnings.append(
            f"MIXED_HOUR_AMBIGUITY: pre-window hours on {start_date_str} mixed "
            f"multiple model groups (${pre_mixed_cost:.2f}); window spend is "
            f"bounded in [${spend_min:.2f}, ${spend_max:.2f}]."
        )

    ratio_upper = (spend_max / base_since_cost) if base_since_cost > 0 else 0.0
    cw_uplift_scaled = cache_write_extra * min(1.0, max(0.0, ratio_upper))
    spend_upper = spend_max + cw_uplift_scaled

    return {
        "spend_base_usd": round(spend_base, 6),
        "spend_min_usd": round(spend_min, 6),
        "spend_upper_usd": round(spend_upper, 6),
        "cache_write_extra_usd": round(cw_uplift_scaled, 6),
        "message_count": total_msgs,
        "alignment_method": method,
        "warnings": warnings,
    }


def grade_confidence(
    used_fraction: float,
    shift_abs: float,
    mixed_ambiguity: bool,
    multi_account: bool = False,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    used_norm = round(used_fraction, 6)
    if used_norm <= 0.0:
        return "UNTOUCHED", ["Bucket is at 100% remaining; no spend to invert."]
    if used_norm >= 0.999:
        reasons.append(
            "SATURATED: bucket is at ~100% used; local spend is an upper bound "
            "unless exact lockout timestamp is known."
        )
        return "LOW", reasons
    if used_norm < 0.02:
        reasons.append(
            f"LOW_SIGNAL: only {used_fraction * 100:.3f}% consumed (< 2%); "
            "extrapolating from small usage is vulnerable to reservation jitter and cache-ratio skew."
        )
        return "LOW", reasons

    rel_shift = shift_abs / max(used_fraction, 1e-6)
    severe_jitter = shift_abs > STABILITY_TOLERANCE and (rel_shift > 0.15 or shift_abs > 0.015)
    minor_drift = shift_abs > STABILITY_TOLERANCE and not severe_jitter

    if severe_jitter:
        reasons.append(
            f"UNSTABLE_READINGS: consecutive reads diverged by {shift_abs * 100:.2f}% "
            f"({rel_shift * 100:.1f}% of consumed quota); re-run after active turns settle."
        )
        return "LOW", reasons
    if mixed_ambiguity:
        # Detailed MIXED_HOUR_AMBIGUITY range warning is already emitted by compute_group_window_spend.
        return "LOW", reasons
    if minor_drift:
        reasons.append(
            f"ACTIVE_SESSION_DRIFT: bucket moved {shift_abs * 100:.2f}% during sampling "
            f"({rel_shift * 100:.1f}% relative); estimate is solid but re-check when idle for tighter precision."
        )
        return "MEDIUM", reasons
    if multi_account:
        reasons.append(
            "MULTI_ACCOUNT_BIAS: multiple accounts detected for this provider; "
            "combined local spend can overestimate a single account's pool."
        )
        return "MEDIUM", reasons
    if used_norm < 0.10:
        reasons.append(
            f"MODERATE_SIGNAL: {used_fraction * 100:.2f}% consumed (2%–10%); "
            "re-check once >= 10% is used for tighter precision."
        )
        return "MEDIUM", reasons
    return "HIGH", reasons


def calibrate_antigravity(
    samples_count: int,
    settle_seconds: float,
    fixture: dict[str, Any] | None = None,
    timeout: float = DEFAULT_CMD_TIMEOUT,
) -> dict[str, Any]:
    tz = local_tz()
    now = dt.datetime.now(tz)
    top_warnings: list[str] = []

    if fixture is not None:
        raw_samples = fixture.get("usage_samples") or [fixture["usage"]]
        now = parse_iso_datetime(fixture["now"], tz) if fixture.get("now") else now
    else:
        raw_samples = []
        for idx in range(max(1, samples_count)):
            if idx > 0 and settle_seconds > 0:
                time.sleep(settle_seconds)
            payload, notices = run_json_cmd(
                ["agy", "-p", "/usage", "--output-format", "json"],
                "Install Antigravity CLI (`agy`) and authenticate first.",
                timeout=timeout,
            )
            raw_samples.append(payload)
            for n in notices:
                if n not in top_warnings:
                    top_warnings.append(n)

    chosen_usage, stability_warnings, shift_map = assess_antigravity_stability(raw_samples)
    top_warnings.extend(stability_warnings)

    cmd_data = chosen_usage.get("command", {}).get("data", {})
    groups = cmd_data.get("groups", [])
    if not groups:
        raise CalibrationError("Antigravity /usage JSON contained no quota groups.")

    bucket_specs: list[dict[str, Any]] = []
    earliest_date: str | None = None
    distinct_dates: set[str] = set()
    for g in groups:
        gname = str(g.get("name", "Unknown"))
        for b in g.get("buckets", []):
            bid = str(b.get("id") or b.get("name"))
            window = str(b.get("window") or "").lower()
            dur = WINDOW_DURATIONS.get(window)
            reset_raw = str(b.get("reset_time") or "")
            reset_local = parse_iso_datetime(reset_raw, tz) if reset_raw else None
            win_start = (reset_local - dur) if (dur is not None and reset_local is not None) else None
            start_date = win_start.strftime("%Y-%m-%d") if win_start is not None else None
            if start_date is not None:
                distinct_dates.add(start_date)
                if earliest_date is None or start_date < earliest_date:
                    earliest_date = start_date
            bucket_specs.append(
                {
                    "group_name": gname,
                    "group_key": classify_antigravity_group_name(gname, bid),
                    "bucket_id": bid,
                    "bucket_name": str(b.get("name", bid)),
                    "window": window,
                    "remaining_fraction": float(b.get("remaining_fraction", 1.0)),
                    "reset_time_utc": reset_raw,
                    "reset_time_local": (
                        reset_local.isoformat(timespec="seconds") if reset_local else "unknown"
                    ),
                    "window_start_local": win_start,
                    "start_date": start_date,
                }
            )

    fresh_start_groups: set[str] = set()
    by_group_starts: dict[str, dict[str, dt.datetime]] = {}
    for spec in bucket_specs:
        if spec["window_start_local"] is not None:
            by_group_starts.setdefault(spec["group_key"], {})[spec["window"]] = spec[
                "window_start_local"
            ]
    for gk, smap in by_group_starts.items():
        if (
            "5h" in smap
            and "weekly" in smap
            and abs((smap["5h"] - smap["weekly"]).total_seconds()) <= 5
        ):
            fresh_start_groups.add(gk)

    if fixture is not None:
        models_by_date: dict[str, list[dict[str, Any]]] = fixture.get("models_by_date") or {
            d: fixture.get("models", {}).get("entries", []) for d in distinct_dates
        }
        hourly_entries: list[dict[str, Any]] = fixture.get("hourly", {}).get("entries", [])
        for entries in models_by_date.values():
            for w in inspect_tokscale_completeness(entries):
                if w not in top_warnings:
                    top_warnings.append(w)
    else:
        models_by_date = {}
        for d in sorted(distinct_dates):
            m_json, notices = run_json_cmd(
                [
                    "tokscale",
                    "models",
                    "-c",
                    "antigravity-cli",
                    "--since",
                    d,
                    "--json",
                    "--no-spinner",
                ],
                "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
                timeout=timeout,
            )
            models_by_date[d] = m_json.get("entries", [])
            for w in notices + inspect_tokscale_completeness(m_json):
                if w not in top_warnings:
                    top_warnings.append(w)
        if earliest_date is not None:
            h_json, notices = run_json_cmd(
                [
                    "tokscale",
                    "hourly",
                    "-c",
                    "antigravity-cli",
                    "--since",
                    earliest_date,
                    "--json",
                    "--no-spinner",
                ],
                "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
                timeout=timeout,
            )
            hourly_entries = h_json.get("entries", [])
            for n in notices:
                if n not in top_warnings:
                    top_warnings.append(n)
        else:
            hourly_entries = []

    calibrated_buckets: list[dict[str, Any]] = []
    group_windows: dict[str, dict[str, float]] = {}

    for spec in bucket_specs:
        rem = spec["remaining_fraction"]
        used = max(0.0, 1.0 - rem)
        group_windows.setdefault(spec["group_key"], {})[spec["window"]] = used

        if spec["window_start_local"] is None or spec["start_date"] is None:
            calibrated_buckets.append(
                {
                    "group_name": spec["group_name"],
                    "group_key": spec["group_key"],
                    "bucket_id": spec["bucket_id"],
                    "window": spec["window"],
                    "window_start_local": "unknown",
                    "reset_time_local": spec["reset_time_local"],
                    "remaining_fraction": rem,
                    "used_pct": round(used * 100.0, 4),
                    "spend_base_usd": None,
                    "spend_min_usd": None,
                    "spend_upper_usd": None,
                    "message_count_since_date": 0,
                    "alignment_method": "unknown_window_duration",
                    "implied_pool_base_usd": None,
                    "implied_pool_min_usd": None,
                    "implied_pool_upper_usd": None,
                    "confidence": "UNKNOWN_WINDOW",
                    "warnings": [
                        f"UNKNOWN_WINDOW_DURATION: unrecognized window '{spec['window']}' "
                        f"or missing reset_time; cannot align spend without guessing."
                    ],
                }
            )
            continue

        spend_info = compute_group_window_spend(
            group_key=spec["group_key"],
            window_start=spec["window_start_local"],
            models_since_entries=models_by_date.get(spec["start_date"], []),
            hourly_entries=hourly_entries,
            tz=tz,
            model_classifier=classify_antigravity_model,
            fresh_window_start=spec["group_key"] in fresh_start_groups,
        )
        mixed_amb = any("MIXED_HOUR_AMBIGUITY" in w for w in spend_info["warnings"])
        shift_abs = shift_map.get(spec["bucket_id"], 0.0)
        confidence, conf_reasons = grade_confidence(
            used_fraction=used,
            shift_abs=shift_abs,
            mixed_ambiguity=mixed_amb,
        )

        implied_base = (spend_info["spend_base_usd"] / used) if used > 0 else None
        implied_min = (spend_info["spend_min_usd"] / used) if used > 0 else None
        implied_upper = (spend_info["spend_upper_usd"] / used) if used > 0 else None

        calibrated_buckets.append(
            {
                "group_name": spec["group_name"],
                "group_key": spec["group_key"],
                "bucket_id": spec["bucket_id"],
                "window": spec["window"],
                "window_start_local": spec["window_start_local"].isoformat(timespec="seconds"),
                "reset_time_local": spec["reset_time_local"],
                "remaining_fraction": rem,
                "used_pct": round(used * 100.0, 4),
                "spend_base_usd": round(spend_info["spend_base_usd"], 4),
                "spend_min_usd": round(spend_info["spend_min_usd"], 4),
                "spend_upper_usd": round(spend_info["spend_upper_usd"], 4),
                "message_count_since_date": spend_info["message_count"],
                "alignment_method": spend_info["alignment_method"],
                "implied_pool_base_usd": round(implied_base, 2) if implied_base is not None else None,
                "implied_pool_min_usd": round(implied_min, 2) if implied_min is not None else None,
                "implied_pool_upper_usd": round(implied_upper, 2) if implied_upper is not None else None,
                "confidence": confidence,
                "warnings": spend_info["warnings"] + conf_reasons,
            }
        )

    multipliers: dict[str, float | None] = {}
    for gk, wmap in group_windows.items():
        u5 = wmap.get("5h", 0.0)
        uw = wmap.get("weekly", 0.0)
        if u5 > 0 and uw > 0:
            b5 = next(
                (b for b in calibrated_buckets if b["group_key"] == gk and b["window"] == "5h"),
                None,
            )
            bw = next(
                (b for b in calibrated_buckets if b["group_key"] == gk and b["window"] == "weekly"),
                None,
            )
            if gk in fresh_start_groups:
                multipliers[gk] = round(u5 / uw, 4)
            elif b5 and bw and b5["implied_pool_base_usd"] and bw["implied_pool_base_usd"]:
                multipliers[gk] = round(
                    bw["implied_pool_base_usd"] / b5["implied_pool_base_usd"], 2
                )
            else:
                multipliers[gk] = None
        else:
            multipliers[gk] = None

    return {
        "provider": "antigravity",
        "observed_at_local": now.isoformat(timespec="seconds"),
        "samples_taken": len(raw_samples),
        "provider_rule_description": cmd_data.get("description", ""),
        "weekly_to_5h_multipliers": multipliers,
        "buckets": calibrated_buckets,
        "warnings": top_warnings,
    }


def calibrate_codex(
    account_email: str | None = None,
    fixture: dict[str, Any] | None = None,
    timeout: float = DEFAULT_CMD_TIMEOUT,
) -> dict[str, Any]:
    tz = local_tz()
    now = dt.datetime.now(tz)
    top_warnings: list[str] = []

    if fixture is not None:
        usage_list = fixture["usage"]
        now = parse_iso_datetime(fixture["now"], tz) if fixture.get("now") else now
    else:
        usage_list, notices = run_json_cmd(
            ["tokscale", "usage", "--json"],
            "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
            timeout=timeout,
        )
        top_warnings.extend(notices)

    codex_accounts = [u for u in usage_list if str(u.get("provider", "")).lower() == "codex"]
    if not codex_accounts:
        raise CalibrationError("No Codex account entries returned by `tokscale usage --json`.")

    selected = None
    if account_email:
        for a in codex_accounts:
            if str(a.get("email") or "").lower() == account_email.lower():
                selected = a
                break
        if selected is None:
            raise CalibrationError(
                f"Codex account '{account_email}' not found in `tokscale usage --json`."
            )
    else:
        selected = next(
            (a for a in codex_accounts if (a.get("account") or {}).get("is_active")),
            codex_accounts[0],
        )

    multi_account = len(codex_accounts) > 1
    if multi_account:
        top_warnings.append(
            f"Detected {len(codex_accounts)} Codex accounts in `tokscale usage`; "
            "local `~/.codex/sessions` combines rollouts across accounts, so local spend "
            "may overestimate a single account's pool."
        )

    metrics = selected.get("metrics") or []
    if not metrics:
        raise CalibrationError("Selected Codex account returned no quota metrics.")

    earliest_date: str | None = None
    parsed_metrics = []
    for m in metrics:
        label = str(m.get("label") or "unknown")
        low = label.lower()
        dur = WINDOW_DURATIONS.get(low)
        if dur is None:
            if "week" in low:
                dur = dt.timedelta(days=7)
            elif "5h" in low or "5-hour" in low or "five" in low:
                dur = dt.timedelta(hours=5)
            elif "30d" in low or "month" in low:
                dur = dt.timedelta(days=30)
            elif "day" in low or "daily" in low or "24h" in low:
                dur = dt.timedelta(days=1)
        reset_raw = str(m.get("resets_at") or "")
        reset_local = parse_iso_datetime(reset_raw, tz) if reset_raw else None
        win_start = (reset_local - dur) if (dur is not None and reset_local is not None) else None
        sdate = win_start.strftime("%Y-%m-%d") if win_start is not None else None
        if sdate is not None and (earliest_date is None or sdate < earliest_date):
            earliest_date = sdate
        parsed_metrics.append(
            {
                "label": label,
                "used_pct": float(m.get("used_percent", 0.0)),
                "remaining_pct": float(m.get("remaining_percent", 100.0)),
                "reset_local": reset_local,
                "win_start": win_start,
                "start_date": sdate,
            }
        )

    if fixture is not None:
        hourly_entries = fixture.get("hourly", {}).get("entries", [])
    elif earliest_date is not None:
        h_json, notices = run_json_cmd(
            [
                "tokscale",
                "hourly",
                "-c",
                "codex",
                "--since",
                earliest_date,
                "--json",
                "--no-spinner",
            ],
            "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
            timeout=timeout,
        )
        hourly_entries = h_json.get("entries", [])
        for n in notices:
            if n not in top_warnings:
                top_warnings.append(n)
    else:
        hourly_entries = []

    buckets = []
    for pm in parsed_metrics:
        used_frac = max(0.0, min(1.0, pm["used_pct"] / 100.0))
        if pm["win_start"] is None or pm["reset_local"] is None:
            buckets.append(
                {
                    "group_name": f"Codex ({selected.get('plan', 'Unknown')})",
                    "group_key": "codex",
                    "bucket_id": f"codex-{pm['label'].lower()}",
                    "window": pm["label"].lower(),
                    "window_start_local": "unknown",
                    "reset_time_local": (
                        pm["reset_local"].isoformat(timespec="seconds")
                        if pm["reset_local"]
                        else "unknown"
                    ),
                    "remaining_fraction": round(1.0 - used_frac, 6),
                    "used_pct": round(pm["used_pct"], 4),
                    "spend_base_usd": None,
                    "spend_min_usd": None,
                    "spend_upper_usd": None,
                    "message_count_since_date": 0,
                    "alignment_method": "unknown_window_duration",
                    "implied_pool_base_usd": None,
                    "implied_pool_min_usd": None,
                    "implied_pool_upper_usd": None,
                    "confidence": "UNKNOWN_WINDOW",
                    "warnings": [
                        f"UNKNOWN_WINDOW_DURATION: unrecognized Codex window label '{pm['label']}' "
                        "or missing resets_at; cannot derive window_start without guessing."
                    ],
                }
            )
            continue

        start_floor = pm["win_start"].replace(minute=0, second=0, microsecond=0)
        boundary_frac = (pm["win_start"].minute * 60 + pm["win_start"].second) / 3600.0
        spend = 0.0
        msgs = 0
        for row in hourly_entries:
            h_dt = parse_local_hour(str(row.get("hour", "")), tz)
            cost = float(row.get("cost") or 0.0)
            mc = int(row.get("messageCount") or 0)
            if h_dt > start_floor:
                spend += cost
                msgs += mc
            elif h_dt == start_floor:
                spend += cost * (1.0 - boundary_frac)
                msgs += int(round(mc * (1.0 - boundary_frac)))

        conf, reasons = grade_confidence(
            used_fraction=used_frac,
            shift_abs=0.0,
            mixed_ambiguity=False,
            multi_account=multi_account,
        )
        implied = (spend / used_frac) if used_frac > 0 else None
        buckets.append(
            {
                "group_name": f"Codex ({selected.get('plan', 'Unknown')})",
                "group_key": "codex",
                "bucket_id": f"codex-{pm['label'].lower()}",
                "window": pm["label"].lower(),
                "window_start_local": pm["win_start"].isoformat(timespec="seconds"),
                "reset_time_local": pm["reset_local"].isoformat(timespec="seconds"),
                "remaining_fraction": round(1.0 - used_frac, 6),
                "used_pct": round(pm["used_pct"], 4),
                "spend_base_usd": round(spend, 4),
                "spend_min_usd": round(spend, 4),
                "spend_upper_usd": round(spend, 4),
                "message_count_since_date": msgs,
                "alignment_method": "codex_hourly_window",
                "implied_pool_base_usd": round(implied, 2) if implied is not None else None,
                "implied_pool_min_usd": round(implied, 2) if implied is not None else None,
                "implied_pool_upper_usd": round(implied, 2) if implied is not None else None,
                "confidence": conf,
                "warnings": reasons,
            }
        )

    return {
        "provider": "codex",
        "observed_at_local": now.isoformat(timespec="seconds"),
        "plan": selected.get("plan"),
        "multi_account_count": len(codex_accounts),
        "buckets": buckets,
        "warnings": top_warnings,
    }


def calibrate_custom(
    args: argparse.Namespace,
    timeout: float = DEFAULT_CMD_TIMEOUT,
) -> dict[str, Any]:
    tz = local_tz()
    now = dt.datetime.now(tz)
    top_warnings: list[str] = []

    if args.used_pct is not None and args.remaining_fraction is not None:
        raise CalibrationError("Specify only one of --used-pct or --remaining-fraction.")
    if args.used_pct is not None:
        if not math.isfinite(args.used_pct) or not (0.0 <= args.used_pct <= 100.0):
            raise CalibrationError("--used-pct must be a finite number between 0 and 100.")
        used_frac = args.used_pct / 100.0
    elif args.remaining_fraction is not None:
        if not math.isfinite(args.remaining_fraction) or not (0.0 <= args.remaining_fraction <= 1.0):
            raise CalibrationError("--remaining-fraction must be a finite number between 0 and 1.")
        used_frac = 1.0 - args.remaining_fraction
    else:
        raise CalibrationError("--provider custom requires --used-pct or --remaining-fraction.")

    if args.spend_usd is not None:
        if not math.isfinite(args.spend_usd) or args.spend_usd < 0:
            raise CalibrationError("--spend-usd must be a finite non-negative number.")
        spend_base = float(args.spend_usd)
        if args.cache_write_upper_usd is not None:
            if not math.isfinite(args.cache_write_upper_usd):
                raise CalibrationError("--cache-write-upper-usd must be a finite number.")
            spend_upper = float(args.cache_write_upper_usd)
        else:
            spend_upper = spend_base
        if spend_upper < spend_base:
            raise CalibrationError("--cache-write-upper-usd cannot be less than --spend-usd.")
        method = "manual_spend_input"
        msgs = 0
    elif args.client and args.since:
        m_json, notices = run_json_cmd(
            ["tokscale", "models", "-c", args.client, "--since", args.since, "--json", "--no-spinner"],
            "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
            timeout=timeout,
        )
        top_warnings.extend(notices)
        top_warnings.extend(inspect_tokscale_completeness(m_json))
        entries = m_json.get("entries", [])
        spend_base = sum(float(e.get("cost") or 0.0) for e in entries)
        spend_upper = spend_base + estimate_cache_write_uplift_usd(entries)
        msgs = sum(int(e.get("messageCount") or 0) for e in entries)
        method = f"tokscale_models_since:{args.client}"
    else:
        raise CalibrationError(
            "--provider custom requires either --spend-usd or (--client AND --since YYYY-MM-DD)."
        )

    conf, reasons = grade_confidence(used_fraction=used_frac, shift_abs=0.0, mixed_ambiguity=False)
    implied_base = (spend_base / used_frac) if used_frac > 0 else None
    implied_upper = (spend_upper / used_frac) if used_frac > 0 else None

    return {
        "provider": "custom",
        "observed_at_local": now.isoformat(timespec="seconds"),
        "buckets": [
            {
                "group_name": args.label,
                "group_key": "custom",
                "bucket_id": "custom",
                "window": args.window_label,
                "window_start_local": args.since or "manual",
                "reset_time_local": "manual",
                "remaining_fraction": round(1.0 - used_frac, 6),
                "used_pct": round(used_frac * 100.0, 4),
                "spend_base_usd": round(spend_base, 4),
                "spend_min_usd": round(spend_base, 4),
                "spend_upper_usd": round(spend_upper, 4),
                "message_count_since_date": msgs,
                "alignment_method": method,
                "implied_pool_base_usd": round(implied_base, 2) if implied_base is not None else None,
                "implied_pool_min_usd": round(implied_base, 2) if implied_base is not None else None,
                "implied_pool_upper_usd": round(implied_upper, 2) if implied_upper is not None else None,
                "confidence": conf,
                "warnings": reasons,
            }
        ],
        "warnings": top_warnings,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"### AI Quota Calibration ({result['provider']})",
        f"- Observed at: `{result['observed_at_local']}`",
    ]
    if result.get("weekly_to_5h_multipliers"):
        mult_parts = [
            f"`{k}` = **{v}x**"
            for k, v in result["weekly_to_5h_multipliers"].items()
            if v is not None
        ]
        if mult_parts:
            lines.append("- Weekly / 5h multiplier: " + ", ".join(mult_parts))
    lines.append("")
    lines.append(
        "| Pool | Window | Window Start -> Reset | Local Spend (Min/Base ~ CW Upper) | Quota Used | Implied Pool ($ API eq.) | Confidence |"
    )
    lines.append("| :--- | :---: | :--- | :---: | :---: | :---: | :---: |")

    for b in result["buckets"]:
        s_min = b.get("spend_min_usd")
        s_base = b.get("spend_base_usd")
        s_upper = b.get("spend_upper_usd")
        s_low = s_min if s_min is not None else s_base

        if s_low is None or s_upper is None:
            spend_str = "N/A"
        elif abs(s_upper - s_low) > 0.01:
            spend_str = f"${s_low:.2f} ~ ${s_upper:.2f}"
        else:
            spend_str = f"${s_low:.2f}"

        p_min = b.get("implied_pool_min_usd")
        p_base = b.get("implied_pool_base_usd")
        p_upper = b.get("implied_pool_upper_usd")
        p_low = p_min if p_min is not None else p_base

        if p_low is None:
            pool_str = "N/A (unknown window)" if b["confidence"] == "UNKNOWN_WINDOW" else "N/A (untouched)"
        elif p_upper is not None and abs(p_upper - p_low) > 0.5:
            pool_str = f"**${p_low:.0f} ~ ${p_upper:.0f}**"
        else:
            pool_str = f"**${p_low:.0f}**"

        win_range = f"`{b['window_start_local']}` -> `{b['reset_time_local']}`"
        lines.append(
            f"| {b['group_name']} (`{b['bucket_id']}`) | {b['window']} | {win_range} | "
            f"{spend_str} | {b['used_pct']:.2f}% | {pool_str} | `{b['confidence']}` |"
        )

    all_warnings = list(result.get("warnings") or [])
    for b in result["buckets"]:
        for w in b.get("warnings") or []:
            all_warnings.append(f"[{b['bucket_id']}] {w}")

    if all_warnings:
        lines.append("")
        lines.append("#### Warnings & Caveats")
        for w in all_warnings:
            lines.append(f"- {w}")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Calibrate black-box AI subscription quota pools against local tokscale spend."
    )
    p.add_argument(
        "--provider",
        choices=("antigravity", "codex", "custom"),
        required=True,
        help="Subscription provider adapter to calibrate.",
    )
    p.add_argument(
        "--samples",
        type=int,
        default=2,
        help="Number of Antigravity /usage reads to check settlement stability (default: 2).",
    )
    p.add_argument(
        "--settle-seconds",
        type=float,
        default=5.0,
        help="Delay in seconds between consecutive Antigravity /usage reads (default: 5.0).",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_CMD_TIMEOUT,
        help="Subprocess timeout in seconds for tokscale/agy commands (default: 60).",
    )
    p.add_argument(
        "--account-email",
        default=None,
        help="For --provider codex, select a specific account email from `tokscale usage`.",
    )
    p.add_argument("--label", default="Custom Pool", help="Display label for --provider custom.")
    p.add_argument("--window-label", default="custom", help="Window name for --provider custom.")
    p.add_argument("--used-pct", type=float, default=None, help="Observed used percentage (0-100).")
    p.add_argument(
        "--remaining-fraction",
        type=float,
        default=None,
        help="Observed remaining fraction (0.0-1.0).",
    )
    p.add_argument("--spend-usd", type=float, default=None, help="Observed window spend in USD.")
    p.add_argument(
        "--cache-write-upper-usd",
        type=float,
        default=None,
        help="Optional cache-write upper bound spend in USD.",
    )
    p.add_argument("--client", default=None, help="tokscale client name for --provider custom.")
    p.add_argument("--since", default=None, help="Start date (YYYY-MM-DD) for --provider custom.")
    p.add_argument(
        "--input-fixture",
        type=Path,
        default=None,
        help="Load frozen JSON snapshots from a local file instead of calling live CLIs.",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    fixture = None
    if args.input_fixture is not None:
        if not args.input_fixture.is_file():
            print(f"Error: fixture file not found: {args.input_fixture}", file=sys.stderr)
            return 2
        try:
            fixture = json.loads(args.input_fixture.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: failed to read fixture JSON '{args.input_fixture}': {exc}", file=sys.stderr)
            return 2

    try:
        if args.provider == "antigravity":
            result = calibrate_antigravity(
                samples_count=args.samples,
                settle_seconds=args.settle_seconds,
                fixture=fixture,
                timeout=args.timeout,
            )
        elif args.provider == "codex":
            result = calibrate_codex(
                account_email=args.account_email,
                fixture=fixture,
                timeout=args.timeout,
            )
        else:
            result = calibrate_custom(args, timeout=args.timeout)
    except CalibrationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
