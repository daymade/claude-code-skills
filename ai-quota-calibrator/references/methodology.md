# Quota Calibration Methodology & Provider Reference

This reference documents the math, bias directions, confidence rules, and
provider-specific quirks used by `scripts/calibrate_quota.py`.

## 1. Core Inversion Formula

For any quota bucket whose provider consumes quota proportionally to token cost:

$$\text{Implied Pool (USD)} = \frac{\text{Window Spend (USD)}}{\text{Used Fraction}}$$

where $\text{Used Fraction} = 1 - \text{remaining\_fraction} = \frac{\text{used\_percent}}{100}$.

When both a short-term (`5h`) bucket and a long-term (`weekly`) bucket are
active from the same starting point (neither has rolled over independently),
their exact capacity ratio is:

$$\text{Weekly-to-5h Multiplier} = \frac{\text{Used Fraction}_{5\text{h}}}{\text{Used Fraction}_{\text{weekly}}}$$

This ratio is **invariant to token pricing** as long as both buckets bill the
same workload over the same elapsed interval (for example, right after both
windows start from `100%`). If the weekly bucket already carried prior days'
usage before the current 5-hour window began, only the **incremental delta**
$\Delta \text{Used}_{5\text{h}} / \Delta \text{Used}_{\text{weekly}}$ across
two settled snapshots recovers the exact multiplier.

## 2. Confidence Grading Rules

| Grade | Conditions | How to interpret |
|---|---|---|
| `HIGH` | `used_pct >= 10%`, `< 99.9%`, stable readings (`|Δ| <= 0.002` across 2 reads), no mixed-hour ambiguity, single-account attribution | Reliable within ~±15–25% of provider internal pricing |
| `MEDIUM` | `2% <= used_pct < 10%`, OR `>= 10%` with minor active-session drift (`|Δ| > 0.002` but `|Δ|/used <= 15%` and `|Δ| <= 1.5%`), OR multi-account caveat | Solid order-of-magnitude estimate; re-check when idle or once >= 10% is consumed |
| `LOW` | `used_pct < 2%`, `used_pct >= 99.9%` (`SATURATED`), severe reading jitter (`|Δ|/used > 15%` or `|Δ| > 1.5%`), or unresolved mixed-hour ambiguity | Directional only; do not treat as a firm pool size |
| `UNTOUCHED` | `used_pct == 0%` (`remaining_fraction == 1.0`) | Bucket has not started; no inversion possible |
| `UNKNOWN_WINDOW` | Unrecognized window duration label or missing `reset_time` | Cannot derive `window_start` without guessing; spend and pool remain `N/A` |

## 3. Why Single-Turn Cold Probes Mislead

A tiny 1-turn synthetic prompt (e.g., 25K input, 100 output, minimal cache
reads) typically consumes `< 0.1%` of a weekly pool:

1. **Signal-to-noise failure**: Backend reservation jitter (`0.01` = 1%) and
   eventual-consistency replica lag are 10–20× larger than the true delta.
2. **Cache-ratio skew**: Real agentic coding sessions often run 80–95% prompt
   cache reads with substantial thinking/output tokens across dozens of tool
   turns. If a provider's internal cost weights differ slightly from public
   list prices on cache reads, cache writes, or thinking tokens, a cold
   zero-thinking probe will diverge sharply (4–5× observed in practice) from
   multi-turn production burn.

Always prefer calibrating against real multi-turn usage (`>= 5–15%` consumed).

## 4. Accounting Sensitivity & Bias Directions

### Cache-Write Upper Bound
Some local session logs record `input`, `cacheRead`, and `output`/`reasoning`
without splitting `cacheWrite` (`cacheWrite == 0`). Standard API pricing for
prompt-cached providers often charges `1.25×` base input for 5-minute cache
writes (for example, `$5/M` vs. `$4/M` on Claude Opus 5.5).

To avoid understating spend when `cacheWrite == 0`:
- **Base spend**: `tokscale` reported cost (treats `input` at standard rate).
- **Cache-write upper bound**: adds `+0.25 × (input_tokens × base_input_rate)`
  for Anthropic/Claude entries when `cacheWrite == 0` (leaving non-Anthropic
  models at their `tokscale` cost unless a custom upper bound is supplied).

### Attribution Bias Table

