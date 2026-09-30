---
name: report-with-html
description: >-
  Produces the reader-facing HTML artifact — report, dashboard, architecture view, data browser, or
  review workbench — evidence-backed, browser-verified. Use when the deliverable IS a visual HTML
  report, or the user asks for an HTML/web presentation. Load data-visualization-discipline for
  chart judgment. Not for chat status or Markdown prose unless asked to become a report; not for
  PowerPoint (deck-creator Route C).
---

# report-with-html

Create a reader-facing HTML artifact whose information architecture follows the
reader's question—not the author's implementation checklist.

## Trigger boundary

Use this skill when the requested artifact is itself a visual HTML report or
interactive information tool. Typical outputs include:

- a system, architecture, journey, causal, decision, comparison, or gap view;
- a client-facing data report or one-pager;
- a data/archive browser or review workbench;
- an explicitly requested HTML/web presentation.

Do not trigger it for a normal status reply, generic review, code diff, issue list,
or Markdown document. Those tasks may be reported in chat unless the user explicitly
asks to turn the result into a visual HTML artifact.

The default delivery is the verified HTML opened in a browser. A PNG is a QA artifact
and is delivered only when the user asks for an image. If the user needs editable
PowerPoint, finish and verify the HTML first, then use `deck-creator` (Route C).

## SSOT map

**Visualization judgment lives in another skill — load it before designing any chart or
geometry.** `data-visualization-discipline:data-visualization-discipline` owns which form
fits the content, which chart type and summary statistic to use, whether segments may be
aggregated, how many categorical colors are allowed, cross-view color identity, table
discipline, the antipattern list, and the pre-delivery self-check gate. This skill does not
restate those rules; a second copy would drift. This skill owns the report page itself:
register calibration, the component shelf, the approved corpus, page order, the decision-card
contract, interaction contracts, and browser verification.

- Reader-facing principles, content boundary, decision-card contract, accessibility:
  `references/design-principles.md`
- **Layout density (铺满画布 / 消灭空洞), page order as narrative rhythm, the HTML table
  micro-spec, and form → component implementation:** `references/visualization-patterns.md`.
  **Not conditional on having already chosen a form** — most of it applies to every page
  regardless of what you draw. This line used to open with "Chosen form →", which reads as a
  precondition; a 2026-08 delivery filed the file under "the implementation lookup I'll consult
  if I build one of those components", never opened it, and shipped a page missing three of its
  rules. The gate a step hides behind must not be a step you have not taken yet.
- Approved corpus and register calibration:
  `references/approved-examples.md`
- Reusable interactions and their keyboard contracts:
  `references/interaction-components.md`
- Long-lived/generated-page maintenance:
  `references/long-lived-report-maintenance.md`
- Fresh-context review payload:
  `references/independent-review-prompt.md`
- Warm-paper starter implementation:
  `assets/report-template.html`

**Read these before authoring** — the principles, the patterns file, the closest
approved example, and `data-visualization-discipline`. The rest are activated by what the
artifact actually contains.

Do not let "read only what's activated" decide the required sources above. That filter operates over needs
you already know you have, so it is structurally unable to surface *a step you don't know
exists* — and it hands the skip a legitimate-sounding rationale, which is worse than forgetting.
These are the sources that tell you which steps exist.

## Product contract

### Reader and evidence first

Write down the audience, the decision or understanding the page must enable, and the
authoritative sources before choosing components. Retrieve current facts during this
session. Every number needs a unit, date/window, and traceable source; unknown values
stay unknown.

Screen copy may contain a factual takeaway when the same page visibly supports it
with data, mechanism, or primary evidence. Remove unsupported value judgments,
slogans, maxims, superlatives, and unproven causal claims. A grep pattern such as
`不是.*是` only surfaces *candidates*; its presence alone is never a failure. Judge each
candidate with the test in `design-principles.md` §3 — delete the sentence, and ask
whether the reader loses a fact they could have checked on this page, or only an opinion.
The first stays, the second goes.

Use complete, audience-readable language. Internal codes, private shorthand, naked
algorithm scores, and unexplained abbreviations do not belong on the page.

### Let the question choose the skeleton

- “How does it work?” → journey, architecture, or mechanism.
- “What should we decide?” → options, trade-offs, decisive unknowns, recommendation.
- “Why did it happen?” → timestamped causal chain plus falsifying evidence.
- “Which is better?” → entities × criteria on a common baseline.
- “Let me inspect this collection.” → list/detail, search/filter, state, provenance,
  deep links, and review-output return path.

