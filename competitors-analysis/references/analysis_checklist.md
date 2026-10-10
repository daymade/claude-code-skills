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
- [ ] Git product directory exists under `$COMPETITORS_BASE/{product-slug}/`; standalone profiles use the `standalone` namespace.
- [ ] Git repository directory uses the `owner-repo` convention; supplied packages retain their bound location.
- [ ] Any existing local clone is reused instead of cloning into a second path.
- [ ] Carrier and edition match the request; separately distributed editions are individually found or unresolved, following the entry's Preflight.

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

Apply this recipe only to Git sources. Use it for first ingestion or requested freshness. Synthesis and
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
- [ ] Answer/citation judgments include the [source readback and counterevidence
  check](#citation-readback-and-counterevidence), not just a returned schema or link.

## 6. Language Checks

Check claims in context, not with a banned-word pass/fail rule:

- [ ] No unsupported implementation or market inference is presented as fact.
- [ ] Strategic inference is labeled, tied to cited observations and scoped to the business.
- [ ] Unknown facts are written as `待验证` with a specific next check.
- [ ] Unverified assumptions do not become requirements or claims of advantage.

## 7. Landscape Checks

For multi-competitor reports:

- [ ] Source register lists carrier, edition and retrieval date, with Git local path/remote/commit or package origin/member/digest; unknown version or origin stays unknown.
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

### Citation Readback And Counterevidence

For a claim that an answer is faithful, or that a citation lets the consumer
continue reading, use the already-authorized reader for that source:

1. Resolve the citation against its recorded source version and location. Read
   the original passage and enough surrounding context to decide whether it
   supports, limits or contradicts the answer. If the citation cannot resolve,
   retain the answer as unverified and record the exact failed read.
2. Inspect the same question's relevant counterpassage, if one is present in the
   bounded source. Do not select only supportive snippets or treat lack of a
   counterexample in that sample as proof of general quality.
3. Record a later source-access check separately from the original observation.
   A payload's `available` field is not a consumer readback. A stopped public
   source does not establish that an existing private archive's permission was
   revoked; permission comes from its own authority. Preserve unknown when that
   authority does not decide the question.
4. For a product recommendation, use the profile's comparison baseline and the
   Landscape decision chain: compare the named acceptance scenario with existing
   assets and the evidenced adopted workflow before proposing a new feature.
   A public client proves only its exposed contract and exercised client behavior;
   it does not reveal the server's architecture or establish answer quality.

The following is a **synthetic report fragment**, not an API schema or a claim
about a real product. Its source version is defined once in the source register:

```markdown
Source register: demo-source-a = frozen demonstration transcript.

| Claim / citation | Evidence version reference | Locator | Original and surrounding context read back | Availability observation |
|---|---|---|---|---|
| "The extractor never misses a frame" / demo-7 | demo-source-a | segment 7 | Original: "Each sampled frame was processed." Next sentence: "Frames between samples were not inspected." The answer overstates the source. | Authorized local snapshot readable at this check; public endpoint no longer readable at a separate later check. |

Comparison baseline: the product authority's existing passage-reading acceptance;
existing asset: its already-authorized transcript archive; actual reuse in the
target reader untested.

Choice: reuse the existing transcript and expose its passages for that acceptance
scenario. This avoids another transcription, but needs a consumer readback.
Counterevidence: the client has a citation contract, yet the target reader may
fail to resolve it. Next check: open the cited passage in that reader, including
the limiting next sentence. If it fails, the reuse path remains unverified.
```

A second narrow check catches client/server overreach: if the only evidence is
a client posting `/chat` and a `Citation` type containing `quote`, the supported
finding is “the client accepts this response shape.” Server retrieval strategy,
model choice and faithful answers remain `待验证`; a returned type is no substitute
for the readback above. Having a CLI is an interface fact, not differentiation
without the comparative acceptance result.

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
