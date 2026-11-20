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
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

WINDOW_DURATIONS = {
    "5h": dt.timedelta(hours=5),
    "five_hour": dt.timedelta(hours=5),
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


class CalibrationError(RuntimeError):
    """Explicit operational or input failure."""


def local_tz() -> dt.tzinfo:
    return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc


def parse_iso_datetime(value: str, tz: dt.tzinfo) -> dt.datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
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


def run_json_cmd(argv: list[str], binary_hint: str) -> Any:
    if shutil.which(argv[0]) is None:
        raise CalibrationError(
            f"Required CLI '{argv[0]}' not found in PATH. {binary_hint}"
        )
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[:400]
        raise CalibrationError(
            f"Command failed (exit {proc.returncode}): {' '.join(argv)}\n{detail}"
        )
    raw = proc.stdout.strip()
    if not raw:
        raise CalibrationError(f"Command returned empty output: {' '.join(argv)}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        # Some CLIs print warnings before JSON; attempt to parse from first { or [
        for ch in ("{", "["):
            idx = raw.find(ch)
            if idx != -1:
                try:
                    return json.loads(raw[idx:])
                except json.JSONDecodeError:
                    pass
        raise CalibrationError(
            f"Failed to parse JSON from {' '.join(argv)}: {exc}"
        ) from exc


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
            # Conservative fallback: attribute up to 25% of total entry cost
            extra += float(e.get("cost") or 0.0) * uplift
        else:
            extra += (inp / 1_000_000.0) * input_rate * uplift
    return extra


def assess_antigravity_stability(
    samples: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str], dict[str, float]]:
    """Compare 1..N usage snapshots to detect 0.01 reservation/replica jitter."""
    if not samples:
        raise CalibrationError("No Antigravity /usage samples available.")
    if len(samples) == 1:
        return samples[0], [], {}

    first = samples[0]
    last = samples[-1]
    warnings: list[str] = []
    shift_by_bucket: dict[str, float] = {}

    def extract_map(payload: dict[str, Any]) -> dict[str, float]:
        out: dict[str, float] = {}
        groups = payload.get("command", {}).get("data", {}).get("groups", [])
        for g in groups:
            for b in g.get("buckets", []):
                bid = str(b.get("id") or b.get("name"))
                out[bid] = float(b.get("remaining_fraction", 1.0))
        return out

    m1 = extract_map(first)
    m2 = extract_map(last)
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

    # Group models from `tokscale models --since <start_date>`
    group_models = [
        e for e in models_since_entries if model_classifier(str(e.get("model", ""))) == group_key
    ]
    other_models = [
        e for e in models_since_entries if model_classifier(str(e.get("model", ""))) != group_key
    ]
    base_since_cost = sum(float(e.get("cost") or 0.0) for e in group_models)
    other_since_cost = sum(float(e.get("cost") or 0.0) for e in other_models)
    total_msgs = sum(int(e.get("messageCount") or 0) for e in group_models)
    cache_write_extra = estimate_cache_write_uplift_usd(group_models)

    # Inspect hourly rows on/after start_date
    pre_pure_sub = 0.0
    pre_mixed_cost = 0.0
    any_group_strictly_before = False
    any_group_pre_window = False
    other_group_pre_window = False
    in_window_pure_cost = 0.0
    in_window_mixed_cost = 0.0

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
            if has_other:
                other_group_pre_window = True
        elif h_dt == start_hour_floor:
            if has_group:
                if boundary_elapsed_frac > 0:
                    any_group_pre_window = True
                if not has_other:
                    pre_pure_sub += cost * boundary_elapsed_frac
                    in_window_pure_cost += cost * (1.0 - boundary_elapsed_frac)
                else:
                    pre_mixed_cost += cost * boundary_elapsed_frac
                    in_window_mixed_cost += cost * (1.0 - boundary_elapsed_frac)
            if has_other and boundary_elapsed_frac > 0:
                other_group_pre_window = True
        else:
            if has_group:
                if not has_other:
                    in_window_pure_cost += cost
                else:
                    in_window_mixed_cost += cost

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
    # Case 3: Algebraic separation if the OTHER group never appeared before window_start
    elif not other_group_pre_window and other_since_cost >= 0.0:
        spend_base = max(0.0, in_window_pure_cost + in_window_mixed_cost - other_since_cost)
        spend_min = spend_base
        spend_max = spend_base
        method = "algebraic_mixed_hour_subtraction"
    else:
        # Unresolvable mixed pre-window hours: preserve honest [min, max] bounds
        spend_max = max(0.0, base_since_cost - pre_pure_sub)
        spend_min = max(0.0, base_since_cost - pre_pure_sub - pre_mixed_cost)
        spend_base = (spend_min + spend_max) / 2.0
        method = "bounded_mixed_hour_estimate"
        warnings.append(
            f"MIXED_HOUR_AMBIGUITY: pre-window hours on {start_date_str} mixed "
            f"multiple model groups (${pre_mixed_cost:.2f}); window spend is "
            f"bounded in [${spend_min:.2f}, ${spend_max:.2f}]."
        )

    # Scale cache-write uplift proportionally to in-window share of base_since_cost
    ratio = (spend_base / base_since_cost) if base_since_cost > 0 else 0.0
    spend_upper = spend_max + cache_write_extra * min(1.0, max(0.0, ratio))

    return {
        "spend_base_usd": round(spend_base, 6),
        "spend_min_usd": round(spend_min, 6),
        "spend_upper_usd": round(spend_upper, 6),
        "cache_write_extra_usd": round(cache_write_extra * min(1.0, max(0.0, ratio)), 6),
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
        reasons.append("MIXED_HOUR_AMBIGUITY: pre-window boundary mixed model groups.")
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
) -> dict[str, Any]:
    tz = local_tz()
    now = dt.datetime.now(tz)

    if fixture is not None:
        raw_samples = fixture.get("usage_samples") or [fixture["usage"]]
        now = parse_iso_datetime(fixture["now"], tz) if fixture.get("now") else now
    else:
        raw_samples = []
        for idx in range(max(1, samples_count)):
            if idx > 0 and settle_seconds > 0:
                time.sleep(settle_seconds)
            raw_samples.append(
                run_json_cmd(
                    ["agy", "-p", "/usage", "--output-format", "json"],
                    "Install Antigravity CLI (`agy`) and authenticate first.",
                )
            )

    chosen_usage, stability_warnings, shift_map = assess_antigravity_stability(raw_samples)
    cmd_data = chosen_usage.get("command", {}).get("data", {})
    groups = cmd_data.get("groups", [])
    if not groups:
        raise CalibrationError("Antigravity /usage JSON contained no quota groups.")

    # Discover all bucket window starts so we fetch tokscale once per distinct start date
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
            reset_local = parse_iso_datetime(reset_raw, tz) if reset_raw else now
            win_start = (reset_local - dur) if dur else reset_local
            start_date = win_start.strftime("%Y-%m-%d")
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
                    "reset_time_local": reset_local.isoformat(timespec="seconds"),
                    "window_start_local": win_start,
                    "start_date": start_date,
                }
            )

    # Identify groups whose 5h and weekly windows started at the exact same timestamp
    # (proves zero prior activity for that group before window_start).
    fresh_start_groups: set[str] = set()
    by_group_starts: dict[str, dict[str, dt.datetime]] = {}
    for spec in bucket_specs:
        by_group_starts.setdefault(spec["group_key"], {})[spec["window"]] = spec["window_start_local"]
    for gk, smap in by_group_starts.items():
        if "5h" in smap and "weekly" in smap and abs((smap["5h"] - smap["weekly"]).total_seconds()) <= 5:
            fresh_start_groups.add(gk)

    if fixture is not None:
        models_by_date: dict[str, list[dict[str, Any]]] = fixture.get("models_by_date") or {
            d: fixture.get("models", {}).get("entries", []) for d in distinct_dates
        }
        hourly_entries: list[dict[str, Any]] = fixture.get("hourly", {}).get("entries", [])
    else:
        models_by_date = {}
        for d in sorted(distinct_dates):
            m_json = run_json_cmd(
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
            )
            models_by_date[d] = m_json.get("entries", [])
        h_json = run_json_cmd(
            [
                "tokscale",
                "hourly",
                "-c",
                "antigravity-cli",
                "--since",
                earliest_date or now.strftime("%Y-%m-%d"),
                "--json",
                "--no-spinner",
            ],
            "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
        )
        hourly_entries = h_json.get("entries", [])

    calibrated_buckets: list[dict[str, Any]] = []
    group_windows: dict[str, dict[str, float]] = {}

    for spec in bucket_specs:
        rem = spec["remaining_fraction"]
        used = max(0.0, 1.0 - rem)
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

        group_windows.setdefault(spec["group_key"], {})[spec["window"]] = used

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
            # Note: exact only when both windows started together; otherwise ratio of implied pools
            b5 = next((b for b in calibrated_buckets if b["group_key"] == gk and b["window"] == "5h"), None)
            bw = next((b for b in calibrated_buckets if b["group_key"] == gk and b["window"] == "weekly"), None)
            if b5 and bw and b5["window_start_local"] == bw["window_start_local"]:
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
        "warnings": stability_warnings,
    }


