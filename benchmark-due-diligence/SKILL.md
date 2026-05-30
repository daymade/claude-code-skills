---
name: benchmark-due-diligence
description: Adversarial due-diligence on a benchmark you envy — a founder, KOL, company, or product whose claimed success you suspect is inflated. Inline four-phase orchestration — fan-out collection, adversarial verification grading every claim L1-L4 to split marketing bubble from real signal, attribution weighting (product vs timing vs IP vs luck, what's replicable), then mapping the validated playbook onto the user's own resources. Use whenever the user wants to 尽调/对标/拆解 a competitor or role-model, 抄/偷师 someone's playbook, suspects 水分/泡沫 in their claims (Product Hunt #1, 0-to-1M users, funding, 估值几个亿), asks whether wins are 真本事 vs 运气/时机, or says someone is 太成功了/crushing it and wants the real story — even if they never say 尽调, and even though it looks web-searchable (it isn't — the value is structured bubble-busting + attribution + self-mapping, not the search). Prefer over deep-research for debunking inflated claims and extracting a replicable playbook, not a neutral briefing.
---

# Benchmark Due Diligence

Take a benchmark the user envies — a founder, KOL, company, or product whose success looks suspiciously shiny — and produce a teardown that ends in **"what this means for ME"**, not a neutral report. The deliverable answers three questions a balanced briefing never does: *How much of this success is real vs marketing bubble? How much is replicable method vs luck/timing? And what, specifically, can the commissioner do with it?*

This is the adversarial, decision-oriented cousin of `deep-research`. Where deep-research builds a trustworthy picture of the world, this skill **assumes the picture is inflated until proven otherwise** and converts the survivors into the commissioner's own moves.

## CRITICAL: run inline, never `context: fork`

