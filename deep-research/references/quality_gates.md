# Quality Gates

Use these gates to test research against its questions and consequential claims. Source counts, domain counts, source-type percentages, citation density, and word counts are diagnostics. They may reveal thin work, but they never prove coverage or quality by themselves.

## Gate 1: Question and Task Coverage (after P2)

| Check | Pass condition | Fix |
|---|---|---|
| Decision questions | Every in-scope question is answered, contradicted, or explicitly unknown | Continue the relevant evidence route or narrow the conclusion |
| Load-bearing claims | Each claim that could change the conclusion has a named evidence route and stop rule | Define the missing route before drafting |
| Original-source capture | Every candidate decisive source has a stable locator and usable excerpt/page/section | Open the original; do not rely on a snippet |
| Counter-evidence | Each provisional conclusion records what could overturn it and what was searched | Run the disconfirming search or label the gap |
| Search provenance | URLs and record identifiers come from actual retrievals | Remove invented or unresolved locators |

## Gate 2: Citation Registry and Evidence Families (after P3)

| Check | Pass condition | Fix |
|---|---|---|
| Claim coverage matrix | Every load-bearing claim maps to supporting, conflicting, or missing evidence | Re-search the uncovered claim or mark unknown |
| Evidence independence | Repeated reports derived from one disclosure, dataset, study, interview, or sponsor are grouped as one family | Collapse the family and correct confidence |
| Source fitness | Each source can directly observe the claim it supports | Replace it or narrow the claim |
| First-party boundary | Authorized internal records are labelled and never counted as external corroboration | Correct provenance and conclusion wording |
| Exclusions | Material excluded sources have a reason | Record the reason and any effect on uncertainty |
| Diagnostics | Counts, domains, type mix, and concentration are reported without pass/fail language | Remove quota-based conclusions |

## Gate 3: Draft Quality (after P5)

| Check | Pass condition | Fix |
|---|---|---|
| Citation validity | Every citation resolves to an approved registry entry | Remove or repair it |
| Claim fidelity | Each citation supports the exact claim, scope, and precision used | Rewrite the claim to match the original evidence or find better evidence |
| Original readback | Every load-bearing claim, conflict, exact number/date, and quotation was checked in the original | Open and record the decisive passage |
| Unknowns | Missing, conflicting, or non-independent evidence is visible at the point it affects the conclusion | Add an explicit limitation or lower confidence |
| Counter-interpretation | Major conclusions include a real alternative when evidence supports one | Add the evidence-backed alternative; never invent a placeholder |
| Format contract | Structure and length follow the user's request | Adjust the document, not the evidence |

## Gate 4: Counter-Review (after P6)

| Check | Pass condition | Fix |
|---|---|---|
| Contradiction handling | The report does not silently choose between conflicting originals | Present the conflict and explain the decision rule |
| Independence check | No conclusion counts syndicated or copied claims as corroboration | Recalculate support by evidence family |
| Precision check | Numbers and quotations match the original source's precision and context | Correct or remove them |
| P6 completion | Evidence and counter-evidence checks are complete; zero issues is allowed | Finish the missing checks and list unresolved uncertainty |

## Gate 5: Final Verification (after P7)

| Check | Pass condition | Fix |
|---|---|---|
| Registry cross-check | Every report citation is valid and every listed source is used | Remove or repair mismatches |
| Load-bearing trace | Every decisive conclusion has a recorded original-source check | Complete it before delivery |
| Low-impact sample | A sample of lower-impact claims traces correctly | If one fails, inspect the full affected claim class |
| Excluded-source check | No excluded source was silently restored | Remove it or formally re-evaluate it |
| Evidence concentration | Dependence on one evidence family is disclosed where it affects confidence | Seek independent evidence or lower confidence |

## Anti-Hallucination Patterns

| Pattern | Fix |
|---|---|
| URL or identifier was never retrieved | Remove it |
| Claim exists only in a task note or search snippet | Open the original or mark unknown |
| Number is more precise than the original | Use the original precision |
| Multiple domains repeat one press release or dataset | Treat them as one evidence family |
| Source authority is high but it cannot observe the claim | Replace it with a fit-for-claim source |
| First-party record is described as external validation | Relabel provenance and narrow the conclusion |
| "Studies show" without identifying evidence | Name the study or remove the phrase |

## Chinese-Specific Patterns

| Pattern | Fix |
|---|---|
| Fake CNKI URL format | Remove and note the gap |
| "某专家表示" without name/institution | Name or remove |
| "据统计" without data source | Add the source or use qualitative language |
| Fabricated institution report | Verify existence or remove |
| Time-sensitive model information lacks AS_OF | Re-search or lower confidence |
