---
name: frontend-visual-qa
description: >-
  Audits already-rendered web, landing-page, HTML deck/slide, browser tool/game,
  dashboard/admin, design-system, and desktop UIs using real-browser or
  native-app journeys, inspected screenshots, DOM geometry, responsive or
  projection viewports, and a bundled Playwright sweep. Use after UI
  implementation to find typography, wrapping, overlap, overflow, responsive,
  route, overlay, map, transient-state, data-visualization, browser-output,
  file-dialog, PDF/print, or Electron-shell defects, or to compare a rendered
  artifact with a visual reference. Do not use for greenfield UI design,
  extracting a design system from screenshots, general QA-program setup, or
  nonvisual code debugging.
---

# Frontend Visual QA

Audit the interface the user can actually see. Treat build success, DOM presence,
and uninspected screenshot files as supporting signals, never as visual proof.

Default to **audit-only**. Do not edit implementation, add tests, install
dependencies, or update snapshots unless the user explicitly asks to fix or
change the UI.

## Scope And Routing

Use this skill only after a rendered artifact exists. Select the smallest audit
profile that covers the request:

- **core visual** — composition, typography, spacing, wrapping, clipping, images;
- **responsive** — breakpoints, reflow, mobile alternatives, scroll ownership;
- **state and journey** — conditional branches, transitions, recovery, routes;
- **browser output** — download, share, clipboard, popup, file dialog, print, PDF;
- **native shell** — Electron or hybrid chrome, permissions, drag regions, IPC UI;
- **page contract** — dashboard/admin, landing/deck, design-system artifact,
  browser tool/game, map/GIS, or review tool;
- **reference parity** — comparison with a named screenshot, product, or tier;
- **data visualization** — chart hierarchy, tokens, semantics, and accessibility.

Combine profiles only when the changed surface or the user requests a broad
release review. Do not force a local line-break review through unrelated auth,
map, export, and native-shell checks.

Use adjacent skills by stage:

- Use ui-designer, frontend-design, or another design skill to derive or create
  a visual direction.
- Use this skill to test the already-rendered result.
- Use qa-expert for a full test strategy, defect program, and release metrics.
- Use both this skill and qa-expert only when rendered visual evidence is one
  part of a broader QA gate.

## Required Outcome

Produce all of the following:

1. A scope contract naming the artifact, actor, job, exact route/state, relevant
   viewports, affected journeys, reference/SSOT, and audit-only versus
   fix-and-verify authorization.
2. A verification status: **verified**, **partial**, or **blocked**.
3. Findings tied to visible evidence, impact, state, viewport, and reproduction.
4. A list of what was actually exercised and what remains unverified.
5. When authorized to fix, a same-state/same-viewport re-run and a proportionate
   regression guard.

Never downgrade the user's real objective to whatever evidence was easiest to
collect.

## Workflow

Track this checklist for nontrivial audits:

    - [ ] 1. Establish the audit contract and authorization
    - [ ] 2. Select the required evidence level and canonical harness
    - [ ] 3. Prove the route, state, data, and viewport are the intended ones
    - [ ] 4. Capture and inspect macro, local, and responsive evidence
    - [ ] 5. Exercise the affected journeys and recipient outputs
    - [ ] 6. Report findings; fix and re-run only when authorized

### 1. Establish The Audit Contract

Read the project instructions, design-system SSOT, tokens, approved assets,
launcher/test SOP, and the changed code. Then write a falsifiable contract:

    Artifact/page type:
    Actor and job:
    Exact route + conditional state:
    Reference or design-system SSOT:
    Relevant viewport/device matrix:
    Intended projection/canvas size, if any:
    Affected interactions and outputs:
    Audit profiles:
    Authorization: audit-only | fix-and-verify
    Anti-goals / must-not-become:
    Pass condition:

Name the correct state before judging pixels. Logged-out, onboarding, empty,
permission-denied, seeded, populated, loading, and feature-flag branches can look
like different products. A clean screenshot of the wrong branch is invalid.
When authorization is in scope, signed-in-but-role-less is a distinct branch;
logged-out or fully privileged evidence cannot stand in for it.

Use the actor's task as the success target. “The chart exists” or “the tab
switches” is not enough when the user needs to decide severity, finish a review,
or recover from an error.

### 2. Select The Evidence Level

