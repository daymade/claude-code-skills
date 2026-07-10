---
name: frontend-visual-qa
description: >-
  Reviews rendered frontends, dashboards/admin consoles, GIS/map canvases,
  design-system/live artifacts, HTML slides, and generated UIs for visual/UX
  defects lint/build miss: wrapping, layout drift, wrong branch, broken
  journeys, route drift, repeated cards, non-deep-linkable workspaces, unowned
  rails, blocking drawers, unusable map pan/zoom/hit targets, dashboard-as-manual
  copy, mobile table failures, brand drift, hardcoded chart colors vs
  design-system tokens, colorblind palette gaps, reporting-grade pages a tier
  below their reference, green tests that pass while the view fails the user's
  job, transient toasts a screenshot misses, and browser-integrated
  export/share/download/print/PDF flows. Use after frontend-design or ui-designer,
  or when the user says generic AI slop, screenshot QA, Chrome DevTools,
  Computer Use, enterprise backend design, URL not changing,
  "not the same level/tier", "look at the page yourself", or user-journey
  walkthroughs. Prioritizes real Chrome/GUI evidence, then scriptable sweeps.
---

# Frontend Visual QA

## Purpose

This skill turns recurring frontend review failures into a repeatable rendered visual QA gate. The core lesson: passing `lint`, `build`, or a scripted screenshot is not enough. The agent must prove that the UI the user can actually see has no embarrassing layout defects.

Two failure modes are equally fatal. **Micro** defects include line breaks, wrapped controls, clipped text, and same-row field/control/helper misalignment. **Macro** defects are whole-page composition: an oversized heading, visual weight dumped in one corner, chrome fighting the canvas, or a generic template gestalt that does not match the product/domain. Fixing every micro defect is still not enough if the whole page reads cheap.

A clean screenshot is also not proof if it is the wrong state. Fresh headless or incognito sessions often render logged-out, onboarding, no-data, or empty branches, which can hide the region under review. Visual QA must name the state/branch, exercise the intended journey, and verify that the user can recover from processing, error, and advanced-mode states.

Browser-integrated outputs are part of the product surface. A button that creates a standalone HTML file, share link, clipboard URL, download, popup, file dialog, or PDF print preview is not verified until the visible browser path is clicked and the resulting artifact is opened or previewed. Headless checks and unit tests can miss popup blockers, blank `about:blank` windows, failed downloads, stale share URLs, and print previews that load only the first shell.

Use it after implementation and before saying a UI is done. Also use it during review when the user says things like "不恰当的换行", "断行", "挤在一起", "滚动条不对", "低级排版错误", "AI slop", "use frontend-design to review", "自己用 Chrome 看", or "为什么你检查不出来".

## Relationship To Other Skills

- `ui-designer`: use first when reference screenshots or brand examples exist. It extracts design-system direction from images; it does not verify a live page.
- `frontend-design`: use while designing/implementing. It sets taste, hierarchy, visual assets, and anti-slop direction; it is not a deterministic QA gate.
- `qa-expert`: use for full QA process, test cases, bug tracking, and release gates; it does not specialize in typography/layout line-break defects.
- `frontend-visual-qa`: use after there is something rendered. It checks the actual UI in Chrome and produces fixable findings.

## Required Workflow

1. **Load Project Intent**
   - Read the product/design context, current route/page, and any design-system docs.
   - If the project already has a design system, tokens, brand assets, logo, or product imagery, inspect those first. A new visual direction that ignores available system assets is a finding, not creativity.
   - Identify the page type: real app, dashboard, landing page, deck-like HTML, static design-system reference, live-artifact design system, game/tool.
   - Name the primary user journey and the exact rendered state/branch before judging pixels. If the change is support work, say that; do not let micro-polish become the main goal.
   - Name the default path and exception path. Advanced modes must not hijack the default trigger, and the way back to the default path must be obvious.
   - For apps with multiple pages, tabs, workspaces, or modes, name the route/state contract: the URL/hash for each user-visible workspace, whether refresh restores it, and whether browser back returns to the previous workspace.
   - Name the actor and their job in plain language before reading the UI labels: end user, reviewer, operator, engineer, or admin. If the page is a support/debug artifact, decide which parts are user workflow and which are technical handoff.
   - Translate the workflow into the user's nouns and verbs. If the visible labels say "export JSON", "gate", "case bundle", "cluster", "spk1", "state file", or similar internal objects, check whether those are the product task or just plumbing that should be secondary, collapsed, or renamed.
   - If reference images or official brand materials exist, use them before judging aesthetics.
   - Write down the page's anti-goals before reviewing. Examples:
     - A design-system specimen is not a real app screen.
     - A live-artifact design system is not a static documentation page; interactive controls are allowed when they demonstrate variants, states, chart behavior, responsive behavior, or component anatomy.
     - A landing page is not an internal dashboard.
     - A dashboard is not a marketing poster.
     - An enterprise admin console is not a long waterfall page, tutorial, or instruction manual.
     - A map/GIS page is not a static infographic; pan, zoom, hit targets, selection feedback, and unobstructed inspection are part of the primary task.
   - Treat page-type drift as a defect, not a taste preference.
   - For design systems, decide whether the intended artifact is:
     - **Static reference**: a rendered specification page focused on rules, tokens, examples, and governance.
     - **Live artifact**: an interactive design-system artifact where buttons, tabs, drawers, chart hover states, filters, and state toggles let reviewers test the system in place.
   - Do not remove useful interactivity from a live-artifact design system merely because it resembles product UI. Instead, check whether each interactive module is explicitly framed as a specimen, state demo, pattern, or component contract.

