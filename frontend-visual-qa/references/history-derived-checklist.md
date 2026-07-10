# History-Derived Frontend Visual QA Checklist

This checklist was distilled from local Claude/Codex history where the user repeatedly corrected rendered frontend artifacts. The raw histories contain private project details; this file keeps the reusable patterns and removes project-specific content.

## Contents

- Recurring Failure Patterns
- Macro Composition Failures
- Whole-Page-First Rule
- Right-State-First Rule
- Journey-State Contract
- Browser-Integrated Delivery Flow Rules
- Mandatory Viewports
- Text And Line-Break Rules
- Layout Rules
- Design-System Artifact Rules
- Live Artifact Design-System Rules
- Enterprise Admin / Dashboard Rules
- Drawer / Inspector Rules
- Map / GIS Rules
- Aesthetic Rules
- How This Differs From Existing Skills

## Recurring Failure Patterns

| Pattern | What It Looked Like | Detection Heuristic | Preferred Fix |
|---|---|---|---|
| Awkward heading break | A title breaks into a final line with one or two Chinese characters, or a semantic phrase is split apart. | In Chrome, inspect rendered text lines for headings and titles. Flag final lines with <=2 non-space chars. | Split the heading intentionally, shorten copy, widen the column, or use `text-wrap: balance`. |
| Semantic word split | High-visibility Chinese copy breaks a common two-character word across lines, such as `这|里`, `这|个`, `不|是`, `我|们`, or `需|要`. It looks careless even when neither line is a short tail. | Inspect rendered line boundaries for key headings, hero/lead copy, labels, spec cells, and repeated component text. Do not apply this mechanically to every ordinary paragraph. | Rewrite the sentence, widen the semantic column, use intentional spans for short phrases, or move the clause to a new line. |
| Over-strict short-tail policing | A reviewer tries to eliminate every two- or three-character final line in normal body copy, creating needless rewrites or over-wide layouts. | Treat short tails as contextual. Prioritize headings, controls, labels, table/spec cells, first viewport copy, and repeated obvious cases. | Fix visible semantic breaks and cramped containers; do not chase every ordinary body-copy short tail. |
| Table first-column break | A short label, date, name, or module title breaks character-by-character in a narrow table column. | Scan table cells and row headers for multi-line short strings. | Change column widths, use `white-space: nowrap` for short labels, or restructure the table for mobile. |
| Wrapped controls | Button/tag/nav text wraps onto two lines, making the control look cheap or ambiguous. | Flag buttons, tabs, nav items, tags, pills with more than one rendered line. | Shorten label, increase control width, use icon+tooltip, or change layout. |
| Sibling field axis drift | Two fields in the same row look related, but one label/input/helper starts higher or lower than the other. | For same-row field groups, compare bounding boxes for field top, label top, input top/bottom, helper/error top, and field height. | Use a shared field component, stable row tracks, and reserved helper/error slots so every sibling has the same vertical anatomy. |
| Helper/error slot shift | One field has an error/helper message and its sibling has none, so the row appears misaligned even though each field is valid alone. | In paired fields, check whether helper/error copy changes the field height or pushes only one control. Empty helper slots count as intentional structure when they preserve alignment. | Reserve an empty helper slot, move helper/error copy into a consistent row, or stack fields instead of pretending they are paired. |
| Repeated specimen axis mismatch | Design-system specimens, state rails, tabs, or metric cards use the same component idea but inconsistent widths, baselines, or edge alignment. | Screenshot the whole group, then measure sibling left/right/top/bottom values in DOM bounding boxes. | Put repeated items on a common grid/flex contract; define stable dimensions and alignment tokens for the component family. |
| Text block crowding | Cards contain too much prose, causing dense grey text and poor hierarchy. | Count lines and visual density; screenshot review catches this better than DOM alone. | Rewrite copy, split into bullets, promote only high-value text, add hierarchy and spacing. |
| Double or wrong scrollbar | Page scrolls when a panel/sidebar should scroll, or two scrollbars appear on the right. | Check scroll containers and user interaction path; verify with Chrome. | Define one owner for scroll. Use `min-height: 0`, stable panel heights, and scoped overflow. |
| DevTools viewport drift | Browser window looks normal, but the page renders as mobile because DevTools emulation was left at `390x844` or another device profile. | In Chrome DevTools, compare `outerWidth/outerHeight` to `innerWidth/innerHeight`, `visualViewport`, and `devicePixelRatio`. | Reset emulation to a desktop viewport before desktop review; after mobile checks, return to the user's expected viewport. |
| Contaminated browser state after display changes | After unplugging an external monitor or changing display scale, the old Chrome window keeps stale zoom, emulation, or window bounds. The page appears broken until Chrome is restarted. | When the user changes displays, do not trust prior screenshots. Re-read `outerWidth`, `innerWidth`, `visualViewport`, DPR, and zoom-sensitive layout geometry in a restarted or explicitly reset Chrome window. | Restart a clean Chrome test window/profile, or explicitly reset zoom/emulation/window bounds before visual QA. Treat earlier evidence as invalid unless it is reproduced after reset. |
| Desktop viewport mismatch | Chrome is a wide desktop window, but DevTools still emulates a narrower desktop viewport such as `1440` inside a `1920` outer window, creating a large blank area on the user's visible screen. | In Chrome DevTools, flag `outerWidth - innerWidth > 120` when the user is looking at a normal desktop window. Also compare the right edge of the main container against both `innerWidth` and `outerWidth`. | Match the emulated viewport to the actual visible browser window, or explicitly state the mismatch before judging layout. |
| Asymmetric first-viewport blank space | A hero or design-system cover leaves a visibly huge empty area on the right while the content appears pinned left or underfilled. | Measure the first viewport content bounds: `leftBlank`, `rightBlank`, content width ratio, and `rightBlank - leftBlank`. Compare against `outerWidth - innerWidth` before blaming CSS. | Fix the viewport contract first. If the viewport is correct, rebalance the grid/container, widen the content area, or intentionally center the composition. |
| First-viewport-only QA | The cover/hero passes, but lower component, chart, pattern, or governance sections still have bad wrapping, overflow, repeated cards, or broken images. | For long pages/design systems, capture and inspect representative lower-section screenshots. Use section overflow checks, not just page-level `overflowX`. | Add a section sweep to the review: first viewport, component/specimen area, chart/data-viz area, pattern/state area, governance/end area where present. |
| Image aspect or crop mismatch | A hero/product image looks stretched, squeezed, or cropped into a shape that hides the useful content. | Compare displayed image ratio to natural image ratio and inspect `object-fit`. Flag `object-fit: fill` or default stretching with a ratio mismatch; warn on heavy `cover` cropping. | Use the correct asset ratio, set a matching container `aspect-ratio`, or choose `object-fit: contain/cover` deliberately with safe focal positioning. |
| Image overlay collision | Labels, badges, or captions sit on top of useful content inside an image, covering cards, product UI, faces, or readable details. | Check text element rectangles against primary image rectangles, especially absolutely positioned captions inside `figure`/hero/media wrappers. | Move captions outside the image, reserve a non-critical overlay zone, or use a separate legend/control area. |
| Page-type drift | The user asks for a design system, but the artifact becomes a fake app dashboard/workbench; or a dashboard becomes a marketing page. | Before reviewing, write the page type and anti-goals. For design systems, check for principles, foundations, components, patterns, do/don't, and governance. | Rebuild the information architecture around the artifact type; do not merely restyle cards. |
| Live artifact misread as fake app | A live design-system artifact uses buttons, tabs, drawers, charts, or state toggles to demonstrate component behavior, but the reviewer treats all interactivity as page-type drift and strips it back to a dead static page. | Ask whether the interaction is labelled as a specimen, state demo, pattern, or component contract. Check whether it exposes variants, states, chart behavior, responsive behavior, or governance rules. | Keep the interaction when it demonstrates the design system. Add labels, anatomy, states, and usage framing so it cannot be mistaken for a finished workbench. |
| Unframed live artifact | Interactive modules exist, but nothing says what component, pattern, state, or rule they demonstrate. The page feels like a half-built product. | Scan nearby headings and labels for specimen/pattern/component/state/variant/token/anatomy/usage language. Check whether sample data is marked as specimen data. | Convert app-like modules into live specimens: add component names, state labels, usage rules, do/don't notes, and explicit sample-data framing. |
| Unexercised live interaction | Buttons, tabs, drawers, or chart controls are visible, but the review never clicks them. The default state looks acceptable while alternate states overflow, clip, or show stale labels. | In Chrome, exercise at least one representative interaction per live specimen family. Record before/after state and inspect overflow, text wrapping, overlay, and scroll ownership while the state is active. | Treat live artifact review like a small interaction QA pass: click variant/state controls, open/close overlays, hover/select charts when possible, then re-screenshot the changed state. |
| Repeated card pile | Many identical cards/panels appear because the agent translated every idea into a card. The page feels generated rather than designed. | Count repeated card/panel/tile containers and inspect whether they express hierarchy or just duplicate a template. | Use tables, rules, specimens, side notes, bands, and structured lists. Keep cards for repeated items, examples, modals, and genuine component specimens. |
| Repeated global KPI strip | A dashboard repeats the same 3-5 overview metric cards at the top of every subpage, so maps, tables, queues, and detail work all start with irrelevant tiles. | Click every sidebar/tab workspace and compare the first viewport. If the same metric card group appears before unrelated task surfaces, flag it. | Keep global KPI cards on the overview only. Subpages should start with their own task surface or a compact workspace-specific summary. |
| Enterprise admin as instruction manual | A backend page becomes a long waterfall of explanatory cards and prose. It tells users what the system is instead of letting them scan, filter, inspect, and act. | Judge the first two viewports: count prose blocks versus operational surfaces such as table, matrix, map, queue, filters, and row actions. Ask what a returning operator would do first. | Replace explanatory sections with task-first surfaces. Keep help text short, inline, and attached to the control or data it clarifies. |
| Route-state drift | Clicking a tab, workspace, map section, or dashboard page changes the visible content but leaves the URL/hash unchanged, so refresh, back, and shared links lose the current state. | After each navigation click, record `location.href`, then refresh and use browser back/forward. Compare visible active nav and page title to the URL. | Give every real page/workspace a canonical route or hash. Add tests for click -> URL, direct URL -> state, refresh -> state, and back -> previous state. |
| Permanent rail without ownership | A right-side tab/rail/panel permanently consumes a large part of the layout but is not navigation, not a selected-object inspector, and not a dismissible drawer. | Inspect whether the rail changes with selection, can close when not needed, owns its scroll, and helps the current task. If it just stands there with generic content, flag it. | Convert it to real navigation, an on-demand drawer, or a contextual inspector tied to the selected object. Otherwise remove it and return width to the primary canvas. |
| Drawer acting like accidental modal | A row-detail drawer opens with a mask, fixed width, or intercepted clicks even though the user should still navigate, filter, or inspect the table behind it. | Open the drawer and record mask count, pointer-events on the main workspace, close path, drawer width, and mobile `scrollWidth`. Screenshot the open state after animation settles. | Use a true modal only for blocking decisions. Otherwise use a non-modal drawer/inspector, pass width props correctly through wrappers, and verify desktop and mobile open states. |
| Mobile table squeezed into desktop grid | Mobile reports no page overflow, but the table is still a desktop grid: key columns are off-screen, row meaning is lost, or actions require sideways drag. | At 390px, compare the mobile row/card/list against the desktop table's decision fields and row actions. Zero page overflow alone is not enough. | Provide a mobile card/list/table pattern with the same status, identity, key metrics, and action. Hide the desktop table when the mobile pattern owns the workflow. |
| Map/GIS treated as static art | A page looks like a map but lacks basic GIS interaction, or map labels/popovers/panels make provinces, cities, or markers hard to click. | Exercise wheel/button zoom, drag pan, reset/fit, marker/region click, hover, and selection clearing. Measure whether overlays cover the clicked target or neighboring targets. | Add real pan/zoom controls, larger hit targets, clear selected states, non-blocking inspectors, and layer rules for labels/popovers/toolbars. |
| Design-system asset drift | A project has existing tokens, product imagery, logo marks, or component conventions, but the new UI invents a separate look and generic placeholder branding. | Before aesthetic judgment, inspect design-system docs/assets and compare the rendered page's colors, typography, logo, image usage, and component patterns. | Reuse the design system first. Add new visual elements only when they extend the system, and document the rule they add. |
| QA script gaming | A detector flags an issue, then the implementation is changed to avoid the selector rather than fixing the visual problem or detector. | Compare the user's complaint, screenshot, and code change. Renaming `.tag-sample` to avoid a wrapped-control warning is a smell unless the detector logic is also corrected. | Fix the detector if it misclassifies, or fix the layout if it is real. Record the reason. |
| Overlap | Calendar/timeline/event labels collide, or blocks overlap after data changes. | Use viewport screenshots around dense areas and inspect bounding boxes when possible. | Reserve dimensions, use collision-aware layout, reduce competing columns, or stack on small widths. |
| Hidden/clipped content | Screenshot/section/page is not fully visible; fixed-height panels cut off text. | Compare `scrollHeight` vs `clientHeight`; inspect screenshots across viewports. | Remove arbitrary fixed heights or provide intentional scroll area with affordance. |
| Low-value copy causing layout damage | Vague slogans or redundant labels make the page longer while adding no decision value. | Ask whether each visible sentence changes user action or understanding. | Cut vague copy. Replace with object/state/action labels. |
| Generic AI slop | Purple gradients, glow, glass cards, decorative blobs, card grids everywhere, "AI empowers" copy. | Compare against domain references and product purpose. | Use domain-specific visuals, brand tokens, real objects/states, and restrained composition. |
| Card side-rail AI slop | A rounded card or large module uses a 3-4px colored left border or left inset shadow to fake status, hierarchy, or sophistication. | Inspect computed styles for large `card/panel/module/alert/shell` containers with `border-left >= 3px` or `box-shadow: inset Npx 0 0`. Exempt small tags, labels, checkboxes, table selection cells, and motif diagrams. | Move state into small capsules/tags, field-level feedback, table row state, top rules, or real object structure. Do not use card-level left rails as decoration. |
| Screenshot not actually reviewed | Agent claims done after build/lint, but browser view still has obvious line breaks. | Require screenshot paths and a short visual finding summary. | Open and inspect screenshots before final response. |
| Transient UI raced by the capture | A toast/snackbar/auto-dismissing alert lives ~1-3s, so a single screenshot or a late `wait_for` misses it. The agent then reports it "does not fire" or is "broken," when it actually rendered correctly and vanished. | Absence of a capture is not a negative result. Arm a `MutationObserver` (or event capture) on the toast/alert selector before triggering, then read the recorded log. Only an observer that stays empty across repeated triggers proves absence. | Instrument the lifecycle instead of racing it. If the observer proves it fires with the right text, the real defect (if any) is that it is too ephemeral to read, not that it is missing. |
| Actionable error too ephemeral / wrong language | A login or form failure shows a ~3s toast, or a raw English/backend string, to a user who must read and act on it in another language. The user misses it or cannot understand it. | Trigger the failure; check the message language/register against the audience, whether it persists long enough to act, whether `role="alert"` is set, and whether fields needing re-entry were cleared. | Map known errors to human localized copy; use persistent inline placement for actionable failures; clear re-entry fields so the recovered state is legible. |
| Authenticated-but-unauthorized surface leak | A user who signs in but has no role/membership/permission yet sees the same shell, entries, and actions as a privileged user, then dead-ends on every click. Fail-closed exists only at the data layer. | Provision or borrow a genuinely role-less account (fresh test accounts often carry full seed permissions and hide this). Compare its rendered surfaces and entry points against a privileged account. | Render a plain "no access yet / contact your admin" state for role-less users; do not expose privileged entries the data layer will reject. |
| Browser output path untested | The page looks fine in-app, but export/share/print/download buttons are never clicked in the real browser. Unit tests pass while the deliverable people receive is blank, blocked, stale, or unreadable. | For every user-visible output action, click the real control in Chrome or Computer Use and observe the browser-level result: download popover/file, new tab/window, alert, clipboard result, share URL, or print preview. | Treat browser-integrated output paths as UI journeys. Verify the artifact the recipient will open, not only the event handler. |
| Popup or print preview blank | A PDF/print button calls `window.open` or `print`, but Chrome opens `about:blank`, blocks the popup, or shows a print shell with no rendered pages. | Click the visible PDF/print control in a normal Chrome window. Verify `chrome://print/` displays nonblank page previews and page count. A handler/unit test is insufficient. | Use a user-gesture-safe print path, such as a prepared same-page/iframe print flow when appropriate, and re-test in real Chrome. Do not claim a PDF file exists unless it was saved and visually inspected. |
| Standalone export quality drift | The app view is readable, but exported HTML/PDF/share output loses the overview-first structure, fonts, spacing, responsive behavior, or hides the next reading layer behind raw protocol noise. | Open the exported file/share URL/print preview as a recipient would. Compare title, first viewport, overview, structure, raw transcript/audit fallback, and mobile rendering against the in-app quality target. | Generate share/export artifacts from the same rendering contract where possible; preserve the human reading path and verify each artifact directly. |
| Share link not opened | The UI reports "copied" or "share ready," but nobody opens the URL. The link may point to localhost-only state, missing snapshot data, wrong route, or a blank page. | After creating a share, paste/open the copied URL in a normal tab/window, refresh it, and inspect desktop plus mobile-ish rendering when the audience includes phones. | Store a self-contained snapshot or clearly state its local-only scope; ensure the share page is read-only when intended and has the same reading quality as the source. |
| Staged viewport not restored | A mobile or narrow emulation profile remains active after testing, so later reviewers see a phone-sized page inside a desktop window. | End the review by reading `outerWidth`, `innerWidth`, `visualViewport`, and DPR again in the user's Chrome. | Reset to the expected desktop viewport or explicitly report the remaining emulation state. |
| Wrong app surface verified | Desktop/native app task was "verified" by opening only the renderer/dev-server URL; native window, IPC, menus, permissions, shortcuts, or shell state were never exercised. | For Electron/native shells, compare the launched surface to the project launcher SOP: app process/window, renderer, and route must all be true. | Use the canonical app harness; report dev-server URLs only as renderer diagnostics, not as app entry points. |
| Ambiguous trigger ownership | One key/button appears to switch between unrelated modes, or old shortcut copy still tells users to use a retired path. | List each primary trigger and the mode it owns; grep rendered UI for stale shortcut/mode labels. | Give each workflow an explicit entry; make mode switches visible and intentional; remove stale copy from UI and docs. |
| Hidden default-mode escape hatch | User enters an advanced mode, provider, review flow, or settings page and cannot tell how to get back to the normal path. | From every mode under review, try to return to the default path in one obvious action. Inspect settings pages reached from errors/status cards. | Add a visible mode selector or return action; rename settings sections around user goals, not implementation details. |
| Unrecoverable processing | A preparation/transcription/save/upload state can hang while the main input path remains blocked and the user has no return-to-idle action. | In the rendered state, look for progress/current work and an escape path. In tests, force a pending promise and assert recovery. | Add progress or specific current-work copy plus retry/cancel/return-to-idle; ignore stale completions after recovery. |
| Error loses feature context | A multi-mode feature fails, but the global toast/floating control shows a generic error from another feature. | Trigger a failure and compare page card, toast, floating control, and settings state. | Preserve `{feature/mode, state, error}` through the UI boundary and render feature-specific retry/reset actions. |
| Provider/model label drift | Status UI says a vague model family or "preparing" while the selected provider, hardware/runtime path, account/config state, or actual blocker is different. | Compare visible model/provider copy to runtime settings, logs, and status payloads. Require actionable progress or next step. | Display the selected provider/runtime truthfully; map raw stage/error codes to user actions; hide raw local paths unless explicitly diagnostic. |
| Internal artifact language as primary UX | A user-facing or reviewer-facing page says `Export JSON`, `gate`, `case bundle`, `state file`, `acceptance evidence`, or similar internal terms where the user expects a task like finish, save, approve, retry, or correct. | Read visible headings, button labels, status text, browser title, and alerts. Ask whether each term names the user's task or an implementation artifact. | Rename primary surfaces around the human task. Move JSON filenames, commands, logs, and gate details into diagnostics or technical handoff. Add forbidden rendered term checks for retired labels. |
| Raw machine IDs as people | Review, diarization, clustering, annotation, moderation, or tagging UI asks users to choose `cluster 1`, `speaker 2`, `spk1`, `label_3`, or opaque model tokens as the main identity. | Inspect primary chips, dropdowns, cards, legends, and row headers. If the label is only meaningful to the model or database, it is not a primary user label. | Give each entity a human alias first (`Person A`, `Me`, role/name placeholders), let the user rename it, and demote raw IDs to small secondary diagnostic tokens. |
| Default prediction asks for repeated work | The UI separately shows a predicted label and then asks the user to select the same label again, so the default state reads like an unmade choice. | In annotation/review rows, compare the displayed prediction to the selected/active control state. If the predicted option is not visibly selected, the user will think they must click it. | Make machine predictions editable selected defaults. The user should only correct wrong predictions or confirm the current labels at a higher level. |
| Blind labeling before transcript/context | Audio/image/text review asks users to identify segments without first showing the machine transcript, crop, preview, or highest-value context. | Walk the first review item as a tired user. If they must play an entire source or inspect raw IDs before knowing what to label, the workflow is too expensive. | Put the most informative context inline with the review item, auto-play or preview the exact span when useful, and prioritize high-value clips rather than dumping a long queue. |
| Review queue has no humane stop path | A queue implies the user must finish every item, while skip/save-later/finish-current-work is hidden or technically worded. | Start the queue, complete one item, then try to stop. Check whether current progress is saved and the next action is obvious. | Provide visible skip/finish/save controls, persist partial work, and explain what will and will not be reused. Do not turn optional evidence completion into an unbounded chore. |
| Correction does not compound | A user correction is saved only as local UI state or a one-off file, so the same kind of mistake will be asked again later. | After a correction/accept/reject/skip action, inspect whether the UI or code path records reusable supervision, preference, training/eval data, or a guard against asking again. | Persist corrections as first-class feedback where appropriate, auto-apply safe matches, and surface the dividend as fewer future asks rather than more manual queues. |
| Feedback loop stops at chat | User reports a low-level UI miss, the code is fixed, but no test, script, or checklist would catch the same class next time. | For every confirmed visual/journey defect, ask which guard now fails if it regresses. | Add/extend a unit, e2e, visual audit, forbidden rendered term, or checklist item before closing. |
| One-off regression guard | A user-reported issue is patched with a project-specific script tied to one route or selector, so similar defects elsewhere still pass. | Ask whether the guard would catch the same failure in another component/page/domain without renaming selectors. | Convert the lesson into a generic visual audit rule, checklist item, or reusable helper; keep project-specific selectors only as optional examples. |
| Class-name substring false positive | Automated QA treats `stage` as if it were `tag`, or otherwise infers semantics from arbitrary substrings. | Review regexes that match raw class strings with patterns like `tag|tab|nav`; test against words that merely contain those letters. | Match semantic class parts/tokens, roles, and native elements, not arbitrary substrings. |
| Tests assert text but not surface | Unit/E2E tests check that some status text exists, but the actual card/button/entry can be hidden, off-screen, stale, or visually contradictory. | Look for viewport assertions, visible button assertions, forbidden stale copy checks, and state-transition tests. | Assert required surfaces are in viewport, forbidden terms are absent, primary action is clickable/disabled for the right reason, and each state returns to idle. |

