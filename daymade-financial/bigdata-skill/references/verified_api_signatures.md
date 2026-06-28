# Verified API signatures + the two data faces

Every signature below was either **runtime-tested (L4)** or **doc-confirmed
(L3)**. Treat L3 as "schema confirmed, run a contract test before relying on it
in production". Nothing here is guessed — if you need an endpoint not listed,
confirm it via `docs.bigdata.com/llms.txt` and add it as L3 until you run it.

## Verification levels

- **L4** — actually ran it, saw HTTP 200 + real data.
- **L3** — found in the docs/llms.txt index, schema confirmed, not yet run live.
  Endpoint path is doc-sourced; verify before production.

## EntityResolver — `kg.py` (SDK knowledge-graph)

`rp_entity_id` (a 6-char alphanumeric like Apple `D8442A`) is the **primary key
for almost everything** — search `Entity(id)`, and every `rest_ext` endpoint.

```text
resolve_id(name, *, country=None) -> str | None      # first hit, or None (no fallback)
find_companies(name, *, country=None, limit=5, as_dict=True)
resolve_by_isin(isins: list[str], *, as_dict=True)   # crosswalk
resolve_by_cusip(cusips) / resolve_by_sedol(sedols)
find_topics(values, *, limit=5)                      # ⚠ Chinese topics ≈ 0 hits
get_entities(ids)                                    # resolves COMP + TOPC, not ENTITY-only
```

- **A-share rule (L4):** the Chinese name returns **0 hits**
  (`find_companies('贵州茅台')` → nothing). Resolve via the **English official
  name** (`'Kweichow Moutai'` → `914E1F`) or **ISIN** (`CNE0000018R8` → `914E1F`).
- `country` is ISO-2 (`'CN'` / `'US'` / `'HK'`).
- `kg.autosuggest` raises `NotImplementedError` in API-key mode (same family as
  `uploads`); use the `find_*` methods, not interactive autosuggest.

## AnnotatedSearcher — `search.py` (SDK search)

```text
search(query, *, chunk_limit=10, date_range=None,
       scope=DocumentType.ALL, sortby=SortBy.RELEVANCE,
       rerank_threshold=None, as_dict=True) -> list[dict]
search_entity(rp_entity_id, *, keyword=None, chunk_limit=10, **kwargs)
entity_query(rp_entity_id, keyword=None)             # Entity(id) [& Keyword(kw)]
```

- `chunk_limit` is the **cost-bearing** parameter; internally wrapped in
  `ChunkLimit(n)` (never a bare int — see `cost_accounting.md`).
- `date_range`: `AbsoluteDateRange(start, end)` or `RollingDateRange.*`. Narrower
  windows cost less at the same limit.
- `scope`: `DocumentType.ALL / NEWS / FILINGS / TRANSCRIPTS`.

Fields the wrapper flattens (the layer the MCP strips), runtime-confirmed:

```text
Document:            id, headline, sentiment, document_scope, source, timestamp,
                     language, url, reporting_period (always None — SDK drops it),
                     reporting_entities, document_type
DocumentChunk:       text, chunk, entities, sentences, relevance, sentiment,
                     section_metadata, speaker
DocumentSentenceEntity: key (rp_entity_id), start, end (char span), query_type
```

`text[start:end]` on a chunk yields the annotated entity's surface form.

## StructuredDataREST — `rest_ext.py` (REST escape hatch)

Mostly `POST /v1/<resource>/query` (exceptions noted below: `entity-sentiment/`
takes a **trailing slash**; co-mentions + batch live under `/v1/search/`). All
return **raw dict/list** (half-documented endpoints — defend on the caller side).
Identifier-bearing endpoints use `{"identifier": {"type": "rp_entity_id",
"value": id}}` (spec-confirmed); `events_calendar` uses `{"rp_entity_id": [...]}`.

