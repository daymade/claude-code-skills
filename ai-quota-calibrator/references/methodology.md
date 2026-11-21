# Quota Calibration Methodology & Provider Reference

This reference documents the math, bias directions, confidence rules, lockout
mechanics, and provider-specific quirks used by `scripts/calibrate_quota.py`.

## 1. Core Inversion Formula

For any quota bucket whose provider consumes quota proportionally to token cost:

$$\text{Implied Pool (USD)} = \frac{\text{Window Spend (USD)}}{\text{Used Fraction}}$$

where $\text{Used Fraction} = 1 - \text{remaining\_fraction} = \frac{\text{used\_percent}}{100}$.

When both a short-term (`5h`) bucket and a long-term (`weekly`) bucket are
active from the same starting point (neither has rolled over independently),
their capacity ratio is:

$$\text{Weekly-to-5h Multiplier} = \frac{\text{Used Fraction}_{5\text{h}}}{\text{Used Fraction}_{\text{weekly}}}$$

This ratio is **invariant to token pricing** while neither bucket is clamped.
However, once `5h` hits `0%` (`LOCKED`) or the `< 1%` pre-reservation floor
(`SOFT_LOCKOUT`), `5h` clamps at `0.0` while the final turn still deducts from
`weekly`. In that clamped regime, `u5 / uw` is a **lower bound** (`>= Xx`),
never an exact multiplier.

## 2. Confidence Grading & Lockout States

### Lockout States
- `OPEN`: Normal operation.
- `SOFT_LOCKOUT` (Antigravity only): `0.001 < remaining_fraction < 0.01`.
  Antigravity applies a `0.01` (1%) pre-reservation check before executing a
  turn, so requests can already be rate-limited even while the UI displays `1%`.
- `LOCKED`: `remaining_fraction <= 0.001` (`>= 99.9%` used).

### Confidence Grades

| Grade | Conditions | How to interpret |
|---|---|---|
| `LOCKOUT_CAP` | Antigravity `5h` bucket hits `LOCKED`/`SOFT_LOCKOUT` from a fresh simultaneous `5h+weekly` start while `weekly` remains open (`< 99%`), with no mixed-hour ambiguity or severe jitter | Direct empirical measurement of the 5h hard cap (uses observed spend directly as the cap) |
| `HIGH` | `used_pct >= 10%`, `< 99.9%`, stable reads (`|Δ| <= 0.002`) OR minor monotonic concurrent burn (`v2 < v1`, `<= 5%` relative on `>= 20%` used), no mixed-hour ambiguity, single-account attribution | Reliable within ~±15–25% of provider internal pricing |
| `MEDIUM` | `2% <= used_pct < 10%`, OR upward rebound (`v2 > v1` within non-severe bounds), OR moderate concurrent drift (`5%–15%` relative), OR multi-account caveat | Solid order-of-magnitude estimate; re-check when idle or once >= 10% is consumed |
| `LOW` | `used_pct < 2%`, `SATURATED` (`>= 99.9%` without fresh-lockout-cap proof), severe jitter (`|Δ|/used > 15%` or `|Δ| > 1.5%`), or unresolved mixed-hour ambiguity | Directional only; do not treat as a firm pool size |
| `UNTOUCHED` | `used_pct == 0%` (`remaining_fraction == 1.0`) | Bucket has not started; no inversion possible |
| `UNKNOWN_WINDOW` | Unrecognized window duration label or missing `reset_time` | Cannot derive `window_start` without guessing; spend and pool remain `N/A` |

## 3. Directional Stability Checks (`v2 - v1`)

Taking two reads spaced ~5 seconds apart separates two very different signals:

- **Upward rebound (`v2 > v1`, `Δ > +0.002`)**: Remaining quota *increased*.
  This indicates a `1%` in-flight reservation refund or multi-replica read lag
  (`RESERVATION_REFUND_OR_REPLICA_LAG`). Always warn and cap confidence.
- **Monotonic concurrent burn (`v2 < v1`, `Δ < -0.002`)**: Remaining quota
  decreased while another active session ran. When `used >= 20%` and the
  relative shift `|Δ| / used <= 5%` (and `|Δ| <= 1.5%`), the calibration
  denominator is barely affected—record an informational `CONCURRENT_BURN` note
  without falsely downgrading a high-sample bucket.

