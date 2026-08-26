---
name: continue-codex-work
description: >-
  Recover actionable context from a prior Codex CLI session's local rollout files
  and continue interrupted work without running `codex resume`. Use this whenever
  the user wants to pick up Codex (OpenAI Codex CLI / GPT agent) work — they give a
  Codex session id, ask to continue what Codex was doing, say a Codex run was cut
  off mid-task, or want to inspect `~/.codex/sessions` rollout JSONL before
  resuming. This is the Codex counterpart of continue-claude-work: reach for it for
  Codex/`~/.codex` sessions, and for continue-claude-work when the prior session was
  Claude Code (`~/.claude`).
argument-hint: "[session-id]"
---

# Continue Codex Work

## Overview

Recover actionable context from a prior **Codex CLI** session and continue execution in the current conversation. Codex records each session as a rollout JSONL under `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (with an optional `state_*.sqlite` index). If the selected session inherited history from a parent, the extractor automatically follows the complete declared lineage and reads every ancestor only through the exact fork snapshot recorded in `history_base`. Use those local files as the source of truth, then continue with concrete edits and checks — not just summarizing.

**Why this exists instead of `codex resume`**: replaying a full rollout re-feeds every reasoning step, tool call, and tool output back into the context window. For long sessions that wastes the window on resolved turns and stale output. This skill **selectively reconstructs** only actionable context — inherited fork snapshots, the last compaction's surviving requests, recent user/assistant turns, the tool calls and files edited, and how the session ended — giving a fresh start with prior knowledge.

This is the Codex sibling of `continue-claude-work`. The two are deliberately split because the on-disk formats differ: Claude Code writes `~/.claude/projects/<encoded>/<session>.jsonl`, Codex writes `~/.codex/sessions/.../rollout-*.jsonl` with a different record schema. Use **this** skill for Codex sessions; use `continue-claude-work` for Claude Code sessions.

## File Structure Reference

For the rollout directory layout, the record/payload schema, and the compaction format, see [references/file_structure.md](references/file_structure.md).

## Workflow

### Step 1: Extract Context (single script call)

Run the bundled extractor. It handles session discovery (via the shared `_core`), rollout parsing, noise filtering, and workspace state in one call:

```bash
# Latest Codex session for the current project (cwd)
python3 scripts/extract_codex_resume.py

# A specific session by id (full or unambiguous prefix)
python3 scripts/extract_codex_resume.py --session <SESSION_ID>

# Search sessions by a keyword in the title
python3 scripts/extract_codex_resume.py --query "skill migrator"

# List recent sessions for the current project
python3 scripts/extract_codex_resume.py --list

# List across all projects (not just the current cwd)
python3 scripts/extract_codex_resume.py --all-projects --list

# Untruncated retained text; default mode already keeps every user turn
python3 scripts/extract_codex_resume.py --session <SESSION_ID> --full
```

**Expected output**: a structured Markdown **briefing**. What you should see:

- A `# Codex Resume Context Briefing` header, then `## Session Info` (id, project cwd, last-active time, title, Codex version).
- A one-line `**Session end reason**` — the single most important routing signal (see Step 2).
- `## Inherited Session Lineage` — when the selected session is a fork, every parent edge from the oldest retained ancestor to the selected child. Each line shows the exact inherited byte prefix and whether the parent later grew. A child whose only local prompt is `继续` is called out explicitly: that prompt is a continuation cue, not the task.
- `## Inherited Actionable Context` — each ancestor's last retained compact summary plus a record-ordinal **chronological handoff timeline**, latest plan, tool calls, and edited files, kept separate from the selected child's local turns. The timeline includes every retained user turn and the first/latest assistant state before the next user turn, so an old final answer cannot be displayed beside a later request as if it answered it. If the child's only prompt is a continuation cue, inherited summaries auto-expand even without `--full`; making the agent manually discover that escape hatch would recreate the original failure.
- `## Compact Summary` — if the session was compacted, the surviving user/assistant thread (system preamble and re-injected `AGENTS.md` are stripped out).
- `## Selected Session Timeline` — the selected rollout's own chronological handoff, kept separate from inherited ancestors. It also retains every user turn and the first/latest assistant state before the next one; long entries name the `--full` escape at the truncation point. A user turn shown as `[skill invoked: <name> — injected body omitted]` is a skill invocation (Codex delivers the whole bundle as the message; the fact matters, the bytes don't).
- `## Latest Plan State` — if the session used Codex's `update_plan` tool, the single most recent plan call, rendered as a step checklist. This is the highest-signal "what stage is this task at" artifact for a multi-step task, and it survives even in very long sessions where the generic tool-call list below would have evicted or truncated it.
- `## Recent Tool Calls`, `## Files Edited in Session` (from patch / FileChange records), `## Errors Encountered`.
- `## Current Workspace State` — git branch, uncommitted changes, recent commits.

If instead you see `No Codex sessions found for <path>`, the current directory has no Codex history — try `--all-projects --list` to find the right project, or pass `--session <id>` directly.

### Step 2: Branch by Session End Reason

