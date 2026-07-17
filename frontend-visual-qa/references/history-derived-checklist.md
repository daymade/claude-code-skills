# Core Visual And Responsive Checks

This path is retained for compatibility. It now contains only the common visual,
responsive, typography, and composition checks. Load the journey/page-contract
reference separately when the audit includes routes, overlays, browser outputs,
native shells, GIS, or review tools.

## Contents

- Standards-Backed Baseline
- Evidence Order
- Viewport And Responsive Checks
- Typography And Line Breaks
- Layout And Composition
- Images And Media
- Reference Parity And Taste
- Mechanical Finding Triage
- Invalid Fixes

## Standards-Backed Baseline

Use these standards as tests, not as decoration:

- WCAG 2.2 Reflow 1.4.10:
  https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
  Check that content intended to scroll vertically can reflow to 320 CSS pixels
  without losing information/functionality or requiring two-dimensional scroll,
  except where a two-dimensional layout is essential.
- WCAG 2.2 Text Spacing 1.4.12:
  https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html
  Check that user overrides for 1.5 line height, 2x paragraph spacing, 0.12em
  letter spacing, and 0.16em word spacing do not clip or hide content.
  These are override-survivability values, not recommended authored defaults.
- WCAG 2.2 Focus Not Obscured 2.4.11:
  https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html
  Check that sticky headers, footers, notifications, and non-modal overlays do
  not entirely hide the focused control.
- WCAG 2.2 Target Size 2.5.8:
  https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
  Check for at least 24 by 24 CSS pixels or sufficient spacing, while respecting
  the criterion's inline, equivalent-control, user-agent, and essential-layout
  exceptions.
- Chrome Device Mode limitations:
  https://developer.chrome.com/docs/devtools/device-mode#limitations
  Treat emulation as a first-order approximation. Use a real device when CPU,
  input, browser chrome, or device-specific behavior matters.
- Playwright visual comparisons:
  https://playwright.dev/docs/test-snapshots
  Keep baseline and comparison environments stable; OS, browser version, fonts,
  hardware, power state, and headless mode can change rendered pixels.

This checklist is not a WCAG conformance claim and does not replace an
established accessibility tool such as axe plus keyboard/assistive-technology
testing.

## Evidence Order

Inspect in this order:

1. Prove the exact route, conditional state, data, and viewport.
2. Open a whole-page or whole-window screenshot and judge macro composition.
3. Open local screenshots for disputed regions.
4. Use DOM geometry/computed styles to explain the visible defect.
5. Use mechanical findings as candidates and triage false positives.

Do not reverse the order by starting from selector warnings and then inventing a
visual defect to justify them.

## Viewport And Responsive Checks

Choose widths from the product contract. A useful default matrix is a common
desktop around 1440 by 900, a wide desktop only when wide composition matters,
and a phone viewport around 390 by 844. Add 320 CSS pixels when WCAG reflow is in
scope and a real target device when device behavior matters.

For a projection, demo, or HTML deck, also use the exact delivery canvas from
the contract. Do not substitute the default desktop size for a specified
projection size such as 1920 by 1080. Inspect every slide/frame at that size for
crop, overflow, readable type, and visual density; add mobile only when the deck
is also meant to be read there.

For each relevant viewport, record:

- requested viewport versus actual inner/visual viewport;
- outer window dimensions when the user sees a real browser window;
- viewport meta content and device scale factor;
- document clientWidth, scrollWidth, and horizontal overflow;
- title, H1, route, and required state markers;
- first-viewport content bounds and left/right blank space;
- computed body and key-heading family, size, weight, line height, and tracking,
  plus relevant control/text-column/rail widths and smallest important text;
- screenshot path and a short observation after opening it.

Flag:

- missing or ineffective viewport meta that leaves a nominal phone run at about
  980 CSS pixels and scales it down;
- desktop emulation inside a much wider visible window;
- stale zoom/emulation after display or scale changes;
- page-level or section-level horizontal overflow;
- a desktop table squeezed into a phone without a usable row alternative;
- hidden identity, status, decision fields, or primary actions on mobile;
- two competing scroll owners or a panel whose scroll is visually ambiguous;
- sticky/floating elements covering content or focused controls.

Zero page overflow is necessary but not sufficient. A phone table can remain
unusable while document overflow is zero.

## Typography And Line Breaks

Judge font family, size, weight, line height, tracking, text-column width, and
copy together.

When DOM/computed-style evidence exists, record the actual values for the body,
key headings, affected controls or text columns, and smallest important text.
For reference comparisons, measure both artifacts in the same state and
viewport. A static screenshot supports visual observations only; do not invent
pixel values or impose a universal minimum type size from it.

Flag:

- headings with a final line of one or two visible characters;
- high-visibility CJK copy that splits a semantic two-character phrase;
- product names, dates, labels, or domain terms broken character-by-character;
- buttons, tabs, tags, pills, or navigation labels wrapping unexpectedly;
- short table labels broken across lines;
- clipped text or hidden overflow that removes meaning;
- tiny important text used to compensate for a narrow layout;
- text-spacing overrides that cause clipping, overlap, or missing controls.

Do not mechanically eliminate every two- or three-character final line in
ordinary body copy. Prioritize headings, controls, labels, first-viewport copy,
repeated component text, and obvious semantic breaks.

Prefer:

- rewriting or shortening copy;
- widening or restructuring the semantic column;
- intentional phrase spans or balanced heading wrapping;
- stable control dimensions;
- a responsive layout change.

