# Cost accounting — chunk billing, the 52x trap, budgeting

Bigdata bills by **chunk**, not by call. One default argument can silently drain
a whole quota, so cost is a first-class concern in this toolkit, not an
afterthought.

## The unit

`1 query_unit = 10 chunks`. Corroborated three independent ways inside the SDK:
the raw `chunks_count` accumulation, `get_usage()` dividing by 10, and
`subscription`'s `query_unit_used = contextual_units_read / 10`.

The REST raw counter
`get_my_quota().organization_consumed.contextual_units_read` is a **chunk**
count, not a query_unit count. `CostTracker` reads this raw counter so the
chunk semantics are preserved (the SDK's high-level `subscription.get_details()`
pre-divides by 10 and loses the chunk granularity).

## List pricing

| Tier | USD / query_unit |
|---|---|
| Fast Search | `0.015` |
| Smart Search | `0.03` |
| Batch (async) | `0.0075` (50% off) |

Source: `docs.bigdata.com` (public list prices).

## The doc-limit trap (use `ChunkLimit`, not a bare `int`)

`Search.run(limit)` accepts either an `int` or a `ChunkLimit(n)`:

- A bare **`int` is a document limit, billed by the full page of chunks** — the
  number of *documents* you ask for barely changes the bill; you pay for the
  chunk page either way.
- **`ChunkLimit(n)` bills by chunk**: `ChunkLimit(10) = 1 query_unit`.

We once measured roughly a **52x gap** (`run(1) ≈ run(10) ≈ 52 query_units`) —
but that is a **single measured data point, not stated in the official pricing
docs**; treat the exact multiple as indicative (it likely varies by ticker /
window / document count). The rule holds regardless: `max_chunks` is the
official billing unit, so always pass `ChunkLimit(n)`. `AnnotatedSearcher.search`
forces it for you; any raw `bd.search.new(...).run(...)` you write must too —
code-review every cold-start backfill for a bare `run(int)`.

A second, smaller lever: **window width** — at the same limit a narrow date
window costs less than a wide one (we saw ~2.6x once; a single measured point —
narrow the window when you can).

## What's billed vs free

Only **chunk-search** counts against your quota (contract-tested 2026-05-30):

| Billed (chunks) | Free (0 chunks) |
|---|---|
| `AnnotatedSearcher` (SDK search), `connected_entities` (co-mentions), `fetch_reporting_period_raw`, the searches a `BatchSearch` runs | every other `StructuredDataREST` endpoint — estimates, financials, prices, dividends, calendar, surprise, ratings, target, screener, `entity_sentiment`, quotas |

So a deep single-ticker dossier built from the structured endpoints (financials,
prices, the sentiment series, estimates) is **essentially free** — the cost is in
the annotated chunk evidence you pull on top of it.

## Two more levers (official)

- **Rerank bills only the *returned* chunks** — pass a `rerank_threshold` to
  `AnnotatedSearcher.search` to recall broadly but pay only for the high-relevance
  hits (official: the `rerank_search` how-to).
- **Batch search is 50% off** (`$0.0075` vs `$0.015` / query_unit) — pack a large
  multi-query backfill through `BatchSearch` (create → upload jsonl → poll →
  download). Official use case: portfolio-wide monitoring.

## Budgeting a backfill before you run it (`CostModel`)

`CostModel` is pure arithmetic — use it to veto an over-budget job *before*
spending anything:

```python
from bigdata_toolkit import CostModel
m = CostModel(chunk_limit_per_query=500, tier="fast")
print(m.estimate(n_entities=20,  n_windows=1))   # PoC sample
print(m.estimate(n_entities=100, n_windows=12))  # 100 names x 3yr quarterly
# -> {'usd':..., 'total_query_units':..., 'pct_of_trial_quota':..., ...}
```

`trial_query_units` (default `67000`) sets the denominator for
`pct_of_trial_quota`. A typical 1-week full-content trial is ≈ 67000 query_units
≈ $1005 at list — but set it to **your account's actual `max_query_units`**
(from `CostTracker.quota()`) for an accurate percentage.

**Trial reality:** an institutional universe (100–200 names) doing one multi-year
backfill **approaches or exceeds the entire trial quota** (100 names × 3yr
quarterly ≈ 90%; 200 names ≈ 180%). A trial is only good for a **PoC-grade
sample (≤20 names, single snapshot)**. A full production load needs a larger
(paid) quota — don't plan a full backfill against trial credits.

## Measuring real spend (`CostTracker`)

Estimates are for vetoing; measure the real burn to calibrate:

```python
from bigdata_toolkit import CostTracker
ct = CostTracker(client)
ct.snapshot()                    # baseline (raises in delta() if you forget — no guessed baseline)
# ... run a batch ...
print(ct.delta())                # {'delta_chunks', 'delta_query_units', 'usd_fast', 'usd_smart', ...}
```

`CostTracker.quota_detailed_raw()` hits `v1/subscription/quotas` — a **free**
side-channel (not chunk-billed) with billing-period + per-unit breakdown. Poll
it mid-backfill to measure the real chunk→credit conversion rather than trusting
the estimate. For a long pull, snapshot/delta around each batch and stop when
cumulative spend nears your cap.
