# Landscape synthesis that changes a decision

Read this for Landscape and when continuing an existing competitive analysis.
The output is a supported product judgment, not the number of competitors covered.

## Start from the business and adopted alternative

Read the current product contract, research entry and latest user correction.
Keep intended behavior separate from implemented behavior. Identify the user's
actual adopted workflow or substitute from business records; a familiar manual
workflow can be a stronger adoption baseline than a named competitor. A historical
self-report describes that time, not current adoption or the whole market.
If adoption evidence is absent, preserve that unknown rather than guessing it.

For mechanism comparisons, apply [mechanism evidence](mechanism_evidence.md) to
the scenario's actual entries and evidence depth before deriving a product gap
or borrowing judgment. Keep source-only findings distinct from exercised behavior
and actual outcomes.

Use existing profiles at their verified evidence versions. Expand the source set
only for a question whose answer could change the judgment. Stop collecting when
the evidence decides the next choice; a missing private preference remains unknown.

## Build a small number of decision-bearing judgments

For each material judgment, write the following chain in connected prose. Tables
can support it, but a feature inventory or “borrow feature X” list cannot replace it.

1. **Observation:** cite the exact code, official capability, business record or
   measured behavior. State its version, time and scope where those matter.
2. **Explanation (inference):** explain why that observation affects adoption,
   customer value, coordination cost or another product outcome. Distinguish the
   causal hypothesis from what was observed; correlation or one failure does not
   establish a general causal law.
3. **Choice and consequence:** name what to prioritize, defer, preserve or change
   relative to the current product, and what value/cost that choice trades away.
   Include why this business is affected. Research recommendations do not authorize
   changes to product contracts, engineering scope, pricing or external commitments.
4. **Challenge:** give the strongest evidenced counterexample or competing
   explanation, and the observable result that would overturn or narrow the choice.
   If there is no supported choice yet, say what remains undecidable and name the
   cheapest next check that would decide it. Do not invent an opportunity to fill a template.

Three useful questions, when relevant to the product:

- **Adoption:** does the product improve existing work immediately, or does the
  user have to migrate and maintain a second system before receiving its benefit?
  Account for both switching cost and downstream savings; migration can be worthwhile.
- **Substitutes and platform evolution:** what can the native platform or a thin
  integration already do? Verify the current official boundary when that fact may
  have changed. Distinguish unavailable, experimental and production-supported
  behavior. “Not in the sampled competitors” does not establish uniqueness or a moat.
- **Responsibility for outcomes:** when a workflow involves handoffs, distinguish
  technical acknowledgement, delivery to the consumer, consumption/adoption and a
  qualified combined result. Determine who handles conflicts and owns that result.
  An automatic bridge can reduce collection work; it does not by itself prove
  outcome quality. Do not infer that more workers necessarily cause human overload.

This choice-and-trade-off lens follows the Harvard Business School Institute for
Strategy and Competitiveness's account of customer value and strategic positioning:
[Business Strategy](https://www.isc.hbs.edu/strategy/business-strategy/Pages/default.aspx).
It is a reasoning method, not evidence that this product has a market advantage.

## Account for material opportunities

Bind the opportunity set to the original objective, explicitly named objects and
the frozen Source Register before selecting recommendations. Extract mechanisms
from those inputs, not only the author's shortlisted findings or our current
failures. An evidenced positive opportunity does not require an earlier accident.
Keep stable keys or source/claim locators and request-key associations. Preserve
merged mechanisms' source mappings; retain non-material items' reasons or groups
so removing them cannot silently change the input set.

Use the existing current-analysis entry for each material mechanism's source,
business-increment hypothesis, conditions and costs, owner, minimum falsifier and
disposition. Keep source facts in Strengths; they do not establish adoption.
Split a useful submechanism from an unsafe default path when their choices differ.

- **Adopted:** state the evidenced scope separately for implementation, exercised
  behavior and actual outcome. Narrow implementation adoption may coexist with
  unverified business benefit; it is not verified outcome adoption.
- **Pending:** name the cheapest decision-bearing check, responsible owner and
  exact blocker/reopening condition or authorized next action. Run checks that
  are executable within this stage's authorization instead of restating defer.
  After a stage without new evidence, reassess priority against the original
  objective or explicitly decline adoption; a real blocker leaves only that item
  unresolved. Do not impose periodic retesting or exceed authorization.
- **Not adopted:** record the evidence and trade-off, plus what would reopen the
  choice. Equivalent existing behavior is a valid reason to preserve the owner.

Before closing, reconcile original request keys, discovered keys and decisions;
inspect missing/duplicate keys and evidence scope. For an existing JSON projection,
read [opportunity reconciliation](opportunity_disposition.md) and run its scoped
helper against independently frozen inputs. Then check the original sources and
objective independently of the disposition author's shortlist for omitted material
mechanisms, relevant increments and real blockers. Structural completeness cannot
prove semantic materiality or evidence truth; an independent finding still needs
source readback. Explain an empty relevant set with its bounded-source evidence.
A standalone Profile without an our-product objective needs no adoption table.

## Save understanding where the next session will read it

When a material conclusion changes, update the project's existing research
entry/current-analysis document before ending that stage or handing off context.
Keep frozen profiles and reports as cited sources. If no durable entry exists,
create one in the project's established research location and link it from the
authoritative project entry. Do not create a memory file or an extra per-task ledger.

The continuation entry needs only decision-bearing state:

- Current user objective and corrections, with links to the product authority.
- Accepted and rejected judgments, their evidence versions, scope and failure
  conditions; distinguish user-approved direction from analyst recommendations.
- Open questions and the next check most likely to change a choice.
- Completed evidence/checks that can be reused, plus any changed input or real blocker.

On continuation, read that entry and reconcile it with the latest user request
before selecting an action. Reuse still-valid sources and checks. Re-fetch or
repeat only for requested freshness, changed inputs, missing evidence or a specific
unresolved concern. Resume the unfinished decision; do not restart the inventory
because conversational detail was lost. Save results and next steps, not process
narration, review receipts or a transcript of the analyst's reasoning.

## Acceptance

A reader who knows the product should be able to say which choice changes, why
the evidence supports it for this business, what it costs, and what would make it
wrong. Accurate citations and a complete capability table alone do not pass.
After interruption, that reader should also know what remains to decide without
repeating evidence gathering that is still valid.
