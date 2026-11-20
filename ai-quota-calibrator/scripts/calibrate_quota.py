#!/usr/bin/env python3
"""Calibrate black-box AI subscription quotas against local tokscale spend.

Zero-dependency Python 3.9+ stdlib CLI. Reconciles live provider quota
percentages (Antigravity `agy -p /usage --output-format json`, Codex
`tokscale usage --json`, or custom percentage inputs) with local `tokscale`
spend aligned to exact window boundaries, including runway projections,
lockout-cap detection, directional stability checks, and top burning sessions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import shutil
import statistics
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
    "1d": dt.timedelta(days=1),
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
ANTIGRAVITY_SOFT_LOCKOUT_THRESHOLD = 0.01  # 1% pre-reservation lockout floor
DEFAULT_CMD_TIMEOUT = 60.0
AUTO_SESSIONS_USED_THRESHOLD = 80.0
DEFAULT_TOP_SESSIONS = 5

_FRAC_SECONDS_RE = re.compile(r"(\d{2}:\d{2}:\d{2})\.(\d+)")
_NUM_HOURS_RE = re.compile(r"^(\d+)[\s-]?h(?:ours?|rs?)?$")
_NUM_DAYS_RE = re.compile(r"^(\d+)[\s-]?d(?:ays?)?$")
_NUM_WEEKS_RE = re.compile(r"^(\d+)[\s-]?w(?:eeks?|ks?)?$")


class CalibrationError(RuntimeError):
    """Explicit operational or input failure."""


def local_tz() -> dt.tzinfo:
    return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc


def parse_iso_datetime(value: str, tz: dt.tzinfo) -> dt.datetime:
    """Parse ISO-8601 / RFC3339 timestamps (including 1-9 fractional digits on Py 3.9+)."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
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


def parse_window_duration(label: str) -> dt.timedelta | None:
    """Resolve a window label into an exact timedelta without guessing."""
    low = label.strip().lower()
    if not low:
        return None
    if low in WINDOW_DURATIONS:
        return WINDOW_DURATIONS[low]

    m_h = _NUM_HOURS_RE.match(low)
    if m_h:
        n = int(m_h.group(1))
        return dt.timedelta(hours=n) if n > 0 else None

    m_d = _NUM_DAYS_RE.match(low)
    if m_d:
        n = int(m_d.group(1))
        return dt.timedelta(days=n) if n > 0 else None

    m_w = _NUM_WEEKS_RE.match(low)
    if m_w:
        n = int(m_w.group(1))
        return dt.timedelta(weeks=n) if n > 0 else None

    if "five" in low and "hour" in low:
        return dt.timedelta(hours=5)
    if re.search(r"\b(?:weekly|1[\s-]?week)\b", low):
        return dt.timedelta(days=7)
    if re.search(r"\b(?:monthly|1[\s-]?month)\b", low):
        return dt.timedelta(days=30)
    if re.search(r"\b(?:daily|24h|1[\s-]?day)\b", low):
        return dt.timedelta(days=1)
    return None


def format_duration(seconds: float) -> str:
    """Format a positive duration in seconds into a concise human string."""
    if seconds <= 0:
        return "expired"
    total_mins = int(round(seconds / 60.0))
    if total_mins < 1:
        return "<1m"
    days, rem_m = divmod(total_mins, 1440)
    hours, mins = divmod(rem_m, 60)
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


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
) -> tuple[dict[str, Any], list[str], list[str], dict[str, float]]:
    """Compare 1..N usage snapshots across all consecutive pairs with directional awareness.

    Returns (chosen_sample, warnings, info_notes, signed_delta_by_bucket) where:
    - positive signed_delta indicates an upward rebound in at least one consecutive step
      (magnitude = max of net shift, total spread, and max rebound step);
    - negative signed_delta indicates monotonic non-increasing burn across all steps
      (magnitude = total spread);
    - 0.0 indicates stability within STABILITY_TOLERANCE across all steps.
    """
    if not samples:
        raise CalibrationError("No Antigravity /usage samples available.")
    if len(samples) == 1:
        return samples[0], [], [], {}

    last = samples[-1]
    warnings: list[str] = []
    info_notes: list[str] = []
    delta_by_bucket: dict[str, float] = {}

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

    extracted = [extract_buckets(s) for s in samples]
    last_map, _ = extracted[-1]

    for bid in last_map:
        series = [m[bid] for m, _ in extracted if bid in m]
        if len(series) < 2:
            delta_by_bucket[bid] = 0.0
            continue
        v_first, v_last = series[0], series[-1]
        steps = [round(series[i + 1] - series[i], 6) for i in range(len(series) - 1)]
        max_rebound = max((d for d in steps if d > 0.0), default=0.0)
        max_drop = max((-d for d in steps if d < 0.0), default=0.0)
        spread = round(max(series) - min(series), 6)
        net_delta = round(v_last - v_first, 6)
        effective_shift = round(max(abs(net_delta), spread, max_rebound, max_drop), 6)
        used_now = round(max(0.0, 1.0 - v_last), 6)

        if max_rebound > STABILITY_TOLERANCE:
            delta_by_bucket[bid] = effective_shift
            warnings.append(
                f"RESERVATION_REFUND_OR_REPLICA_LAG: bucket '{bid}' rebounded upward by "
                f"+{max_rebound * 100:.2f}% ({v_first * 100:.2f}% -> {v_last * 100:.2f}%) between reads."
            )
        elif effective_shift > STABILITY_TOLERANCE:
            delta_by_bucket[bid] = -effective_shift
            rel = round(effective_shift / max(used_now, 1e-6), 6)
            if used_now >= 0.20 and rel <= 0.05 and effective_shift <= 0.015:
                info_notes.append(
                    f"CONCURRENT_BURN: bucket '{bid}' decreased monotonically by "
                    f"{effective_shift * 100:.2f}% ({v_first * 100:.2f}% -> {v_last * 100:.2f}%, "
                    f"{rel * 100:.1f}% relative) from an active session."
                )
            else:
                warnings.append(
                    f"Bucket '{bid}' decreased by {effective_shift * 100:.2f}% between consecutive "
                    f"reads ({v_first * 100:.2f}% -> {v_last * 100:.2f}%), indicating active in-flight "
                    f"requests or 1% pre-reservation."
                )
        else:
            delta_by_bucket[bid] = 0.0

    ratio_warned: set[str] = set()
    for idx in range(len(extracted) - 1):
        gw1 = extracted[idx][1]
        gw2 = extracted[idx + 1][1]
        for gk, w2 in gw2.items():
            if gk in ratio_warned:
                continue
            w1 = gw1.get(gk, {})
            u5_1, uw_1 = w1.get("5h", 0.0), w1.get("weekly", 0.0)
            u5_2, uw_2 = w2.get("5h", 0.0), w2.get("weekly", 0.0)
            if u5_1 > 0.005 and uw_1 > 0.005 and u5_2 > 0.005 and uw_2 > 0.005:
                r1 = u5_1 / uw_1
                r2 = u5_2 / uw_2
                if abs(r2 - r1) > RATIO_SHIFT_TOLERANCE:
                    ratio_warned.add(gk)
                    warnings.append(
                        f"Group '{gk}' used_5h/used_weekly ratio shifted between consecutive reads "
                        f"({r1:.2f}x -> {r2:.2f}x), consistent with a flat 1% in-flight reservation "
                        f"or 0% floor clamping."
                    )

    return last, warnings, info_notes, delta_by_bucket


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

    if fresh_window_start and not any_group_strictly_before:
        spend_base = base_since_cost
        spend_min = base_since_cost
        spend_max = base_since_cost
        method = "exact_fresh_window_start"
    elif not any_group_pre_window:
        spend_base = base_since_cost
        spend_min = base_since_cost
        spend_max = base_since_cost
        method = "exact_models_since"
    elif pre_mixed_cost == 0.0:
        spend_base = max(0.0, base_since_cost - pre_pure_sub)
        spend_min = spend_base
        spend_max = spend_base
        method = "models_since_minus_pure_pre_hours"
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

    # Estimate in-window message count proportionally when pre-window hours were subtracted
    msg_ratio = (spend_base / base_since_cost) if base_since_cost > 0 else 0.0
    window_msgs = int(round(total_msgs * min(1.0, max(0.0, msg_ratio))))

    return {
        "spend_base_usd": round(spend_base, 6),
        "spend_min_usd": round(spend_min, 6),
        "spend_upper_usd": round(spend_upper, 6),
        "cache_write_extra_usd": round(cw_uplift_scaled, 6),
        "message_count": total_msgs,
        "window_message_count": window_msgs,
        "alignment_method": method,
        "warnings": warnings,
    }


def determine_lockout_state(remaining_fraction: float, provider: str) -> str:
    if round(remaining_fraction, 6) <= 0.001:
        return "LOCKED"
    if provider == "antigravity" and remaining_fraction < ANTIGRAVITY_SOFT_LOCKOUT_THRESHOLD:
        return "SOFT_LOCKOUT"
    return "OPEN"