Use the strongest level required by the claim:

| Level | Evidence | Claims it can support |
|---|---|---|
| A | Real visible Chrome/browser or canonical native-app window, driven through the user journey | Browser/OS chrome, downloads, clipboard, popup blocking, file pickers/dialogs, print preview, permissions, native shell, actual visible-window complaints |
| B | Same-state browser DevTools or project E2E/Playwright run with representative data | DOM geometry, routes, focus, overlays, interaction states, repeatable responsive behavior |
| C | Fresh headless mechanical sweep from the bundled script | Overflow, wrapping, images, basic layout heuristics, screenshot candidates |
| D | Source, lint, build, unit tests, or static DOM reasoning | Hypotheses and regression support only |

Do not promote a lower level into a stronger conclusion:

- A screenshot path that was never opened has no visual evidence value.
- A fresh headless empty state cannot verify the user's populated state.
- A renderer URL cannot verify an Electron/native shell.
- A handler call cannot verify Chrome print preview, popup, or download UI.
- Device emulation is an approximation; use a real device when device-specific
  behavior is material.

If the required Level A surface is unavailable or another session owns the GUI,
continue only with evidence that does not pretend to replace it. Report the
exact missing evidence and mark the affected claim **partial** or **blocked**.

### 3. Prove State And Viewport

Use the project's canonical launcher and existing fixture/auth path. Do not
invent a new server command or silently seed a different state.

Two driving constraints decide what evidence is even obtainable, so settle them
before capturing anything. **Extension-based browser control generally cannot
open `file://`** — a local artifact needs a local HTTP server before it can be
driven interactively, and the two schemes differ in CORS behavior, so name which
one produced the evidence. And **after any edit, assume the browser is showing
you the previous build**: cache-bust the URL and verify a visible freshness
anchor (version stamp / build time) before judging content, or you will chase a
defect you already fixed. Both traps, plus the click/screenshot/emulation ones,
are in
[references/browser-driving-and-observation-traps.md](references/browser-driving-and-observation-traps.md).

Record this state from the rendered page:

    () => ({
      href: location.href,
      title: document.title,
      h1: document.querySelector("h1")?.textContent?.replace(/\s+/g, " ").trim() || null,
      inner: [innerWidth, innerHeight],
      outer: [outerWidth, outerHeight],
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      visualViewport: visualViewport
        ? [visualViewport.width, visualViewport.height, visualViewport.scale]
        : null,
      dpr: devicePixelRatio,
      metaViewport: document.querySelector('meta[name="viewport"]')?.content || null,
    })

Compare outerWidth, innerWidth, visualViewport, and clientWidth before blaming
CSS for blank space or mobile layout. Reset stale zoom/device emulation and
re-capture after display or scale changes. Restore the user's expected viewport
when finished.

For a scripted sweep, first prove the target state is reproducible with one of:

- the project's fixture/storage-state/setup path;
- one or more required rendered markers passed with repeated --require flags;
- a direct deep link whose refresh restores the same state.

Otherwise label the run a **fresh-session diagnostic**, not a pass.

When the audit must sign in to a SPA, when scripted login fails or bounces back
to the auth route, or when the target runs on localhost behind shell proxies,
load
[references/auth-session-and-environment-traps.md](references/auth-session-and-environment-traps.md)
before filing any login/network finding — those failures are usually the
driving harness or the environment impersonating a product defect.

After authentication, do not drive from remembered sidebar labels or assume the
target navigation is already mounted. Record the final URL, a short visible body
excerpt, and the currently available links/buttons; then follow the canonical
entry the rendered landing page actually exposes. If an expected locator is
absent, treat navigation-contract or harness drift as the leading diagnosis
until the target route/state is independently proven.

### 4. Capture And Inspect Rendered Evidence

Capture the whole visible composition before zooming into a local defect. Then
inspect the affected component and at least one relevant responsive width.
Include lower sections for long pages; a clean hero does not validate the rest.

Open every screenshot with an image viewer and record what you saw. Use DOM
geometry to explain a visible problem, not to replace visual judgment.

Check at minimum:

- macro hierarchy, balance, density, repeated context, and page-type fit;
- type family, size, weight, line height, tracking, column width, and semantic
  line breaks;
- computed body/key-heading typography, relevant control/text-column/rail
  widths, and the smallest important text when DOM evidence is available;
