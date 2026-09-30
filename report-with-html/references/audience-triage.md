# Audience triage for step 9's independent review

Referenced from: SKILL.md step 1 (`读者已知清单`), step 9 (post-review triage), the Loop
Contract's third exit, and step 10 acceptance item 4. This file holds the mechanism and its
grounding; SKILL.md's own text stays short and points here — same split as
`design-principles.md`/`visualization-patterns.md` already use.

## The problem this solves

Step 9's reviewer is deliberately built with **no inherited context** — `references/independent-review-prompt.md`
tells it "you have never worked on this project, don't know anyone in it, don't know any
background... don't go read other files, don't search any proper nouns." That persona is
the point: it is what lets the reviewer catch things the author is blind to. It should not be
weakened.

But step 1 (`Define success`) legitimately lets an author declare a narrow, already-informed
audience — "the author himself, verifying his own day's work, already familiar with every
system and script involved." When that declaration is honest, the zero-context reviewer is
*guaranteed* to flag domain terms that declared audience already knows, on every single
delivery, because its persona is strictly more ignorant than any real reader of an internal
report ever is. Before this mechanism existed, the only thing standing between "real defect"
and "reviewer persona doing exactly what it's designed to do" was the author's own
in-the-moment judgment call — undocumented, unfalsifiable, and made by the same person whose
work is being judged.

Observed failure (2026-09-13, `favorites-ledger.html`): two independent review cycles both
answered the closing "can you act on this page alone?" question "no." Cycle 2's reasons were
narrower than cycle 1's, but all of them reduced to "a stranger doesn't know what `verify_gate`
/ `circuit breaker` / `rescue_rendered.py` mean" — terms the report's own declared reader
(its author, hours after writing the code that uses them) already knew cold. Nothing in the
workflow could tell the difference between that and a genuine comprehension defect; the author
had to reconstruct the distinction by hand, after the fact, with no committed record to check it
against.

## The mechanism

**1. Declare the list before the first review, not after.** Step 1 adds a required field,
`读者已知清单`: the specific terms, scripts, or systems the declared audience is assumed to
already know, written in backtick-quoted, checkable form —
`` `verify_gate`、`rescue_rendered.py`、`circuit breaker` ``. This is committed to `page.html.gate.md`
*before* step 9 dispatches its first reviewer. Writing it after seeing a review's findings is
the failure this guards against — a list assembled to explain away whatever a reviewer happened
to flag is not a declaration, it's a retrofit, and it would make every future finding
unfalsifiable by the same move. **`init --force` re-renders and refreshes every timestamp on
every call, whether or not `page.html` changed a single byte** — an earlier draft of this file
claimed the gate/page mtime comparison would incidentally catch a post-review retrofit; a
second independent review (2026-09-13) correctly showed that's false, since re-rendering an
unchanged page still produces fresh files. `delivery_gate.py check` instead diffs the current
`读者已知清单` answer against the copy preserved in the gate file's own "上一轮的答案" appendix
(present from the second `init` onward): any term new since that snapshot must carry a `补记`
marker in the same answer, or `check` fails it as an unlabeled retrofit — see the Machine
consumer section below for what this does and does not close.

**2. The reviewer prompt does not change.** Do not feed the reviewer this list, and do not
mention its existence to it. Telling a reviewer "the reader already knows X" before it reads
the page either gets X excused from a *real* comprehension check or, worse, teaches the
reviewer what answer you want — the exact failure `independent-review-prompt.md` already
guards against by using its prompt verbatim with no per-run customization.

**3. After a review returns, triage each "I don't understand this" finding against the
declared list — mechanically where possible.** For every term the reviewer flagged:
- **On the list** → log it as `audience-declared-known` with the one-line reason, and it does
  not count toward the Loop Contract's same-axis-recurrence test. This is a named, expected
  phenomenon in usability research — a **phantom problem**: "identifying a label as confusing
  for users, when in fact the specialized user base is very familiar with the term" (Jeff
  Sauro, [*Managing False Positives in UX Research*](https://measuringu.com/false-positives/),
  MeasuringU, 2016).
- **Not on the list** → check whether it is a genuine omission (the declared audience really
  would already know it, the list was just incomplete) or a genuine gap (even the declared
  audience might stumble) → the latter counts as a real finding, unchanged from today's
  behavior. A genuine omission gets added, but labeled where it's added
  (`补记于 cycle N 审阅之后`), not blended silently into the list — `delivery_gate.py init
  --force` already preserves the pre-cycle list verbatim in the gate file's "上一轮的答案"
  appendix, so an unlabeled addition is trivially caught by diffing against it. Say it plainly
  instead of relying on someone doing that diff.
