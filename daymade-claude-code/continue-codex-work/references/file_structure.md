# Codex CLI Session File Structure

Reference for the on-disk format the `extract_codex_resume.py` script parses.
Verified against real rollouts from Codex CLI `0.144.4` (July 2026).

## Directory layout

```
~/.codex/                                  # CODEX_HOME (override with $CODEX_HOME)
├── sessions/
│   └── YYYY/MM/DD/
│       └── rollout-<ISO8601>-<uuid>.jsonl # one file per session; the uuid is the session id
├── archived_sessions/                     # same shape, archived sessions
├── sqlite/  or  ./                        # state_*.sqlite index (schema drifts between versions)
├── session_index.jsonl                    # optional id -> thread_name title map
└── AGENTS.md                              # project/global standing instructions (re-injected into rollouts)
```

The session id is a UUIDv7 embedded in the rollout filename and repeated inside the `session_meta` record. The optional `state_*.sqlite` `threads` table indexes sessions (id, cwd, title, timestamps, `rollout_path`); the shared `_core.codex` reader prefers it and falls back to scanning rollout files directly when it is missing or its schema has changed.

## Rollout JSONL — record schema

Every line is one JSON object with a top-level `timestamp`, `type`, and (usually) `payload`. The `payload.type` further discriminates `event_msg` and `response_item` records. Approximate frequency in a real 1100-line session is shown to indicate what dominates.

| `type` | `payload.type` | Carries | Used for |
|--------|----------------|---------|----------|
| `session_meta` | — | `id`, `cwd`, `timestamp`, `cli_version`, `model_provider` | Session Info header |
| `compacted` | — | `message` (often empty), `replacement_history` (list of messages), `window_number` | Compact Summary |
| `event_msg` | `context_compacted` | just a marker | (the real content is in the `compacted` record) |
| `event_msg` | `user_message` | `message` (plain string) | Last User Requests |
| `event_msg` | `agent_message` | `message` (plain string) | Last Assistant Responses |
| `event_msg` | `patch_apply_end` | `changes` (map: path -> {content\|unified_diff}), `success`, `stderr` | Files Edited; errors |
| `event_msg` | `task_complete` | `last_agent_message`, `duration_ms` | Assistant text; turn boundary → end reason |
| `event_msg` | `token_count` | usage counters | ignored (noise) |
| `response_item` | `message` | `role` (developer/user/assistant), `content` (list) | see note below |
| `response_item` | `reasoning` | model thinking | ignored (noise) |
| `response_item` | `function_call` | `name`, `arguments` (JSON string), `call_id` | Recent Tool Calls |
| `response_item` | `function_call_output` | `call_id`, `output` (list) | pairs a call; error detection |
| `response_item` | `custom_tool_call` | `name` (e.g. `exec`), `input`, `call_id`, `status` | Recent Tool Calls |
| `response_item` | `custom_tool_call_output` | `call_id`, `output` (list) | pairs a call; error detection |

### Message content element types (important)

`response_item/message` `content` is a list of `{type, text}` where `type` is **`input_text`** for user/developer content and **`output_text`** for assistant content. The shared `extract_text` decodes `text`/`input_text` but **not** `output_text`. That is why the parser reads user/assistant turns from the `event_msg` stream (`user_message` / `agent_message` / `task_complete.last_agent_message`, all plain strings) instead of from `response_item/message` — the event stream mirrors the same turns without the `output_text` gap, and avoids double-counting. Tool `output` and compaction `content` use `input_text`, which `extract_text` handles.

## Compaction format

When Codex compacts, it emits a `compacted` record whose `replacement_history` is the list of messages that **replace** the compacted window — not a single distilled summary like Claude Code. That history also re-injects the system preamble. In one real record the 13 items were:

- items with `role: "user"` — the surviving user requests (high signal)
- items with `role: "developer"` — the permissions block, the agent-role message, `<multi_agent_mode>` (system noise)
- a `role: "user"` item whose content is `# AGENTS.md instructions for <cwd>` (~50 KB) — re-injected standing instructions, not a real turn (noise)

So the parser keeps only `role` in `{user, assistant}` **and** drops anything `is_noise_text` recognizes (`<permissions instructions`, `<system-reminder`, `# AGENTS.md instructions for`, …), then truncates each surviving item. The result is the real request thread, without the harness scaffolding.

## Session end reason

Derived from the tail of the rollout and the set of unpaired tool calls:

- **completed** — the last significant record is `task_complete` or `agent_message` (the agent had the last word).
- **interrupted** — a `function_call`/`custom_tool_call` has no matching `*_output` (dispatched but never returned).
- **in_progress** — tools ran and returned, but there is no closing `agent_message`/`task_complete` (cut off mid-task). This is the common resume case.
- **abandoned** — the last significant record is a `user_message` with no response.
- **error_cascade** — three or more tool failures (failed `patch_apply_end`, or error-looking tool `output`).
