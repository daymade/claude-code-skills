---
name: claude-code-permission-triage
description: >-
  Diagnose unexpected, missing, delayed, parked, or misdelivered Claude Code
  permission prompts and approval cards for subagents, background workers, and
  Agent Team teammates, including Plan Mode interactions. Use for evidence
  collection, known-issue matching, root-cause classification, and sanitized
  upstream feedback. Not for editing allow/deny rules, writing hooks, MCP OAuth,
  or reading conversation history.
disable-model-invocation: true
---

# Claude Code permission triage

Classify the event before explaining it. A permission-shaped UI can be a normal
permission check, a Plan Mode approval, an interactive question, an MCP login,
a hook dialog, or a delivery failure. Do not start with profile or model blame.

## Scope and handoffs

| Need | Owner |
|---|---|
| Explain why a permission card appeared, did not appear, was delayed, parked, or reached the wrong surface | This Skill |
| Change `allow`, `ask`, `deny`, `defaultMode`, or settings files | `update-config` |
| Author, change, or configure `PreToolUse` / `PermissionRequest` hook behavior | `claude-code-hooks` |
| Observe a missing, parked, or misdelivered permission request by comparing expected hook events with the transcript | This Skill |
| Read a session, tool call, hook input, or timeline | `read-claude-code-history` |
| Decide whether to spawn, wait for, or stop a worker | `daymade-agent-discipline` |
| Grade evidence, statistics, and counter-tests | `daymade-evidence-discipline` |
| MCP OAuth or server authentication | The MCP/server authentication owner |

## Stop rule

Stop and hand off when the request is only a configuration change, hook change,
MCP OAuth flow, or history read.

Missing evidence is **not** a final `unknown`. Continue authorized read-only
collection. Stop only when the next step is irreversible, outward-facing,
paid, or requires access the current identity does not have; then name the
missing source and the smallest next action.

Never retry the same failing call, spawn another worker, edit settings, or edit
the transcript to make the symptom disappear.

## Evidence order

### 1. Freeze identity

Record:

- event time in UTC and local time;
- Claude Code version;
- entrypoint: CLI, Desktop, VS Code, Web, SDK, or Remote Control;
- launch flag and settings sources, with secrets removed;
- agent-teams enablement and teammate mode;
- session, worker, team, and `tool_use_id` as sanitized labels;
- repository/project as a synthetic label;
- model and effort as covariates, not causes.

### 2. Freeze original records

Collect read-only:

- parent and worker transcripts;
- the `Agent` spawn input;
- team/agent configuration and mailbox state;
- effective settings and CLI flags;
- hook and Notification logs;
- MCP/connector configuration;
- a render/delivery observation when available.

Record path, byte count, and SHA-256 for each load-bearing artifact. Do not
rewrite the source.

### 3. Build the mode timeline

Use record timestamps, never file mtime. Keep these fields separate:

- requested mode at launch;
- mode requested in the spawn call;
- mode observed on the worker;
- mode observed when the event occurred;
- every parent mode switch, with its evidence.

### 4. Classify the event

Use two independent axes.

| Axis | Values |
|---|---|
| Event surface | permission card; teammate-forwarded request; plan approval; `AskUserQuestion`; MCP OAuth; Notification; hook dialog; unknown |
| Delivery state | shown and answered; shown and unanswered; emitted but not rendered; parked without a result; held or queued; blocked other messages; succeeded or failed without a card; unknown |

Then classify the worker:

- main session;
- foreground subagent;
- background subagent;
- nested subagent;
- in-process teammate;
- split-pane teammate;
- top-level background session;
- SDK worker;
- unknown.

Do not infer worker type from a display name alone. Use the spawn input,
agent-teams state, team config, hooks, and transcript lineage together.

### 5. Check the expected exceptions first

Before calling this a product defect, rule out:

- explicit `ask` rules;
- deny rules;
- organization connector `ask`;
- `AskUserQuestion`;
- MCP tools marked `requiresUserInteraction`;
- recognized critical-path `rm`/`rmdir` or `Dangerous rm operation not ruled out`;
- `ExitPlanMode` or another plan approval;
- cross-session messaging safeguards;
- reads or writes blocked outside the working directories;
- `PreToolUse` or `PermissionRequest` hook decisions;
- a parent or worker mode that was not the mode shown in the UI.

A `PermissionRequest` hook fires only after a permission decision is needed.
It can answer that request; its presence does not prove the worker inherited
the wrong mode.

## Check the current contract

At investigation time, retrieve and record the retrieval date and Claude Code
version for these canonical pages:

- Agent Teams permissions: <https://code.claude.com/docs/en/agent-teams#permissions>
- Subagent permission modes: <https://code.claude.com/docs/en/sub-agents#permission-modes>
- Permission-mode exceptions: <https://code.claude.com/docs/en/permission-modes#actions-no-mode-auto-approves>
- PermissionRequest hooks: <https://code.claude.com/docs/en/hooks#permissionrequest>

The stable rule is that `bypassPermissions` is not an absolute no-prompt
guarantee. Worker type, spawn time, event time, host surface, and documented
live coupling decide whether a mismatch is expected, a delivery defect, a mode
inheritance defect, or unresolved.

## Known-issue search

Search before writing a root-cause story. Record the query, date, matched
issues, considered issues, and ruled-out issues.

Seed issues, last verified 2026-11-21:

| Issue | Symptom family |
|---|---|
| #26479 | Agent Teams teammate ignores bypass and project permission state |
| #104869 | in-process teammate permission request is not rendered and parks |
| #104870 | pending teammate request blocks lead message delivery |
| #107910 | one open teammate prompt blocks all teammate messages |
| #108380 | background/nested subagent prompts despite bypass |
| #105736 | session falls back from auto/bypass after spawning a subagent |

Re-search open, closed, duplicate, and maintainer comments at investigation
time. Related delivery-blocking issues are not independent root causes; do not
double-count them.

Useful query shapes:

```text
repo:anthropics/claude-code is:issue "Agent Teams" teammate bypassPermissions
repo:anthropics/claude-code is:issue "Waiting for team lead approval"
repo:anthropics/claude-code is:issue "background subagent" bypassPermissions
repo:anthropics/claude-code is:issue "Plan Mode" permission prompt
repo:anthropics/claude-code is:issue PermissionRequest teammate
```

## Statistics

When reporting frequency:

- filter by each record's internal timestamp;
- deduplicate by `tool_use_id`;
- label missing, repeated, and ambiguous IDs separately;
- stratify by model, mode, entrypoint, version, worker type, and a predefined
  complexity band;
- report numerator, denominator, time window, coverage, and blind spots;
- write `0` as `0 within the covered evidence surface`, never `never happened`.

`permissionDecision.source=user_*` identifies the decision source. It does not
prove that a new card was rendered or that the user clicked a new prompt.
Count visible prompts only with independent render/delivery evidence.

Before a negative conclusion, check the lead main view, teammate pane,
agent/task status, Notification/debug logs, form responses, image attachments,
and thread replies. Unchecked surfaces remain explicit blind spots.

## Output

Use exactly four sections.

```text
## Facts
## Inferences
## Unknowns
## Next steps
```

Bind every load-bearing fact to a timestamp, sanitized identity,
`tool_use_id`, version, and evidence path or public URL. Separate observation
from mechanism. Give one safe next action with an owner and stop condition.

Classify the result as one of:

- expected exception;
- configuration or workflow;
- Anthropic product defect;
- delivery/UI defect;
- unresolved.

## Anthropic escalation gate

Recommend an upstream issue only when all are true:

1. the behavior reproduces on a recorded Claude Code version;
2. a minimal synthetic repro exists;
3. the actual behavior conflicts with the official contract or proves a defect;
4. configuration, hooks, MCP auth, and history-reader explanations are ruled out;
5. exact issue search found no sufficient duplicate;
6. the mode timeline and delivery state are complete enough to classify;
7. impact, frequency, and workaround are stated;
8. all private identifiers and raw settings are removed;
9. the user authorizes the outward submission.

If the parent changed mode before the event, bind the conclusion to worker
type and timing. An in-process teammate with a documented next-turn mode check
can support a mode-inheritance or demotion defect when the observed mode
conflicts with that contract. For split-pane, background, nested, or SDK
workers without an explicit live-coupling rule, record the result as
unresolved and collect the next discriminating evidence; do not label it a
teammate permission defect from the parent switch alone.

## Sanitized feedback template

```text
Symptom:
Time and timezone:
Claude Code version:
Entrypoint:
Agent teams enabled / teammate mode:
Worker type:
Requested mode:
Spawn-time mode:
Observed event-time mode:
Event surface:
Delivery state:
tool_use_id:
Minimal synthetic repro:
Expected:
Actual:
Official contract:
Related issues:
Evidence available:
Blind spots:
Impact and workaround:
```

Never place session IDs, team IDs, absolute paths, customer or project names,
user names, tokens, raw settings, mailbox JSON, or unredacted screenshots in a
public repository or issue.