- wrapped controls, clipped content, unexpected overflow, competing scroll
  owners, sticky overlap, dense data-driven collisions, and same-row alignment;
- image load, crop, natural/display ratio, focal point, and overlay collisions;
- mobile preservation of identity, status, decision fields, and primary action;
- status-semantic density on list/queue pages: alarm-toned chips repeated across
  rows, one global fact re-rendered per row, and unlabeled numeric/graphic cells
  (contract details in the journey/page-contract reference);
- keyboard focus visibility, focus obstruction, and target size/spacing when
  accessibility is in scope. A default screenshot cannot show this: an element
  can pass "is it focusable" and still leave the user lost, because a global
  `outline:none` suppressed the ring and nothing replaced it. The sweep reports
  `focus-indicator-suppressed` (error) and `focus-indicator-default-only`
  (warning); confirm visually that the focus state is also distinguishable from
  the *selected* and *hover* states, which a stylesheet audit cannot judge;
- motion that ignores user preference — the sweep reports
  `motion-without-reduced-motion-fallback` when the page animates but declares no
  `@media (prefers-reduced-motion: reduce)`. Degrading means keeping the end
  state and dropping the travel (keep the highlight, drop the flash), not
  removing the feedback;
- states that only exist off the default path: a wrapped narrow-viewport row
  screenshotted *with a selection active*, a scroll container at a height that
  actually scrolls, an expanded/error/empty variant. Default-state evidence is
  partial evidence — say which states the report covers
  ([references/browser-driving-and-observation-traps.md](references/browser-driving-and-observation-traps.md) §6);
- parity with the named reference and the project's tokens/assets before
  applying generic taste rules.

Load [references/history-derived-checklist.md](references/history-derived-checklist.md)
for the core visual/responsive defect catalog and standards-backed checks.

Some defects produce no diagnostic anywhere: a global reset outranking a
component's own styles, a library renaming its internal DOM classes so whole
rule groups match nothing, a font family declared but never shipped, geometry
written into theme config where source scans cannot see it, a new design token
reusing a name the file already spent, a property that cannot apply because the
rule never set the layout mode it presupposes, and per-element compliance that
still reads as "no design system" in aggregate. Source review, type checks and
geometry assertions are structurally blind to these — the artifacts are valid
and simply do nothing. When a page looks cheap while every gate is green, that
combination is the signature. Load
[references/silent-degradation-and-evidence.md](references/silent-degradation-and-evidence.md)
for the detection method per class, and probe the two highest-yield ones
mechanically:

    node <skill-root>/scripts/silent_degradation_probe.mjs font \
      --url http://127.0.0.1:5173/ --weight 700 \
      --family "Brand Sans" --family "Fallback Sans"

    node <skill-root>/scripts/silent_degradation_probe.mjs class \
      --css path/to/bridge.css --library-css node_modules/<lib>/dist/<lib>.css

Pass every family in the stack and the weight the page really uses. The probe
answers with five verdicts — platform generic / healthy / host-provided-only /
broken asset / absent here — and only host-provided-only and broken asset are
defects. CSS generic families such as `system-ui` are intentionally supplied by
the platform; never tell users to bundle or remove them. Do not compress the
remaining outcomes into "working or dead": a bundled fallback and a
never-shipped family look identical until the fonts are loaded, and reporting
the first as the second sends the reader to delete the thing that was protecting
them.

A declared font that never loads is the single highest-yield check, because it
degrades every screen simultaneously and both obvious tests give false
positives: computed `fontFamily` returns the declared name, and
`document.fonts.check()` returns true even with no `@font-face` at all. Only
comparing rendered width against a deliberately nonexistent family is decisive,
and the probe string must contain Latin characters — CJK is full-width in every
font and cannot reveal a substitution. Width comparison has its own trap: fonts
load lazily, so measure only after awaiting `document.fonts.load()` for each
candidate, or a perfectly good bundled fallback reads as dead.

Run the bundled sweep from the audited project so it can resolve the project's
existing Playwright dependency:

    node <skill-root>/scripts/visual_layout_audit.mjs \
      --url http://127.0.0.1:5173/ \
      --page-type app \
      --require "Expected state marker" \
      --screenshot-sections

