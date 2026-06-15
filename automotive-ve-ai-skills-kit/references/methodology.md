# Automotive VE AI Skill Methodology

## 1. Mine The Workflow

Capture role, trigger, inputs, repeated actions, decisions, outputs, downstream users, rework causes, and sensitive data boundaries.

## 2. Score Skill Candidates

Score from 1 to 5:

- frequency
- time cost
- standardization
- risk control
- data availability
- visible benefit
- user willingness

Priority bands:

- `pilot-now`: score >= 28
- `validate-next`: score 22-27
- `document-first`: score <= 21

## 3. Productize The Skill

Define trigger scenario, target users, required inputs, workflow steps, output format, human-review gates, data boundaries, quality checks, and success metrics.

## 4. Preserve Human Review

Use evidence labels:

- `Fact`: directly present in the source
- `Calculation`: derived from visible numbers and formulas
- `Hypothesis`: plausible but unverified
- `Needs confirmation`: requires a human owner

## 5. Measure Adoption

Track active users, repeat usage, task time, rework count, field completeness, missed confirmation questions, satisfaction, and issue fix rate.

## 6. Audit Evidence Claims

Before using project work in a resume, portfolio, release note, or management summary, break claims into atomic statements and classify each one.

Required fields:

- `source_kind`: platform record, repository artifact, independent source, self-reported, or mixed.
- `evidence_level`: `L4` for directly checkable platform/repository records, `L3` for multiple independent sources, `L2` for one credible third-party source, `L1` for self-reported or weak evidence.
- `verdict`: confirmed, largely credible, doubtful, or debunked.
- `evidence_status`: verified, open, pending-review, or missing.
- `claim_level`: resume-ready, boundary-only, or do-not-claim.

Rules:

- Do not claim open PRs as merged, accepted, or contributor status.
- Do not claim internal deployment, supplier quote handling, real BOM handling, or business impact without approved evidence.
- Use conservative wording such as "submitted PR", "published demo", "verified by CI", and "review-pending".
