# Enterprise Research Quality Checklist

Apply three levels of control. Counts and formatting metrics diagnose the work; the pass condition is whether the evidence can carry the requested decision.

## L1: Evidence Quality

For each in-scope decision question:

- [ ] The legal entity, period, geography, and relevant business boundary are explicit.
- [ ] Each load-bearing claim has a source that can directly observe it.
- [ ] Decisive originals have been opened and recorded with a stable locator.
- [ ] Repeated publications from one disclosure, filing, dataset, study, interview, or sponsor are grouped as one evidence family.
- [ ] Material contradictory evidence has been sought and preserved.
- [ ] Exact figures use consistent definitions, periods, currencies, and restatement status.
- [ ] Authorized first-party records are labelled; external corroboration is separate.
- [ ] Missing evidence remains `unknown` rather than being filled by inference.

### Dimension Coverage Prompts

Use only the prompts relevant to the question:

| Dimension | Decision-bearing prompts |
|---|---|
| Company fundamentals | Which legal entity, owners, controllers, and effective dates matter? |
| Business and products | Which segments, products, customers, or revenue mechanisms determine the decision? |
| Competitive position | Which alternatives are actually available, and under what market definition? |
| Financial and operations | Which figures carry the conclusion, and what governing originals define them? |
| Recent developments | Which events changed the decision, rather than merely filling a timeline? |
| First-party/proprietary | Which authorized records establish internal facts, and which claims still need external corroboration? |

## L2: Analysis Quality

- [ ] Every conclusion answers a named decision question.
- [ ] Claim strength matches evidence strength and independence.
- [ ] A real counter-interpretation is included when evidence supports one.
- [ ] Conflicts are resolved by definitions and provenance or remain explicit.
- [ ] Recommendations, when requested, identify which evidence and assumptions they depend on.
- [ ] SWOT, risk matrices, barrier scores, and weighted scorecards appear only when they improve the decision.
- [ ] Any framework weights, probability bands, or scores are sourced, accepted by the user, or labelled as analyst assumptions.

## L3: Document Quality

- [ ] The structure follows the user's format contract.
- [ ] The executive summary distinguishes supported findings from unknowns.
- [ ] Each exact number, date, and quotation traces to an original source.
- [ ] Tables use consistent definitions and expose incomparable values.
- [ ] The appendix includes the source registry and evidence-family notes when useful.
- [ ] Length, source totals, domain counts, and source-type mix are reported only as diagnostics.

## Optional Enterprise Report Structure

Use this structure when it matches the request; remove irrelevant sections rather than filling them mechanically.

```text
# {Company Name} Research Report

## Executive Summary
## Research Questions, Scope, and Unknowns
## Company and Entity Context
## Business, Customers, and Product Evidence
## Market and Alternatives
## Financial and Operating Evidence
## Risks and Recent Decision-Relevant Events
## Assessment or Recommendation
## Evidence Registry and Limitations
```

## Result Handling

- Proceed when every load-bearing question is supported, contradicted, or explicitly unknown and the decision can tolerate the unknowns.
- Re-search only the question whose missing evidence can change the conclusion.
- Stop or narrow the recommendation when a decisive unknown remains.
