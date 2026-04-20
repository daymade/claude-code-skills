---
name: cnvs-whiteboard
description: PRIMARY skill for any cnvs.app board work. Collaborate on a cnvs.app whiteboard (canvas / board / drawing surface) in real time — read shared state, add/update/move/delete text, links, sticky notes, strokes, images, and Mermaid diagrams (flowcharts, sequence diagrams, class and ER diagrams, mind maps, gantt charts, concept maps, and more), and render the SVG preview when the board has drawings. Use whenever the user references a cnvs.app board (URL `https://cnvs.app/#<id>`, `cnvs://board/<id>/...`, or `/mcp` endpoint), asks to draw / sketch / diagram / flowchart / annotate / brainstorm / collaborate / edit / watch / create content on a shared whiteboard or canvas, or drops a board ID expecting the agent to act on it — even if they don't name cnvs.app, MCP, or REST. For push-to-model notifications on human edits this skill delegates to the generic `mcp-listen` skill; install both for the full loop.
compatibility: Requires outbound HTTPS access to https://cnvs.app. MCP subscriptions need a Streamable-HTTP MCP client (Claude Code, Claude Desktop, Cursor, OpenCode, Aider with MCP plugin, etc.). Writes work from any runtime via plain REST — no MCP client required.
license: MIT
metadata:
  author: cnvs.app
  version: "1.0.0"
  homepage: https://cnvs.app/cnvs-whiteboard/
  board_url_pattern: "https://cnvs.app/#<boardId>"
---

# cnvs-whiteboard

Be a live AI collaborator on a cnvs.app board — discover changes, make edits, stay in the loop without polling, and don't wake yourself on your own writes. One skill, copy-pasteable patterns.

> **If you only read one thing.** Listen for edits via MCP subscriptions (the only real-time push channel). Act on the board via the REST API (universal — works from any runtime with outbound HTTP, no MCP client required). Don't use MCP tool-calls for writes if REST is available: it wastes tool-call slots, adds session bookkeeping, and blocks every non-MCP agent runtime from ever contributing. The hybrid **MCP-listen + REST-write** loop is what this skill wires up.

## How to use this skill

Each time you receive a board ID (or URL), run through this checklist:

1. [ ] **Set your author tag.** Pick an `ai:<label>` (e.g. `ai:claude`, `ai:gpt4`, `ai:myagent`). Pass it on every mutation. It becomes immutable.
2. [ ] **Read the current snapshot.** `GET https://cnvs.app/json/<id>` (keep the returned `ETag`).
3. [ ] **View the SVG preview** if the board contains lines or images (see §1.4). Numbers alone won't tell you what a stroke actually depicts.
4. [ ] **Listen for changes** (optional, push-driven): install the `mcp-listen` skill and wire `cnvs://board/<id>/state.json` through `Monitor` with `--ignore-author-prefix ai:`.
5. [ ] **React** — re-read snapshot on every push (send `If-None-Match` to skip no-op pushes), then mutate via REST.

## TL;DR flow

```
┌──────────────────────┐        ┌──────────────────────────┐
│ mcp-listen skill     │        │ your agent logic         │
│ (MCP SDK + Monitor)  │── push ▶│ refresh, decide, respond │
└──────────────────────┘        └──────────────┬───────────┘
          ▲                                     │
          │ notifications/resources/updated     │
          │ (SSE, ~3 s debounced)               │ HTTP
          │                                     ▼
┌─────────┴────────────────────────────────────────────────┐
│                    cnvs.app server                        │
│  POST /mcp (subscribe, read)   POST /api/boards/... (mutate)
└──────────────────────────────────────────────────────────┘
```

1. **Subscribe** once to `cnvs://board/<id>/state.json` over MCP — server pushes an event within ~3 s of every edit.
2. **React** via REST — `POST /api/boards/<id>/texts` (and siblings) for create/update, `/move` for reposition, `DELETE` for erase.
3. **Filter self-echoes** with `--ignore-author-prefix "ai:"` so your own writes don't wake the listener.

## Why this split

| need | use | why |
|---|---|---|
| real-time awareness of human edits | **MCP subscriptions** | the only push channel; REST has no webhook |
| making edits | **REST API** | universal (any HTTP client), stateless, mirrors every MCP tool 1:1, doesn't burn the model's per-turn tool-call budget |
| client runtime can't speak MCP | **REST for everything** | fallback: read with `GET /json/<id>` (ETag-aware) + poll with `GET /wait` long-poll |

MCP-for-writes is legitimate but strictly slower per cycle (JSON-RPC envelope + session header + tool-call slot per mutation), AND it requires an MCP-capable client. REST requires nothing but outbound HTTPS.

## Part 1 — Listen via MCP (push-to-model)

### 1.1 Install the `mcp-listen` skill

