# GitHub CLI Automation and Reliability

Use this reference for machine-readable output, pagination, retries, bulk operations,
GitHub Enterprise hosts, scripting, debugging, and performance. All writes follow the
mutation contract in [`../SKILL.md`](../SKILL.md).

## Contents

- Machine-readable output
- Pagination and large result sets
- Error handling and retries
- Safe bulk operations
- Enterprise hosts and authentication
- Automation patterns
- Configuration, performance, and debugging

## Machine-readable output

Prefer `--json` plus `--jq` for decisions. Human output can change formatting and should not
be parsed with `grep` to extract object IDs.

```bash
# Structured gh output
gh pr list -R OWNER/REPO --json number,title,state,headRefOid,url

# Built-in jq projection
gh pr list -R OWNER/REPO --json number,title,state \
  --jq '.[] | select(.state == "OPEN") | {number,title}'

# Go template for human-readable display
gh pr list -R OWNER/REPO \
  --template '{{range .}}{{.number}}: {{.title}}{{"\n"}}{{end}}'
```

Request only the fields needed to decide or verify the operation. This reduces GraphQL cost and
makes acceptance checks explicit.

## Pagination and large result sets

High-level `gh ... list` commands use `--limit`; they do not accept a generic `--page` flag.

```bash
gh pr list -R OWNER/REPO --state all --limit 200 \
  --json number,title,state,url
```

For complete REST collections, use `gh api --paginate`. When query fields are supplied with
`-f` or `-F`, force `GET` because those flags otherwise switch the method to `POST`.

```bash
gh api -X GET 'repos/OWNER/REPO/pulls?state=all&per_page=100' \
  --paginate --slurp \
  --jq '[.[][] | {number,title,state}]'

gh api -X GET 'repos/OWNER/REPO/issues?state=all&per_page=100' \
  --paginate --slurp
```

For GraphQL pagination, the query must accept `$endCursor` and return
`pageInfo { hasNextPage endCursor }`; then use `--paginate`. Do not simulate “all” with a guessed
page count.

## Error handling and retries

### Separate transport acceptance from state acceptance

A zero exit code or successful HTTP status proves the request completed at that interface. The
independent readback in `SKILL.md` decides whether the requested state exists.

```bash
if ! result=$(gh api 'repos/OWNER/REPO/pulls/123' 2>error.log); then
  printf 'GitHub read failed\n' >&2
  sed -n '1,80p' error.log >&2
  exit 1
fi
printf '%s\n' "$result" | jq '{number,state,merged,head_sha:.head.sha}'
```

Avoid suppressing errors with `2>/dev/null` when absence and authorization failure would lead to
different actions. A `404` can mean absent, hidden, or inaccessible.

### Retry only operations that are safe to repeat

Bounded retries are appropriate for read-only requests and explicitly idempotent writes. Use the
server's rate-limit or `Retry-After` signal when available.

```bash
result=''
for delay in 1 2 4; do
  if result=$(gh api 'repos/OWNER/REPO/pulls/123'); then
    break
  fi
  sleep "$delay"
done
test -n "$result" || { printf 'Read failed after bounded retries\n' >&2; exit 1; }
```

Do not blindly retry comments, reviews, invitations, workflow dispatches, releases, repository
creation, or PR/issue creation. After a timeout or 5xx, query by exact target/content/idempotency
key first. Retry only if readback proves the first request did not land.

## Safe bulk operations

Bulk work is a sequence of exact single-object operations, not one unreviewed pipeline.

1. Query and freeze a finite target set with immutable IDs/SHAs.
2. Display it with the proposed action.
3. Confirm the current request authorizes that exact set and consequence.
4. Process one object at a time, recording success/failure.
5. Read every object back and report partial completion honestly.

```bash
targets=$(gh issue list -R OWNER/REPO --label needs-triage \
  --json number,title,state,url)
printf '%s\n' "$targets" | jq .

# Execute only after this exact set is authorized.
printf '%s\n' "$targets" | jq -r '.[].number' | while read -r issue; do
  if gh issue edit "$issue" -R OWNER/REPO --add-label reviewed; then
    gh issue view "$issue" -R OWNER/REPO --json number,state,labels,url
  else
    printf 'Issue %s failed; continuing for a complete per-item report\n' "$issue" >&2
  fi
done
```

