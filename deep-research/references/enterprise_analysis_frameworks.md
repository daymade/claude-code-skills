# Enterprise Analysis Frameworks

Use these frameworks only when they help answer the user's decision. Do not execute them as a fixed sequence. Omit empty quadrants, unsupported risk categories, or synthetic scores rather than manufacturing completeness.

## SWOT Analysis Template

Each SWOT entry MUST include evidence and source attribution.

```
|              | Positive Factors                  | Negative Factors                  |
|--------------|-----------------------------------|-----------------------------------|
| **Internal** | **S (Strengths)**                 | **W (Weaknesses)**                |
|              | 1. {description}                  | 1. {description}                  |
|              |    • Evidence: {data/fact}        |    • Evidence: {data/fact}        |
|              |    • Source: {citation}           |    • Source: {citation}           |
|              |    • Impact: {assessment}         |    • Impact: {assessment}         |
|              |                                   |                                   |
| **External** | **O (Opportunities)**             | **T (Threats)**                   |
|              | 1. {description}                  | 1. {description}                  |
|              |    • Evidence: {trend/policy}     |    • Evidence: {pressure/risk}    |
|              |    • Source: {citation}           |    • Source: {citation}           |
|              |    • Probability: {assessment}    |    • Probability: {assessment}    |
|              |    • Impact: {assessment}         |    • Impact: {assessment}         |
```

**Requirements when SWOT is selected**:
- Include only material entries; entry counts are diagnostic
- Every entry must have evidence with source
- S/W must be data-backed (not opinions)
- O/T include probability and impact only when the evidence supports estimates; otherwise use qualitative uncertainty

**Strategic Implications Matrix** (generate after SWOT):
- **SO Strategy** (leverage strengths to capture opportunities): 1-2 specific recommendations
- **WO Strategy** (overcome weaknesses to seize opportunities): 1-2 specific recommendations
- **ST Strategy** (use strengths to counter threats): 1-2 specific recommendations
- **WT Strategy** (mitigate weaknesses to avoid threats): 1-2 specific recommendations

## Competitive Barrier Quantification Framework

Use the dimensions below as a candidate checklist. Score only when the user needs a comparative rating and the weights are defensible for that decision.

| Dimension | Weight | Strong | Moderate | Weak |
|-----------|--------|--------|----------|------|
| **Network Effects** | 20% | 4.5 — Clear network effects (social platforms, marketplaces) | 3.0 — Exists but replaceable | 1.5 — Minimal network effects |
| **Scale Economies** | 15% | 4.0 — Unit cost drops 30%+ with scale | 2.5 — Cost drops 10-30% | 1.0 — Cost drops <10% |
| **Brand Value** | 15% | 4.0 — Category leader, high pricing power | 2.5 — Known brand, competitive | 1.0 — Commodity brand, price-sensitive |
| **Technology/Patents** | 15% | 4.0 — Core patents, hard to circumvent | 2.5 — Some patent protection | 1.0 — Peripheral patents only |
| **Switching Costs** | 15% | 4.0 — High lock-in (data, ecosystem) | 2.5 — Moderate switching friction | 1.0 — Low switching cost |
| **Regulatory Licenses** | 10% | 3.5 — Heavy regulation, hard to obtain | 2.0 — Standard regulatory requirements | 0.5 — Light regulation |
| **Data Assets** | 10% | 3.5 — Massive proprietary high-quality data | 2.0 — Some data accumulation | 0.5 — Limited or public data |

**Scoring**: Total = Σ(dimension score × weight). Treat the listed weights and thresholds as an illustrative starting model, not observed facts. Confirm or replace them before presenting a score as decision evidence.

**Rating Scale**:
| Score | Rating | Interpretation |
|-------|--------|---------------|
| ≥3.5 | A+ | Exceptional moat |
| ≥2.8 | A | Strong moat |
| ≥2.0 | B+ | Good moat |
| ≥1.5 | B | Moderate moat |
| ≥1.0 | C+ | Limited moat |
| <1.0 | C | Weak moat |

**Output format**: Present a scorecard table with each dimension's strength rating, raw score, justification (with evidence), and the weighted total with final rating.

## Risk Matrix Framework

Consider the risk categories that could materially change the decision. Add domain-specific categories and omit irrelevant ones with a short reason.

### Risk Assessment Scales

**Probability**:
| Level | Range | Score |
|-------|-------|-------|
| High | >70% | 0.7-1.0 |
| Medium | 30-70% | 0.3-0.7 |
| Low | <30% | 0.0-0.3 |

**Impact**:
| Level | Description | Score |
|-------|-------------|-------|
| High | >30% revenue impact | 3 |
| Medium | 10-30% revenue impact | 2 |
| Low | <10% revenue impact | 1 |

**Risk Level**: Risk Value = Probability Score × Impact Score
| Color | Level | Threshold |
|-------|-------|-----------|
| Red | High risk | ≥2.5 |
| Yellow | Medium risk | 1.0 – 2.5 |
| Green | Low risk | <1.0 |

### 8 Mandatory Risk Categories

| # | Category | Typical Triggers |
|---|----------|-----------------|
| 1 | Market risk | Industry slowdown, demand shifts |
| 2 | Competitive risk | New entrants, incumbents pivoting |
| 3 | Technology risk | Tech obsolescence, disruption |
| 4 | Regulatory risk | Policy tightening, compliance cost |
| 5 | Financial risk | Cash flow stress, debt levels |
| 6 | Operational risk | Key talent loss, supply chain |
| 7 | Talent risk | Brain drain, recruiting difficulty |
| 8 | Geopolitical risk | Trade friction, data localization |

### Risk Table Format

| Category | Specific Risk | Probability | Impact | Risk Value | Level | Evidence/Triggers | Current Mitigations | Recommended Actions |
|----------|--------------|-------------|--------|------------|-------|-------------------|--------------------|--------------------|

**Requirements when a risk matrix is selected**:
- Cover every material risk identified by the question map; category count is diagnostic
- Each risk entry must cite specific evidence or triggers
- Distinguish observed probability/impact evidence from analyst judgment
- Provide mitigations or actions only when the user requested recommendations

## Comprehensive Scoring (Final Section)

Generate a comprehensive scorecard only when the user needs a weighted comparison and has accepted the dimensions, scales, and weights:

```
| Dimension | Score | Weight | Weighted | Key Evidence |
|-----------|-------|--------|----------|-------------|
| Business Quality | X/10 | 25% | | |
| Competitive Position | X/10 | 20% | | |
| Financial Health | X/10 | 20% | | |
| Growth Potential | X/10 | 15% | | |
| Risk Profile | X/10 | 10% | | |
| Management Quality | X/10 | 10% | | |
| **Total** | | 100% | **X/10** | |
```

Every score must reference specific evidence. Label uncalibrated weights and judgment calls; if they would create false precision, present an evidence table without a total score.
