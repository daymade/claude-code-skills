---
name: deep-research
description: |
  Generate format-controlled research reports with evidence tracking, citations, and iterative review. This skill should be used when users request a research report, literature review, market or industry analysis, competitive landscape, policy or technical brief, or require a strict report template and section formatting that a single deepresearch pass cannot reliably enforce.
---

# Deep Research

Create high-fidelity research reports with strict format control, evidence mapping, and multi-pass synthesis.

## Quick Start

1. Clarify the report spec and format contract
2. Build a research plan and query set
3. Collect evidence with the deepresearch tool (multi-pass if needed)
4. Triage sources and build an evidence table
5. Draft the full report in multiple complete passes (parallel subagents)
6. UNION merge, enforce format compliance, verify citations
7. Present draft for human review and iterate

## Core Workflow

Copy this checklist and track progress:

```
Deep Research Progress:
- [ ] Step 1: Intake and format contract
- [ ] Step 2: Research plan and query set
- [ ] Step 3: Evidence collection (deepresearch tool)
- [ ] Step 4: Source triage and evidence table
- [ ] Step 5: Outline and section map
- [ ] Step 6: Multi-pass full drafting (parallel subagents)
- [ ] Step 7: UNION merge and format compliance
- [ ] Step 8: Evidence and citation verification
- [ ] Step 9: Present draft for human review and iterate
```

### Step 1: Intake and Format Contract

Establish the report requirements before any research:

- Confirm audience, purpose, scope, time range, and geography
- Lock output format: Markdown, DOCX, slides, or user-provided template
- Capture required sections and exact formatting rules
- Confirm citation style (footnotes, inline, numbered, APA, etc.)
- Confirm length targets per section
- Ask for any existing style guide or sample report

Create a concise report spec file:

```
Report Spec:
- Audience:
- Purpose:
- Scope:
- Time Range:
- Geography:
- Required Sections:
- Section Formatting Rules:
- Citation Style:
- Output Format:
- Length Targets:
- Tone:
- Must-Include Sources:
- Must-Exclude Topics:
```

If a user provides a template or an example report, treat it as a hard constraint and mirror the structure.

### Step 2: Research Plan and Query Set

Define the research strategy before calling tools:

- Break the main question into 3-7 subquestions
- Define key entities, keywords, and synonyms
- Identify primary sources vs secondary sources
- Define disqualifiers (outdated, low quality, opinion-only)
- Assemble a query set per section

Use [references/research_plan_checklist.md](references/research_plan_checklist.md) for guidance.

### Step 3: Evidence Collection (Deepresearch Tool)

Use the deepresearch tool to collect evidence and citations.

- Run multiple complete passes if coverage is uncertain
- Vary query phrasing to reduce blind spots
- Preserve raw tool output in files for traceability

**File structure (recommended):**
```
<output_dir>/research/<topic-name>/
  deepresearch_pass1.md
  deepresearch_pass2.md
  deepresearch_pass3.md
```

If deepresearch is unavailable, rely on user-provided sources only and state limitations explicitly.

### Step 4: Source Triage and Evidence Table

Normalize and score sources before drafting:

- De-duplicate sources across passes
- Score sources using [references/source_quality_rubric.md](references/source_quality_rubric.md)
- Build an evidence table mapping claims to sources

Evidence table minimum columns:

- Source ID
- Title
- Publisher
- Date
- URL or reference
- Quality tier (A/B/C)
- Notes

### Step 5: Outline and Section Map

Create an outline that enforces the format contract:

- Use the template in [references/research_report_template.md](references/research_report_template.md)
- Produce a section map with required elements per section
- Confirm ordering and headings match the report spec

### Step 6: Multi-Pass Full Drafting (Parallel Subagents)

Avoid single-pass drafting; generate multiple complete reports, then merge.

#### Preferred Strategy: Parallel Subagents (Complete Draft Each)

Use the Task tool to spawn parallel subagents with isolated context. Each subagent must:

- Load the report spec, outline, and evidence table
- Draft the FULL report (all sections)
- Enforce formatting rules and citation style

**Implementation pattern:**
```
Task(subagent_type="general-purpose", prompt="Draft complete report ...", run_in_background=false) -> version1.md
Task(subagent_type="general-purpose", prompt="Draft complete report ...", run_in_background=false) -> version2.md
Task(subagent_type="general-purpose", prompt="Draft complete report ...", run_in_background=false) -> version3.md
```

**Write drafts to files, not conversation context:**
```
<output_dir>/intermediate/<topic-name>/version1.md
<output_dir>/intermediate/<topic-name>/version2.md
<output_dir>/intermediate/<topic-name>/version3.md
```

### Step 7: UNION Merge and Format Compliance

Merge using UNION, never remove content without evidence-based justification:

- Keep all unique findings from all versions
- Consolidate duplicates while preserving the most detailed phrasing
- Ensure every claim in the merged draft has a cited source
- Enforce the exact section order, headings, and formatting
- Re-run formatting rules from [references/formatting_rules.md](references/formatting_rules.md)

### Step 8: Evidence and Citation Verification

Verify traceability:

- Every numeric claim has at least one source
- Every recommendation references supporting evidence
- No orphan claims without citations
- Dates and time ranges are consistent
- Conflicts are explicitly called out with both sources

Use [references/completeness_review_checklist.md](references/completeness_review_checklist.md).

### Step 9: Present Draft for Human Review and Iterate

Present the draft as a reviewable version:

- Emphasize that format compliance and factual accuracy need human review
- Accept edits to format, structure, and scope
- If the user provides another AI output, cross-compare and UNION merge

## Output Requirements

- Match the requested language and tone
- Preserve technical terms in English
- Respect the report spec and formatting rules
- Include a references section or bibliography

## Reference Files

| File | When to Load |
| --- | --- |
| [research_report_template.md](references/research_report_template.md) | Build outline and draft structure |
| [formatting_rules.md](references/formatting_rules.md) | Enforce section formatting and citation rules |
| [source_quality_rubric.md](references/source_quality_rubric.md) | Score and triage sources |
| [research_plan_checklist.md](references/research_plan_checklist.md) | Build research plan and query set |
| [completeness_review_checklist.md](references/completeness_review_checklist.md) | Review for coverage, citations, and compliance |

## Anti-Patterns

- Single-pass drafting without parallel complete passes
- Splitting passes by section instead of full report drafts
- Ignoring the format contract or user template
- Claims without citations or evidence table mapping
- Mixing conflicting dates without calling out discrepancies
- Copying external AI output without verification
- Deleting intermediate drafts or raw research outputs