def grade_confidence(
    used_fraction: float,
    signed_delta: float,
    mixed_ambiguity: bool,
    multi_account: bool = False,
    lockout_state: str = "OPEN",
    is_fresh_lockout_cap: bool = False,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    used_norm = round(used_fraction, 6)
    signed_norm = round(signed_delta, 6)
    shift_abs = round(abs(signed_norm), 6)
    is_rebound = signed_norm > STABILITY_TOLERANCE

    if used_norm <= 0.0:
        return "UNTOUCHED", ["Bucket is at 100% remaining; no spend to invert."]

    if lockout_state == "SOFT_LOCKOUT":
        reasons.append(
            f"SOFT_LOCKOUT: only {(1.0 - used_fraction) * 100:.2f}% remaining (< 1% pre-reservation "
            "threshold); new requests may already be rate-limited."
        )

    rel_shift = round(shift_abs / max(used_norm, 1e-6), 6)
    severe_jitter = shift_abs > STABILITY_TOLERANCE and (rel_shift > 0.15 or shift_abs > 0.015)

    # Fresh simultaneous 5h window hitting lockout while sibling weekly remains open directly
    # measures the hard cap for that 5h window (not an unknown-timestamp historical saturation).
    if is_fresh_lockout_cap and not mixed_ambiguity and not severe_jitter and not multi_account:
        reasons.append(
            "LOCKOUT_CAP: bucket hit lockout from a fresh simultaneous window start while "
            "the weekly pool remains open; local spend directly measures this 5h hard cap."
        )
        return "LOCKOUT_CAP", reasons

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

    if severe_jitter:
        reasons.append(
            f"UNSTABLE_READINGS: consecutive reads diverged by {shift_abs * 100:.2f}% "
            f"({rel_shift * 100:.1f}% of consumed quota); re-run after active turns settle."
        )
        return "LOW", reasons

    if mixed_ambiguity:
        return "LOW", reasons

    if is_rebound:
        reasons.append(
            f"RESERVATION_REFUND_OR_REPLICA_LAG: remaining fraction increased by "
            f"+{shift_abs * 100:.2f}% between reads; re-check once settled."
        )
        return "MEDIUM", reasons

    # Monotonic downward burn (signed_delta < -STABILITY_TOLERANCE):
    # tolerate small relative concurrent burn (<= 5% relative on >= 20% used) without downgrading HIGH.
    if signed_norm < -STABILITY_TOLERANCE:
        if not (used_norm >= 0.20 and rel_shift <= 0.05):
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


def compute_runway_metrics(
    now: dt.datetime,
    window_start: dt.datetime | None,
    reset_local: dt.datetime | None,
    remaining_fraction: float,
    lockout_state: str,
    spend_base: float | None,
    implied_base: float | None,
    implied_upper: float | None,
    window_msgs: int,
) -> dict[str, Any]:
    """Compute deterministic countdown, remaining API dollars, and burn-rate ETA."""
    if reset_local is not None:
        ttr_sec = max(0, int(round((reset_local - now).total_seconds())))
        ttr_str = format_duration(ttr_sec)
    else:
        ttr_sec = None
        ttr_str = None

    raw_rem_usd: float | None = None
    if lockout_state in ("LOCKED", "SOFT_LOCKOUT"):
        rem_usd_base = 0.0
        rem_usd_upper = 0.0
    elif implied_base is not None:
        raw_rem_usd = max(0.0, implied_base * remaining_fraction)
        rem_usd_base = round(raw_rem_usd, 2)
        rem_usd_upper = round(max(0.0, (implied_upper or implied_base) * remaining_fraction), 2)
    else:
        rem_usd_base = None
        rem_usd_upper = None

    avg_cpm = (
        round(spend_base / window_msgs, 4)
        if (spend_base is not None and spend_base > 0 and window_msgs > 0)
        else None
    )

    if lockout_state in ("LOCKED", "SOFT_LOCKOUT"):
        est_rem_msgs: int | None = 0
    elif rem_usd_base is not None and avg_cpm is not None and avg_cpm > 0:
        est_rem_msgs = int(rem_usd_base / avg_cpm)
    else:
        est_rem_msgs = None

    raw_burn_rate: float | None = None
    burn_rate: float | None = None
    if window_start is not None and spend_base is not None and spend_base > 0:
        elapsed_h = (now - window_start).total_seconds() / 3600.0
        if elapsed_h >= 0.05:
            raw_burn_rate = spend_base / elapsed_h
            burn_rate = round(raw_burn_rate, 2)

    if lockout_state in ("LOCKED", "SOFT_LOCKOUT"):
        eta_str: str | None = "0m (locked)"
    elif raw_rem_usd is not None and raw_rem_usd > 0 and raw_burn_rate is not None and raw_burn_rate > 0:
        eta_sec = (raw_rem_usd / raw_burn_rate) * 3600.0
        eta_str = "< 1m" if eta_sec < 60 else format_duration(eta_sec)
    else:
        eta_str = None

    return {
        "time_to_reset_seconds": ttr_sec,
        "time_to_reset": ttr_str,
        "remaining_usd_base": rem_usd_base,
        "remaining_usd_upper": rem_usd_upper,
        "avg_cost_per_msg_usd": avg_cpm,
        "estimated_remaining_msgs": est_rem_msgs,
        "burn_rate_usd_per_hour": burn_rate,
        "eta_to_exhaustion": eta_str,
    }


def summarize_top_sessions(
    session_entries: list[dict[str, Any]],
    limit: int,
    model_classifier: Any | None = None,
    target_groups: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate and rank top burning sessions, flagging context-snowball outliers."""
    if limit <= 0 or not session_entries:
        return []

    by_group_total: dict[str, float] = {}
    by_group_cpms: dict[str, list[float]] = {}
    parsed: list[dict[str, Any]] = []

    for e in session_entries:
        model = str(e.get("model") or "unknown")
        gk = model_classifier(model) if model_classifier else "all"
        if target_groups and gk not in target_groups:
            continue
        cost = float(e.get("cost") or 0.0)
        msgs = int(e.get("messageCount") or 0)
        inp = int(e.get("input") or 0)
        cw = int(e.get("cacheWrite") or 0)
        cr = int(e.get("cacheRead") or 0)
        tot_in = inp + cw + cr
        cr_pct = round((cr / tot_in * 100.0), 1) if tot_in > 0 else 0.0
        avg_ctx_k = round((tot_in / msgs) / 1000.0, 1) if msgs > 0 else 0.0
        cpm = (cost / msgs) if msgs > 0 else 0.0
        by_group_total[gk] = by_group_total.get(gk, 0.0) + cost
        if msgs > 0 and cost > 0:
            by_group_cpms.setdefault(gk, []).append(cpm)
        parsed.append(
            {
                "session_id": str(e.get("sessionId") or e.get("session") or "unknown"),
                "group_key": gk,
                "model": model,
                "message_count": msgs,
                "cost_usd": round(cost, 4),
                "avg_cost_per_msg_usd": round(cpm, 4),
                "avg_context_k": avg_ctx_k,
                "cache_read_pct": cr_pct,
            }
        )

    medians = {
        gk: statistics.median(vals) for gk, vals in by_group_cpms.items() if vals
    }

    parsed.sort(key=lambda x: x["cost_usd"], reverse=True)
    out: list[dict[str, Any]] = []
    for item in parsed[:limit]:
        gk = item["group_key"]
        gtot = by_group_total.get(gk, 0.0)
        share = round((item["cost_usd"] / gtot * 100.0), 1) if gtot > 0 else 0.0
        med = medians.get(gk, 0.0)
        snowball = (
            item["message_count"] >= 50
            and item["cache_read_pct"] >= 90.0
            and (
                (med > 0 and item["avg_cost_per_msg_usd"] >= 1.5 * med)
                or item["avg_cost_per_msg_usd"] >= 0.09
            )
        )
        out.append(
            {
                **item,
                "share_of_group_spend_pct": share,
                "context_snowball": snowball,
            }
        )
    return out


def calibrate_antigravity(
    samples_count: int,
    settle_seconds: float,
    fixture: dict[str, Any] | None = None,
    timeout: float = DEFAULT_CMD_TIMEOUT,
    top_sessions: int | None = None,
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

    chosen_usage, stability_warnings, info_notes, delta_map = assess_antigravity_stability(raw_samples)
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
            dur = parse_window_duration(window)
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
                    "reset_local_dt": reset_local,
                    "reset_time_local": (
                        reset_local.isoformat(timespec="seconds") if reset_local else "unknown"
                    ),
                    "window_start_local": win_start,
                    "start_date": start_date,
                }
            )

    fresh_start_groups: set[str] = set()
    by_group_starts: dict[str, dict[str, dt.datetime]] = {}
    by_group_used: dict[str, dict[str, float]] = {}
    for spec in bucket_specs:
        gk = spec["group_key"]
        by_group_used.setdefault(gk, {})[spec["window"]] = max(0.0, 1.0 - spec["remaining_fraction"])
        if spec["window_start_local"] is not None:
            by_group_starts.setdefault(gk, {})[spec["window"]] = spec["window_start_local"]
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
        gk = spec["group_key"]
        lockout_state = determine_lockout_state(rem, "antigravity")
        group_windows.setdefault(gk, {})[spec["window"]] = used

        if spec["window_start_local"] is None or spec["start_date"] is None:
            runway = compute_runway_metrics(
                now=now,
                window_start=None,
                reset_local=spec["reset_local_dt"],
                remaining_fraction=rem,
                lockout_state=lockout_state,
                spend_base=None,
                implied_base=None,
                implied_upper=None,
                window_msgs=0,
            )
            calibrated_buckets.append(
                {
                    "group_name": spec["group_name"],
                    "group_key": gk,
                    "bucket_id": spec["bucket_id"],
                    "window": spec["window"],
                    "window_start_local": "unknown",
                    "reset_time_local": spec["reset_time_local"],
                    "remaining_fraction": rem,
                    "used_pct": round(used * 100.0, 4),
                    "lockout_state": lockout_state,
                    "spend_base_usd": None,
                    "spend_min_usd": None,
                    "spend_upper_usd": None,
                    "message_count_since_date": 0,
                    "window_message_count": 0,
                    "alignment_method": "unknown_window_duration",
                    "implied_pool_base_usd": None,
                    "implied_pool_min_usd": None,
                    "implied_pool_upper_usd": None,
                    "confidence": "UNKNOWN_WINDOW",
                    **runway,
                    "warnings": [
                        f"UNKNOWN_WINDOW_DURATION: unrecognized window '{spec['window']}' "
                        f"or missing reset_time; cannot align spend without guessing."
                    ],
                }
            )
            continue

        if round(used, 6) <= 0.0:
            spend_info = {
                "spend_base_usd": 0.0,
                "spend_min_usd": 0.0,
                "spend_upper_usd": 0.0,
                "cache_write_extra_usd": 0.0,
                "message_count": 0,
                "window_message_count": 0,
                "alignment_method": "untouched_bucket",
                "warnings": [],
            }
        else:
            spend_info = compute_group_window_spend(
                group_key=gk,
                window_start=spec["window_start_local"],
                models_since_entries=models_by_date.get(spec["start_date"], []),
                hourly_entries=hourly_entries,
                tz=tz,
                model_classifier=classify_antigravity_model,
                fresh_window_start=(gk in fresh_start_groups or spec["window"] == "weekly"),
            )
        mixed_amb = any("MIXED_HOUR_AMBIGUITY" in w for w in spend_info["warnings"])
        signed_delta = delta_map.get(spec["bucket_id"], 0.0)
        sibling_weekly_used = by_group_used.get(gk, {}).get("weekly", 1.0)
        is_fresh_lockout_cap = (
            spec["window"] == "5h"
            and gk in fresh_start_groups
            and lockout_state in ("LOCKED", "SOFT_LOCKOUT")
            and sibling_weekly_used < 0.99
            and spend_info["spend_base_usd"] > 0
        )

        confidence, conf_reasons = grade_confidence(
            used_fraction=used,
            signed_delta=signed_delta,
            mixed_ambiguity=mixed_amb,
            lockout_state=lockout_state,
            is_fresh_lockout_cap=is_fresh_lockout_cap,
        )

        # For LOCKOUT_CAP (exact fresh 5h hard cap), the spend itself is the cap even if
        # soft-locked at 99.3% used (avoids tiny 0.7% extrapolation drift).
        divisor = 1.0 if confidence == "LOCKOUT_CAP" else used
        implied_base = (spend_info["spend_base_usd"] / divisor) if divisor > 0 else None
        implied_min = (spend_info["spend_min_usd"] / divisor) if divisor > 0 else None
        implied_upper = (spend_info["spend_upper_usd"] / divisor) if divisor > 0 else None

        runway = compute_runway_metrics(
            now=now,
            window_start=spec["window_start_local"],
            reset_local=spec["reset_local_dt"],
            remaining_fraction=rem,
            lockout_state=lockout_state,
            spend_base=spend_info["spend_base_usd"],
            implied_base=implied_base,
            implied_upper=implied_upper,
            window_msgs=spend_info["window_message_count"],
        )

        calibrated_buckets.append(
            {
                "group_name": spec["group_name"],
                "group_key": gk,
                "bucket_id": spec["bucket_id"],
                "window": spec["window"],
                "window_start_local": spec["window_start_local"].isoformat(timespec="seconds"),
                "reset_time_local": spec["reset_time_local"],
                "remaining_fraction": rem,
                "used_pct": round(used * 100.0, 4),
                "lockout_state": lockout_state,
                "spend_base_usd": round(spend_info["spend_base_usd"], 4),
                "spend_min_usd": round(spend_info["spend_min_usd"], 4),
                "spend_upper_usd": round(spend_info["spend_upper_usd"], 4),
                "message_count_since_date": spend_info["message_count"],
                "window_message_count": spend_info["window_message_count"],
                "alignment_method": spend_info["alignment_method"],
                "implied_pool_base_usd": round(implied_base, 2) if implied_base is not None else None,
                "implied_pool_min_usd": round(implied_min, 2) if implied_min is not None else None,
                "implied_pool_upper_usd": round(implied_upper, 2) if implied_upper is not None else None,
                "confidence": confidence,
                **runway,
                "warnings": spend_info["warnings"] + conf_reasons,
            }
        )

    # Guard against physically impossible 5h > weekly implied pool caused by a mid-hour 5h reset
    # or mixed-hour ambiguity sweeping pre-reset spend from boundary hours in `tokscale hourly`.
    # Note: do NOT compare independent remaining dollars (rem5 vs remw), because a clean fresh 5h
    # window can legitimately have more remaining dollars than a nearly spent weekly window.
    for gk in dict.fromkeys(b["group_key"] for b in calibrated_buckets):
        b5 = next((b for b in calibrated_buckets if b["group_key"] == gk and b["window"] == "5h"), None)
        bw = next((b for b in calibrated_buckets if b["group_key"] == gk and b["window"] == "weekly"), None)
        if not (b5 and bw):
            continue
        p5 = b5.get("implied_pool_base_usd")
        p5_hi = b5.get("implied_pool_upper_usd")
        pw = bw.get("implied_pool_base_usd")
        if p5 is None or pw is None:
            continue
        exceeds_cap = p5 > pw * 1.05
        low_conf_upper_exceeds = (
            b5.get("confidence") == "LOW"
            and p5_hi is not None
            and p5_hi > pw * 1.05
            and (b5.get("spend_min_usd") == 0.0 or b5.get("used_pct", 100.0) < 10.0)
        )
        if exceeds_cap or low_conf_upper_exceeds:
            b5["boundary_hour_overcount"] = True
            b5["confidence"] = "LOW"
            b5["implied_pool_base_usd"] = None
            b5["implied_pool_min_usd"] = None
            b5["implied_pool_upper_usd"] = None
            b5["remaining_usd_base"] = None
            b5["remaining_usd_upper"] = None
            b5["avg_cost_per_msg_usd"] = None
            b5["estimated_remaining_msgs"] = None
            b5["burn_rate_usd_per_hour"] = None
            b5["eta_to_exhaustion"] = None
            b5["warnings"].append(
                f"MID_HOUR_RESET_OVERCOUNT: 5h window started at {b5['window_start_local']} "
                f"so boundary-hour spend (${b5['spend_min_usd']:.2f} ~ ${b5['spend_upper_usd']:.2f}) "
                f"cannot cleanly separate pre-reset usage (naive 5h implied ${p5:.0f} / upper ${(p5_hi or p5):.0f} vs weekly ${pw:.0f}); "
                "withholding 5h dollar projection until post-reset spend settles."
            )

    multipliers: dict[str, float | None] = {}
    clamped_multipliers: dict[str, bool] = {}
    for gk, wmap in group_windows.items():
        u5 = wmap.get("5h", 0.0)
        uw = wmap.get("weekly", 0.0)
        b5 = next((b for b in calibrated_buckets if b["group_key"] == gk and b["window"] == "5h"), None)
        bw = next((b for b in calibrated_buckets if b["group_key"] == gk and b["window"] == "weekly"), None)
        if u5 > 0 and uw > 0:
            is_clamped = bool(b5 and b5["lockout_state"] in ("LOCKED", "SOFT_LOCKOUT"))
            if gk in fresh_start_groups:
                multipliers[gk] = round(u5 / uw, 4)
                clamped_multipliers[gk] = is_clamped
                if is_clamped:
                    top_warnings.append(
                        f"CLAMPED_MULTIPLIER: group '{gk}' 5h bucket is at/near 0% ({b5['lockout_state']}); "
                        f"observed ratio {multipliers[gk]:.2f}x is a lower bound because 5h is clamped at 0%."
                    )
            elif b5 and bw and b5["implied_pool_base_usd"] and bw["implied_pool_base_usd"]:
                multipliers[gk] = round(bw["implied_pool_base_usd"] / b5["implied_pool_base_usd"], 2)
                clamped_multipliers[gk] = is_clamped
            else:
                multipliers[gk] = None
                clamped_multipliers[gk] = False
        else:
            multipliers[gk] = None
            clamped_multipliers[gk] = False

    # Build alternate-pool switch recommendations when any group is LOCKED or SOFT_LOCKOUT.
    # When multiple windows in a group are locked, report the binding (longest) lockout.
    locked_groups: dict[str, dict[str, Any]] = {}
    open_groups: dict[str, dict[str, Any]] = {}

    def _lockout_rank(bucket: dict[str, Any]) -> tuple[int, int]:
        ttr_sec = bucket.get("time_to_reset_seconds")
        return (ttr_sec if isinstance(ttr_sec, int) else -1, 1 if bucket["window"] == "weekly" else 0)

    for b in calibrated_buckets:
        gk = b["group_key"]
        if b["lockout_state"] in ("LOCKED", "SOFT_LOCKOUT"):
            prev = locked_groups.get(gk)
            if prev is None or _lockout_rank(b) > _lockout_rank(prev):
                locked_groups[gk] = b
    for gk in dict.fromkeys(b["group_key"] for b in calibrated_buckets):
        if gk in locked_groups:
            continue
        gb = [b for b in calibrated_buckets if b["group_key"] == gk]
        if gb and all(b["lockout_state"] == "OPEN" for b in gb):
            b5 = next((b for b in gb if b["window"] == "5h"), None)
            bw = next((b for b in gb if b["window"] == "weekly"), None)
            rep = b5 or bw or gb[0]
            open_groups[gk] = {
                "group_name": rep["group_name"],
                "group_key": gk,
                "remaining_5h_pct": round(b5["remaining_fraction"] * 100.0, 1) if b5 is not None else None,
                "remaining_weekly_pct": round(bw["remaining_fraction"] * 100.0, 1) if bw is not None else None,
                "remaining_5h_usd": b5["remaining_usd_base"] if b5 is not None else None,
                "remaining_weekly_usd": bw["remaining_usd_base"] if bw is not None else None,
            }

    switch_recommendations: list[dict[str, Any]] = []
    for lgk, lb in locked_groups.items():
        if open_groups:
            switch_recommendations.append(
                {
                    "locked_group": lb["group_name"],
                    "locked_bucket": lb["bucket_id"],
                    "lockout_state": lb["lockout_state"],
                    "resets_in": lb["time_to_reset"],
                    "reset_time_local": lb["reset_time_local"],
                    "available_alternatives": list(open_groups.values()),
                }
            )

    # Top-session attribution: auto-enabled on high burn (>=80% or locked) unless explicitly 0
    high_pressure_buckets = [
        b
        for b in calibrated_buckets
        if b["used_pct"] >= AUTO_SESSIONS_USED_THRESHOLD or b["lockout_state"] != "OPEN"
    ]
    high_pressure_groups = {b["group_key"] for b in high_pressure_buckets}
    effective_top_n = (
        top_sessions
        if top_sessions is not None
        else (DEFAULT_TOP_SESSIONS if high_pressure_groups else 0)
    )
    session_attribution: list[dict[str, Any]] = []
    sess_since: str | None = None
    if effective_top_n > 0:
        # Anchor session lookup to the earliest start date among the high-pressure buckets
        # (so a 5h-only lockout stays tightly scoped to 5h, while a weekly lockout covers the full week).
        anchor_buckets = high_pressure_buckets if high_pressure_buckets else calibrated_buckets
        target_dates = [
            b["window_start_local"][:10]
            for b in anchor_buckets
            if b["window_start_local"] != "unknown"
        ]
        sess_since = min(target_dates) if target_dates else now.strftime("%Y-%m-%d")
        if fixture is not None:
            raw_sessions = (
                (fixture.get("sessions_by_date") or {}).get(sess_since)
                or (fixture.get("sessions") or {}).get("entries", [])
            )
        else:
            s_json, s_notices = run_json_cmd(
                [
                    "tokscale",
                    "models",
                    "-c",
                    "antigravity-cli",
                    "--since",
                    sess_since,
                    "--group-by",
                    "session,model",
                    "--json",
                    "--no-spinner",
                ],
                "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
                timeout=timeout,
            )
            raw_sessions = s_json.get("entries", [])
            for n in s_notices:
                if n not in top_warnings:
                    top_warnings.append(n)
        session_attribution = summarize_top_sessions(
            raw_sessions,
            limit=effective_top_n,
            model_classifier=classify_antigravity_model,
            target_groups=high_pressure_groups or None,
        )

    return {
        "provider": "antigravity",
        "observed_at_local": now.isoformat(timespec="seconds"),
        "samples_taken": len(raw_samples),
        "provider_rule_description": cmd_data.get("description", ""),
        "weekly_to_5h_multipliers": multipliers,
        "weekly_to_5h_multipliers_clamped": clamped_multipliers,
        "buckets": calibrated_buckets,
        "switch_recommendations": switch_recommendations,
        "top_sessions_since": sess_since if session_attribution else None,
        "top_sessions": session_attribution,
        "notes": info_notes,
        "warnings": top_warnings,
    }


# Pricing rates ($/token) for turn-level TTL cold-resend attribution when local transcripts exist.
_TURN_RATE_MAP: list[tuple[str, tuple[float, float, float]]] = [
    ("claude-opus-5-5", (4.0e-6, 0.2e-6, 20.0e-6)),
    ("claude-sonnet-5-5", (3.0e-6, 0.3e-6, 15.0e-6)),
    ("claude-opus-4-6", (5.0e-6, 0.5e-6, 25.0e-6)),
    ("claude-sonnet-4-6", (3.0e-6, 0.3e-6, 15.0e-6)),
]


def _turn_rates(model: str) -> tuple[float, float, float]:
    low = model.lower()
    for prefix, rates in _TURN_RATE_MAP:
        if low.startswith(prefix):
            return rates
    return (4.0e-6, 0.2e-6, 20.0e-6)


def analyze_antigravity_turn_forensics(
    result: dict[str, Any],
    brain_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Inspect local Antigravity transcripts strictly for top_sessions IDs (zero full-dir scan).

    Separates primary session normal burn vs 5m Prompt Cache TTL cold-resend waste vs concurrent
    subagent overlap to compute lossless zero-compression savings (never recommending <250k compact).
    """
    top_sessions: list[dict[str, Any]] = result.get("top_sessions") or []
    if not top_sessions:
        return None
    base_dir = brain_dir if brain_dir is not None else (Path.home() / ".gemini" / "antigravity-cli" / "brain")
    if not base_dir.is_dir():
        return None

    # Focus on the highest-pressure group (locked / >=80% used), else the top session's group
    buckets = result.get("buckets") or []
    target_bucket = next(
        (b for b in buckets if b.get("window") == "5h" and b.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT")),
        None,
    ) or next(
        (b for b in buckets if b.get("used_pct", 0.0) >= AUTO_SESSIONS_USED_THRESHOLD),
        None,
    )
    target_group = target_bucket["group_key"] if target_bucket else top_sessions[0]["group_key"]
    group_sessions = [s for s in top_sessions if s.get("group_key") == target_group]
    if not group_sessions:
        return None

    tz = local_tz()
    win_start_dt: dt.datetime | None = None
    if target_bucket and target_bucket.get("window_start_local") not in (None, "unknown"):
        try:
            win_start_dt = parse_iso_datetime(str(target_bucket["window_start_local"]), tz) - dt.timedelta(minutes=5)
        except ValueError:
            win_start_dt = None

    # Deduplicate by session_id because `tokscale --group-by session,model` can emit multiple rows per session.
    sessions_by_id: dict[str, dict[str, Any]] = {}
    for s in group_sessions:
        sid = str(s.get("session_id") or "")
        if not sid or sid == "unknown":
            continue
        prev = sessions_by_id.get(sid)
        cost = float(s.get("cost_usd") or 0.0)
        msgs = int(s.get("message_count") or 0)
        if prev is None:
            sessions_by_id[sid] = {
                "session_id": sid,
                "model": str(s.get("model") or ""),
                "cost_usd": cost,
                "message_count": msgs,
                "avg_context_k": s.get("avg_context_k"),
            }
        else:
            prev["cost_usd"] += cost
            prev["message_count"] += msgs
            if s.get("avg_context_k") is not None and (
                prev["avg_context_k"] is None or float(s["avg_context_k"]) > float(prev["avg_context_k"])
            ):
                prev["avg_context_k"] = s.get("avg_context_k")

    if not sessions_by_id:
        return None
    dedup_sessions = sorted(sessions_by_id.values(), key=lambda x: x["cost_usd"], reverse=True)

    spans: dict[str, dict[str, Any]] = {}
    ttl_events_by_sid: dict[str, list[dict[str, Any]]] = {}

    for s in dedup_sessions:
        sid = s["session_id"]
        t_path = base_dir / sid / ".system_generated" / "logs" / "transcript.jsonl"
        if not t_path.is_file():
            continue

        s_turns = 0
        peak_ctx = 0
        first_ts: dt.datetime | None = None
        last_ts: dt.datetime | None = None
        sid_ttl_events: list[dict[str, Any]] = []
        try:
            with t_path.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    if '"PLANNER_RESPONSE"' not in raw_line:
                        continue
                    try:
                        obj = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict) or obj.get("type") != "PLANNER_RESPONSE":
                        continue
                    model = str(obj.get("model") or s.get("model") or "")
                    if classify_antigravity_model(model) != target_group:
                        continue
                    ts_raw = obj.get("created_at")
                    ts_dt: dt.datetime | None = None
                    if ts_raw:
                        try:
                            ts_dt = parse_iso_datetime(str(ts_raw), tz)
                        except ValueError:
                            ts_dt = None
                    if win_start_dt is not None and ts_dt is not None and ts_dt < win_start_dt:
                        continue

                    inp = int(obj.get("input_tokens") or 0)
                    cr = int(obj.get("cache_read_tokens") or 0)
                    out = int(obj.get("output_tokens") or 0)
                    if inp == 0 and cr == 0 and out == 0:
                        continue
                    s_turns += 1
                    ctx = inp + cr
                    if ctx > peak_ctx:
                        peak_ctx = ctx
                    if ts_dt is not None:
                        if first_ts is None or ts_dt < first_ts:
                            first_ts = ts_dt
                        if last_ts is None or ts_dt > last_ts:
                            last_ts = ts_dt

                    # Prompt Cache 5m TTL expiry cold-resend detector: turn > 1 with >=50k fresh input
                    if s_turns > 1 and inp >= 50_000:
                        r_in, r_cr, r_out = _turn_rates(model)
                        turn_cost = inp * r_in + cr * r_cr + out * r_out
                        avoidable = max(0.0, inp - 2000) * max(0.0, r_in - r_cr)
                        sid_ttl_events.append(
                            {
                                "sid": sid[:8],
                                "time": ts_dt.strftime("%H:%M:%S") if ts_dt else "unknown",
                                "input_k": round(inp / 1000.0, 1),
                                "cost_usd": round(turn_cost, 2),
                                "waste_usd": round(avoidable, 2),
                            }
                        )
        except OSError:
            continue

        if s_turns > 0:
            spans[sid] = {
                "session_id": sid,
                "short_id": sid[:8],
                "turns": s_turns,
                "peak_context_k": round(peak_ctx / 1000.0, 1),
                "first_ts": first_ts,
                "last_ts": last_ts,
            }
            if sid_ttl_events:
                ttl_events_by_sid[sid] = sid_ttl_events

    if not spans:
        return None

    primary = next((s for s in dedup_sessions if s["session_id"] in spans), None)
    if primary is None:
        return None
    p_sid = primary["session_id"]
    p_span = spans[p_sid]

    subagent_rows: list[dict[str, Any]] = []
    subagent_sids: set[str] = set()
    sub_cost = 0.0
    for s in dedup_sessions:
        sid = s["session_id"]
        if sid == p_sid:
            continue
        sp = spans.get(sid)
        # Require verified transcript span overlapping the primary session (never classify pre-window/missing transcripts).
        if not (sp and p_span["first_ts"] and p_span["last_ts"] and sp["first_ts"] and sp["last_ts"]):
            continue
        overlaps = (
            sp["turns"] >= 2
            and sp["first_ts"] <= p_span["last_ts"]
            and sp["last_ts"] >= p_span["first_ts"]
        )
        if overlaps:
            c = float(s["cost_usd"])
            sub_cost += c
            subagent_sids.add(sid)
            subagent_rows.append(
                {
                    "session_id": sid,
                    "short_id": sid[:8],
                    "cost_usd": round(c, 2),
                    "turns": sp["turns"],
                }
            )

    # Count only non-subagent TTL cold-resend waste so offloaded subagents are never double-counted.
    ttl_events: list[dict[str, Any]] = []
    for sid, evs in ttl_events_by_sid.items():
        if sid not in subagent_sids:
            ttl_events.extend(evs)
    ttl_actual_total = sum(float(e["cost_usd"]) for e in ttl_events)
    ttl_waste_total = sum(float(e["waste_usd"]) for e in ttl_events)

    window_total = sum(float(s["cost_usd"]) for s in dedup_sessions)
    if target_bucket and target_bucket.get("spend_base_usd"):
        window_total = max(window_total, float(target_bucket["spend_base_usd"]))
    zero_save = round(min(window_total, sub_cost + ttl_waste_total), 2)
    zero_pct = round((zero_save / window_total) * 100.0, 1) if window_total > 0 else 0.0

    ttl_events.sort(key=lambda e: e["waste_usd"], reverse=True)
    return {
        "group_key": target_group,
        "window_total_usd": round(window_total, 2),
        "primary_session": {
            "session_id": p_sid,
            "short_id": p_sid[:8],
            "cost_usd": round(float(primary["cost_usd"]), 2),
            "avg_context_k": primary.get("avg_context_k"),
            "peak_context_k": p_span["peak_context_k"],
            "turns": p_span["turns"],
        },
        "concurrent_subagents": {
            "count": len(subagent_rows),
            "cost_usd": round(sub_cost, 2),
            "share_pct": round((sub_cost / window_total) * 100.0, 1) if window_total > 0 else 0.0,
            "sessions": subagent_rows,
        },
        "ttl_cold_misses": {
            "count": len(ttl_events),
            "actual_cost_usd": round(ttl_actual_total, 2),
            "avoidable_waste_usd": round(ttl_waste_total, 2),
            "events": ttl_events,
        },
        "zero_compression_savings_usd": zero_save,
        "zero_compression_savings_pct": zero_pct,
    }


def fetch_codex_standby_accounts(
    timeout: float = DEFAULT_CMD_TIMEOUT,
    fixture: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch all local Codex accounts via `tokscale usage --json` as standby pool context."""
    tz = local_tz()
    warnings: list[str] = []
    if fixture is not None:
        raw_candidate = fixture.get("codex_usage")
        if raw_candidate is None and isinstance(fixture.get("usage"), list):
            raw_candidate = fixture.get("usage")
        raw_list = raw_candidate if isinstance(raw_candidate, list) else []
    else:
        try:
            raw_list, notices = run_json_cmd(
                ["tokscale", "usage", "--json"],
                "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
                timeout=timeout,
            )
            warnings.extend(notices)
            if not isinstance(raw_list, list):
                raw_list = []
        except CalibrationError as exc:
            return [], [f"CODEX_STANDBY_UNAVAILABLE: {exc}"]

    out: list[dict[str, Any]] = []
    for u in raw_list:
        if not isinstance(u, dict) or str(u.get("provider") or "").lower() != "codex":
            continue
        metrics = [m for m in (u.get("metrics") or []) if isinstance(m, dict)]
        # Select the most constrained window so a locked weekly quota is not masked by an open 5h window.
        m = max(metrics, key=lambda item: float(item.get("used_percent") or 0.0)) if metrics else {}
        reset_raw = str(m.get("resets_at") or "")
        reset_short = "—"
        if reset_raw:
            try:
                reset_short = parse_iso_datetime(reset_raw, tz).strftime("%m-%d %H:%M")
            except ValueError:
                reset_short = reset_raw
        bal = float((u.get("credit_status") or {}).get("balance") or 0.0)
        out.append(
            {
                "email": str(u.get("email") or "unknown"),
                "plan": str(u.get("plan") or "Unknown"),
                "is_active": bool((u.get("account") or {}).get("is_active")),
                "window": str(m.get("label") or "unknown"),
                "used_pct": round(float(m.get("used_percent") or 0.0), 1),
                "reset_local_short": reset_short,
                "credit_usd": round(bal, 2),
            }
        )
    return out, warnings


def _fmt_pct_plain(val: float | None) -> str:
    return f"{val:.1f}%" if val is not None else "—"


def build_business_summary(
    result: dict[str, Any],
    plan_usd: float | None = None,
    codex_accounts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate live business decision summary (pool independence, waste risk, ROI, dynamic routing)."""
    buckets = result.get("buckets") or []
    forensics = result.get("window_forensics")
    codex_accounts = codex_accounts or []

    g_w = next((b for b in buckets if b.get("group_key") == "gemini" and b.get("window") == "weekly"), None)
    g_5 = next((b for b in buckets if b.get("group_key") == "gemini" and b.get("window") == "5h"), None)
    p_w = next((b for b in buckets if b.get("group_key") == "3p" and b.get("window") == "weekly"), None)
    p_5 = next((b for b in buckets if b.get("group_key") == "3p" and b.get("window") == "5h"), None)

    open_codex = [c for c in codex_accounts if float(c.get("used_pct") or 0.0) < 99.9]
    codex_hint = (
        f"；同机另有 {len(open_codex)} 个空载 Codex 备用号" if open_codex else ""
    )

    if result.get("provider") == "antigravity" and (g_w or g_5 or p_w or p_5):
        p5_locked = bool(p_5 and p_5.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT"))
        pw_locked = bool(p_w and p_w.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT"))
        g5_locked = bool(g_5 and g_5.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT"))
        gw_locked = bool(g_w and g_w.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT"))
        opus_locked = p5_locked or pw_locked
        gemini_locked = g5_locked or gw_locked

        # Binding lockout bucket per group (weekly overrides 5h when both locked)
        opus_lock_b = p_w if pw_locked else (p_5 if p5_locked else None)
        gemini_lock_b = g_w if gw_locked else (g_5 if g5_locked else None)

        p_lock_ttr = opus_lock_b.get("time_to_reset") if opus_lock_b else "—"
        p_lock_at = (opus_lock_b.get("reset_time_local") or "")[11:19] if opus_lock_b else "—"
        g_lock_ttr = gemini_lock_b.get("time_to_reset") if gemini_lock_b else "—"

        gw_rem_usd = g_w.get("remaining_usd_base") if g_w else None
        gw_rem_pct = round(g_w["remaining_fraction"] * 100.0, 1) if g_w else None
        g5_rem_pct = round(g_5["remaining_fraction"] * 100.0, 1) if g_5 else None
        pw_rem_usd = p_w.get("remaining_usd_base") if p_w else None
        pw_rem_pct = round(p_w["remaining_fraction"] * 100.0, 1) if p_w else None
        p5_rem_pct = round(p_5["remaining_fraction"] * 100.0, 1) if p_5 else None
        p5_rem_usd = p_5.get("remaining_usd_base") if p_5 else None
        pw_ttr_sec = p_w.get("time_to_reset_seconds") if p_w else None
        pw_ttr = p_w.get("time_to_reset") if p_w else "—"

        gw_cap = g_w.get("implied_pool_base_usd") if g_w else None
        pw_cap = p_w.get("implied_pool_base_usd") if p_w else None
        ratio_str = (
            f"约为 Opus 周池的 {gw_cap / pw_cap:.0f}×"
            if (gw_cap and pw_cap and pw_cap > 0)
            else "远大于 Opus 独立池"
        )

        # Headline + subline handle ALL 4 real lock states cleanly!
        if opus_locked and gemini_locked:
            headline = f"Antigravity 双池当前均已锁死（Opus 距解锁 {p_lock_ttr} / Gemini 距解锁 {g_lock_ttr}）"
            subline = (
                f"当前订阅内 Gemini 与 Claude/GPT 均已触达限流，建议先切同机备用账号或等待最快重置窗口{codex_hint}。"
            )
        elif opus_locked:
            lock_scope = "Opus 周池" if pw_locked else "Opus 5h"
            headline = f"{lock_scope} 当前锁死（{p_lock_ttr} 后于 {p_lock_at} 解锁），立刻切 Gemini 池无阻塞干活"
            subline = (
                f"Gemini 与 Claude/GPT 为两套完全独立配额池：Gemini 5h 池余 {_fmt_pct_plain(g5_rem_pct)} / 周池余 "
                f"{_fmt_usd_plain(gw_rem_usd)}（{_fmt_pct_plain(gw_rem_pct)}），Opus 周池尚余 {_fmt_usd_plain(pw_rem_usd)}（{_fmt_pct_plain(pw_rem_pct)}）{codex_hint}。"
            )
        elif gemini_locked:
            lock_scope = "Gemini 周池" if gw_locked else "Gemini 5h"
            headline = f"{lock_scope} 当前锁死（{g_lock_ttr} 后解锁），可暂切 Opus 池承接高优任务"
            subline = (
                f"Gemini 与 Claude/GPT 为两套独立配额池：Opus 5h 余 {_fmt_pct_plain(p5_rem_pct)} / 周池余 "
                f"{_fmt_usd_plain(pw_rem_usd)}（{_fmt_pct_plain(pw_rem_pct)}），注意严控并发子代理以防耗尽 Opus 池{codex_hint}。"
            )
        else:
            headline = f"双池均可用：Opus 5h 余 {_fmt_pct_plain(p5_rem_pct)}（{_fmt_usd_plain(p5_rem_usd)}），Gemini 周池余 {_fmt_usd_plain(gw_rem_usd)}"
            subline = (
                f"Gemini 与 Claude/GPT 为两套独立配额池：Opus 5h 可随时用于单主会话核心架构决策，"
                f"并发子代理与长上下文重构仍优先走 Gemini 池以防提前撞墙{codex_hint}。"
            )

        if not gemini_locked:
            primary_open = {
                "headline": f"Gemini 5h 余 {_fmt_pct_plain(g5_rem_pct)}",
                "detail": (
                    f"周池尚余 {_fmt_usd_plain(gw_rem_usd)}（{_fmt_pct_plain(gw_rem_pct)} · 重置 {g_w.get('time_to_reset') or '—'}）"
                    if g_w else "同订阅独立主池"
                ),
            }
        elif not opus_locked:
            primary_open = {
                "headline": f"Opus 5h 余 {_fmt_pct_plain(p5_rem_pct)}",
                "detail": f"Gemini 锁死（{g_lock_ttr} 后解锁），Opus 周池余 {_fmt_usd_plain(pw_rem_usd)}",
            }
        else:
            primary_open = {
                "headline": f"Codex 备用 {len(open_codex)} 号" if open_codex else "双池等待解锁",
                "detail": f"Gemini {g_lock_ttr} / Opus {p_lock_ttr} 后解锁",
            }

        watched = {
            "label": "Opus 池状态",
            "value": (
                f"{'周池' if pw_locked else ''}锁死 · {p_lock_ttr} 解锁"
                if opus_locked
                else f"可用 · 余 {_fmt_pct_plain(p5_rem_pct)}"
            ),
            "detail": (
                f"解锁时间 {p_lock_at} · 周池尚余 {_fmt_usd_plain(pw_rem_usd)}（{_fmt_pct_plain(pw_rem_pct)}）"
                if opus_locked
                else f"周池尚余 {_fmt_usd_plain(pw_rem_usd)}（{_fmt_pct_plain(pw_rem_pct)} · 重置 {pw_ttr}）"
            ),
            "is_locked": opus_locked,
        }

        # Explicit "不用 Opus 亏不亏？" answer
        days_left = (pw_ttr_sec / 86400.0) if isinstance(pw_ttr_sec, (int, float)) else None
        if pw_locked:
            waste_status = "ON_TRACK"
            waste_head = "本周 Opus 已用满"
            waste_detail = f"专属 Opus 周池已 100% 消化完毕（零浪费），将在 {pw_ttr} 后刷新下一周额度。"
        elif pw_rem_pct is not None and days_left is not None and days_left <= 2.0 and pw_rem_pct >= 40.0:
            waste_status = "HIGH_WASTE_RISK"
            waste_head = f"建议尽快用掉 {_fmt_usd_plain(pw_rem_usd)}"
            waste_detail = f"双池独立！距 Opus 周重置仅剩 {pw_ttr} 但还剩 {_fmt_pct_plain(pw_rem_pct)} 专属额度，不用就作废。"
        elif pw_rem_pct is not None:
            waste_status = "ON_TRACK"
            waste_head = f"独立池 · 周余 {_fmt_usd_plain(pw_rem_usd)}"
            waste_detail = (
                f"不用 Opus 确实浪费专属周池（~{_fmt_usd_plain(pw_cap)}/周），"
                f"但当前已用 {100.0 - pw_rem_pct:.1f}% 且距周重置还有 {pw_ttr}，按需花在核心主任务即可。"
            )
        else:
            waste_status = "ON_TRACK"
            waste_head = "Gemini / Opus 独立计费"
            waste_detail = "两套池子互不挤占，无需为了省 Gemini 而不用 Opus。"

        weekly_spend = sum(
            float(b.get("spend_base_usd") or 0.0)
            for b in buckets
            if b.get("window") == "weekly" and b.get("spend_base_usd") is not None
        )
        roi_mult = round(weekly_spend / plan_usd, 2) if (plan_usd and plan_usd > 0 and weekly_spend > 0) else None
        plan_roi = {
            "weekly_spend_usd": round(weekly_spend, 2),
            "plan_usd": plan_usd,
            "roi_multiple": roi_mult,
            "detail": (
                f"当前周窗已消耗 ${weekly_spend:,.2f} 等效 API（相对 ${plan_usd:.0f}/月订阅已回本 {roi_mult:.1f}×）"
                if roi_mult is not None
                else f"当前周窗实测消耗 ${weekly_spend:,.2f} 等效 API（传入 --plan-usd 可自动算月费回本倍数）"
            ),
        }

        sub_save_str = (
            f"本窗并发子代理实耗 ${forensics['concurrent_subagents']['cost_usd']:.2f}（{forensics['concurrent_subagents']['share_pct']}%）"
            if forensics and forensics["concurrent_subagents"]["count"] > 0
            else "Opus 5h 仅约周池一半体量，并发多 Agent 极易打穿"
        )
        ttl_save_str = (
            f"本窗 5m 缓存过期冷重传损耗 ${forensics['ttl_cold_misses']['avoidable_waste_usd']:.2f}（{forensics['ttl_cold_misses']['count']} 次）"
            if forensics and forensics["ttl_cold_misses"]["count"] > 0
            else "250k+ 长上下文静置超 5 分钟会触发 20× 全价重传"
        )

        gemini_chan = (
            f"Gemini 锁死（{g_lock_ttr} 后解锁）" + (" · 暂切 Codex 备用号" if open_codex else " · 暂切备用通道")
            if gemini_locked else "Gemini 5h / 周池"
        )
        gemini_tone = "warn" if gemini_locked else "safe"
        deep_chan = (
            ("Codex 备用号 / 等待最快解锁" if open_codex else f"等待最快解锁（Opus {p_lock_ttr} / Gemini {g_lock_ttr}）")
            if (opus_locked and gemini_locked)
            else (f"先用 Gemini · {p_lock_at} 解锁后切 Opus" if opus_locked else "直接使用 Opus 5.5（单主会话）")
        )
        deep_tone = "warn" if opus_locked else "safe"

        live_routing = [
            {
                "workload": "长上下文代码重构 / 持续多文件读写",
                "pattern": ">250k 上下文持续工作",
                "channel": gemini_chan,
                "tone": gemini_tone,
                "reason": (
                    f"Gemini 当前锁死（{g_lock_ttr} 后解锁）。"
                    if gemini_locked else
                    f"Gemini 5h 池余 {_fmt_pct_plain(g5_rem_pct)} / 周池余 {_fmt_usd_plain(gw_rem_usd)}，体量{ratio_str}。"
                ),
                "rule": f"无需为了省钱把主会话压到 <250k；若用 Opus 跑长会话，严避 >5 分钟静置冷重传（{ttl_save_str}）。",
            },
            {
                "workload": "并发多子代理 / 批量审计与改造",
                "pattern": "2+ 并行 Subagent",
                "channel": gemini_chan if gemini_locked else "Gemini 池（禁止并开 Opus 子代理）",
                "tone": gemini_tone,
                "reason": f"{sub_save_str}。",
                "rule": "主会话可以按需用 Opus，但所有并发子代理统一分流到 Gemini，主会话零压缩即可大幅延长存活时间。",
            },
            {
                "workload": "高难架构决策 / 单主会话深度推理",
                "pattern": "单主会话、高决策密度",
                "channel": deep_chan,
                "tone": deep_tone,
                "reason": (
                    f"{'Opus 周池已耗尽' if pw_locked else f'Opus 5h 距解锁仅剩 {p_lock_ttr}'}，周池余 {_fmt_usd_plain(pw_rem_usd)}（{_fmt_pct_plain(pw_rem_pct)}）。"
                    if opus_locked else
                    f"Opus 5h 当前可用，周池尚余 {_fmt_usd_plain(pw_rem_usd)}（{_fmt_pct_plain(pw_rem_pct)}），正是消化专属 Opus 额度的最佳场景。"
                ),
                "rule": "保持单主会话连续对话，离座 >5 分钟前先收尾或切换，避免 250k+ 上下文冷重传。",
            },
            {
                "workload": "日常检索 / 问答 / 快速定位",
                "pattern": "短对话、高频触发",
                "channel": (
                    "Codex 备用号" if (gemini_locked and open_codex)
                    else ("Opus 5h（暂代）" if (gemini_locked and not opus_locked) else "Gemini 5h 池" + (" / Codex 备用号" if open_codex else ""))
                ),
                "tone": "warn" if (gemini_locked and not open_codex) else "safe",
                "reason": (
                    f"Gemini 锁死（{g_lock_ttr} 后解锁），先用可用备用池承接短查询。"
                    if gemini_locked else
                    f"Gemini 5h 余 {_fmt_pct_plain(g5_rem_pct)}，把稀缺的 Opus 周池完整留给高难主任务。"
                ),
                "rule": "独立短任务新开会话，不携带无关历史上下文。",
            },
        ]

        return {
            "headline": headline,
            "subline": subline,
            "primary_open_pool": primary_open,
            "watched_pool": watched,
            "waste_risk": {"status": waste_status, "headline": waste_head, "detail": waste_detail},
            "plan_roi": plan_roi,
            "live_routing": live_routing,
        }

    # Generic fallback for codex / custom providers
    locked = [b for b in buckets if b.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT")]
    headline = (
        f"{result.get('provider')} 存在 {len(locked)} 个锁死窗口"
        if locked else f"{result.get('provider')} 当前所有配额窗口均可用"
    )
    return {
        "headline": headline,
        "subline": f"观测时间：{result.get('observed_at_local')}",
        "live_routing": [],
    }


def _fmt_usd_plain(val: float | None) -> str:
    if val is None:
        return "待校准"
    if val >= 100:
        return f"${val:,.0f}"
    return f"${val:,.2f}"


def calibrate_codex(
    account_email: str | None = None,
    fixture: dict[str, Any] | None = None,
    timeout: float = DEFAULT_CMD_TIMEOUT,
    top_sessions: int | None = None,
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
        dur = parse_window_duration(label)
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
        rem_frac = round(1.0 - used_frac, 6)
        lockout_state = determine_lockout_state(rem_frac, "codex")

        if pm["win_start"] is None or pm["reset_local"] is None:
            runway = compute_runway_metrics(
                now=now,
                window_start=None,
                reset_local=pm["reset_local"],
                remaining_fraction=rem_frac,
                lockout_state=lockout_state,
                spend_base=None,
                implied_base=None,
                implied_upper=None,
                window_msgs=0,
            )
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
                    "remaining_fraction": rem_frac,
                    "used_pct": round(pm["used_pct"], 4),
                    "lockout_state": lockout_state,
                    "spend_base_usd": None,
                    "spend_min_usd": None,
                    "spend_upper_usd": None,
                    "message_count_since_date": 0,
                    "window_message_count": 0,
                    "alignment_method": "unknown_window_duration",
                    "implied_pool_base_usd": None,
                    "implied_pool_min_usd": None,
                    "implied_pool_upper_usd": None,
                    "confidence": "UNKNOWN_WINDOW",
                    **runway,
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
            signed_delta=0.0,
            mixed_ambiguity=False,
            multi_account=multi_account,
            lockout_state=lockout_state,
        )
        implied = (spend / used_frac) if used_frac > 0 else None
        runway = compute_runway_metrics(
            now=now,
            window_start=pm["win_start"],
            reset_local=pm["reset_local"],
            remaining_fraction=rem_frac,
            lockout_state=lockout_state,
            spend_base=spend,
            implied_base=implied,
            implied_upper=implied,
            window_msgs=msgs,
        )
        buckets.append(
            {
                "group_name": f"Codex ({selected.get('plan', 'Unknown')})",
                "group_key": "codex",
                "bucket_id": f"codex-{pm['label'].lower()}",
                "window": pm["label"].lower(),
                "window_start_local": pm["win_start"].isoformat(timespec="seconds"),
                "reset_time_local": pm["reset_local"].isoformat(timespec="seconds"),
                "remaining_fraction": rem_frac,
                "used_pct": round(pm["used_pct"], 4),
                "lockout_state": lockout_state,
                "spend_base_usd": round(spend, 4),
                "spend_min_usd": round(spend, 4),
                "spend_upper_usd": round(spend, 4),
                "message_count_since_date": msgs,
                "window_message_count": msgs,
                "alignment_method": "codex_hourly_window",
                "implied_pool_base_usd": round(implied, 2) if implied is not None else None,
                "implied_pool_min_usd": round(implied, 2) if implied is not None else None,
                "implied_pool_upper_usd": round(implied, 2) if implied is not None else None,
                "confidence": conf,
                **runway,
                "warnings": reasons,
            }
        )

    session_attribution: list[dict[str, Any]] = []
    high_pressure_buckets = [
        b
        for b in buckets
        if b["used_pct"] >= AUTO_SESSIONS_USED_THRESHOLD or b["lockout_state"] != "OPEN"
    ]
    effective_top_n = (
        top_sessions
        if top_sessions is not None
        else (DEFAULT_TOP_SESSIONS if high_pressure_buckets else 0)
    )
    sess_since: str | None = None
    if effective_top_n > 0 and earliest_date is not None:
        anchor_buckets = high_pressure_buckets if high_pressure_buckets else buckets
        valid_dates = [b["window_start_local"][:10] for b in anchor_buckets if b["window_start_local"] != "unknown"]
        sess_since = min(valid_dates) if valid_dates else earliest_date
        if fixture is not None:
            raw_sessions = (
                (fixture.get("sessions_by_date") or {}).get(sess_since)
                or (fixture.get("sessions") or {}).get("entries", [])
            )
        else:
            s_json, s_notices = run_json_cmd(
                [
                    "tokscale",
                    "models",
                    "-c",
                    "codex",
                    "--since",
                    sess_since,
                    "--group-by",
                    "session,model",
                    "--json",
                    "--no-spinner",
                ],
                "Install tokscale (`bun install -g tokscale` or `npm install -g tokscale`).",
                timeout=timeout,
            )
            raw_sessions = s_json.get("entries", [])
            for n in s_notices:
                if n not in top_warnings:
                    top_warnings.append(n)
        session_attribution = summarize_top_sessions(raw_sessions, limit=effective_top_n)

    return {
        "provider": "codex",
        "observed_at_local": now.isoformat(timespec="seconds"),
        "plan": selected.get("plan"),
        "multi_account_count": len(codex_accounts),
        "buckets": buckets,
        "top_sessions_since": sess_since if session_attribution else None,
        "top_sessions": session_attribution,
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

    rem_frac = round(1.0 - used_frac, 6)
    lockout_state = determine_lockout_state(rem_frac, "custom")
    conf, reasons = grade_confidence(
        used_fraction=used_frac,
        signed_delta=0.0,
        mixed_ambiguity=False,
        lockout_state=lockout_state,
    )
    implied_base = (spend_base / used_frac) if used_frac > 0 else None
    implied_upper = (spend_upper / used_frac) if used_frac > 0 else None
    runway = compute_runway_metrics(
        now=now,
        window_start=None,
        reset_local=None,
        remaining_fraction=rem_frac,
        lockout_state=lockout_state,
        spend_base=spend_base,
        implied_base=implied_base,
        implied_upper=implied_upper,
        window_msgs=msgs,
    )

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
                "remaining_fraction": rem_frac,
                "used_pct": round(used_frac * 100.0, 4),
                "lockout_state": lockout_state,
                "spend_base_usd": round(spend_base, 4),
                "spend_min_usd": round(spend_base, 4),
                "spend_upper_usd": round(spend_upper, 4),
                "message_count_since_date": msgs,
                "window_message_count": msgs,
                "alignment_method": method,
                "implied_pool_base_usd": round(implied_base, 2) if implied_base is not None else None,
                "implied_pool_min_usd": round(implied_base, 2) if implied_base is not None else None,
                "implied_pool_upper_usd": round(implied_upper, 2) if implied_upper is not None else None,
                "confidence": conf,
                **runway,
                "warnings": reasons,
            }
        ],
        "top_sessions": [],
        "warnings": top_warnings,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"### AI Quota Calibration ({result['provider']})",
        f"- Observed at: `{result['observed_at_local']}`",
    ]
    if result.get("weekly_to_5h_multipliers"):
        clamped_map = result.get("weekly_to_5h_multipliers_clamped") or {}
        mult_parts = []
        for k, v in result["weekly_to_5h_multipliers"].items():
            if v is None:
                continue
            if clamped_map.get(k):
                mult_parts.append(f"`{k}` = **>={v:.2f}x** *(5h clamped)*")
            else:
                mult_parts.append(f"`{k}` = **{v:.2f}x**")
        if mult_parts:
            lines.append("- Weekly / 5h multiplier: " + ", ".join(mult_parts))
    lines.append("")
    lines.append(
        "| Pool | Window | Resets In | Local Spend (Min/Base ~ CW Upper) | Quota Used | Implied Pool ($ API eq.) | Remaining Runway | Confidence |"
    )
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :---: |")

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
            if b.get("boundary_hour_overcount"):
                pool_str = "N/A (mid-hour reset)"
            elif b["confidence"] == "UNKNOWN_WINDOW":
                pool_str = "N/A (unknown window)"
            else:
                pool_str = "N/A (untouched)"
        elif p_upper is not None and abs(p_upper - p_low) > 0.5:
            pool_str = f"**${p_low:.0f} ~ ${p_upper:.0f}**"
        else:
            pool_str = f"**${p_low:.0f}**"

        ttr = b.get("time_to_reset") or "—"
        state = b.get("lockout_state", "OPEN")
        used_str = f"{b['used_pct']:.2f}%"
        if state == "LOCKED":
            used_str += " (`LOCKED`)"
        elif state == "SOFT_LOCKOUT":
            used_str += " (`SOFT_LOCKOUT`)"

        if state in ("LOCKED", "SOFT_LOCKOUT"):
            runway_str = f"$0 (resets in {ttr})"
        elif b.get("remaining_usd_base") is not None:
            parts = [f"~${b['remaining_usd_base']:.0f}"]
            if b.get("estimated_remaining_msgs") is not None:
                parts.append(f"~{b['estimated_remaining_msgs']} msgs")
            if b.get("eta_to_exhaustion"):
                parts.append(f"ETA {b['eta_to_exhaustion']}")
            runway_str = " / ".join(parts)
        else:
            runway_str = "—"

        lines.append(
            f"| {b['group_name']} (`{b['bucket_id']}`) | {b['window']} | {ttr} | "
            f"{spend_str} | {used_str} | {pool_str} | {runway_str} | `{b['confidence']}` |"
        )

    if result.get("switch_recommendations"):
        lines.append("")
        lines.append("#### Lockout & Alternate Pool Recommendations")
        for rec in result["switch_recommendations"]:
            alt_strs = []
            for a in rec["available_alternatives"]:
                win_parts = []
                if a.get("remaining_5h_pct") is not None:
                    p5 = f"{a['remaining_5h_pct']}% 5h"
                    if a.get("remaining_5h_usd") is not None:
                        p5 += f" / ~${a['remaining_5h_usd']:.0f}"
                    win_parts.append(p5)
                if a.get("remaining_weekly_pct") is not None:
                    win_parts.append(f"{a['remaining_weekly_pct']}% weekly")
                detail = f" ({', '.join(win_parts)})" if win_parts else ""
                alt_strs.append(f"**{a['group_name']}**{detail}")
            alts = ", ".join(alt_strs)
            lines.append(
                f"- **{rec['locked_group']}** (`{rec['locked_bucket']}`) is `{rec['lockout_state']}` "
                f"(resets in `{rec['resets_in']}` at `{rec['reset_time_local']}`). "
                f"Available now in the same subscription: {alts}."
            )

    if result.get("top_sessions"):
        lines.append("")
        since_tag = (
            f" (since `{result['top_sessions_since']}`)"
            if result.get("top_sessions_since")
            else ""
        )
        lines.append(f"#### Top Burning Sessions{since_tag}")
        lines.append("| Session | Group | Model | Msgs | Avg Ctx | Spend | $/Msg | Cache Read | Share | Flag |")
        lines.append("| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for s in result["top_sessions"]:
            flag = "`CONTEXT_SNOWBALL`" if s["context_snowball"] else "—"
            ctx_str = f"{s['avg_context_k']:.1f}k" if s.get("avg_context_k") is not None else "—"
            lines.append(
                f"| `{s['session_id'][:8]}` | `{s['group_key']}` | `{s['model']}` | {s['message_count']} | "
                f"{ctx_str} | ${s['cost_usd']:.2f} | ${s['avg_cost_per_msg_usd']:.3f} | "
                f"{s['cache_read_pct']:.1f}% | {s['share_of_group_spend_pct']:.1f}% | {flag} |"
            )

    forensics = result.get("window_forensics")
    if forensics:
        prim = forensics["primary_session"]
        sub = forensics["concurrent_subagents"]
        ttl = forensics["ttl_cold_misses"]
        lines.append("")
        lines.append("#### Window Loss Attribution & Zero-Compression Savings")
        lines.append(
            f"- Primary session `{prim['short_id']}`: `${prim['cost_usd']:.2f}` "
            f"(avg `{prim.get('avg_context_k')}k` / peak `{prim['peak_context_k']}k` context, `{prim['turns']}` turns)."
        )
        lines.append(
            f"- Concurrent subagents (`{sub['count']}`): `${sub['cost_usd']:.2f}` (`{sub['share_pct']}%` of window spend)."
        )
        lines.append(
            f"- 5m Prompt Cache TTL cold resends (`{ttl['count']}` turns >=50k fresh input): "
            f"`${ttl['avoidable_waste_usd']:.2f}` avoidable 20x waste (actual `${ttl['actual_cost_usd']:.2f}`)."
        )
        lines.append(
            f"- **Zero-compression lossless savings**: `${forensics['zero_compression_savings_usd']:.2f}` "
            f"(`{forensics['zero_compression_savings_pct']:.1f}%`) by offloading subagents + avoiding >5m cold resends (no `<250k` compact)."
        )

    bsum = result.get("business_summary")
    if bsum and bsum.get("headline"):
        lines.append("")
        lines.append("#### Business Summary")
        lines.append(f"- **Verdict**: {bsum['headline']}")
        if bsum.get("waste_risk"):
            lines.append(f"- **Pool independence & waste check**: {bsum['waste_risk']['headline']} — {bsum['waste_risk']['detail']}")
        if bsum.get("plan_roi"):
            lines.append(f"- **Weekly API spend / ROI**: {bsum['plan_roi']['detail']}")

    if result.get("notes"):
        lines.append("")
        lines.append("#### Concurrent Activity Notes")
        for n in result["notes"]:
            lines.append(f"- {n}")

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
        "--top-sessions",
        type=int,
        default=None,
        help="Include top N burning sessions (default: auto=5 when any bucket >= 80%% or locked; 0 to disable).",
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
    p.add_argument(
        "--plan-usd",
        type=float,
        default=None,
        help="Optional monthly subscription price in USD (e.g. 250) to compute weekly API ROI.",
    )
    p.add_argument(
        "--include-codex",
        action="store_true",
        help="For --provider antigravity, also attach live same-machine Codex standby accounts from `tokscale usage`.",
    )
    p.add_argument(
        "--brain-dir",
        type=Path,
        default=None,
        help="Optional override for local Antigravity brain transcript directory (for turn-level TTL/subagent forensics).",
    )
    p.add_argument(
        "--html",
        type=Path,
        default=None,
        help="Write a live, zero-dependency HTML business cockpit report to this path.",
    )
    p.add_argument(
        "--open",
        action="store_true",
        help="Open the generated --html report in the default browser.",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.plan_usd is not None and (not math.isfinite(args.plan_usd) or args.plan_usd <= 0):
        print(f"Error: --plan-usd must be a finite positive number (got {args.plan_usd}).", file=sys.stderr)
        return 2

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
                top_sessions=args.top_sessions,
            )
            # Attach bounded local turn-level forensics (disabled in fixture mode unless --brain-dir passed)
            if fixture is None or args.brain_dir is not None:
                forensics = analyze_antigravity_turn_forensics(result, brain_dir=args.brain_dir)
                if forensics is not None:
                    result["window_forensics"] = forensics
            codex_standby: list[dict[str, Any]] = []
            if args.include_codex or (fixture is not None and fixture.get("codex_usage")):
                codex_standby, cx_warns = fetch_codex_standby_accounts(timeout=args.timeout, fixture=fixture)
                if codex_standby:
                    result["codex_standby_accounts"] = codex_standby
                for w in cx_warns:
                    if w not in result["warnings"]:
                        result["warnings"].append(w)
            result["business_summary"] = build_business_summary(
                result, plan_usd=args.plan_usd, codex_accounts=codex_standby
            )
        elif args.provider == "codex":
            result = calibrate_codex(
                account_email=args.account_email,
                fixture=fixture,
                timeout=args.timeout,
                top_sessions=args.top_sessions,
            )
            result["business_summary"] = build_business_summary(result, plan_usd=args.plan_usd)
        else:
            result = calibrate_custom(args, timeout=args.timeout)
            result["business_summary"] = build_business_summary(result, plan_usd=args.plan_usd)
    except CalibrationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.html is not None:
        scripts_dir = Path(__file__).resolve().parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from render_report_html import render_html_report

        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_html_report(result), encoding="utf-8")
        if args.open:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            if shutil.which(opener):
                subprocess.Popen([opener, str(args.html)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
