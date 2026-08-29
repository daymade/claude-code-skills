---
name: github-ops
description: >-
  Operates GitHub through gh CLI and the REST/GraphQL APIs with explicit target,
  authorization, impact preview, and independent readback. Use for pull requests,
  issues, Actions, repositories, collaborators, teams, organization member
  privileges, base permissions, 2FA enforcement, repository settings, API
  automation, parallel or superseded PR convergence, and public or enterprise
  GitHub. Also use when a GitHub write returned success but the requested state did
  not change, or when deciding whether a setting is writable through CLI, REST,
  GraphQL, or only the GitHub UI.
---

# GitHub Operations

Deliver the requested GitHub state, not a successful-looking command. A `200`, `201`,
`202`, or `204` response is evidence that GitHub accepted a request; it is not proof
that every requested field changed, an invitation was accepted, an asynchronous job
finished, or the user's business outcome was achieved.

## Route by operation

Read only the reference required for the task:

| Task | Reference |
|---|---|
| Create, review, merge, close, compare, or converge PRs; retire remote PR branches | [`references/pr_operations.md`](references/pr_operations.md) |
| Create, edit, search, transfer, close, or bulk-manage issues | [`references/issue_operations.md`](references/issue_operations.md) |
| Inspect, clone, create, edit, rename, archive, transfer, change visibility, or delete repositories | [`references/repository_operations.md`](references/repository_operations.md) |
| Inspect or change collaborators, teams, base permissions, member privileges, or organization 2FA | [`references/organization_access_and_settings.md`](references/organization_access_and_settings.md) |
| Trigger, inspect, rerun, cancel, or purge Actions; manage secrets or variables | [`references/workflow_operations.md`](references/workflow_operations.md) |
| Use raw REST/GraphQL endpoints, pagination, rate limits, webhooks, or Enterprise hosts | [`references/api_reference.md`](references/api_reference.md) |
| Build scripts, retries, bulk operations, or machine-readable output | [`references/best_practices.md`](references/best_practices.md) |

For local Git recovery, dirty worktrees, bundles, or lost commits, use `git-safety-net`.
This skill owns GitHub-hosted state.

## Universal operating contract

### 1. Classify the request before touching GitHub

- **Answer, inspect, diagnose, or review:** read-only. Do not create a PR, issue,
  comment, invitation, workflow run, or setting change.
- **Create, change, merge, close, grant, revoke, publish, or delete:** the named
  state change is authorized. Keep the target and blast radius inside that request.
- **Destructive, public, credential-related, production-triggering, or externally
  communicative:** require the exact target, consequence, and recovery path. If the
  user did not provide a material choice such as repository owner, visibility, or
  message content, stop before the write.

Do not turn a read-only investigation into a mutation because the fix looks obvious.
Do not send a comment, review, issue, or invitation whose recipient or content was not
authorized in the current task.

### 2. Bind identity, host, and target

Before the first write, verify the active account and resolve a fully qualified target:

```bash
gh auth status --hostname HOST
gh api --hostname HOST user --jq '.login'
gh repo view HOST/OWNER/REPO \
  --json nameWithOwner,visibility,isPrivate,viewerPermission,url
```

For `github.com`, `OWNER/REPO` is sufficient. Never use `gh auth status --show-token`
for routine diagnosis, and never print, paste, or log a token.

Before the first push to a remote in the current session, read its live visibility:

```bash
gh repo view OWNER/REPO \
  --json nameWithOwner,visibility,isPrivate,stargazerCount,forkCount,url
```

### 3. Read current authority and preview the delta

Use GitHub-hosted state, not a stale local ref or remembered setting. Capture only the
fields required to prove the requested transition. Before a consequential write, make
this plan explicit:

```text
Target: fully qualified repository, organization, PR, issue, run, or account
Current: authoritative fields and immutable IDs/SHAs
Requested: exact field or state transition
Blast radius: people, repositories, forks, runs, or public surfaces affected
Recovery: exact inverse operation or explicit “not recoverable”
Readback: independent GET/CLI query and expected result
```

If the user already authorized this exact consequence, execute it. Do not add a
ceremonial second confirmation. If target, scope, public exposure, deletion, recipient,
or recovery remains ambiguous, pause before the write.

### 4. Choose an interface whose input contract actually supports the change