## 4. Why Single-Turn Cold Probes Mislead

A tiny 1-turn synthetic prompt (e.g., 25K input, 100 output, minimal cache
reads) typically consumes `< 0.1%` of a weekly pool:

1. **Signal-to-noise failure**: Backend reservation jitter (`0.01` = 1%) and
   eventual-consistency replica lag are 10–20× larger than the true delta.
2. **Cache-ratio skew**: Real agentic coding sessions often run 80–95% prompt
   cache reads with substantial thinking/output tokens across dozens of tool
   turns. A cold zero-thinking probe can diverge 4–5× from real multi-turn burn.

Always prefer calibrating against real multi-turn usage (`>= 5–15%` consumed)
or a `LOCKOUT_CAP` event.

## 5. Runway, Burn Rate & Context-Snowball Attribution

- **Remaining API-dollar runway**: `remaining_usd = implied_pool_usd * remaining_fraction`
  (`$0` when `LOCKED` or `SOFT_LOCKOUT`).
- **Per-message cost & remaining messages**: `avg_cost_per_msg = window_spend / window_msgs`,
  `estimated_remaining_msgs = int(remaining_usd / avg_cost_per_msg)`.
- **Burn rate & ETA**: `burn_rate_usd_per_hour = window_spend / elapsed_hours`
  (computed only when `elapsed_hours >= 0.05`, i.e., >= 3 minutes), yielding
  `eta_to_exhaustion = remaining_usd / burn_rate_usd_per_hour`.
- **`CONTEXT_SNOWBALL` detection**: In `top_sessions`, a session is flagged
  when `message_count >= 50`, `cache_read_pct >= 90%`, and its per-message cost
  is either `>= 1.5×` the group median or `>= $0.09/msg`. Very long sessions
  accumulate hundreds of thousands of cached tokens per turn; even at a 95%
  cache discount, cache reads alone can double per-turn spend and dominate a
  5-hour cap.

## 6. Accounting Sensitivity & Bias Directions

### Cache-Write Upper Bound
Some local session logs record `input`, `cacheRead`, and `output`/`reasoning`
without splitting `cacheWrite` (`cacheWrite == 0`). Standard API pricing for
prompt-cached providers often charges `1.25×` base input for 5-minute cache
writes (for example, `$5/M` vs. `$4/M` on Claude Opus 5.5).

To avoid understating spend when `cacheWrite == 0`:
- **Base spend**: `tokscale` reported cost (treats `input` at standard rate).
- **Cache-write upper bound**: adds `+0.25 × (input_tokens × base_input_rate)`
  for Anthropic/Claude entries when `cacheWrite == 0`.

### Attribution Bias Table

| Condition | Direction on `local_spend` | Effect on Implied Pool Size |
|---|---|---|
| Other machines, web app, or IDE extensions also burn the **same** account's quota | `local_spend < true_spend` | **Underestimates** true pool capacity |
| Multiple accounts share **one** local `tokscale` client directory (e.g., Codex multi-account) | `local_spend > single_account_spend` | **Overestimates** single-account capacity |
| Bucket is already at `100%` without fresh-lockout-cap proof (`SATURATED`) | Spend may have stopped hours/days ago or spilled into retries/credits | Only an **approximate upper bound** unless lockout timestamp is known |
| `tokscale` warns of unpriced or stale-priced models | Missing cost for unpriced models | **Underestimates** spend and pool capacity |

## 7. Window Alignment & Mixed-Model Hours

`tokscale hourly --json` buckets spend by **local wall-clock hour**
(`"YYYY-MM-DD HH:00"`) and sums all models used during that hour into a single
`cost` field with a `models` list. Meanwhile, provider quota APIs report
`reset_time` in UTC ISO-8601 (`"...Z"` or `"+00:00"`).

To align a bucket's window `[window_start, now]` for a model group `G`:

1. Convert `reset_time` to local timezone and subtract the parsed window
   duration (`5h`, `daily`/`24h`, `7d`/`weekly`, `N-day`, `30d`/`monthly`).
   Unrecognized labels yield `UNKNOWN_WINDOW` rather than guessing.
