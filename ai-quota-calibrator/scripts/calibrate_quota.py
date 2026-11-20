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

        spend_info = compute_group_window_spend(
            group_key=gk,
            window_start=spec["window_start_local"],
            models_since_entries=models_by_date.get(spec["start_date"], []),
            hourly_entries=hourly_entries,
            tz=tz,
            model_classifier=classify_antigravity_model,
            fresh_window_start=gk in fresh_start_groups,
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
            pool_str = "N/A (unknown window)" if b["confidence"] == "UNKNOWN_WINDOW" else "N/A (untouched)"
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
        lines.append("| Session | Group | Model | Msgs | Spend | $/Msg | Cache Read | Share | Flag |")
        lines.append("| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
        for s in result["top_sessions"]:
            flag = "`CONTEXT_SNOWBALL`" if s["context_snowball"] else "—"
            lines.append(
                f"| `{s['session_id'][:8]}` | `{s['group_key']}` | `{s['model']}` | {s['message_count']} | "
                f"${s['cost_usd']:.2f} | ${s['avg_cost_per_msg_usd']:.3f} | "
                f"{s['cache_read_pct']:.1f}% | {s['share_of_group_spend_pct']:.1f}% | {flag} |"
            )

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
                top_sessions=args.top_sessions,
            )
        elif args.provider == "codex":
            result = calibrate_codex(
                account_email=args.account_email,
                fixture=fixture,
                timeout=args.timeout,
                top_sessions=args.top_sessions,
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
