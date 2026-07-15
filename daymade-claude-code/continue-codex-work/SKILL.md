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

Recover actionable context from a prior **Codex CLI** session and continue execution in the current conversation. Codex records each session as a rollout JSONL under `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (with an optional `state_*.sqlite` index). Use those local files as the source of truth, then continue with concrete edits and checks — not just summarizing.

**Why this exists instead of `codex resume`**: replaying a full rollout re-feeds every reasoning step, tool call, and tool output back into the context window. For long sessions that wastes the window on resolved turns and stale output. This skill **selectively reconstructs** only actionable context — the last compaction's surviving requests, recent user/assistant turns, the tool calls and files edited, and how the session ended — giving a fresh start with prior knowledge.

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
```

**Expected output**: a structured Markdown **briefing**. What you should see:

- A `# Codex Resume Context Briefing` header, then `## Session Info` (id, project cwd, last-active time, title, Codex version).
- A one-line `**Session end reason**` — the single most important routing signal (see Step 2).
- `## Compact Summary` — if the session was compacted, the surviving user/assistant thread (system preamble and re-injected `AGENTS.md` are stripped out).
- `## Last User Requests` and `## Last Assistant Responses` — the most recent turns.
- `## Recent Tool Calls`, `## Files Edited in Session` (from `apply_patch` results), `## Errors Encountered`.
- `## Current Workspace State` — git branch, uncommitted changes, recent commits.

If instead you see `No Codex sessions found for <path>`, the current directory has no Codex history — try `--all-projects --list` to find the right project, or pass `--session <id>` directly.

### Step 2: Branch by Session End Reason

The briefing's **Session end reason** tells you how the prior run stopped. Route on it:

| End reason | What it means | Strategy |
|-----------|---------------|----------|
| **Clean exit** | The agent had the last word (a completed turn). | Read the last user request that was addressed; continue from any pending work. |
| **In progress** | Tools ran but the agent left no closing message — cut off mid-task. | This is the common resume case. Read the recent tool calls + files edited, verify what landed, and finish the turn the agent was in. |
| **Interrupted** | Tool calls were dispatched but never returned (hard stop / ctrl-c). | Re-check whether those actions took effect, then retry or move on. |
| **Abandoned** | A user message got no response. | Treat the last user message as the current request. |
| **Error cascade** | Repeated tool failures. | Do not retry blindly — diagnose the root cause first. |

### Step 3: Reconcile and Continue

Before making changes:
1. Confirm the current directory matches the session's `cwd`.
2. If the git branch differs from what the briefing shows, note it and decide whether to switch.
3. Inspect the files listed under **Files Edited** — verify the prior run's changes actually landed (a rollout records that a patch was *attempted*; confirm the current file state).
4. Do not assume old claims hold without checking — compaction and tool output are lossy.

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
- **User / assistant turns** from the event stream (`event_msg/user_message`, `event_msg/agent_message`, `task_complete.last_agent_message`) — these store plain strings and mirror the `response_item/message` items, so we avoid double-counting and sidestep `output_text` content that isn't needed here.
- **Files edited** from `event_msg/patch_apply_end` — the keys of its `changes` map are the files `apply_patch` touched.
- **Tool calls** from `response_item/function_call` and `custom_tool_call`, paired with their `*_output` by `call_id` (an unpaired call means it never returned).
- **Compaction** from `compacted` records — Codex replaces the compacted window with a `replacement_history` of messages (not a single summary), and re-injects the system preamble; the parser keeps only the user/assistant turns.

### Session end reason detection

Classified from the tail of the rollout: a trailing `task_complete`/`agent_message` is **completed**; unpaired tool calls are **interrupted**; tools that ran with no closing message are **in progress**; a trailing user message is **abandoned**; three or more tool failures are an **error cascade**.

### Noise filtering

Codex re-injects large system blocks after compaction and between turns — the permissions block, the agent-role message, and the project's `AGENTS.md`. The parser drops these using the shared `is_noise_text` (which recognizes `<permissions instructions`, `<system-reminder`, `# AGENTS.md instructions for`, and similar prefixes) so the briefing shows the real conversation, not the harness scaffolding.

## Guardrails

- Do not run `codex resume` or `codex --continue` — this skill provides context recovery within the current conversation.
- Do not treat the compact summary or tool output as complete truth — they are lossy. Always verify claims against the current workspace.
- Do not overwrite unrelated working-tree changes.
- Do not load a whole rollout file into context — always use the script (rollouts are routinely multiple MB).

## Limitations

- Cannot recover sessions whose rollout files were deleted from `~/.codex/sessions/`.
- Cannot access sessions from other machines (files are local only).
- Tool-call previews are truncated — for the full command or patch, read the rollout line directly.
- Compaction is lossy — early-conversation detail may be gone.
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