| Method | Endpoint | What it returns | Level |
|---|---|---|---|
| `events_calendar(id?, *, categories, start_date, end_date, countries?, limit=5, cursor?)` | `v1/events-calendar/query` | forward earnings/call calendar; pass no entity + `countries` + window to scan the whole market | **L4** |
| `analyst_estimates(id, *, period='quarter', limit=5)` | `v1/analyst-estimates/query` | forward consensus: REVENUE/EBITDA/EBIT/NET_INCOME/SGA/EPS LOW/HIGH/AVG + analyst counts, by fiscal period | **L4** |
| `latest_surprise(id)` | `v1/latest-surprise/query` | most recent reporting_date + eps/revenue actual vs estimated + surprise_pct (single latest period only) | **L4** |
| `analyst_ratings(id)` | `v1/analyst-ratings/query` | strong_buy/buy/hold/sell/strong_sell + consensus | **L4** |
| `price_target(id)` | `v1/price/target/query` | target high/low/consensus/median + currency | **L4** |
| `company_screener(*, market_cap_more_than, sector, industry, country, exchange, is_etf, limit, **extra)` | `v1/company-screener/query` | universe construction | **L4** (filters nested under `filters`, verified) |
| `income_statement(id, *, period, limit)` | `v1/income-statement/query` | income statement fields (REVENUE/GROSS_PROFIT/EBITDA/EBIT/NET_INCOME…), `{fields,values}` | **L4** |
| `balance_sheet(id, *, period, limit)` | `v1/balance-sheet/query` | balance sheet (TOTAL_ASSETS/TOTAL_DEBT/NET_DEBT/EQUITY…), `{fields,values}` | **L4** |
| `cash_flow_statement(id, *, period, limit)` | `v1/cash-flow-statement/query` | cash flow (OPERATING_CASH_FLOW/FREE_CASH_FLOW/CAPEX…), `{fields,values}` | **L4** |
| `key_metrics_ttm(id)` | `v1/key-metrics-ttm/query` | TTM metrics (EV/EBITDA, ROE, ROIC, FCF yield…), flat list | **L4** |
| `company_ratios_ttm(id)` | `v1/company-ratios-ttm/query` | TTM ratios (margins, P/E, P/B, D/E, dividend yield…), flat list | **L4** |
| `company_profile(id)` | `v1/company-profile/query` | profile (name/CEO/sector/website/employees/IPO…), flat list | **L4** |
| `daily_prices(id, *, start_date, end_date)` | `v1/price/daily/query` | daily OHLC (DATE/OPEN/HIGH/LOW/CLOSE/VOLUME/VWAP…), `{fields,values}` | **L4** |
| `dividends(id, *, start_date, end_date)` | `v1/dividends/query` | dividend history (DATE/DIVIDEND/YIELD/FREQUENCY…), `{fields,values}` | **L4** |
| `revenue_geographic_segments(id, *, period, limit)` | `v1/company-revenue-geographic-segments/query` | revenue by region (REGION_SEGMENTS nested) | **L4** |
| `revenue_product_segments(id, *, period, limit)` | `v1/company-revenue-product-segments/query` | revenue by product (PRODUCT_SEGMENTS nested) | **L4** |
| `entity_sentiment(id, *, start_date, end_date)` | `v1/entity-sentiment/` ⚠️ trailing slash | daily sentiment series (daily_sentiment/sentiment_pressure/abnormal_media_attention) | **L4** |
| `connected_entities(id, *, date_range, limit)` | `v1/search/co-mentions/entities` | co-mention graph grouped by category (total_chunks/headlines); optional `date_range` → `query.filters.timestamp` — **chunk-billed** | **L4** |
| `BatchSearch.create_job()` / `.get_status(id)` / `.upload_input` / `.download_results` | `v1/search/batches` (+ `/{id}`) | batch search **50% off**; create/status L4, upload/download wired but end-to-end unverified | **L4 / L3** |
| `fetch_reporting_period_raw(payload)` | `cqs/query-chunks` | raw `stories[].reportingPeriod` the SDK model drops — **chunk-billed** | **L4** |

Endpoint quirks (all runtime-observed):

- `analyst_estimates(period='quarter')` caps `limit` at **~20**; `limit=30`
  → 400 with an unhelpful message. Don't read it as a dead endpoint.
- `company_screener` filters **must be nested under a `"filters"` object**
  (`{"filters": {market_cap_more_than, sector, industry, country, exchange,
  is_etf}, "limit": n}`, `limit`≤1000 at top level). Flat top-level filters do
  **not** 400 — they are silently dropped and the screener returns an unfiltered
  universe (contract-tested 2026-05-30: flat → Gold ETF; nested → NVIDIA/Alphabet).
- `analyst_estimates` identifier shape observed as
  `{"identifier": {"type": "rp_entity_id", "value": id}}`; some RavenPack
  versions accept a bare `rp_entity_id` array instead. If one 400s, try the other.
- These analyst/events/quota endpoints are **not chunk-billed** (only search's
  `query-chunks` increments usage). `fetch_reporting_period_raw` is the one
  exception — it goes through `query-chunks` and IS chunk-billed.

## CostTracker / CostModel — `cost.py`

```text
CostTracker(client).quota()        -> {max_chunks, used_chunks, remaining_chunks,
                                       used/remaining/max_query_units, pct_used}
                  .snapshot()      -> records baseline; .delta() -> spend since baseline
                  .quota_detailed_raw()  -> free REST side-channel (v1/subscription/quotas)
CostModel(chunk_limit_per_query=500, tier='fast', trial_query_units=67000)
         .estimate(n_entities, n_windows=1) -> {usd, total_query_units, pct_of_trial_quota, ...}
```

## Known entity IDs (worked examples — public companies, safe to reuse)

| Name | rp_entity_id | Note |
|---|---|---|
| Apple | `D8442A` | resolves from `"Apple"` directly |
| NVIDIA | `E09E2B` | resolves from `"NVIDIA"` (country `US`) |
| Kweichow Moutai (贵州茅台) | `914E1F` | A-share: resolve via `"Kweichow Moutai"` or ISIN `CNE0000018R8`, **not** the Chinese name |

## The two data faces (the precise conclusion)

Do not collapse this into "Bigdata doesn't work for A-shares". It's two faces:

1. **Structured financial face** (`rest_ext.py`): **works for A-shares + HK** via
   `rp_entity_id` (English name or ISIN). Data is fresh (recently-updated
   surprises observed). Holes: some A-share `price_target` returns
   the entity with no numeric target (US names like AAPL are complete).
2. **Unstructured Chinese-NLP face** (`search.py`): **dead end** — a
   data-source-level gap, not an SDK bug. Chinese entity detection ≈ 0, CJK chunk
   sentiment is a doc-level inherited value (chunk sentiment == doc sentiment),
   and `language` mislabels Chinese filings as English. For Chinese-language
   content, pair Bigdata with a China-domestic research/news source; use Bigdata
   for the structured face, ISIN/KG crosswalk, and English-language sentiment.