| Condition | Direction on `local_spend` | Effect on Implied Pool Size |
|---|---|---|
| Other machines, web app, or IDE extensions also burn the **same** account's quota | `local_spend < true_spend` | **Underestimates** true pool capacity |
| Multiple accounts share **one** local `tokscale` client directory (e.g., Codex multi-account) | `local_spend > single_account_spend` | **Overestimates** single-account capacity |
| Bucket is already at `100%` (`SATURATED`) | Spend may have stopped hours/days ago or spilled into retries/credits | Only an **approximate upper bound** unless lockout timestamp is known |
| `tokscale` warns of unpriced or stale-priced models | Missing cost for unpriced models | **Underestimates** spend and pool capacity |

## 5. Window Alignment & Mixed-Model Hours

`tokscale hourly --json` buckets spend by **local wall-clock hour**
(`"YYYY-MM-DD HH:00"`) and sums all models used during that hour into a single
`cost` field with a `models` list. Meanwhile, provider quota APIs report
`reset_time` in UTC ISO-8601 (`"...Z"` or `"+00:00"`).

To align a bucket's window `[window_start, now]` for a model group `G`:

1. Convert `reset_time` to local timezone and subtract the window duration
   (`7 days` for `weekly`, `5 hours` for `5h`, `30 days` for `30d`).
2. Query `tokscale models -c <client> --since <window_start_local_date> --json`
   to get exact per-model totals from local midnight `00:00` of
   `window_start_local_date` through `now`.
3. Query `tokscale hourly -c <client> --since <window_start_local_date> --json`
   to inspect hours before `window_start`:
   - **Fresh simultaneous start**: when a group's `5h` and `weekly` windows
     share the exact same `window_start` (within 5 seconds) and no hour strictly
     before `start_hour_floor` contains that group, zero spend from that group
     occurred before `window_start` even if the boundary hour mixed other groups—
     `models_since[G]` is exact!
   - **Pure-group pre-window hours** (`models ⊆ G`): subtract directly; prorate
     the boundary hour containing `window_start` by
     `(minute * 60 + second) / 3600`.
   - **Zero pre-window presence** (no hour before `window_start` contains any
     model in `G`): zero subtraction needed—`models --since` is exact!
   - **Unresolvable mixed boundary**: if a pre-window hour mixes multiple
     groups with no fresh-start proof, keep a transparent `[min, upper]`
     interval in both JSON (`spend_min_usd`, `implied_pool_min_usd`) and
     Markdown, and emit a `MIXED_HOUR_AMBIGUITY` warning rather than guessing a
     split.

Note: Local timezone offset is derived from the system clock at observation time;
for weekly windows that cross a daylight-saving-time (DST) transition, boundary
hours may shift by 1 hour.

## 6. Provider Notes

### Antigravity (`--provider antigravity`)
- **Quota source**: `agy -p /usage --output-format json`
  - `command.data.description` states the official accounting rule: quota is
    consumed proportionally to token cost, models within a group share a weekly
    and 5-hour limit, the 5-hour limit smooths aggregate demand, and the weekly
    limit ties to your tier.
  - `command.data.groups[].buckets[]` exposes 16-digit float
    `remaining_fraction`, `window` (`"weekly"` / `"5h"`), `id` (e.g.,
    `gemini-weekly`, `gemini-5h`, `3p-weekly`, `3p-5h`), and UTC `reset_time`.
- **Spend source**: `tokscale` client `antigravity-cli` (reads local CLI
  conversation SQLite databases under `~/.gemini/antigravity-cli/conversations/`).
  Note: `tokscale antigravity status` only tracks IDE/App language-server cache,
  not `antigravity-cli`.
- **Known `tokscale` mapping**: For Antigravity CLI Claude models, `tokscale`
  places output tokens in `reasoning` (`output == 0`) and prices `reasoning` at
  the output rate.
- **Known backend jitter**: In-flight requests can temporarily subtract a flat
  `0.01` (1%) from both `5h` and `weekly` buckets before settling a few seconds
  later. Taking two reads separated by ~4–5 seconds catches this immediately.

### Codex (`--provider codex`)
- **Quota source**: `tokscale usage --json` (entries with `"provider": "Codex"`,
  selecting the `"is_active": true` account by default, or `--account-email`).
- **Spend source**: `tokscale` client `codex`.
- **Multi-account caveat**: If `tokscale usage --json` lists multiple Codex
  accounts, local `~/.codex/sessions` aggregates rollouts across accounts. Flag
  this explicitly because attributing combined local spend to one account's
  quota percentage overstates that account's pool size.