2. **Check The User-Visible Chrome First**
   - If Chrome DevTools tools are available and the user is looking at the page, inspect that page before running headless scripts.
   - If Computer Use or another real GUI controller is available, use it for browser-integrated journeys: click the visible button in Chrome, observe browser chrome, downloads, alerts, new windows/tabs, clipboard/share URLs, and `chrome://print/` preview. DevTools/Playwright can assist, but they do not replace this check for download/share/print/popup paths.
   - For Electron/native/hybrid desktop apps, use the project's canonical app harness. Do not treat a renderer dev-server URL as proof that the native app launched; verify the app process/window and renderer surface.
   - Establish the viewport contract before judging layout. Record all four widths because they answer different questions:
     - `outerWidth`: the user's visible Chrome window.
     - `innerWidth`: the CSS layout viewport the page is rendered into.
     - `visualViewport.width`: the post-emulation/zoom viewport the user is actually seeing.
     - `documentElement.clientWidth`: the page viewport after scrollbar subtraction.
   - Record the real browser state with DevTools:

```js
() => ({
  href: location.href,
  title: document.title,
  innerWidth,
  innerHeight,
  outerWidth,
  outerHeight,
  clientWidth: document.documentElement.clientWidth,
  scrollWidth: document.documentElement.scrollWidth,
  overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  dpr: devicePixelRatio,
  visualViewport: window.visualViewport
    ? { width: visualViewport.width, height: visualViewport.height, scale: visualViewport.scale }
    : null,
  h1: document.querySelector("h1")?.textContent?.replace(/\s+/g, " ").trim() || null,
  metaViewport: document.querySelector('meta[name="viewport"]')?.content || null
})
```

   - If a normal desktop Chrome window is still reporting a mobile viewport such as `390x844`, DevTools emulation is probably still enabled. Reset it to a desktop viewport such as `1440x900x1`, then re-check before judging the page.
   - Also catch subtler desktop emulation drift: if `outerWidth - innerWidth > 120` while the user says the Chrome window is full-size, the page is being judged inside a smaller emulated viewport. Do not judge "right-side blank space" or max-width until the emulated viewport matches the visible browser window or the mismatch is explicitly stated.
   - After unplugging/plugging an external display, changing display scaling, or moving Chrome between displays, treat the existing Chrome window as contaminated until proven clean. Old zoom, stale DevTools emulation, and inherited window bounds can make a correct page look broken or hide a real bug. Prefer restarting a clean Chrome test window/profile, then record `outerWidth`, `innerWidth`, `visualViewport`, and zoom-sensitive geometry again.
   - Measure the first viewport geometry in the same DevTools pass:

```js
() => {
  const content = document.querySelector("main") || document.body;
  const heroImage = [...document.images]
    .filter((img) => img.complete && img.naturalWidth)
    .map((img) => {
      const rect = img.getBoundingClientRect();
      return { img, rect, area: rect.width * rect.height };
    })
    .filter((item) => item.rect.bottom > 0 && item.rect.top < innerHeight)
    .sort((a, b) => b.area - a.area)[0];
  const contentRect = content.getBoundingClientRect();
  return {
    content: {
      left: Math.round(contentRect.left),
      right: Math.round(contentRect.right),
      leftBlank: Math.round(Math.max(0, contentRect.left)),
      rightBlank: Math.round(Math.max(0, innerWidth - contentRect.right)),
    },
    heroImage: heroImage ? {
      displayed: `${Math.round(heroImage.rect.width)}x${Math.round(heroImage.rect.height)}`,
      displayedRatio: +(heroImage.rect.width / heroImage.rect.height).toFixed(3),
      naturalRatio: +(heroImage.img.naturalWidth / heroImage.img.naturalHeight).toFixed(3),
      objectFit: getComputedStyle(heroImage.img).objectFit,
    } : null,
  };
}
```

   - Treat a large right blank area as a viewport-contract problem until proven otherwise: first check `outerWidth - innerWidth`; then compare first-viewport `leftBlank` and `rightBlank`; only then decide whether it is an intentional max-width layout.
   - Do not leave the user's browser stuck in mobile emulation after the review. End on the viewport the user expects, or state exactly what viewport remains active.

3. **Run Mechanical Checks**
   - Start or identify the dev server.
   - Run the app's normal checks first: `lint`, `build`, unit/e2e tests when present.
   - Run the bundled visual audit script when a URL is available:

```bash
cd /path/to/project
npm install -D playwright-core   # if the project does not already have it
node <path-to-this-skill>/scripts/visual_layout_audit.mjs --url http://127.0.0.1:5173/
```

   - The script defaults should avoid hanging on SPAs and dev servers. Use `--wait-until networkidle` only when the app reliably reaches network idle; otherwise prefer `domcontentloaded` plus a settle delay.

   - If the artifact has a known page type, pass it explicitly:

```bash
node <path-to-this-skill>/scripts/visual_layout_audit.mjs \
  --url http://127.0.0.1:5173/ \
  --page-type design-system
```

   - If the intended deliverable is an interactive rendered design system, use the live artifact page type:

```bash
node <path-to-this-skill>/scripts/visual_layout_audit.mjs \
  --url http://127.0.0.1:5173/ \
  --page-type live-artifact-design-system
```

   - For long pages, design systems, and live artifacts, capture lower-section screenshots as part of the same run:

```bash
node <path-to-this-skill>/scripts/visual_layout_audit.mjs \
  --url http://127.0.0.1:5173/ \
  --page-type live-artifact-design-system \
  --screenshot-sections
```

   - Section screenshots should include representative component/specimen, chart/data-viz, pattern/state, and governance/usage areas when those areas exist. A first-viewport-only pass is not enough for a design system.
   - Pass product-specific forbidden rendered terms only when the project has known stale names:

```bash
node <path-to-this-skill>/scripts/visual_layout_audit.mjs \
  --url http://127.0.0.1:5173/ \
  --forbid "Old Product Name|Deprecated Font|staging-only label"
```

   - Pass required rendered terms for the state/branch under review so the sweep proves the relevant surface is present:

```bash
node <path-to-this-skill>/scripts/visual_layout_audit.mjs \
  --url http://127.0.0.1:5173/ \
  --require "Start recording|Settings|Project Alpha"
```

   - If the user is looking at a wider Chrome window than the scripted viewport, pass the visible window width so the script can flag a mismatch:

```bash
node <path-to-this-skill>/scripts/visual_layout_audit.mjs \
  --url http://127.0.0.1:5173/ \
  --expected-window-width 1920
```

   - Do not "fix" script failures by renaming classes, hiding overflow, or removing selectable text. If the script misclassifies a container as a control, fix the script rule or record the false positive with evidence.
   - The script is a sweep, not proof by itself. DevTools evidence and screenshot inspection still decide user-visible correctness.

4. **Use Real Browser Evidence**
   - First confirm the screenshot is on the same state/branch the user is reporting. Compare `h1`, title, visible headline, and required rendered terms. If the user is on a connected/populated branch but the capture shows onboarding/empty/logged-out, the screenshot is invalid for this review.
   - Reach the user's actual state by reusing their browser/profile, seeding required data, setting the app's onboarding-complete flag, or using the app's own e2e/mock harness. If you must use mock data or a substituted font, state that tradeoff.
   - Screenshot the whole rendered page first — sidebar, header, main, footer/composer, and chrome included — before zooming into any inner container. Macro composition defects are only visible at this scale.
   - Verify at least one desktop viewport and one mobile viewport.
   - Record: `outerWidth`, `innerWidth`, `visualViewport.width`, `outerWidth - innerWidth`, `innerHeight`, `overflowX`, document title/H1, important image load status.
   - For the first viewport, also record the effective content bounds, left/right blank space, primary image displayed ratio versus natural ratio, and whether any label/caption overlaps important image content.
   - Record enough typography evidence to answer whether the font, spacing, width, text size, and style are right: body font family, H1 size, body size, sidebar/rail width, repeated text-column width, and smallest important text size.
   - Take screenshots. Inspect them. Do not treat the screenshot file as proof until you actually look at it.
   - Some UI is time-boxed: toasts, snackbars, auto-dismissing banners, inline validation that clears on the next keystroke, and short animations live for a second or two and then vanish. A single screenshot, or a `wait_for` that fires a beat late, can miss them entirely — and "I couldn't capture it" then gets misread as "it never rendered" or "the handler is broken." Absence of a capture is not evidence of absence; a screenshot that arrives after the element auto-dismissed proves nothing about whether it fired. Before concluding a transient element is missing or broken, instrument its lifecycle instead of racing it: attach a `MutationObserver` (or capture the relevant event) that records every matching node as it is added, then trigger the action and read the log. Only after the observer stays empty across repeated triggers is "it did not fire" an actual finding. Conversely, if the observer proves the toast fires with the right text, then the real defect is often that it is too ephemeral to read (see the error-copy persistence note in Exercise The User Journey), not that it is absent.

```js
// Arm before triggering the action. Adapt the selector to the app's toast/alert markup.
() => {
  window.__transient = [];
  const sel = '[role="alert"], .toast, .snackbar, .notification, .ant-message, [class*="toast"]';
  new MutationObserver(() => {
    document.querySelectorAll(sel).forEach((el) => {
      const t = el.textContent?.replace(/\s+/g, " ").trim();
      if (t && !window.__transient.includes(t)) window.__transient.push(t);
    });
  }).observe(document.body, { childList: true, subtree: true });
  return "observer armed";
}
// ...trigger the action, let it settle, then read what actually appeared:
// () => window.__transient
```

   - If the user complained about a specific area, scroll to that area and screenshot it, not just the top of the page.
   - For repeated controls, form fields, state rails, metric cards, tab bars, or design-system specimens, run an explicit geometry pass. Compare siblings that share a visual row or repeated component contract: label top, control/input top and bottom, helper/error top, field height, left/right edges, and baseline rhythm. A field with an error/helper must not sit higher/lower than its sibling; either reserve an empty helper slot or change the layout so the whole row stays aligned.
   - Do not rely on "looks roughly lined up" from a full-page screenshot when the user points to a local mismatch. Use bounding boxes from the real DOM for the disputed group, then inspect the local screenshot.
   - For long pages or design systems, inspect at least the first viewport plus representative lower sections. Do not stop after a clean hero/cover screenshot.
   - For a live artifact design system, exercise at least one interactive specimen: variant/tab/segmented switch, drawer/modal open-close, chart state, filter state, or responsive/state demo. Record what changed and whether text, overlay, scroll ownership, or overflow broke while the state was active.
   - If no meaningful interaction can be exercised in a live artifact, report that as a finding rather than silently treating it as static documentation.

