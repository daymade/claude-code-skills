---
name: frontend-visual-qa
description: >-
  Reviews rendered frontends, websites, dashboards, HTML slides, design-system
  specimens, live-artifact design systems, and generated UIs for visual quality
  defects that lint/build miss.
  Use when shipping or reviewing UI, especially after frontend-design or
  ui-designer work, or when the user mentions awkward line breaks, orphan
  Chinese characters, cramped text, wrapped buttons/tags/nav, horizontal
  overflow, double scrollbars, overlapping elements, repeated card piles,
  wrong page type such as a design system turning into an app dashboard, tiny
  dense typography, wrong font/spacing/width/type-scale choices, generic AI
  slop, screenshot QA, Chrome DevTools, or "look at the page yourself."
  Prioritizes the user's real Chrome viewport when
  available, then runs scriptable desktop/mobile sweeps.
---

# Frontend Visual QA

## Purpose

This skill turns recurring frontend review failures into a repeatable rendered visual QA gate. The core lesson: passing `lint`, `build`, or a scripted screenshot is not enough. The agent must prove that the UI the user can actually see has no embarrassing layout defects.

Use it after implementation and before saying a UI is done. Also use it during review when the user says things like "不恰当的换行", "断行", "挤在一起", "滚动条不对", "低级排版错误", "AI slop", "use frontend-design to review", "自己用 Chrome 看", or "为什么你检查不出来".

## Relationship To Other Skills

- `ui-designer`: use first when reference screenshots or brand examples exist. It extracts design-system direction from images; it does not verify a live page.
- `frontend-design`: use while designing/implementing. It sets taste, hierarchy, visual assets, and anti-slop direction; it is not a deterministic QA gate.
- `qa-expert`: use for full QA process, test cases, bug tracking, and release gates; it does not specialize in typography/layout line-break defects.
- `frontend-visual-qa`: use after there is something rendered. It checks the actual UI in Chrome and produces fixable findings.

## Required Workflow

1. **Load Project Intent**
   - Read the product/design context, current route/page, and any design-system docs.
   - Identify the page type: real app, dashboard, landing page, deck-like HTML, static design-system reference, live-artifact design system, game/tool.
   - If reference images or official brand materials exist, use them before judging aesthetics.
   - Write down the page's anti-goals before reviewing. Examples:
     - A design-system specimen is not a real app screen.
     - A live-artifact design system is not a static documentation page; interactive controls are allowed when they demonstrate variants, states, chart behavior, responsive behavior, or component anatomy.
     - A landing page is not an internal dashboard.
     - A dashboard is not a marketing poster.
   - Treat page-type drift as a defect, not a taste preference.
   - For design systems, decide whether the intended artifact is:
     - **Static reference**: a rendered specification page focused on rules, tokens, examples, and governance.
     - **Live artifact**: an interactive design-system artifact where buttons, tabs, drawers, chart hover states, filters, and state toggles let reviewers test the system in place.
   - Do not remove useful interactivity from a live-artifact design system merely because it resembles product UI. Instead, check whether each interactive module is explicitly framed as a specimen, state demo, pattern, or component contract.

2. **Check The User-Visible Chrome First**
   - If Chrome DevTools tools are available and the user is looking at the page, inspect that page before running headless scripts.
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

   - If the user is looking at a wider Chrome window than the scripted viewport, pass the visible window width so the script can flag a mismatch:

```bash
node <path-to-this-skill>/scripts/visual_layout_audit.mjs \
  --url http://127.0.0.1:5173/ \
  --expected-window-width 1920
```

   - Do not "fix" script failures by renaming classes, hiding overflow, or removing selectable text. If the script misclassifies a container as a control, fix the script rule or record the false positive with evidence.
   - The script is a sweep, not proof by itself. DevTools evidence and screenshot inspection still decide user-visible correctness.

4. **Use Real Browser Evidence**
   - Verify at least one desktop viewport and one mobile viewport.
   - Record: `outerWidth`, `innerWidth`, `visualViewport.width`, `outerWidth - innerWidth`, `innerHeight`, `overflowX`, document title/H1, important image load status.
   - For the first viewport, also record the effective content bounds, left/right blank space, primary image displayed ratio versus natural ratio, and whether any label/caption overlaps important image content.
   - Record enough typography evidence to answer whether the font, spacing, width, text size, and style are right: body font family, H1 size, body size, sidebar/rail width, repeated text-column width, and smallest important text size.
   - Take screenshots. Inspect them. Do not treat the screenshot file as proof until you actually look at it.
   - If the user complained about a specific area, scroll to that area and screenshot it, not just the top of the page.
   - For long pages or design systems, inspect at least the first viewport plus representative lower sections. Do not stop after a clean hero/cover screenshot.
   - For a live artifact design system, exercise at least one interactive specimen: variant/tab/segmented switch, drawer/modal open-close, chart state, filter state, or responsive/state demo. Record what changed and whether text, overlay, scroll ownership, or overflow broke while the state was active.
   - If no meaningful interaction can be exercised in a live artifact, report that as a finding rather than silently treating it as static documentation.