## Macro Composition Failures

The patterns above are caught row-by-row; these are whole-page defects a clean micro pass still misses. Judge them from a full-page screenshot, ideally beside the benchmark the user named.

| Pattern | What It Looked Like | Detection Heuristic | Preferred Fix |
|---|---|---|---|
| Overweight hero heading | Main title huge + bold + left-aligned, shouting instead of inviting; it dominates the viewport. | Compare heading size/weight to the benchmark and to body text. | Reduce size and weight, consider centering, and match the benchmark's hierarchy. |
| Unbalanced visual weight | Eyebrow + title + subtitle + input all stacked top-left; the rest of the canvas sits empty. | Whole-page screenshot. Ask where the eye lands and whether weight is centered/intentional or dumped in a corner. | Center or rebalance the composition, narrow the focal column, and balance vertical whitespace. |
| Chrome fights canvas | A near-black sidebar against a warm/light body; the boundary reads as two unrelated apps. | Whole-page screenshot; compare chrome lightness/temperature to the body and to the benchmark. | Align chrome tokens with the benchmark and product surface. |
| Same context repeated | Workspace/project name appears in the top bar, heading, and sidebar. | Read every visible string; flag the same identity stated 3+ times in one viewport. | Say it once where it carries most meaning; drop duplicates. |
| Enterprise chrome copied across all pages | The shell makes every workspace feel like the same overview page: same metric strip, same explanatory lead, same card rhythm, then the actual content appears below the fold. | Compare whole-page screenshots across at least three workspaces. If the primary difference is only nav active state and lower content, the shell is overpowering the task. | Give each workspace a distinct information architecture while sharing tokens and navigation. Overview can summarize; task pages should privilege the work object. |
| Gap to benchmark unmeasured | "Looks better now" declared without putting the after-shot beside the named reference. | Check whether there is an after-vs-benchmark comparison. | Screenshot both, name concrete remaining differences, then close those. |