2. Query `tokscale models -c <client> --since <window_start_local_date> --json`
   to get exact per-model totals from local midnight `00:00` through `now`.
3. Query `tokscale hourly -c <client> --since <window_start_local_date> --json`
   to inspect hours before `window_start`:
   - **Fresh simultaneous start or rolling weekly start**: when either a group's
     `5h` and `weekly` windows share the exact same `window_start` (within 5
     seconds) or the bucket itself is a rolling `weekly` window, and no hour
     strictly before `start_hour_floor` contains that group, zero spend from
     that group occurred before `window_start` even if the boundary hour mixed
     other groups—`models_since[G]` is exact (`exact_fresh_window_start`).
   - **Pure-group pre-window hours** (`models ⊆ G`): subtract directly; prorate
     the boundary hour containing `window_start` by
     `(minute * 60 + second) / 3600`.
   - **Zero pre-window presence** (no hour before `window_start` contains any
     model in `G`): zero subtraction needed—`models --since` is exact.
   - **Unresolvable mixed boundary & mid-hour 5h reset overcount**: if a
     pre-window hour mixes multiple groups with no fresh-start proof, keep a
     transparent `[min, upper]` interval in both JSON (`spend_min_usd`,
     `implied_pool_min_usd`) and Markdown, and emit `MIXED_HOUR_AMBIGUITY`.
     Furthermore, because a 5-hour pool's capacity can never exceed its sibling
     weekly pool, whenever a `5h` bucket's implied cap exceeds the sibling
     `weekly` pool by `> 5%` (or a `LOW`-confidence `5h` bucket's upper bound
     exceeds `weekly` by `> 5%` with `spend_min_usd == 0` or `< 10%` used),
     emit `MID_HOUR_RESET_OVERCOUNT`, set `boundary_hour_overcount = true`, and
     withhold the invalid 5h dollar projection until post-reset spend settles.
     (Independent remaining dollars `rem5` vs `remw` are intentionally NOT
     compared here, since a freshly reset 5h pool can legitimately have more
     remaining dollars than a nearly spent weekly pool.)

Note: Local timezone offset is derived from the system clock at observation time;
for weekly windows that cross a daylight-saving-time (DST) transition, boundary
hours may shift by 1 hour.

## 8. Bounded Turn-Level Forensics & Lossless Savings

When `top_sessions` is populated for Antigravity, `analyze_antigravity_turn_forensics()`
reads local `transcript.jsonl` files **strictly for those session IDs** (never
scanning the full transcript directory) to separate three real cost drivers:

1. **Primary session normal burn**: cache-read and reasoning spend of the top
   session, along with its average (`avg_context_k`) and peak (`peak_context_k`)
   prompt context length.
2. **Concurrent subagents**: multi-turn sessions in the same quota group whose
   active window overlaps the primary session (e.g., subagents spawned onto an
   Opus 5h pool instead of Gemini).
3. **5-minute Prompt Cache TTL cold resends (`20×`)**: turns after turn 1 with
   `>= 50k` fresh `input_tokens`, which re-pay full input rate (`$4/M`) instead
   of cached read rate (`$0.20/M`).

The resulting `zero_compression_savings_usd` quantifies how much quota can be
saved purely by offloading concurrent subagents and avoiding `>5m` cold resends
on `250k+` sessions—without recommending unrealistic `<250k` auto-compact rules.

## 9. Provider Notes

### Antigravity (`--provider antigravity`)
- **Quota source**: `agy -p /usage --output-format json` (`command.data.groups[].buckets[]`).
- **Spend source**: `tokscale` client `antigravity-cli` (reads local CLI
  conversation SQLite databases under `~/.gemini/antigravity-cli/conversations/`).
- **Known `tokscale` mapping**: For Antigravity CLI Claude models, `tokscale`
  places output tokens in `reasoning` (`output == 0`) and prices `reasoning` at
  the output rate.

### Codex (`--provider codex`)
- **Quota source**: `tokscale usage --json` (entries with `"provider": "Codex"`,
  selecting the `"is_active": true` account by default, or `--account-email`).
- **Spend source**: `tokscale` client `codex`.
- **Multi-account caveat**: If `tokscale usage --json` lists multiple Codex
  accounts, local `~/.codex/sessions` aggregates rollouts across accounts.
