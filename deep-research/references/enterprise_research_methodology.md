# Enterprise Research Methodology

## Six-Dimension Coverage Map

Use these dimensions to check whether a decision question has an unexamined evidence route. Investigate only the relevant dimensions, and state why omitted dimensions cannot change the conclusion.

### Dimension 1: Company Fundamentals

```
Step 1.1: Confirm legal entity
├── Clarify parent/subsidiary/affiliate boundaries
├── Query: "{company} legal entity corporate structure"
├── Output: Entity scope statement
└── Verify: Map operating entities to brands

Step 1.2: Basic information
├── Query round 1: "{company} founding date headquarters founder"
├── Query round 2: "{company} company overview profile"
├── Query round 3: "{company} CEO management team executives"
├── Source priority: Official site > Regulatory filings > Authoritative media
└── Output: Basic info table (name, founded, HQ, CEO, employees, listing status)

Step 1.3: Funding history
├── Query: "{company} funding rounds valuation IPO"
├── Key fields: round, amount, investors, post-money valuation, date
└── Output: Funding timeline table

Step 1.4: Ownership structure
├── Query: "{company} ownership structure beneficial owner"
├── Key fields: controller identity, economic interest %, voting rights %, control mechanisms (dual-class etc.)
└── Output: Ownership summary
```

### Dimension 2: Business & Products

```
Step 2.1: Business landscape scan
├── Query round 1: "{company} product lines business segments"
├── Query round 2: "{company} revenue breakdown by segment"
├── Query round 3: "{company} business model monetization"
├── Key fields: segment name, positioning, revenue share, YoY growth, synergies
└── Output: Business landscape table

Step 2.2: Core product analysis
├── Query: "{company} core products DAU MAU user base"
├── Per product: positioning, target users, scale (DAU/MAU), market share, monetization, competitive advantage, trends
└── Output: Product matrix table

Step 2.3: Revenue structure analysis
├── Source: Financial reports (deep extraction)
├── Breakdown by: segment, geography, customer type, pricing model
└── Output: Revenue structure summary
```

### Dimension 3: Competitive Position

```
Step 3.1: Industry position
├── Query: "{company} industry ranking market share"
├── Key fields: industry definition, TAM/SAM/SOM, company rank, share, concentration (CR3/CR5)
└── Output: Industry position analysis

Step 3.2: Competitor identification & comparison
├── Query round 1: "{company} competitors"
├── Query round 2: "{company} vs {competitor A} comparison"
├── Query round 3: "{company} vs {competitor B} differences"
├── Comparison dimensions: founding, revenue, market share, core products, user scale, valuation/market cap, strengths, weaknesses
├── Stop when the comparison set represents the decision alternatives; record excluded candidates
└── Output: Competitive comparison table

Step 3.3: Competitive barriers assessment
├── Use quantified barrier framework (see enterprise_analysis_frameworks.md)
├── 7 dimensions: network effects, scale economies, brand, technology/patents, switching costs, regulatory licenses, data assets
└── Output: Barrier scorecard with rating
```

### Dimension 4: Financial & Operations

```
Step 4.1: Financial data collection
├── Query: "{company} financial results {year} revenue profit"
├── Core metrics (3-year minimum): revenue, revenue growth, net income, gross margin, net margin, operating cash flow, R&D expense, R&D ratio
└── Output: Financial metrics table (3+ years)

Step 4.2: Operating efficiency analysis
├── Query: "{company} ROE ROA efficiency per-employee"
├── Efficiency metrics: ROE, ROA, revenue per employee, accounts receivable days, debt-to-equity
└── Output: Operating efficiency table

Step 4.3: Cross-validation
├── Open the governing filing or audited statement for key financial data
├── Use independent corroboration when the figure is disputed, transformed, or decision-critical
├── Sources: company filings, regulatory filings, and transparent financial datasets
├── Reconcile any deviation that could change the conclusion
├── Check period, currency, scope, accounting definition, and restatement status
└── Output: Validation record
```

### Dimension 5: Recent Developments

