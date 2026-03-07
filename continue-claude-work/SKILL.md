---
name: continue-claude-work
description: Recover actionable context from local `.claude` session artifacts and continue interrupted work without running `claude --resume`. This skill should be used when the user provides a Claude session ID, asks to continue prior work from local history, or wants to inspect `.claude` files before resuming implementation.
argument-hint: [session-id]
---

# Continue Claude Work

## Overview

Recover actionable context from a prior Claude Code session and continue execution in the current conversation. Use local session files as the source of truth, then continue with concrete edits and checks — not just summarizing.

**Why this exists instead of `claude --resume`**: `claude --resume` replays the full session transcript into the context window. For long sessions this wastes tokens on resolved issues and stale state. This skill **selectively reconstructs** only actionable context — the latest compact summary, pending work, known errors, and current workspace state — giving a fresh start with prior knowledge.

## File Structure Reference

For directory layout, JSONL schemas, and compaction block format, see `references/file_structure.md`.

## Workflow

### Step 1: Extract Context (single script call)

Run the bundled extraction script. It handles session discovery, compact-boundary parsing, noise filtering, and workspace state in one call:

```bash
# Latest session for current project
python3 scripts/extract_resume_context.py

# Specific session by ID
python3 scripts/extract_resume_context.py --session <SESSION_ID>

# Search by topic
python3 scripts/extract_resume_context.py --query "auth feature"

# List recent sessions
python3 scripts/extract_resume_context.py --list
```

The script outputs a structured Markdown **briefing** containing:
- **Session metadata** from `sessions-index.json`
- **Compact summary** — Claude's own distilled summary from the last compaction boundary (highest-signal context)
- **Last user requests** — the most recent explicit asks
- **Last assistant responses** — what was claimed done
- **Errors encountered** — tool failures and error outputs
- **Unresolved tool calls** — indicates interrupted session
- **Subagent workflow state** — which subagents completed, which were interrupted, their last outputs
- **Session end reason** — clean exit, interrupted (ctrl-c), error cascade, or abandoned
- **Files touched** — files created/edited/read during the session
- **MEMORY.md** — persistent cross-session notes
- **Git state** — current status, branch, recent log

The script automatically skips the currently active session (modified < 60s ago) to avoid self-extraction.

### Step 2: Branch by Session End Reason

The briefing includes a **Session end reason**. Use it to choose the right continuation strategy:

| End Reason | Strategy |
|-----------|----------|
| **Clean exit** | Session completed normally. Read the last user request that was addressed. Continue from pending work if any. |
| **Interrupted** | Tool calls were dispatched but never got results (likely ctrl-c or timeout). Retry the interrupted tool calls or assess whether they are still needed. |
| **Error cascade** | Multiple API errors caused the session to fail. Do not retry blindly — diagnose the root cause first. |
| **Abandoned** | User sent a message but got no response. Treat the last user message as the current request. |

If the briefing has a **Subagent Workflow** section with interrupted subagents, check what each was doing and whether to retry or skip.

### Step 3: Reconcile and Continue

Before making changes:
1. Confirm the current directory matches the session's project.
2. If the git branch has changed from the session's branch, note this and decide whether to switch.
3. Inspect files related to pending work — verify old claims still hold.
4. Do not assume old claims are valid without checking.

Then:
- Implement the next concrete step aligned with the latest user request.
- Run deterministic verification (tests, type-checks, build).
- If blocked, state the exact blocker and propose one next action.

### Step 4: Report

Respond concisely:
- **Context recovered**: which session, key findings from the briefing
- **Work executed**: files changed, commands run, test results
- **Remaining**: pending tasks, if any

## How the Script Works

### Compact-Boundary-Aware Extraction

The script finds the **last** compact boundary in the session JSONL and extracts its summary. This is the single highest-signal piece of context in any long session -- Claude's own distilled understanding of the entire conversation up to that point. For details on compaction format and JSONL schemas, see `references/file_structure.md`.

### Size-Adaptive Strategy

| Session size | Strategy |
|-------------|----------|
| Has compactions | Read last compact summary + all post-compact messages |
| < 500 KB, no compactions | Read last 60% of messages |
| 500 KB - 5 MB | Read last 30% of messages |
| > 5 MB | Read last 15% of messages |

### Subagent Context Extraction

When a session has subagent directories (`<session-id>/subagents/`), the script parses each subagent's JSONL to extract agent type, completion status, and last text output. This enables recovery of multi-agent workflows -- e.g., if a 32-subagent evaluation pipeline was interrupted, the briefing shows which agents completed and which need retry.

### Session End Reason Detection

The script classifies how the session ended:
- **completed** -- assistant had the last word (clean exit)
- **interrupted** -- unresolved tool calls (ctrl-c or timeout)
- **error_cascade** -- 3+ API errors
- **abandoned** -- user sent a message with no response

### Noise Filtering

These message types are skipped (37-53% of lines in real sessions):
- `progress`, `queue-operation`, `file-history-snapshot` -- operational noise
- `api_error`, `turn_duration`, `stop_hook_summary` -- system subtypes
- `<task-notification>`, `<system-reminder>` -- filtered from user text extraction

## Guardrails

- Do not run `claude --resume` or `claude --continue` — this skill provides context recovery within the current session.
- Do not treat compact summaries as complete truth — they are lossy. Always verify claims against current workspace.
- Do not overwrite unrelated working-tree changes.
- Do not load the full session file into context — always use the script.

## Limitations

- Cannot recover sessions whose `.jsonl` files have been deleted from `~/.claude/projects/`.
- Cannot access sessions from other machines (files are local only).
- Edit tool operations show deltas, not full file content — use `claude-code-history-files-finder` for full file recovery.
- Compact summaries are lossy — early conversation details may be missing.
- `sessions-index.json` can be stale (entries pointing to deleted files). The script falls back to filesystem-based discovery.

## Example Trigger Phrases

- "continue work from session `abc123-...`"
- "don't resume, just read the .claude files and continue"
- "check what I was working on in the last session and keep going"
- "search my sessions for the PR review work"