## Whole-Page-First Rule

Capture and judge the entire rendered page before zooming into any inner container. Macro defects like heading scale, visual balance, chrome color, and redundancy are only visible at whole-page scale. When the user named a product to match, that screenshot is the benchmark; a general aesthetic principle never outranks the specific target.

## Right-State-First Rule

A whole-page screenshot of the wrong conditional branch is a false verification. Compare the shot's `h1`, title, and visible headline to the state the user described. Logged-out, onboarding, no workspace/project, empty data, plan/permission, and feature-flag variants can all render different pages.

## Journey-State Contract

Rendered QA is incomplete until the primary journey has been exercised. For each changed flow, record entry, trigger owner, active state, long-running state, error state, return state, cross-surface consistency, route/addressability, and the regression guard. If any state blocks the main journey with no safe next action, classify it at least P1.

## Browser-Integrated Delivery Flow Rules

When the feature produces something outside the current DOM, review that output as a first-class artifact. Browser chrome is part of the workflow for downloads, share links, clipboard copy, new windows/tabs, file dialogs, and print/PDF preview.

- Prefer the user's visible Chrome window when the failure is about what the user will click. If Computer Use is available, use it to click and observe; if only DevTools/Playwright is available, state the limitation.
- Download/export: verify completion in the browser or filesystem, then open/inspect the downloaded artifact. A successful button click is not enough.
- Share: create the link, open it directly, refresh it, and inspect desktop plus mobile-ish rendering when the link is meant for others. Check that the reader lands on a human-readable page, not raw logs or protocol furniture.
- PDF/print: verify Chrome print preview renders nonblank pages and the expected page count/destination. A blocked popup, `about:blank`, empty preview, or only the first shell page is at least P1.
- Clipboard/new-tab/alert: verify the visible result. For clipboard URLs, paste/open them; for alerts, confirm the message is human-readable and not a raw implementation dump.
- Recipient quality matters. Local HTML, PDF, and share pages should be close to the in-app human-readable view unless the product explicitly says they are technical audit artifacts.
- Do not save a file just to prove the path works if print preview is sufficient for the task; but if you report that a saved file exists, actually save and visually inspect it.

