# lark-cli API Extraction (Path A — primary)

The primary, highest-fidelity way to turn a Feishu/Lark source into Markdown. Everything here was verified end-to-end on a real multi-document collection import (lark-cli 1.0.27 and 1.0.32, 2026-05).

## Contents

- Why API over browser
- Step 0: proxy and auth preflight
- Step 1: classify the URL
- Step 2: resolve wiki node → doc token
- Step 3: fetch the body programmatically
- Step 4: spreadsheets
- Step 5: the reference-graph recursion (collections/hubs)
- Step 6: cross-tenant and personal-space sources
- Step 7: frontmatter and provenance
- Command troubleshooting
- What a clean run looks like

## Why API over browser

On real collection work the lark-cli path did the entire job and the browser path was never needed, because the API path:

1. Recurses a hub's reference graph programmatically — a browser cannot "follow" `<mention-doc>` references mechanically.
2. Resolves permission boundaries from exact error codes (`131006`, `99991679`) instead of guessing from a rendered page.
3. Streams the body to disk via `jq`/`cat` so the document text **never passes through the model** (paraphrasing is undetectable later — the core fidelity argument).
4. Does not depend on a browser extension being connected (the in-browser surface frequently fails to connect; an anonymous debugging Chrome cannot read login-walled content anyway).

## Step 0: proxy and auth preflight

```bash
export LARK_CLI_NO_PROXY=1
lark-cli --version          # confirm ≥ 1.0.32 (2026-05); older works but lacks fixes
lark-cli auth status        # must be valid for the target tenant
```

`LARK_CLI_NO_PROXY=1` is mandatory for `*.feishu.cn` (mainland, direct-connect). Without it, lark-cli prints:

```
[lark-cli] [WARN] proxy detected: https_proxy=http://127.0.0.1:1082 — requests
(including credentials) will transit through this proxy. Set LARK_CLI_NO_PROXY=1 to disable proxy.
```

That warning is the signal — credentials would transit the proxy and Feishu's domestic DNS would be hijacked. This is host-specific and does not conflict with rules that force `claude.ai`/`anthropic.com` through a proxy; Feishu is a different, direct host.

## Step 1: classify the URL

| URL shape | Meaning | Action |
|---|---|---|
| `…/wiki/<node_token>` | wiki node (a pointer, **not** a doc) | Step 2 then Step 3 |
| `…/docx/<doc_token>` | doc, already a doc token | Step 3 directly |
| `…/sheets/<sp_token>` | spreadsheet | Step 4 |
| `…/minutes/<minute_token>` | Minutes / 妙记 | see feishu-minutes-transcript.md |
| `…/base/<token>`, `…/file/<token>` | Bitable / file attachment | see reference-graph dispatch (Step 5) |
| `https://<anything>.feishu.cn/docx/…` or `https://my.feishu.cn/docx/…` | cross-tenant / personal space | Step 6 (same fetch, permission is per-doc) |

## Step 2: resolve wiki node → doc token

A wiki `node_token` is a navigation pointer; fetching it as a doc fails. Resolve it:

```bash
lark-cli wiki spaces get_node --params '{"token":"<node_token>"}'
```

Returns `{"code":0,"data":{"node":{"node_token":"…","obj_token":"<DOC_TOKEN>","obj_type":"docx","node_type":"origin","has_child":false,…}}}`.

- Use `.data.node.obj_token` + `.data.node.obj_type` for Step 3.
- `has_child:false` on the entry node does **not** mean "no content" — a collection hub is typically a single docx whose *body* references many other docs (Step 5), not a multi-node wiki tree.
- `code 131006 … node permission denied` → this node is permission-walled; stop and go to Path B (docx-export-to-markdown.md). Do not try to bypass it.

## Step 3: fetch the body programmatically

```bash
lark-cli docs +fetch --doc <obj_token> --format json > /tmp/fetch.json 2> /tmp/fetch.err
jq -r '.data.markdown' /tmp/fetch.json > "<sanitized-title>.md"
```

- `.data.markdown` is clean Markdown with Feishu rich-media tags preserved (resolve them in Step 5).
- **Keep stdout/stderr separate.** `stderr` may carry `[deprecated] docs +fetch with v1 API is deprecated` — harmless. Doing `2>/dev/null | jq` in one pipe produced a spurious `Exit code 5`; redirect to files and inspect instead.
- **Never** reconstruct `.data.markdown` by reading and retyping it. `jq -r` it to disk. This is the fidelity guarantee that makes Path A structurally safer than any browser/LLM path.
- `--format json` is preferred over text so you parse one field deterministically.

## Step 4: spreadsheets

A `<sheet token="<SP>_<SID>"/>` tag (or a `…/sheets/<SP>` URL) carries the spreadsheet token and sheet id joined by `_`. Split on `_`:

```bash
lark-cli sheets +info --spreadsheet-token <SP> \
  --jq '.data.sheets[]? | {sheet_id, title, rowCount: .gridProperties.rowCount, colCount: .gridProperties.columnCount}'

lark-cli sheets +read --spreadsheet-token <SP> --sheet-id <SID> \
  --range A1:AZ200 --value-render-option ToString \
  --jq '.data.valueRange.values'
```

- `--value-render-option ToString` returns plain text cells (formulas/dates rendered), which is what Markdown tables need.
- The result is a 2-D array; render it to a Markdown table. Size the range from `sheets +info` row/col counts; do not blind-guess a tiny range.

