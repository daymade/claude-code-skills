# Repository operations guide template

Use this only when the repository needs a durable handoff document. Replace every
placeholder from project evidence; delete sections the project does not need.

## Template

~~~markdown
# <Project name> operations guide

> Tell the Agent what outcome you want in normal language. The commands below are
> the verified project contract, not a requirement that you run them by hand.

## One-time setup

### 1. Confirm repository state

~~~bash
git status --short --branch
~~~

Expected: the intended branch and a visible list of any local changes. Do not hide
or automatically stash changes.

### 2. Verify declared prerequisites

| Requirement | Declared by | Verification | Expected output |
|---|---|---|---|
| <tool/runtime> | <manifest or runbook> | <version command> | <verified example> |

Install only missing requirements using the method documented for this project and
operating system.

### 3. Install project dependencies

~~~bash
<dependency installation command from the manifest/lockfile>
~~~

Expected: <observable success signal>.

### 4. Configure local values

- Source of required variable names: <env template or config schema>.
- Store values in: <project-authorized local location>.
- Never copy a value from another environment or invent a fallback.
- Verify presence without printing secret contents.

### 5. Run the smoke test

~~~bash
<smallest real verification command>
~~~

Expected: <exit code plus product-level signal>.

## Daily use

| Outcome | Agent action or command | Success signal |
|---|---|---|
| Sync before work | Inspect state; clean → git pull --ff-only | Fast-forward or already current |
| Start the project | <start command> | <health response/window/output> |
| Run focused tests | <test command> | <expected pass summary> |
| Save an intended change | Ask the Agent to review and commit selected files | Commit contains only intended paths |

If the worktree has local changes or histories diverged, the Agent reports the
state instead of automatically stashing, merging, rebasing, or forcing.

## Recovery

### <Observed failure signature>

- Evidence: <exact error/exit status>
- Root cause: <verified cause>
- Repair: <project-consistent command or edit>
- Verification: <command and expected result>

## Ownership and boundaries

- Project instructions: <AGENTS.md/CLAUDE.md or equivalent>
- Operational source of truth: <manifest/runbook/config>
- Actions requiring explicit approval: <push/deploy/destructive/external actions>
~~~

## Adaptation checklist

1. Derive every requirement from a project file or exercised command.
2. Keep one operational source of truth; do not repeat volatile versions or values.
3. Put expected output immediately after each command.
4. Separate one-time setup from daily operation.
5. Include only failures that were observed or are intrinsic to the selected tool.
6. Test commands on each target operating system.
7. Write for a capable collaborator; explain project-specific context, not generic
   computing concepts.