5. **Classify Findings**
   - `P0`: page unusable, blank, primary action blocked, text unreadable, severe overlap.
   - `P1`: horizontal page overflow, double/incorrect scroll container, modal/toolbar blocks content, major responsive failure.
   - `P2`: awkward heading line break, orphan Chinese character/word, wrapped button/tag, cramped card text, important image missing.
   - `P3`: minor spacing, weak contrast, inconsistent alignment, non-critical polish.
   - `Intent`: wrong artifact type, such as a design system presented as a fake app, a dashboard presented as a poster, or a landing page presented as a component catalog.
   - `Taste`: generic AI slop aesthetic, wrong domain style, unmotivated gradient/glow/card pile, not enough brand/product signal.

6. **Fix And Re-run**
   - Do not say "fixed" after editing CSS. Re-run the visual checks and inspect screenshots again.
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

Load `references/history-derived-checklist.md` for the detailed checklist. Minimum checks:

- awkward Chinese or mixed Chinese/English line breaks;
- semantic Chinese word splits across rendered line boundaries in high-visibility copy, such as `这|里`, `这|个`, `不|是`, or `我|们`;
- orphan lines where high-visibility text ends with one or two Chinese characters;
- short-tail lines in ordinary body copy are context-dependent: do not mechanically fail every 2-3 character tail. Judge by visibility, semantic break, repeated occurrence, and whether the container is unnecessarily narrow.
- wrapped controls: buttons, tabs, pills, tags, nav items, menu labels;
- typography system mismatch: font family, type scale, line height, text-column width, and density do not match the artifact type or domain;
- cramped text in cards/tables/timelines;
- text clipped by fixed heights;
- horizontal page overflow;
- viewport/window mismatch that makes a normal desktop Chrome render through a smaller emulated viewport;
- excessive or asymmetric blank space in the first viewport;
- lower-section layout failures that are hidden by a clean first viewport;
- scroll container mistakes: double scrollbars, page scroll when a panel should scroll, sticky controls blocking content;
- overlapping elements;
- images not loaded, distorted, stretched, too cropped, wrong aspect ratio, overlaid by labels/captions, or not representative of the product/domain;
- title/H1/visible system name drift;
- page-type drift: design system vs app/workbench/dashboard/landing/deck;
- live-artifact drift: useful interactive specimens are wrongly removed, or live controls appear without specimen labels, state/variant framing, or usage rules;
- unexercised live-artifact interactions: controls exist, but nobody checked the changed state for overflow, clipping, overlay, stale chart data, or scroll problems;
- repeated card/panel grids that replace information architecture;
- generic AI slop aesthetics: purple/blue gradient default, glass cards, decorative orbs/glow, card grids everywhere, vague "AI empowers" copy.

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
- task-first layout, real navigation, meaningful data states, one scroll owner;
- controls have stable dimensions and do not wrap;
- data visualizations show units, source, time range, and empty/error states.

Red flags:
- marketing hero composition inside an operations tool;
- decorative cards around every section;
- chart-like visuals without units or source;
- global page scroll competing with panel scroll.

## Evidence Format

When reporting, be concrete:

```markdown
Findings:
- P2 awkward heading break: `.hero-title` renders as `客户增长分析 / 系统` at 1700px. Fix: split H1 into intentional semantic spans.
- P1 horizontal overflow: mobile 390px has `overflowX=42`; source `.toolbar`.
- Taste: hero uses generic purple gradient and no real product/domain visual; replace with domain-specific image.

Verified:
- desktop 1700x1000: `overflowX=0`, title/H1 correct, primary image loaded.
- mobile 390x844: `overflowX=0`, no wrapped controls.
- screenshots: `/tmp/page-desktop.png`, `/tmp/page-mobile.png`.
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
- Reviewing only the first viewport of a long page and missing broken lower sections.
- Leaving tabs/drawers/modals/chart states unclicked in a live artifact.
- Fixing one visible line break without scanning other headings/buttons/tables.
- Overcorrecting Chinese short-tail lines by forcing every 2-3 character final line to disappear.
- Answering "font/spacing/width/size/style are fine" without computed values and screenshot evidence.
- Gaming the QA script by renaming classes or hiding overflow instead of fixing the visual defect or the detector.
- Treating a design-system specimen as permission to build a fake product screen.
- Turning "avoid repeated cards" into a mechanical "remove all cards" rule. The real issue is whether cards serve component specimens or replace information architecture.
- Adding `overflow: hidden` to hide the problem.
- Shrinking all text until it fits.
- Letting labels or table first columns break character-by-character.
- Saying "responsive" because CSS has media queries.
- Treating `frontend-design` as a substitute for actual Chrome verification.
- Treating a headless Playwright pass as proof that the user's current Chrome window is correct.

## Bundled Resources

- `scripts/visual_layout_audit.mjs`: Playwright-core script that loads a URL at desktop/mobile viewports and reports bad terms, horizontal overflow, section overflow, orphan heading lines, wrapped controls, clipped text, image defects, and optional lower-section screenshots.
- `references/history-derived-checklist.md`: distilled checklist from local Claude/Codex history and recurring user corrections.