The briefing's **Session end reason** tells you how the prior run stopped. Route on it:

| End reason | What it means | Strategy |
|-----------|---------------|----------|
| **Clean exit** | The agent had the last word (a completed turn). | Read the last user request that was addressed; continue from any pending work. |
| **In progress** | Tools ran but the agent left no closing message — cut off mid-task. | This is the common resume case. Read the recent tool calls + files edited, verify what landed, and finish the turn the agent was in. |
| **Interrupted** | Tool calls were dispatched but never returned, or the turn was aborted mid-way (hard stop / ctrl-c / esc). An unresolved call takes priority over a `task_complete` error in this classification — so if the briefing *also* shows a `> The last recorded task_complete also carried an error` line right after "Unresolved tool calls", the error is plausibly why the call never returned (`usage_limit_exceeded` and `context_window_exceeded` are exactly the errors likely to strand a call mid-flight; read that line before assuming it's a plain hang). | Re-check whether those actions took effect, then retry or move on. |
| **Abandoned** | A user message got no response. | Treat the last user message as the current request. |
| **Error cascade** | Repeated tool failures. | Do not retry blindly — diagnose the root cause first. |
| **Errored** | The last turn's `task_complete` carried an error (e.g. `usage_limit_exceeded`, `context_window_exceeded`, `unauthorized`, `cyber_policy`) and produced no closing message. The briefing inlines the exact error so you don't have to open the raw rollout. | Read the specific `codex_error_info` before doing anything — the right next step differs per code (retry later vs. re-auth vs. rephrase vs. start a new thread). **For `usage_limit_exceeded` and `internal_server_error` specifically: these are often transient and clear on a schedule (usage limits reset, server load subsides).** If the original Codex process/terminal might still be open, check whether it already resumed and finished the work on its own before starting a manual continuation — duplicating that work is pure waste. A session can also show **Clean exit with a caveat**: the closing message is real but `task_complete` still carried an error (measured ~4 in 468 real cases) — read the caveat, the turn likely still finished, but the flagged issue may be worth a look. |

### Step 3: Reconcile and Continue

Before making changes:
1. If `Inherited Session Lineage` appears, identify the actual objective from `Inherited Actionable Context`; never treat a local `继续` / `continue` cue as a standalone specification.
2. Confirm the current directory matches the session's `cwd`.
3. If the git branch differs from what the briefing shows, note it and decide whether to switch.
4. Inspect the files listed under **Files Edited** — verify the prior run's changes actually landed (a rollout records that a patch was *attempted*; confirm the current file state).
5. Read the `Recovery boundary` literally: exact byte ancestry does not reverse Codex compaction, restore omitted attachment content, or prove old tool claims. Verify the current workspace.

Then:
- Implement the next concrete step aligned with the latest user request.
- Run deterministic verification (tests, type-checks, build).
- If blocked, state the exact blocker and propose one next action.

### Step 4: Report

Respond concisely:
- **Context recovered**: which session, key findings from the briefing.
- **Work executed**: files changed, commands run, test results.
- **Remaining**: pending tasks, if any.

## How the Script Works

### Session discovery reuses the shared core

Discovery goes through `_core.codex.collect_codex` (bundled into `scripts/_core/`), the same schema-tolerant reader the `local-conversation-history` skill uses: it prefers the `state_*.sqlite` index and falls back to scanning raw rollout JSONL when the DB is missing or its schema has drifted. So listing, `--query`, and latest-for-project all share one tested implementation.

### Rollout parsing

Codex's rollout schema is not Claude's. The parser reads:
- **User / assistant turns** from two possible streams, because where turns live drifts by Codex version (measured on ~2,600 rollouts, 0.142.2–0.149.0): the `event_msg/user_message` / `agent_message` mirror stream (the norm through 0.146.x and in the 0.147/0.148 alphas, rare residuals after) and `response_item/message` records (user text is `input_text`, assistant text is `output_text`, decoded locally). The streams do not always mirror — some versions keep per-step commentary only in the event stream, and mid-turn queued user inputs appear only in message records — so both are collected and the **richer stream wins per role** (ties go to the event stream), never double-counting or silently dropping either role's bigger half. Each selected turn retains its physical record ordinal; both selected and inherited briefings interleave those chosen role streams by ordinal instead of printing two time-ambiguous role buckets. An image-only user message renders as `[image-only user message]` instead of vanishing. `task_complete.last_agent_message` is a tail safeguard inserted at its original record only when the chosen stream lacks that text anywhere; it is never relocated to the end merely because later commentary exists. `response_item/agent_message` records are inter-agent traffic (sub-agent routing messages, plaintext or encrypted), never main-thread text.
- **Files edited** from `event_msg/patch_apply_end` (norm ≤0.146 + alphas; rare residuals later) and from `event_msg/item_completed` items of type `FileChange` (0.147+, where patch events vanished) — the keys of the `changes` map are the files touched; both sources feed one set.
- **Tool calls** from `response_item/function_call` and `custom_tool_call`, paired with their `*_output` by `call_id` (an unpaired call means it never returned). The most recent `update_plan` call gets extra treatment: its full parsed `plan` (and `explanation` when present) is tracked separately, last-call-wins, exempt from the 120-char tool-call preview and the last-20 window — measured stable on ~4,000 real calls, always a JSON string parsing to `{"plan": [...]}` or `{"explanation": ..., "plan": [...]}`, each step `{"step", "status"}`.
- **Compaction** from `compacted` records — Codex replaces the compacted window with a `replacement_history` of messages (not a single summary), and re-injects the system preamble; the parser keeps only the user/assistant turns.

### Fork lineage and exact snapshots

A fork's `session_meta.history_base` declares the parent `thread_id`, `end_byte_offset`, and (when present) `end_ordinal_exclusive`. The extractor follows that chain recursively, root first, and parses each parent only in the half-open byte range `[0, end_byte_offset)`. This matters because the parent's rollout may keep growing after the child forks; reading the parent's current tail would import events the child never inherited and can silently change the recovered task.

For both selected and inherited handoff views, each retained user turn stays in record order with the first and latest assistant state before the next user turn. This keeps the state that a correction responded to and the state reached before the next correction without replaying every tool-progress message. Default output never drops a retained user turn because the actual objective can occur anywhere; it clips each message instead. `--full` removes character clipping and, for an assistant-only history, restores every retained assistant state.

Lineage recovery is fail-fast. A `forked_from_id` / `history_base.thread_id` mismatch, missing parent rollout, cycle, out-of-range offset, or offset through the middle of a JSONL record stops extraction with the exact reason. If a rollout names only `forked_from_id` but provides no byte boundary, the briefing reports that limitation and does **not** guess from the parent's current file. Archived parents are resolved as well as live sessions.

### Session end reason detection

Classified from the tail of the rollout: a trailing `task_complete` or `final_answer`-phase assistant message is **completed**; unpaired tool calls or a trailing `turn_aborted` are **interrupted**; tools that ran with no closing message, or a tail stuck at a `commentary`-phase message (cut off mid-turn), are **in progress**; a trailing user message is **abandoned**; three or more tool failures are an **error cascade**. A `task_complete` can also carry an `error` (`{"message", "codex_error_info"}`) — measured on a corpus scan of 468 real occurrences across 6,650 rollouts, spanning 6 distinct `codex_error_info` values. This is captured on every `task_complete` (last-wins, so a later clean turn correctly clears a stale earlier error) and composed with the closing message rather than treated as mutually exclusive with it: error present **and** no closing message (464/468 in the scan) is **errored**, inlining the exact `codex_error_info` and message; error present **but** a real closing message anyway (4/468) stays **completed**, with a caveat noting the error rather than hiding it.

### Noise filtering

Codex re-injects large system blocks after compaction and between turns — the permissions block, the agent-role message, and the project's `AGENTS.md`. The parser drops these using the shared `is_noise_text` (which recognizes `<permissions instructions`, `<system-reminder`, `# AGENTS.md instructions for`, and similar prefixes) so the briefing shows the real conversation, not the harness scaffolding.

## Guardrails

- Do not run `codex resume` or `codex --continue` — this skill provides context recovery within the current conversation.
- Do not treat the compact summary or tool output as complete truth — they are lossy. Always verify claims against the current workspace.
- Do not replace an exact inherited snapshot with the parent's current full rollout. Post-fork parent events did not belong to the child.
- Do not overwrite unrelated working-tree changes.
- Do not load a whole rollout file into context — always use the script (rollouts are routinely multiple MB).

## Limitations

- Cannot recover sessions whose rollout files were deleted from `~/.codex/sessions/`.
- Cannot access sessions from other machines (files are local only).
- Long briefing sections are truncated by default; each truncation point prints a `rerun with --full` hint, and `--full` prints the untruncated **retained** text. User turns in both selected and inherited timelines are never count-capped; assistant progress is reduced to the first/latest state between user turns, while inherited file/tool caps still apply. Tool-call previews stay capped at 120 chars by design — for a full command or patch, grep the rollout for the call's `call_id`.
- Compaction is lossy — early-conversation detail may be gone even when lineage is exact and `--full` is used. Image-only turns remain markers; the original image/audio bytes are not reconstructed into the briefing.
- Codex has no per-session auto-memory equivalent to Claude Code's `MEMORY.md`; the project's `AGENTS.md` is deliberately filtered out as re-injected noise, so read it separately if you need the project's standing instructions.

## Example Trigger Phrases

- "continue the Codex session `019f66...`"
- "codex got cut off mid-task, pick up where it left off"
- "don't `codex resume`, just read the rollout and keep going"
- "what was Codex doing in my last session in this repo?"
- "find the Codex run where I built the skill migrator and continue it"

## Related Skills

- **`continue-claude-work`** — the same capability for Claude Code sessions (`~/.claude`). If the prior session was Claude, not Codex, use that skill instead.
- **`local-conversation-history`** — lists both Claude and Codex conversations across every config home. Use it first when you are not sure which session (or which provider) you want, then bring the Codex session id here.
