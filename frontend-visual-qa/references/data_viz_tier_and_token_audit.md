# Data-Viz Tier & Design-System Token Audit

Extends the main visual-QA workflow with checks that recur whenever the artifact
is a **reporting-grade data page** (dashboard, KPI board, monitoring console,
analytical report) rather than a CRUD form: whether it hits the visual **tier**
the user expects, whether its chart colors obey the **design system's token
contract**, and whether a **categorical palette** is actually colorblind-safe.

Load this when the user says a data page is "not the same level / tier" as a
reference they made before, when you see hardcoded chart hex, or when you are
adding series / identity colors to a design system.

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

## 2. Visual tier: benchmark against the reference, quantify the gap

When the user says a data page is "not the same level / tier" as something they
made before, do not argue from taste. **Open the reference artifact in the
browser, screenshot it, read its CSS / computed values, and diff quantifiable
visual parameters side by side.** The recurring gap between a *generic-admin
tier* and a *reporting-grade tier*:

| Param | generic-admin tier (low) | reporting-grade tier (high) |
|---|---|---|
| Headline numbers | small, single ink color, ~20-22px | large 30-32px, semantic color (good / warn) |
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
reference in mind. Note also: the same token set usually supports both tiers —
the board just uses the *display* type-scale step and denser composition. A
hardcoded 29px is usually a missing token reference, not a reason to fork the
design system.

## 3. Design-system color-token audit (charts especially)

Design systems almost always say "chart colors come from tokens, never inline
hex" — and chart code is where that rule breaks most, because someone ports a
one-off HTML chart's hardcoded palette straight in.

- **Grep for hardcoded hex** in chart / component code: `#[0-9a-fA-F]{6}`
  outside the token file. White / black are usually fine; **business / series
  colors are not**. Each such hex is a finding.
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

## 4. Categorical palette must be colorblind-validated

A design system's **semantic** colors (red = alert, green = success, amber =
watch, blue = neutral — each bound to one meaning) cannot double as
**categorical** identity colors for N parallel series (multiple videos,
accounts, platforms, cohorts). If series-3 is "red", it collides with
"red = alert". Most systems are *missing* a categorical palette, so people
hardcode one — usually badly (too gray, or colorblind-ambiguous).

When adding or auditing a categorical palette:

- **Validate it, don't eyeball it — compute the four checks numerically.** A
  categorical palette has to pass four measurable tests, so read the numbers
  rather than trusting appearance:
  - **lightness band**: keep every slot within a controlled lightness range so
    none dominates;
  - **chroma floor**: no slot so low-chroma it "reads gray" — the classic
    one-off-chart failure;
  - **CVD separation**: every adjacent pair keeps ΔE ≥ 12 after simulating
    protan / deuteran / tritan deficiency (Machado or Brettel model);
  - **contrast vs the surface**: each slot clears a WCAG contrast ratio on the
    page background.
  Approving a palette on how it looks is exactly the eyeball failure these
  numbers exist to prevent.

- **Slot ordering is the CVD mechanism, not cosmetic.** If two adjacent slots
  fail CVD separation, reorder so warm / cool alternate — on one real palette
  that pushed the worst-adjacent ΔE from 4.5 to 27.7 without changing the hues.
- **Keep categorical clear of the semantic hues.** Put the identity colors a
  chart uses most (the first few slots) on hues the semantic palette doesn't own
  — avoid alert-red and success-green, so a series line never reads as a status
  and a red failure / ✕ marker on the same chart stays distinct from every
  series line.
- A borderline contrast on one slot is acceptable only with the relief rule
  (legend / direct labels / table view present). A chroma-floor failure or a CVD
  separation failure must be fixed before the palette ships.
