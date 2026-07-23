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
change the UI. Permission to fix source does not authorize rebuilding,
restarting, or deploying any target.

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
- This skill audits whether an artifact **renders** correctly, not whether it
  **communicates**. A page can pass every check here while its labels are opaque
  internal abbreviations and its numbers contradict each other between sections.
  Route copy, terminology and audience fit to a content/writing-discipline skill,
  and never let a green visual pass be reported as "a first-time reader can
  follow this" — that is a different question, answered by a reader, not by a
  rendering.

## Required Outcome

Produce all of the following:

1. A scope contract naming the artifact, actor, job, target kind and canonical
   target identity, conditional state, viewports, affected journeys,
   reference/SSOT, and authorization.
2. A verification status: **verified**, **partial**, or **blocked**.
3. Findings tied to visible evidence, impact, state, viewport, and reproduction.
4. A list of what was actually exercised and what remains unverified.
5. When freshness or deployment is claimed, a separate delivery status and its
   identity evidence; when target mutation is explicitly authorized, identity
   before/after, a same-target/state/viewport re-run, and a regression guard.

Never downgrade the user's real objective to whatever evidence was easiest to
collect.

## Workflow

Track this checklist for nontrivial audits:

    - [ ] 1. Establish the audit contract and authorization
    - [ ] 2. Select the required evidence level and canonical harness
    - [ ] 3. Prove the target, state, data, viewport, and claimed freshness
    - [ ] 4. Capture and inspect macro, local, and responsive evidence
    - [ ] 5. Exercise the affected journeys and recipient outputs
    - [ ] 6. Report findings; fix and re-run only when authorized

### 1. Establish The Audit Contract

Read the project instructions, design-system SSOT, tokens, approved assets,
launcher/test SOP, and the changed code. Then write a falsifiable contract:

    Artifact/page type:
    Actor and job:
    Target kind + canonical identity:
      web = exact in-browser URL (query/fragment included) + named environment
      single file/image = canonical path + content hash + rendering scheme
      multi-resource artifact = canonical entry + dependency/manifest digest + renderer
      native = installed artifact fingerprint + build/version + process/window + renderer route
    Conditional state:
    Delivery identity/status, only when freshness/deployment is claimed:
    Reference or design-system SSOT:
    Relevant viewport/device matrix:
    Intended projection/canvas size, if any:
    Affected interactions and outputs:
    Audit profiles:
    Source authorization: audit-only | fix-and-verify
    Interaction/action authority: read-only navigation | fixture-safe state changes | <named actions>
    Target mutation authority: none | isolated diagnostic | local target | deploy <named environment>
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
- A pointer cursor, hover style, or "click to X" badge cannot verify the click
  does anything: a signifier without a working handler is a dead click, confirmed
  only by triggering it (step 5).
- Device emulation is an approximation; use a real device when device-specific
  behavior is material.

If the required Level A surface is unavailable or another session owns the GUI,
continue only with evidence that does not pretend to replace it. Report the
exact missing evidence and mark the affected claim **partial** or **blocked**.

### 3. Prove Target, State And Viewport

Read project-authoritative status before launching anything. Use the canonical
launcher only when each side effect fits its own authority: lifecycle permission
covers rebuild/restart/deploy, while seed or transactional data changes require
interaction/action authority. Never infer one from the other. An authorized
isolated diagnostic server is labeled non-target.

Keep an exact web URL in browser memory, but persist only a redacted structural
URL plus a stable digest/query-key list. Single files/images use path, content
hash, and renderer; multi-resource HTML/decks require an authoritative resource
manifest or dependency-closure digest. Native UI needs an installed-artifact
fingerprint/code signature plus build, process/window, and renderer route.
A renderer dev URL is diagnostic only. Treat raw screenshots as temporary local
sensitive evidence; share/commit only a minimal redacted derivative.

When a claim concerns a source change, freshness, or deployment, additionally
close the source-to-target chain:

1. take the expected identity from the target's release contract, not local HEAD
   unless that target is supposed to run HEAD;
2. read project-authoritative runtime build/image/release status;
3. map browser/data-plane evidence to that expected artifact—a hashed filename
   alone proves nothing unless an expected manifest maps it;
4. prove the intended route, actor, data, conditional state, and viewport.

Without identity mapping, a freshness/deployment claim is **unprovable**; when
neither is claimed, use **not applicable**. Current pixels remain independently verifiable.
If a source fix and target differ, its closure stays **partial — source fixed,
verification target stale**. Audit-only work continues inspecting the live
target without mutation. Source fix authority alone does not permit a target
lifecycle; with separately authorized target mutation, record identity before
the action, run only the named canonical lifecycle, re-prove identity, and
repeat the same target/state/viewport. If lifecycle ownership is unresolved,
that mutation path is **blocked**.

Prefer a cache-disabled reload/fresh context. Change the query only when the
project declares it semantically inert, preserve existing query/fragment, and
run final evidence on the original URL. The detailed page-state probe,
`file://` boundary, cache rules, redirects, and viewport comparison are in
[references/browser-driving-and-observation-traps.md](references/browser-driving-and-observation-traps.md)
§2–§5. Record the final URL and dimensions before CSS diagnosis, then restore
the user's expected viewport when finished.

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