Prefer, in order:

1. a purpose-built `gh` subcommand;
2. a documented REST endpoint for one resource or authoritative readback;
3. GraphQL when the required mutation/query is GraphQL-only or combines related data;
4. the documented GitHub UI when the setting has no supported API input.

Response fields are not automatically writable fields. Before using `PATCH`, compare
the desired key against the operation's current **request body parameters**, not the
shape returned by `GET`. GitHub may ignore an unsupported key while still returning a
successful response. Do not switch API families merely to make the command run.

Use explicit methods with `gh api`. Adding `-f` or `-F` changes the default method to
`POST`; filtered GET requests must include `-X GET`.

### 5. Mutate once; do not retry ambiguity

- Pin repository, object number, branch, run ID, username, and expected SHA where the
  operation supports it.
- Do not blindly retry non-idempotent writes such as comments, invitations, workflow
  dispatches, releases, or PR/issue creation. After a timeout or 5xx, read back first to
  determine whether the first request landed.
- For bulk changes, freeze and display the finite target list, then process one target
  at a time with per-item results. Never pipe an unreviewed live query directly into a
  destructive `xargs` command.
- Do not bypass repository hooks, required checks, branch protections, signatures, or
  visibility-consequence acknowledgements.

### 6. Verify through an independent readback

Run a fresh read that does not trust the mutation response or a cached local ref:

| Mutation | Required acceptance evidence |
|---|---|
| PR merge/close/edit | PR state plus accepted behavior on the fetched base when landing matters |
| Branch deletion | Hosted branch/ref is absent; local remote-tracking cleanup is a separate check |
| Issue/comment/review | Exact object exists once with the intended state/content |
| Repository create/edit/visibility | Fully qualified repository readback matches owner, visibility, and requested fields |
| Collaborator/team permission | Invitation state if pending, then effective permission; also identify remaining base/team grants when revoking |
| Organization setting | A fresh organization/settings read returns every requested field; UI-only settings require UI readback plus any available API signal |
| 2FA requirement | Preflight affected accounts, UI confirmation, API readback, then membership/outside-collaborator audit |
| Workflow dispatch/rerun/cancel | The intended run ID reaches the expected state; command acceptance is not completion |
| Secret/variable change | Metadata and consumer behavior, never secret value disclosure |

For asynchronous state, poll with a bounded deadline and report `pending` if the terminal
state is not observed. If readback differs, report `failed/no-op` or `partially applied`,
show the mismatched fields, and keep recovery available. Never say “done” from the write
receipt alone.

### 7. Report the business outcome

End with one of four honest states:

- **changed and verified** — requested state is independently observed;
- **already satisfied** — no write was necessary;
- **pending** — accepted but not yet terminal, with the next authoritative check;
- **failed/no-op or partial** — requested and observed states differ, with recovery and
  unresolved risk.

## High-impact boundaries

- Repository creation requires an explicit `OWNER/REPO` and visibility. Never default
  a generic example to `--public`; public exposure is a product decision.
- Repository visibility changes can expose code, Actions logs, artifacts, forks, and
  history. Use `gh repo edit --visibility ... --accept-visibility-change-consequences`
  only after the consequences and exact repository are authorized, then read back.
- Merges, branch deletions, repository creation/deletion/transfer/visibility changes,
  organization-wide permissions, 2FA enforcement, and secret rotation require their
  operation-specific reference.
- PR and issue title formats are repository policy. Inspect templates, contribution
  guidance, checks, or an accepted recent example; do not invent a universal JIRA prefix.
- Enterprise policy can override organization or repository controls. Preserve `HOST`
  explicitly and report when a lower layer cannot change the enforced state.

## Safe read-only quick reference

```bash
gh pr list -R OWNER/REPO --state open --json number,title,state,url
gh pr view 123 -R OWNER/REPO --json number,title,state,headRefOid,baseRefOid,url
gh issue list -R OWNER/REPO --state open --json number,title,state,url
gh workflow list -R OWNER/REPO
gh run list -R OWNER/REPO --limit 20 \
  --json databaseId,status,conclusion,headSha,url
gh api -X GET 'repos/OWNER/REPO/branches?per_page=100' --paginate --jq '.[].name'
```

Use `--json`/`--jq` for decisions. Human-formatted output is for reading, not parsing.