Use --file <artifact.html> for a local HTML artifact. Run
node <skill-root>/scripts/visual_layout_audit.mjs --help for all flags. For a
contracted canvas, pass one or more exact viewports; custom viewports replace
the default responsive matrix:

    node <skill-root>/scripts/visual_layout_audit.mjs \
      --file deck.html --page-type deck --viewport 1920x1080 \
      --screenshot-sections

For a long page whose evidence depends on below-the-fold covers or thumbnails,
add --scroll-visible-media. It visits rendered media rows before capture so lazy
loading can start, while excluding CSS-hidden responsive alternatives. Without
that flag, offscreen lazy media is reported as deferred coverage rather than a
broken asset. In either mode, inspect the screenshots: “not requested,” “still
loading,” and “request completed but undecodable” are different states.

Use repeated --forbid patterns only for project-specific stale names or rendered
terms that the current product contract explicitly prohibits. Do not encode
generic taste preferences as forbidden regexes.

The script exits:

- 0 when no mechanical errors remain;
- 1 when errors remain, or warnings remain with --fail-on-warning;
- 2 for invalid input, missing prerequisites, or runtime/setup failure.

The script writes viewport screenshots and frontend-visual-qa-report.json to a
unique temporary run directory by default. An explicit --out directory must be
new or empty so stale screenshots cannot masquerade as current evidence. It is a
Level C sweep, not the final verdict.

Do not mutate the audited project merely to run the sweep. Reuse its package
manager and canonical browser harness. If Playwright is absent, continue with
available Level A/B evidence and report the omitted Level C sweep; install a
dependency only when dependency changes are authorized.

For an authenticated page, pass repeated `--header "Name: value"` flags only
when needed. The probe applies them exclusively to the `--url` origin and strips
them from cross-origin redirects and requests. TLS verification stays enabled;
use `--ignore-https-errors` only for an explicitly trusted self-signed test
origin.

Run the probe regressions from a project that already provides Playwright:

```bash
node --test <skill-root>/tests/test_silent_degradation_probe.mjs
```

### 5. Exercise Journeys And Outputs

Exercise only the relevant transition matrix:

    entry -> ready -> active -> processing -> success/error -> recovery -> ready

Also verify, when applicable:

- click -> URL/state -> refresh -> deep link -> back/forward;
- drawer/modal/popover open, focus, background interaction, close, and mobile;
- transient notification lifecycle with observation armed before the trigger;
- advanced mode -> visible current mode and trigger owner -> one-step return to default;
- provider/model/runtime status -> selected configuration and current status evidence;
- download -> completed file -> opened recipient artifact;
- share -> copied/opened URL -> refreshed recipient state;
- file picker/dialog -> visible open/cancel/select path -> recovered app state;
- print/PDF -> real Chrome preview -> nonblank pages;
- Electron/native -> canonical app process/window -> native controls and shell.

Load
[references/journey-and-page-contracts.md](references/journey-and-page-contracts.md)
when the audit includes state transitions, authorization, modes,
provider/model/runtime truth, routes, transient states, overlays, browser
outputs, native shells, landing/deck/browser tool/game artifacts, dashboards,
design-system artifacts, GIS/maps, or review tools.

Load
[references/data_viz_tier_and_token_audit.md](references/data_viz_tier_and_token_audit.md)
only for reporting-grade data pages, named tier/reference comparisons, chart
token audits, or categorical palettes.

Before reporting a nontrivial audit, re-walk the primary path as a tired user
without debugger context. Look first for unclear trigger or mode ownership,
hidden return-to-default, blocked recovery, misleading runtime labels, raw
machine language, unreachable controls, avoidable manual work, and the missing
guard that would let the same defect recur. This is a falsification pass, not an
excuse to expand a local visual-only audit into every profile.

### 6. Report, Fix, And Re-run

**Every appearance claim ships with the pixels that show it.** A reader who
cannot see the defect cannot decide anything about it, and cannot check whether
the finding is even real. Crop to the affected element with just enough
surrounding context to locate it — a full-page screenshot proves nothing about a
14px misalignment, and prose alone ("the buttons look cheap") is unactionable no
matter how accurate. `scripts/silent_degradation_probe.mjs shot` crops one
element plus padding for exactly this.

