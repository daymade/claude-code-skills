# Data-Viz Tier & Design-System Token Audit

Extends the main visual-QA workflow with checks that recur whenever the artifact
is a **reporting-grade data page** (dashboard, KPI board, monitoring console,
analytical report) rather than a CRUD form: whether it hits the visual **tier**
the user expects, whether its chart colors obey the **design system's token
contract**, and whether a **categorical palette** is actually colorblind-safe.

Load this when the user says a data page is "not the same level / tier" as a
reference they made before, when you see hardcoded chart hex, or when you are
adding series / identity colors to a design system.

## Contents

- Success Is The Actor's Job
- Verify Data Context And Non-Happy States
- Benchmark Visual Tier Against The Reference
- Audit Design-System Color Tokens
- Validate Categorical Palettes

## 1. Success = the actor's job, not "it rendered / tests are green"

The cheapest wrong standard is "the page opens, the sections are all present,
the e2e suite is green." A test that asserts *presence* ("the chart is on the
page", "the tabs switch", "the nine zones exist") stays green while the artifact
still fails the actual job — because the test verifies **structure**, not
whether the view answers the question the user arrived with. Green tests over the
wrong target are a *false pass* that hides a product gap.

Before judging pixels, write the actor's job as a question per state, then check
the view answers *that*:

- triage / overview state → "is this bad, do I need to act?"
- tracking state → "is it getting better, what changed?"
- closeout / summary state → "is it done, can I sign off?"

Assert on the **content that answers the question** (does the triage view
actually carry a severity verdict and a magnitude?), not on the DOM node's
existence. A rendered page plus green tests is the floor, never the finish line —
the finish line is a real user completing their job at each stage.

## 2. Verify data context and non-happy states

A chart that renders cleanly can still make the wrong claim. Verify:

- units on KPIs, axes, tooltips, and derived values;
- data source or provenance, selected time range, and freshness/timezone when
  they materially change interpretation;
- distinct loading, genuinely empty, filtered-no-match, permission-denied, and
  error states;
- unknown or failed data is never rendered as zero, success, or a completed
  trend;
- error and stale-data states explain the next safe action.

A happy-state screenshot cannot verify these branches. Exercise them through
the project's representative fixture/state controls, or list them as
unverified rather than granting a full data-page pass.

## 3. Visual tier: benchmark against the reference, quantify the gap

When the user says a data page is "not the same level / tier" as something they
made before, do not argue from taste. **Open the reference artifact in the
browser, screenshot it, read its CSS / computed values, and diff quantifiable
visual parameters side by side.** The table below is an illustrative pattern,
not a universal scale:

| Param | generic-admin tier (low) | reporting-grade tier (high) |
|---|---|---|
| Headline numbers | smaller, single ink color | larger display step, deliberate semantic emphasis where appropriate |
| Verdict / summary | plain text block | key phrases color-coded (red = failure / loss, green = alive / gain, amber = watch) |
| KPI layout | separate rounded cards | one divided strip of big numbers, each with a 2-line explaining note |
| Status badge | small bordered chip | solid-fill, large letter-spacing, confident |
| Note under a number | one dry label | a second line that actually explains the number |

The tier gap is **measurable** (font px, color count, notes-per-KPI), not vibes.
Read the reference's own values to get the target numbers, then report the gap as
a `Taste` / `Intent` finding with the concrete param:

```
Taste tier-drift: KPI numbers render 22px single-color vs reference 30px with
semantic color + 2-line note — reads as generic admin, not reporting-grade.
```

A pretty page in the wrong tier still fails a user who has a higher-tier
reference in mind. Do not copy the example numbers above. Measure the named
reference and the target in the same viewport and state. One token system may
support both tiers when it already provides the needed display step and density
range. Check that contract before adding a one-off size or forking the system.

## 4. Design-system color-token audit (charts especially)

When the project design system says chart colors come from tokens, audit chart
code as a likely drift point: one-off artifacts are often copied with their
palette literals intact.

- **Search for hardcoded color literals** in chart/component code, including
  `#[0-9a-fA-F]{6}`. Classify each hit against the project's token contract;
  report unexplained business, semantic, or series colors rather than assuming
  every literal—or every black/white primitive—is automatically right or wrong.
- **Prove token resolution at runtime** — don't trust the source. In DevTools,
  read the computed color and confirm it resolved from the token, not a stale
  hex left behind after an edit:

```js
() => [...document.querySelectorAll('.series-dot')]
  .map(el => getComputedStyle(el).backgroundColor)
// expect the token's rgb(), NOT the old hardcoded value
```

- **One token set, two densities.** A reporting board and a CRUD console can
  share the same tokens; the board just uses the display type-scale step (e.g. a
  `--t-display` for KPI numbers) and denser composition. You rarely need a
  second design system.

## 5. Categorical palette must be colorblind-validated

A design system's **semantic** colors (red = alert, green = success, amber =
watch, blue = neutral — each bound to one meaning) cannot double as
**categorical** identity colors for N parallel series (multiple videos,
accounts, platforms, cohorts). If series-3 is "red", it collides with
"red = alert". Most systems are *missing* a categorical palette, so people
hardcode one — usually badly (too gray, or colorblind-ambiguous).

Use standards and an explicit project policy:

- WCAG 2.2 Use of Color:
  https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html
  Do not encode a series, state, or decision with hue alone. Add direct labels,
  symbols, patterns, line styles, or an equivalent table where needed.
- WCAG 2.2 Non-text Contrast:
  https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
  Graphical objects required for understanding should reach 3:1 against
  adjacent colors unless an equivalent presentation makes that object
  nonessential.
- ColorBrewer:
  https://colorbrewer2.org/
  Prefer an established colorblind-safe qualitative palette when it fits the
  series count and brand context.

Then validate the rendered chart:

1. Separate semantic status tokens from categorical identity tokens. A series
   should not accidentally read as success, warning, or failure.
2. Simulate protan, deutan, and tritan color-vision deficiencies with an
   established tool or model.
3. Measure perceptual distance in one declared color space and record the
   minimum pairwise result. Use the project's documented threshold when one
   exists; do not invent a universal ΔE cutoff.
4. Test series that touch, cross, overlap, or appear adjacent in the actual
   chart. Palette array order alone is not the visual adjacency.
5. Check lightness/chroma balance so one identity does not dominate or disappear.
6. Check default, hover, selected, disabled, and muted states against the real
   surface.
7. Confirm direct labels, legend mapping, focus/hover feedback, and an equivalent
   data view preserve meaning when colors become difficult to distinguish.

Treat simulation and numeric distance as evidence, not a complete accessibility
verdict. Fix ambiguous pairs, add redundant encodings, or reduce simultaneous
series before shipping.
