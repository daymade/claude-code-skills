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
argument-hint: "[product-name] [competitor-url-or-search-query]"
---

# Competitors Analysis

Build competitor intelligence that can be shared, re-run, and audited later. This
skill has two layers:

1. **Repository evidence**: clone or update the competitor code under the durable
   competitors workspace, then cite facts from actual files and commits.
2. **Landscape synthesis**: summarize positioning, pricing, strengths, weaknesses,
   gaps, and opportunities, but only after separating sourced facts from judgment.

This skill intentionally subsumes lightweight "competitor scan" workflows. A scan
is useful for the landscape table, but it is not enough for technical conclusions.

## Stop Gate — required input (read this first)

This skill runs as `context: fork` and **cannot ask the user anything**. The
"ask if missing" pattern below therefore does not apply to you. Enforce this hard
gate as your very first action:

**If the caller did not pass an explicit product/market target for THIS invocation,
STOP immediately.** Report back: "competitors-analysis needs an explicit
product-name or market; none was provided, and as a background fork I cannot ask —
aborting rather than inventing a target." Then exit.

Do **not**:
- invent or infer a target — a plausible task you generated yourself is still
  fabricated, not the user's;
- run `ls` on `$COMPETITORS_BASE` to pick an existing product directory as your
  target;
- fall through to Discover mode to fill the gap.

A target counts as "provided" only if it came from the caller's request/arguments
this invocation — not from a directory name on disk, not from your own reasoning.

## Entry Router

If the user's request is missing the product/market or target customer segment,
ask for that context before synthesizing positioning or opportunity claims (in
`context: fork` you cannot ask — the Stop Gate above already handled the
missing-target case; if you reached here, a target was provided). Known
competitors are optional; if absent, use Discover mode.

Use the user's wording to choose the path:

| User intent | Mode | What to do |
|---|---|---|
| "find competitors", "竞品有哪些", broad market query | Discover | Search GitHub and web sources, shortlist candidates, clone only relevant repositories |
| "add competitor <url>" | Ingest | Clone the repository, record remote + commit, then produce a first profile |
| "analyze competitor", "review this repo" | Profile | Update or clone locally, read code, write a cited technical profile |
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
not collide. If the caller named a product directory **this invocation** and it
already exists on disk, use it as the source of truth and do not re-clone
elsewhere. Never adopt an existing product directory the caller did not name this
invocation — that is exactly how a target-less fork silently picks up an unrelated
project (2026-09-20 incident: a no-arg fork fabricated an "A2A market" task and
ratified it by reusing the on-disk `agent-communication` dir for 1h23m).

## Preflight

Before analysis, establish these facts from commands, not memory:

```bash
repo="$COMPETITORS_BASE/{product-slug}/{owner-repo}"
test -d "$repo/.git"
git -C "$repo" remote -v
git -C "$repo" fetch --all --prune
git -C "$repo" log -1 --format='%H%x09%cI%x09%s'
```

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

## Report Structure

For a single competitor, use `references/profile_template.md`.

For a landscape summary, use this structure:

```markdown
# {Product} Competitor Landscape

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
| Opportunity judgment | Evidence rows it derives from plus explicit confidence |

### Forbidden

Do not write unsupported technical claims. Avoid these patterns unless they appear
inside an explicit "bad example" block:

| Pattern | Why |
|---|---|
| "推测", "可能", "应该", "大概", "似乎" | Blurs evidence and judgment |
| "未公开", "未披露" | Pretends to know disclosure status |
| "architecture, inferred from UI" | Technical architecture must come from code |
| Unsourced numbers | Cannot be audited later |

When evidence is unavailable, write `待验证` and state the exact next check that
would verify it.

## Output Quality Bar

Before finishing, run the checks in `references/analysis_checklist.md`:

- Local repository exists under `$COMPETITORS_BASE/{product-slug}/`.
- Remote URL and latest commit are recorded.
- Each technical claim has a file:line citation.
- Market facts have a source and retrieval date.
- Landscape judgments are separated from facts.
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
