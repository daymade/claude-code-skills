# Why the Bigdata MCP is lossy, and how the REST escape hatch works

The whole reason this skill exists: the MCP server is not the API. Understanding
the layering tells you exactly where the missing data went and how to get it.

## The layers

| Layer | What it is | What it gives you |
|---|---|---|
| **MCP server** | A chat-optimized wrapper | Readable prose + pre-synthesized tearsheets (incl. an aggregate sentiment score and an estimates summary). **Does not expose** numeric per-chunk sentiment, entity character-spans, fiscal-period time series, per-field JSON, or a universe screener. |
| **SDK** (`bigdata_client.Bigdata`) | Official Python client | High-level `search`, `knowledge_graph`, `subscription`, `chat`, `watchlists`, `uploads`. |
| **`bd._api`** (`BigdataConnection`) | The SDK's own transport | Holds `bd._api.http`, a `RateLimitedHTTPWrapper` with `api_url='https://api.bigdata.com/'`, carrying the JWT auth + proxy already. |
| **`/v1/*` REST** | Official, publicly documented structured API (`docs.bigdata.com/api-reference`) — the SDK's **migration target** (SDK EOL 2026-12-31) | estimates, events-calendar, surprise, ratings, price/target, screener, **full financials, prices, dividends, revenue segments, daily entity-sentiment**, subscription/quotas. **No SDK high-level method wraps these** — but the same backend + same JWT serves them, and they outlive the SDK. |

The MCP and the SDK talk to the same backend. The MCP hands you synthesized
output (prose, tearsheets), not the structured substrate underneath; the SDK's
own `bd._api.http` reaches the `/v1/*` endpoints that hold it.

> **These `/v1/*` endpoints are official and publicly documented — not a hidden
> backend.** And Bigdata is sunsetting the SDK (EOL **2026-12-31**; the
> SDK-underlying endpoints are to be decommissioned) in favour of this REST API,
> so leaning on `bd._api.http` / REST here is the *forward-compatible* path, not
> a hack. The SDK-only pieces (`kg`, SDK `search`) are the parts with a shelf life.

## The evidence chain (runtime L4 — not doc inference)

- `bd._api` is a `bigdata_client.connection.BigdataConnection`.
- It holds `bd._api.http` (`RateLimitedHTTPWrapper`), `api_url='https://api.bigdata.com/'`.
- Every SDK high-level method (`query_chunks`, `by_ids`, `autosuggest`,
  `get_my_quota`, …) internally delegates to `self.http.post(endpoint, json=…)`
  / `self.http.get(endpoint, params=…)`.
- Therefore hitting an endpoint the SDK never wrapped is just: call
  `self.http.<verb>(relative_path, …)` yourself. The toolkit exposes this as
  `BigdataClient.http` (and `.conn` for `bd._api`).

## The HTTP wrapper signature (runtime-confirmed)

```text
http.get(endpoint: str, params: dict = None) -> dict | list
http.post(endpoint: str, json: dict | list[dict]) -> dict | list
http.put / http.patch / http.delete
http.get_chunks(endpoint, chunk_size) -> Iterable[bytes]
http.async_get([...]) -> concurrent GET
```

`endpoint` is a **relative path** (e.g. `"v1/events-calendar/query"`); the
wrapper does `urljoin(api_url, endpoint)`. Absolute URLs also work.

## Route-shape rules (where hours get wasted)

- **Business face is `POST /v1/<resource>/query`.** A bare `GET /v1/<resource>`
  returns **404** — there is no GET route.
- **Platform face is `GET`** — e.g. `GET v1/subscription/quotas`.
- **`403 'Missing Authentication Token'` means the API Gateway has no route on
  that path — it is NOT a permission denial.** `404` means the path doesn't
  exist at all. Don't read 403 as "my key lacks access".
- Confirm an unfamiliar path against `docs.bigdata.com/llms.txt` before
  guessing. Guessing burns time on 403/404 ambiguity.

## Wrapping a new `/v1/*` endpoint

1. **Introspect** what the SDK already does so you copy its delegation shape:

   ```python
   print(client.introspect_conn())   # lists bd._api methods + source head
   ```

2. **Ad hoc call** through the escape hatch:

   ```python
   resp = client.http.post(
       "v1/some-new-resource/query",
       {"identifier": {"type": "rp_entity_id", "value": "E09E2B"}},
   )
   quotas = client.http.get("v1/subscription/quotas")     # platform GET
   ```

3. **Field present on the wire but dropped by the SDK model?** (`reporting_period`
   is the canonical case — it's ~75% populated on filings over REST, but the
   SDK's `ChunkedDocumentResponse` model omits it, so `Document.reporting_period`
   is always `None`.) Spy the real payload the SDK sends, then replay it raw:

   ```python
   orig = client.http.post
   captured = {}
   def spy(endpoint, json):
       if endpoint == "cqs/query-chunks":
           captured["payload"] = json
       return orig(endpoint, json)
   client.http.post = spy
   searcher.search_entity("E09E2B", keyword="revenue", chunk_limit=5)  # trigger once
   # captured["payload"] is the real schema → adapt → rest.fetch_reporting_period_raw(...)
   ```

Once you've confirmed a new endpoint works, add a thin method to
`rest_ext.py` so the next caller doesn't rediscover it — that is how the toolkit
grew. Keep returning **raw dict/list** for half-documented endpoints; their
schema can drift, so let the caller defend.

## The bottom line

`MCP gave you less than the API has` is the trigger. `bd._api.http` over the
same JWT is the answer. Everything in `rest_ext.py` is just named, verified
shortcuts onto that one escape hatch.