```
Step 5.1: Recent news scan (past 6 months)
├── Query round 1: "{company} latest news {current year}"
├── Query round 2: "{company} strategy pivot latest developments"
├── Query round 3: "{company} executive changes leadership"
├── Query round 4: "{company} partnership acquisition latest"
├── Query round 5: "{company} product launch new release"
├── Event types: product launches, fundraising/capital, strategy shifts, executive changes, M&A/partnerships, regulatory/compliance
├── Include events that change the decision; event count is diagnostic
└── Output: Major events table

Step 5.2: Strategic signal interpretation
├── Dimensions: expansion signals, contraction signals, transformation signals, risk signals
└── Output: Strategic signal analysis
```

### Dimension 6: Authorized First-Party and Proprietary Sources

```
Step 6.1: Query authorized records when they can directly establish a business fact
├── Query 1: "our company's relationship with {target company}"
├── Query 2: "internal assessment of {target company}"
├── Query 3: "{target company} competitive analysis"
├── Query 4: "{target company} industry research"
└── Output: Internally established facts with record owner, locator, and external-corroboration status

Step 6.2: Apply the provenance boundary
├── Internal records may establish what the organization did, agreed, paid, delivered, or observed
├── They do not count as independent external validation
└── Mark the result: internally established / externally corroborated / conflicted / externally unknown
```

## Evidence Routes for Enterprise Claims

Choose sources by who can observe the fact. These routes are especially useful when company marketing and generic web coverage only repeat one another.

| Claim | Start with | Then test against | Boundary |
|---|---|---|---|
| Named customer or purchase | Customer procurement notices, awarded-contract records, signed customer-side records supplied with authorization | Customer budget/board documents, implementation records | A vendor logo or case-study page alone is a lead |
| Investor position or ownership | Fund/regulatory filings, shareholder registers, beneficial-ownership disclosures | Fund reports and issuer filings for the same reporting date | Media summaries of one filing are one evidence family |
| Regulatory status | Regulator registers, decisions, filings, licences, and correspondence | Entity disclosures and qualified analysis | Company assertions do not establish compliance |
| Deployment and technical capability | Customer engineering write-ups, technical artifacts, benchmarks with methods | Supplier engineering case studies and product documentation | Supplier case studies establish what the supplier claims unless the customer or artifact corroborates it |
| Revenue or operating metric | Audited statements and governing filings | Transparent datasets or independent calculations using the same definitions | Two websites copying the filing are not two sources |

Examples of public record systems include SEC EDGAR for filings and ownership reports, USAspending or jurisdictional procurement portals for public awards, and customer engineering publications for deployed-system details. Select the jurisdiction-specific original record rather than assuming these examples are universal.

## Data Source Priority Matrix

| Priority | Source Type | Reliability | Timeliness | Use Case |
|----------|-----------|-------------|------------|----------|
| **P0** | Governing original record | Claim-specific | Varies | Filings, awards, contracts, standards, authenticated business records |
| **P1** | Independent direct observer | Claim-specific | Varies | Regulator, customer, primary study, transparent dataset |
| **P2** | Transparent synthesis | Claim-specific | Varies | Research institution, analyst report, reputable journalism |
| **P3** | Lead or perception evidence | Claim-specific | Often high | Forums, reviews, social media |

**Rule**: Priority follows claim fitness and provenance, not a universal source score. A first-party original may decide what the organization did while remaining unable to validate how outsiders judged it.

## Cross-Validation Rules

| Data Type | Decisive original | When corroboration is required | Conflict handling |
|---|---|---|---|
| Financial data | Governing filing or audited statement | Disputed, transformed, or decision-critical figure | Reconcile definitions, period, currency, and restatements |
| Market share | Dataset/report with disclosed market definition | Conclusion depends on rank or share | Preserve competing market definitions |
| Management info | Current regulator/company filing | Material role or control is disputed | Use effective dates and legal-entity scope |
| User metrics | Measurement owner with disclosed definition | External claim or trend depends on it | Compare definitions and collection methods |

## Search Strategy Best Practices

1. **Multi-angle queries**: Search by source owner and evidence route, not only by claim wording
2. **Time filtering**: Set a freshness horizon that matches each claim; keep older governing records when they remain authoritative
3. **Site restriction**: Use `site:` for authoritative domains when possible
4. **Language diversity**: Query in both English and the company's primary language
5. **Exclude noise**: Use `-` to exclude irrelevant results
6. **Progressive depth**: Start broad, then narrow based on gaps, conflicts, and load-bearing claims
