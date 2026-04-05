---
name: deep-research
description: |
  Generate format-controlled research reports with evidence tracking, citations, source governance, and multi-pass synthesis.
  This skill should be used when users request a research report, literature review, market or industry analysis,
  competitive landscape, policy or technical brief. Triggers: "帮我调研一下", "深度研究", "综述报告", "深入分析",
  "research this topic", "write a report on", "survey the literature on", "competitive analysis of",
  "技术选型分析", "竞品研究", "政策分析", "行业报告".
  V6 adds: source-type governance, AS_OF freshness checks, mandatory counter-review, and citation registry. V6.1 adds: source accessibility (circular verification forbidden, exclusive advantage encouraged).
---

# Deep Research

Create high-fidelity research reports with strict format control, evidence mapping, source governance, and multi-pass synthesis.

## Architecture: Lead Agent + Subagents

```
Lead Agent (coordinator — minimizes raw search context)
  |
  P0: Environment + source policy setup
  |
  P1: Research Task Board (roles, queries, parallel groups)
  |
  Dispatch ──→ Subagent A ──→ writes task-a.md ──┐
           ──→ Subagent B ──→ writes task-b.md ──┤ (parallel)
           ──→ Subagent C ──→ writes task-c.md ──┘
  |                                               |
  |     research-notes/  <────────────────────────┘
  |
  P2: Build citation registry with source_type + as_of + authority
  P3: Evidence-mapped outline with counter-claim flags
  P4: Draft from notes (never from raw search results)
  P5: Counter-review (claims, confidence, alternatives)
  P6: Verify (every [n] in registry, traceability check)
  P7: Polish → final report with confidence markers
```

**Context efficiency:** Subagents' raw search results stay in their context and are discarded. Lead agent sees only distilled notes (~60-70% context reduction).

## Mode Selection

Determine the research mode before starting:

| Dimension | Options |
|-----------|---------|
| **Topic Mode** | Enterprise Research (company/corporation) OR General Research (industry/policy/tech) |
| **Depth Mode** | Standard (5-6 tasks, 3000-8000 words) OR Lightweight (3-4 tasks, 2000-4000 words) |

- **Enterprise Research Mode**: Six-dimension data collection with structured analysis frameworks (SWOT, risk matrix, competitive barrier quantification)
- **General Research Mode**: Standard P0-P7 research pipeline with source governance
- **Depth Selection**: Lightweight for single entity/concept < 30 words; Standard for multi-entity comparison or "深入"/"comprehensive" requests

## Source Governance (V6)

### Source Accessibility Classification

**CRITICAL RULE**: Every source must be classified by accessibility:

| Accessibility | Definition | Examples | Usage Rule |
|--------------|------------|----------|------------|
| `public` | Available to any external researcher without authentication | Public websites, news articles, WHOIS (without privacy), academic papers | ✅ Always allowed |
| `semi-public` | Requires registration or limited access | LinkedIn profiles, Crunchbase basic, industry reports (free tier) | ✅ Allowed with disclosure |
| `exclusive-user-provided` | User's paid subscriptions, private APIs, proprietary databases | Crunchbase Pro, PitchBook, private data feeds, internal databases | ✅ **ALLOWED** for third-party research |
| `private-user-owned` | User's own accounts when researching themselves | User's registrar for user's own company, user's bank for user's own finances | ❌ **FORBIDDEN** - circular verification |

**⚠️ CIRCULAR VERIFICATION BAN**: You must NOT:
- Use user's private data to "discover" what they already know about themselves
- Research user's own company by accessing user's private accounts
- Present user's private knowledge as "research findings"

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

**Quality Gates:**
- Standard mode: ≥30% official sources in final approved set
- Lightweight mode: ≥20% official sources
- Maximum single-source share: ≤25% (Standard), ≤30% (Lightweight)
- Minimum unique domains: 5 (Standard), 3 (Lightweight)

## AS_OF Date Policy

Set `AS_OF` date explicitly at P0. For all time-sensitive claims:
- Include source publication date with every citation
- Downgrade confidence if source is older than relevant horizon
- Flag stale sources in registry (studies >3 years, news >6 months for fast-moving topics)

## P0: Environment & Policy Setup

Check capabilities before starting:

| Check | Requirement | Impact if Missing |
|-------|-------------|-------------------|
| web_search available | Required | Stop - cannot proceed |
| web_fetch available | Required for DEEP tasks | SCAN-only mode |
| Subagent dispatch | Preferred | Degrade to sequential |
| Filesystem writable | Required | In-memory notes only |

