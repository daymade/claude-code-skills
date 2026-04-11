# Search Best Practices — Deep Dive

This document is the reference for Capability 4 (fan-out search with personalization). Read it when the user asks about how to search, reports weird search results, or wants to tune the `copilot.json` configuration.

## The three hard constraints of the IMA search API

Any search workflow on top of IMA has to account for these three constraints. They are not documented by upstream; they were discovered by observation.

### 1. No cross-knowledge-base endpoint

`search_knowledge` requires `knowledge_base_id` to be set. There is no endpoint that searches across all KBs at once. The only way to find content in all your KBs is a client-side fan-out: enumerate your KBs first, then call `search_knowledge` once per KB.

### 2. No relevance score in the response

A hit object looks like this:

```json
{
  "media_id": "wechatarticle_…",
  "title": "…",
  "parent_folder_id": "…",
  "highlight_content": "…",
  "media_type": 6
}
```

That's it. No similarity score, no BM25 rank, no recency weight, nothing that lets a client know "this hit is more relevant than that hit". Hits come back in an undocumented order that is believed to be insertion-order or last-modified order, but it cannot be trusted as a relevance ranking.

**Consequence**: any ranking beyond "here are the hits the server returned in the order it returned them" must be invented by the client. This wrapper does not attempt cross-KB relevance ranking — it only groups by KB with user-declared priority.

### 3. Silent 100-result truncation

`search_knowledge` returns at most 100 hits per call. When the query saturates a KB, the response comes back with `info_list` of length exactly 100 and **no** `is_end` or `next_cursor` field. The API documentation mentions a `cursor` parameter in the request, but the server does not emit a cursor in the response, so pagination is impossible in practice.

High-frequency queries against large KBs (e.g., searching "AI" across a 25,000-entry KB) return the "first 100" without any indication that more exist.

**Detection rule**: a response with exactly 100 hits and no `is_end`/`next_cursor` is treated as truncated. `search_fanout.py` uses this rule and surfaces a warning listing the truncated KBs.

**Mitigation**: the only workaround is to narrow the query — add a second term, a phrase match, or a distinctive keyword that reduces the candidate set below 100 per KB.

## Permission model: subscribed KBs return 'no permission'

