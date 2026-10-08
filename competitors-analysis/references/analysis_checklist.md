# Competitor Analysis Checklist

Use this checklist before, during, and after any competitor analysis. The purpose
is to keep repository evidence, market evidence, and judgment separate.

## 1. Scope And Storage

- [ ] Analysis target comes from the request or the current project's authoritative entry.
- [ ] A supplied repository URL proceeds as Profile even without our-product context.
- [ ] Our-product comparison cites the confirmed project contract; omit it for a standalone request or unresolved context.
- [ ] Missing comparison context does not block independent repository profiles; no-target/no-project requests stop without inventing a market.
- [ ] Competitor base directory is explicit:
  `COMPETITORS_BASE="${COMPETITORS_BASE:-$HOME/workspace/competitors}"`.
- [ ] Product directory exists under `$COMPETITORS_BASE/{product-slug}/`; standalone profiles use the `standalone` namespace.
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

Use the fetch recipe for first ingestion or requested freshness. Synthesis and
continuation reuse verified profiles at pinned commits; confirm remote/object
availability locally and refresh only for changed inputs or unresolved evidence.

```bash
repo="$COMPETITORS_BASE/{product-slug}/{owner-repo}"
test -d "$repo/.git"
git -C "$repo" remote -v
git -C "$repo" fetch --all --prune
git -C "$repo" log -1 --format='%H%x09%cI%x09%s'
```

- [ ] Remote URL is recorded.
- [ ] Analyzed commit hash is recorded; distinguish it from current upstream.
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

Check claims in context, not with a banned-word pass/fail rule:

- [ ] No unsupported implementation or market inference is presented as fact.
- [ ] Strategic inference is labeled, tied to cited observations and scoped to the business.
- [ ] Unknown facts are written as `待验证` with a specific next check.
- [ ] Unverified assumptions do not become requirements or claims of advantage.

## 7. Landscape Checks

For multi-competitor reports:

- [ ] Source register lists local path, remote, commit, and retrieval date.
- [ ] Positioning table distinguishes user segment from technical implementation.
- [ ] Strengths are tied to user-visible behavior or code evidence.
- [ ] Weaknesses/gaps cite evidence or are labeled as `待验证`.
- [ ] Read `landscape_synthesis.md`; a correct feature table alone does not pass.
- [ ] The baseline includes the user's actual adopted workflow or substitute, when evidenced.
- [ ] Each material judgment connects evidence, causal explanation, a concrete choice and cost, a counterexample/alternative explanation, and a falsifying check.
- [ ] Claims of differentiation include current native/platform capabilities when relevant; absence in our sample is not proof of market uniqueness.
- [ ] Technical acknowledgement, delivery, adoption and qualified outcome are distinguished when relevant.
- [ ] Risks and assumptions include the next check that could change the choice.
- [ ] Update the existing project research entry when understanding changes; retain evidence versions, live conclusions, failure conditions and open questions.
- [ ] Continuation reads that entry and latest user correction before acting; do not rerun a completed inventory without changed inputs or a specific gap.

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