Set policy variables:
- `AS_OF`: Today's date (YYYY-MM-DD) - mandatory for timed topics
- `MODE`: Standard (default) or Lightweight
- `SOURCE_TYPE_POLICY`: Enforce official/academic/secondary/journalism/community/other labels
- `COUNTER_REVIEW_PLAN`: What opposing interpretation to test

Report: `[P0 complete] Subagent: {yes/no}. Mode: {standard/lightweight}. AS_OF: {YYYY-MM-DD}.`

When researching a specific company/enterprise, follow this specialized workflow that ensures six-dimension coverage, quantified analysis frameworks, and three-level quality control.

### Enterprise Workflow Overview

```
Enterprise Research Progress:
- [ ] E1: Intake — confirm company entity, research depth, format contract
- [ ] E2: Six-dimension data collection (parallel where possible)
  - [ ] D1: Company fundamentals (entity, founding, funding, ownership)
  - [ ] D2: Business & products (segments, products, revenue structure)
  - [ ] D3: Competitive position (industry rank, competitors, barriers)
  - [ ] D4: Financial & operations (3-year financials, efficiency metrics)
  - [ ] D5: Recent developments (6-month events, strategic signals)
  - [ ] D6: Internal/proprietary sources (or note limitation)
- [ ] E3: Structured analysis frameworks
  - [ ] SWOT analysis (evidence-backed, 4 quadrants × 3-5 entries)
  - [ ] Competitive barrier quantification (7 dimensions, weighted score)
  - [ ] Risk matrix (8 categories, probability × impact)
  - [ ] Comprehensive scorecard (6 dimensions, weighted total)
- [ ] E4: L1/L2/L3 quality checks at each stage transition
- [ ] E5: Draft report using 7-chapter enterprise template
- [ ] E6: Multi-pass drafting + UNION merge (same as general Step 6-7)
- [ ] E7: Present draft for human review and iterate
```

## P1: Research Task Board

Decompose the research question into 4-6 investigation tasks (Standard) or 3-4 tasks (Lightweight).

Each task assignment includes:
- **Expert Role**: Specialist persona (e.g., "Policy Historian", "Ecosystem Mapper")
- **Objective**: One-sentence investigation goal
- **Queries**: 2-3 pre-planned search queries
- **Depth**: DEEP (fetch 2-3 full articles) or SCAN (snippets sufficient)
- **Output**: Path to research notes file
- **Parallel Group**: Group A (independent) or Group B (depends on Group A)

### Task Decomposition Rules

1. Each task covers one coherent sub-topic a specialist would own
2. Group A tasks must be independent and source-diverse
3. Max 3 tasks per parallel group (concurrency limit)
4. Every task must flag time-sensitive claims and expected citation aging risk

### Enterprise Research Integration

When in Enterprise Research Mode, task board maps to six dimensions:
- Task A: Company fundamentals (entity, founding, funding, ownership)
- Task B: Business & products (segments, products, revenue structure)
- Task C: Competitive position (industry rank, competitors, barriers)
- Task D: Financial & operations (3-year financials, efficiency metrics)
- Task E: Recent developments (6-month events, strategic signals)
- Task F: Internal/proprietary sources (or document limitation)

Report: `[P1 complete] {N} tasks in {M} groups. Dispatching Group A.`

---

## Enterprise Research Mode (Specialized Pipeline)

When researching a specific company/enterprise, follow this specialized workflow that ensures six-dimension coverage, quantified analysis frameworks, and three-level quality control.

### E1: Intake

Same as P0/P1 above, plus:
- Confirm the exact legal entity being researched (parent vs subsidiary)
- Select research depth: Quick scan (3-5 pages) / Standard (10-20 pages) / Deep (20-40 pages)
- Identify any specific comparison targets (benchmark companies)

## P2: Dispatch + Investigate

Subagents execute tasks using [references/subagent_prompt.md](references/subagent_prompt.md) and output to [references/research_notes_format.md](references/research_notes_format.md).

### With Subagents (Claude Code / Cowork / DeerFlow)

1. Dispatch Group A tasks in parallel (max 3 concurrent)
2. Each subagent searches, fetches, and tags source types
3. Every source line includes `Source-Type` and `As Of`
4. Wait for Group A completion
5. Dispatch Group B (can read Group A notes)

### Subagent Output Requirements

