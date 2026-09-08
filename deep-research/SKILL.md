---
name: deep-research
description: >-
  Generate format-controlled research reports with evidence tracking, citations, source governance, and multi-pass synthesis.
  This skill should be used when users request a research report, literature review, market or industry analysis,
  competitive landscape, policy or technical brief. Triggers: "帮我调研一下", "深度研究", "综述报告", "深入分析",
  "research this topic", "write a report on", "survey the literature on", "competitive analysis of",
  "技术选型分析", "竞品研究", "政策分析", "行业报告".
---

# Deep Research

Create high-fidelity research reports with strict format control, evidence mapping, source governance, and multi-pass synthesis.

## Architecture: Lead Agent + Subagents

```
Lead Agent (coordinator — minimizes raw search context)
  |
  P0: Environment + source policy setup
  |
  P1: Question and claim map (decision questions, evidence routes, stop rules)
  |
  Dispatch ──→ Subagent A ──→ writes task-a.md ──┐
           ──→ Subagent B ──→ writes task-b.md ──┤ (parallel)
           ──→ Subagent C ──→ writes task-c.md ──┘
  |                                               |
  |     research-notes/  <────────────────────────┘
  |
  P2: Build evidence packets + citation registry
  P3: Evidence-mapped outline with counter-evidence and unknowns
  P4: Draft from evidence packets; reopen decisive originals
  P5: Counter-review (claims, confidence, alternatives)
  P6: Verify every load-bearing claim and exact fact
  P7: Polish → final report with confidence markers
```

**Context discipline:** Keep raw search-result noise in task workspaces. Pass evidence packets to the lead agent, including locators and short source excerpts. Notes are routing aids, not authorities: the lead agent must open the original source for every load-bearing claim, conflicting claim, and exact figure/date/quotation used in the report.

## Mode Selection

Determine the research mode before starting:

| Dimension | Options |
|-----------|---------|
| **Topic Mode** | Enterprise Research (company/corporation) OR General Research (industry/policy/tech) |
| **Depth Mode** | Standard (multiple decision questions or contested evidence) OR Lightweight (one bounded question with a small evidence surface) |

- **Enterprise Research Mode**: Question-led company research with optional analysis frameworks selected only when they help answer the decision
- **General Research Mode**: Standard P0-P7 research pipeline with source governance
- **Depth Selection**: Choose from the number and consequence of unresolved questions, not prompt length, task count, or a target word count

## Source Governance (V6)

### Source Accessibility Classification

Classify every source by accessibility:

| Accessibility | Definition | Examples | Usage Rule |
|--------------|------------|----------|------------|
| `public` | Available to any external researcher without authentication | Public websites, news articles, WHOIS (without privacy), academic papers | ✅ Always allowed |
| `semi-public` | Requires registration or limited access | LinkedIn profiles, Crunchbase basic, industry reports (free tier) | ✅ Allowed with disclosure |
| `exclusive-user-provided` | User's paid subscriptions, private APIs, proprietary databases | Crunchbase Pro, PitchBook, private data feeds, internal databases | ✅ **ALLOWED** for third-party research |
| `authorized-first-party` | User-authorized records about the user's own organization, transactions, or work | Contracts, invoices, CRM records, meeting transcripts | ✅ May establish internal business facts; label provenance |

**First-party boundary:** User-authorized records may establish what the organization did, agreed, paid, delivered, or observed. They do not count as independent external validation of market standing, customer sentiment, regulatory compliance, or third-party claims. Never relabel an internal record as an external finding.

**✅ EXCLUSIVE INFORMATION ADVANTAGE**: You SHOULD:
- Use user's Crunchbase Pro to research competitors
- Use user's proprietary databases for market research
- Use user's private APIs for investment analysis
- Leverage any exclusive source user provides for third-party research

### Source Type Labels

Every source MUST also be tagged with:

| Label | Definition | Examples |
|-------|------------|----------|
| `official` | Primary source, official documentation | Company SEC filings, government reports, official blog |
| `academic` | Peer-reviewed research | Journal articles, conference papers, dissertations |
| `secondary-industry` | Professional analysis | Industry reports, analyst coverage, trade publications |
| `journalism` | News reporting | Reputable media outlets, investigative journalism |
| `community` | User-generated content | Forums, reviews, social media, Q&A sites |
| `other` | Uncategorized or mixed | Aggregators, unverified sources |

**Coverage diagnostics:** Track source counts, domains, source-type mix, and concentration to reveal thin coverage. Never pass or fail research from these totals alone. Gate on whether each decision question and load-bearing claim has fit-for-purpose evidence, whether counter-evidence was sought, and whether remaining unknowns are explicit.

## AS_OF Date Policy

Set `AS_OF` date explicitly at P0. For all time-sensitive claims:
- Include source publication date with every citation
- Downgrade confidence if source is older than relevant horizon
- Define a freshness horizon per claim class and flag material outside it; a universal age cutoff is only a diagnostic

## P0: Environment & Policy Setup

Check capabilities before starting:

| Check | Requirement | Impact if Missing |
|-------|-------------|-------------------|
| Required evidence channel available | Required | Narrow scope or stop with the affected questions marked unknown |
| Original-source retrieval available | Required for load-bearing claims | Do not promote summaries/snippets to final evidence |
| Subagent dispatch | Preferred | Degrade to sequential |
| Filesystem writable | Required | In-memory notes only |

Set policy variables:
- `AS_OF`: Today's date (YYYY-MM-DD) - mandatory for timed topics
- `MODE`: Standard (default) or Lightweight, justified by the question map
- `SOURCE_TYPE_POLICY`: Enforce official/academic/secondary/journalism/community/other labels
- `COUNTER_REVIEW_PLAN`: What evidence would overturn each provisional conclusion

Report: `[P0 complete] Subagent: {yes/no}. Mode: {standard/lightweight}. AS_OF: {YYYY-MM-DD}.`

When researching a specific company, use the specialized workflow to route evidence by question. Treat the six dimensions as a coverage map, not a mandatory report outline.

### Enterprise Workflow Overview

```
Enterprise Research Progress:
- [ ] E1: Intake — confirm company entity, research depth, format contract
- [ ] E2: Question-led evidence collection across relevant dimensions
  - [ ] D1: Company fundamentals (entity, founding, funding, ownership)
  - [ ] D2: Business & products (segments, products, revenue structure)
  - [ ] D3: Competitive position (industry rank, competitors, barriers)
  - [ ] D4: Financial & operations (3-year financials, efficiency metrics)
  - [ ] D5: Recent developments (6-month events, strategic signals)
  - [ ] D6: Internal/proprietary sources (or note limitation)
- [ ] E3: Optional analysis framework selected for the decision (or none)
- [ ] E4: Claim/evidence/unknown checks at each stage transition
- [ ] E5: Draft in the user's requested structure
- [ ] E6: Multi-pass drafting + UNION merge (same as general Step 6-7)
- [ ] E7: Present draft for human review and iterate
```

## P1: Research Task Board

Decompose the assignment into decision questions. Create tasks only where separate evidence routes or expertise make the work clearer.

Each task assignment includes:
- **Expert Role**: Specialist persona (e.g., "Policy Historian", "Ecosystem Mapper")
- **Objective**: One-sentence investigation goal
- **Queries**: 2-3 pre-planned search queries
- **Depth**: DEEP (fetch 2-3 full articles) or SCAN (snippets sufficient)
- **Output**: Path to research notes file
- **Parallel Group**: Group A (independent) or Group B (depends on Group A)
- **Decision Question**: The exact question this task helps answer
- **Load-Bearing Claims**: Provisional claims that would change the conclusion
- **Disconfirming Evidence**: What would weaken or overturn each claim
- **Evidence Route**: Which source owners or record systems can actually observe the fact
- **Stop Rule**: What counts as answered, contradicted, or still unknown

### Task Decomposition Rules

1. Each task covers one coherent sub-topic a specialist would own
2. Group A tasks must be logically independent; source independence is assessed by underlying evidence, ownership, and incentive, not domain count
3. Max 3 tasks per parallel group (concurrency limit)
4. Every task must flag time-sensitive claims, counter-evidence sought, and expected citation aging risk

