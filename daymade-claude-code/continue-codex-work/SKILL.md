---
name: continue-codex-work
description: >-
  Continues interrupted Codex work only after read-codex-history verifies rollout identity and
  fork/compaction lineage — restores the original outcome, unfulfilled requests, and the next
  action. Use when given a Codex Session ID, asked to pick up a prior Codex run, told Codex was
  interrupted, fused, compacted or stuck, or asked to take over without `codex resume`. Not for a
  conversation Codex already natively resumed.
argument-hint: "[session-id]"
---

# Continue Codex Work

Continue means finish the still-unfulfilled business task. Reading history is a
mandatory evidence phase, not the deliverable.

## Entry gate: external takeover, not native resume

| Current situation | Action |
|---|---|
| Codex itself natively resumed this same conversation, and the restored turns or compaction state are already in the current context | Do not invoke this Skill or `read-codex-history`. Continue directly from the retained context, then verify current workspace and external state before changing anything. |
| A new/different Agent context must take over an earlier Codex rollout, or the user identifies another Session ID whose continuity is not already present here | Use this Skill. Step 1's verified history receipt remains mandatory. |

A restart is not enough to choose the second row. The deciding fact is whether
the current conversation is the host-restored continuation of the same Session,
not whether a Codex process was restarted.

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

**Isolated or remote `CODEX_HOME` staging**: When taking over a Codex session staged to
a separate directory (for example on a remote worker or an isolated handover bundle),
pass `CODEX_HOME=<staged-codex-home>` to `read-codex-history`
(`find_codex_session.py <session-id> --format json` and
`read_codex_session.py --session <session-id> --full`) rather than scanning the host's
default `~/.codex`. Require `status: "unique"` and `identity_verified: true` from the
staged index before proceeding.

## Step 2: Rebuild the continuation contract

Before choosing the next action or reporting a stage complete, fill this internal
contract from the verified read receipt and the project's current stage source.
Use the latest human request when no project stage source exists.

| Field | Evidence required |
|---|---|
| Original business outcome | Earliest still-governing human request across inherited and selected timelines |
| Current explicit request | Latest human request that is not only a continuation cue |
| Current delivery stage / non-goals | Latest human correction narrowing what to deliver now and what to defer; do not promote the original long-term ambition back above it |
| Already completed | Independent completion evidence, not Agent narration or an assistant final. Bind it to artifact/session identity and input conditions; reuse it while those conditions are unchanged. Read volatile runtime and delivery state fresh. |
| Still unfulfilled | Requested result without completion evidence |
| User corrections / do-not-repeat | Human messages rejecting a route, assumption, or output |
| Proven assets and successful routes | Existing code, documents, Skills, outputs, commands, and prior successful experiments |
| Next direct action | One action whose success visibly reduces the unfulfilled business result |

If the child contains only “继续,” “continue,” or `/fork`, inherit the task from the
verified parent snapshot. A local cue is not a standalone goal.

## Step 3: Reconcile with current reality

1. Read the current target project's `AGENTS.md`/`CLAUDE.md`.
2. Confirm cwd, branch, working tree, relevant files, and external state. When continuing
   on a remote host or a fresh pool checkout, inspect `git status` and `git rev-parse HEAD`
   directly rather than assuming uncommitted working-tree state from the source machine
   exists in the target checkout.
3. Before independent takeover edits, reruns or dispatch, execute this Skill's
   `scripts/start_work.py` against the loaded `agent-message` Skill. Retain the
   recovered stable task key and owned paths across Forks, but obtain the actor
   from the current host; never adopt a parent/history/context-pack ID. Native
   parent/worker work retains the host task tree and skips independent registration.

   ```bash
   python3 '<loaded-continue-codex-work>/scripts/start_work.py' \
     --peer-skill '<absolute-loaded-agent-message>' -- \
     --repo '<absolute-target-checkout>' --path '<owned-repo-relative-file-or-directory>' \
     --task '<stable-issue-or-deliverable>' --actor '<exact-current-host-address>'
   ```

   The wrapper runs the existing `peer.py coord start` and preserves its result
   and exit code. On exit 3, use its existing owner/result lead before starting
   replacement work. An empty registry retains unknown occupancy. Resolve a
   missing dependency through the existing Skill owner; do not create a second
   board. Follow agent-message's current work-entry/reconciliation contract for
   non-Git resources, changed identities and released declarations. This checks
   the invoked entry; it does not enforce all host file writes.
4. Verify that recorded patches, commits, pushes, downloads, jobs, or Agent outputs
   actually landed; rollouts record attempted actions too.
5. Retrieve and reuse prior successful assets before creating a replacement.
6. For transient failures such as usage limits or service errors, verify whether the
   original process later resumed and finished before duplicating work.
   For an existing native Goal, use [Native Goal reconciliation](references/native-goal-reconciliation.md)
   to distinguish unfinished business, runtime status, supported recovery and observed
   automatic continuation. An absent recovery tool in one tool menu is not proof that
   the live host has no recovery control.
7. Check what was **in flight** when the session stopped. A long task may survive
   its controller; a start record proves neither completion nor process death.
   Read its existing receipt/output and verify the current process before deciding
   whether to monitor, finish archival or rerun. If the process is gone and the
   result is unconfirmed, give an authorized rerun a detached
   result-to-disk channel (e.g. remote `( cmd > log 2>&1 </dev/null; echo $? > rc ) &`
   polled through the rc file — prefer `setsid`/`nohup` where the target has them,
   since a pty-backed session can still SIGHUP a bare subshell) so the next
   interruption cannot take the result again.

**In-flight CI example:** An existing `result.json` names commit `H`, owner `O`
and a running test phase; its lifecycle marker records PID `P`. Before starting
another CI, match `P`'s live argv to `H` and the exact output path, match its cwd
and child test phase to that receipt, and observe log growth or a child completing
the documented timeout fixture. A matching live operation should be monitored
through its original result, archive and cleanup, keeping its owner and accumulated
budget. A vanished controller or an old receipt mtime does not authorize a second
run; PID existence alone does not establish identity. Reconcile any final-head
delta separately and rerun only the affected checks. This process check follows
Step 1 for external takeover; native continuation still uses the entry gate above.

## Step 4: Execute the business task

Perform the next direct action and close its feedback loop. Reviews, Skill work,
infrastructure cleanup, format polish, and extra safety machinery remain subordinate
unless they directly unblock the original result or the user explicitly promoted them.

Before every material branch, ask: “If this succeeds, which unfulfilled result in
the current authorized stage becomes smaller?” No answer means the branch is not
continuation work. A blocked source, login or provider route blocks only dependent
work; execute other necessary authorized work before declaring the whole task blocked.

Verify the result at the user's consumption surface: searchable bytes alone do not
prove a readable page, and generated suggestions do not prove saved human decisions.
Reuse passed checks for unchanged inputs; expand verification only for new changes,
failures or unresolved evidence gaps.

Do not run `codex resume` or `codex --continue`. Do not overwrite unrelated changes.

## Step 5: Report against the contract

- **Recovered goal**: exact Session lineage and original business outcome.
- **Executed**: actions and independent verification.
- **Now complete**: contract rows actually closed.
- **Remaining**: unresolved rows and exact blockers.
- **Not repeated**: relevant rejected routes deliberately avoided.

Context recovery, parser success, a green review, or a finished subprocess is not by
itself successful continuation. The user's business result is the completion unit.
