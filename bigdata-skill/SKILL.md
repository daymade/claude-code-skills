---
name: bigdata-skill
description: >-
  Pull Bigdata.com (RavenPack) financial and news data via the official
  `bigdata-client` SDK and `/v1/*` REST endpoints — structured financials,
  prices, analyst estimates, daily entity-sentiment series, annotated chunk
  search, screener — when the Bigdata MCP returns only pre-synthesized tearsheets
  but you need the machine-readable substrate. Use when the user mentions
  Bigdata.com, RavenPack, a `bd_v2_` key, the bigdata MCP, rp_entity_id,
  chunk/query_unit cost, or wants structured financials, fundamentals, prices,
  sentiment, or annotated news.
---

# Bigdata.com SDK + REST Toolkit

Get the structured substrate the Bigdata.com MCP server doesn't hand over. The
MCP returns clean prose and pre-synthesized tearsheets, but its search tool
gives chunks with no per-chunk sentiment or entity spans, and its tearsheets
give aggregate values — not the fiscal-period time series, universe screener, or
per-field JSON you'd build a pipeline on. The official `bigdata-client` SDK plus
a thin REST passthrough over the *same backend, same JWT* reach the official
`/v1/*` endpoints that hold it. This skill bundles a toolkit that does exactly
that — already debugged, already cost-guarded — so you don't re-pay the
discovery cost.

## The core problem this solves (read this first)

The Bigdata MCP server answers "what's the sentiment around NVIDIA?" with a
readable paragraph or a pre-synthesized tearsheet — genuinely useful for a chat
turn. But the moment you need the **machine-readable substrate** to build a
pipeline on, the MCP doesn't hand it over:

- its **search** tool returns chunks with text + relevance only — **no per-chunk
  sentiment number, no entity character spans**;
- its **tearsheets** give aggregate values (a single sentiment score, a summary
  of estimates) — **not** a fiscal-period time series you can compute on, a
  universe screener, or per-field JSON.

The fix is a general pattern, not a Bigdata trick:

> **When an MCP data source returns only synthesized output but you need the
> structured fields underneath, drop to the vendor SDK or REST.** MCP optimizes
> for a chat turn, not a pipeline.

Crucially, for Bigdata these structured fields are **official, publicly
documented REST endpoints** (`docs.bigdata.com/api-reference/...`), not a hidden
backend — and Bigdata is **sunsetting the SDK (EOL 2026-12-31) in favour of this
REST API**, so the REST layer here is the forward-compatible path, not a hack.
The SDK (`bigdata_client.Bigdata`) covers search + knowledge-graph; **`bd._api.http`**
reaches every `/v1/*` endpoint the SDK never wrapped. The bundled
`bigdata_toolkit` packages both behind one `BigdataClient`.

## When to use this skill

Trigger on any of these, in any language:

- The user is using **Bigdata.com / RavenPack** and the MCP result feels thin —
  "where's the sentiment score?", "I need entity-level data", "the calendar".
- They want **forward / structured** financials for a ticker: analyst
  estimates, earnings or event calendar, earnings surprise, analyst ratings,
  price targets, a company screener / universe.
- They want **annotated news chunks** with numeric sentiment + entity spans, or
  a sentiment time series / co-mention graph.
- They mention a **`bd_v2_` API key**, `rp_entity_id`, `query_unit` / chunk
  cost, `bigdata-client`, or "the bigdata MCP isn't enough".
- They're building an **investment-research dataset** and need a reusable,
  cost-aware data-pull layer rather than one-off MCP calls.

## Setup (one time)

**1 — API key (never hardcode it).** The client fail-fasts if it's missing:

```bash
export BIGDATA_API_KEY=bd_v2_xxxxxxxx
```

**2 — An isolated Python env with the official SDK.** The bundled toolkit
imports `bigdata_client`; install it once:

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python bigdata-client
# Behind a slow/blocked PyPI (e.g. mainland China) add a mirror, and unset any
# outbound proxy for the install step so uv reaches the index directly:
#   --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