## Mandatory Viewports

Use real browser rendering, not mental simulation.

- Desktop wide: around `1700x1000`.
- Desktop common: around `1440x900`.
- Mobile: around `390x844`.
- If the target is a projection/demo page, also test the intended projection size.

For each viewport record:

- `document.title`
- first `h1`
- `innerWidth` / `innerHeight`
- `outerWidth` / `outerHeight` when using the user's visible Chrome
- `outerWidth - innerWidth` when using the user's visible Chrome
- `visualViewport.width` / `visualViewport.scale` when DevTools emulation may be active
- `documentElement.scrollWidth - clientWidth`
- first viewport content `leftBlank` / `rightBlank` / width ratio
- primary image load status
- primary image displayed ratio / natural ratio / object-fit
- text overlays that intersect important image content
- typography evidence: font family, key text sizes, line heights, sidebar/rail width, repeated text-column width, smallest important text size
- screenshot path
- browser-output evidence when relevant: completed download filename/size, opened export/share URL, print preview page count, nonblank preview status, and whether mobile-ish rendering was checked
- route evidence for navigable apps: initial URL, URL after each workspace/tab click, direct deep-link reload result, and browser back/forward result
- overlay evidence when a drawer/modal/inspector is part of the journey: mask count, close path, pointer-events on main workspace, drawer width, and mobile scroll width
- lower-section screenshot paths when the page is long, a design system, or a live artifact