### Enterprise Research Integration

When in Enterprise Research Mode, map questions to the relevant dimensions rather than creating all six tasks automatically:
- Task A: Company fundamentals (entity, founding, funding, ownership)
- Task B: Business & products (segments, products, revenue structure)
- Task C: Competitive position (industry rank, competitors, barriers)
- Task D: Financial & operations (3-year financials, efficiency metrics)
- Task E: Recent developments (6-month events, strategic signals)
- Task F: Authorized first-party records (when they can answer a business fact; never counted as external corroboration)

Report: `[P1 complete] {N} tasks in {M} groups. Dispatching Group A.`

---

## Enterprise Research Mode (Specialized Pipeline)

When researching a specific company, route each decision question through the relevant enterprise dimensions. Use the dimensions to find missing evidence paths; do not run all six or add quantified frameworks by default.

### E1: Intake

Same as P0/P1 above, plus:
- Confirm the exact legal entity being researched (parent vs subsidiary)
- Select research depth from the decision questions, evidence difficulty, and requested output; page counts are planning diagnostics only
- Identify any specific comparison targets (benchmark companies)

## P2: Dispatch + Investigate

Subagents execute tasks using [references/subagent_prompt.md](references/subagent_prompt.md) and output evidence packets in [references/research_notes_format.md](references/research_notes_format.md).

### With Subagents (Claude Code / Cowork / DeerFlow)

1. Dispatch Group A tasks in parallel (max 3 concurrent)
2. Each subagent searches, fetches, and tags source types
3. Every source line includes `Source-Type` and `As Of`
4. Wait for Group A completion
5. Dispatch Group B (can read Group A notes)

### Subagent Output Requirements

Each task-{id}.md must contain:
- **Question status**: answered / contradicted / unknown, with the stopping evidence
- **Sources section**: stable locators from actual retrievals with source type, accessibility, date, and source-family identity
- **Claim-evidence table**: claim, evidence excerpt/locator, scope, confidence, and whether the original was opened
- **Counter-evidence and unknowns**: what was sought, what was found, and what remains unresolved

### Without Subagents (Degraded Mode)

Lead agent executes tasks sequentially, acting as each specialist. Preserve raw search noise outside the final evidence packet; retain a query log when reproducibility matters.

### Enterprise Research: Six-Dimension Collection

Follow [references/enterprise_research_methodology.md](references/enterprise_research_methodology.md) for:
- Detailed collection workflow per dimension (query strategies, data fields, validation)
- Data source priority matrix (P0-P3 ranking)
- Claim-specific corroboration and conflict-handling rules

**Key principles**:
- Evidence-driven: every conclusion must trace to a citable source
- Corroboration: a second source adds weight only when it is independent of the same underlying disclosure or dataset
- Restrained judgment: mark speculation explicitly, avoid unsubstantiated claims
- Structured presentation: complex information via tables, lists, hierarchies

Run L1 quality check after completing each dimension (see enterprise_quality_checklist.md).

Status per task: `[P2 task-{id} complete] {N} sources, {M} findings.`
Status all: `[P2 complete] {N} tasks done, {M} total sources. Building registry.`

### E3: Select Analysis Frameworks Only When Useful

Load [references/enterprise_analysis_frameworks.md](references/enterprise_analysis_frameworks.md) only when the user's decision benefits from a framework. Use SWOT for strategic option framing, a risk matrix for decisions with explicit probability/impact inputs, and scoring only when weights and scales are defensible. Omit the framework rather than fabricate entries or precision.

Run L2 quality check after analysis is complete.

### E4: Quality Control

Three-level checks from [references/enterprise_quality_checklist.md](references/enterprise_quality_checklist.md):
- **L1 (Data)**: Source count, attribution, cross-validation, timeliness
- **L2 (Analysis)**: Decision-question coverage, claim support, counter-evidence, and framework fitness when a framework is used
- **L3 (Document)**: Structure compliance, format consistency, readability, appendices

### E5: Draft Using Enterprise Template

