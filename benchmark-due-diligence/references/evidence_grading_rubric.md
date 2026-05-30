# Evidence Grading Rubric

How collection and verification agents tag and judge every claim. This is the machinery that turns "they say they're #1" into "category award + monthly #1, the annual-#1 claim is debunked."

## Contents
- Two stances: objective collection vs adversarial verification
- source_kind (set during collection)
- Evidence levels L1–L4 (set during verification)
- Verdicts
- The grading discipline: grade, don't binary
- JSON schemas (collection + verification)

## Two stances

Collection and verification run as **separate agents with opposite postures**. Never merge them — an agent told to both gather and judge rationalizes what it found.

| | Collection agent | Verification agent |
|---|---|---|
| Stance | Objective — gather what's out there | Adversarial — default-skeptical, hunt for water |
| Goal | Coverage + provenance | Falsification |
| Output | findings + source_kind + gaps | verdicts (L1–L4 + ruling) + bubble_summary |
| Tools | WebSearch / WebFetch / agent-reach / qcc | Same, but aimed at finding *disconfirming* evidence |

## source_kind (set during collection)

Tag every finding by where it came from — this is what later lets the verifier weight it:

- `对象自述/营销` (self-reported / marketing) — the subject's own blog, pitch deck, PR wire, founder interview. Treat as **claims**, not facts.
- `第三方独立信源` (independent third party) — registries, audited data, reporting that is not a reprint of the subject's PR.
- `混合` (mixed) — e.g., a media article that quotes the subject's numbers without independent verification.

## Evidence levels L1–L4 (set during verification)

| Level | Meaning |
|---|---|
| **L4** | Hard data directly checkable — corporate registry, runtime observation, third-party audited figures, the platform's own official records |
| **L3** | Multiple *independent* sources agree (not reprints of the same press release) |
| **L2** | A single credible third-party source |
| **L1** | Only the subject's own statement / marketing / no independent corroboration |

Bubble-busting is the act of moving a claim *down* from its self-asserted level. A "#1 of the year" asserted at L1 (the subject's bio) routinely collapses to "category award + a monthly #1" once checked against the platform's own award records at L4.

## Verdicts

- `坐实` (confirmed) — L3/L4 backs it
- `大体可信` (largely credible) — plausible, partially corroborated, minor gaps
- `存疑` (doubtful) — single-source / unfalsifiable / internal contradictions
- `证伪-水分` (debunked — water) — falsifying evidence found; the claim is inflated or wrong

## The grading discipline: grade, don't binary

The point is **not** to declare the benchmark a fraud. Most envied benchmarks are *real success wrapped in inflated storytelling* — and the trap cuts both ways: naive belief AND reflexive cynicism both destroy the signal. The verdict ladder forces the middle path: confirm what's solid, debunk what's water, mark the rest doubtful. A strong teardown's one-liner is usually shaped like **"the moves are real, the numbers are inflated"** — a nuance that only survives if you grade each claim instead of judging the subject as a monolith.

## JSON schemas

Pass these as the `schema` option to each agent so the model is forced to return validated structure.

**Collection output:**

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "dimension": { "type": "string" },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "claim": { "type": "string", "description": "one fact or asserted claim" },
          "detail": { "type": "string" },
          "sources": { "type": "array", "items": { "type": "string" }, "description": "source URLs" },
          "source_kind": { "type": "string", "enum": ["对象自述/营销", "第三方独立信源", "混合"] }
        },
        "required": ["claim", "detail", "sources", "source_kind"]
      }
    },
    "gaps": { "type": "string", "description": "not-found / doubtful, to fill later — NEVER guessed" }
  },
  "required": ["dimension", "findings", "gaps"]
}
```

**Verification output:**

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "dimension": { "type": "string" },
    "verdicts": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "claim": { "type": "string" },
          "evidence_level": { "type": "string", "enum": ["L4", "L3", "L2", "L1"] },
          "verdict": { "type": "string", "enum": ["坐实", "大体可信", "存疑", "证伪-水分"] },
          "reasoning": { "type": "string" },
          "cross_sources": { "type": "array", "items": { "type": "string" }, "description": "URLs actually checked while verifying" }
        },
        "required": ["claim", "evidence_level", "verdict", "reasoning", "cross_sources"]
      }
    },
    "bubble_summary": { "type": "string", "description": "the biggest water in this dimension" }
  },
  "required": ["dimension", "verdicts", "bubble_summary"]
}
```