This skill is an **orchestrator** — it spawns parallel collection + verification agents (via the `Workflow` tool, or `Task` agents) and may invoke other skills (`deep-research`, `osint-investigate`, `qcc`). Subagents cannot spawn subagents or call skills. Setting `context: fork` would silently break the entire fan-out. **Do not add a `context` field.** (Same constraint osint-investigate documents — it's a hard runtime rule, not a preference.)

## The one rule that protects the commissioner: two injection channels

Everything the agents see flows through exactly two channels. Keeping them separate is the single most important discipline in this skill:

| Channel | Content | Injected into |
|---|---|---|
| **FACTS** | Already-verified *public* facts about the benchmark (relationships, who-owns-what, the headline claim flagged `⚠️ to-verify`) | **Every** agent — collection, verification, synthesis |
| **COMMISSIONER_CONTEXT** | The commissioner's *private* reality — real resources, client names, strategic intent, what they can actually leverage | **Only the final mapping agent (Phase 4)** |

**Why this split is non-negotiable:** collection and verification agents take their input and run external `WebSearch` on it. If the commissioner's client names or strategy leak into those prompts, they get searched on the open web — a privacy breach. The mapping phase genuinely needs "who is the commissioner"; the collection phase must never see it. Encode this in the orchestration (see `references/workflow_orchestration_template.md`), don't rely on remembering it mid-run.

## Phase 0 — nail the foundation by evidence, not appearance (do this BEFORE any agent)

The fastest way to waste a 12-agent fan-out is to build it on a foundation you *inferred from appearances*. Two failure modes recur and both have burned real runs:

1. **Inferring relationships between entities from names/domains.** "Their content lives at `academy.example.com`, and they're the founder, so they must own that community" — when in reality they were just an invited guest. A shared domain, a similar name, or co-occurrence is an **observation**, not ownership. Verify with an authoritative source before treating any A↔B relationship as fact.
2. **Treating the commissioner's *client* as the commissioner's *asset*.** If the commissioner does service work for an accelerator/brand, that accelerator is the *client's* asset — the commissioner can't leverage its audience or capital. Mapping the benchmark's playbook onto resources the commissioner doesn't actually control produces castles in the air.

So before fanning out, establish by evidence (not vibes):
- **The benchmark's real entity graph** — who owns whom, who merely partners/guests. Don't reason from names.
- **The headline-claim attribution** — the benchmark's whole narrative usually rests on one trophy stat ("took product X from 0 → 1M users"). Are they the founder, or the *departed growth lead*? This is the **#1 to-verify target**; write it into FACTS with a `⚠️`.
- **What the commissioner truly controls** — separate *owned assets* from *client/partner assets*.

Write the results into `FACTS` (public half) and `COMMISSIONER_CONTEXT` (private half). A shaky foundation makes every downstream agent confidently wrong.

## The four-phase orchestration

Use the `Workflow` tool (preferred — deterministic fan-out, see the ready-to-fill template in `references/workflow_orchestration_template.md`) or `Task` agents. Scale agent count to how thorough the user wants (a few dimensions for a quick read, 6+ with multi-vote verification for a deep audit).

**Phase 1 + 2 — collect → verify, per dimension, as a pipeline** (each dimension verifies the moment its collection finishes; no global barrier):

- **Collection agent** — *objective* stance. Every finding carries a source URL and a `source_kind` (`对象自述/营销` vs `第三方独立信源` vs `混合`). Anything not found goes in `gaps` — **never** filled by guessing.
- **Verification agent** — *adversarial, default-skeptical* stance. Grade every claim `L1–L4` and rule `坐实 / 大体可信 / 存疑 / 证伪-水分`. The job is to actively hunt **falsifying** evidence, especially for the headline claims (the trophy stat, "#1 ranking", funding amount, user counts). `bubble_summary` names the biggest water in that dimension.

Grading rubric, `source_kind`, verdicts, and both JSON schemas → **`references/evidence_grading_rubric.md`**.

Typical dimensions (tailor to the benchmark type — person / company / product):
1. Subject background **+ headline-claim attribution** (the #1 bubble target)
2. Corporate base — entity, founding, funding/valuation
3. Core product/business **real metrics** — user counts, revenue, rankings, awards, cross-verified against third parties
4. Playbook teardown — platform matrix, persona, content types, how they borrow other people's audiences, how personal IP funnels to the product
5. Comparison sample — a structurally-similar peer or parallel path
6. Sector + how this class of playbook usually wins **and usually fails**

**Phase 3 — synthesis: due-diligence conclusion** (single agent, consumes all verdicts):
1. Real relationship map (correcting the common misreadings from Phase 0)
2. **Bubble-busting table** — claim | evidence level | verdict | one-line basis, sorted by most-water-first
3. Playbook teardown — concrete, copyable actions
4. **Attribution breakdown (the core)** — what share of the success is product vs market-timing vs personal-IP-marketing vs operations? Give % ranges with reasons, and explicitly split *replicable method* from *luck / timing / non-transferable endowment*.

**Phase 4 — synthesis: what this means for the commissioner** (single agent; consumes Phase 3 **+ COMMISSIONER_CONTEXT**):
1. **Resource-mapping table** — benchmark's playbook elements × the commissioner's real resources; tag each cell ✅ borrow-able / ⚠️ not-replicable (luck/timing) / 🔄 already-doing / 🚫 bubble-don't-copy, one line each
2. Landing points — exactly how the commissioner uses it (their to-B service / their own IP / their tooling)
3. Action list + open questions (what's still unconfirmed)

Attribution weighting and the four-tag mapping framework → **`references/attribution_and_resource_mapping.md`**.

## Don't rebuild what already exists

This skill's edge is the *adversarial bubble-busting + attribution + commissioner-mapping* layers. The plumbing underneath is not novel — reuse it:

- **Fan-out collection / source governance** — borrow the lead-agent + subagent pattern from `deep-research`. (What's unique here is the skeptical verification stance and the L1–L4 bubble grading, not the parallelism.)
- **Person-subject identity / footprint checks** — invoke `osint-investigate` (ACH hypothesis matrix, Bellingcat-style pivots) rather than re-deriving identity attribution.
- **Mainland-China corporate registration / funding** — invoke the `qcc` family of skills for 工商 data.
- **Social-platform playbook data** — the `agent-reach` CLI covers B站/小红书/抖音/YouTube/X.

## Read before you run

- **`references/evidence_discipline_traps.md`** — the recurring traps (inferring relationships from appearances, headline-claim attribution, client-vs-asset, foundation-before-fan-out, grade-don't-binary, privacy leak) with real teardown war-stories. Read this first; it's where runs actually break.
- **`references/evidence_grading_rubric.md`** — L1–L4, source_kind, verdicts, collection/verification schemas.
- **`references/attribution_and_resource_mapping.md`** — attribution weighting + four-tag mapping + landing-point framework.
- **`references/workflow_orchestration_template.md`** — a ready-to-fill `Workflow` script with the FACTS / COMMISSIONER_CONTEXT injection split already wired in.

## Next Step

After the due-diligence conclusion is ready, suggest the natural follow-on (opt-in, never auto-run):

```
Due-diligence teardown is done.

Options:
A) Render it as a shareable PDF report — pdf-creator (Recommended if this goes to a partner/team)
B) One dimension needs deeper neutral background — deep-research on that sub-topic
C) No thanks — the markdown teardown is enough
```
