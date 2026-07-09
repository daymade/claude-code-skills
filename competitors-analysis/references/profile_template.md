# {Competitor Name} Competitor Profile

## Source Register

| Field | Value |
|---|---|
| Repository | {GitHub URL} |
| Local path | `$COMPETITORS_BASE/{product-slug}/{owner-repo}` |
| Remote | `{git remote get-url origin}` |
| Branch | `{git branch --show-current}` |
| Commit | `{git log -1 --format='%H'}` |
| Commit date | `{git log -1 --format='%cI'}` |
| Retrieved | {YYYY-MM-DD} |
| License | {license source} |

## Analysis Boundary

This profile separates:

- **Repository facts**: verified from local cloned source code and cited as
  `file:line`.
- **Market facts**: sourced from GitHub/API/official pages with retrieval date.
- **Judgment**: synthesis based on cited evidence, labeled with confidence.

## Positioning

> "{README or official description quote}"
>
> Source: `{README.md:start-end}` or {official page URL, retrieved YYYY-MM-DD}

| Question | Answer | Source |
|---|---|---|
| Target user | {segment} | {source} |
| Primary promise | {promise} | {source} |
| Distribution model | {CLI/web/app/library/etc.} | {source} |
| Pricing / monetization | {value or 待验证} | {source or next check} |

## Technical Stack

| Area | Value | Source |
|---|---|---|
| Language/runtime | {value} | `{file}:{line}` |
| UI framework | {value} | `{file}:{line}` |
| Backend/server | {value} | `{file}:{line}` |
| Storage | {value} | `{file}:{line}` |
| Build/test tooling | {value} | `{file}:{line}` |

## Repository Structure

```text
{owner-repo}/
├── {file-or-dir}
└── ...
```

Source command:

```bash
find "$repo" -maxdepth 2 -mindepth 1 -print | sort
```

## Core Implementation Findings

| Capability | Implementation | Evidence | Notes |
|---|---|---|---|
| {capability} | {how it works} | `{file}:{start}-{end}` | {notes} |
| {capability} | {how it works} | `{file}:{start}-{end}` | {notes} |

## Data Model / Input Format

Use this section when the competitor parses structured data, session logs, exports,
or protocol messages.

| Data object | Fields / shape | Evidence | Implication |
|---|---|---|---|
| {object} | {fields} | `{file}:{start}-{end}` | {why it matters} |

## User-Facing Capabilities

| Capability | User-visible behavior | Evidence | Maturity |
|---|---|---|---|
| {feature} | {behavior} | `{file}:{line}` / `{README.md}:{line}` | {stable/partial/experimental/待验证} |

## Strengths

| Strength | Evidence | Why it matters |
|---|---|---|
| {strength} | `{file}:{line}` | {product implication} |

## Weaknesses And Gaps

| Gap | Evidence | Opportunity |
|---|---|---|
| {gap} | `{file}:{line}` or `待验证: {next check}` | {opportunity} |

## Comparison With {Our Product}

| Dimension | Competitor | Source | Our product | Source |
|---|---|---|---|---|
| {dimension} | {value} | `{file}:{line}` | {value} | `{file}:{line}` |

## Recent Change Signal

| Signal | Value | Source |
|---|---|---|
| Latest commit | `{hash} {date} {subject}` | `git log -1` |
| Recent release | {value or 待验证} | {source or next check} |
| Active issues | {value or 待验证} | {GitHub API, retrieved YYYY-MM-DD} |

## Opportunities

| Opportunity | Evidence base | Confidence | Next action |
|---|---|---|---|
| {opportunity} | {source rows} | High/Medium/Low | {specific action} |

## Risks And Assumptions

| Item | What is known | What still needs verification | Next check |
|---|---|---|---|
| {risk/assumption} | {evidence} | {unknown} | {command/source to check} |

## Source Reading Log

| File | Why read | Key finding | Citation |
|---|---|---|---|
| `{file}` | {reason} | {finding} | `{file}:{start}-{end}` |
