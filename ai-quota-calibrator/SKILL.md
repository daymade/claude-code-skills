---
name: ai-quota-calibrator
description: >-
  Calibrates black-box AI subscription quotas into API dollars, runway, and top
  burning sessions by reconciling tokscale spend against live provider fractions
  (Antigravity, Codex, custom caps). Use when asked how big a 5h/weekly quota is,
  why a pool hit rate limit, or 额度相当于多少钱/反推配额/谁烧光了额度. Not for
  ccusage audits (claude-usage-analyst) or Codex reset news (tibo-reset-codex).
---

# AI Quota Calibrator

Execute this Skill directly on the user's behalf—never ask the user to manually
copy-paste CLI commands when the agent can run the bundled calibrator itself.

Estimate the true API-dollar capacity, weekly-to-5h multiplier, remaining
runway, reset countdown, alternate available pools, and top burning sessions of
percentage-based AI subscriptions by reconciling local `tokscale` spend against
live provider quota fractions.

## Prerequisites & Readiness Check

Verify the required CLIs before running calibration; fail explicitly if missing
instead of guessing quota sizes or fabricating token prices.

```bash
command -v tokscale && tokscale --version
```

- If `tokscale` is missing, report the missing prerequisite (`bun install -g
  tokscale` or `npm install -g tokscale`) and stop.
- For **Antigravity** (`--provider antigravity`), also verify `command -v agy`.
  Antigravity quota comes from `agy -p /usage --output-format json`; local CLI
  spend is read from `tokscale` client `antigravity-cli`.
- For **Codex** (`--provider codex`), quota comes from `tokscale usage --json`
  and local spend from `tokscale` client `codex`.
- For **any other percentage-based subscription** (`--provider custom`), pass
  the provider's reported `--used-pct` (or `--remaining-fraction`) with either
  `--client <tokscale-client> --since YYYY-MM-DD` or `--spend-usd <amount>`.

## Core Calibration Workflow

Resolve `<skill-dir>` from this loaded `SKILL.md` path and execute the bundled
zero-dependency Python 3.9+ calibrator directly.

### 1. Antigravity (Gemini Models & Claude/GPT 3P Pools)

```bash
python3 "<skill-dir>/scripts/calibrate_quota.py" --provider antigravity \
  --include-codex --html /tmp/ai-quota-cockpit.html --open
```

- Defaults: `--samples 2 --settle-seconds 5`, `--timeout 60`, automatic top-5
  session attribution whenever any bucket is `>= 80%` used or locked, and
  bounded turn-level forensics (strictly scoped to `top_sessions` IDs) separating
  primary-session burn, concurrent subagents, and 5-minute Prompt Cache TTL
  cold-resend (`20x`) waste.
- Pass `--plan-usd <monthly_price>` (when known) to compute weekly API ROI,
  `--include-codex` to append live same-machine Codex standby accounts,
  `--html <path> [--open]` to generate and open a zero-CDN live business cockpit,
  `--top-sessions N` to override top-session count (`0` to skip), `--json` for
  structured output, or `--samples 1` only when no concurrent sessions are active.

### 2. Codex (via `tokscale usage` + `tokscale hourly`)

```bash
python3 "<skill-dir>/scripts/calibrate_quota.py" --provider codex
```

Pass `--top-sessions 5` to include top Codex sessions, or `--account-email` to
target a specific Codex account.

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
lockout caps, soft lockouts, mixed-model hours, multi-account bias, or adding a
new provider.

1. **Never extrapolate from a single tiny cold probe (`< 2%` consumed).**
   Single low-output turns sit inside reservation jitter and have skewed cache
   ratios, misestimating pool capacity by 4–5×. Grade `< 2%` buckets `LOW` and
   rely on real multi-turn usage (`>= 5%` preferred, `>= 10%` for `HIGH`).
2. **Distinguish rebound jitter from monotonic concurrent burn (Antigravity).**
   The script compares both signed `remaining_fraction` delta (`v2 - v1`) and
   the `used_5h / used_weekly` ratio across two reads:
   - **Upward rebound (`v2 > v1`)**: true `RESERVATION_REFUND_OR_REPLICA_LAG`
     — warn and downgrade confidence.
   - **Small monotonic burn (`v2 < v1`, `<= 5%` relative on `>= 20%` used)**:
     normal concurrent session activity (`CONCURRENT_BURN` info note), keeping
     `HIGH` confidence instead of false-alarm downgrades.
3. **Recognize `< 1%` soft lockout, clamped multipliers, and `LOCKOUT_CAP`.**
   - Antigravity enforces a `1%` (`0.01`) pre-reservation floor, so buckets
     with `0.1% < remaining < 1%` are already in `SOFT_LOCKOUT`.
   - When `5h` hits `LOCKED` or `SOFT_LOCKOUT`, `5h` is clamped near `0%` while
     `weekly` keeps deducting—treat the observed `u5 / uw` ratio as a lower
     bound (`>= Xx`), not an exact multiplier.
   - When a `5h` bucket hits lockout from a fresh simultaneous `5h+weekly`
     start while `weekly` remains open, local spend directly measures that 5h
     hard cap (`LOCKOUT_CAP`), distinct from unknown-timestamp `SATURATED`
     (`LOW`).
4. **Align spend to exact window boundaries & bracket cache writes.**
   Convert UTC `reset_time` into local time, subtract pure pre-window hours,
   surface mixed-hour boundaries transparently as `[min, upper]` in both JSON
   and Markdown, and report both base `tokscale` spend and 5-minute cache-write
   upper bounds when `cacheWrite == 0`.
5. **Guard against mid-hour 5h reset overcounts & report lossless savings honestly.**
   - When a `5h` bucket resets mid-hour, `tokscale hourly` can mix pre-reset
     spend into the boundary hour and make a naive `5h` implied cap or runway
     exceed its sibling `weekly` pool. The script flags `MID_HOUR_RESET_OVERCOUNT`,
     withholds bogus dollar projections, and reports `%` remaining cleanly until
     post-reset spend settles.
   - Always check `top_sessions` and `window_forensics` when a pool is `>= 80%`
     or locked to quantify concurrent subagents, `CONTEXT_SNOWBALL` average/peak
     context length, and 5-minute Prompt Cache TTL cold-resend (`20x`) waste—
     preferring zero-compression lossless levers (subagent offload + avoiding
     `>5m` cold resends) over unrealistic `<250k` auto-compact rules.
   - Multi-machine/web/IDE usage on the **same** account **underestimates**
     pool size; multiple accounts sharing **one** local client directory
     **overestimates** single-account capacity.
   - Surface all script warnings (including `tokscale` unpriced/stale-pricing
     stderr notices and `UNKNOWN_WINDOW` labels).

## Output Format

Deliver a concise, direct diagnostic report (do not dump raw commands for the
user to run):

1. **Headline status & pool capacity**: Implied API-dollar size of each pool
   (base ~ CW upper), `Weekly ÷ 5h` multiplier (noting clamp lower bound if
   applicable), and any locked/soft-locked pools with exact reset countdown.
2. **Calibration & runway table**: Pool | Window | Resets In | Local Spend |
   Quota Used (with `LOCKED`/`SOFT_LOCKOUT` badge) | Implied Pool | Remaining
   Runway (`~$` / `~msgs` / `ETA`) | Confidence.
3. **Lockout attribution & switch action** (when any pool is locked or `>= 80%`):
   Top burning sessions (highlighting any `CONTEXT_SNOWBALL` outlier) and
   immediately available alternate pools in the same subscription.
4. **Caveats**: Script warnings, concurrent notes, and attribution bias limits.