def calibrate_codex(
    account_email: str | None = None,
    fixture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tz = local_tz()
    now = dt.datetime.now(tz)

    if fixture is not None:
        usage_list = fixture["usage"]
        now = parse_iso_datetime(fixture["now"], tz) if fixture.get("now") else now
    else:
        usage_list = run_json_cmd(
            ["tokscale", "usage", "--json"],
            "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
        )

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
            raise CalibrationError(f"Codex account '{account_email}' not found in `tokscale usage --json`.")
    else:
        selected = next((a for a in codex_accounts if (a.get("account") or {}).get("is_active")), codex_accounts[0])

    multi_account = len(codex_accounts) > 1
    top_warnings: list[str] = []
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
        reset_raw = str(m.get("resets_at") or "")
        reset_local = parse_iso_datetime(reset_raw, tz) if reset_raw else now
        win_start = (reset_local - dur) if dur else reset_local
        sdate = win_start.strftime("%Y-%m-%d")
        if earliest_date is None or sdate < earliest_date:
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
    else:
        h_json = run_json_cmd(
            [
                "tokscale",
                "hourly",
                "-c",
                "codex",
                "--since",
                earliest_date or now.strftime("%Y-%m-%d"),
                "--json",
                "--no-spinner",
            ],
            "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
        )
        hourly_entries = h_json.get("entries", [])

    buckets = []
    for pm in parsed_metrics:
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

        used_frac = max(0.0, min(1.0, pm["used_pct"] / 100.0))
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


def calibrate_custom(args: argparse.Namespace) -> dict[str, Any]:
    tz = local_tz()
    now = dt.datetime.now(tz)

    if args.used_pct is not None and args.remaining_fraction is not None:
        raise CalibrationError("Specify only one of --used-pct or --remaining-fraction.")
    if args.used_pct is not None:
        if not (0.0 <= args.used_pct <= 100.0) or math.isnan(args.used_pct):
            raise CalibrationError("--used-pct must be between 0 and 100.")
        used_frac = args.used_pct / 100.0
    elif args.remaining_fraction is not None:
        if not (0.0 <= args.remaining_fraction <= 1.0) or math.isnan(args.remaining_fraction):
            raise CalibrationError("--remaining-fraction must be between 0 and 1.")
        used_frac = 1.0 - args.remaining_fraction
    else:
        raise CalibrationError("--provider custom requires --used-pct or --remaining-fraction.")

    if args.spend_usd is not None:
        if args.spend_usd < 0 or math.isnan(args.spend_usd):
            raise CalibrationError("--spend-usd must be non-negative.")
        spend_base = float(args.spend_usd)
        spend_upper = (
            float(args.cache_write_upper_usd)
            if args.cache_write_upper_usd is not None
            else spend_base
        )
        if spend_upper < spend_base:
            raise CalibrationError("--cache-write-upper-usd cannot be less than --spend-usd.")
        method = "manual_spend_input"
        msgs = 0
    elif args.client and args.since:
        m_json = run_json_cmd(
            ["tokscale", "models", "-c", args.client, "--since", args.since, "--json", "--no-spinner"],
            "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
        )
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
        "warnings": [],
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
        "| Pool | Window | Window Start -> Reset | Local Spend (Base ~ CW Upper) | Quota Used | Implied Pool ($ API eq.) | Confidence |"
    )
    lines.append("| :--- | :---: | :--- | :---: | :---: | :---: | :---: |")

    for b in result["buckets"]:
        if abs(b["spend_upper_usd"] - b["spend_base_usd"]) > 0.01:
            spend_str = f"${b['spend_base_usd']:.2f} ~ ${b['spend_upper_usd']:.2f}"
        else:
            spend_str = f"${b['spend_base_usd']:.2f}"

        if b["implied_pool_base_usd"] is None:
            pool_str = "N/A (untouched)"
        elif b["implied_pool_upper_usd"] is not None and abs(
            b["implied_pool_upper_usd"] - b["implied_pool_base_usd"]
        ) > 0.5:
            pool_str = f"**${b['implied_pool_base_usd']:.0f} ~ ${b['implied_pool_upper_usd']:.0f}**"
        else:
            pool_str = f"**${b['implied_pool_base_usd']:.0f}**"

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
        default=4.0,
        help="Delay in seconds between consecutive Antigravity /usage reads (default: 4.0).",
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
        fixture = json.loads(args.input_fixture.read_text(encoding="utf-8"))

    try:
        if args.provider == "antigravity":
            result = calibrate_antigravity(
                samples_count=args.samples,
                settle_seconds=args.settle_seconds,
                fixture=fixture,
            )
        elif args.provider == "codex":
            result = calibrate_codex(account_email=args.account_email, fixture=fixture)
        else:
            result = calibrate_custom(args)
    except CalibrationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