5. **Exercise The User Journey And State Contract**
   - Click through the actual path the user will take, not only the initial render. Verify the primary action, stop/cancel path, retry path, settings/escape hatch, and return-to-idle path.
   - For export/download/share/print flows, exercise every user-visible output path that is part of the deliverable:
     - Download/export: click the real control, verify the browser reports a completed download or the file appears, then open/inspect the artifact instead of trusting the click handler.
     - Share link: create the link, open it in a normal tab/window, verify the shared page is read-only when intended, and inspect desktop plus mobile-ish rendering if external readers will use phones.
     - PDF/print: click the real control and verify Chrome print preview opens with nonblank rendered pages and the expected destination. Opening `about:blank`, a blocked popup alert, or a preview with only shell chrome is a P1. Do not claim a saved PDF exists unless it was actually saved and visually inspected.
     - Clipboard/alert/new-tab paths: verify the visible result, not only the API call.
   - For tabbed dashboards and multi-workspace apps, verify navigation changes both the visible workspace and the addressable state. Refresh, direct deep link, and browser back/forward must return to the expected workspace unless the product explicitly has a single-page temporary preview contract.
   - For enterprise admin pages, verify the default screen is operational: tables, matrices, filters, queues, maps, row actions, or selected-object inspectors should carry the work. Explanatory copy, onboarding prose, and repeated metric cards must not displace the primary workflow.
   - For map/GIS pages, exercise wheel/button zoom, drag pan, region/marker click, reset/fit, and selection clearing. Popovers, permanent panels, toolbars, or drawers must not cover the target the user just clicked or make nearby regions hard to hit.
   - For detail drawers, inspectors, and side panels, verify the ownership contract: no selected object means no permanent generic detail panel; selected-object details must be closeable or clearly contextual; masks must not block unrelated navigation unless the workflow is intentionally modal.
   - For data tables on mobile, verify the user can still scan the important fields and trigger row actions. A desktop table with horizontal scroll can be acceptable for dense admin work, but it fails when key columns/actions disappear, labels squeeze, or the user must drag sideways before understanding the row.
   - For annotation, correction, approval, or review pages, verify the default path is "confirm what the system already thinks, correct only what is wrong, save/finish" rather than "understand machine labels, choose from raw clusters, export evidence." Machine predictions should be visible as editable defaults, not duplicated as non-editable status chips plus separate choices.
   - Verify that raw machine identifiers, IDs, logs, JSON filenames, gate names, and follow-up commands are not the main call to action. Keep them available in diagnostics or technical handoff when they are necessary, but do not make them the primary user journey.
   - Verify that the user can defer or stop without losing work. A review/annotation queue must have an obvious save/finish/skip path and should not imply that the user must complete an unbounded backlog.
   - For modeful UIs, list the mutually exclusive modes and the owner of each trigger. The same key/button/gesture must not silently mean two unrelated things unless the mode is unmistakable, switching is explicit, and the default path has an obvious one-step return.
   - Verify the authenticated-but-unauthorized state, not only logged-in and logged-out. A user who signs in successfully but has no role, membership, tenant, or permission yet must not see the same surfaces, entries, and actions as a privileged user. Fail-closed belongs at the UI layer too: if the data layer denies the rows but the UI still renders the privileged shell and entry points, the user lands in a populated-looking workbench that dead-ends on every click. The correct state is a plain "no access yet / contact your admin" surface. This state is easy to miss because a fresh test account often has full seed permissions — provision or borrow a genuinely role-less account to see it.
   - For each visible state (`ready`, `active`, `processing`, `error`, `disabled`, `recovery`), verify that the copy says what is happening, the action available is the next safe action, and global/floating surfaces show the same mode.
   - Every blocking or long-running state must show progress, current work, or a recovery action. A stuck `processing` state with no way back to the main journey is a P1 even if the layout is pretty.
   - Error states must preserve the feature context that failed. A multi-step or mode-specific failure must not degrade into a generic error that looks like another feature failed.
   - Error copy must be in the user's language and register. Raw backend strings, English exception messages, or stack fragments leaking to a localized or non-technical audience — for example a login form that shows a verbatim English `Invalid login credentials` to operators who use the product in another language — is a defect: map known errors to human, localized text and fall back to the raw string only for genuinely unknown ones. An error the user must act on also needs a surface that persists long enough to read and act on. A toast that auto-dismisses in ~3s is too ephemeral for an actionable failure; prefer inline or persistent placement with `role="alert"` so assistive tech announces it, and clear the fields the user must re-enter (for example the password) so the recovered state is legible rather than looking unchanged.
   - Convert each confirmed miss into either a product fix or a regression guard. A visual QA finding that remains only in chat memory is not closed.
   - When a UI is a temporary scaffold that may later become product infrastructure, review it with product standards anyway: low-friction defaults, plain actor/task language, and compounding user effort. Do not excuse hostile interaction just because the page was first built for diagnostics.