- The disposition and its one-line reason go in the same review-outcome file step 9 already
  requires ("each finding with its disposition and reason") — this is not a new artifact, it's
  a required column on the one that already exists.

**4. The author's triage is provisional; step 10 independently re-derives it.** An earlier
draft of this mechanism claimed the triage was "a lookup, not a re-judgment" and let the
author's disposition stand on its own, analogous to `delivery_gate.py`'s `COORD_SCRIPT_LABEL`
check (does this referenced file exist — yes/no). An independent review of this design (2026-09-13)
correctly rejected that analogy: whether a reviewer's paragraph of prose "reduces to" a single
listed term is an interpretive judgment, not a file-exists check, and it is exactly the kind of
judgment `Step 10. Independent acceptance` in SKILL.md already argues cannot be self-certified
("the author still ruled on whether their own evidence sufficed... a second pair of eyes does").
So the author's first pass is cheap and provisional — quote the reviewer's finding verbatim
next to the list entry, so the reduction is checkable — and step 10's independent, non-fork
agent is the one that actually re-derives each `audience-declared-known` disposition from the
quote and the list, without reading the author's stated reason first, before it counts as
disposed. This is the *same* separate-role arbitration pattern the adversarial-review
literature uses (Sources §3) — it doesn't need a new dedicated role because step 9/10 already
put one there for exactly this reason; it needed pointing at this specific judgment, which the
first draft of this file failed to do.

**5. A CAPPED EXIT explained entirely by declared-known terms is a third disposition, not a
stall.** The Loop Contract in SKILL.md step 9 gets a third exit alongside SUCCESS EXIT and
CAPPED EXIT:

```text
AUDIENCE-MISMATCH EXIT: every reason behind a cycle's "no" on review-prompt item 9 is disposed
          as audience-declared-known (§3 above) — the reviewer persona did exactly what a
          zero-context persona always does to an honestly-narrow-audience report, and nothing
          here indicates the declared audience itself would be lost. Ship. Log the disposition
          table in the review-outcome file. This is not the CAPPED EXIT above — it does not go
          to the user as a blocked report, because there is no genuine unresolved finding left
          to decide. Fires after cycle 1 alone if nothing survives triage: REMEDIATION calls for
          "reproduce the finding, apply one bounded fix" — with no real finding, there is
          nothing to reproduce or fix, so a mandatory cycle 2 would spend a review on an
          unchanged page and get the same phantom verdict back.
```

If even one item-9-driving reason survives triage as a real gap, the ordinary CAPPED EXIT
applies unchanged: stop, report the backlog, do not self-authorize a third reviewer.

## Machine consumer

Declaring a list nobody checks is exactly the failure mode `delivery_gate.py`'s own header
comment warns about: "a rule whose only referee is its author gets comprehended instead of
executed." Three checks exist for this field (implemented and calibrated 2026-09-13 —
`AUDIENCE_LABEL` in `scripts/delivery_gate.py`, next to `COORD_SCRIPT_LABEL`):
- The generic placeholder scan already used for every Stage-1 field (an unfilled `读者已知清单`
  fails `check` the same way an unfilled Stage-1 answer always has — no new code, existing
  mechanism; the current Stage-1 list is `STAGE1` in `delivery_gate.py`, not repeated here).
- Every backtick-quoted term in the answer must appear in `extract_visible_text(page)` — the
  page's reader-visible text, not its raw HTML source. A term stuffed into a comment, `alt`
  text, `aria-hidden` content, or inline `display:none` passes a naive substring-of-source
  check but was never something a reader actually saw; `extract_visible_text` excludes those
  cases before matching (it cannot exclude a CSS-class-driven hide, which needs a browser's
  computed styles — that gap is why step 10 below also checks this by hand). A declared-known
  term absent from the visible text entirely is dead weight: padding, or evidence the term was
  cut from the report after the list was written.
- Every term in the current `读者已知清单` answer is diffed against the copy of that same
  answer preserved in the gate file's "上一轮的答案" appendix (from the second `init` onward —
  there is nothing to diff against on the very first round, by construction). A term absent
  from the prior snapshot must carry a `补记` marker in the current answer or `check` fails it.
- Step 10 acceptance item 4 (`Review completion`) independently re-derives each
  `audience-declared-known` disposition from the reviewer's quoted finding and the list — see
  §4 above for why this can't be the author's own call — and separately checks that a disposed
  term is something the reader would actually encounter, not one sitting in markup a person
  never reads. This reuses the existing acceptance pass rather than adding a new one.

