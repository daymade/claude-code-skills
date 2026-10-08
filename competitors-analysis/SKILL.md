---
name: competitors-analysis
description: >-
  Clones and audits competitor repositories into evidence-based intelligence with file:line
  citations. Use to track competitors, add a competitor repo, review competitor code, compare
  capabilities, build a competitor landscape, or check for code updates: 竞品分析 / 竞品 / competitor scan
  / analyze competitor / compare with X / latest competitor code. Not for market research without
  code (use deep-research).
context: fork
agent: general-purpose
argument-hint: "[competitor-url-or-search-query] [optional-product-name]"
---

# Competitors Analysis

Build competitor intelligence that can be shared, re-run, and audited later. This
skill has two layers:

1. **Repository evidence**: clone or update the competitor code under the durable
   competitors workspace, then cite facts from actual files and commits.
2. **Landscape synthesis**: explain which product choices the evidence changes,
   including trade-offs and what would overturn the judgment. Keep positioning,
   pricing, strengths and gaps as supporting evidence.

This skill intentionally subsumes lightweight "competitor scan" workflows. A scan
is useful for the landscape table, but it is not enough for technical conclusions.

## Resolve the analysis target (read this first)

The executing agent resolves two separate inputs: the **repository to analyze**
and the **our-product context used for comparison**. A repository URL identifies
the first; a separately typed product name is not required to profile it.

1. Honor the current request's explicit product/market and exclusions first.
   If the caller requests a standalone profile, do not add an our-product comparison.
2. Otherwise, read the current project's `AGENTS.md` / `CLAUDE.md` and follow its
   product-contract or research entry to confirm the product and analysis scope.
   The caller's current project is valid context for this invocation. A directory
   basename alone is not enough; record the authoritative file used to identify it.
   A delegated caller should pass the project path and relevant entry when available.
3. A supplied repository URL without a confirmed our-product context selects a
   standalone **Profile**. Continue repository analysis; omit comparison and
   opportunities specific to our product. A missing customer segment does not
   block code facts or sourced positioning from the repository's own docs.
4. For **Discover** or **Landscape**, use the explicit request or confirmed
   current project to establish the scope. If comparison context remains unknown,
   complete any supplied repository profiles and report the exact missing context
   to the caller. An interactive host may ask only for the unresolved comparison
   input; a noninteractive fork reports it without blocking independent profiles.

**Stop only when neither an analysis target nor an actionable current-project
scope is available.** Report that missing input to the caller. Do not invent a
task, browse `$COMPETITORS_BASE` to choose an unrelated product, or start discovery
from a self-generated market. A fork receiving neither a task request nor
caller-bound project scope must stop; its inability to ask is not a reason to
reject a supplied repository URL.

## Entry Router

Resolve scope above before selecting a mode. A bare repository URL selects
Profile, using the confirmed current project for comparison when available.
Known competitors are optional for a scoped Discover request.

Use the user's wording to choose the path:

| User intent | Mode | What to do |
|---|---|---|
| "find competitors", "竞品有哪些", broad market query | Discover | Search GitHub and web sources, shortlist candidates, clone only relevant repositories |
| "add competitor <url>" | Ingest | Clone the repository, record remote + commit, then produce a first profile |
| A repository URL, "analyze competitor", "review this repo" | Profile | Update or clone locally, read code, write a cited technical profile; compare with the confirmed current product when applicable |
| "compare", "landscape", "opportunities" | Landscape | Ensure each competitor has a profile, then synthesize gaps and opportunities |
| "latest code", "有没有更新" | Update | Pull/fetch existing competitors and report changed commits before analysis |

## Durable Source Layout

Use a durable workspace, not `/tmp`. The default base is:

```bash
COMPETITORS_BASE="${COMPETITORS_BASE:-$HOME/workspace/competitors}"
```

Directory convention:

```text
$COMPETITORS_BASE/
└── {product-slug}/
    ├── {owner-repo}/
    └── ...
```

Use `owner-repo` for GitHub repositories so forks and similarly named projects do
not collide. Derive `product-slug` from the explicitly named or authoritatively
confirmed current product. If neither applies, use `standalone` for a supplied
repository URL; this is a storage namespace, not an invented market.
Reuse the matching product directory and clone after checking its remote.
Do not browse other product directories to manufacture the analysis scope.

## Preflight

For first ingestion or an explicit freshness/update request, establish these
facts from commands, not memory:

```bash
repo="$COMPETITORS_BASE/{product-slug}/{owner-repo}"
test -d "$repo/.git"
git -C "$repo" remote -v
git -C "$repo" fetch --all --prune
git -C "$repo" log -1 --format='%H%x09%cI%x09%s'
```

For synthesis or continuation, reuse verified profiles and their pinned commits.
Confirm the matching remote and required objects locally; do not fetch or repeat
unchanged checks merely because the context was compressed. Refresh only for
requested freshness, changed inputs, missing evidence, or an unresolved concern.
Record the analyzed commit rather than describing it as current upstream.

If the repository is missing, clone it first. Prefer SSH for GitHub when possible:

```bash
mkdir -p "$COMPETITORS_BASE/{product-slug}"
git clone --depth 1 <git-ssh-url> "$COMPETITORS_BASE/{product-slug}/{owner-repo}"
```

If SSH fails for a public repository, report the failure and retry with the
repository's HTTPS URL only when that keeps the work moving.

## Discovery Workflow

Use `gh search repos` for GitHub repository discovery. Search multiple query
phrases; do not trust one keyword.

```bash
gh search repos "product keywords" \
  --limit 30 \
  --archived=false \
  --json fullName,url,description,stargazersCount,forksCount,openIssuesCount,language,pushedAt,updatedAt,defaultBranch
```

