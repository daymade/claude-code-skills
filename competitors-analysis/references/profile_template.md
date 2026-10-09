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

## Citation Readback

Use this section when a judgment depends on retrieved content or a product's
answer/citation behavior. Follow the worked check in
[analysis_checklist.md](analysis_checklist.md#citation-readback-and-counterevidence).
Record the source version once in the source register or snapshot authority and
reference it here.

| Claim / citation | Evidence version reference | Locator | Original and surrounding context read back | Availability observation |
|---|---|---|---|---|
| {claim} | {source-register row or snapshot identity} | {file lines / segment / timestamp; omit unavailable coordinates} | {short excerpt supporting or challenging the claim, or exact read failure} | {checked date, route and readable / inaccessible / not checked} |

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

Include this section only when the request names our product or the current
project's authoritative entry confirms it. Cite that scope source and distinguish
product requirements from implemented behavior. Omit this section for a standalone
request or unresolved our-product context; complete the repository profile anyway.

Comparison baseline: {link to our product's contract and named acceptance
scenario}; {link to the existing artifact/workflow that could meet it};
{evidence of implemented and actually used behavior, or explicit unknown}.

| Dimension | Competitor | Source | Our product | Source |
|---|---|---|---|---|
| {dimension} | {value} | `{file}:{line}` | {value} | `{file}:{line}` |

## Recent Change Signal

| Signal | Value | Source |
|---|---|---|
| Recent release | {value or 待验证} | {source or next check} |
| Active issues | {value or 待验证} | {GitHub API, retrieved YYYY-MM-DD} |

## Opportunities

For each material opportunity, fill the decision chain in
[landscape_synthesis.md](landscape_synthesis.md#build-a-small-number-of-decision-bearing-judgments):

- **Observation:** {reference evidence rows, including citation readback when relevant}.
- **Explanation:** {labeled inference, scope and confidence}.
- **Choice and consequence:** {preserve / reuse / defer / change, linked to the
  baseline acceptance scenario and existing assets; concrete value and cost}.
- **Challenge:** {counterevidence or alternative explanation, and the observable
  result that would overturn the choice; cheapest next check if undecidable}.

## Risks And Assumptions

| Item | What is known | What still needs verification | Next check |
|---|---|---|---|
| {risk/assumption} | {evidence} | {unknown} | {command/source to check} |
