# Enterprise Research Methodology

## Six-Dimension Data Collection

Enterprise research requires parallel collection across six dimensions. Execute all six in order, writing findings to a structured draft after each dimension.

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
├── Minimum: ≥3 competitors identified
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
├── Require ≥2 independent sources for key financial data
├── Sources: company filings (primary), regulatory filings, authoritative financial data providers
├── Deviation rules:
│   ├── ≤10%: Pass
│   ├── 10-20%: Flag with explanation
│   └── >20%: Require third-party verification
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
├── Minimum: ≥5 events identified
└── Output: Major events table

Step 5.2: Strategic signal interpretation
├── Dimensions: expansion signals, contraction signals, transformation signals, risk signals
└── Output: Strategic signal analysis
```

### Dimension 6: Internal/Proprietary Sources

```
Step 6.1: Internal knowledge base query (if available)
├── Query 1: "our company's relationship with {target company}"
├── Query 2: "internal assessment of {target company}"
├── Query 3: "{target company} competitive analysis"
├── Query 4: "{target company} industry research"
└── Output: Internal perspective supplementary info

Step 6.2: If no internal sources available
├── State explicitly: "No internal/proprietary sources available for this research"
├── Compensate with additional public source depth
└── Note limitation in final report
```

## Data Source Priority Matrix

| Priority | Source Type | Reliability | Timeliness | Use Case |
|----------|-----------|-------------|------------|----------|
| **P0** | Official filings / annual reports | 10/10 | High | Core financial data |
| **P0** | Company website / announcements | 10/10 | High | Basic info, updates |
| **P1** | Regulatory filings | 9/10 | High | Ownership, licenses |
| **P1** | Authoritative industry reports | 9/10 | Medium | Market position, trends |
| **P2** | Mainstream financial media | 8/10 | High | News, analysis |
| **P2** | Professional research institutions | 8/10 | Medium | Deep analysis, forecasts |
| **P3** | Social media / forums | 5/10 | High | Sentiment signals only |

**Rule**: P0 + P1 are primary sources. P2 for validation. P3 for reference only, never as sole source.

## Cross-Validation Rules

| Data Type | Min Sources | Max Deviation | Primary Source | Fallback Sources |
|-----------|------------|---------------|----------------|-----------------|
| Financial data | 2 | 10% | Official financial reports | Regulatory filings, analyst reports |
| Market share | 2 | 15% | Industry reports | Company disclosures, third-party analysis |
| Management info | 1 | N/A | Company official sources | Regulatory filings, reputable media |
| User metrics | 2 | 20% | Company disclosures | Third-party analytics, industry reports |

## Search Strategy Best Practices

1. **Multi-angle queries**: 3 different query angles per topic
2. **Time filtering**: Prioritize data within last 12 months for operational data, last 3 years for financial trends
3. **Site restriction**: Use `site:` for authoritative domains when possible
4. **Language diversity**: Query in both English and the company's primary language
5. **Exclude noise**: Use `-` to exclude irrelevant results
6. **Progressive depth**: Start broad, then narrow based on gaps identified
