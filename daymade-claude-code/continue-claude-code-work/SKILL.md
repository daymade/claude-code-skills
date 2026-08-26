---
name: continue-claude-code-work
description: >-
  Continues interrupted Claude Code work only after local history has been read
  and reconciled. Use when the user provides a Claude Code Session ID, asks to
  pick up prior Claude work, says a Claude run was interrupted or compacted, or
  wants the current Agent to take over without `claude --resume`. Reconstructs
  the original business outcome, unfulfilled requests, user corrections,
  successful prior assets, current workspace truth, and the next action that
  directly advances the goal. For Codex sessions use continue-codex-work.
argument-hint: "[session-id]"
---

# Continue Claude Code Work

Continue means execute the still-unfinished business task. It does not mean
summarize the transcript, perfect the history tool, or start a new experiment.

## Step 1: Obtain a verified read receipt

Invoke `daymade-claude-code:read-claude-code-history` for the exact Session. Ask
that Skill for a chronological evidence briefing, not separate “last user” and
“last assistant” buckets. If the Session ID is unknown, use its search/inventory
route first.

Do not act until the receipt states:

- exact Session ID and project;
- sources and time coverage;
- compaction and raw-chronology boundaries;
- every retained human request, including queued prompts;
- end reason, unresolved calls, files touched, and explicit gaps.

If a clipped section could contain the objective or a correction, re-read it with
the reader's full mode. If identity, ancestry, or authorship is unresolved, stop;
continuing from a guessed Session is worse than asking for the missing evidence.

## Step 2: Rebuild the continuation contract

Before the first project-changing tool call, write this compact internal contract
from evidence. Do not invent a value to fill a blank.

| Field | Evidence required |
|---|---|
| Original business outcome | Earliest still-governing human request, not a later implementation detail |
| Current explicit request | Latest human request that is not merely “继续” |
| Already completed | Independent current-state verification, not the old Agent's claim |
| Still unfulfilled | Requested result with no completion evidence |
| User corrections / do-not-repeat | Human messages that rejected a route, output, or assumption |
| Proven assets and successful routes | Existing code, docs, Skills, outputs, or commands that previously worked |
| Next direct action | One action whose success visibly reduces the unfulfilled business result |

When the latest message is only “继续,” inherit the objective from the verified
chronology. Never treat the cue itself as the specification.

## Step 3: Reconcile with current reality

1. Read the target project's current `AGENTS.md`/`CLAUDE.md` and authoritative
   project state; historical instructions may be stale.
2. Confirm the current cwd, branch, working tree, and relevant files.
3. Verify whether prior writes, commits, external operations, or background jobs
   actually landed. A transcript records attempts as well as successes.
4. Retrieve the proven asset or prior successful path before authoring a replacement.
5. If another process may still complete the same transiently failed work, verify its
   current result before duplicating it.

## Step 4: Execute the business task

Take the next direct action from the contract and verify its result. Skill edits,
review expansion, documentation systems, and infrastructure cleanup remain subordinate
unless the user explicitly made one of them the business outcome or they are strictly
required to unblock it.

Before changing direction, ask mechanically: “If this succeeds, which original
unfulfilled result becomes smaller?” If the answer is none, record it as a later
proposal and return to the task.

Do not run `claude --resume` or `claude --continue`. Do not overwrite unrelated
working-tree changes.

## Step 5: Report against the contract

- **Recovered goal**: Session and original business outcome.
- **Executed**: actions and independent verification.
- **Now complete**: contract rows that are actually closed.
- **Remaining**: unfulfilled rows and exact blockers.
- **Not repeated**: prior rejected routes deliberately avoided when relevant.

Do not say “continued successfully” when only context extraction or a process step
completed; the business result is the completion unit.