Do not stream a live search into `xargs` for merges, approvals, closes, deletes, permission
changes, workflow control, or messages. The query can change while the writes run, and parallel
writes make recovery and rate-limit behavior harder to attribute.

## Enterprise hosts and authentication

Keep the host explicit when more than one GitHub instance is configured:

```bash
gh auth login --hostname github.example.com
gh auth status --hostname github.example.com
gh api --hostname github.example.com user --jq '.login'
gh pr list -R github.example.com/OWNER/REPO
```

For a shell session dedicated to one enterprise host:

```bash
export GH_HOST=github.example.com
gh auth status
```

Use `gh auth login`, a CI secret store, or the platform's credential mechanism. Never place a
token literal in a command, document, process argument, log, or committed environment file. Do not
use `gh auth status --show-token` for routine checks.

Enterprise policy can override organization and repository settings. If a mutation returns a
policy error or readback remains unchanged, inspect the enterprise policy layer instead of trying
alternate payload spellings.

## Automation patterns

### Create, identify, verify

Do not scrape the PR number from the human URL output. Create once, then identify the PR from the
verified head branch and read back structured fields.

```bash
gh pr create -R OWNER/REPO \
  --title "Describe the change" \
  --body-file pr-description.md \
  --base main \
  --head feature-branch

gh pr view feature-branch -R OWNER/REPO \
  --json number,title,state,headRefOid,baseRefOid,url
```

### Merge only the reviewed head

```bash
head_sha=$(gh pr view 123 -R OWNER/REPO --json headRefOid --jq '.headRefOid')
gh pr checks 123 -R OWNER/REPO --watch
gh pr merge 123 -R OWNER/REPO --squash --match-head-commit "$head_sha"
gh pr view 123 -R OWNER/REPO --json number,state,mergedAt,mergeCommit,url
```

The final GitHub readback proves PR state; fetch the base and run the acceptance check to prove
the intended behavior landed.

### Poll asynchronous state with a deadline

```bash
deadline=$((SECONDS + 300))
while (( SECONDS < deadline )); do
  state=$(gh run view RUN_ID -R OWNER/REPO --json status --jq '.status')
  test "$state" = completed && break
  sleep 10
done
gh run view RUN_ID -R OWNER/REPO \
  --json databaseId,status,conclusion,headSha,url
```

If the deadline expires, report `pending`; do not turn a timeout into a failure or success claim.

## Configuration

```bash
gh repo set-default OWNER/REPO
gh config set git_protocol ssh
gh config list
```

Treat the default repository as convenience, not authority for a consequential write. Reconfirm
the fully qualified target immediately before mutation.

Useful environment variables:

- `GH_HOST`: selected GitHub host.
- `GH_REPO`: default `[HOST/]OWNER/REPO` for commands that support it.
- `GH_PAGER`: pager selection.
- `GH_NO_UPDATE_NOTIFIER=1`: suppress CLI update notices in automation.
- `GH_TOKEN` / `GITHUB_TOKEN`: non-interactive authentication supplied by a protected runtime;
  never inline or echo the value.

## Performance

- Cache a read-only response within one decision when the relevant hosted state cannot change
  underneath the operation.
- Re-read immediately before a destructive write or when another actor can move the target.
- Select only required JSON fields.
- Use REST pagination rather than guessed loops.
- Check `gh api rate_limit` instead of persisting rate-limit numbers that vary by resource,
  authentication, plan, and platform policy.

```bash
gh api rate_limit --jq '.resources | with_entries(.value |= {
  limit,remaining,reset,used
})'
```

## Debugging

```bash
GH_DEBUG=1 gh pr list -R OWNER/REPO
GH_DEBUG=api gh api 'repos/OWNER/REPO/pulls/123'
gh api -i 'repos/OWNER/REPO/pulls/123'
```

Debug output can contain repository names, request bodies, headers, and other sensitive context.
Inspect it locally and redact it before sharing. Never enable token-printing flags.

When a `gh` GraphQL-backed subcommand fails but a REST endpoint exists, use REST to recover the
hosted state. Report the failed query channel separately; one API path failing does not prove the
resource is absent.

## Completion checklist

- Active account, host, and fully qualified target were verified.
- Any write used the current operation input contract.
- Non-idempotent writes were not blindly retried.
- Bulk targets were frozen and previewed before mutation.
- The requested state was independently read back.
- Partial, pending, or policy-blocked outcomes remain visible.