## Text And Line-Break Rules

- Chinese headings must not end with a final line of one or two characters.
- High-visibility Chinese copy should not split common semantic two-character words across line boundaries, such as `这|里`, `这|个`, `我|们`, or `不|是`.
- Domain terms should stay intact: product names, module names, dates, city/dealer names, labels.
- Two- or three-character final lines in ordinary body text are not automatically defects. Flag them only when they are high visibility, split a semantic unit, occur repeatedly in the same component pattern, or reveal a too-narrow container.
- Buttons/tags/nav labels should not wrap unless the control is explicitly designed for two lines.
- Do not globally shrink font size to solve line breaks.
- Do not hide overflow to suppress evidence.
- Prefer rewriting content over forcing narrow containers to accept long text.
- Treat product names, labels, dates, and domain phrases as semantic units. If a semantic unit breaks badly, fix the content or layout instead of accepting the browser's default wrap.

## Layout Rules

- Do not put every concept into identical cards.
- Do not put cards inside cards unless it is a modal or repeated item structure.
- Do not reduce "avoid cards" to "no cards anywhere." The question is whether the card has a job.
- Do not reuse an overview metric strip as page furniture. If the metric does not help the current workspace act, remove it or move it to overview.
- Preserve clear primary/secondary hierarchy.
- Give repeated fixed-format elements stable dimensions.
- For sibling fields or repeated component specimens, define a common anatomy: label row, control row, helper/error row, action row. If one sibling lacks content in a row, reserve the slot or change the layout.
- Same visual row means same axes. Compare top/bottom/height values for labels, controls, helper/error text, and card bodies; do not accept "close enough" when the mismatch is visible.
- A panel that scrolls must visibly own its scroll; the page must not hijack panel scrolling.
- Sticky/floating controls must not cover content.
- Persistent rails must have a named role: navigation, selected-object inspector, utility panel, or dismissible drawer. A generic rail that permanently narrows the main canvas is layout debt.
- A detail drawer that is not meant to block work should not create a visible or hit-test mask over the main workspace.
- Mobile data views must preserve the row's identity, status, decision metrics, and action. A hidden desktop table plus a real mobile list/card pattern is usually better than a squeezed admin table.
- A wide desktop first viewport should not accidentally underfill one side. If there is a large blank area, classify whether it comes from viewport emulation, intentional max-width centering, or broken grid/container sizing.
- Section containers must not have their own accidental horizontal overflow even when the whole document reports `overflowX=0`.
- Font size, line height, spacing, and column width must be judged together. A readable font can still fail if the column is too narrow, and a wide layout can still fail if the type scale is too small for the artifact.