Each task-{id}.md must contain:
- **Sources section**: URLs from actual search results with Source-Type, As Of, Authority (1-10)
- **Findings section**: Max 10 one-sentence facts with source numbers
- **Deep Read Notes** (DEEP tasks): 2-3 sources read in full with key data/insights
- **Gaps section**: What was searched but NOT found, alternative interpretations

### Without Subagents (Degraded Mode)

Lead agent executes tasks sequentially, acting as each specialist. Raw search results are discarded after writing notes.

### Enterprise Research: Six-Dimension Collection

Follow [references/enterprise_research_methodology.md](references/enterprise_research_methodology.md) for:
- Detailed collection workflow per dimension (query strategies, data fields, validation)
- Data source priority matrix (P0-P3 ranking)
- Cross-validation rules (min sources, max deviation thresholds)

**Key principles**:
- Evidence-driven: every conclusion must trace to a citable source
- Multi-source validation: key data requires ≥2 independent sources
- Restrained judgment: mark speculation explicitly, avoid unsubstantiated claims
- Structured presentation: complex information via tables, lists, hierarchies

Run L1 quality check after completing each dimension (see enterprise_quality_checklist.md).

Status per task: `[P2 task-{id} complete] {N} sources, {M} findings.`
Status all: `[P2 complete] {N} tasks done, {M} total sources. Building registry.`

### E3: Structured Analysis Frameworks

Apply frameworks from [references/enterprise_analysis_frameworks.md](references/enterprise_analysis_frameworks.md) in order:
1. **SWOT analysis** — each entry with evidence + source + impact assessment
2. **Competitive barrier quantification** — 7 dimensions with weighted scoring → A+/A/B+/B/C+/C rating
3. **Risk matrix** — 8 mandatory categories, probability × impact → Red/Yellow/Green
4. **Comprehensive scorecard** — 6-dimension weighted total → X/10

Run L2 quality check after analysis is complete.

### E4: Quality Control

Three-level checks from [references/enterprise_quality_checklist.md](references/enterprise_quality_checklist.md):
- **L1 (Data)**: Source count, attribution, cross-validation, timeliness
- **L2 (Analysis)**: SWOT completeness, risk coverage, barrier scoring, conclusion support
- **L3 (Document)**: Structure compliance, format consistency, readability, appendices

### E5: Draft Using Enterprise Template

Use the 7-chapter enterprise report template from enterprise_quality_checklist.md:
1. Company Overview
2. Business & Product Structure
3. Market & Competitive Position
4. Financial & Operations Analysis
5. Risks & Concerns
6. Recent Developments
7. Comprehensive Assessment & Conclusion

Plus appendices: Data Source Index, Glossary, Disclaimer.

### E3-E7: Enterprise Analysis, Drafting, and Review

- **E3: Structured Analysis** — Apply frameworks from [references/enterprise_analysis_frameworks.md](references/enterprise_analysis_frameworks.md)
- **E4: Quality Control** — Run L1/L2/L3 checks per [references/enterprise_quality_checklist.md](references/enterprise_quality_checklist.md)
- **E5: Draft** — Use 7-chapter enterprise template
- **E6-E7: Multi-Pass Drafting and Review** — Same as P4-P7 below

---

## P3: Citation Registry + Source Governance

Lead agent reads all task notes and builds unified registry.

### Registry Process

1. Read every task file's `## Sources` section
2. Merge all sources, deduplicate by URL
3. Assign sequential [n] numbers by first appearance
4. Tag: source_type, as_of date, authority score (1-10), task id
5. **Apply quality gates:**
   - Standard: ≥12 approved sources, ≥5 unique domains, ≥30% official
   - Lightweight: ≥6 approved sources, ≥3 unique domains, ≥20% official
   - Max single-source share: ≤25% (Standard), ≤30% (Lightweight)
6. **Drop sources** below threshold and list them explicitly

### Registry Output Format

```
CITATION REGISTRY

Approved:
[1] Author/Org — Title | URL | Source-Type: official | Accessibility: public | Date: 2026-03-01 | Auth: 8 | task-a
[2] ...

Dropped:
x Source | URL | Source-Type: community | Accessibility: privileged | Auth: 3 | Reason: PRIVILEGED SOURCE - NOT ALLOWED

Stats: {approved}/{total}, {N} domains, official_share {xx}%
Privileged sources rejected: {N}
```

**Critical rule:** These [n] are FINAL. P5 may only cite from Approved list. Dropped sources never reappear.

