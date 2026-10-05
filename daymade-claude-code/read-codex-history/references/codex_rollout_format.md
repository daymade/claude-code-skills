# Codex CLI Session File Structure

Reference for the on-disk format the `read_codex_session.py` script parses.
Verified against ~2,600 real rollouts spanning Codex CLI `0.142.2`–`0.149.0` (July–August 2026).

## Directory layout

```
~/.codex/                                  # CODEX_HOME (override with $CODEX_HOME)
├── sessions/
│   └── YYYY/MM/DD/
│       └── rollout-<ISO8601>-<thread-id>[_<rollout-id>].jsonl
├── archived_sessions/                     # same shape, archived sessions
├── sqlite/  or  ./                        # state_*.sqlite index (schema drifts between versions)
├── session_index.jsonl                    # optional id -> thread_name title map
└── AGENTS.md                              # project/global standing instructions (re-injected into rollouts)
```

Verify the session ID against the rollout's `session_meta` record; a filename or
state-database row alone is not identity proof. Treat `state_*.sqlite` as an
inventory metadata index. Follow the [current inventory contract](../SKILL.md#recent-inventory)
when it is missing or unreadable, and use the [exact-session locator](../SKILL.md#exact-session-evidence-and-lineage)
for a known ID. Do not substitute a raw rollout sweep for an unavailable inventory.

## Rollout JSONL — record schema

Every line is one JSON object with a top-level `timestamp`, `type`, and (usually) `payload`. The `payload.type` further discriminates `event_msg` and `response_item` records. Reasoning and tool-execution records dominate by volume; the table below lists what the parser reads and what it deliberately ignores. The table describes the chronological briefing. Keyword search additionally reads native `CommandExecution` completions as tool results; it does not treat them as conversation turns.

| `type` | `payload.type` | Carries | Used for |
|--------|----------------|---------|----------|
| `session_meta` | — | `id`, `cwd`, `timestamp`, `cli_version`, `model_provider`; forks may also carry `forked_from_id` + `history_base` | Session Info header; exact inherited lineage |
| `compacted` | — | `message` (often empty), `replacement_history` (list of messages), `window_number` | Compacted Context |
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

**Version drift, measured on ~2,600 real rollouts (0.142.2–0.149.0):** the `event_msg/user_message` / `agent_message` mirror stream is the norm through 0.146.x and in the 0.147/0.148 alphas; stable 0.147.0 drops it for most sessions (measured 30/1050 residual files at the time), with rare residuals into 0.149.0. The two streams do NOT always mirror each other, and the divergence runs in both directions and per role: in 0.142.3 / 0.143.0 / 0.144.0 the event stream also carries per-step **commentary** narration that `response_item/message` never has (one measured file: 494 event messages vs 29 message records), while mid-turn queued user inputs appear only in message records (whole-stream selection was measured to lose the final user request on real dual-stream files). The parser therefore collects both streams and lets the **richer stream win per role**, with ties going to the event stream. Each chosen turn keeps its physical record ordinal; selected and fork briefings interleave the chosen user and assistant streams by ordinal, rather than placing requests and responses in separate buckets that erase which state preceded a correction. Assistant `message` records carry a `phase` field: a session whose tail is a `commentary` message was cut off mid-turn and is classified **in progress**, not completed. `task_complete.last_agent_message` is inserted at its own record ordinal only when the selected assistant stream lacks that text anywhere; a completed old turn is never moved behind later commentary. Two more user-turn shapes: an invoked skill arrives as a user message whose whole body is the skill bundle (`<skill>…</name>…`, measured 2.7–148 KB), rendered as a one-line `[skill invoked: <name> — injected body omitted]` marker; and an image-only message (an `input_image` item with no text) renders as `[image-only user message]` instead of vanishing from the briefing.

## Compaction format

When Codex compacts, it emits a `compacted` record whose `replacement_history` is the list of messages that **replace the live model window** — not a single distilled summary like Claude Code. In the observed append-only rollouts, raw records written before that boundary remain earlier in the JSONL; the extractor continues parsing them for the chronological timeline and ingests every compacted record. The briefing renders the latest compacted continuation state for the selected session and the latest one per ancestor, because each later state supersedes the earlier compacted window. That history also re-injects the system preamble. In one real record the 13 items were:

- items with `role: "user"` — the surviving user requests (high signal)
- items with `role: "developer"` — the permissions block, the agent-role message, `<multi_agent_mode>` (system noise)
- a `role: "user"` item whose content is `# AGENTS.md instructions for <cwd>` (~50 KB) — re-injected standing instructions, not a real turn (noise)

So the parser keeps only `role` in `{user, assistant}` **and** drops anything `is_noise_text` recognizes (`<permissions instructions`, `<system-reminder`, `# AGENTS.md instructions for`, …). It stores the full surviving text; the briefing renderer applies one visible section-level limit in default mode, and `--full` removes that clipping. The result is the retained continuation thread without harness scaffolding or irreversible parser-side truncation.

## Forked-session lineage

A fork can have an almost empty local rollout — for example, its only local user message may be `继续` — while inheriting the actual task from one or more ancestors. Current Codex records the edge in the child's `session_meta`:

```json
{
  "forked_from_id": "<parent-session-id>",
  "history_base": {
    "thread_id": "<parent-session-id>",
    "end_ordinal_exclusive": 4200,
    "end_byte_offset": 12345678
  }
}
```

`end_byte_offset` selects the half-open physical byte range `[0, end_byte_offset)` and must end between complete JSONL records. `end_ordinal_exclusive`, when declared, must agree with that prefix. In paginated history, stored ordinals start at zero in an initial rollout and at the inherited `end_ordinal_exclusive` in a new segment; the leading metadata consumes one ordinal. The reader verifies every stored ordinal and rejects disagreement between byte and ordinal cutoffs.

The parent file may contain later records; the reader excludes all bytes after the inherited cutoff. In Codex 0.160 paginated history, `history_base.thread_id` names an immutable physical rollout, while `session_meta.id` and `forked_from_id` identify logical threads. A revert can keep the logical ID and create a filename with a different `_rollout-id` suffix. The state index selects the current segment; ancestor references resolve by physical rollout ID, and repeated physical IDs fail as cycles. A missing indexed selection among multiple segments is ambiguous. Copies of one physical rollout retain the byte-identical/append-only rule and reject divergence. For older non-paginated history, `forked_from_id` remains a cross-check against the history-base ID. A parent ID without an exact boundary remains a reported gap; complete logical `--tools` export refuses that gap.

Verified format authority: Codex [`rust-v0.160.0` rollout lineage](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/thread-store/src/local/rollout_lineage.rs), [current rollout selection](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/thread-store/src/local/thread_rollout_resolver.rs), and [stored ordinal state](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/rollout/src/ordinal.rs).

This recovery is compaction-aware. It reads raw pre-compaction records still present inside each exact snapshot and ingests every surviving `message` / `replacement_history`; it cannot recreate content absent from both sources or turn an image-only marker back into the original attachment. The briefing renders only the latest compacted context for the selected session and the latest one from each ancestor; when the selected child contains only a continuation cue, inherited latest context auto-expands because otherwise the hidden task can still sit beyond the default character cutoff. Selected and inherited raw history render every retained user and assistant text turn in record order. Neither role is count-capped because the original objective, a correction, or the only proven successful asset can occur in the middle; default mode clips each long turn and `--full` removes character clipping without changing turn selection. Inherited tool/file caps remain deliberate.

### Legacy embedded fork snapshot (no `history_base`)

Older Codex CLI (measured: `history_mode: "legacy"`, cli_version `0.149.0`) had no `history_base` byte-boundary contract yet. Instead, on fork it copies the entire inherited prefix of the parent's own rollout **inline**, as literal JSONL records, right after the child's own leading `session_meta`:

```json
{"type": "session_meta", "payload": {"id": "<child-id>", "forked_from_id": "<parent-id>", "history_mode": "legacy"}}
{"type": "session_meta", "payload": {"id": "<parent-id>", ...}}
```

— i.e. the file's *second* record is itself a `session_meta` whose `payload.id` equals the first record's `forked_from_id`. A rollout with exactly two `session_meta` identities is therefore not always a real identity conflict; `validate_selected_rollout_identity`'s "fused rollout" error is deliberately narrow, so `recover_legacy_embedded_fork` runs first and only treats the shape above as an embedded snapshot, never anything looser.

The embedded copy is a re-serialization, not a byte-identical copy: the wrapper `timestamp` is rewritten to the fork moment, and some payload shapes gain an extra key. Measured on a real 17,312-record embedded snapshot (session `01a037ab-baa7-74a3-9832-41086a99fd4e`, forked from `01a02fe8-8477-7632-bb47-9cadf3eae086`, 66.3 MB / 19,161 records total): every `response_item/message` payload gained an `id` (namespaced under the CHILD's own session id, e.g. `msg_01a037ab-...`, not the parent's), and every `response_item/reasoning` payload gained a null `content`; every other payload was untouched. Comparing record-for-record after dropping the `id` key and every null-valued key from both sides matched all 17,312 records against the real parent file with zero exceptions — the parent had 7 further records of its own after the fork point (17,319 total), correctly excluded.

Because there is no declared byte offset to trust, the extractor **derives and verifies** one: it locates the parent rollout by the declared `forked_from_id`, then streams the child's records (from index 1 onward) against the parent's own records (from index 0), stopping at the first mismatch under the normalization above. The resulting byte offset is read directly off the parent's real bytes via `tell()`, so — unlike an externally declared `history_base.end_byte_offset` — it always lands on a true JSONL line boundary by construction. Fails closed, distinctly, when: the declared parent cannot be located; fewer than 2 leading records match (not strong enough evidence to build a lineage edge on); or a third `session_meta` identity turns up in the child's own tail beyond the embedded range (the pre-existing fused-rollout error, unchanged). On success the briefing's "Inherited Session Lineage" section reports the parent's path, the derived record/byte boundary, how many records were inherited, and how many are the child's own — and the Selected Session Timeline contains only the child's own records, never the embedded copy. Scope: only the *selected* session's own embedded snapshot is recovered this way; an ancestor further up a chain that is itself a legacy-embedded fork keeps the pre-existing soft warning below, unrecovered.

## Session end reason

Derived from the tail of the rollout and the set of unpaired tool calls:

- **completed** — the last significant record is `task_complete` or `agent_message` (the agent had the last word).
- **interrupted** — a `function_call`/`custom_tool_call` has no matching `*_output` (dispatched but never returned).
- **in_progress** — tools ran and returned, but there is no closing `agent_message`/`task_complete` (cut off mid-task). This is the common resume case.
- **abandoned** — the last significant record is a `user_message` with no response.
- **error_cascade** — three or more tool failures (failed `patch_apply_end`, or error-looking tool `output`).