Capture the whole visible composition before zooming into the defect, then the
affected component, relevant responsive widths, and lower sections. Open every
screenshot with an image viewer and record what you saw; an uninspected file is
not evidence.

Calibrate the capture before trusting it. Falsify apparent clipping against DOM
geometry, pin device scale where supported, wait for fonts/network/animation,
and use the engine the recipient actually views. DOM evidence explains pixels;
it does not replace them.

The full capture-calibration protocol and minimum inspection set are in
[references/browser-driving-and-observation-traps.md](references/browser-driving-and-observation-traps.md)
§12. Extent and device-emulation traps specific to headless capture are
catalogued in the same reference at §4–§5.

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

Pass every family in the stack and the weight the page really uses. Interpret
all five verdicts exactly; platform generics are healthy, while only
host-provided-only and broken asset are defects. The reference explains why
computed family names, `document.fonts.check()`, unloaded candidates, and
CJK-only width probes otherwise create false conclusions.

Run the bundled sweep from the audited project so it can resolve the project's
existing Playwright dependency:

    node <skill-root>/scripts/visual_layout_audit.mjs \
      --url 'http://127.0.0.1:5173/?state=fixture#/ready' \
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

The script writes screenshots and its JSON report to a unique temporary run
directory; explicit --out must be new or empty. It is a Level C sweep, not the
final verdict. Never commit/share raw evidence: reports hash rendered labels and
redact target-derived values, while derivative screenshots need identifying
pixels redacted. Its target-string fingerprint and single-file byte hash do not
compute a multi-resource closure/native identity; supply the project contract.

Do not mutate the audited project merely to run the sweep. Reuse its package
manager and canonical browser harness. If Playwright is absent, continue with
available Level A/B evidence and report the omitted Level C sweep; install a
dependency only when dependency changes are authorized.

Pass headers through `--header-env "Name: ENV_NAME"`; argv contains only the
header/env names, never the value. Raw `--header` is disabled. Values stay on the
target origin; TLS stays enabled except for an explicitly trusted self-signed origin.

Run the probe regressions from a project that already provides Playwright:

```bash
node --test <skill-root>/tests/test_silent_degradation_probe.mjs
```

### 5. Exercise Journeys And Outputs

**A visible signifier is not proof of behavior — trigger every relevant control
whose side effects fit the explicit action authority, confirm the response, and
mark the rest unverified.** Pointer/hover/button styling can be a false affordance:
the handler is absent or stale, while screenshots and plausible source both pass.
Only a real Level A/B trigger verifies behavior. Prioritize late-added lightboxes,
thumbnail grids, and copy actions. Assert the resulting state—not dispatch—and
rule out delegation, hydration timing, or trusted-gesture gates before calling a
dead click (browser-driving-and-observation-traps.md trap 1). A missing visible
cue around working behavior is the inverse failure in the silent-degradation
reference.

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

    Current-render status: verified | partial | blocked
    Delivery status: matched | mismatched | unprovable | not applicable
    Fix-closure status: verified | partial | blocked | not applicable
    Target: <web: redacted requested/final + target-string fingerprint/query keys/redirects | single-file/image: redacted canonical path + content hash + renderer | multi-resource: entry + authoritative manifest/dependency-closure digest + renderer | native: installed-artifact fingerprint/signature + build/version + process/window + renderer route>
    Environment: <verified name or unverified>
    Delivery identity: <expected; observed before -> after; evidence>
    Actor/job; reference/pass condition; affected journeys:
    Authorization: <source scope; interaction/action scope; target-mutation scope>
    Scope: <state, viewports, profiles>

    Findings:
    - Major · browser-output · PDF action · desktop
      Impact/state/viewport/reproduction:
      Evidence artifact/crop:
      Evidence: clicking the visible control opens about:blank; print preview has no page.
      Fix: use a user-gesture-safe print path and re-test the recipient preview.

    Verified:
    - <journey/state/viewport + concrete evidence>

    Not verified:
    - <missing surface/evidence and why>

In **audit-only** mode, continue read-only evidence gathering but make no source
or target mutation. In **fix-and-verify** mode:

1. Fix the root cause rather than hiding overflow, shrinking all type, changing
   selectors to evade the detector, or removing a feature.
2. Preview subjective alternatives live before committing a shared visual token.
3. Update a target only under its separate named mutation authority; otherwise
   report source-fixed/target-unverified without expanding scope.
4. Re-run the same canonical target and re-prove identity, route, state,
   viewport, journey, and recipient output.
5. Add or update the smallest regression guard that would catch the confirmed
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

Call **current-render status** verified only when:

- the canonical target kind/identity, final target, data, and actor state are
  proven;
- delivery is matched, mismatched, or unprovable when freshness is claimed,
  otherwise not applicable;
- every screenshot cited in the report was opened and inspected;
- relevant viewports and lower sections were covered;
- affected interactions and outputs were exercised at the required evidence
  level;
- no unresolved Blocker/Major finding contradicts the pass;
- remaining limitations are explicit.

Call **fix-closure status** verified only after an authorized fix is rechecked against the same canonical target/state/viewport; otherwise use partial or blocked.

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
  Range-server media stalls. Read it before driving a real browser, and whenever
  an observation surprises you.
- evals/evals.json and evals/trigger-evals.json — behavior and routing
  regression cases; excluded from packaged runtime content.