## Design-System Artifact Rules

When the page is a design system, review it as a design system, not as an app screen.

- It should explain why the system exists, what it governs, and what it excludes.
- It should contain foundations, component anatomy, variants, states, usage guidance, do/don't examples, responsive rules, and governance.
- Component examples may use cards or panels, but the page's information architecture should not be a pile of business cards.
- Fake data is acceptable only as a specimen. It must not make the page read like a real dashboard.
- Business strategy, competitor notes, or roadmap context belong in supporting docs unless the design-system page explicitly frames them as product principles.
- If the artifact lacks a do/don't section or state/variant rules, it is probably a showcase page, not a design system.

## Live Artifact Design-System Rules

Some projects intentionally ship the design system as a live artifact: a rendered, interactive page that lets reviewers test components and patterns directly. Do not downgrade it into a static documentation page.

- Interactivity is allowed when it demonstrates design-system behavior: variants, states, token application, chart tooltip/selection, drawer/modal behavior, responsive collapse, empty/error/loading cases, or governance rules.
- A live specimen must name what is being demonstrated. Nearby text should make the unit legible as a component, pattern, state demo, chart contract, shell specimen, or responsive rule.
- Controls should feel like test harnesses for the design system, not unfinished business actions. If a button says "open case" or "assign lead," the surrounding frame must explain the component state or pattern being tested.
- Sample business data must be visibly framed as specimen data. Otherwise the artifact will read as a fake workbench.
- Do not remove useful live specimens just because they resemble product UI. Fix the framing first: add anatomy, variant/state labels, usage guidance, and do/don't examples.
- Fail the artifact when interaction changes content without revealing a design rule. A live artifact earns its interactivity by making a rule testable.
- Click representative controls during review. A live artifact is not verified until at least one changed state has been inspected for overflow, clipping, image/text collision, and scroll ownership.

