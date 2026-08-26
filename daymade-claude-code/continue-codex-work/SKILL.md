---
name: continue-codex-work
description: >-
  Continues interrupted OpenAI Codex work only after read-codex-history verifies
  the selected rollout identity and complete fork/compaction lineage. Use when
  the user provides a Codex Session ID, asks to pick up a prior Codex run, says
  Codex was interrupted, fused, compacted, or stuck, or wants the current Agent
  to take over without `codex resume`. Restores the original business outcome,
  unfulfilled requests, user corrections, proven prior assets, current workspace
  truth, and the next action that directly advances the goal.
argument-hint: "[session-id]"
---

# Continue Codex Work

Continue means finish the still-unfulfilled business task. Reading history is a
mandatory evidence phase, not the deliverable.

## Step 1: Obtain a verified Codex read receipt

Invoke `daymade-claude-code:read-codex-history` for the exact Session ID and request
the full chronological Session evidence briefing. If the ID is unknown, use that
Skill's inventory or bounded search first.

The receipt must state:

- prompt-ledger, state-index, and rollout sources used;
- selected `session_meta.id` and whether it exactly matches the requested ID;
- root-to-child fork lineage and exact inherited byte boundaries;
- selected and inherited chronological user/assistant turns;
- compacted context, latest plan, end reason, unresolved calls, files, and gaps.

Fail closed on a mismatched rollout, missing child rollout, ambiguous physical copy,
missing parent, broken byte boundary, or continuation cue with no recoverable parent
objective. Never continue from the “closest” file.

## Step 2: Rebuild the continuation contract

Before the first project-changing tool call, fill this internal contract from the
read receipt and current-state verification:

| Field | Evidence required |
|---|---|
| Original business outcome | Earliest still-governing human request across inherited and selected timelines |
| Current explicit request | Latest human request that is not only a continuation cue |
| Already completed | Current independent verification, not old Agent narration |
| Still unfulfilled | Requested result without completion evidence |
| User corrections / do-not-repeat | Human messages rejecting a route, assumption, or output |
| Proven assets and successful routes | Existing code, documents, Skills, outputs, commands, and prior successful experiments |
| Next direct action | One action whose success visibly reduces the unfulfilled business result |

If the child contains only “继续,” “continue,” or `/fork`, inherit the task from the
verified parent snapshot. A local cue is not a standalone goal.

## Step 3: Reconcile with current reality

1. Read the current target project's `AGENTS.md`/`CLAUDE.md`.
2. Confirm cwd, branch, working tree, relevant files, and external state.
3. Verify that recorded patches, commits, pushes, downloads, jobs, or Agent outputs
   actually landed; rollouts record attempted actions too.
4. Retrieve and reuse prior successful assets before creating a replacement.
5. For transient failures such as usage limits or service errors, verify whether the
   original process later resumed and finished before duplicating work.

## Step 4: Execute the business task

Perform the next direct action and close its feedback loop. Reviews, Skill work,
infrastructure cleanup, format polish, and extra safety machinery remain subordinate
unless they directly unblock the original result or the user explicitly promoted them.

Before every material branch, ask: “If this succeeds, which original unfulfilled
result becomes smaller?” No answer means the branch is not continuation work.

Do not run `codex resume` or `codex --continue`. Do not overwrite unrelated changes.

## Step 5: Report against the contract

- **Recovered goal**: exact Session lineage and original business outcome.
- **Executed**: actions and independent verification.
- **Now complete**: contract rows actually closed.
- **Remaining**: unresolved rows and exact blockers.
- **Not repeated**: relevant rejected routes deliberately avoided.

Context recovery, parser success, a green review, or a finished subprocess is not by
itself successful continuation. The user's business result is the completion unit.