6. **Run A Counter-Review Pass**
   - Before reporting "done" on nontrivial UI, run an adversarial pass focused on what a tired real user would misunderstand first: mode ownership, the way back to default, blocked states, misleading provider/model labels, raw machine IDs, internal artifact language, inaccessible controls, whether the UI asks for avoidable manual work, and which guard now catches the same class of miss.

7. **Classify Findings**
   - `P0`: page unusable, blank, primary action blocked, text unreadable, severe overlap.
   - `P1`: horizontal page overflow, double/incorrect scroll container, modal/toolbar/panel blocks content, major responsive failure, ambiguous primary trigger, non-addressable navigation for real pages/workspaces, unusable map pan/zoom/hit targets, permanent unowned side rail, detail drawer mask blocking unrelated work, hidden way back to default mode, stuck processing with no recovery, wrong error/feature context, wrong app/surface verified.
   - `P2`: awkward heading line break, orphan Chinese character/word, wrapped button/tag, cramped card text, important image missing.
   - `P3`: minor spacing, weak contrast, inconsistent alignment, non-critical polish.
   - `Intent`: wrong artifact type, such as a design system presented as a fake app, a dashboard presented as a poster, or a landing page presented as a component catalog.
   - `Taste`: generic AI slop aesthetic, wrong domain style, unmotivated gradient/glow/card pile, not enough brand/product signal.

8. **Fix And Re-run**
   - Do not say "fixed" after editing CSS. Re-run the visual checks and inspect screenshots again.
   - For a subjective visual choice — which of several colors, gradients, spacings, radii, or weights reads right — do not guess-commit-revert, and do not ask the user to imagine the options. Preview the candidates live in the browser first: override the token/style with DevTools `evaluate_script`, or drop a small comparison overlay that renders each candidate as a swatch/row, screenshot it, and pick from the rendered evidence before editing source. This turns a taste argument into a visual diff, avoids edit-revert churn, and gives a defensible reason for the choice. When the change is to a shared design token, preview it on a dense specimen page too — not only the one screen that prompted it — so a global change is judged where it actually repeats.
   - If there is a benchmark, put your after-screenshot beside it and name the concrete remaining gap. A general aesthetic principle never outranks the specific target the user asked to match.
   - For awkward line breaks, prefer structural fixes over random width tweaks:
     - shorten copy;
     - split title into intentional spans;
     - change layout tracks;
     - widen the semantic column;
     - move metadata into a second line;
     - use `white-space: nowrap` only for short labels/buttons/tags;
     - use `text-wrap: balance` for headings where supported;
     - use container-specific font sizes, not viewport-wide scaling.

## What To Check

Load `references/history-derived-checklist.md` for the detailed checklist; for reporting-grade data pages (dashboards, KPI boards, monitoring consoles) also load `references/data_viz_tier_and_token_audit.md`. Minimum checks:

- awkward Chinese or mixed Chinese/English line breaks;
- semantic Chinese word splits across rendered line boundaries in high-visibility copy, such as `这|里`, `这|个`, `不|是`, or `我|们`;
- orphan lines where high-visibility text ends with one or two Chinese characters;
- short-tail lines in ordinary body copy are context-dependent: do not mechanically fail every 2-3 character tail. Judge by visibility, semantic break, repeated occurrence, and whether the container is unnecessarily narrow.
- wrapped controls: buttons, tabs, pills, tags, nav items, menu labels;
- typography system mismatch: font family, type scale, line height, text-column width, and density do not match the artifact type or domain;
- cramped text in cards/tables/timelines;
- text clipped by fixed heights;
- same-row sibling drift: labels, inputs, helper/error text, tab items, metric cards, and repeated component specimens not sharing the same visual axes;
- helper/error slot shifts: one field grows or moves because only one sibling has helper/error copy, making paired fields look misaligned;
- horizontal page overflow;
- viewport/window mismatch that makes a normal desktop Chrome render through a smaller emulated viewport;
- excessive or asymmetric blank space in the first viewport;
- lower-section layout failures that are hidden by a clean first viewport;
- scroll container mistakes: double scrollbars, page scroll when a panel should scroll, sticky controls blocking content;
- overlapping elements;
- route/state drift: visible page, workspace, tab, or mode changes while the URL/hash, refresh state, browser history, or direct deep link does not;
- enterprise-admin drift: long waterfall layouts, instruction-manual copy, overview KPI strips repeated on every workspace, or decorative panels replacing the table/map/queue/action surface;
- persistent side rails or "tabs" that consume width without being a real navigation area, drawer, inspector, or selected-object context;
- drawer/overlay state defects: opened drawer uses a mask that blocks unrelated navigation, has no close path, has unstable width, or overflows mobile;
- mobile table collapse defects: desktop table columns/actions disappear or require sideways dragging before the user can understand the row;
- map/GIS interaction defects: no zoom/pan, tiny or obstructed hit targets, popovers covering the clicked region, toolbar overlays blocking markers, or selection panels that prevent inspection;
- images not loaded, distorted, stretched, too cropped, wrong aspect ratio, overlaid by labels/captions, or not representative of the product/domain;
- project design-system drift: available tokens, components, logo, or product imagery are ignored in favor of a new unrelated visual language;
- title/H1/visible system name drift;
- page-type drift: design system vs app/workbench/dashboard/landing/deck;
- live-artifact drift: useful interactive specimens are wrongly removed, or live controls appear without specimen labels, state/variant framing, or usage rules;
- unexercised live-artifact interactions: controls exist, but nobody checked the changed state for overflow, clipping, overlay, stale chart data, or scroll problems;
- ambiguous or overloaded controls/shortcuts;
- hidden or confusing return path from advanced mode back to the default mode;
- blocked processing/error states without recovery or clear next action;
- provider/model/runtime labels that are too vague, stale, or not backed by the actual selected path;
- browser-integrated output defects: download not completed, standalone export unreadable, share link opens the wrong/blank state, print/PDF preview blocked or blank, or clipboard/new-tab behavior unverifiable in the real browser;
- internal implementation language leaking into the main path: JSON/export/gate/log/case IDs, raw model clusters, or command snippets shown as the thing the user is supposed to understand;
- review/annotation UX that makes users choose from unnamed machine IDs, repeat a default prediction, or finish by exporting evidence instead of completing a human task;
- one-off correction flows that do not explain or implement how a correction reduces future work;
- wrong app surface: renderer page verified while the native shell/user-visible app was not;
- repeated card/panel grids that replace information architecture;
- generic AI slop aesthetics: purple/blue gradient default, glass cards, decorative orbs/glow, card grids everywhere, vague "AI empowers" copy.
- accidental brand collision: a decorative motif reproduces another famous brand's signature — four equal hard-edged primary blocks read as Google's bar, a particular swoosh or ring reads as a competitor logo — so the product looks off-brand or unprofessional. It is most visible on a lone hero element where the motif stands alone rather than dissolving into a dense grid; when in doubt, anchor the motif in the product's own brand color and soften the resemblance.
- success-target drift: e2e/visual assertions that only prove structure exists ("section present", "tab switches", "nine zones render") while never asserting the view answers the user's actual question at that state — a false pass that hides a product gap;
- transient-UI verification gap: a toast/snackbar/auto-dismissing alert/inline validation is declared missing or broken because a single screenshot or a late `wait_for` did not catch it, without instrumenting the element's lifecycle to prove presence or absence — treating a missed capture as a negative result; or the element does fire correctly but auto-dismisses too fast for the user to read an actionable message;
- visual-tier drift: a reporting-grade data page (dashboard, KPI board, monitoring console) rendered at generic-admin tier — small single-color numbers, plain-text verdict, separate card pile — when the user has a higher-tier reference in mind. Open the reference, diff quantifiable params (number px, color semantics, notes-per-KPI). See `references/data_viz_tier_and_token_audit.md`;
- chart color-token drift: chart/series colors hardcoded as hex instead of design-system tokens (grep `#[0-9a-fA-F]{6}` outside the token file; prove resolution with `getComputedStyle`), or a categorical series palette shipped without colorblind (CVD) validation and colliding with the semantic hues. See `references/data_viz_tier_and_token_audit.md`.

## Page-Type Contracts

Use this section before judging the UI. A visually polished page can still be wrong if it is the wrong artifact.

### Design System / Specimen

Expected signals:
- scope and version;
- design principles;
- foundations/tokens: color, typography, spacing, radius, elevation, motion;
- component anatomy, variants, states, usage, do/don't;
- patterns that combine components;
- accessibility, content, data-viz, responsive, and governance rules.

Red flags:
- the page reads as a real workbench/dashboard instead of a specification;
- business metrics, competitor notes, or roadmap content dominate the first screen;
- many repeated cards replace component anatomy and usage guidance;
- fake data modules look like product features rather than specimens;
- the artifact lacks do/don't, states, or governance.

### Live Artifact Design System

Expected signals:
- visible system scope, version, and artifact status;
- interactive specimens for components, charts, states, tokens, responsive behavior, or patterns;
- each live module is labelled as a specimen, pattern, state demo, or component contract;
- interactions expose design behavior: variant switching, state changes, empty/error/loading cases, chart tooltip/selection, drawer/modal behavior, responsive collapse, or governance rules;
- sample business data is clearly specimen data and does not pretend that the real app/workbench is complete.

Red flags:
- treating all controls, tabs, buttons, drawers, or charts as "fake app" and stripping the artifact into a dead static document;
- app-like panels dominate without anatomy, variants, state names, usage rules, or do/don't guidance;
- the page becomes an operational workbench where the reviewer cannot tell what design rule is being demonstrated;
- repeated business cards replace component contracts and interaction specimens;
- live interactions change content but do not reveal any design-system behavior.
- controls cannot be exercised, or the exercised state creates overflow, clipped text, modal/drawer scroll mistakes, or stale chart labels.

### Real App / Dashboard

Expected signals:
- task-first layout, real navigation, addressable page/workspace state, meaningful data states, one scroll owner;
- enterprise admin surfaces prioritize tables, matrices, maps, queues, filters, row actions, and drill-ins over explanatory prose;
- overview metrics appear where they help triage; subpages use workspace-specific summaries or no top metrics at all;
- detail drawers/panels are invoked by selection or action; the default state gives width to the primary work surface;
- controls have stable dimensions and do not wrap;
- data visualizations show units, source, time range, and empty/error states.

