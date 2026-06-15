---
name: automotive-ve-ai-skills-kit
description: Convert automotive value engineering and VAVE workflows into reusable Claude Code skills with candidate scoring, opportunity-register drafting, SOP generation, adoption metrics, evidence-claim auditing, and human-review guardrails. Use for BOM reviews, quotation analysis, cost-opportunity workshops, VE meeting notes, resume or portfolio evidence checks, and AI productivity pilots in engineering or procurement teams.
---

# Automotive VE AI Skills Kit

## Overview

Convert automotive value engineering workflows into small, testable AI Skills. Use the skill to mine high-frequency work, rank Skill candidates, structure VAVE opportunity registers, draft SOPs, measure pilot adoption, and audit public claims without inventing cost, supplier, quality, engineering, or contribution conclusions.

## When To Use This Skill

- Analyze value engineering, VAVE, BOM review, quotation review, supplier collaboration, or cost-opportunity workflows.
- Turn interviews, meeting notes, or SOP fragments into Skill candidates and operating documents.
- Draft a VAVE opportunity register from approved or synthetic BOM, quotation, benchmark, and meeting-note inputs.
- Review AI Skill adoption feedback after a pilot.
- Audit resume, release, portfolio, or management-summary claims against evidence links and review status.
- Build a safe automotive VE productivity demo without proprietary data.

## Core Workflow

1. Mine the workflow: identify role, trigger, input, repeated actions, decisions, output, downstream user, rework causes, and sensitive data boundaries.
2. Score candidate workflows across frequency, time cost, standardization, risk control, data availability, visible benefit, and user willingness.
3. Productize the Skill with trigger scenario, target users, required inputs, workflow steps, output format, human-review gates, data boundaries, quality checks, and success metrics.
4. Draft outputs such as VAVE opportunity registers, SOPs, FAQs, checklists, and adoption reports.
5. Preserve human review by labeling conclusions as `Fact`, `Calculation`, `Hypothesis`, or `Needs confirmation`.
6. Audit public claims by linking each claim to source kind, evidence level, verdict, status, safe wording, and do-not-claim boundaries.

## Output Templates

### Skill Candidate Ranking

```markdown
| Scenario | Role | Score | Priority | Pain |
|---|---|---:|---|---|
```

### VAVE Opportunity Register

```markdown
| ID | Opportunity | Evidence Type | Potential Impact | Risk | Required Review | Next Action | Owner |
|---|---|---|---|---|---|---|---|
```

### Adoption Report

```markdown
| Metric | Before | After | Change | Status | Note |
|---|---:|---:|---:|---|---|
```

### Evidence Claim Matrix

```markdown
| Claim | Source | Evidence Level | Verdict | Status | Claim Level | Evidence | Safe Wording | Boundary |
|---|---|---|---|---|---|---|---|---|
```

## Guardrails

- Do not fabricate missing costs, supplier quotes, material specs, confirmed savings, or engineering feasibility conclusions.
- Use redacted or synthetic data unless the user confirms an approved enterprise environment.
- Mark uncertain items as assumptions or questions for validation.
- Keep expert judgment outside the AI output unless the source explicitly contains a verified decision.
- Avoid broad, high-risk automation as a first pilot.
- Do not describe open PRs as merged, accepted, or contributor status.
- Treat self-reported or marketing-only claims as weak unless backed by repository, platform, or independent evidence.

## Resources

- Read `references/methodology.md` for the six-step VE AI Skill workflow.
- See the reference project for scripts, examples, tests, and five standalone Skills: https://github.com/onyx679/automotive-ve-ai-skills-kit