**3 — Outbound proxy (only if your network needs one to reach
`api.bigdata.com`).** Two equivalent options — the official SDK accepts both: an
env var, or `BigdataClient(proxy=...)` in code. The env var is simplest:

```bash
export HTTPS_PROXY=http://<host>:<port>     # plus WSS_PROXY for chat/WebSocket
```

If a proxy does TLS interception (self-signed CA) and you hit SSL handshake
errors, the official fix is `BigdataClient(verify_ssl="<proxy-CA>.pem")` — not
blind retries.

**4 — Make the bundled package importable** by putting this skill's `scripts/`
on `PYTHONPATH` (or `sys.path.insert(0, "<this-skill>/scripts")`).

**Smoke-test the whole path** (entity resolve + quota are free; `--with-search`
adds one ~1 query_unit chunk search):

```bash
BIGDATA_API_KEY=bd_v2_xxx PYTHONPATH=scripts .venv/bin/python scripts/probe_example.py
```

## Quickstart

```python
import sys
sys.path.insert(0, "<this-skill>/scripts")          # so `import bigdata_toolkit` resolves
from bigdata_toolkit import (
    BigdataClient, EntityResolver, AnnotatedSearcher,
    StructuredDataREST, CostTracker, CostModel, rc,   # rc = SSL-retry wrapper
)

c  = BigdataClient()                                  # SDK + REST escape hatch, one object
er = EntityResolver(c)
nvda = rc(lambda: er.resolve_id("NVIDIA", country="US"))   # -> 'E09E2B'  (rp_entity_id is the gateway key)

# --- Structured financials the MCP does NOT expose (REST escape hatch) ---
rest = StructuredDataREST(c)
est  = rc(lambda: rest.analyst_estimates(nvda, period="quarter", limit=5))  # forward consensus
surp = rc(lambda: rest.latest_surprise(nvda))                               # last EPS/revenue surprise
cal  = rc(lambda: rest.events_calendar(nvda, categories=["earnings-call"],
                                       start_date="2026-06-01", end_date="2026-12-31"))

# --- Annotated chunks the MCP STRIPS: sentiment + entity spans (cost-guarded) ---
s    = AnnotatedSearcher(c)
docs = rc(lambda: s.search_entity(nvda, keyword="data center", chunk_limit=10))
# each chunk dict: {"sentiment": float, "entities": [{"key": rp_id, "start", "end"}], "text", ...}

# --- Always know your spend (chunk-billed; see Cost discipline) ---
ct = CostTracker(c); ct.snapshot()
# ... run a batch ...
print(ct.delta())     # {'delta_chunks':..., 'delta_query_units':..., 'usd_fast':...}
```

Wrap **every** network call in `rc(lambda: ...)` — a first-handshake `SSL:
UNEXPECTED_EOF` is common and the SDK's internal retry doesn't cover it.

## Routing — which capability answers the question