**What none of this closes.** The whole mechanism rests on step 1's audience declaration being
honest — "this report's real reader already knows X" is a claim about the world that no
mechanical check can verify, only make cheaper to state honestly and more annoying to state
dishonestly (a term must be real, visible, and traceable to when it was added). An author who
decides upfront, before any review, to declare an unrealistically broad audience has not
triggered any retrofit check — nothing here catches that, and nothing short of a human who
knows the actual reader (step 10, or the user) can. Treat step 10's independent read of the
audience declaration itself, not just of individual dispositions, as part of what "re-derives
it" means.

## Sources (2026-09-13 research pass, three independent web-search agents, one axis each)

None of the three axes found a single existing methodology that names this exact combination
(strict zero-context reviewer + a separate, evidence-checkable triage step). The mechanism
above is assembled from adjacent, independently-sourced precedent, not copied from one place.
Each claim below is attributed to what was actually found; none is invented.

**§1 — Usability/UX research methodology**
- Employees/insiders are a legitimate test population *when they are the real target audience*:
  Angie Li, [*Employees as Usability-Test Participants*](https://www.nngroup.com/articles/employees-user-test/),
  NN/G, 2016.
- "Phantom problems" — the named concept behind declared-known-term findings — Jeff Sauro,
  [*Managing False Positives in UX Research*](https://measuringu.com/false-positives/),
  MeasuringU, 2016.
- Single evaluators are a statistically unreliable, non-reproducible signal on their own —
  only ~20% finding-overlap across evaluators in the cited data — Hertzum, M., & Jacobsen,
  N. E. (2001), *The Evaluator Effect*, International Journal of Human-Computer Interaction,
  15(1) ([author copy](https://mortenhertzum.dk/publ/IJHCI2003.pdf)). This is why the triage
  step treats a single review cycle's raw findings as inputs to a decision, not as the decision.
- Cognitive Walkthrough requires a *written, pre-declared* statement of assumed user
  background before the walkthrough runs: Wharton, Rieman, Lewis & Polson (1994), in Nielsen &
  Mack (eds.), *Usability Inspection Methods* ([ACM DL](https://dl.acm.org/doi/10.5555/189200.189214));
  modern treatment in Kim Flaherty, [*Evaluate Interface Learnability with Cognitive
  Walkthroughs*](https://www.nngroup.com/articles/cognitive-walkthroughs/), NN/G, 2022. This
  supports committing the assumed-background list *before* the review runs — it does **not**
  support keeping the reviewer blind to it: CW's own practice is to hand that list *to* the
  evaluator, so it can role-play the target user. This mechanism deliberately does the
  opposite (§2 below) for a different, unrelated reason — not because CW endorses it.
- Novice evaluator output filtered by an expert before it counts as an official finding: De
  Lima Salgado et al. (2018), [*Guiding Usability Newcomers to Understand the Context of
  Use*](https://link.springer.com/chapter/10.1007/978-3-319-76430-6_7) (collaborative
  heuristic evaluation).
- Krug's "recruit loosely, grade on a curve" — keep the test population/persona loose, then
  discount findings against a known mismatch at interpretation time, rather than tightening
  the persona itself (multiple secondary summaries of Krug's *Rocket Surgery Made Easy*
  cross-confirm this maxim).

**§2 — Technical writing / documentation style guides**
- DITA's `audience` / `experiencelevel` metadata — the concrete precedent for a written,
  structured "who is this for / what do they already know" field attached to a document,
  which is what `读者已知清单` is modeled on.
- RFC convention's "assumed-familiar" terminology framing — a document-level declaration of
  what the reader is assumed to know, checkable against the document's own prerequisites
  section.
- Fagan inspection kickoff briefings and exploratory-testing "charters" show that giving
  reviewers a scope declaration is an established, non-controversial practice in other mature
  review methodologies — it is not automatically "polluting independence." (This is why step
  9's reviewer prompt itself stays unchanged in this design: the research found the
  contamination risk is manageable in general, but this skill still chooses not to take it,
  because the specific failure mode being guarded against — a reviewer that learns to produce
  the answer it's fed — is exactly the one `independent-review-prompt.md` was already
  hardened against.)
- Honest gap: Diátaxis (tutorials/how-to/reference/explanation) does not address the
  internal-informed vs. external-naive axis at all — confirmed against the framework's own
  site. Its organizing axis (task-need) is orthogonal to audience-knowledge, not a competing
  answer to it.
- Honest gap: no source was found for a review process that formally states "do not penalize
  a finding the document's own front matter already declared as assumed-known" as a named,
  citable rule. The mechanism above is a reasoned design built from DITA's conditional-content
  architecture, not a copy of an existing template.

**§3 — Software QA / code review / definition-of-done practices**
- ISO 9241-11 and ISO/IEC 25010 require "specified users" and "context of use" as *mandatory,
  explicit* parameters before usability/quality-in-use can even be evaluated — the standards-body
  precedent for "audience is a required input to the acceptance criteria," even though ordinary
  agile "Definition of Done" templates (searched: ~10 DoD templates across Scrum.org, Atlassian,
  Miro, Planio, Plane, KaiRise) do not carry an explicit audience field.
- The strongest single analogy: Martin Fowler (from Ian Robinson), [*Consumer-Driven
  Contracts: A Service Evolution Pattern*](https://www.martinfowler.com/articles/consumerDrivenContracts.html) —
  "consumer contracts are... non-authoritative with regard to the total set of contractual
  obligations placed on the provider." An undeclared consumer's unmet expectation does not
  automatically breach the provider's contract. Step 1's audience declaration is the
  authoritative contract; the zero-context reviewer is an undeclared consumer, and its
  "I don't understand X" is not automatically a breach unless X falls outside what the real
  contract promised.
- Google SRE Workbook, [*Postmortem Culture*](https://sre.google/workbook/postmortem-culture/):
  explicitly names undefined internal jargon in a postmortem as a defect, but its prescribed
  fix is a **glossary**, not a rewrite of the informed-reader prose — "if you're unfamiliar
  with X, read the glossary before you continue." This is the precedent for preferring a
  glossary/known-terms declaration over diluting register when a finding does turn out to be
  real.
- Named triage-role patterns from adjacent domains — Red/Blue/Purple team in security
  ([Praetorian, *Red Team vs. Blue Team vs. Purple Team*](https://www.praetorian.com/security-101/red-team-vs-blue-team-vs-purple-team/)),
  and Builder/Critic/Moderator or Maker/Checker/Arbiter in adversarial code review
  ([ASDLC.io, *Adversarial Code Review*](https://asdlc.io/patterns/adversarial-code-review/);
  [Augment Code's guide](https://www.augmentcode.com/guides/adversarial-code-review), which
  names the role "Arbiter" and recommends "run advisory comments first to calibrate trust and
  false positive tolerance...convert critical findings into blocking gates"). These all use a
  *separate* role for arbitration because the arbitration is a judgment call — §4 above reaches
  the same conclusion here: the author's first pass is advisory, and step 10's independent agent
  is this mechanism's Arbiter for whether a disposition actually holds.
- SAST/DAST false-positive triage discipline is the clearest "must be documented, can't just
  disagree" precedent: "a finding should not be closed as a false positive simply because
  someone disagrees with it" ([Invicti, *False Positive Triage
  Checklist*](https://www.invicti.com/blog/web-security/false-positive-triage-checklist);
  [Astra Security's triage guide](https://www.getastra.com/blog/dast/false-positive-triage/)) —
  the source for requiring a logged reason on every disposition, not just a checkbox.
- A real two/three-stage acceptance precedent where no single layer has final say over its own
  findings: Stribog, [*Catalogue Audit: 49 Articles, 342
  Defects*](https://stribog.com/blog/catalogue-audit-49-articles-342-defects-what-we-found) —
  an independent third pass overrode the second pass's severity 13 times and reframed 177 of
  its "confirmed" findings, while also catching 29 the second pass missed.

**Evidence-quality caveats, named rather than smoothed over (2026-09-13, second independent
review of this design):** these sources are not uniform in strength and this file's prose
mostly doesn't flag that. The Sauro "phantom problem" citation's own evidence base is
expert-prediction-vs-real-user-test data; nothing in this mechanism runs an analogous real-user
check — the term is borrowed for the *shape* of the failure, not as proof this specific
instance clears the same evidentiary bar. Hertzum & Jacobsen's ~20% evaluator-overlap finding
is about diverse *human* evaluators; a step 9 re-review is very likely the same model re-run
against the same fixed prompt, so the diversity this mechanism actually gets is narrower than
what that citation's own data was measuring — cited correctly for "one review isn't the final
word," not for "reviews are as independent as Hertzum & Jacobsen's subjects were." And Stribog's
write-up is a vendor's own blog post about its own service, sitting in the same list as
peer-reviewed HCI papers with no signal distinguishing the two. None of this makes the design
wrong; it means "grounded in research" here spans a fair range of source authority, and this
whole mechanism — the incident that motivated it, the three-axis research pass, and its first
implementation — was built same-day, which is exactly the condition under which drafting speed
and self-review both have the least time to surface exactly these gaps.
