# Enterprise Research Quality Checklist

Three-level quality control executed at each stage transition.

## L1: Data Collection Quality (after each dimension)

### Per-Dimension Checks

| Check Item | Standard | Method | Pass Condition |
|-----------|----------|--------|---------------|
| Source count | Key data points ≥2 sources | Count source annotations | ≥90% compliance |
| Source attribution | All data has source marked | Check citations in draft | ≥95% completeness |
| Cross-validation pass rate | Data deviation ≤10% | Compare multi-source data | ≥95% validation pass |
| Timeliness | Financial: ≤2 years; News: ≤6 months | Check timestamps | 100% compliance |

**Result handling**: All pass → proceed. Partial fail → supplement sources. Critical fail → re-collect dimension.

### Dimension-Specific Checklists

**D1 Company Fundamentals** (target: 11/11):
- [ ] Legal entity boundaries clarified
- [ ] Founding date with month/year
- [ ] Headquarters city identified
- [ ] Founder/CEO confirmed (≥2 sources)
- [ ] Employee count with year
- [ ] Listing status (exchange, ticker)
- [ ] Latest valuation/market cap with date
- [ ] Core business one-liner
- [ ] Funding history ≥3 rounds
- [ ] ≥5 milestone events in timeline
- [ ] Ownership structure: controller identified

**D2 Business & Products** (target: 7/7):
- [ ] ≥3 business segments identified
- [ ] Revenue share per segment
- [ ] ≥3 core products analyzed
- [ ] User metrics (DAU/MAU) with numbers
- [ ] Monetization model per product
- [ ] Revenue breakdown (segment/geography/customer)
- [ ] Growth/decline trend per segment

**D3 Competitive Position** (target: 7/7):
- [ ] Industry clearly defined
- [ ] Market size quantified
- [ ] Company rank established
- [ ] Market share with number
- [ ] ≥3 competitors identified
- [ ] Multi-dimension comparison table complete
- [ ] ≥5 barrier dimensions assessed with scores

**D4 Financial & Operations** (target: 9/9):
- [ ] Revenue: 3-year data
- [ ] Net income: 3-year data
- [ ] Gross margin: 3-year data
- [ ] Net margin: 3-year data
- [ ] Operating cash flow: 3-year data
- [ ] R&D expense: 3-year data
- [ ] Key financial data cross-validated (≥2 sources)
- [ ] Metric definitions consistent across years
- [ ] ≥3 efficiency metrics (ROE/ROA/etc.)

**D5 Recent Developments** (target: 5/5):
- [ ] ≥5 recent events (within 6 months)
- [ ] Events span ≥3 event types
- [ ] Each event has impact assessment
- [ ] ≥2 strategic direction signals identified
- [ ] Most recent event within 1 month

**D6 Internal/Proprietary** (target: 2/2):
- [ ] Internal knowledge base queried (or limitation noted)
- [ ] Internal document search executed (or limitation noted)

## L2: Analysis Quality (after analysis frameworks applied)

| Check Item | Standard | Method | Pass Condition |
|-----------|----------|--------|---------------|
| SWOT completeness | Each quadrant ≥3 entries | Entry count | Full coverage |
| SWOT evidence | Every entry has data backing | Check "Evidence" fields | 100% evidenced |
| Risk matrix coverage | All 8 categories assessed | Category checklist | 100% covered |
| Barrier quantification | All 7 dimensions scored | Check scorecard completeness | 100% scored |
| Conclusion support | All conclusions trace to evidence | Trace each conclusion | 100% supported |

**Result handling**: All pass → proceed to writing. Partial fail → supplement analysis evidence. Critical fail → re-execute analysis framework.

## L3: Document Quality (after report drafted)

| Check Item | Standard | Method | Pass Condition |
|-----------|----------|--------|---------------|
| Structure compliance | Follows 7-chapter template | Compare against template | ≥95% compliance |
| Table format consistency | All tables uniformly formatted | Visual inspection | 100% uniform |
| Readability | Paragraphs ≤450 chars; ≥3 parallel items use lists | Paragraph length check | ≥95% compliance |
| Data annotation | All data has source + year | Citation audit | 100% complete |
| Appendix completeness | Includes source index + glossary | Content check | 100% complete |

**Result handling**: All pass → deliver. Partial fail → format optimization. Critical fail → regenerate document.

## Enterprise Report Structure (7 Chapters)

```
# {Company Name} Research Report

> Executive Summary: {1-2 sentence core conclusion}

---

## 1. Company Overview
### 1.1 Basic Information (table)
### 1.2 Development Timeline
### 1.3 Funding History (table)
### 1.4 Ownership Structure & Control
### 1.5 Core Management Team (table)

## 2. Business & Product Structure
### 2.1 Business Landscape Overview
### 2.2 Core Product Matrix (table)
### 2.3 Revenue Structure Analysis
### 2.4 Business Development Trends

## 3. Market & Competitive Position
### 3.1 Industry Position Analysis
### 3.2 Competitive Comparison (table)
### 3.3 Competitive Barrier Assessment (scorecard)

## 4. Financial & Operations Analysis
### 4.1 Key Financial Metrics (3-year comparison table)
### 4.2 Operating Efficiency Assessment
### 4.3 Financial Health Summary

## 5. Risks & Concerns
### 5.1 Risk Matrix Analysis (8-category table)
### 5.2 Key Risk Deep-Dives
### 5.3 Risk Mitigation Recommendations

## 6. Recent Developments
### 6.1 Major Recent Events (table)
### 6.2 Strategic Signal Interpretation

## 7. Comprehensive Assessment & Conclusion
### 7.1 SWOT Summary
### 7.2 Comprehensive Scorecard
### 7.3 Core Conclusions & Outlook

---

## Appendices
### A. Data Source Index
### B. Glossary
### C. Disclaimer
```

## Quality Control Four Dimensions

Apply throughout all stages:

| Dimension | Focus | Key Checks |
|-----------|-------|------------|
| **Accuracy** | Data correctness | Source attribution, fact verification, cross-validation, error tolerance |
| **Completeness** | Information coverage | Dimension coverage, key element presence, conclusion support, risk coverage |
| **Timeliness** | Data currency | Data freshness, trend capture, signal detection, dynamic updates |
| **Consistency** | Uniform standards | Metric definitions aligned, format unified, style consistent, terminology standardized |