## Enterprise Admin / Dashboard Rules

For enterprise backends, judge whether the screen supports repeated operational use. Returning users should be able to scan status, filter data, inspect exceptions, and act without reading a page-length explanation.

- The primary surface should be a table, matrix, map, queue, timeline, form, or inspector tied to a real workflow.
- Overview pages may summarize with KPI cards; subpages should not inherit those cards unless the numbers directly drive that subpage's action.
- Top copy should identify the current workspace and state, not explain the whole product. If a paragraph reads like sales collateral or onboarding, cut or move it.
- Sidebar or tab navigation should update the active route. Refresh and direct links must restore the same workspace.
- Detail panels should appear because something is selected or invoked. Always-visible generic panels are suspect.
- Data-boundary copy is useful, but it should usually be a terse chip, column label, status tag, or inline note attached to the relevant data. If it becomes a paragraph stack, the backend is turning into a manual.
- A dashboard that requires scrolling past explanation cards before reaching the table/map/queue is failing the admin-console page type.

## Drawer / Inspector Rules

Drawers and inspectors are useful when they clarify the selected object. They are harmful when they permanently occupy layout width or accidentally inherit modal behavior.

- Default state: no selected object should mean no large generic detail rail.
- Selected state: the panel title should name the selected object and the body should show actions/evidence for that object.
- Blocking is a product decision. If the user should keep scanning the table/map behind the drawer, verify `mask=false` behavior, background pointer events, and navigation clicks.
- Width must be rendered, not assumed from wrapper props. Inspect the actual drawer content rectangle on desktop and mobile.
- Mobile open state needs its own screenshot. Check `documentElement.scrollWidth - clientWidth`, drawer width, close path, and whether the first meaningful action is reachable.

