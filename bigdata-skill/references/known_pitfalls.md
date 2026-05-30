# Known pitfalls (symptom → root cause → fix)

Every entry here cost real debugging time. Most are already fixed or guarded in
the bundled toolkit; the rest you handle at call sites. When you hit a new one,
add it here with the same shape so the next person doesn't re-debug it.

## 1. First-handshake `SSL: UNEXPECTED_EOF`

- **Symptom:** the first call (often entity resolve) throws
  `SSLError: UNEXPECTED_EOF` / `Connection reset` / `RemoteDisconnected`,
  especially through an outbound proxy. Retrying by hand works.
- **Root cause:** the SDK's HTTP layer (`requests` / `aiohttp`) doesn't retry an
  **SSL handshake EOF** — and the official exception hierarchy doesn't even model
  it. One network blip becomes a hard exception.
- **Fix:** wrap every network call in `rc()` (bundled in `retry.py`, exported
  from the package). It retries only on transient markers
  (`SSL`/`EOF`/`Connection`/`Max retries`/`timeout`/`RemoteDisconnected`) and
  re-raises everything else immediately — it does not swallow real errors.

  ```python
  from bigdata_toolkit import rc
  nvda = rc(lambda: er.resolve_id("NVIDIA", country="US"))
  ```

## 2. `All(entity, Keyword(kw))` → `TypeError: All() takes 1 positional argument`

- **Symptom:** building an "entity AND keyword" query with
  `All(Entity(id), Keyword(kw))` raises `TypeError`.
- **Root cause:** `bigdata_client.query.All` takes a **single iterable**, not
  two positional args.
- **Fix:** combine with the overloaded `&` operator. Already fixed in
  `AnnotatedSearcher.entity_query`:

  ```python
  from bigdata_client.query import Entity, Keyword
  q = Entity(id) & Keyword(kw)          # not All(Entity(id), Keyword(kw))
  ```

## 3. The 52x doc-limit billing trap

- **Symptom:** a tiny search burned ~52 query_units when you expected ~1.
- **Root cause:** `Search.run(int)` is a document limit billed by the full chunk
  page — `run(1) ≈ run(10) ≈ 52 query_units`.
- **Fix:** always `ChunkLimit(n)`. `AnnotatedSearcher.search` does this for you;
  any raw `bd.search` must too. Detail: `cost_accounting.md`.

## 4. Closure capture in a backfill loop

- **Symptom:** every iteration of a loop pulls the **same** (last) keyword /
  window, even though the loop variable changes.
- **Root cause:** `rc(lambda: f(kw))` captures `kw` by reference; by the time
  the lambda runs, the loop has advanced.
- **Fix:** bind the loop variables as default args:

  ```python
  docs = rc(lambda kw=kw, dr=dr, lim=lim:
            s.search_entity(nvda, keyword=kw, chunk_limit=lim, date_range=dr))
  ```

## 5. `analyst_estimates(period="quarter")` 400s above `limit≈20`

- **Symptom:** `limit=30` → HTTP 400 with an unhelpful message; looks like the
  endpoint is broken.
- **Root cause:** quarterly estimates cap `limit` at ~20.
- **Fix:** keep `limit ≤ 20`; page if you need more history.

## 6. `company_screener` filters silently ignored → UNfiltered universe

- **Symptom:** the screener returns `200` with a `results` list, but the rows
  ignore your filters entirely (ask `market_cap_more_than: 1e12`, get a small
  Gold ETF back).
- **Root cause:** filters must be **nested under a `"filters"` object**
  (`{"filters": {market_cap_more_than, sector, industry, country, exchange,
  is_etf}, "limit": n}`). Passing them as **flat top-level keys does NOT 400 —
  the backend silently drops them and returns an unfiltered universe.**
- **Fix:** nest them under `filters` (the toolkit's `company_screener` now does).
  Contract-tested 2026-05-30: flat `{market_cap_more_than: 1e12}` returned a Gold
  ETF; nested `{filters: {market_cap_more_than: 1e12}}` correctly returned NVIDIA
  / Alphabet. An earlier note here said "pass flat" — that was wrong; the live
  test overrides it.

## 7. `Document.reporting_period` is always `None`

- **Symptom:** every document's `reporting_period` is `None` even for filings.
- **Root cause:** the field exists on the REST wire (~75% populated on filings)
  but the SDK's `ChunkedDocumentResponse` model omits it, so pydantic drops it.
- **Fix:** read the raw wire via `StructuredDataREST.fetch_reporting_period_raw`
  (spy the real `cqs/query-chunks` payload first — see
  `escape_hatch_architecture.md`). Note this path **is chunk-billed**. Format is
  mixed: absolute `'2026FY'` + relative `'FQ1'`–`'FQ4'`; `'FQ1'` has no year
  anchor, so reconcile against the same story's `'YYYYFY'` or timestamp.

## 8. Chinese company name → 0 hits

- **Symptom:** `find_companies('贵州茅台')` returns nothing.
- **Root cause:** the data source's Chinese entity layer is empty (not a bug you
  can code around).
- **Fix:** resolve via the **English official name** (`'Kweichow Moutai'`) or
  **ISIN** (`resolve_by_isin(['CNE0000018R8'])`). Same for topics — Chinese
  topic strings (`'人工智能'`) return 0.

## 9. `kg.autosuggest` → `NotImplementedError`

- **Symptom:** interactive autosuggest raises `NotImplementedError`.
- **Root cause:** not implemented in **API-key mode** (same family as `uploads`).
- **Fix:** use the `find_*` resolvers; there is no autosuggest in key mode.

## 10. `403 'Missing Authentication Token'` misread as a permission error

- **Symptom:** a `/v1/*` call returns 403 and you assume your key lacks access.
- **Root cause:** the API Gateway returns this when **there is no route on that
  path** (e.g. you did `GET` where only `POST /query` exists). It is not a
  permission denial; `404` means the path doesn't exist.
- **Fix:** use `POST /v1/<resource>/query` for the business face, `GET` only for
  the platform face (`v1/subscription/quotas`). Confirm unfamiliar paths against
  `docs.bigdata.com/llms.txt`.

## 11. Two response shapes: columnar `{fields, values}` vs flat `[{...}]`

- **Symptom:** `income_statement` / `daily_prices` return `{results: {fields,
  values}}` (or `{results: [{fields, values}]}`), not records — `results[0]["REVENUE"]` fails.
- **Root cause:** financials / prices / dividends / revenue-segments use a
  columnar `{fields, values}` shape; `*_ttm` / `company_profile` are already flat.
- **Fix:** wrap the columnar ones in `fields_values_to_records()` →
  `[{field: value}]` (single-entity results auto-flatten).

## 12. `entity-sentiment` uses a trailing slash, not `/query`

- **Symptom:** `POST v1/entity-sentiment/query` 404s.
- **Root cause:** the path is `v1/entity-sentiment/` (trailing slash), unlike the
  `v1/<x>/query` business-face pattern; body uses `timestamp:{start,end}`, not `date_range`.
- **Fix:** the toolkit's `entity_sentiment()` already uses the right path + shape.

## 13. `connected_entities` (co-mentions) is chunk-billed; the structured endpoints aren't

- **Symptom:** a co-mention call increments chunk usage while financials / prices cost 0.
- **Root cause:** co-mentions runs over the search service (response carries
  `usage.api_query_units`); the structured `/v1/*` endpoints don't bill chunks.
- **Fix:** keep `connected_entities` limits small and budget for it like a search.