Implementation state is a badge on that skeleton, not the skeleton itself. A missing
dependency, unverified result, or unknown must remain visible.

### Geometry and real evidence

Use position and length for important quantitative comparisons. Color carries category
or state, not a second independent measure. A geometry needs an explicit encoding key
and a data-supported readout.

Do not redraw the same entity set in multiple decorative forms. Each section must
answer a different sub-question. For UI or visual-product review, real screenshots are
the primary evidence: crop the exact defect with enough surrounding context and keep
before/after crops identical.

Use an installed mature charting capability or the current project's declared chart
stack for statistical charts. If neither exists, research and select a maintained
library before implementing; do not hand-build a chart engine.

### Interaction and accessibility

**Evidence comes to the reader; the reader does not travel to the evidence.** When the
page cites a clause, a screenshot, or a source passage, embed it at the point of citation
— an in-place overlay or drawer that returns the reader to where they were. An anchor
that throws the reader elsewhere on the page and expects them to navigate back is
prohibited, not merely discouraged; `design-principles.md` §13 holds the rule and the
user's own words for it. Hash anchors remain correct for nav and for external deep links:
what is banned is being forced to leave mid-read.

Copy approved interactions from `assets/components/` instead of rebuilding them.
Behavior is part of the component contract; register-specific styling may change.
Copying a component is three steps, and the third is the one that gets skipped:

1. Read the component file's own header contract — it states prerequisites the registry
   table does not repeat (required CSS tokens, required DOM structure, which element
   types it scans). `citation-drawer`, for instance, only linkifies inside `<section>`
   elements and needs a generator-produced `#s9`.
2. Make those prerequisites true in your page.
3. **Click the component's primary interaction in a real browser before delivery.** A
   component can be present, id-unique, tag-balanced and completely inert — every static
   check passes while the feature does nothing. Only the click distinguishes those two
   worlds.

Every interaction must work without a pointer:

- use native buttons, links, and dialogs when available;
- provide a visible close control and Escape handling for modal surfaces;
- keep focus inside an open modal and restore it to the invoker on close;
- expose names, states, and relationships with semantic HTML and ARIA;
- preserve visible focus, logical tab order, and usable narrow-screen geometry.

## Workflow

1. **Define success.** Record audience, question, source set, required evidence,
   delivery form, and what would make the artifact fail. The gate template (step 5) also
   always carries a `读者已知清单` slot — fill it when the declared audience is narrower than
   "any reader" (an internal, already-informed reader rather than a stranger): the specific
   terms, scripts, or systems that audience is assumed to already know, in checkable
   backtick-quoted form. When the audience genuinely is a stranger, write
   `不适用: <why>` — the slot still has to be filled, just with that answer. Write this before
   step 9's first review, not after one returns findings — see `references/audience-triage.md`
   for why the ordering is load-bearing and how step 9 uses this list.
2. **Calibrate.** Read all four mandatory files — `design-principles.md`,
   `references/visualization-patterns.md`, the closest entry in `approved-examples.md`, and
   `data-visualization-discipline` — then any component reference the artifact activates.
   Use the nearest approved register; do not copy a skin blindly. (This step used to say
   "the *activated* pattern reference", which let the patterns file be filed as not-yet-needed
   and skipped; the SSOT map above explains why that filter cannot work here.)
3. **造量纲 — before a line of HTML.** Section by section, name what in the content is
   **ordered / has magnitude / has direction / has a counterpart**, and write that quantity
   down. Each geometry then carries it in the markup:

   ```html
   <div data-geometry="退款家数刻度轴"
        data-derived-from="退款家数（0–30 家线性，共同基线；位置=家数÷30）"> … </div>
   ```

   **A section whose quantity you cannot name is prose.** Say so and leave it as prose —
   wrapping the sentence in a coloured box is the antipattern, not the fix.

   **A number and the coordinate that encodes it come out of the same script.** As soon as
   any geometry is positioned by a computed value — a bar length, a tick at `left:30.80%`,
   an axis label, a line's endpoints — write a small no-dependency script that prints *both*
   the finding and the coordinates, paste from its output, and ship the script next to the
   page. Computing the value in prose and then hand-writing the SVG attribute is a two-copy
   fact with no `grep` that can catch the drift: it is how the same quantity ends up rounded
   two different ways in two sections, and how an axis label lands at the position of a
   smaller number — a lie factor authored by the very page arguing against lie factors.
   Shipping the script also makes the drawing auditable: a reader re-runs it and diffs.
   Step 5's gate asks for that script's path and stats the file, so this rule has a machine
   consumer rather than being one more thing only you referee. (It was prose-only for exactly
   one version, and an independent audit named it the next rule likely to get skipped — the
   variable that decides whether a step survives is not "does it produce an artifact" but
   "does anything downstream consume the artifact". The nine visual-discipline gates were
   already artifact steps when they got skipped.)

   Why this is a numbered step rather than a principle: the rule already lived in
   `design-principles.md` §2 *and* in `data-visualization-discipline`, and was read in both
   places immediately before a delivery that shipped eight prose sections and one geometry.
   A judgment step whose only referee is its author gets **comprehended instead of executed**.
   These two attributes are what let a script see whether the step happened.
