# Evidence Packet Format

Use task notes to move evidence between researchers and the lead agent without flooding the lead context with raw search results. Notes are a routing and audit layer, not an authority. Every final load-bearing claim, conflict, exact number/date, and quotation must be checked in the original source.

## Workspace Structure

```text
workspace/research-notes/
  task-a.md
  task-b.md
  registry.md
  query-log.md        # when reproducibility or a negative search matters
```

Keep raw snippets, rejected results, and bulk search output outside the evidence packet. Preserve enough query history to reproduce material negative findings.

## Per-Task Evidence Packet

```markdown
---
task_id: a
role: Procurement Researcher
decision_question: Which named customers have actually purchased the product?
status: answered|contradicted|unknown
---

## Question and Stop Rule

- Decision question: ...
- Why it matters: ...
- Stop rule: ...
- Result: answered|contradicted|unknown

## Sources

[1] Title | stable URL or record ID | Source-Type: official | Accessibility: public | Evidence-Family: buyer-award-123 | As Of: 2026-03 | Authority: high
[2] Title | stable URL or record ID | Source-Type: official | Accessibility: authorized-first-party | Evidence-Family: signed-contract-abc | As Of: 2025-11 | Authority: high

## Claim-Evidence Table

| Claim | Source | Original opened? | Evidence excerpt or exact locator | Scope/limits | Confidence |
|---|---|---|---|---|---|
| Buyer awarded supplier a contract | [1] | yes | Award notice, supplier field, page/section ... | Award does not prove successful delivery | High |

## Counter-Evidence and Unknowns

- Disconfirming evidence sought: ...
- Result: ...
- Unresolved: ...

## Source-Family Notes

- [1] and [3] repeat the same buyer award record; count as one evidence family.
```

## Source Rules

- Use stable URLs, filing/accession numbers, award IDs, DOIs, page numbers, table names, or section headings.
- Record the source family behind each publication. Different domains that copy one press release or dataset are not independent.
- Record accessibility separately from source type.
- Use `authorized-first-party` for user-authorized records about the user's own business and state the record owner.
- Use a qualitative authority label or a numeric score only as a sorting aid; neither replaces claim fitness.
- Use `undated` when the date is genuinely unavailable and explain whether that matters.

## Claim Rules

- Write claims at the precision and scope supported by the source.
- Separate observation from inference.
- Preserve contradictions; do not rewrite an original to match a note.
- Mark unsupported conclusions `unknown` rather than inventing a bridge.
- Limit the packet to decision-bearing evidence. Source and finding counts are diagnostics, not quotas.

## Registry Format

```markdown
# Citation Registry

## Approved Sources

[1] Buyer award notice | URL | Source-Type: official | Accessibility: public | Evidence-Family: award-123 | As Of: 2026-03 | From: task-a

## Claim Coverage

| Load-bearing claim | Support | Counter-evidence | Decisive original checked | Status |
|---|---|---|---|---|
| ... | [1] | none found after ... | yes | supported |

## Excluded Sources

x Source | URL | Reason: repeats [1] without new evidence

## Diagnostics

- Sources reviewed / approved / excluded: ...
- Unique domains: ...
- Independent evidence families: ...
- Source-type mix: ...
- Decision questions answered / contradicted / unknown: ...
```

Registry numbers are final for the report. A source can be re-evaluated, but it must pass through the registry again before citation.