## Map / GIS Rules

For GIS or map-like workspaces, review the map as an interactive control, not as a background image.

- Verify zoom in/out, drag pan, reset/fit, marker/region click, hover/selected states, and clear-selection behavior.
- Hit targets must be large enough for dense regions; labels, popovers, and markers must not stack into an unclickable knot.
- Toolbars, legends, drawers, and inspectors must not cover the geography the user just clicked or the nearby targets they are likely to click next.
- Selection should coordinate with adjacent tables or inspectors without trapping the user in a modal or permanent panel.
- If a map view exists as a sidebar tab or workspace, its route must be addressable like any other real page.

## Aesthetic Rules

- First viewport must communicate the actual domain/product, not just generic SaaS competence.
- Visual assets should reveal the product, place, object, gameplay, or state being discussed.
- Avoid default AI visual tropes: purple/blue gradients, glassmorphism, floating orbs, excessive glow, decorative dashboards with fake data.
- Watch for accidental brand collision: a decorative motif that reproduces another famous brand's signature (four equal hard-edged primary blocks reading as Google's bar, a swoosh/ring reading as a competitor logo) looks off-brand and unprofessional. It stands out most on a lone hero element. Anchor such motifs in the product's own brand color and soften hard equal-weight divisions.
- Avoid card-level colored left rails on rounded cards and panels. Small vertical capsules in tags/labels can be deliberate; scaled-up left bars on containers usually read as generated UI.
- If a page belongs to a brand or industry, check official materials or reference images before choosing style.
- If a project already has a design system, logo, or approved imagery, use that as the first source of visual truth before generating a new mark or image language.

## How This Differs From Existing Skills

- `ui-designer` extracts visual systems from reference images.
- `frontend-design` guides distinctive implementation.
- `qa-expert` sets up broad QA processes and bug tracking.
- This checklist catches rendered visual defects after the UI exists.