Red flags:
- marketing hero composition inside an operations tool;
- the page becomes a long explanatory waterfall instead of a backend users can scan and operate;
- decorative cards around every section;
- the same KPI card strip appears on every workspace regardless of that workspace's job;
- tab/sidebar navigation changes the visible page but leaves the URL stuck on the parent route;
- a permanent right rail consumes canvas width without behaving like navigation, an inspector, or a dismissible drawer;
- a drawer opens with a mask or fixed width that blocks unrelated work, hides the table, or overflows mobile;
- a mobile breakpoint hides table meaning instead of offering a readable card/list/table pattern;
- chart-like visuals without units or source;
- global page scroll competing with panel scroll.

### Map / GIS Workbench

Expected signals:
- zoom in/out, wheel zoom or equivalent, drag pan, reset/fit-to-view, and clear selection are available and verified;
- geographic regions, markers, and clusters have generous hit targets and visible hover/selected states;
- details appear in an inspector or drawer that does not cover the clicked geography or prevent the next click;
- map controls, legends, labels, and popovers have stable layers and do not overlap important features;
- selected map state can sync to the rest of the dashboard without trapping the user.

Red flags:
- a "map" is a static illustration with no real pan/zoom;
- the user must click several times because markers or provinces are too small, overlapped, or hidden under a tooltip/panel;
- labels, popovers, or side panels block the exact province/city/marker the user is trying to inspect;
- switching into the map workspace leaves the URL on the previous dashboard route.

## Evidence Format

When reporting, be concrete:

```markdown
Findings:
- P2 awkward heading break: `.hero-title` renders as `客户增长分析 / 系统` at 1700px. Fix: split H1 into intentional semantic spans.
- P1 horizontal overflow: mobile 390px has `overflowX=42`; source `.toolbar`.
- P1 mode collision: `Fn` starts two unrelated flows with no visible mode boundary; fix by assigning explicit triggers and a visible return-to-default path.
- P1 route-state drift: clicking `Map` renders the map workspace but the URL remains `#/dashboard`; fix by giving each workspace a canonical route and testing refresh/back/deep-link.
- P1 map interaction defect: the map has province markers but no zoom/pan and selection popovers cover neighboring targets. Fix: add map navigation controls, larger hit targets, and non-blocking inspector placement.
- P1 enterprise-admin drift: every workspace repeats the same four overview KPI cards before the actual work surface. Fix: keep overview metrics on the overview only and let subpages start with their task surface.
- P1 permanent rail without ownership: a right-side rail is visible before anything is selected and only contains generic prose. Fix: remove it, convert it to navigation, or make it an invoked selected-object drawer/inspector.
- P1 drawer blocks main workflow: opening row details creates a mask over the table and prevents workspace navigation. Fix: use a true modal only when blocking is intentional; otherwise use a non-modal drawer and verify close/width/mobile behavior.
- P1 mobile table collapse: mobile 390px hides key account fields/actions behind a desktop-width table. Fix: provide a mobile card/list/table pattern with the same decision fields and row action.
- P1 PDF export path broken: clicking `PDF` in real Chrome opens `about:blank` or a popup-blocked window instead of a rendered print preview. Fix: use a user-gesture-safe print path and verify `chrome://print/` shows nonblank pages.
- P1 share artifact drift: the in-app page is readable, but the generated share URL opens an empty/raw/protocol-heavy page. Fix: route share output through the same overview-first rendering contract and test the share URL directly.
- P1 internal workflow leak: the review page's primary action is `Export JSON`, while the user's task is to finish a review. Fix: rename the main action to `Save review result`, keep JSON/commands in technical handoff, and add forbidden-term checks for retired labels.
- P1 raw machine-label UX: the page asks users to choose `Cluster 1 / spk1 / spk2` without first naming people. Fix: show editable human aliases as the primary choices and demote machine IDs to secondary tokens.
- P2 same-row field mismatch: paired fields render with helper/error slot heights that differ by 18px; fix by reserving helper slots or stacking fields.
- Taste: hero uses generic purple gradient and no real product/domain visual; replace with domain-specific image.