Four rules that decide whether the evidence survives contact with a reader:
comparisons must be **scale-matched** (two full-width regions placed side by side
shrink until the 3px difference under discussion vanishes — crop both to the same
component at the same width instead); dimensions are reported in **CSS px, never
device px** (a DPR-2 capture has twice the pixel count, and quoting that as page
height has produced a false "20 screens long" finding); a capture taken before a
fix is **labeled with the commit it shows** rather than presented as current; and
findings resting on a **code count** rather than a photograph are **marked as
such**, so the reader knows which parts of the list are equally evidenced.

Separate **impact** from **category**. Follow the project's severity taxonomy
when one exists. Otherwise use:

- **Blocker** — false success, destructive/misleading action, or primary journey
  cannot complete without a safe workaround;
- **Major** — core task, recipient output, recovery, route, or critical control
  is unusable;
- **Moderate** — comprehension or operation is materially degraded but a safe
  workaround exists;
- **Minor** — polish defect with little task impact.

Use categories such as layout, responsive, state, route, accessibility,
browser-output, native-shell, intent, or taste. Taste and Intent are not
severity levels.

Report with this compact schema:

    Status: verified | partial | blocked
    Scope: <artifact, route/state, viewports, profiles>

    Findings:
    - Major · browser-output · PDF action · desktop
      Evidence: clicking the visible control opens about:blank; print preview has no page.
      Fix: use a user-gesture-safe print path and re-test the recipient preview.

    Verified:
    - <journey/state/viewport + concrete evidence>

    Not verified:
    - <missing surface/evidence and why>

In **audit-only** mode, stop after the evidence-backed report. In
**fix-and-verify** mode:

1. Fix the root cause rather than hiding overflow, shrinking all type, changing
   selectors to evade the detector, or removing a feature.
2. Preview subjective alternatives live before committing a shared visual token.
3. Re-run the same route, state, viewport, journey, and recipient output.
4. Add or update the smallest regression guard that would catch the confirmed
   failure class.

Three habits keep the fix pass from manufacturing its own defects — each has
produced one:

- **Shoot the "before" while the defect still exists.** After the rebuild it is
  unreproducible, and a closure report can then only assert the improvement.
  Reuse the identical crop window for the after-shot so the pair differs by one
  variable.
- **Grep a new shared name before introducing it.** A token named after a word
  the file already spent (`rail`, `bar`, `card`) silently overrides or gets
  overridden depending on definition order, changing two subsystems at once
  (silent-degradation class 1f).
- **Prove the repaired assertion can fail.** Reintroduce the defect, watch it go
  red with the expected magnitude, then remove it. An assertion that stayed
  green through the whole bug does not become a guard by being rewritten.

## Completion Gate

Call the audit **verified** only when:

- the intended route, branch, data, and actor state are proven;
- every screenshot cited in the report was opened and inspected;
- relevant viewports and lower sections were covered;
- affected interactions and outputs were exercised at the required evidence
  level;
- no unresolved Blocker/Major finding contradicts the pass;
- remaining limitations are explicit;
- an authorized fix was rechecked in the same conditions.

Otherwise report **partial** or **blocked**. Never ask the user to perform a
check the available agent tools can perform.

## Bundled Resources

- scripts/visual_layout_audit.mjs — Playwright-powered mechanical viewport,
  layout, and media-state sweep with screenshots and JSON evidence.
- references/history-derived-checklist.md — core visual/responsive defect
  catalog plus standards-backed checks.
- references/journey-and-page-contracts.md — state, route, overlay,
  browser-output, native-shell, and page-type contracts.
- references/auth-session-and-environment-traps.md — authenticated-SPA login and
  post-login navigation driving traps plus environment hijack diagnostics
  (proxy, CSP entry point, server-log triangulation).
- references/data_viz_tier_and_token_audit.md — conditional data-viz,
  reference-tier, token, and palette audit.
- references/browser-driving-and-observation-traps.md — the auditor's own failure
  modes: misread clicks, stale caches, `file://` limits, viewport-vs-page
  screenshots, width-resize vs device emulation, states a default screenshot
  cannot show, hidden-tab media deferral, virtual-time false negatives,
  `--dump-dom` timing (and the title-encoded interaction probe done right), and
  Range-server media stalls. Read it before driving a real browser, and whenever an observation
  surprises you.
- evals/evals.json and evals/trigger-evals.json — behavior and routing
  regression cases; excluded from packaged runtime content.