Do not globally shrink type or hide overflow.

## Layout And Composition

Judge the whole page before local pixel alignment.

Check:

- whether the first viewport communicates the actual actor, object, and task;
- whether visual weight is balanced rather than dumped in one corner;
- whether the shell/chrome and canvas belong to one product;
- whether the same context is repeated in title, header, sidebar, and cards;
- whether repeated modules express hierarchy or merely copy one card template;
- whether the primary work surface appears before explanation and decoration;
- whether persistent rails have a named role;
- whether same-row fields share label, control, helper/error, and action axes;
- whether repeated specimens share widths, baselines, and edge alignment;
- whether fixed heights clip content after localization or data changes;
- whether dense calendars, timelines, event blocks, labels, tags, or annotation
  lanes overlap one another, obscure adjacent targets, or become inoperable with
  representative worst-case data;
- whether whitespace is intentional and symmetric rather than a broken grid.

Measure local alignment after the screenshot shows a real mismatch. Compare
bounding boxes for sibling label top, control top/bottom, helper top, field
height, and left/right edges. Reserve helper/error slots when fields must remain
on the same visual row.

Cards are not inherently wrong. Flag card piles when they replace information
architecture, not when they represent genuine repeated items, specimens, or
modal surfaces.

## Images And Media

Verify:

- image request/load state and nonzero natural dimensions;
- displayed ratio versus natural ratio;
- intentional object-fit and focal position;
- crop severity at each relevant viewport;
- text/badge/caption collision with important image content;
- asset relevance to the product/domain;
- use of approved logo, imagery, and design-system assets.

Classify media before calling it broken:

- **not requested** — a rendered but offscreen lazy image has not entered its
  loading threshold; visit the audited row/section before judging the asset;
- **still loading** — a requested image has not completed at capture time;
  record incomplete evidence rather than inventing a network or asset cause;
- **broken** — the request completed but the image has zero natural dimensions
  or cannot decode.

Responsive implementations may keep desktop and mobile branches in the DOM at
the same time. Scope image readiness, geometry, scrolling, and interaction to
the branch that is CSS-rendered at the current viewport. Do not wait for or
scroll to images inside display:none, visibility:hidden, zero-size, or otherwise
inactive alternatives. Audit hidden alternatives separately only when they can
remain focusable or intercept input.

For a full-page media audit, scroll the relevant rendered rows or sections to
trigger lazy loading, wait for those requests to settle, then inspect completion
and natural dimensions. A blanket document.images.every(img => img.complete)
wait is invalid because offscreen lazy media may correctly remain untouched.

Flag default stretching and accidental heavy crop. Do not infer safe crop from
object-fit: cover alone; inspect the focal content.

## Reference Parity And Taste

When the user names a reference, open both artifacts in comparable states and
viewports. The specific reference outranks generic taste advice.

Compare measurable parameters:

- content bounds and visual center;
- heading/body size and weight;
- spacing rhythm and density;
- chrome/body color temperature;
- card, rule, and border treatment;
- image scale/crop;
- repeated component geometry;
- chart and status color semantics.

Preview subjective alternatives in the browser before editing shared tokens.
Compare rendered candidates on both the reported screen and a dense specimen.

Treat these as conditional taste findings, not universal errors:

- purple/blue gradients, glass, glow, or floating blobs;
- decorative left rails on cards;
- rounded-card repetition;
- a reporting layout that feels “one tier lower”;
- resemblance to another brand's signature motif.

They become defects when they conflict with the named reference, brand system,
product domain, actor's job, or established project rules.

## Mechanical Finding Triage

| Candidate | Confirm with | Typical root fix |
|---|---|---|
| orphan heading line | opened screenshot + rendered lines | copy, width, intentional wrap |
| wrapped control | screenshot + line boxes | label, control width, layout |
| clipped text | scroll/client geometry + screenshot | remove bad fixed height or provide intentional scroll |
| horizontal overflow | document and section geometry | correct min-width, grid, or responsive alternative |
| wrong scroll owner | wheel/keyboard journey | min-height contract and scoped overflow |
| same-row drift | sibling bounding boxes | shared anatomy or reserved helper slot |
| dense-item collision | opened dense-state screenshot + affected bounding boxes | collision-aware layout, reserved lanes, stacking, or a responsive alternative |
| deferred/broken image | request state + visible-branch screenshot + natural dimensions | trigger the lazy row, then repair the actual asset or loader |
| image ratio/crop | natural/display ratio + screenshot | matching aspect ratio and deliberate object-fit |
| underfilled first viewport | inner/outer widths + content bounds | reset emulation or repair container/grid |
| focus obstruction | keyboard traversal + screenshot | scroll-padding, overlay position, or modal contract |
| repeated-card density | whole-page comparison | stronger information architecture |

The script reports candidates. Confirm their user-visible effect before
assigning impact. Aesthetic heuristics should normally remain warnings.

## Invalid Fixes

Reject these responses to a finding:

- rename a class to evade the detector;
- add overflow: hidden to erase evidence;
- shrink all type until it fits;
- remove a feature to make a snapshot pass;
- update every visual baseline without isolating the intended change;
- accept a fresh empty state as proof of the populated branch;
- claim a screenshot was reviewed without opening it;
- replace a real GUI requirement with a handler call or headless click;
- fix one occurrence without scanning the repeated component family;
- apply a universal aesthetic rule when the project reference says otherwise.