Empirically, the IMA OpenAPI search endpoints only work on KBs the user **created themselves**. KBs the user subscribed to (e.g., public curated libraries, friends' shared knowledge bases) enumerate successfully via `search_knowledge_base` (so they show up in the fan-out target list) but return `code: 220030, msg: 没有权限` when hit with `search_knowledge`.

This is not configurable on the client side — it is a server-side entitlement check tied to KB ownership.

**Consequence for the wrapper**:
- Do not hide denied KBs from the fan-out call list entirely — the user needs to know which ones they could search if they forked a copy.
- Do not render denied KBs in the main results area — they are noise that drowns out real hits.
- Collect them in a separate "ℹ️ subscribed KBs (no search permission)" block at the end of the output.

`search_fanout.py` implements this partitioning in its `rank_groups()` function using the `220030` error code as the partition key.

## The fan-out strategy

```
load credentials
load ~/.config/ima/copilot.json  (optional)
enumerate all KBs via search_knowledge_base("")
filter out KBs in skip_kbs
fan out search_knowledge to the remainder, in parallel (default 12 workers)
partition results into: priority | others | denied | empty
render:
  priority group first, in user-declared order
  others group next, sorted by hit count descending
  summary line
  denied group at the bottom (as an ℹ️ note, not a result)
  truncated warning (if any)
```

Every step after credential load is stateless — rerunning the script with the same query produces the same output, modulo rare eventual-consistency windows on newly added content.

## The `copilot.json` configuration file

Location: `~/.config/ima/copilot.json`. Override with `IMA_COPILOT_CONFIG=<path>` environment variable (primarily used by tests).

Shape:

```json
{
  "priority_kbs": ["kb name 1", "kb name 2"],
  "skip_kbs":     ["kb name 3"],
  "fanout_strategy": "parallel-then-merge"
}
```

### `priority_kbs` (list of strings)

KB names that should be surfaced at the top of every search. Order within the list is preserved — the first entry becomes the first priority group, the second becomes the second, and so on. KBs that appear here but have no hits for the current query are silently omitted from the priority section.

**Intent**: surface the user's trusted / curated / high-signal KBs ahead of noisy or exploratory ones. A good rule of thumb is "KBs I've personally vetted" in priority, "KBs I added but haven't fully read" in unranked others.

**Naming**: must match the KB name exactly, including spacing and Unicode. If the user's config uses a name that no KB has, it is silently ignored.

### `skip_kbs` (list of strings)

KB names to exclude from the fan-out entirely. They are not searched, they don't appear in the denied block, they don't appear in the results. They *are* counted in the "Searched across N knowledge bases" header along with a `skipped via config: …` line.

**Intent 1 — strict subsets**: if KB B is a strict subset of KB A (every document in B also appears in A), searching both produces duplicate hits. Skipping B eliminates the duplication without losing any content.

**Intent 2 — off-topic noise**: some KBs never contain anything relevant to the user's searches (e.g., a parked KB they created for a different project). Skipping saves a round trip and reduces output clutter.

### `fanout_strategy` (string, reserved)

Currently only `"parallel-then-merge"` is implemented. The field is kept in the schema for forward compatibility.

## Evidence-based subset detection

Before adding a KB to `skip_kbs` as a strict subset of another, verify the subset relationship with multiple queries. Relying on hit counts alone is unsafe because of the 100-hit truncation: a KB that returns 100 hits on query X with 30 "independent" titles may actually be a strict subset, with the difference being a truncation artifact rather than real extra content.

**Verification procedure**:

1. Pick 2–3 queries expected to return strictly less than 100 hits in both KBs. "RAG", "MCP", "embedding" are good candidates for technical KBs — narrow enough to avoid truncation, common enough to return non-trivial result sets.
2. For each query, run the two KBs separately via `search_knowledge` and collect the set of `title` values from each.
3. Compute `set(B) - set(A)`. If this is consistently empty across all queries, B is (probably) a subset of A. If any difference persists, they are not in a subset relationship.
4. If truncated results show up (exactly 100 hits), discard that query — the set difference will be a truncation artifact, not a real content difference.

The rationale is that querying at most ~100 hits is cheap (3–4 API calls) and any genuine subset relationship will be visible with just a few narrow queries, whereas high-frequency queries will mislead. See the conversation history around this skill's creation for a worked example on the `personal-kb` vs `master-kb` pair.

## Rendering details

Text mode (the default):

- Each KB group is a header line with an emoji (`🥇` for priority, `📚` for others) and a hit count.
- The first `--max-results` hits per KB are listed with title and highlight snippet (truncated to 120 chars).
- "N more" is printed if hits exceed the limit.
- A separator line precedes the summary.
- The summary shows total hits and total KBs with results.
- Denied KBs are printed as an `ℹ️` block at the bottom so they never drown out real results.
- Truncated KBs are printed as a `⚠️` block with guidance to narrow the query.

JSON mode (`--json`): emits `{priority, others, denied, skipped_by_config}` arrays with full hit metadata for downstream tools.

## When the agent should use this capability

Trigger on explicit search intents:
- "搜一下 XXX"
- "search for XXX in my IMA notes"
- "find articles about XXX"
- "在 ima 里搜 XXX"
- "知识库里有没有 XXX"

Also trigger on implicit intents when the user is asking a question whose answer the user is likely to have previously saved to their knowledge base:
- "what was that RAG framework the author of the HyDE paper mentioned?"
- "I read something last month about Qwen3 fine-tuning, what was the key takeaway?"

For these, run a fan-out search first with the key nouns, show the top priority-group hits, and let the user ask follow-ups based on what's returned.

## When the agent should refuse

Refuse (or at least suggest alternatives) when the user asks to:
- Fuzzy-search across all KBs with a single vague word — this will likely truncate and give poor results. Suggest narrower queries first.
- Rank results by recency — the API doesn't return timestamps; any such ranking would be a lie.
- Deduplicate across KBs by semantic similarity — the hits only carry titles and snippets; full deduplication needs a separate embedding step that this skill does not implement.
