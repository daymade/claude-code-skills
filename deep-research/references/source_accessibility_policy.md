# Source Accessibility and First-Party Evidence Policy

Classify access separately from evidentiary role. A private or paid source can be excellent evidence; a public page can still be copied, circular, or unable to observe the claim.

## Accessibility Classes

| Class | Definition | Examples | Permitted use |
|---|---|---|---|
| `public` | Open to an external researcher | Regulatory filings, government data, public papers, company sites | Use within the source's observation scope |
| `semi-public` | Registration or limited access required | Free-tier databases, registered portals | Use with access disclosure |
| `exclusive-user-provided` | Paid or proprietary access supplied by the user for third-party research | Licensed databases, private market feeds | Use and label the access boundary |
| `authorized-first-party` | User-authorized records about the user's own organization, work, or transactions | Contracts, invoices, CRM exports, meeting transcripts, internal operating data | Use for business facts the record directly captures |

Never expose credentials or confidential source material beyond the user's requested output.

## First-Party Evidence Boundary

Authorized first-party records can establish facts such as:

- what the organization agreed, bought, paid, delivered, recorded, or measured;
- what a named participant said in an authenticated meeting or message record;
- what the organization's own system logged at a specific time.

They cannot, by themselves, establish:

- independent customer sentiment or market reputation;
- regulatory compliance or legal sufficiency;
- competitor behavior;
- an external party's state of mind;
- an independently verified market, performance, or quality claim.

Write the resulting status explicitly:

| Status | Meaning |
|---|---|
| `internally-established` | A first-party original directly records the business fact |
| `externally-corroborated` | An independent external source confirms the relevant claim |
| `conflicted` | Material sources disagree |
| `externally-unknown` | No fit-for-purpose independent source was found |

Do not discard a valid internal fact merely because it is not external. Do not upgrade it to external validation merely because the user authorized access.

## Exclusive Sources for Third-Party Research

Use authorized paid subscriptions, private APIs, and proprietary databases to research competitors, markets, and investments. Record:

- the source owner and access class;
- the claim it can observe;
- its methodology or data lineage when available;
- whether an independent source shares the same underlying dataset.

An exclusive source is a competitive information advantage. It still needs ordinary claim fitness, freshness, and conflict checks.

## External-Footprint Questions

When the question is specifically what an external investigator can verify, restrict the evidence set to sources available to that investigator. Internal records may explain the difference but cannot fill the public-footprint result.

Example output:

```text
External visibility: minimal
Public evidence checked: official registries, procurement records, regulatory filings, web presence
Externally verifiable claims: [list]
Externally unknown: [list]
Internal records supplied by the user: excluded from the external-verifiability conclusion
```

## Decision Checklist

1. What exact claim is being tested: an internal business fact, an external-verifiability claim, or a third-party claim?
2. Who created the record, and what could they directly observe?
3. Is the user authorized to provide it for this task?
4. Does another citation repeat the same underlying record or add independent evidence?
5. Which conclusion status follows: internally established, externally corroborated, conflicted, or externally unknown?
