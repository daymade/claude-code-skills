# Interaction Complexity, State-Transition Motion, and Adversarial Boundary Checks

Load this reference when auditing or refining interactive web apps, workbenches,
or dashboards for UX complexity elimination, motion craft, responsive/theme
resilience, or undo/bulk state safety. Keep complexity inside the system; never
push state-machine edge cases onto the user.

## 1. UX Complexity-Elimination Checks (8 Axes)

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
   (version/timestamp checked so it never overwrites a newer decision) and keep
   failed undo entries available for retry rather than popping before success.
6. **Never interrupt active work.** Replace blocking `window.confirm()` dialogs
   with inline confirmation, let users inspect individual items inside a group
   without forcing a jump to a capped raw view, sequence async refreshes so late
   responses cannot overwrite newer state, preserve unsaved drafts and open
   disclosures across re-renders, and only advance selection if the originating
   item still owns focus.
7. **Easy frequent actions, hard-to-mishit bulk/destructive actions.** Keep
   frequent single-item actions reachable by hover/focus and keyboard; guard
   bulk actions with a two-step inline arming flow that **freezes the exact
   target ID set at arming time** and auto-disarms on any filter, search, tab,
   or `Escape` change. Hidden hover actions (`opacity: 0`) must set
   `pointer-events: none` until revealed.
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
- **Direct manipulation and mid-flight interruptibility.** Resizable splitters
  must track pointer capture 1:1 with double-click reset and pixel clamping so a
  persisted split percentage cannot overflow narrower desktop viewports. Numeric
  roll animations must cancel prior `requestAnimationFrame` handles and start
  from the live interpolated value, never snapping back to the previous endpoint.
- **Strict `prefers-reduced-motion: reduce`.** Collapse transition/animation
  durations and replace animated countdown bars (which otherwise vanish in
  `0.01ms` while Undo is still live) with a static Undo affordance.

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
| Dark-mode contrast | White text on bright blue primary buttons (`<3:1`) | Primary buttons meet WCAG AA (`>=4.5:1`) in both light and dark themes |
| Frame smoothness | Jank during tab switch or list scroll | Measured `requestAnimationFrame` deltas stay smooth (target median `<=20ms`, P95 `<=33ms`) with zero console/page errors |
