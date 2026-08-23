# Codex CLI Session File Structure

Reference for the on-disk format the `extract_codex_resume.py` script parses.
Verified against ~2,600 real rollouts spanning Codex CLI `0.142.2`–`0.149.0` (July–August 2026).

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

Every line is one JSON object with a top-level `timestamp`, `type`, and (usually) `payload`. The `payload.type` further discriminates `event_msg` and `response_item` records. Reasoning and tool-execution records dominate by volume; the table below lists what the parser reads and what it deliberately ignores.

| `type` | `payload.type` | Carries | Used for |
|--------|----------------|---------|----------|
| `session_meta` | — | `id`, `cwd`, `timestamp`, `cli_version`, `model_provider` | Session Info header |
| `compacted` | — | `message` (often empty), `replacement_history` (list of messages), `window_number` | Compact Summary |
| `event_msg` | `context_compacted` | just a marker | (the real content is in the `compacted` record) |
| `event_msg` | `user_message` | `message` (plain string) | turn stream (see version note below) |
| `event_msg` | `agent_message` | `message` (plain string) | turn stream (see version note below) |
| `event_msg` | `item_completed` | generic completed-item envelope; `item.type` ∈ `UserMessage` / `AgentMessage` / `Reasoning` / `CommandExecution` / `FileChange` / … | **only `FileChange` is read** (Files Edited, ≥0.147) — the turn mirrors inside are deliberately never read for turns |
| `event_msg` | `patch_apply_end` | `changes` (map: path -> {content\|unified_diff}), `success`, `stderr` | Files Edited; errors (norm ≤0.146 + alphas; rare residuals later) |
| `event_msg` | `task_complete` | `last_agent_message`, `duration_ms` | Assistant-text tail safeguard; turn boundary → end reason |
| `event_msg` | `turn_aborted` | abort marker | end reason → interrupted |
| `event_msg` | `task_started` / `token_count` / `thread_settings_applied` / `thread_goal_updated` | lifecycle markers, usage counters | ignored (noise) |
| `response_item` | `message` | `role` (developer/user/assistant), `content` (list), `phase` (`commentary`/`final_answer`, assistant only) | **the turn stream** — see note below |
| `response_item` | `agent_message` | `author`, `recipient`, `content` (plaintext and/or `encrypted_content`) | inter-agent traffic — **never main-thread text, always skipped** |
| `response_item` | `reasoning` | model thinking | ignored (noise) |
| `response_item` | `function_call` | `name`, `arguments` (JSON string), `call_id` | Recent Tool Calls |
| `response_item` | `function_call_output` | `call_id`, `output` (list) | pairs a call; error detection |
| `response_item` | `custom_tool_call` | `name` (e.g. `exec`), `input`, `call_id`, `status` | Recent Tool Calls |
| `response_item` | `custom_tool_call_output` | `call_id`, `output` (list) | pairs a call; error detection |
| `turn_context` / `world_state` / `inter_agent_communication_metadata` | — | turn settings, world snapshots, sub-agent routing metadata | observed; ignored |

### Message content element types (important)

`response_item/message` `content` is a list of `{type, text}` where `type` is **`input_text`** for user/developer content and **`output_text`** for assistant content (user turns may also carry `input_image` items, with or without text). The shared `extract_text` decodes `text`/`input_text` but **not** `output_text`, so the parser joins `output_text` items locally (changing the shared helper would alter every sibling skill that bundles `_core`).

**Version drift, measured on ~2,600 real rollouts (0.142.2–0.149.0):** the `event_msg/user_message` / `agent_message` mirror stream is the norm through 0.146.x and in the 0.147/0.148 alphas; stable 0.147.0 drops it for most sessions (measured 30/1050 residual files at the time), with rare residuals into 0.149.0. The two streams do NOT always mirror each other, and the divergence runs in both directions and per role: in 0.142.3 / 0.143.0 / 0.144.0 the event stream also carries per-step **commentary** narration that `response_item/message` never has (one measured file: 494 event messages vs 29 message records), while mid-turn queued user inputs appear only in message records (whole-stream selection was measured to lose the final user request on real dual-stream files). The parser therefore collects both streams and lets the **richer stream win per role** — requests and responses display in separate sections, so per-role selection never silently drops either role's bigger half; ties go to the event stream, the historical display stream. Assistant `message` records carry a `phase` field: a session whose tail is a `commentary` message was cut off mid-turn and is classified **in progress**, not completed. Two more user-turn shapes: an invoked skill arrives as a user message whose whole body is the skill bundle (`<skill>…</name>…`, measured 2.7–148 KB), rendered as a one-line `[skill invoked: <name> — injected body omitted]` marker; and an image-only message (an `input_image` item with no text) renders as `[image-only user message]` instead of vanishing from the briefing.

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
