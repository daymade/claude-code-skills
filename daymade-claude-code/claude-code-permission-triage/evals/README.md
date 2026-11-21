# Trigger evaluation notes

`claude-code-permission-triage` is a manual-only router child
(`disable-model-invocation: true`). These cases therefore evaluate whether the
model-invocable `claude-code-ops-router` selects the child, not whether the
disabled child appears in the automatic skill catalog.

A zero automatic-trigger rate for the child is expected and is not a pass or a
failure. Run a real router trigger measurement only after separate authorization
because it invokes a model.

## Boundary

Route to this Skill when the user reports an observed permission-card or
approval-block failure involving a worker, delivery state, mode timeline, or
upstream feedback. Route elsewhere for a generic feature-contract question,
configuration change, hook authoring, MCP OAuth, history read, usage analysis,
statusline setup, ordinary team creation, or macOS TCC/Keychain permission.

## Positive cases

| Case | Expected owner | Why |
|---|---|---|
| 1 | this Skill | bypass is active but a named teammate still prompts |
| 2 | this Skill | background subagent is parked without a rendered card |
| 3 | this Skill | Plan Mode teammate waits for lead approval |
| 4 | this Skill | one dialog blocks teammate message delivery |
| 5 | this Skill | sanitized upstream permission-defect feedback |
| 6 | this Skill | worker mode inheritance needs a timeline |
| 7 | this Skill | missing hook event is evidence for delivery triage |
| 8 | this Skill | card is delayed and the worker is parked |
| 9 | this Skill | background worker is blocked on an out-of-scope read |
| 10 | this Skill | teammate request was sent but no approval control rendered |

## Negative cases

| Case | Expected owner | Why |
|---|---|---|
| 1 | `update-config` | add an allow rule |
| 2 | `update-config` | change the default permission mode |
| 3 | `claude-code-hooks` | author a PermissionRequest hook |
| 4 | MCP authentication owner | OAuth re-authorization |
| 5 | `claude-usage-analyst` | quota burn |
| 6 | `read-claude-code-history` | read a recorded session |
| 7 | `statusline-generator` | configure the statusline |
| 8 | `daymade-agent-discipline` | ordinary team creation |
| 9 | Claude Code permission guide | generic dangerous-rm contract question |
| 10 | macOS permissions owner | TCC/Keychain dialog |

Cases 9 and 10 in the positive set are observed worker failures. Case 9 in the
negative set is a generic contract question. The distinction is incident
evidence versus feature documentation, not whether the underlying exception can
prompt under bypass.
