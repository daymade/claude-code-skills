# Evidence Discipline Traps

Real failure modes that have broken benchmark-DD runs. Read this first — it's where runs actually go wrong, and every trap is cheap to avoid and expensive to recover from.

## Contents
- Trap 1: inferring relationships from appearances
- Trap 2: the headline-claim attribution
- Trap 3: client ≠ commissioner's asset
- Trap 4: foundation before fan-out
- Trap 5: grade, don't binary
- Trap 6: privacy leak into external search

## Trap 1 — inferring relationships between entities from names/domains

**The trap:** the benchmark's content lives at `community.example.com`, they're a well-known founder, so you write "they run that community" into FACTS. The downstream agents inherit it and confidently build on a relationship that doesn't exist.

**War-story (anonymized):** a founder appeared to "own" a popular paid AI community because their viral post lived there. They were in fact an *invited guest*; the community belonged to a different educator entirely. Treating the guest spot as an owned channel inverted the whole competitive picture — and it was caught only because someone re-read the source and noticed the post literally said "[the community host] invited me to share."

**The rule:** a shared domain / similar name / co-occurrence is an **observation**, not **ownership**. Before any A↔B relationship enters FACTS, verify it against an authoritative source. Always distinguish "I observed X near Y" from "X owns Y."

## Trap 2 — the headline-claim attribution is the #1 target

**The trap:** the benchmark's entire IP narrative rests on one trophy stat, and you take it at face value because it's repeated everywhere — but "everywhere" is the same PR reprinted N times.

**War-story:** the headline was "took product X from 0 → 1M users in a year." Verification found the person was the **departed head of growth**, not the founder; the real founder was someone else (the product's own makers list and registry proved it), and an independent outlet said "3 months to 500K," not "1 year to 1M." The trophy stat was borrowing a former employer's achievement, inflated on top.

**The rule:** find the one claim the subject's whole story depends on, flag it `⚠️ to-verify` in FACTS, and make verifying its *attribution* (who actually did it) and its *magnitude* the highest-priority task in the whole run. Check the product's own about page, the registry, the Product Hunt makers list, LinkedIn — anything **except** the subject's own bio.

## Trap 3 — the commissioner's client is not the commissioner's asset

**The trap:** the commissioner does service work for a big-name platform, so you map the benchmark's "leverage your audience" playbook onto that platform's audience. But the commissioner is a *vendor*, not the owner — they can't pull those levers.

**War-story:** a teardown mapped a benchmark's community-flywheel playbook onto an accelerator the commissioner appeared associated with. The commissioner was actually a paid service provider to that accelerator — they couldn't touch its enrollment or capital. The whole "what you can do" section was advice the commissioner literally could not execute, and had to be rewritten once the ownership was corrected.

**The rule:** in Phase 0, hard-split the commissioner's **owned assets** from **client/partner assets**. Only owned assets are valid mapping targets in Phase 4.

## Trap 4 — establish the foundation before you fan out, not after

**The trap:** excited to start, you launch the multi-agent fan-out, then discover mid-run that two entities you told the agents were related actually aren't. Every result is now contaminated and the run has to be redone.

**The rule:** Phase 0 (verify the entity graph + headline attribution + commissioner resources) happens *before* the orchestration. It's a handful of authoritative lookups that save an entire re-run. Foundation first, fan-out second — never the reverse.

## Trap 5 — grade, don't binary

**The trap:** the user is suspicious ("it's all bubble"), so the run reflexively debunks everything; or the opposite, it treats the survivors as fully proven. Both lose the signal.

**The rule:** the deliverable's value is *separating* real signal from water, not picking a side. Apply the L1–L4 + verdict ladder per-claim (see `evidence_grading_rubric.md`). The best teardowns conclude "the moves are real, the numbers are inflated" — a nuance that only exists if you resist judging the subject as a monolith.

## Trap 6 — never let commissioner context leak into external search

**The trap:** to give the collection agents "context," you paste the commissioner's situation — including client names and strategy — into their prompts. Those agents then run `WebSearch` on it, and the commissioner's private business becomes a query on the open web.

**The rule:** the two-channel split (see SKILL.md) is a hard wall. FACTS (public, about the benchmark) → all agents. COMMISSIONER_CONTEXT (private) → only the Phase-4 mapping agent, which does no external search. Wire it into the orchestration so it cannot be forgotten mid-run — don't rely on remembering it.