**Circular verification handling**: When researching the user's own company/assets, if you discover data in user's private accounts (e.g., user's domain registrar showing they own domains), you MUST:
1. Reject it from the registry (user already knows this)
2. Note it as "CIRCULAR - USER ALREADY KNOWS" in Dropped
3. Search for equivalent PUBLIC sources (e.g., public WHOIS, news articles)
4. Report from external investigator perspective only

**Exclusive source handling**: When user EXPLICITLY PROVIDES their paid subscriptions or private APIs for third-party research (e.g., "Use my Crunchbase Pro to research competitors"), you SHOULD:
1. Accept it as "exclusive-user-provided" accessibility
2. Use it as competitive advantage
3. Cite it properly in registry
4. If no public equivalent exists, mark as [unverified] or omit the claim

Report: `[P3 complete] {approved}/{total} sources. {N} domains. Official share: {xx}%. Privileged rejected: {N}.`

### Handling Information Black Box

When researching entities with no public footprint (like the "字节跳动子公司" example):

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
- ❌ Use user's own credentials to "fill in the gaps"
- ❌ Assume the company exists based on domain registration alone
- ❌ Fill missing data with speculation
- ❌ Claim to have "verified" information you accessed through privileged means

**DO:**
- ✅ Clearly state what an external researcher can/cannot verify
- ✅ Document all failed search attempts
- ✅ Mark claims as [unverified] or omit entirely
- ✅ Downgrade mode to Lightweight or stop if insufficient public sources
- ✅ Recommend direct contact for due diligence

---

## P4: Evidence-Mapped Outline

Lead agent reads notes + registry to build outline.

1. Identify cross-task patterns
2. Design sections topic-first, not task-order-first
3. Map each section to specific findings with source numbers
4. Flag sections needing counter-review
5. Mark recency-sensitive claims with AS_OF checks

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

Write section by section using [references/report_template_v6.md](references/report_template_v6.md).

**Rules:**
- Every factual claim needs citation [n]
- Numbers/percentages must have source
- Add **confidence marker** per section: High/Medium/Low with rationale
- Add **counter-claim sentence** when evidence conflicts
- No new sources may be introduced
- Use [unverified] for unsupported statements

**Anti-hallucination:**
- Lead agent never invents URLs — only from subagent notes
- Lead agent never fabricates data — mark [unverified] if number not in notes

Status: `[P5 in progress] {N}/{M} sections, ~{words} words.`

---

## P6: Counter-Review (Mandatory)

For each major conclusion, perform opposite-view checks:

1. **Could the conclusion be wrong?**
2. **Which high-impact claims depend on a single source?**
3. **Which claims lack official/academic support?**
4. **Are stale sources used for time-sensitive claims?**
5. **Find ≥3 issues** (re-examine if 0 found)

### Using Counter-Review Team (Recommended)

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

### Manual Counter-Review (Fallback)

If Counter-Review Team is unavailable, perform manual checks:
- Verify every high-confidence claim has ≥2 sources
- Check official/academic backing for key claims
- Verify AS_OF dates on time-sensitive claims
- Document opposing interpretations

### Output

Include in final report:
```
## 核心争议 / Key Controversies
- **争议 1:** [主张 A 与反向证据 B 对比] [n][m]
- **争议 2:** ...
```

Report: `[P6 complete] {N} issues found: {critical} critical, {high} high, {medium} medium.`

---

## P7: Verify

Cross-check before finalization:

1. **Registry cross-check:** List every [n] in report vs approved registry
2. **Spot-check 5+ claims:** Trace to task notes
3. **Remove/fix non-traceable claims**
4. **Validate no dropped source resurrected**
5. **Check source concentration** for key claims

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
- **Lead agent reading raw search results** — only read subagent notes
- **Inventing URLs** — only use URLs from actual search results
- **Resurrecting dropped sources** — dropped in P3 never reappear
- **Missing AS_OF for time-sensitive claims** — always include source date
- **Skipping counter-review** — mandatory P6 must find ≥3 issues
- **CIRCULAR VERIFICATION** — never use user's private data to "discover" what they already know about themselves
- **IGNORING EXCLUSIVE SOURCES** — when user provides Crunchbase Pro etc. for competitor research, USE IT

## Next Step: Verify and Deliver

After completing research, suggest verification and output:

```
Research report complete: [N] sources cited, [M] claims made.

Options:
A) Verify facts — run /fact-checker on the report (Recommended)
B) Create slides — run /ppt-creator from the findings
C) Export as PDF — run /pdf-creator for formal delivery
D) No thanks — the report is ready as-is
```
