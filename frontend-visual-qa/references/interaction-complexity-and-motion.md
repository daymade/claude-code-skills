# Interaction Complexity, State-Transition Motion, and Adversarial Boundary Checks

Load this reference when auditing or refining interactive web apps, workbenches,
or dashboards for UX complexity elimination, motion craft, responsive/theme
resilience, or undo/bulk state safety. Keep complexity inside the system; never
push state-machine edge cases onto the user.

## 1. UX Complexity-Elimination Checks (8 Axes)

**Pre-polish core-loop gate:** Before auditing or polishing micro-interactions,
visual chrome, or motion, exercise one end-to-end primary user journey (cold
start -> core input/upload/submit -> page reload & session/context switch ->
error recovery). Never treat 120 FPS animations or clean component polish as a
pass while a primary workflow drops user input, streams raw machine payloads
into user-facing text, or loses/corrupts state across reloads or context
switches.

Verify each axis against the live rendered surface, not source intent:

1. **System-decidable state stays automatic.** Do not force users to triage
   informational/no-action rows (`needs_ack=false`), decode machine IDs, or
   manually group duplicate repeats when one shared predicate can filter and
   aggregate them by default. Use the exact same pending predicate across KPIs,
   lists, and bulk actions.
2. **Hide controls that have no job right now.** Collapse raw IDs, technical
   metadata, empty zero-count filters, and secondary forms behind disclosures;
   on narrow mobile screens (`<=640px`), keep non-actionable summary cards from
   pushing the first actionable item below the opening viewport.
3. **Act on obvious follow-ups.** Offer contextual next actions where the user's
   eyes already are (for example, pairing a noise dismissal with a rule-downgrade
   action in the undo toast), without silently overwriting explicit manual
   overrides during bulk-adopt actions.
4. **One concept, one label everywhere.** Statuses, tiers, and channels must use
   the same vocabulary across list rows, inspectors, filters, charts, toasts,
   and exported artifacts.
5. **Immediate response and safe reversal.** Every state mutation should confirm
   in place without scroll jump, support toggle-back when re-clicking an active
   choice, and provide a reversible Undo path. Undo must be conflict-safe
   (version/timestamp checked on server-backed actions so it never overwrites a
   newer decision) and **scope-composable on client workspaces** (revert only
   the cleared slice/delta—never restore a whole-page snapshot that silently
   wipes edits the user made in another dimension after clearing). Keep failed
   undo entries available for retry rather than popping before success.
6. **Never interrupt active work.** Replace blocking `window.confirm()` dialogs
   with inline confirmation, let users inspect individual items inside a group
   without forcing a jump to a capped raw view, sequence async refreshes so late
   responses cannot overwrite newer state, preserve unsaved drafts and open
   disclosures across re-renders, and only advance selection if the originating
   item still owns focus. Keep triggering buttons mounted across loading, error,
   and success states (attach error-shake animations to an inner `<span>` rather
   than remounting the `<button>`, which drops keyboard focus), and bind async
   confirmations (such as clipboard copies or background fetches) to a monotonic
   request or session token so a late promise cannot mislabel a newer URL or
   session.
7. **Easy frequent actions, hard-to-mishit bulk/destructive actions.** Keep
   frequent single-item actions reachable by hover/focus and keyboard; guard
   bulk actions with a two-step inline arming flow that **freezes the exact
   target ID set at arming time** and auto-disarms on any filter, search, tab,
   or `Escape` change. When clearing a configuration or credential that drives a
   live runtime (such as microphone capture or an active stream), stop the live
   runtime and return to the safe default mode as part of the two-step clear,
   and read entitlement-dependent badges or post-clear notices reactively rather
   than from a one-time mount snapshot. Hidden hover actions (`opacity: 0`) must
   set `pointer-events: none` until revealed.
8. **Self-explaining UI and honest group state.** Represent mixed statuses inside
   aggregated groups explicitly instead of letting the lead record speak for all
   members; preserve per-record notes when a group action does not deliberately
   edit the note; never compute savings/forecasts by subtracting a partial sample
   from a larger window total.

## 2. State-Transition Motion Standards

Audit motion by **state transitions** (appear, disappear, move, resize, content
swap, icon/number change, press, hover, load, complete, error) rather than by
widget catalog:

- **One unified motion language.** Share timing and easing tokens across the
  surface (snappy micro-feedback, spring-out reveals, fast exits). Repeat
  actions must stay quieter and faster than first-time reveals (for example,
  animate chart fills once on first visit rather than replaying on every tab
  switch; animate inspector swaps only when selection identity actually changes).