Use the 7-chapter enterprise report template from enterprise_quality_checklist.md only when it matches the requested decision. Otherwise adapt the structure around the question map.
1. Company Overview
2. Business & Product Structure
3. Market & Competitive Position
4. Financial & Operations Analysis
5. Risks & Concerns
6. Recent Developments
7. Comprehensive Assessment & Conclusion

Plus appendices: Data Source Index, Glossary, Disclaimer.

### E3-E7: Enterprise Analysis, Drafting, and Review

- **E3: Structured Analysis** — Select a framework from [references/enterprise_analysis_frameworks.md](references/enterprise_analysis_frameworks.md) only when it improves the decision and its inputs are defensible; otherwise use a claim-evidence table
- **E4: Quality Control** — Run L1/L2/L3 checks per [references/enterprise_quality_checklist.md](references/enterprise_quality_checklist.md)
- **E5: Draft** — Use 7-chapter enterprise template
- **E6-E7: Multi-Pass Drafting and Review** — Same as P4-P7 below

---

## P3: Citation Registry + Source Governance

Lead agent reads all task notes and builds unified registry.

### Registry Process

1. Read every task file's claim-evidence table and sources
2. Merge sources; deduplicate URLs but also group multiple publications derived from the same study, filing, press release, dataset, interview, or sponsor as one evidence family
3. Assign sequential [n] numbers by first appearance
4. Tag: source_type, accessibility, as_of date, evidence family, authority, independence limits, and task id
5. Build a claim-coverage matrix: supporting evidence, disconfirming evidence, decisive original checked, and remaining unknown
6. Record excluded sources with reasons. Do not exclude a source merely for failing an arbitrary score; restrict it to claims it can support

### Registry Output Format

```
CITATION REGISTRY

Approved:
[1] Author/Org — Title | URL | Source-Type: official | Accessibility: public | Evidence-Family: filing-123 | Date: 2026-03-01 | task-a
[2] ...

Dropped:
x Source | URL | Source-Type: secondary-industry | Accessibility: public | Evidence-Family: unknown | Reason: original record could not be retrieved; summary cannot carry the claim

Diagnostics: {approved}/{total}, {N} domains, {N} independent evidence families, source-type mix
Coverage: {answered}/{total questions}; {N} load-bearing claims unresolved
```

**Critical rule:** These [n] are FINAL. P5 may only cite from Approved list. Dropped sources never reappear.

**Authorized first-party handling**: When researching the user's own organization or assets:
1. Use authorized original records for internal business facts they directly record
2. Label them `authorized-first-party` and state whose record it is
3. Seek an external source only when the claim requires external corroboration
4. Keep the conclusion explicit: internally established, externally corroborated, conflicted, or externally unknown

**Exclusive source handling**: When user EXPLICITLY PROVIDES their paid subscriptions or private APIs for third-party research (e.g., "Use my Crunchbase Pro to research competitors"), you SHOULD:
1. Accept it as "exclusive-user-provided" accessibility
2. Use it as competitive advantage
3. Cite it properly in registry
4. If no independent equivalent exists, preserve the source's valid first-party scope and mark the external claim unknown

Report: `[P3 complete] {answered}/{total} questions answered. {N} load-bearing claims supported, {M} unresolved. Source totals are diagnostics.`

### Handling Information Black Box

When researching entities with no public footprint:

**What an external researcher would find:**
- WHOIS: Privacy protected → No owner info
- Web search: No news, no press releases
- Social media: No company pages
- Business registries: No public API or requires local access
- Result: **Complete information black box**

**Correct response:**
```
Findings: NO PUBLIC INFORMATION AVAILABLE

Sources checked:
- WHOIS (public): Privacy protected [failed]
- Company registry (public): Access denied/No API [failed]
- News media: No coverage [failed]
- Corporate website: Placeholder only [minimal]

Verdict: UNABLE TO VERIFY COMPANY EXISTENCE from external perspective
Sources found: 0 (or minimal, e.g., only WHOIS showing domain exists)
Confidence: N/A - Insufficient evidence
```

