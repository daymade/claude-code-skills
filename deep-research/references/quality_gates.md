# Quality Gates V6

## Gate 1: Task Notes Quality (after P2)

| Check | Standard | Lightweight | Fix |
|-------|----------|-------------|-----|
| All tasks completed | 100% | 100% | Re-dispatch failed tasks |
| Sources per task | >= 2 | >= 1 | Run additional searches |
| Findings per task | >= 3 | >= 2 | Deepen search or fetch more |
| DEEP tasks have Deep Read Notes | 100% | 100% | Fetch and read top source |
| All source URLs from actual search | 100% | 100% | Remove any invented URL |

## Gate 2: Citation Registry (after P3)

| Check | Standard | Lightweight | Fix |
|-------|----------|-------------|-----|
| Total approved sources | >= 12 | >= 6 | Flag thin areas for P6 |
| Unique domains | >= 5 | >= 3 | Diversify in re-search |
| Max single-source share | <= 25% | <= 30% | Find alternatives |
| Official source coverage | >= 30% for standard | >= 20% for lightweight | Add official sources |
| Source-type balance | official + academic + secondary at least 2 types | same | Fill missing type
| Dropped sources listed | All | All | Must be explicit |
| No duplicate URLs | 0 duplicates | 0 | Merge during P3 |

## Gate 3: Draft Quality (after P5)

| Check | Standard | Lightweight | Fix |
|-------|----------|-------------|-----|
| Every [n] in registry | 100% | 100% | Remove or fix |
| No dropped source cited | 0 violations | 0 | Remove immediately |
| Citation density | >= 1 per 200 words | >= 1 per 300 words | Add citations |
| Every section has confidence marker | 100% | 100% | Add missing |
| High-confidence claims backed by official source | 100% | 100% | Downgrade or re-source |
| Counter-claim recorded for major sections | 100% | 70% | Add opposing interpretation |
| Total word count | 3000-8000 | 2000-4000 | Adjust scope |

## Gate 4: Notes Traceability (after P6)

| Check | Threshold | Fix |
|-------|-----------|-----|
| Every specific claim traceable to a task note finding | 100% | 100% | Remove or mark [unverified] |
| Every statistic/number appears in some task note | 100% | 100% | Remove or verify |
| No claim contradicts a task note | 0 contradictions | 0 | Rewrite to match notes |
| Claims with recency sensitivity include source date and AS_OF | 100% | 100% | Add date metadata |
| P6 found >= 3 issues | Must | Re-examine harder if 0 found |

## Gate 5: Verification (after P7)

| Check | Threshold | Fix |
|-------|-----------|-----|
| Registry cross-check: all [n] valid | 100% | 100% | Remove invalid [n] |
| Spot-check: 5+ claims traced to notes | >= 4/5 pass | Fix failing claims |
| No dropped source resurrected | 0 | Remove immediately |
| Source concentration check for key claims | None > 25% | diversify |

## Anti-Hallucination Patterns

| Pattern | Where to detect | Fix |
|---------|----------------|-----|
| URL not from any subagent search | P7 registry check | Remove citation |
| Claim not in any task note | P6 traceability check | Remove or mark [unverified] |
| Number more precise than source | P6 ("73.2%" when note says "about 70%") | Use note's precision |
| Source authority inflated | P3 registry building | Re-score from notes |
| Source type mismatched to claim | P3 + P6 | Reclassify or replace source |
| "Studies show..." without naming study | P6 | Name specific source or remove |
| Dropped source reappears | P7 cross-check | Remove immediately |
| Subagent invented a URL | Gate 1 (lead verifies subagent notes) | Remove from notes before P3 |

## Chinese-Specific Patterns

| Pattern | Fix |
|---------|-----|
| Fake CNKI URL format | Remove, note gap |
| "某专家表示" without name/institution | Name or remove |
| "据统计" without data source | Add source or qualitative language |
| Fabricated institution report | Verify existence or remove |
| 旧模型信息未标注 AS_OF | 降级置信度并重搜 |