Verified:
- state/branch: connected ready branch, h1 matches user-reported state.
- journey: start -> processing -> recovery -> idle verified; stale shortcut copy absent.
- desktop 1700x1000: `overflowX=0`, title/H1 correct, primary image loaded.
- mobile 390x844: `overflowX=0`, no wrapped controls.
- screenshots: `/tmp/page-desktop.png`, `/tmp/page-mobile.png`.
- browser outputs: HTML download completed and opened; share URL opened in Chrome; PDF print preview rendered 50 nonblank pages.
```

## Anti-Patterns

- Checking only code and not rendered output.
- Using a narrow desktop window and calling it mobile or desktop validation.
- Leaving DevTools mobile emulation active, then mistaking the page for a broken desktop layout.
- Leaving a desktop emulated viewport active inside a larger Chrome window, then missing a large blank area the user can see.
- Trusting a Chrome window after display changes without restarting or revalidating zoom/emulation/window bounds.
- Judging only `innerWidth` while the user is reacting to the full visible Chrome `outerWidth`.
- Calling a centered max-width layout "fine" before checking whether the right blank area is symmetric and intentional.
- Taking a screenshot but not opening it.
- Concluding a toast/snackbar/transient element "does not fire" from one screenshot or a late `wait_for`, instead of arming a MutationObserver or event capture and proving what actually rendered. A missed capture is not a negative result; the element may live for a second and vanish before the tool reacts.
- Reviewing only the first viewport of a long page and missing broken lower sections.
- Leaving tabs/drawers/modals/chart states unclicked in a live artifact.
- Fixing one visible line break without scanning other headings/buttons/tables.
- Overcorrecting Chinese short-tail lines by forcing every 2-3 character final line to disappear.
- Answering "font/spacing/width/size/style are fine" without computed values and screenshot evidence.
- Guess-committing a subjective visual choice (color, gradient, spacing, weight) and reverting when it looks wrong, instead of previewing the candidates live in the browser and comparing screenshots before touching source.
- Gaming the QA script by renaming classes or hiding overflow instead of fixing the visual defect or the detector.
- Treating a design-system specimen as permission to build a fake product screen.
- Turning "avoid repeated cards" into a mechanical "remove all cards" rule. The real issue is whether cards serve component specimens or replace information architecture.
- Reusing the same top KPI cards on every page because they look "dashboard-like." Overview metrics belong to overview; workspaces need the controls and data for their own task.
- Letting a tab/workspace switch remain invisible to URL, refresh, deep link, and browser history.
- Treating a GIS/map view as acceptable because it looks like a map image while basic zoom, pan, click, and unobstructed inspection are broken.
- Adding a permanent right rail because there is space, without deciding whether it is navigation, an inspector, or a dismissible drawer.
- Letting a drawer inherit modal behavior by accident. If the rest of the dashboard should remain usable, verify mask count, pointer events, close behavior, and responsive width.
- Calling mobile "responsive" because page-level `overflowX` is zero while the actual data table is unusable or key actions are hidden.
- Writing explanatory prose to justify an interface instead of making the interface directly usable.
- Inventing a fresh brand treatment while existing design-system tokens, assets, or logos are available.
- Adding `overflow: hidden` to hide the problem.
- Shrinking all text until it fits.
- Letting labels or table first columns break character-by-character.
- Accepting same-row field/control/helper misalignment because each individual component looks valid in isolation.
- Saying "responsive" because CSS has media queries.
- Treating `frontend-design` as a substitute for actual Chrome verification.
- Treating a headless Playwright pass as proof that the user's current Chrome window is correct.
- Treating a Playwright click, unit test, or direct function call as proof that browser chrome behaviors work. Downloads, clipboard, popups, share links, and print/PDF previews need real GUI evidence when they are part of the deliverable.
- Claiming PDF export is fixed because `window.print()` was called, without observing Chrome print preview and rendered pages.
- Treating a renderer dev server as proof that an Electron/native app launched.
- Verifying one static screenshot while skipping the user's actual journey and state transitions.
- Treating an internal diagnostic or review scaffold as exempt from product UX standards when it is part of a workflow the user may repeat.
- Making users reason about raw clusters, speaker IDs, JSON files, logs, gate names, or command snippets before they can complete the human task.
- Duplicating machine predictions as header badges and selectable options, so the default state looks like a choice the user must repeat rather than a prediction they can correct.
- Turning user correction into one-time busywork. If a user labels, accepts, rejects, skips, or corrects something, the system should save it, reuse it, and reduce future asks when the product supports that loop.
- Fixing a user-reported UI miss without adding any regression guard or repeatable review step.
- Fixing a user-reported UI miss with a project-specific one-off script when the failure class is generic. Convert it into a reusable checklist item, visual audit rule, or test pattern instead.
- Treating a rendered page or a green test suite as proof of user success. An assertion that "the section is present" or "the tabs switch" stays green while the artifact still fails the actor's real job; assert on the content that answers the user's question at each state, not on the DOM node's existence.
- Accepting a generic-admin visual tier (small single-color numbers, plain-text verdict, card pile) when the user has a higher-tier reference in mind, instead of opening that reference and diffing quantifiable params (number px, semantic color, notes-per-KPI). The tier gap is measurable, not vibes.
- Hardcoding chart/series colors as hex when the design system defines color tokens, and shipping a categorical identity palette without colorblind (CVD) validation — or reusing the semantic palette (alert-red, success-green) as series identity so a line reads as a status.

## Bundled Resources

- `scripts/visual_layout_audit.mjs`: Playwright-core script that loads a URL at desktop/mobile viewports and reports bad terms, horizontal overflow, section overflow, orphan heading lines, wrapped controls, clipped text, image defects, same-row field/control/helper misalignment, and optional lower-section screenshots.
- `references/history-derived-checklist.md`: distilled checklist from local Claude/Codex history and recurring user corrections.
- `references/data_viz_tier_and_token_audit.md`: for reporting-grade data pages — the "success is the actor's job, not render/green-tests" standard, benchmarking visual tier against a reference with quantifiable params, design-system color-token audit (hardcoded hex + `getComputedStyle` proof), and colorblind (CVD) validation for categorical series palettes.