4. **Author.** If a calling Skill supplies a user-approved local report form that still
   fits this report's output contract, use that form as the starting point. Otherwise
   start from `assets/report-template.html` or an approved example. The calling Skill
   owns template approval and storage; this Skill owns report generation and visual QA.
   Keep customer facts and conclusions tied to current evidence, and do not copy the
   caller's template into this Skill's update-owned `assets/`. Use actual shelf
   components. If the page embeds mutable source documents, follow the long-lived-report
   reference and keep generated and authored regions separate.
5. **Run the delivery gate — it produces the artifacts the judgment steps otherwise skip.**

   ```bash
   uv run <skill-dir>/scripts/delivery_gate.py init  page.html [--height 9600]
   #   → renders page.png AND page--masked.png (all text transparent — the squint test,
   #     headless; see the script header for the technique's provenance)
   #   → scans for ≥120 CSS px whitespace voids (visualization-patterns.md 版面填充纪律)
   #   → writes page.html.gate.md: the delivery gates + the stage-1 questions
   #     (`STAGE1` in delivery_gate.py owns the exact list), every slot empty
   # Read the masked PNG segment by segment, fill every slot, then:
   uv run <skill-dir>/scripts/delivery_gate.py check page.html   # exit 1 until it passes
   ```

   `check` fails on: a missing or stale masked render (so 遮字自测 cannot be claimed without
   the evidence), a percentage-driven visual with no `data-geometry`/`data-derived-from` (so
   造量纲 cannot be skipped — pure-layout boxes opt out **visibly** with `data-layout`), any
   unfilled slot, and a gate file older than the page (so "filled the checklist, then kept
   editing" cannot pass). It asserts these steps **happened**; it says nothing about whether
   the conclusions are right — that is still steps 9 and 10.
6. **Render a fresh artifact.** Step 5 already produced `page.png` at the height you passed
   it; re-render here only when you changed the page since, and **pass the same height** —
   `render_report.sh` overwrites in place, so a shorter H silently replaces a good render with
   a truncated one.

   ```bash
   <skill-dir>/scripts/render_report.sh page.html page.png 1300 2400   # H is an example, not a default
   ```

   `<skill-dir>` is this skill's own directory — its absolute path is given to you when
   the skill loads. Bare relative paths like `report-with-html/scripts/…` only resolve
   from one particular parent directory and fail with exit 127 anywhere else.

   The renderer fails without a new valid PNG and never treats an existing output as
   success. Set `CHROME_BIN` to an explicit managed Chrome/Chromium executable in CI
   or a shared-browser environment; an invalid override is a hard failure.

   Then split it and read every segment — a tall PNG exceeds what one Read can resolve:

   ```bash
   uv run <skill-dir>/scripts/crop_segments.py page.png --segments 5
   ```

   **That step is also where truncation is caught.** Chrome screenshots exactly the
   `--window-size` you passed and never grows to fit, while the renderer's PNG check only
   proves the bytes are a valid image — so a page taller than your H loses its tail
   silently, and §6 of `design-principles.md` puts the strongest conclusion last. The
   splitter warns when content runs to the final canvas row, which means the canvas cut
   through the page rather than the page ending inside it. It is checked here rather than
   in the renderer because the only non-mutating way to measure page height is a second
   `--dump-dom` call, and that hangs on some pages — a gate that can never measure is a
   gate that always skips.

   **That warning has one false positive, and its obvious remedy does not terminate under
   it — so read the warning's own two branches before you re-render.** If the page sizes
   anything in `vh` (a scrolling panel at `max-height:78vh` is the common case), headless
   `1vh` is `H/100`, so raising H grows that element too and content stays pinned to the
   canvas bottom at *every* H. Discriminate once by rendering at a clearly different H and
   comparing the reported content bottom: unchanged means it was real truncation and is now
   fixed; still ≈ the new canvas height means it is the `vh` loop. Do not keep doubling H —
   an operator who sees the same warning at 3000 and at 40000 learns to ignore it, and a
   gate trained into noise no longer catches the real truncation it exists for.

   Also test the narrow-screen layout with real device emulation and measure overflow.
   Device emulation is not optional phrasing: headless Chrome clamps `--window-size` to a
   ~500 CSS px minimum width (measured 2026-09-17: asking 390 yields `innerWidth=500`;
   `--force-device-scale-factor` does not shrink the CSS viewport either). For 390-class
   phone widths use Playwright/CDP `Emulation.setDeviceMetricsOverride` (or Ego) — never
   report a `--window-size=390` run as a phone-width test.

   Measuring painted bar spans for the proportion gate: anchor on the *container* (find the
   track box first, then measure dark pixels inside it), never cluster content pixels
   globally — edge antialiasing creates phantom clusters and a long bar hides its own track
   row (two real failures from 2026-09-17).
7. **Exercise the journey.** In a real browser, follow the reader's route—not merely
   a click list. Test understanding order, the obvious next action, keyboard access,
   modal focus, deep links, filters, and error/empty states. Use
   `frontend-visual-qa` for micro, macro, and intent review. Every shelf component you
   embedded gets its primary interaction clicked here, and you write down what you
   observed — "the drawer opened and highlighted clause 7" is evidence; "the component
   is present" is not.
8. **Reconcile and verify.**

   - For a rewrite or merge, run:

     ```bash
     uv run --python 3.12 python <skill-dir>/scripts/reconcile_content_diff.py old.html new.html
     ```

     It opens both pages in Chrome and compares their initial, computed reader-visible
     text. This does not traverse tabs/accordions or other interaction-created states;
     cover those states in the Journey/browser harness.
   - For generated long-lived pages, run the page generator and then its `--check`
     mode. Missing/duplicate anchors or stale output are failures.
   - Search for stale facts, shorthand, unsupported claims, broken file paths, and
     duplicated version/status values.
9. **Independent reader review — and leave a file saying it happened.** The reviewer
   must start with no inherited conversation or author reasoning: in Codex use
   `fork_turns: "none"`; in Claude Code start a separate non-fork `general-purpose`
   agent and put all required reader context in its prompt. Give that reviewer the HTML plus its
   rendered screenshots — and nothing else (the table below says "the page and nothing else";
   screenshots are the page, a text-only reviewer answers the visual questions by reading
   source, which is indistinguishable in the write-up from having looked), using
   `references/independent-review-prompt.md` verbatim. Reader comprehension failures
   are defects — with one exception, `读者已知清单` below, that a page not declaring a
   narrow audience never gets to claim. Treat proposed implementation changes as
   hypotheses and reproduce them before changing the artifact.

   Confirm the reviewer can actually open a browser before you send it the page — several
   of the review questions are about focus, Escape and keyboard order, and a text-only
   reviewer will answer them by reading the source. You cannot introspect a subagent's
   capabilities before spawning it, so make it the reviewer's own first action: tell it to
   attempt the browser step and **report "browser unavailable — items 7 and 8 answered from source"
   in its output** if it cannot. An unmarked source-read answer is the failure; a marked one
   is a known gap you can cover another way. That answer is indistinguishable in
   the write-up from one produced by clicking, and it lands in exactly the blind spot this
   skill warns about: every static check passes while the feature does nothing.

   Write the outcome to a file next to the page (or in your review archive): **how the
   reviewer was spawned (agent type, and that it was not a fork)**, the prompt you gave,
   each finding with its disposition and reason, and what could not be checked. Record the
   spawn details because a fork's write-up reads identically to an independent one — the
   only thing that distinguishes them is a fact about how it was launched, and if that is
   never written down, the independence requirement above is unverifiable by anyone
   including you. The file itself is the point: a review that leaves nothing behind is
   indistinguishable from a review you meant to run and didn't, and that is the failure
   mode this step actually has. It is not that authors disagree with the step; it is
   that under delivery pressure the step is the cheapest thing to silently drop.

   **Triage every "I don't understand this" finding against `读者已知清单` before it counts —
   provisionally; step 10 independently re-derives it, this isn't a self-check.** The
   reviewer's zero-context persona is deliberate and does not change — but a term that is on
   the list committed in step 1 is a **phantom problem** (Sauro, MeasuringU): the reviewer
   correctly has no way to know it, and the declared audience isn't actually confused by it.
   Quote the reviewer's finding **verbatim** next to the list entry it's disposed against —
   "reduces to a known term" is an interpretive claim, not a file-exists check, and the quote
   is what lets someone other than you judge whether the reduction was honest. Log the
   disposition as `audience-declared-known` with that quote and reason; it does not count
   toward the same-axis-recurrence test below. A flagged term that is *not* on the list either
   stands as a real finding, unchanged from today, or gets added now — in which case say so
   directly in the gate file next to the entry (`补记于 cycle N 审阅之后`) rather than blending
   it into the original list silently. Do not backdate it: `init --force`'s preserved
   "上一轮的答案" appendix already carries the list as it stood before this cycle, so a
   silently-blended addition is trivially caught by diffing the current list against that
   appendix — say it plainly instead of relying on someone doing that diff. Full mechanism and
   the grounding for why this pass is provisional rather than final are in
   `references/audience-triage.md`.

   **Deciding whether to run it again is an observation, not a self-assessment.** Ask:
   since the last recorded review, did the page's skeleton, components, decision-card
   content, any number, or **any term or label the reviewer had to interpret** change?
   Any yes → new reviewer, because the previous one read a different page. Renaming terms
   deserves its own mention: it is the standard fix for the reviewer's "words I could not
   understand" finding, and it is easy to file under wording — but the new words have
   never been read by anyone but you, which is the exact condition the review exists to
   remove. Typo and punctuation fixes → no rerun; say so in the closeout instead. Do not
   decide by asking yourself whether the change "felt structural." The
   documented failure is a page reviewed as prose and then rebuilt as graphics: each
   rebuild feels like polishing an already-reviewed page, and three consecutive versions
   shipped having been read by no one.

   **That trigger has no ceiling of its own — pair it with a budget, or "any substantive
   edit needs review" mints an unbounded stream of fresh rounds.** Every genuine fix is,
   by definition, exactly the kind of change the trigger above requires a new reviewer
   for, so a converging review and a runaway one are indistinguishable from inside a
   single round — the failure has been observed at both small scale (three full rounds to
   close one low-stakes correction) and large (21 rounds on a real decision document,
   stopped only because a human asked why). This is the Loop Contract from
   `claude-code-hooks`'s SKILL.md rule 7 — "If the hook demands remediation, prove the
   loop terminates"
   (`daymade-claude-code/claude-code-hooks/SKILL.md` (daymade/claude-code-skills),
   read there for the general framework and its worked failure cases) — instantiated for
   this step instead of a hook:

   ```text
   LOOP KEY: this delivery's lineage (the HTML frozen at round 1 plus every descendant
             edit) + one failure axis: can a fresh, uninformed reader use this page?
   FIRE T:   after audience triage (above), a review still answers review-prompt item 9
             "no" — or surfaces any finding that amounts to the same thing (the reader
             could not actually make the decision this page exists to produce) — on that
             same axis, using only findings that survived triage
   REMEDIATION R: reproduce the finding, apply one bounded fix, re-run the review once
   VARIANT V: 2 - completed review cycles for this lineage
   BUDGET:   2 cycles total — the initial review plus one narrowly scoped re-review.
             A third reviewer on this lineage is never automatic.
   SUCCESS EXIT: the re-review answers item 9 "yes" on that same axis, with nothing else
             reopening it
   AUDIENCE-MISMATCH EXIT: EVERY SINGLE post-triage reason behind a cycle's "no" disposes as
             audience-declared-known — ship, log the disposition table, do not report this
             to the user as blocked. "Every" means every: a "no" with two reasons, one
             audience-related and one a genuine unrelated defect (a chart missing a unit, a
             broken cross-reference), is not this exit — the unrelated reason alone routes
             through ordinary REMEDIATION/CAPPED EXIT, same as if it had appeared by itself.
             This can fire after cycle 1 alone: if nothing survived triage, there is no
             finding for REMEDIATION to reproduce and fix, so a mandatory cycle 2 would just
             re-review an unchanged page for a second phantom verdict.
             (see `references/audience-triage.md`)
   CAPPED EXIT: at least one post-triage finding is real and recurring across two cycles —
             stop, report the remaining findings as a backlog, do not ship silently, and do
             not dispatch a third reviewer on your own authority
   ```

   This skill's own reviewer output has no severity vocabulary to key off — the review
   prompt (`references/independent-review-prompt.md`) returns nine answered questions, not
   BLOCKER/MAJOR-rated findings, and step 10's acceptance vocabulary is PASS / FAIL /
   CANNOT-CHECK — so FIRE T and SUCCESS EXIT above are keyed to review-prompt item 9's own
   "最后一问" answer (can the reader act on this page with no other explanation?) rather
   than to rule 7's example severity labels, which describe a different kind of review and
   don't otherwise appear anywhere in this skill.

   **A same-axis recurrence and a new, unrelated finding get different treatment on
   cycle 2** — conflating them is what turns a bounded loop into an expanding one. Apply
   the audience triage above to each cycle's findings first; everything below is about
   what survives it. If cycle 1's findings dispose entirely as audience-declared-known,
   take the AUDIENCE-MISMATCH EXIT right there — there is nothing left for cycle 2 to
   re-review.
   - Cycle 2 reproduces a comprehension failure **on the same axis** cycle 1 already
     named (the reader still can't use the page, even if the specific wording changed) →
     that is the CAPPED EXIT above **only if the finding survived triage**. If both
     cycles' reasons dispose entirely as audience-declared-known, that is the
     AUDIENCE-MISMATCH EXIT instead — ship, don't report blocked. When a real,
     post-triage finding does recur: stop. Report `blocked`. Do not reason "but this
     finding is real" into a third dispatch — realness was never the missing check; a new
     user-authorized task with its own predeclared budget is what's missing, and only the
     user can open one.
   - Cycle 2 surfaces something **genuinely new and unrelated** (cycle 1 was about a
     decision card's clarity; cycle 2 incidentally flags an unrelated color problem) →
     record it as a separate backlog item for a separate task. It does not consume this
     lineage's budget and, by itself, is not grounds for a cycle 3 on this lineage — ship
     what converged, and open the new item as its own review with its own budget if the
     user wants it pursued now.

   **The same crossing applies once this lineage has already passed step 10 once.** A
   formal acceptance is not immune to reopening, and that is a distinct failure from the
   one above — it recurs even when every individual finding along the way was real and on
   a fresh axis (three separate passing acceptances on one lineage, each individually
   genuine, is the documented worst case). If step 10 has already returned a clean verdict
   for this lineage and something is about to dispatch another step 9/10 round anyway,
   that crossing — by itself, before judging whether the new finding is real — is the
   signal to stop and ask the user, not to silently reopen.
10. **Independent acceptance.** Hand the acceptance checklist below, plus the page and its
   sources, to a *second* fresh-context agent — separate from the reader in step 9,
   because they answer different questions (see the table under that list). It returns a
   verdict and evidence per item. Its FAILs are findings you reproduce and fix, exactly
   like step 9's; its PASSes are the only thing that closes an item.
11. **Finalize after review.** Apply accepted fixes, rerender, repeat the browser journey,
   and **re-run the delivery gate** — editing the page after filling the gate file
   deliberately invalidates it, so `check` will be red here and that is the design, not a
   malfunction. Re-run `init --force` (it carries the previous answers into an appendix so
   you review-and-move rather than retype), re-read the *new* masked render, move each answer
   up only after confirming it still holds, then `check` again. Only then open the final HTML
   for the user. Do not open a pre-review draft as the delivered artifact.

**Where a new lesson goes — two questions, in this order, before writing one into this skill.**

**First: was the failure *"I forgot to do it"* or *"I did it and could not see it was
wrong"*?** The first belongs in the workflow above; a reminder solves it. The second has to
become a question somebody **else** asks, because the author did not skip it — they looked
straight at it and judged it fine. Colour, terminology, whether a chart supports its own
caption, whether a decision card is missing an option: all of the second kind. Putting
those on a list the author answers is exactly how a rule ends up written down *and still
violated* — which is what happened to every rule this skill had to relearn the hard way.

**Then, if it is somebody else's question: can it be answered from the page alone?**
Yes → the reader's prompt (`references/independent-review-prompt.md`). No → the acceptance
list below. That second question is what keeps the two lists from growing copies of each
other; the table below states the same boundary from the other side.

## Delivery acceptance — an independent agent runs this list, not you

Two independent passes close a delivery, and **they do not overlap**: every check lives in
exactly one of them, so there is nothing for them to drift apart on.

| | step 9 · reader review | step 10 · acceptance |
|---|---|---|
| gets | **the page and nothing else** (screenshots count as the page) | the page **plus** your sources, your commands, your review file, **and the gate artifacts** |
| asks | can you read it? can you decide from it? | does what is off the page agree with what is on it? |
| its questions live in | `references/independent-review-prompt.md` — all of them, used verbatim | the five items below |
| authority | everything visible on the page | provenance and process |

**The split rule, so a future addition lands in one place instead of both:** does answering
it require something *outside* the page? **No → it is a reader question**; add it to the
review prompt. **Yes → it belongs here.** Colour, wording, whether a chart supports its own
caption, whether a decision card is missing an option, whether the headings form an
argument — all visible on the page, all the reader's. Only the five below need what the
reader does not have.

Hand this list, the page **and its gate artifacts** (`page.html.gate.md`, `page--masked.png`),
the sources behind its load-bearing facts, the commands you ran, and the step 9 review file to a
fresh-context agent (non-fork). You may walk it yourself first — it catches the
obvious misses cheaply — but *you do not get to declare the items passed.*

Why it cannot be a self-check, stated plainly because the urge to skip it peaks exactly
when delivery is close: an earlier version of this list asked the author to "be able to
point to" each item, which they could always sincerely claim. Rewriting it to demand pasted
evidence fixed half the problem — the evidence now exists — and left the other half, because
the author still ruled on whether their own evidence sufficed. The failures behind these
items were all that shape: a chart its author found perfectly clear, a colour scheme they
had considered and approved, a recommendation whose missing downside they never noticed.
None was a forgotten step. Reminders do not reach errors like these; a second pair of eyes
does.

Ask for: item number, PASS / FAIL / CANNOT-CHECK, and the specific evidence — a quoted
line, a count, a command's output. An item that cannot be checked is reported as such,
never as a pass.

1. **Provenance** — every load-bearing fact traces to a source *outside* the page, with an
   as-of date: not only numbers, but quoted clauses, claims about what someone agreed to,
   statements about a dependency's status. The reader can check a page against itself;
   only this pass can check it against the world. Anything untraceable is removed from the
   page or visibly marked unknown.
2. **Fresh render** — the rendered PNG is newer than the page's last edit. Substitute the
   actual filenames:

   ```bash
   [ page.png -nt page.html ] && echo FRESH || echo STALE
   ```

   Use this shape rather than `find page.png -newer page.html`: when the PNG is missing or
   the name is misspelled, `find` prints an error to stderr, and "there was output" then
   reads as a pass. `-nt` collapses stale, missing and misnamed into one STALE.
3. **Content integrity** — if the page was rewritten or merged, the
   `reconcile_content_diff.py` output must be supplied; if it is generated, the generator's
   `--check` output. Both answer a question no amount of looking at the page can: whether
   it still says what its sources say. If the author states neither applies (hand-authored,
   first version), record that answer as given — an explicit skip is auditable, an assumed
   one is not.

   Two outputs to read correctly rather than wave through. The reconciler prints **how many
   fragments it actually compared**; a near-zero count means "nothing was comparable", not
   "nothing was lost" — its extractor samples CJK-initial runs, so a non-Chinese page yields
   almost none. And if it times out — Chrome produced no complete DOM within its limit —
   record the item as **not reconciled**, never as passed. The generator's `--check` has its own blind spot it now guards against —
   it is a self-consistency comparison, so zero clause anchors would appear identically on
   both sides; it therefore asserts the anchor count separately and exits non-zero at zero.
4. **Review completion** — open the step 9 review file, quote one of the reviewer's own
   findings verbatim, and record how that reviewer was spawned. A path only proves a file
   exists and the author writes that file; the reviewer's own words and the spawn details
   are what cannot be produced without a review having run. Then check each finding has a
   disposition, and ask for every change made afterwards: if that list holds anything
   beyond wording — skeleton, components, decision-card content, any number, or any term
   the reviewer had to interpret — step 9 required a fresh reviewer, so establish whether
   one ran. If the page declares `读者已知清单` (step 1), the author's disposition of each
   `audience-declared-known` finding is a provisional first pass, not the answer — **this is
   the independent re-derivation that makes it real, not a second look at the author's own
   conclusion**: read the reviewer's quoted finding and the list entry it was disposed
   against, and independently judge — without reading the author's stated reason first —
   whether you would classify it the same way. A finding that only *mentions* a listed term
   in passing, while its actual complaint is something else (a chart's claim, a broken
   cross-reference, a color collision), does not dispose just because the term is on the
   list — check what the reviewer's sentence is actually complaining about, not which words
   appear in it. Disagree with the author's classification → the item is undisposed, not
   passed, regardless of what the author wrote. Also confirm the declared term is something
   the page's *reader* would actually encounter — a term stuffed into a comment, `alt` text,
   `aria-hidden` content, or `display:none` markup satisfies "appears on the page" mechanically
   but was never something a reader could have already known *from reading this page*, and
   disposing a finding against it is exactly the gaming path `references/audience-triage.md`
   names. Finally, check the list's own history: if any disposed term is absent from the
   version of `读者已知清单` preserved in the gate file's "上一轮的答案" appendix from before
   this review cycle, and the gate file doesn't say so plainly next to that entry (`补记于
   cycle N 审阅之后` or equivalent), that is an unlabeled retrofit — treat it as undisposed,
   not as passed. A labeled late addition is not automatically disqualified; judge whether the
   audience really would already know it, same as any other entry.

5. **Delivery gate ran, and its answers describe this page** — ask for three things, because
   the first two are cheap to fake and the third is what makes them mean something:
   (a) `page.html.gate.md` and `page--masked.png` **exist**, and `check` exits 0 right now
   (paste the output). A nonzero exit is a **FAIL of this item**, not an invitation to let the
   author re-run `init --force` and try again while you wait — the gate is supposed to be green
   before the page reaches you; (b) **count the distinct geometries visible in the masked PNG FIRST, write that
   number down, and only then open the gate table** — reading the table first makes you go
   looking for the shapes it lists, which is confirmation bias with a known direction. Then
   compare the two counts — the masked render is the ground truth here. **Two things before you call a mismatch:** a
   long page needs `crop_segments.py` first (a 19000px PNG is unreadable in one Read), and a
   *composite* geometry legitimately shows as several shapes — a timeline with a main axis and
   an inset, a paired before/after bar — so read the gate row's own `data-derived-from` before
   counting it twice. A real mismatch means either a visual escaped the scanner (it only reads static markup: inline percentage styles on a
   short property list, plus `<svg>`/`<canvas>` **elements** — a width set from a CSS class, a
   gradient stop, a `transform` percentage, or a chart a JS library injects at runtime are all
   invisible to it; note `<canvas>` the *element* is caught, what it *draws* is not) or a wrapper is claiming several as one; (c) pick **two** filled rows at random and check each one's "遮字后读出的关系" against the
   masked PNG yourself. One row is too thin — faking a single row survives a 1-in-N draw. And
   judge the right thing: the question is not "is this sentence true" but **"could it have been
   written from the source without opening that image?"** A claim that merely restates what the
   markup says ("six bars rising left to right") passes the first test and fails the second;
   say so when that is all you got. Where the masked PNG came from matters too — it is produced
   by the author's own run, so if anything about it looks off, re-render it yourself with
   `delivery_gate.py init --force` on a copy and compare.

   Why this item exists, stated plainly because it is the one the author has the strongest
   reason to omit: without it, steps 3 and 5 are **opt-in**. An independent review of the 2026-08
   version found the whole gate skippable at zero cost — no downstream role asked for its
   artifacts, so an author could skip 3 and 5, run 6 through 11 in full, and nothing would notice. A gate nobody is assigned to
   check is a gate that exists only for people who were going to do the work anyway.

If an item cannot be answered, the gap is written down plainly rather than the page being
declared complete. An honest gap is something the reader can act on; a green checklist
covering a check that never ran is not.

## Dependencies

- `content-writing-discipline` for the user's writing/register rules when available;
- `frontend-visual-qa` for browser and visual inspection — it ships in the sibling
  `claude-code-skills` suite, not this one, so it may not be loadable in a given session.
  If it is not available, do the inspection directly instead of skipping it: read the
  rendered PNG segment by segment for micro (typography, alignment, contrast), macro
  (page rhythm, section balance), and intent (does each view answer its sub-question);
- Google Chrome or Chromium for rendering — **step 5's gate needs it too**, plus `uv`
  (it installs `delivery_gate.py`'s `pillow` from the PEP 723 header). The old workflow could
  run start-to-finish on stdlib alone; this one cannot, because the gate's whole point is
  producing artifacts. Without them, say so in acceptance item 5 as a CANNOT-CHECK with the
  reason — do not report the item as passed, and do not silently skip steps 3 and 5;
- Python 3.10+ for PNG validation and content reconciliation — `reconcile_content_diff.py`
  is standard-library only; `delivery_gate.py` declares `pillow` via PEP 723 and `uv run`
  installs it automatically —
  `reconcile_content_diff.py` uses `X | None` annotations that raise on 3.9;
- optional `d2` for auto-layout diagrams;
- `deck-creator` (Route C) only after the HTML design is accepted and editable PPTX is required.
