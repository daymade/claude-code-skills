---
name: dual-pool-review
description: Multi-round adversarial review methodology that rotates reviewers across two pools — fixed (curated, knows your context) and random (fresh web search each round) — to catch blind spots a single reviewer or single round would miss. Use when reviewing complex output, security-critical code, or identity/persona-related content. Use when you need review depth beyond a single pass. Use when a single perspective may have dangerous blind spots.
---

# Dual-Pool Adversarial Review

Multi-round adversarial review with rotating reviewer pools. Run this whenever a single "looks good to me" is not enough — complex multi-file changes, security-critical output, identity-defining content, or any work where blind spots compound.

## When to Use This Skill

Activate this skill when:
- Reviewing multi-file changes or architectural decisions
- Reviewing security-critical or user-facing output
- Any output where "one person said it's fine" is not sufficient
- When a single perspective will miss something structural
- When the cost of an undetected issue is high

## Core Architecture: The Two Pools

The dual-pool system prevents both stale-perspective and no-context failures:

**Fixed Pool (curated, 4-6 personas):** Reviewers matched to the user's domain, style, and known weak spots. Stable across sessions — they learn patterns. Examples: a systems programmer, a security engineer, an API designer, a data scientist. Maintain this pool in project memory.

**Random Pool (fresh each round):** Recruit one new reviewer per round via web search. Search for a keyword relevant to what this round needs, then find a person with verifiable expertise — GitHub profile, published work, conference talk, or documented domain knowledge. An SEO blog or anonymous forum post with no attribution is not a valid reviewer. If you cannot name the person and state why they are qualified, pick a different result.

## Round Structure

Each round: 1 manager + fixed-pool reviewers + 1 random-pool reviewer.

Follow these steps in order:

1. **Recruit the team** — select fixed reviewers with lenses relevant to the review's scope, then recruit 1 fresh reviewer from web search
2. **Extract quotes FIRST** — each reviewer runs a web search before seeing the target, extracting 3-5 verbatim quotes (more for security-critical work). This is non-negotiable.
3. **Independent review** — each reviewer examines the target through ONLY their pre-extracted quotes
4. **Cross-persona synthesis** — deduplicate findings, count concurrences, promote severity
5. **Stop check** — ask: "Did this round find significant issues the previous round missed?" Continue only if yes. Do not run rounds because an arbitrary count says so.
6. **Carryover limit** — at most 2 reviewers carry over to the next round

## Quote-First Rule (Non-Negotiable)

> Extract quotes BEFORE reviewing. Never search for quotes to support an opinion already formed.

Each reviewer runs a web search with the pattern `"[Persona name] [topic] principles"` or equivalent, extracts verbatim quotes, then reviews the target through ONLY those quotes. Findings that do not map to a pre-extracted quote are rejected.

**This is the proof mechanism.** If a finding cites a specific, searchable quote, the AI did not invent it. If there is no quote, there is no finding.

## Symmetric Burden

Make every conclusion expensive — in both directions:

- **Found an issue:** Must cite 1+ specific, verbatim quote from web search
- **Found nothing:** Must cite 3+ quotes the output successfully satisfies, with explanation of HOW

This eliminates fake findings (expensive to fabricate) AND lazy "everything looks fine" (also expensive).

## Severity Classification

| Level | Definition | Action |
|-------|-----------|--------|
| BLOCKER | 2+ concurrences on CRITICAL, or security/data-loss | Fix before anything else |
| CRITICAL | Wrong result, data loss, security violation | Fix before merge |
| WARNING | Fragile, misleading, likely future bug | Fix or document why not |
| NOTE | Improvement, does not affect correctness | Optional |

**Concurrence promotion:** 2+ reviewers independently finding the same issue → promote one level. At least one concurring reviewer must be from the random pool; otherwise the concurrence is "corroboration" (two AI reviewers running the same underlying model may share biases) and promotion is half a level (e.g. WARNING stays WARNING but gets an `[AGREED]` marker).

## Adaptive Round Count

Use the stop check to decide, not a fixed number:

- **Start with 1 round** for any review
- **After each round**, compare: did this round find new, significant issues?
- **Observed patterns** (guidelines, not rules): single-file changes typically converge in 1 round; multi-file in 2; security-critical may need 3+
- **The stop check overrides all patterns** — if round 2 finds nothing new, do not run round 3
- **Asymmetric cost:** a useless round costs as much as one that finds a CRITICAL

## Lightweight Path

For single-file, low-risk changes where full dual-pool is overkill:

- Deploy 1 reviewer (from fixed pool) + web search verification
- Reviewer still extracts quotes before reviewing
- Evidence table still required (single-column)
- If the reviewer finds CRITICAL or WARNING → escalate to full dual-pool

## Output Format

Every round must produce this exact structure:

```markdown
# Round [N] — Manager: [name], Search: "[keyword]"

## Evidence (Web Search Results)
| Reviewer | Search Query | Quotes Extracted |
|----------|-------------|------------------|
| [Fixed 1] | "[query]" | 1. "[verbatim quote]"<br>2. "[verbatim quote]" |
| [Random]  | "[query]" | ... |

## Per-Reviewer Findings

### [Name] ([Fixed/Random])
| # | Severity | Finding | Evidence (Quote) |
|---|----------|---------|-------------------|
| 1 | WARNING | [specific finding] | "[exact quote this maps to]" |

## Cross-Persona Synthesis

| # | Severity | Finding | Concurrences | Promoted From |
|---|----------|---------|-------------|---------------|
| 1 | CRITICAL | [finding] | Reviewer A + Random B | WARNING → CRITICAL |

## Stop Check
**New findings this round vs previous?** [Yes/No — list if yes]
**Continue?** [Yes/No — reason]

## Round Verdict
**BLOCK / CONCERNS / CLEAN**
```

**Without the evidence table, the review is worthless.** The web search results column proves every reviewer did real research. The quote column proves every finding has a source. If you cannot fill the evidence table, do not submit the review — redo it.

## Carryover Rules

- At most 2 reviewers carry over from the previous round
- Their previous findings are visible to the new round (accumulated knowledge)
- The manager changes every round (fresh orchestration perspective)
- The random reviewer is always new

## Anti-Patterns

| Anti-Pattern | Why It Fails |
|-------------|--------------|
| Same reviewers every round | No fresh perspective. The random pool exists for a reason. |
| Skipping web search | Without search results, findings are unverifiable. |
| Quotes extracted AFTER forming opinions | Confirmation bias. Extract first, review second. |
| Evidence table empty or "N/A" | The review did not happen. Redo it. |
| Random reviewer has no identifiable expertise | SEO blog or anonymous forum post ≠ a reviewer. |
| "Everything looks fine" with no quotes | Lazy. Symmetric burden exists to prevent this. |
| More than 2 carryover reviewers | Entrenches groupthink. The limit is a feature. |
| Round N+1 when round N found nothing new | Wasting effort. The stop check said stop. |

## Integrity Check (After Each Round)

Run this self-audit after every round:

1. Would this person actually say this, or am I projecting?
2. Can every finding be traced to a specific, verbatim quote in the evidence table?
3. Did the random reviewer catch something the fixed pool missed? (If not across multiple rounds, the random-pool search keywords are not diverse enough.)
4. **Outcome check:** Did this review change the output in a meaningful way? Track over time: does dual-pool catch issues simpler methods miss?
