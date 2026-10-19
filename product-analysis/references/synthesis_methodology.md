# Synthesis Methodology

Weight, merge, and validate findings from multiple parallel agents.

## Multi-Agent Synthesis Framework

### Step 1: Collect Raw Findings

Wait for all agents to complete. For each agent, extract:
- **Quantitative data**: counts, measurements, lists
- **Qualitative assessments**: good/bad/unclear judgments
- **Evidence**: file paths, line numbers, code snippets

### Step 2: Cross-Validation Matrix

Create a matrix comparing findings and their original evidence. Treat this
synthetic example as a reporting shape, not observed product data:

```
| Finding | Reports | Original observation / scope | Confidence / next check |
|---------|---------|------------------------------|-------------------------|
| First-screen controls | 57 / 54 / 61 | Different states; unverified | Unresolved; reproduce one state |
| Feature entry points | 3 / 3 / 2 | Two reports copy one source; live trace shows 2 | Use verified 2 within traced scope |
| Remove a page | Yes / no | Task and consumer impact unobserved | Hypothesis; inspect affected tasks |
```

Assign confidence per claim from source authority, measurement validity, coverage
and independent reproduction. Mark unobserved or conflicting claims unresolved.
Agreement is a lead, not corroboration when reports share an observation or
mistake. A single reproducible source trace can outweigh several agreeing reports.
Separate confidence in a count from confidence in its effect on a user's task.

### Step 3: Disagreement Resolution

When agents disagree:
1. Check if they analyzed different files/scopes
2. Check if one agent missed context (e.g., conditional rendering)
3. If genuine disagreement, note both perspectives in report
4. Codex-only findings are "different model perspective" — valuable but need validation

Apply the same source check to agreement. Reproduce the material claim at its
actual consumer; qualify scope when rendering, roles, data or clients differ.

### Step 4: Priority Assignment

**P0 (Critical)**: Issues that prevent a new user from completing basic tasks
- Examples: broken onboarding, missing error messages, dead navigation links

**P1 (High)**: Issues that significantly increase cognitive load or confusion
- Examples: duplicate entry points, information overload, unclear primary action

**P2 (Medium)**: Issues worth addressing but not blocking launch
- Examples: verified unused API endpoints, minor inconsistencies, missing edge case handling

Assign these priorities from observed task impact, severity and reach, with
uncertainty explicit. Counts of controls, steps or routes locate hypotheses;
they do not prove confusion, time-to-value or business loss. Preserve useful
duplicate entry points and supported API clients when the task evidence warrants
them. Before marking an API unused, inspect relevant frontend, CLI, integration,
external-client contracts and lifecycle evidence; otherwise report coverage unknown.

### Step 5: Report Generation

Structure the report for actionability:

1. **Executive Summary** (2-3 sentences, the "so what")
2. **Quantified Metrics** (source, state/scope and coverage; separate measured counts from inferred effects)
3. **P0 Issues** (with specific file:line references)
4. **P1 Issues** (with suggested fixes)
5. **P2 Issues** (backlog items)
6. **Cross-Model Insights** (findings unique to one model)
7. **Competitive Position** (if compare scope was used)

## Weighting Rules

- Prefer evidence matched to the claim: source traces for implementation, observed
  task behavior for usability, and relevant outcome data for business effects.
- Keep measured counts and qualitative feedback in their appropriate scopes;
  neither outranks the other solely by format.
- Check evidence independence and reproduce material claims instead of counting votes.
- Rank by supported business/task consequences, including internal faults that
  can prevent delivery; keep unmeasured impact unknown.
- State the next decisive observation when uncertain; an easy fix path does not
  establish that a finding matters or justify displacing a more consequential gap.