For each candidate, record:

| Field | Source |
|---|---|
| Repository name and URL | `gh search repos` / `gh repo view` |
| Description | GitHub API or README line citation after clone |
| Activity | `pushedAt`, latest commit, release notes if present |
| Stars/forks/issues | GitHub API with retrieval date |
| Why it is relevant | user's product scope + repository evidence |

Clone only candidates that are relevant to the user's product or analysis goal.
For broad markets, first present a shortlist with evidence and then analyze the
strongest set.

## Repository Fact Gathering

Read files in this order and capture exact sources:

1. Project metadata: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, or
   equivalent.
2. README and docs: positioning, screenshots, installation, pricing links.
3. Entry points: `main`, `bin`, `scripts`, `src/`, `app/`, `packages/`.
4. Core implementation: renderer, parser, storage, export, sync, auth, API, or
   domain-specific modules.
5. Tests and fixtures: they often reveal supported data structures and edge cases.
6. Releases/changelog: current direction and recent changes.

Use `nl -ba <file>` or an editor with line numbers before citing. Every technical
claim about implementation needs `file:line` evidence.

## Landscape Workflow

Before synthesizing existing profiles, read
[`references/landscape_synthesis.md`](references/landscape_synthesis.md). Follow
its evidence → causal explanation → product choice → counterexample/falsifier
chain and its project-document continuation contract. A capability matrix or a
list of features to borrow does not satisfy Landscape. A supported conclusion
that no change is warranted is valid; do not manufacture a new direction.

## Report Structure

For a single competitor, use `references/profile_template.md`. Record the current
project's authoritative scope source when used. Without our-product context,
omit its comparison section and keep opportunity judgments repository-specific.

For a landscape summary, use this structure:

```markdown
# {Product} Competitor Landscape

## Decisions Changed By The Evidence
For each material judgment: cited observations, causal explanation (inference),
concrete choice and its cost, alternative explanation/counterexample, and the
observation that would overturn it. State scope and unresolved assumptions.

## Current Understanding And Next Check
Link the existing project research entry; retain accepted/rejected judgments,
their evidence versions and failure conditions, and the next decision-bearing check.

## Source Register
| Competitor | Local path | Remote | Commit | Retrieved |
|---|---|---|---|---|

## Positioning
| Competitor | User segment | Primary promise | Source |
|---|---|---|---|

## Product And Technical Comparison
| Dimension | Competitor A | Source | Competitor B | Source | Our product | Source |
|---|---|---|---|---|---|---|

## Strengths
| Competitor | Strength | Evidence | Why it matters |
|---|---|---|---|

## Weaknesses And Gaps
| Competitor | Gap | Evidence | Opportunity |
|---|---|---|---|

## Opportunities
| Opportunity | Evidence base | Product implication | Confidence |
|---|---|---|---|

## Risks And Assumptions
| Item | What is known | What still needs verification | Next check |
|---|---|---|---|
```

## Evidence Rules

### Required

| Claim type | Required evidence |
|---|---|
| Dependency/framework/version | Config file line citation |
| Feature support | README/docs line citation plus code citation when technical |
| Parser/export/storage behavior | Code line citation |
| Pricing/cloud-hosted claim | Official page citation with retrieval date |
| Popularity/activity | GitHub API/page citation with retrieval date |
| Opportunity judgment | Cited observations, explicit confidence, labeled inference and scope, choice/trade-off, counterexample or alternative explanation, and falsifying check |

### Forbidden

Do not present unsupported technical claims as repository facts. Strategic
inference is allowed when labeled and supported by the Landscape chain; words
such as “可能 / likely” do not by themselves make a claim valid or invalid.
Check what the sentence claims and its evidence, rather than banning a word:

| Pattern | Why |
|---|---|
| Inferred implementation presented as observed code behavior | Judgment cannot fill a missing code fact |
| "未公开", "未披露" | Pretends to know disclosure status |
| "architecture, inferred from UI" | Technical architecture must come from code |
| Unsourced numbers | Cannot be audited later |

When an implementation or market fact is unavailable, write `待验证` and state
the exact next check that would verify it. Do not promote an unresolved assumption
into a requirement, claimed competitive advantage, or implementation authorization.

## Output Quality Bar

Before finishing, run the checks in `references/analysis_checklist.md`:

- Local repository exists under `$COMPETITORS_BASE/{product-slug}/`.
- Remote URL and analyzed commit are recorded; freshness is explicit.
- Each technical claim has a file:line citation.
- Market facts have a source and retrieval date.
- Landscape judgments explain a concrete choice, its trade-off and falsifier; facts and inference remain separate.
- For project-backed analysis, new understanding is saved in the existing project research entry before a stage ends or context handoff; unchanged evidence is reused on continuation.
- The final answer names gaps, opportunities, and risks without pretending they
  are code facts.

## Script

Use `scripts/update-competitors.sh` as the starting point for durable competitor
repository management:

```bash
COMPETITORS_BASE="$HOME/workspace/competitors" \
PRODUCT_NAME="{product-slug}" \
./scripts/update-competitors.sh status

./scripts/update-competitors.sh discover "claude code viewer"
./scripts/update-competitors.sh clone-url https://github.com/org/repo
./scripts/update-competitors.sh pull
```

The script is a template. For a long-running product, copy it into that product's
own repo or operations directory and fill the persistent competitor list.

## Relationship To Product Analysis

`product-analysis` may invoke this skill for compare mode. Keep this skill focused
on competitor discovery, repository evidence, and competitive synthesis. Do not
turn it into a general product audit orchestrator.
