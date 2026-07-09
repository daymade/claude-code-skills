# Competitor Analysis Checklist

Use this checklist before, during, and after any competitor analysis. The purpose
is to keep repository evidence, market evidence, and judgment separate.

## 1. Scope And Storage

- [ ] Product or market scope is explicit.
- [ ] Competitor base directory is explicit:
  `COMPETITORS_BASE="${COMPETITORS_BASE:-$HOME/workspace/competitors}"`.
- [ ] Product directory exists under `$COMPETITORS_BASE/{product-slug}/`.
- [ ] Repository directory uses the `owner-repo` convention.
- [ ] Any existing local clone is reused instead of cloning into a second path.

## 2. Discovery Checks

For broad searches, run more than one query:

```bash
gh search repos "primary keywords" --limit 30 --archived=false \
  --json fullName,url,description,stargazersCount,forksCount,openIssuesCount,language,pushedAt,updatedAt,defaultBranch
```

- [ ] Search queries are recorded.
- [ ] Candidate relevance is tied to the user's product scope.
- [ ] Broad search results are shortlisted before deep analysis.
- [ ] Forks, archived repos, and stale repos are identified rather than silently
  treated as first-class competitors.

## 3. Repository Preparation

```bash
repo="$COMPETITORS_BASE/{product-slug}/{owner-repo}"
test -d "$repo/.git"
git -C "$repo" remote -v
git -C "$repo" fetch --all --prune
git -C "$repo" log -1 --format='%H%x09%cI%x09%s'
```

- [ ] Remote URL is recorded.
- [ ] Latest local commit hash is recorded.
- [ ] Commit date is recorded.
- [ ] Default branch or current branch is recorded.
- [ ] Local changes, if any, are noted before pulling.

## 4. Source Reading

- [ ] README or docs are read for positioning.
- [ ] Config files are read for language, framework, scripts, and dependencies.
- [ ] Entry points are identified from config or file layout.
- [ ] Core implementation files are read directly.
- [ ] Tests or fixtures are checked when the competitor handles structured data.
- [ ] Changelog/releases are checked when the user asks for "latest".

## 5. Citation Checks

Use line-numbered reads before writing technical claims:

```bash
nl -ba package.json | sed -n '1,140p'
nl -ba src/main.ts | sed -n '1,220p'
```

- [ ] Versions cite config file lines.
- [ ] Feature claims cite README/docs and implementation lines when available.
- [ ] Parser/export/storage claims cite code lines.
- [ ] Market data cites GitHub/API/web source plus retrieval date.
- [ ] Each comparison-table value has a source cell.

## 6. Language Checks

Search the final report for unsupported language:

```bash
rg -n "(推测|可能|应该|大概|似乎|或许|未知|未披露|未公开|assume|probably|maybe)" profile.md
```

- [ ] No unsupported inference is presented as fact.
- [ ] Unknowns are written as `待验证` with a specific next check.
- [ ] Judgment is separated from repository facts.

## 7. Landscape Checks

For multi-competitor reports:

- [ ] Source register lists local path, remote, commit, and retrieval date.
- [ ] Positioning table distinguishes user segment from technical implementation.
- [ ] Strengths are tied to user-visible behavior or code evidence.
- [ ] Weaknesses/gaps cite evidence or are labeled as `待验证`.
- [ ] Opportunities cite the evidence rows they derive from.
- [ ] Risks and assumptions include the next verification step.

## Common Fixes

### Unsupported Architecture Claim

Before:

```markdown
## Architecture
The app probably uses a microservice architecture.
```

After:

```markdown
## Architecture
The repository exposes one Vite app and one Node server entrypoint:
- `apps/web/package.json:7` defines `vite --host`.
- `server/index.ts:1-42` creates the HTTP server.
```

### Unsourced Comparison Row

Before:

```markdown
| Dimension | Competitor | Our product |
|---|---|---|
| Export | HTML and PDF | HTML and PDF |
```

After:

```markdown
| Dimension | Competitor | Source | Our product | Source |
|---|---|---|---|---|
| Export | HTML and PDF | `src/export.ts:12-84` | HTML and PDF | `src/export/share.ts:1-92` |
```

### Stale Local Clone

Before:

```markdown
Analyzed local copy in ~/Downloads/repo.
```

After:

```markdown
Analyzed `$COMPETITORS_BASE/{product}/{owner-repo}` at commit
`<full-hash>` (`git log -1 --format='%H %cI %s'`).
```