This skill doesn't bundle the listener itself — installation is a one-liner from its own canonical location:

```bash
mkdir -p ~/.claude/skills/mcp-listen
cd       ~/.claude/skills/mcp-listen
curl -O https://cnvs.app/mcp-listen/SKILL.md \
     -O https://cnvs.app/mcp-listen/package.json \
     --create-dirs -o scripts/listen.mjs https://cnvs.app/mcp-listen/scripts/listen.mjs
npm install --silent
```

No global install, no daemons. The skill lives under your user dir and only runs when Claude Code spawns it. Full details: `https://cnvs.app/mcp-listen/SKILL.md`.

### 1.2 Wire it through Claude Code's `Monitor`

```
Monitor(
  description: "cnvs.app board <id> — human edits only",
  persistent: true,
  command: "node ~/.claude/skills/mcp-listen/scripts/listen.mjs \
              --ignore-author-prefix 'ai:' \
              https://cnvs.app/mcp \
              cnvs://board/<id>/state.json \
              2>&1 | grep --line-buffered -E '\"event\":\"(resource_updated|error|disconnected)\"'"
)
```

Every stdout line from the listener becomes a separate in-chat notification that triggers a fresh model turn. No polling.

### 1.3 What you receive per edit

```json
{
  "ts": "2026-04-14T21:08:05.105Z",
  "event": "resource_updated",
  "uri": "cnvs://board/<id>/state.json",
  "trigger": {
    "id": "31c081fb",
    "author": "user:658ebc2c",
    "kind": "text",
    "last_updated": "2026-04-14 21:08:02"
  }
}
```

The `trigger` block names the latest-touched item so you know WHO edited WHAT KIND of item without a second fetch.

### 1.4 ALWAYS look at the preview, not just the JSON

**Critical pattern.** When the trigger is `kind: "line"` or `kind: "image"`, the JSON snapshot gives you *numbers* (point arrays, bounding boxes, image dimensions). A multimodal model reasoning about numbers can tell "a 47-point red stroke in bbox (323,1771)-(585,2066)" but has no idea whether that's **a heart, a lightning bolt, a signature, or illegible scribbling**. The human drew something *for you to see*; seeing only coordinates is functionally blindness.