**DO NOT:**
- ❌ Describe an internally established fact as independently externally corroborated
- ❌ Assume the company exists based on domain registration alone
- ❌ Fill missing data with speculation
- ❌ Discard an authorized first-party record when it directly establishes an internal business fact

**DO:**
- ✅ Clearly state what an external researcher can/cannot verify
- ✅ Report authorized first-party facts as internally established, separately from external visibility
- ✅ Document all failed search attempts
- ✅ Mark claims as [unverified] or omit entirely
- ✅ Narrow or stop when evidence cannot answer the decision question
- ✅ Recommend direct contact for due diligence

---

## P4: Evidence-Mapped Outline

Lead agent reads evidence packets + registry to build the outline, then reopens decisive originals.

1. Identify cross-task patterns
2. Design sections topic-first, not task-order-first
3. Map each section to specific findings with source numbers
4. Flag sections needing counter-review
5. Mark recency-sensitive claims with AS_OF checks
6. Mark every load-bearing claim as supported / contradicted / unknown

Outline format:
```
## N. {Section Title}
Sources: [1][3][7] from tasks a, b
Claims: {claim from task-a finding 3}, {claim from task-b finding 1}
Counter-claim candidates: {alternative explanations}
Recency checks: {source dates + AS_OF}
Gaps: {limited official evidence}
```

---

## P5: Draft from Notes

Write section by section using [references/report_template_v6.md](references/report_template_v6.md), adapting it to the user's format contract.

**Rules:**
- Every factual claim needs citation [n]
- Numbers/percentages must have source
- Add **confidence marker** per section: High/Medium/Low with rationale
- Add **counter-claim sentence** when evidence conflicts
- New sources may enter only through the same registry and verification path
- Use [unverified] for unsupported statements

**Anti-hallucination:**
- Lead agent never invents URLs; every locator must come from an actual retrieval
- Lead agent never treats notes as proof; reopen the original for load-bearing claims, conflicts, exact numbers/dates, and quotations
- Lead agent never fabricates data; unsupported claims remain unknown or are omitted

Status: `[P5 in progress] {N}/{M} sections, ~{words} words.`

---

## P6: Counter-Review (Mandatory)

For each major conclusion, perform opposite-view checks. These checks do not automatically require another agent or a team; use independent reviewers only when the user request or applicable workspace instructions call for them:

1. **Could the conclusion be wrong?**
2. **Which high-impact claims depend on one evidence family, even if many domains repeat it?**
3. **Which claims lack a source that can directly observe the fact?**
4. **Are stale sources used for time-sensitive claims?**
5. **Report only evidence-backed issues; zero findings is a valid outcome.** State unresolved uncertainty explicitly. Do not invent issues or repeat a completed check solely to reach an issue count.

### Using Counter-Review Team (Optional)

For comprehensive parallel review, use the Counter-Review Team:

```bash
# 1. Prepare inputs
counter-review-inputs/
  ├── draft_report.md
  ├── citation_registry.md
  ├── task-notes/
  └── p0_config.md

# 2. Dispatch to 4 specialist agents in parallel
SendMessage to: claim-validator
SendMessage to: source-diversity-checker
SendMessage to: recency-validator
SendMessage to: contradiction-finder

# 3. Wait for all specialists to complete

# 4. Send to coordinator for synthesis
SendMessage to: counter-review-coordinator
  inputs: [4 specialist reports]

# 5. Receive final P6 Counter-Review Report
```

See [references/counter_review_team_guide.md](references/counter_review_team_guide.md) for detailed usage.

### Manual Counter-Review (Default)

When a review team has not been selected, perform these evidence checks directly. Obtain individual independent review if the user request or applicable workspace instructions require it:
- Verify every load-bearing claim against its decisive original
- Check whether corroborating sources are genuinely independent and able to observe the claim
- Verify AS_OF dates on time-sensitive claims
- Document opposing interpretations

### Output

Include only evidence-backed controversies in the final report. Use numbered entries only when such controversies exist. If none are established, state that explicitly; never fill placeholder disputes to satisfy the template. Report unresolved uncertainty separately, or state that none remains.

