# Synthesis Methodology

How to weight, merge, and validate findings from multiple parallel agents.

## Multi-Agent Synthesis Framework

### Step 1: Collect Raw Findings

Wait for all agents to complete. For each agent, extract:
- **Quantitative data**: counts, measurements, lists
- **Qualitative assessments**: good/bad/unclear judgments
- **Evidence**: file paths, line numbers, code snippets

### Step 2: Cross-Validation Matrix

Create a matrix comparing findings across agents:

```
| Finding | Agent A | Agent B | Codex | Confidence |
|---------|---------|---------|-------|------------|
| "57 interactive elements on first screen" | 57 | 54 | 61 | HIGH (3/3 agree on magnitude) |
| "Skills has 3 entry points" | 3 | 3 | 2 | HIGH (2/3 exact match) |
| "Risk pages should be removed" | Yes | - | No | LOW (disagreement, investigate) |
```

**Confidence levels**:
- **HIGH**: 2+ agents agree (exact or same magnitude)
- **MEDIUM**: 1 agent found, others didn't look
- **LOW**: Agents disagree — requires manual investigation

### Step 3: Disagreement Resolution

When agents disagree:
1. Check if they analyzed different files/scopes
2. Check if one agent missed context (e.g., conditional rendering)
3. If genuine disagreement, note both perspectives in report
4. Codex-only findings are "different model perspective" — valuable but need validation

### Step 4: Priority Assignment

**P0 (Critical)**: Issues that prevent a new user from completing basic tasks
- Examples: broken onboarding, missing error messages, dead navigation links

**P1 (High)**: Issues that significantly increase cognitive load or confusion
- Examples: duplicate entry points, information overload, unclear primary action

**P2 (Medium)**: Issues worth addressing but not blocking launch
- Examples: unused API endpoints, minor inconsistencies, missing edge case handling

### Step 5: Report Generation

Structure the report for actionability:

1. **Executive Summary** (2-3 sentences, the "so what")
2. **Quantified Metrics** (hard numbers, no adjectives)
3. **P0 Issues** (with specific file:line references)
4. **P1 Issues** (with suggested fixes)
5. **P2 Issues** (backlog items)
6. **Cross-Model Insights** (findings unique to one model)
7. **Competitive Position** (if compare scope was used)

## Weighting Rules

- Quantitative findings (counts, measurements) > Qualitative judgments
- Code-evidenced findings > Assumption-based findings
- Multi-agent agreement > Single-agent finding
- User-facing issues > Internal code quality issues
- Findings with clear fix path > Vague "should improve" suggestions
