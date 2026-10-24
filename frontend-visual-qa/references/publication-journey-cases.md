# Publication journey calibration cases

Use these synthetic cases when auditing a publication's composition or density,
especially after local checks passed but the user still rejects the whole path.
The executing auditor applies the existing **Information necessity before layout**
check to the declared discovery → selection → reading path. A local line-break
request alone does not authorize a whole-site redesign. Stop at that scope.

These are known-answer task packets, not screenshots or reports of a real site.
In a live audit, obtain the canonical render and perform the journey before
claiming any appearance, interaction or reading result. No script enforces the
semantic judgments below; an auditor must examine the actual task and evidence.

## Failing case: all links work, but the reading routes are interchangeable

Actor: a reader choosing a paper about how candidate changes are selected,
then finding its supporting source and a relevant follow-up.

Supplied observations:

- The home page offers a featured story, a chronological library, a topic
  section and repeated publication-introduction bands with equal visual weight.
- The topic section contains exactly the same stories, ordering and summaries
  as the chronological library. Topic names give no selection criterion.
- Every story row repeats a topic badge, a summary, an expanded-summary preview,
  source metadata and a second identical read action.
- The reader page opens with a large repeat of the cover and publication
  introduction before the argument. Follow-up links say only “Read more.”
- Links, search, source access and figure dialogs work; local overflow, line
  breaks and button states have already passed checks.

Expected audit action: do not issue an overall pass from those local checks.
Inspect the competing discovery routes, row information and article entry as
one task. Cite the duplicate topic ordering and missing selection criterion as
specific evidence of a route that adds no topic-based choice. Identify which
context can be disclosed or relocated without losing source access. Treat
equal-weight competition as a rendering hypothesis until pixels are inspected.
Do not invent a missing-handler defect or report a measured time saving.

For an authorized fix, compare the same content and viewport after changing the
structural competition; re-walk source access and continued reading. Fixing one
badge or one title wrap cannot establish closure of the declared whole-path
complaint. A diagram earns attention by explaining an actual relationship, not
by satisfying an image quota.

## Healthy control: necessary context and distinct route jobs

Same actor and content, with these supplied observations:

- The chronological library supports “what changed recently”; topic routes
  describe different questions and show matching article examples. Overlapping
  membership is explicitly explained where it affects the reader's choice.
- Each row exposes the title and the difference it explains; secondary metadata
  is available on demand. The article opens with the argument and its mechanism.
- A mechanism caption distinguishes observations from the author's explanatory
  illustration. A nearby source control leads to the original evidence.
- The follow-up states the next question, rather than repeating a generic CTA.
- An independently consumed figure repeats a necessary unit and comparison label.

Expected audit action: retain context that prevents a specific misreading,
including the figure's unit, comparison label and evidence boundary. Do not
flag overlapping topics or every repeated label as inherently redundant.
Explain how the routes support different choices; do not prescribe a palette,
grid, number of controls, or “one article per row” as the only valid design.
The packet supplies semantic controls only: actual pixels, clicks, freshness
and human aesthetic acceptance remain unverified until separately observed.

## Bounded replay and closure

Ask a fresh auditor, using the ordinary Skill entry, to handle both packets:

1. State the actor's task and what evidence the packet can establish.
2. For the failing case, name the unresolved whole-path problem despite the
   passing local checks, with a concrete observation and next discriminating probe.
3. For the healthy case, identify context whose deletion would cause a concrete
   misunderstanding; do not manufacture a blanket minimalism violation.
4. Separate the packet-based conclusion from unobserved pixels, behavior and
   real-reader acceptance. Preserve audit-only authority unless a fix is requested.

An auditor who passes the first case solely because controls work misses the
failure. An auditor who deletes every caption in the second case overgeneralizes
it. Passing both is a bounded calibration observation, not proof of future
design quality or permission to restart an accepted frontend.