- **Pure GPU compositing (`transform` / `opacity` only).** Avoid layout-thrashing
  properties in transitions:
  - Segmented/tab thumbs: animate `translate3d(...) scaleX(...)`, never `width`.
  - Disclosures/accordions: toggle `hidden` + `inert` with subtle `opacity` /
    `translate3d` entry instead of animating `grid-template-rows` or `height`.
  - Avoid synchronous forced-reflow loops (`offsetWidth` reads inside per-node
    animation resets).
  - **Tailwind v4 individual transform properties:** Utilities such as
    `translate-*`, `scale-*`, and `rotate-*` compile to standalone CSS
    properties rather than `transform`. While Tailwind v4's built-in
    `transition-transform` includes `transform, translate, scale, rotate`,
    pairing those utilities with custom CSS `transition-property: transform` or
    arbitrary lists like `transition-[opacity,transform]` silently drops
    interpolation (abrupt snap with zero errors), and custom
    `prefers-reduced-motion` rules that only cover `transform` can miss them.
    Include the explicit standalone property (`transition-[translate,transform]`,
    `transition-[scale,transform]`, `transition-[rotate,transform]`) whenever
    authoring custom property lists, and verify computed interpolation.
- **Reversible exits, mid-exit reversal, and snapshot retention.** Presence
  hooks must distinguish a fresh mount (staging across 2 `requestAnimationFrame`
  frames from the hidden pose) from a rapid mid-exit reopen (reversing
  immediately without a 2-frame dip). While an exit transition plays, retain the
  last valid payload snapshot (error banner text, lightbox image, progress
  readout) so the surface does not flash blank mid-fade, apply `inert` to block
  stray clicks, and cancel any active drag immediately when closing.
- **Isolate transient animation state from durable document state.** When a
  canvas or scene engine animates live element properties (`opacity`,
  `width`/`height`, draw `points`), never persist intermediate animation values
  into saved checkpoints or exports. Every exit path (pause, close, jump, reset,
  share/export) must reconcile concurrent user edits first and strip unsettled
  transient animation attributes before writing or sharing.
- **Direct manipulation and mid-flight interruptibility.** Resizable splitters
  must track pointer capture 1:1 with double-click reset and pixel clamping so a
  persisted split percentage cannot overflow narrower desktop viewports. Numeric
  roll animations must cancel prior `requestAnimationFrame` handles and start
  from the live interpolated value, never snapping back to the previous endpoint.
  For interruptible WAAPI transforms (such as zoom/pan cameras), sample the live
  `getComputedStyle(el).transform` matrix before cancelling the previous
  animation, guard `onfinish`/`oncancel` with an animation-instance identity
  check, and convert SVG pointer coordinates through `getScreenCTM().inverse()`
  so drags stay 1:1 without drift. For animated `<dialog>` exits, guard the
  delayed `.close()` call with a monotonic opening sequence token (`openSeq`) so
  rapid `Escape` + reopen cannot be closed by a stale exit timer.
- **Avoid global scroll, SVG hit-box, and theme-paint traps.**
  - Do not set `html { scroll-behavior: smooth; }` globally: it delays browser
    back-button scroll restoration and causes programmatic click/popup races on
    long pages. Scope smooth scrolling strictly to explicit user clicks on
    same-page `#hash` anchors (respecting `prefers-reduced-motion`).
  - Keep inactive SVG `<text>` labels at `display: none` (revealing via
    `@keyframes` on activation) rather than `opacity: 0`: invisible `<text>`
    still inflates the parent `<g>` bounding box and intercepts pointer clicks
    on neighboring nodes.
  - Avoid global `transition: color, background-color` on theme switches (which
    thrashes paint across the full DOM); use an instant palette swap paired with
    a composited toggle-icon transition.
- **Strict `prefers-reduced-motion: reduce`.** Collapse transition/animation
  durations **and delays** (`animation-delay: 0ms`, `transition-delay: 0ms`),
  include `::backdrop` in the selector list (native `<dialog>` backdrops are not
  matched by `*`), and replace animated countdown bars (which otherwise vanish
  in `0.01ms` while Undo is still live) with a static Undo affordance.

## 3. Adversarial Boundary Matrix (Run Before Sign-Off)

Self-authored E2E scripts tend to test the author's happy path. Pair them with a
fresh-context independent pass (or cross-model review) targeting these concrete
failure traps:

| Surface | Failure trap to probe | Pass condition |
|---|---|---|
| Hidden hover controls | `opacity: 0` buttons still accept stray clicks | Computed `pointer-events: none` until hovered/selected/focused |
| Overlays & modals | Focus lands inside closed dialogs, collapsed forms, or offscreen mobile sheets; background shortcuts still fire | Closed/offscreen regions carry `inert`; open dialogs/sheets move focus inside, trap background with `inert`, and restore focus on close |
| Breakpoint transitions | Resize `900 -> 1440 -> 900` after opening a sheet and switching tabs | Sheet and backdrop close cleanly on breakpoint/tab changes; zero orphaned overlays |
| Persisted split layouts | Saved `72%` left pane opened at `1050px` viewport | JS clamps split width by available min left/right pixels (`scrollWidth <= innerWidth`) |
| Mobile ergonomics (`390px`) | Tiny `24px` action chips or wide policy tables forcing horizontal scroll | Action touch targets `>=36px` tall; dense tables stack into cards with zero horizontal overflow |
| Extreme viewports (`320px` & `1024×500`) | Horizontal overflow on `320px` mini-phone widths (especially single-column `grid-template-columns: 1fr` + CJK `word-break: keep-all`), or sticky headers/drawers clipping primary controls on short landscape viewports (`500px` tall) | Use `minmax(0, 1fr)` with `overflow-wrap: break-word` on mobile grids; measure overflow with `scrollWidth - clientWidth` (not `window.innerWidth`, which includes reserved `scrollbar-gutter: stable` tracks) so `scrollWidth <= clientWidth` at `320px`; at `1024×500` with the relevant drawer or sticky header open, the intended content region scrolls and the primary control activates cleanly |
| Fixed-width dialogs & lengthened copy | Replacing short upstream copy inside a fixed-width onboarding/modal window whose grid omits `grid-template-columns: minmax(0, 1fr)` or keeps `white-space: nowrap` inflates the implicit track and clips primary CTAs off the right edge | Assert `scrollWidth <= innerWidth` and `left >= 0 && right <= innerWidth` on every visible button in both default and localized (e.g. CJK) runs; constrain the grid with `minmax(0, 1fr)` and allow `white-space: normal` / `text-wrap: balance` |
| Lazy-loaded route CSS cascade | Async route CSS chunks (e.g., `React.lazy()` code-split routes) can append later in the production cascade and silently override shared component rules only after visiting that route | In the production build, compare the shared component's computed styles on cold entry against after visiting the lazy route and returning; scope chunk rules so computed styles stay unchanged |
| MPA cross-route shared-component CSS | Reusing a control class (such as a copy-link or state-toggle button) in a second MPA/Astro template whose layout does not import the original page's stylesheet leaves state rules missing (for example, rendering both idle and active icons simultaneously) | Visually inspect screenshots on every consuming route template and move shared control state rules into the shared base stylesheet |
| Mobile in-flow disclosure dismissal | Collapsing an in-flow mobile disclosure/drawer on outside `pointerdown` reflows the document before `click` fires, swallowing the user's first tap below; global outside-close listeners can also fire during an active modal | A real first tap on an outside control activates it once and closes the disclosure (for example, by dismissing on bubble-phase `click`), while interacting inside an active modal (`dialog:modal` or the app's modal owner) leaves the disclosure unchanged |
| Light/dark contrast & dark-theme parity | Low-contrast primary buttons (`<4.5:1`), unreadable dark caution/warning tokens, or manual `:root[data-theme="dark"]` drifting from OS `@media (prefers-color-scheme: dark)` | Primary buttons and status/caution cues meet WCAG AA in both light and dark themes (`>=4.5:1` normal text, `>=3:1` qualifying large text, `>=3:1` against adjacent colors for essential UI control/state cues), and resolved dark token values match between manual dark (on OS light) and OS dark (with app override cleared) |
| Tailwind v4 individual transforms | `translate-*`, `scale-*`, or `rotate-*` paired with custom CSS `transition: transform` or arbitrary `transition-[...,transform]` snaps abruptly or bypasses `transform`-only `prefers-reduced-motion` rules | Computed `transition-property` includes the standalone property (`translate`/`scale`/`rotate`), interpolation runs smoothly, and `prefers-reduced-motion: reduce` collapses it |
| Session switches & async feedback | Switching sessions/URLs flashes prior-session suggestions or loading indicators on the first render, a late clipboard/fetch promise mislabels the new target, or error-shake remounts `<button>` and drops focus | Session-scoped state hides prior items on the first render; async callbacks verify a monotonic request/session token; triggering buttons remain mounted and keep focus on error |
| In-flight animation + concurrent edits | Dragging or deleting an element mid-fade/scale/draw then clicking Pause, Close, or Share writes intermediate `opacity`, `width`, or `points` into saved state or share links | Every exit path reconciles concurrent user edits and strips unsettled transient animation attributes before checkpointing or exporting |
| Frame smoothness | Jank during tab switch or list scroll | Measured `requestAnimationFrame` deltas stay smooth (target median `<=20ms`, P95 `<=33ms`) with zero console/page errors |