| The user wants… | Use | Module |
|---|---|---|
| Company name / ISIN / CUSIP / SEDOL → `rp_entity_id` | `EntityResolver.resolve_id` / `.resolve_by_isin` | `kg.py` (SDK) |
| Forward analyst consensus (revenue/EPS by fiscal period) | `StructuredDataREST.analyst_estimates` | `rest_ext.py` |
| Latest earnings surprise (actual vs estimate) | `.latest_surprise` | `rest_ext.py` |
| Upcoming earnings / event calendar (one name or whole market) | `.events_calendar` | `rest_ext.py` |
| Analyst ratings / price-target consensus | `.analyst_ratings` / `.price_target` | `rest_ext.py` |
| Full financial statements (income / balance / cash-flow, multi-year) | `.income_statement` / `.balance_sheet` / `.cash_flow_statement` | `rest_ext.py` |
| TTM valuation metrics & ratios (EV/EBITDA, ROE, P/E, margins) | `.key_metrics_ttm` / `.company_ratios_ttm` | `rest_ext.py` |
| Company profile (CEO, sector, employees, IPO date) | `.company_profile` | `rest_ext.py` |
| Daily OHLC prices / dividend history | `.daily_prices` / `.dividends` | `rest_ext.py` |
| Revenue by geography / product segment | `.revenue_geographic_segments` / `.revenue_product_segments` | `rest_ext.py` |
| Daily entity-sentiment time series (don't self-aggregate from chunks!) | `.entity_sentiment` | `rest_ext.py` |
| Co-mention graph (supply-chain / competitor / customer — ⚠️ chunk-billed) | `.connected_entities` | `rest_ext.py` |
| Build a universe by market-cap / sector / country | `.company_screener` | `rest_ext.py` |
| News/filing/transcript chunks with sentiment + entity spans | `AnnotatedSearcher.search_entity` | `search.py` (SDK) |
| Bulk-pull many searches 50% cheaper (portfolio backfill) | `BatchSearch` (create→upload→poll→download) | `rest_ext.py` |
| Track / forecast quota spend before a backfill | `CostTracker` / `CostModel` | `cost.py` |
| Hit an endpoint the toolkit hasn't wrapped yet | `client.http.post("v1/<resource>/query", body)` | `client.py` |

> `income/balance/cash-flow/daily-prices/dividends/revenue-segments` return
> `{fields, values}` — wrap them in `fields_values_to_records()` to get
> `[{field: value}]`. The `*_ttm` / `company_profile` endpoints are already flat.
> All structured endpoints above are **free** (0 chunks) except
> `connected_entities` and `AnnotatedSearcher` (chunk-billed).

## The two data faces (do NOT say "Bigdata fails for Chinese / A-shares")

This split is the most important non-obvious conclusion — state it precisely:

| Face | Path | A-share / Chinese verdict |
|---|---|---|
| **Structured financial** (estimates, calendar, surprise, ratings, target, screener, **financials, prices, dividends, revenue segments, daily entity-sentiment**) | REST (`rest_ext.py`) | **Works** — via `rp_entity_id` resolved from the **English name or ISIN** (not the Chinese name). Data is fresh. Minor holes (some A-share price-targets return the entity with no numeric target). The daily `entity_sentiment` series lives **here** and works for any resolvable entity — it is **not** the dead end below. |
| **Unstructured Chinese NLP** (Chinese-news entity detection, per-chunk Chinese sentiment) | SDK search (`search.py`) | **Dead end** — a data-source-level gap, not an SDK bug: Chinese entity detection ≈ 0, per-chunk CJK sentiment is a doc-level inherited value, and `language` mislabels Chinese filings as English. Pair Bigdata with a China-domestic source for Chinese-language *chunk* content; use Bigdata for the structured face (incl. aggregate `entity_sentiment`) + ISIN/KG crosswalk + English-language chunk sentiment. |

## Cost discipline

`1 query_unit = 10 chunks` (official). **Only chunk-search is billed** — the
structured `/v1/*` endpoints (estimates, financials, prices, calendar, surprise,
ratings, the sentiment time series, screener…) are **free** (0 chunks,
contract-tested). `connected_entities` (co-mentions) and `AnnotatedSearcher`
**are** chunk-billed.

Three levers when you do pay for chunks:

1. **`ChunkLimit`, never a bare `int`.** `Search.run(int)` is a *document* limit
   billed by the full chunk page; `ChunkLimit(n)` bills per chunk.
   `AnnotatedSearcher.search` forces `ChunkLimit` for you. (We observed roughly a
   52x gap once — **a single measured data point, not stated in the official
   docs**; treat the exact multiple as indicative. The rule "use `ChunkLimit`"
   holds regardless, because `max_chunks` is the official billing unit.)
2. **Rerank bills only the *returned* chunks** (official) — pass a
   `rerank_threshold` to recall broadly but pay only for the high-relevance hits.
3. **Batch search is 50% cheaper** (`$0.0075` vs `$0.015` / qu) — use
   `BatchSearch` for a large multi-query backfill.

Use `CostModel` to veto an over-budget job *before* running it, and
`CostTracker.snapshot()` / `delta()` to measure real spend. Full accounting →
`references/cost_accounting.md`.

## Known pitfalls (already solved — don't re-debug these)

Each cost real debugging time and is fixed or guarded in the toolkit. Full
reproductions and fixes in **`references/known_pitfalls.md`**:

1. **First-handshake `SSL: UNEXPECTED_EOF`** → wrap calls in `rc()`; the SDK's
   urllib3 retry only covers HTTP status, not the SSL EOF.
2. **`All(entity, Keyword(kw))` raises `TypeError`** → combine with the `&`
   operator (`entity & Keyword(kw)`); `All` takes a single iterable. (Fixed in
   `AnnotatedSearcher.entity_query`.)
3. **The 52x doc-limit billing trap** → always `ChunkLimit`, never a bare `int`.
4. **Closure capture in loops** → bind loop vars: `rc(lambda q=q, dr=dr: ...)`.
5. **`analyst_estimates(period="quarter")` 400s above `limit≈20`.**
6. **`company_screener` filters must nest under `"filters"`** — flat top-level
   keys don't 400, they're silently dropped → unfiltered universe.
7. **`Document.reporting_period` is always `None`** (the SDK model drops a field
   present on the REST wire) → `fetch_reporting_period_raw`.

## What this skill will not do

- **Never hardcode an API key.** `BigdataClient` reads `BIGDATA_API_KEY` and
  fail-fasts if absent — no plaintext fallback (that is exactly the pattern
  secret scanners catch).
- **Only ever reads — never writes or uploads.** Every method is a read-only
  query (`uploads` is `NotImplementedError` in API-key mode anyway), so the
  toolkit can't mutate your account or push data anywhere.
- **Never invent an endpoint or a schema.** Every signature here is runtime
  L4-verified or marked L3 (doc-confirmed, not yet run); see
  `references/verified_api_signatures.md`. For a new endpoint, confirm the path
  via `docs.bigdata.com/llms.txt` rather than guessing.

## File layout

```
bigdata-skill/
├── SKILL.md                       # this file — routing + setup + quickstart
├── scripts/
│   ├── bigdata_toolkit/           # the verified, cost-guarded package
│   │   ├── client.py              # BigdataClient: SDK (.bd) + REST escape hatch (.http/.conn)
│   │   ├── kg.py                  # EntityResolver: name/ISIN/CUSIP/SEDOL → rp_entity_id
│   │   ├── search.py              # AnnotatedSearcher: chunks + sentiment + entity spans (SDK)
│   │   ├── rest_ext.py            # StructuredDataREST (estimates/financials/prices/dividends/sentiment/co-mentions/screener) + BatchSearch + fields_values_to_records — official REST
│   │   ├── cost.py                # CostTracker + CostModel: chunk billing + budget veto
│   │   └── retry.py               # rc(): SSL/transient-error retry passthrough
│   └── probe_example.py           # runnable end-to-end smoke test
└── references/
    ├── escape_hatch_architecture.md  # WHY the MCP is lossy; bd._api.http mechanism; adding endpoints
    ├── verified_api_signatures.md    # L4/L3-verified signatures + the two data faces, with evidence
    ├── cost_accounting.md            # chunk billing, the 52x trap, CostModel/CostTracker, budgeting
    └── known_pitfalls.md             # every pitfall above, with reproduction + fix
```

## References

| Read when you need to… | File |
|---|---|
| Understand *why* the MCP is insufficient and how the REST escape hatch works (and how to wrap a new `/v1/*` endpoint) | `references/escape_hatch_architecture.md` |
| Look up an exact verified method signature + its verification level | `references/verified_api_signatures.md` |
| Budget a backfill or debug a surprise quota burn | `references/cost_accounting.md` |
| Diagnose an error you hit while pulling data | `references/known_pitfalls.md` |