## Step 5: the reference-graph recursion (collections/hubs)

A hub is the root of a reference graph. Treat it as BFS/DFS over references until every branch reaches a leaf (a doc with no further references).

**Enumerate references with the bundled extractor** (a missed reference is a missing document — the single biggest hub-scraping failure; do not hand-roll `grep` and forget the `my.feishu.cn` personal-space pattern, which is exactly what happened before this script existed):

```bash
python3 scripts/feishu_extract_refs.py <fetched-body>.md
# → JSON array of {type, token_or_url, title}
```

The references it recognizes (the full rich-media inventory): `<mention-doc token type>`, `<sheet token>`, `<lark-table><lark-tr><lark-td>` (inline tables — render in place, not a reference), `<image token>`, `<view><file>`, cross-tenant `https://<tenant>.feishu.cn/(docx|wiki|sheets|base|file)/<token>`, personal-space `https://my.feishu.cn/docx/<token>`, Minutes `https://<tenant>.feishu.cn/minutes/<token>`, Tencent-Meeting `https://meeting.tencent.com/crm/<id>`.

**Dispatch table:**

| Reference type | Handler |
|---|---|
| `mention-doc` type `docx` / cross-tenant `/docx/` / `my.feishu.cn/docx/` | Step 3 `docs +fetch` |
| `mention-doc` / URL `/wiki/` | Step 2 then Step 3 |
| `sheet` / `/sheets/` | Step 4 |
| `/minutes/` URL | feishu-minutes-transcript.md (native transcript API) |
| `meeting.tencent.com/crm/` | Tencent Meeting tooling (outside this skill — its native transcript API; never download+re-ASR) |
| `<lark-table>` | render inline to a Markdown table (pandas `read_html` handles colspan/rowspan); it is content, not a link |
| `<image token>` | register the token; lark-cli cannot download it (see permission-and-failure-boundaries.md) |
| `<view><file>` | attachment — record token + filename; treat like an image gap unless separately retrievable |

**Recursion loop:** fetch root → extract refs → for each new ref, dispatch and fetch → run the extractor on each newly fetched body → repeat until no new tokens appear. A child doc can itself embed another reference (e.g. a summary doc that embeds a third Minutes link); the loop must re-scan every newly fetched file, not only the root.

**Leaf / completion gate** — before declaring the collection done, no rich-media reference may remain unresolved anywhere:

```bash
grep -rlE '<(lark-table|lark-tr|sheet token=|mention-doc|view type=)' . \
  && echo "UNRESOLVED — keep recursing" || echo "clean"
```

This grep being empty is a hard acceptance gate for collections.

## Step 6: cross-tenant and personal-space sources

`https://<other-tenant>.feishu.cn/docx/…` and `https://my.feishu.cn/docx/…` (personal space) use the **same** `docs +fetch` — Feishu permission is per-document, not per-domain. A reference living in another tenant or someone's personal space is often still readable with the current token. Do not skip a reference just because its host differs; try the fetch and let the error code (`131006` / `0`) decide.

## Step 7: frontmatter and provenance

Each produced file should carry minimal frontmatter so the extraction is auditable and the host PKM can file it (this skill stops at producing it, not filing it):

```yaml
---
title: <document title>
source: <original feishu URL or token>
source_type: docx | wiki | sheet | minutes
extracted: <YYYY-MM-DD>
post_process: <one line if any non-trivial transform was applied; omit if pure jq passthrough>
---
```

`post_process` matters when text was reshaped (e.g. a sheet rendered to a table, or Path B's heading restoration) — it tells a future reader the body is not a byte-for-byte API passthrough.

## Command troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `docs +fetch` "Exit code 5" but data looks present | `2>/dev/null` swallowed stderr while `jq` failed on mixed stream | Redirect stdout/stderr to separate files; parse the file |
| `wiki spaces get_node` → `code 131006` | No read permission on that node | Path B (owner exports docx); do not bypass |
| `api …/transcript` → `code 99991679` | Missing scope | feishu-minutes-transcript.md (device-flow scope grant) |
| lark-cli reports `API returned an empty JSON response body` | lark-cli mis-renders a binary/error HTTP response | Real status is hidden — see permission-and-failure-boundaries.md; do not trust "empty JSON" literally |
| Need an API lark-cli does not wrap | — | `lark-cli api <METHOD> <path> --params '{…}' --as user`; find the spec via `open.feishu.cn/llms-docs/zh-CN/llms-<module>.txt` (the `/document/server-docs/` pages are flaky in WebFetch) |

## What a clean run looks like

Single doc:

```
$ export LARK_CLI_NO_PROXY=1
$ lark-cli wiki spaces get_node --params '{"token":"<node_token>"}'
{"code":0,"data":{"node":{"obj_token":"<DOC>","obj_type":"docx","has_child":false,...}}}
$ lark-cli docs +fetch --doc <DOC> --format json > /tmp/f.json 2> /tmp/f.err
$ jq -r '.data.markdown' /tmp/f.json | wc -c
   6166
$ LC_ALL=C grep -rl $'\xef\xbf\xbd' . ; echo "ffd_count=$?"
ffd_count=1          # 1 = grep found nothing = clean
```

Collection: the same, then N rounds of `feishu_extract_refs.py` → dispatch → fetch, ending with the residual-tag grep printing `clean`.
