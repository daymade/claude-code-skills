---
name: ai-quota-calibrator
description: >-
  Calibrates black-box AI subscription quotas into equivalent API dollars and
  runway by reconciling local tokscale spend against live provider fractions
  (Antigravity Gemini/Claude pools, Codex, custom caps). Use when asked how big
  a 5h/weekly quota really is, why a pool drains fast, or 额度相当于多少钱/反推配额.
  Not for ccusage-only audits (claude-usage-analyst) or Codex reset news (tibo-reset-codex).
---

# AI Quota Calibrator

Estimate the true API-dollar capacity, weekly-to-5h multiplier, and remaining
runway of percentage-based AI subscriptions by reconciling local `tokscale`
spend against live provider quota fractions.

## Prerequisites & Readiness Check

Verify the required CLIs before running calibration; fail explicitly if missing
instead of guessing quota sizes or fabricating token prices.

```bash
command -v tokscale && tokscale --version
```

- If `tokscale` is missing, instruct the user to install it (for example via
  `bun install -g tokscale` or `npm install -g tokscale`) and stop.
- For **Antigravity** (`--provider antigravity`), also verify `agy`:
  ```bash
  command -v agy
  ```
  Antigravity quota comes from `agy -p /usage --output-format json`; local CLI
  token spend is read from `tokscale` client `antigravity-cli`.
- For **Codex** (`--provider codex`), quota comes from `tokscale usage --json`
  and local spend from `tokscale` client `codex`.
- For **any other percentage-based subscription** (`--provider custom`), use
  the provider's reported `used_percent` (or `remaining_fraction`) together with
  either a `--client <tokscale-client> --since YYYY-MM-DD` lookup or an explicit
  `--spend-usd <amount>`.

## Core Calibration Workflow

Locate this Skill's directory (`<skill-dir>`) from the loaded `SKILL.md` path and
run the bundled zero-dependency Python 3.9+ calibrator.

### 1. Antigravity (Gemini Models & Claude/GPT 3P Pools)

```bash
python3 "<skill-dir>/scripts/calibrate_quota.py" --provider antigravity
```

Pass `--json` for machine-readable output, `--samples 2 --settle-seconds 5`
(default) to detect transient in-flight reservations, or `--samples 1` when
latency matters and no other Antigravity sessions are active.

### 2. Codex (via `tokscale usage` + `tokscale hourly`)

```bash
python3 "<skill-dir>/scripts/calibrate_quota.py" --provider codex
```

### 3. Custom / Manual Provider

```bash
python3 "<skill-dir>/scripts/calibrate_quota.py" --provider custom \
  --label "My Plan (Weekly)" --used-pct 20.0 \
  --client claude --since 2026-11-14
```

Or supply spend directly when reconciling an external billing export:

```bash
python3 "<skill-dir>/scripts/calibrate_quota.py" --provider custom \
  --label "Partner Pool (5h)" --used-pct 15.0 --spend-usd 4.50 \
  --cache-write-upper-usd 5.10
```

## Calibration Discipline (Mandatory Gates)

Read [references/methodology.md](references/methodology.md) when interpreting
edge cases, mixed-model hours, multi-account bias, or adding a new provider.

1. **Never extrapolate from a single tiny cold probe (`< 2%` consumed).**
   A single low-output turn has an unrepresentative cache ratio and can sit
   inside backend reservation jitter, misestimating pool capacity by 4–5×.
   Grade buckets `< 2%` consumed as `LOW` confidence and wait for real
   multi-turn usage (`>= 5%` preferred, `>= 10%` for `HIGH` confidence).
2. **Guard against in-flight reservation and replica jitter (Antigravity).**
   Antigravity temporarily deducts a flat `0.01` (1%) while a request settles
   and can serve slightly lagged values across backend replicas. The script
   reads `agy -p /usage --output-format json` twice and compares `remaining_fraction`
   and the `used_5h / used_weekly` ratio; if readings diverge, report the
   instability warning and re-run once active sessions pause.
3. **Align spend to exact window boundaries in local time.**
   Convert UTC `reset_time` into the local timezone used by `tokscale hourly`
   to derive `window_start = reset_time - window_duration` (`7d` for weekly,
   `5h` for 5-hour). Subtract pre-window hours on the start date and prorate
   the boundary hour; surface any mixed-model boundary uncertainty as a
   bounded range instead of fabricating an exact split.
4. **Report both base spend and cache-write upper bound.**
   When local logs omit separate `cacheWrite` counters (`cacheWrite == 0`, as in
   current `antigravity-cli` records), compute:
   - **Base**: `tokscale` reported cost (standard input + cache read +
     output/reasoning).
   - **Cache-write upper bound**: price new `input` tokens at the 5-minute
     cache-write rate (e.g., `1.25×` base input for Anthropic Claude models)
     to bracket cache-creation billing.
   Note that `tokscale` maps Antigravity Claude output tokens into `reasoning`
   (`output == 0`), which is already priced at the output rate—do not
   double-count or assume output was dropped.
5. **Respect saturation and attribution limits.**
   - If `used_percent >= 99.9%` (`SATURATED`), local spend over the full window
     cannot separate pre-lockout burn from other activity unless the lockout
     time is known—mark confidence `LOW` and explain the cap.
   - Multi-machine or web/IDE usage on the **same** account makes local spend
     smaller than true spend (**underestimates** pool size).
   - Multiple accounts sharing **one** local `tokscale` client directory (e.g.,
     multi-account Codex) make local spend larger than single-account spend
     (**overestimates** single-account pool size).

## Output Format

Present the reconciled result concisely in this structure:

1. **Headline summary**: Implied API-dollar size of each active pool (base ~
   cache-write upper), exact `Weekly ÷ 5h` multiplier when both windows are
   active, and any stark asymmetry between model pools (e.g., first-party vs.
   third-party).
2. **Calibration table**: Pool | Window (`start → reset`, local TZ) | Window
   Spend (`base ~ upper`) | Quota Used (`%`) | Implied Pool Size (`$ API eq.`)
   | Confidence.
3. **Runway & practical allocation**: Translate the calibrated rate into
   turns/hours remaining at the user's observed workload intensity and suggest
   which tasks fit each pool.
4. **Warnings & limits**: Surface every script warning (instability, low
   signal, mixed-hour boundary, saturation, multi-account/multi-machine bias,
   or `tokscale` unpriced/stale-pricing notices).
