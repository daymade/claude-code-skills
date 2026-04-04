# Research Notes Format Specification

The research notes are the ONLY communication channel between subagents and
the lead agent. Every fact in the final report must be traceable to a line in
these notes. No exceptions.

## File Structure

```
workspace/research-notes/
  task-a.md       Subagent A writes (history expert)
  task-b.md       Subagent B writes (transport historian)
  task-c.md       Subagent C writes (telecom analyst)
  task-d.md       Subagent D writes (comparative analyst)
  registry.md     Lead agent builds from task-*.md (P3)
```

## Per-Task Notes Format

Each `task-{id}.md` file follows this exact structure:

```markdown
---
task_id: a
role: Economic Historian
status: complete
sources_found: 4
---

## Sources

[1] Before AI skeptics, Luddites raged against the machine | https://www.nationalgeographic.com/... | Source-Type: secondary-industry | As Of: 2025-08 | Authority: 8/10
[2] Rage against the machine | https://www.cam.ac.uk/research/news/rage-against-the-machine | Source-Type: academic | As Of: 2024-04 | Authority: 8/10
[3] Luddite | https://en.wikipedia.org/wiki/Luddite | Source-Type: community | As Of: 2026-03 | Authority: 7/10
[4] Learning from the Luddites | https://forum.effectivealtruism.org/... | Source-Type: community | As Of: 2025-10 | Authority: 6/10

## Findings

- Luddite movement began March 11, 1811 in Arnold, Nottinghamshire. [3]
- Luddites were skilled craftspeople, not anti-technology extremists. [1][2]
- In the 100M-person textile industry, Luddites never exceeded a few thousand. [2]
- Government crushed movement: 12 executed at York Assizes, Jan 1813. [3]
- Movement collapsed by 1817 under military repression. [1]
- Full textile mechanization transition took 50-90 years (1760s-1850s). [4]
- Textile workers' real wages dropped ~70% during transition. [4]
- Key lesson for AI: Luddites organized AFTER displacement began, losing leverage. [4]

## Deep Read Notes

### Source [1]: National Geographic — Luddites and AI
Key data: destroyed up to 10,000 pounds of frames in first year alone.
  Movement spread from Nottinghamshire to Yorkshire and Lancashire in 1812.
  Children made up 2/3 of workforce at Cromford factory.
Key insight: Luddites attacked the SYSTEM of exploitation, not machines per se.
  They protested manufacturers circumventing standard labor practices.
Useful for: framing section on historical displacement, correcting "anti-tech" myth

### Source [2]: Cambridge University
Key data: Luddites were "elite craftspeople" not working class broadly.
  Yorkshire croppers had 7-year apprenticeships. Movement was localized, never exceeded a few thousand.
Key insight: The movement was smaller and more elite than popular history suggests.
Useful for: nuancing the scale of historical resistance

## Gaps

- Could not find quantitative data on how many specific jobs were lost to textile machines
- No Chinese-language academic sources on Luddite movement found
- Alternative explanation: displacement narrative may be partly confounded by wartime demand shocks
```

## Source Line Format

Each source line in the `## Sources` section must contain exactly:
```
[n] Title | URL | Source-Type: one-of{official|academic|secondary-industry|journalism|community|other} | As Of: YYYY-MM(or YYYY) | Authority: score/10
```

Rules:
- [n] numbers are LOCAL to this task file (start at [1])
- Lead agent will reassign GLOBAL [n] numbers in registry.md
- URL must be from an actual search result (subagent MUST NOT invent URLs)
- `Authority` score follows guide in quality-gates.md
- `As Of` must be provided; use `undated` if unknown
- High-confidence claims in final report must use `official` or `academic` sources

## Findings Line Format

Each finding must be:
- One sentence of specific, factual information
- End with source number(s) in brackets: [1] or [1][2]
- Max 10 findings per task (forces prioritization)
- No vague claims like "research shows..." — name what specifically

Good: `Full textile mechanization transition took 50-90 years (1760s-1850s). [4]`
Bad: `The transition took a long time. [4]`
Bad: `Studies suggest that it was a lengthy process.` (no source, vague)

## Deep Read Notes Format

For each source that was web_fetched (full article read):
- Key data: specific, numeric evidence from article
- Key insight: the one thing this source says that others don't
- Useful for: which final section this supports

Max 4 lines per source. This is a research notebook, not a summary.

## Gaps Section

List what the subagent searched for but could NOT find, and possible counter-readings.
This signals where evidence is thin and confidence should be lowered.

## Registry Format (built by lead agent in P3)

The `registry.md` file merges all task sources into a global registry and adds source-type / as-of fields.

```markdown
# Citation Registry
Built from: task-a.md, task-b.md, task-c.md, task-d.md

## Approved Sources

[1] National Geographic — Luddites | https://www.nationalgeographic.com/... | Source-Type: secondary-industry | As Of: 2026-03 | Auth: 8 | From: task-a
[2] Cambridge — Rage against machine | https://www.cam.ac.uk/... | Source-Type: academic | As Of: 2012-04 | Auth: 8 | From: task-a
[3] OpenAI — Day Horse Lost Job | https://blogs.microsoft.com/... | Source-Type: official | As Of: 2026-01 | Auth: 8 | From: task-b
...
[N] Last source

## Dropped

x Quora answer | https://www.quora.com/... | Source-Type: community | As Of: 2024-10 | Auth: 3 | Reason: below threshold
x Study.com | https://study.com/... | Source-Type: secondary-industry | As Of: undated | Auth: 4 | Reason: better sources available

## Stats

Total evaluated: 22
Approved: 16
Dropped: 6
Unique domains: 12
Source-type: official 4 / academic 3 / secondary-industry 5 / journalism 2 / community 2
Max single-source share: 3/16 = 19% (pass)
```

Rules for registry:
- [n] numbers here are FINAL — they appear unchanged in the report
- Every [n] in the report must exist in the Approved list
- Every Dropped source must NEVER appear in the report
- If two tasks found the same URL, keep it once with the higher authority score
