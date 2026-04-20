---
name: mcp-listen
description: GENERIC push-to-model pump for ANY Streamable-HTTP MCP server with subscriptions. Opens a session, subscribes to given resource URIs, and emits one JSON line per `notifications/resources/updated` event on stdout — designed to be wrapped by Claude Code's Monitor so every push becomes an in-chat notification (no polling). Use when a user wants to react in real time to remote state changes from an arbitrary MCP server — watched files, remote queues, task runners — even if they don't name MCP/SSE/subscriptions. For cnvs.app boards specifically, use alongside the `cnvs-whiteboard` skill (which owns read/write and delegates push here). Ships `--ignore-author` flags for self-echo filtering on cnvs-shaped payloads (`texts[] / lines[] / images[]` with `author` + `last_updated`); on other resource shapes the skill emits every event unconditionally and the caller filters downstream.
compatibility: Requires Node.js 18+ and npm (run `npm install` inside the skill directory once before first use).
license: MIT
metadata:
  author: cnvs.app
  version: "0.2.0"
  homepage: https://cnvs.app/mcp-listen/
---

# mcp-listen

Minimal MCP notification pump. Opens a Streamable-HTTP session against an MCP server, subscribes to one or more resource URIs, and emits one JSON line per `notifications/resources/updated` event on stdout. Designed to be wrapped by Claude Code's `Monitor` tool so each event becomes a real-time notification to the model — no polling, no manual log tailing.

## When to use

Any time the user wants the model to "react to X on Y MCP server the moment it happens" — collaborative whiteboards (cnvs.app), file watchers, remote state changes, anything that advertises `capabilities.resources.subscribe: true`. If the server is available over Streamable HTTP (`POST /mcp` + `GET /mcp` SSE), this skill works without any server-side changes.

## Setup (first run only)

```bash
cd ~/.claude/skills/mcp-listen
npm install --silent
```

## Usage via Monitor

Pattern for Claude Code:

```
Monitor(
  command: "node ~/.claude/skills/mcp-listen/scripts/listen.mjs [--ignore-author <tag>]... <mcp-url> <resource-uri> [<uri> ...]",
  description: "watching <short name> for <event>",
  persistent: true
)
```

### Self-echo filter (opt-in, **cnvs-shaped payloads only**)

MCP subscriptions notify *every* subscriber — including the one whose write triggered the push. For a listener that ALSO writes to the same board, every one of its own writes would otherwise wake it as a notification, creating a feedback loop.

**Important limitation up front.** The filter is only applied when the target server returns snapshots shaped like cnvs.app (`texts[] / lines[] / images[]` each with `author` + `last_updated`). For any other MCP server the filter **silently no-ops** — every event is emitted unconditionally and the caller is responsible for filtering downstream. The flags still accept input (they don't error), but they have no effect on non-cnvs shapes.

Two flags opt into filtering (cnvs-shaped payloads):
- `--ignore-author <tag>` — exact match, repeatable. Pass the caller's own author tag (e.g. `ai:claude` for Claude Code, `ai:gpt` for a GPT-based agent, `user:xyz` for a specific human).
- `--ignore-author-prefix <prefix>` — prefix match, repeatable. `--ignore-author-prefix ai:` mutes every AI collaborator, useful when a human is driving and only wants to see human edits.

**No default** — the skill can't guess what tag the caller writes under. Pass explicitly. Both flags accept `""` (empty string) which no-ops, so wrapper scripts can safely inject a blank value when the feature isn't needed.

On each `resources/updated` (for cnvs-shaped snapshots) the skill does one `resources/read`, picks the latest-touched item across `texts`/`lines`/`images`, and if its `author` matches any rule it suppresses the notification.

Each emitted event carries a `trigger` block so the model sees *who* caused the push without a second fetch:

```json
{"ts":"...","event":"connected","mcpUrl":"https://cnvs.app/mcp","ignoreAuthors":["ai:claude"]}
{"ts":"...","event":"subscribed","uri":"cnvs://board/<id>/state.json"}
{"ts":"...","event":"resource_updated","uri":"cnvs://board/<id>/state.json",
  "trigger":{"id":"31c081fb","author":"user:658ebc2c","kind":"text","last_updated":"2026-04-14 21:08:02"}}
```

Writes authored by ignored tags produce no output — the model is never woken for its own echoes (cnvs-shaped snapshots only; see limitation above).

## What to do on each notification

`event: "resource_updated"` is the trigger for action. Fetch the fresh state via whatever read tool/endpoint the target exposes (`resources/read` over MCP, or an HTTP equivalent) and react. The subscription is debounced server-side when the server implements bursts-to-one aggregation (cnvs.app does ~3 s), so one notification may cover multiple near-simultaneous edits.

## Reconnection

On transport error or close the script waits with exponential backoff (1 s → 30 s cap) and re-subscribes. Every reconnect emits a fresh `connected` + `subscribed` line so the chat trail stays honest about what happened.

## Gotchas

- **Monitor exits immediately after `connected` / `subscribed`.** Node had no active handles keeping it alive; the SDK's SSE connection alone isn't always enough. The script uses an explicit heartbeat `setInterval` as keep-alive — don't remove it.
- **Subscribe succeeds but no `resource_updated` ever arrives.** The server is returning `204 No Content` instead of `202 Accepted` for `notifications/initialized`. The official MCP SDK opens its SSE channel only on `202`. Probe: `curl -X POST <server>/mcp -d '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' -v 2>&1 | grep '^< HTTP'` → should show `202`.
- **Feedback loop: your own writes wake the listener.** You forgot `--ignore-author <your-tag>` (or the prefix variant). Add it.
- **Works for any Streamable-HTTP MCP server with subscriptions** — not just cnvs.app. The cnvs-shaped `trigger` extraction falls through on non-board payloads and emits every event unfiltered.

## Limits

- One process per server. If you need to watch two different MCP servers, spawn two Monitors.
- Relies on the server correctly implementing MCP resource subscriptions. Inspect with `npx @modelcontextprotocol/inspector <url>` first if unsure.
- Dies with the Claude Code session. For longer watches use cron jobs or a real systemd/launchd unit.

## Related skills

- **cnvs-whiteboard** ([install](https://cnvs.app/cnvs-whiteboard/SKILL.md)) — complementary skill that teaches the agent how to read from and write to a cnvs.app whiteboard over REST. Pair the two when the remote state you're watching *is* a cnvs.app board: this skill gives you the push channel, cnvs-whiteboard gives you the mutation and render pipeline.
