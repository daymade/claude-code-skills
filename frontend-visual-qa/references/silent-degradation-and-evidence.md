# Silent degradation, and the evidence a visual finding must carry

Two things this file covers, both learned from audits where the product looked
cheap while every automated gate stayed green:

1. **Silent degradation** — defect classes where nothing errors. The source is
   correct, the build passes, the assertions pass, and the pixels are still
   wrong. Static analysis is structurally unable to see these.
2. **Evidence discipline** — what a visual finding must carry to be actionable.
   A reader who cannot see the defect cannot decide anything about it.

## Part 1 — Why static checks miss a whole category

A lint rule reads what the author wrote. A geometry assertion reads a box. The
defects below live in between: in the cascade's verdict, in a library's DOM, in
whether a declared asset was ever shipped. In every one of them **the failing
artifact is syntactically valid and produces no diagnostic** — a CSS rule that
matches no element is not an error in CSS; it simply does nothing.

The practical consequence: *the only detector is rendered output*. Not the
source, not the type system, not the build log.

### 1a. Cascade override — the component's own styles lose

A global reset can outrank a component's styles and strip them, while every
component call site remains correct.

Real instance: `.app-surface button:not([class*="ant-"])` has specificity
`0-2-1`; the button primitive's `.btn--primary.btn--info` has `0-2-0`. The
`:not()` contributes its argument's weight, and the extra element selector
(`button`) decides it. The reset won on every hand-authored button in the
workspace: background and border removed, leaving primary buttons as bare text
with a 2px `::after` underline. Users reported "the clickable things don't look
clickable"; the source review found nothing, because nothing was wrong there.

**Detect:** screenshot the surface, then read `getComputedStyle` on a control
that should have an affordance. `backgroundColor: rgba(0,0,0,0)` plus
`borderStyle: none` on something that is semantically a button is the signature.

**Do not** fix by adding `!important` at the call site — that inverts the
cascade for everyone downstream. Narrow the reset (`button:not([class])`) or
raise the primitive's specificity within its own layer.

### 1b. Library rename — a whole rule group stops matching

Component libraries rename internal DOM classes across major versions. Every
stylesheet rule targeting the old names quietly matches nothing, and the
components revert to the library's stock appearance — which is precisely the
"looks like an unstyled framework app" complaint.

Real instance: antd 5 → 6 moved the Select frame from an inner
`.ant-select-selector` to the outer `.ant-select` (v6 renders
`.ant-select > .ant-select-content + .ant-select-suffix`), renamed the Modal
body container `-content` → `-container`, the Drawer panel `-content` →
`-section`, and Popconfirm's `-message-title` → `-title`. Nine rules across the
bridge stylesheet were dead. The design system's tone vocabulary — the colored
rail that marks a control's semantic state — had not rendered for an unknown
number of releases.

**Detect:** enumerate every library-internal class the stylesheet references
and count each one in the *installed* library's compiled CSS.
`scripts/silent_degradation_probe.mjs class` does this:

    node <skill-root>/scripts/silent_degradation_probe.mjs class \
      --css path/to/library-bridge.css \
      --library-css node_modules/<library>/dist/<library>.css \
      --prefix ant

Two refinements that prevent false alarms and false clears:

- A dead name inside a **selector group** whose sibling branch still matches
  costs nothing (`.ant-input:focus, .ant-input-focused` — the first still
  works). Confirm the group before editing.
- A rename can also change **which element** carries the class. Drawer's
  `-section` sits on the same element as the caller's own className, so
  `.my-drawer .ant-drawer-section` still matches nothing — the rule must target
  `.my-drawer` itself. Check the level, not just the name.

### 1c. Declared font that was never shipped

The most invisible of the three, because the two obvious checks both return
success:

| Check | Reports | Truth |
|---|---|---|
| `getComputedStyle(el).fontFamily` | the declared stack | says nothing about availability |
| `document.fonts.check('16px "X"')` | `true` | returns true when **no** `@font-face` exists at all |
| **width vs. a nonexistent family** | differs / identical | **the only reliable signal** |

Real instance: `--font-sans` listed a brand family first; the app shipped zero
`@font-face` rules and zero font files. Every glyph in the product rendered in a
system fallback. Neither the author's machine nor the reviewer's could see it,
because the fallback is what both had always seen — there was no control group.