```
## 核心争议 / Key Controversies
未发现有证据支持的核心争议。
未解决的不确定性：无。
```

The example above applies only when both statements are supported by the completed checks; otherwise list the actual controversies or unresolved questions.

Report: `[P6 complete] {N} issues found: {critical} critical, {high} high, {medium} medium.`

---

## P7: Verify

Cross-check before finalization:

1. **Registry cross-check:** List every [n] in report vs approved registry
2. **Load-bearing check:** Trace every decisive conclusion, exact figure/date/quotation, and disputed fact to the original source
3. **Sample low-impact claims:** Use spot checks only as a diagnostic; expand to the full affected class when one fails
4. **Validate no dropped source resurrected**
5. **Check evidence-family concentration** for key claims

Report: `[P7 complete] {N} spot-checks, {M} violations fixed.`

---

## Output Requirements

- Match the requested language and tone
- Preserve technical terms in English
- Respect the report spec and formatting rules
- Include a references section or bibliography

## Reference Files

### Core V6 Pipeline References

| File | When to Load |
| --- | --- |
| [source_accessibility_policy.md](references/source_accessibility_policy.md) | **P0 (CRITICAL)**: Source classification rules - read first |
| [subagent_prompt.md](references/subagent_prompt.md) | P2: Task dispatch to subagents |
| [research_notes_format.md](references/research_notes_format.md) | P2: Subagent output format |
| [report_template_v6.md](references/report_template_v6.md) | P5: Draft with confidence markers and counter-review |
| [quality_gates.md](references/quality_gates.md) | All phases: Quality thresholds and anti-hallucination checks |

### General Research References

| File | When to Load |
| --- | --- |
| [research_report_template.md](references/research_report_template.md) | Build outline and draft structure |
| [formatting_rules.md](references/formatting_rules.md) | Enforce section formatting and citation rules |
| [source_quality_rubric.md](references/source_quality_rubric.md) | Score and triage sources |
| [research_plan_checklist.md](references/research_plan_checklist.md) | Build research plan and query set |
| [completeness_review_checklist.md](references/completeness_review_checklist.md) | Review for coverage, citations, and compliance |

### Enterprise Research References (load when in Enterprise Research Mode)

| File | When to Load |
| --- | --- |
| [enterprise_research_methodology.md](references/enterprise_research_methodology.md) | Six-dimension data collection workflow, source priority, cross-validation rules |
| [enterprise_analysis_frameworks.md](references/enterprise_analysis_frameworks.md) | SWOT template, competitive barrier quantification, risk matrix, comprehensive scoring |
| [enterprise_quality_checklist.md](references/enterprise_quality_checklist.md) | L1/L2/L3 quality checks, per-dimension checklists, 7-chapter report template |

## Anti-Patterns

- Single-pass drafting without parallel complete passes
- Splitting passes by section instead of full report drafts
- Ignoring the format contract or user template
- Claims without citations or evidence table mapping
- Mixing conflicting dates without calling out discrepancies
- Copying external AI output without verification
- Deleting intermediate drafts or raw research outputs
- **Lead agent trusting notes as authority** — use packets for routing, then reopen decisive originals
- **Inventing URLs** — only use URLs from actual search results
- **Resurrecting dropped sources** — dropped in P3 never reappear
- **Missing AS_OF for time-sensitive claims** — always include source date
- **Skipping evidence checks** — complete P6, report only supported findings, and allow zero issues when no issue is established.
- **FIRST-PARTY OVERCLAIM** — authorized records can establish internal business facts but cannot impersonate external validation
- **IGNORING EXCLUSIVE SOURCES** — when user provides Crunchbase Pro etc. for competitor research, USE IT

## Next Step: Verify and Deliver

After completing research, suggest verification and output:

```
Research report complete: [N] sources cited, [M] claims made.

Options:
A) Verify facts — run /fact-checker on the report (Recommended)
B) Create slides — pass the verified findings and citation registry to the active presentation workflow
C) Export as PDF — run /daymade-docs:pdf-creator for formal delivery
D) No thanks — the report is ready as-is
```