On every `resource_updated` where the trigger is `line` or `image` (or when a `text` contains Mermaid source you'd otherwise render mentally), fetch `/svg-preview/<id>` and *view the image*:

```bash
curl -s "https://cnvs.app/svg-preview/<id>" -o /tmp/board.svg
# If you have rsvg-convert / ImageMagick / similar, rasterise for a multimodal read:
rsvg-convert -w 1600 /tmp/board.svg -o /tmp/board.png
# Then open /tmp/board.png with your image-reading tool of choice.
```

For runtimes without local SVG rasterisation: the raw SVG is consumable as `image/svg+xml` by modern multimodal models directly, and the preview embeds tiny thumbnails for pasted images so the SVG itself carries all the visual context — no extra fetch of the full base64 `dataUrl` needed.

For `kind: "text"` triggers without Mermaid, the JSON `content` field has everything — no preview needed. But when in doubt, one extra `/svg-preview` fetch is cheaper than misinterpreting the edit.

### 1.5 Fallback when MCP is unavailable

If your runtime can't load MCP clients at all, use **REST long-poll** instead:

```bash
# Blocks until the next debounced edit burst or 25 s timeout.
curl -s "https://cnvs.app/api/boards/<id>/wait?timeout_ms=25000"
# → {"boardId":"...","updated":true,"timedOut":false,"etag":"W/\"<id>-<ts>-<counts>\""}
```

Burns one rate-limit slot per call. Chain repeatedly. Less efficient than MCP push (one request in flight vs continuous SSE) but completely portable.

## Part 2 — Act via REST

Full API reference is in [`/llms.txt`](https://cnvs.app/llms.txt) (text, LLM-friendly) and [`/openapi.json`](https://cnvs.app/openapi.json) (OpenAPI 3.1, machine-readable). This section shows the typical "I received a push, time to react" round-trip. For request / response schemas of every endpoint, the two authoritative docs above.

### 2.1 Re-read the snapshot after a push (ETag-aware)

```bash
# Initial fetch — keep the returned ETag.
curl -si https://cnvs.app/json/<id> | sed -n '/^etag:/p;/^$/q'

# Follow-up on the next push — 304 if nothing actually changed.
curl -si -H 'If-None-Match: W/"<boardId>-<ts>-<counts>"' https://cnvs.app/json/<id>
```

### 2.2 Canonical mutation shape

```bash
# One representative example; every endpoint follows the same shape.
curl -s -X POST https://cnvs.app/api/boards/<id>/texts \
  -H 'Content-Type: application/json' \
  -d '{"x":100,"y":200,"content":"# Hello","postit":true,"author":"ai:myagent"}'
```

Every endpoint — `/texts`, `/links`, `/strokes`, `/images`, `/{kind}/{id}/move`, `DELETE /{kind}/{id}` — returns a small JSON echo with at least `id` and `author`. Full request/response schemas + all variations (mermaid content, flat point arrays, data-URL images, move semantics per kind) are in [`/llms.txt`](https://cnvs.app/llms.txt) and [`/openapi.json`](https://cnvs.app/openapi.json).

## Gotchas

These are the non-obvious facts that will trip the agent if they're not stated up front:

- **Author tags are IMMUTABLE** after creation. `author = creator`, forever. A move/edit by another collaborator only advances `last_updated`. Use this for reliable self-filtering and attribution.
- **Ink colors are a fixed five-name palette** (`auto` / `black` / `red` / `blue` / `green`, case-insensitive). Custom hex codes sent through the API / MCP silently clamp to `auto` (`var(--text-color)`) — this keeps AI writes visible across light and dark themes. **Pass a name, not an RGB value.**
- **Default author on REST mutations is `ai:rest`** if you don't pass `author`. To claim attribution cleanly, always pass `author: "ai:<your-name>"`.
- **Rate limit**: 60 req / 10 s per board. REST + MCP share a Worker-isolate-local bucket; WebSockets get a separate per-board Durable-Object bucket. 429 carries `Retry-After`.
- **Per-board quotas**: 500 texts (100 k chars each), 50 images (900 kB each, 10 MB total), 2000 strokes. 413 response names the specific `kind` in its body.
- **Debounce**: notifications aggregate bursts into one event ~3 s after activity settles. One push may cover many edits — always re-fetch the full snapshot after a trigger.
- **CORS**: `*` on every public endpoint. No preflight surprises from browser runtimes.
- **Validation errors** return `{code:"invalid_payload", field, reason}` with HTTP 400 — `field` names the exact offender. Parse it, don't retry blindly.
- **Image paste caveat**: `dataUrl` must be under 900 kB and `thumbDataUrl` (if sent) must be PNG/JPEG/WebP, NOT SVG. 413 with `kind:"image_bytes_per_item"` if you exceed.

## Part 3 — Minimal end-to-end pseudocode

```
// one-time
install_skill("mcp-listen")
MCP_LISTENER = spawn_monitor([
  "node", "~/.claude/skills/mcp-listen/scripts/listen.mjs",
  "--ignore-author-prefix", "ai:",
  "https://cnvs.app/mcp",
  f"cnvs://board/{BOARD_ID}/state.json",
])

// event loop — each notification re-invokes the model
on_notification(event):
  if event.trigger.author.startswith("ai:"): return  // extra belt — listener already filters
  snapshot = GET(f"/json/{BOARD_ID}", headers={"If-None-Match": last_etag})
  if snapshot.status == 304: return
  last_etag = snapshot.headers["ETag"]
  decision = reason_about(snapshot.body, event.trigger)
  for mutation in decision.mutations:
    POST(f"/api/boards/{BOARD_ID}/{mutation.kind}", json=mutation.payload, headers={"Content-Type": "application/json"})
```

## Live machine-readable docs

Always consult these before inventing endpoint shapes or limits:

- [`/llms.txt`](https://cnvs.app/llms.txt) — LLM-friendly human-readable reference (full API surface).
- [`/openapi.json`](https://cnvs.app/openapi.json) — OpenAPI 3.1, machine-readable.
- [`/quotas.json`](https://cnvs.app/quotas.json) — live limits manifest; parse this instead of hardcoding.
- [`/.well-known/mcp.json`](https://cnvs.app/.well-known/mcp.json) — MCP discovery metadata.
- [`/.well-known/mcp/server.json`](https://cnvs.app/.well-known/mcp/server.json) — MCP Registry server entry.

## Related skills

- **mcp-listen** ([install](https://cnvs.app/mcp-listen/SKILL.md)) — the push-to-model listener this skill depends on for real-time awareness. Generic: works for any Streamable-HTTP MCP server with subscriptions, not just cnvs.app.

## Troubleshooting

- **413 on a legit-looking image upload.** Check the error body — `field` names the offending parameter. Common causes: `dataUrl` exceeds 900 kB, or `thumbDataUrl` is SVG (must be PNG/JPEG/WebP).
- **429 out of nowhere on an idle board.** You're probably polling `/json` in a tight loop. Either switch to the `mcp-listen` skill (0 polls) or use `GET /wait` (one call per cycle).
- **Ink I wrote shows black instead of the color I asked for.** You passed an RGB/hex value. Use a color *name* from the palette (`auto`/`black`/`red`/`blue`/`green`).
- **My writes wake my own listener.** Add `--ignore-author <your-tag>` or `--ignore-author-prefix ai:` to the Monitor command.