**Detect:**

    node <skill-root>/scripts/silent_degradation_probe.mjs font \
      --url http://127.0.0.1:5173/ --family "Brand Sans" --family "Brand Mono"

**The probe string must contain Latin characters.** CJK glyphs are full-width in
essentially every font, so an all-CJK probe measures the same width whatever
font actually renders, and reports a false pass. This exact mistake produced a
false "font not working" reading on an app where it *was* working.

Also check the whole stack, not just the first family: a `--font-mono` whose
first entry is a platform-only face (`DIN Alternate` on macOS) renders one way
for the team and another for everyone else.

### 1d. Geometry values that live in theme config

Design-token discipline is usually enforced by scanning source for raw values.
Values written into a component library's theme provider are invisible to that
scan: the page's own source contains no spacing value at all, so the scan is
clean while the rendered rhythm comes from, e.g., `itemMarginBottom: 14` — a
number on no scale.

**Detect:** read the theme configuration as part of the audit surface, and
check its geometry values against the token scale. A clean source scan on a page
that visibly has off-scale rhythm is the tell.

### 1e. Per-element compliance, aggregate incoherence

Every element can satisfy every rule while the composition still reads as
"no design system," because the rules constrain each element in isolation and
say nothing about **how many different ways the same concept is expressed**.

Real instance, one toolbar, one row: a native `<input type=date>`, a library
Select, a tinted info pill, two plain-text buttons, and one plain-text button
with an underline — five clickable/input syntaxes side by side. Elsewhere: the
same decorative rail implemented seven times at different sizes and colors; a
count rendered in four different size/family pairings.

**Detect:** it is a counting task, not a per-element check. For each recurring
semantic object (clickable, count, status marker, filter control), enumerate the
distinct implementations across the app. More than one is the finding; the
target is one primitive per concept.

## Part 2 — Evidence a visual finding must carry

A finding the reader cannot see is a finding they cannot act on. The rule:
**a claim about appearance ships with the pixels that show it.**

- **Crop to the defect, keep enough context to locate it.** A full-page
  screenshot proves nothing about a 14px misalignment. `shot` mode crops one
  element plus padding.
- **Comparisons must be scale-matched.** Two 1200px-wide toolbars placed
  side by side in a report shrink to ~460px each and the difference under
  discussion — a 3px colored rail, an arrow shape — disappears. Crop both to the
  *same component* at the *same width* instead. (A report making this mistake
  committed the very sin it was reporting.)
- **Report CSS px, never device px.** A DPR-2 capture has twice the pixel
  count; quoting that as page height once produced a false "the page is 20
  screens long" finding when it was 10. State the viewport and DPR alongside.
- **Date the capture against the code.** A screenshot from before a fix is
  still valid evidence *of the old state* — label which commit it shows, and say
  so, rather than quietly presenting it as current.
- **Separate "photographed" from "counted."** Findings resting on a code count
  (seven rails, four count styles) are weaker than photographed ones until they
  too are captured. Mark which is which rather than letting the reader assume
  the whole list is equally evidenced.

## Part 3 — Assertions have blind spots too; state what yours cannot see

A geometry assertion measures a chosen box, and the choice is a hypothesis.

Real instance: a suite asserted the form label's left edge aligns with the
input's. It measured the **label element box** — but a decorative `::before`
inside that box pushed the *text* 14px right. The visible misalignment was
exactly what the assertion existed to catch, and it passed. Measuring the first
text node (`Range.getBoundingClientRect()`) sees what the eye sees.

When adding an assertion, write down what it would *not* catch. That sentence is
usually where the next defect lives.

## Fast triage

When a page "looks cheap" but every gate is green, check in this order — cheapest
and highest-yield first:

1. **Fonts** — `probe font`. Wrong typeface degrades every screen at once.
2. **Library class names** — `probe class`. One rename can kill a whole
   component family's styling.
3. **Affordance** — do controls that should be clickable have background or
   border? Cascade override is the usual cause.
4. **Syntax count** — how many ways is the same concept expressed on one screen?
5. **Theme config geometry** — off-scale values invisible to source scans.
