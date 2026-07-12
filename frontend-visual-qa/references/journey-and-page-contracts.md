# Journey, Browser-Output, And Page-Type Contracts

Load this reference only when the audit includes state transitions, routes,
overlays, browser-owned output, native shells, complex page types, maps, or
review/annotation workflows.

## Contents

- Evidence Boundary
- Journey And State Matrix
- Authorization, Mode, And Runtime Truth
- Route And Addressability
- Transient UI
- Drawers, Modals, Popovers, And Focus
- Browser-Integrated Outputs
- Electron And Native Shells
- Landing, Deck, And Browser Tool/Game Artifacts
- Dashboard And Enterprise Admin
- Design-System Artifacts
- Map And GIS Workbenches
- Review And Annotation Tools

## Evidence Boundary

Use the visible surface that owns the behavior.

- Use real browser or native GUI evidence for browser chrome, downloads,
  clipboard, popup blocking, print preview, permissions, drag regions, and
  native-window interactions.
- Use same-state DevTools or project E2E for routes, DOM geometry, focus order,
  overlays, and repeatable interaction states.
- Use fresh headless runs only as mechanical diagnostics. They cannot prove an
  authenticated, seeded, or native state unless the project harness reproduces
  that state.
- Mark unavailable GUI-owned checks unverified. Do not silently substitute a
  handler call, source inspection, or headless click.

Keep authentication state inside the project's fixture, storage-state, or test
harness. Do not load a user's personal browser profile into the bundled script.

## Journey And State Matrix

Write the affected transition before clicking:

    entry -> ready -> active -> processing -> success/error -> recovery -> ready

For each relevant state, verify:

- the visible trigger has one clear owner;
- the state name and current work are understandable;
- global, floating, and page-local surfaces agree;
- long-running work exposes progress or a safe escape;
- error copy preserves feature context and gives the next safe action;
- retry/cancel/recovery returns to a usable state;
- stale async completion cannot overwrite a newer state;
- advanced modes show a one-step path back to the default workflow.

Do not require every possible state for a local visual-only change. Cover the
states affected by the implementation or explicitly requested by the user.

Treat these as Major unless the project taxonomy says otherwise:

- a primary action blocks indefinitely with no recovery;
- success is shown when the operation failed or produced the wrong artifact;
- the UI returns to an unrelated feature or mode after error;
- a user can enter an advanced mode but cannot identify or leave it.

Before closing a nontrivial journey audit, repeat the main path without
developer context and ask what a tired or first-time user will misunderstand
first. Check trigger ownership, return-to-default, recovery, runtime truth,
internal language, manual burden, and which regression guard catches the miss.

## Authorization, Mode, And Runtime Truth

Apply these checks only when authorization, modes, providers, or runtime status
are affected, or when the user requests a broad gate.

- Test signed-in-but-unauthorized separately from logged-out and privileged.
  Use a genuinely role-less, membership-less, tenant-less, or permission-less
  fixture/account; seeded admin accounts often hide this branch.
- A rejected data request does not prove the UI fails closed. An unauthorized
  user must not receive the privileged shell, entries, and actions only to hit a
  dead end on every click. Show a plain actionable no-access/request-access or
  contact-admin surface instead.
- List mutually exclusive modes and the owner of each trigger. The same key,
  button, or gesture must not silently mean unrelated actions unless the current
  mode is unmistakable, switching is explicit, and default recovery is one step.
- Compare visible provider, model, hardware/runtime, progress, and blocker copy
  with the authoritative selected configuration plus current status payload or
  logs. A label cannot verify itself. After switching, stale async completion
  must not overwrite the newer path.
- Keep raw paths, stage codes, and machine identifiers in diagnostics. User
  status should say what is actually selected, what is happening, and the next
  safe action.

## Route And Addressability

For every real page, tab, workspace, or map view under review:

1. Record the initial URL and visible active item.
2. Click the navigation control.
3. Confirm both the visible workspace and URL/hash changed coherently.
4. Refresh and confirm the same workspace returns.
5. Open the URL directly in a new tab or clean test context.
6. Use browser back and forward and verify the visible state follows.

Do not demand a route for a deliberately temporary component-state demo.
Document that contract instead. A visible product workspace that cannot survive
refresh or deep linking is route-state drift.

## Transient UI

A late screenshot cannot prove a toast, snackbar, inline validation message, or
short animation never appeared. Arm observation before the trigger:

    () => {
      window.__visualQaTransient = [];
      const selector =
        '[role="alert"], .toast, .snackbar, .notification, [class*="toast"]';
      const record = () => {
        document.querySelectorAll(selector).forEach((element) => {
          const text = element.textContent?.replace(/\s+/g, " ").trim();
          if (text && !window.__visualQaTransient.includes(text)) {
            window.__visualQaTransient.push(text);
          }
        });
      };
      record();
      new MutationObserver(record).observe(document.body, {
        childList: true,
        subtree: true,
      });
      return "observer armed";
    }

Trigger the action repeatedly, then read window.__visualQaTransient.

Separate four outcomes:

- nothing appeared — handler/event path may be broken;
- the expected message appeared and persisted — behavior verified;
- the expected message appeared but vanished too quickly — persistence defect;
- a raw, wrong-language, or contextless message appeared — copy/mapping defect.

For actionable failures, prefer persistent inline placement or a notification
that remains long enough to act. Check role=alert, focus behavior, localization,
and whether fields requiring re-entry return to a legible state.

## Drawers, Modals, Popovers, And Focus

Decide whether the overlay is blocking before reviewing it.

For non-modal inspectors:

- keep the primary workspace usable;
- avoid a hit-test mask;
- tie the panel to a selected object;
- provide a clear close path;
- give the panel one explicit scroll owner.

For modal decisions:

- trap focus intentionally;
- expose a visible title and close/cancel path;
- restore focus to the trigger;
- prevent background action intentionally rather than accidentally.

For every relevant overlay, record:

- trigger and selected object;
- rendered width and viewport;
- mask count and background pointer behavior;
- initial focus, keyboard traversal, Escape behavior, and restored focus;
- page and panel scroll width/height;
- mobile open-state screenshot.

Use rendered geometry, not wrapper props, as evidence. Sticky headers, footers,
notifications, and non-modal dialogs must not entirely hide focused controls.

## Browser-Integrated Outputs

Review the recipient artifact, not only the event handler.
Unless the product explicitly promises a technical audit artifact, the exported
HTML, PDF, or share page should preserve a human-readable path comparable to the
in-app view.

### Download Or Export

1. Click the visible control through the user gesture.
2. Confirm the browser reports completion or the expected file appears.
3. Record the final filename, type, and nonzero size.
4. Open the file and inspect its first viewport plus representative later pages
   or sections.
5. Compare the recipient reading path with the in-app artifact.

### Share

1. Create or copy the share URL through the visible control.
2. Paste/open the actual URL.
3. Refresh it and verify its route/state is self-contained as promised.
4. Confirm read-only versus editable behavior.
5. Inspect the recipient desktop and relevant mobile rendering.

### Print Or PDF

1. Click the real print/PDF control in visible Chrome.
2. Confirm Chrome print preview opens rather than about:blank or a blocked popup.
3. Confirm the preview contains nonblank pages and an expected page count.
4. Check page breaks, clipped content, repeated headers/footers, and orientation.
5. Do not claim a saved PDF exists unless it was actually saved and inspected.

### Clipboard, Popup, Or New Tab

Verify the visible result. Paste and open copied URLs or text. Confirm the popup
or tab has the intended URL, content, title, and recovery/close path.

### File Picker Or Browser Dialog

Open the real picker/dialog from the visible trigger. Verify the accepted file
types, single/multiple/directory contract, cancel recovery, and—using a safe
project fixture—the selected-file state the app renders. Playwright
`setInputFiles` or direct input assignment can verify post-selection app logic;
it cannot prove the OS/browser dialog, its filters, or cancel path.

## Electron And Native Shells

Use the project's canonical app harness. A renderer dev-server URL proves only
that the renderer can load.

Verify:

- the app process and real window exist;
- the intended renderer route is visible inside that window;
- title bar, traffic-light/safe areas, drag and non-drag regions work;
- menus, permissions, global shortcuts, IPC-backed controls, and overlays are
  exercised where affected;
- window resize, compact state, and sidebar collapse preserve controls;
- native dialogs or settings links open from the real app;
- the app returns to a usable state after cancel, denial, or error.

Do not report a native-shell pass from DOM screenshots alone.

## Landing, Deck, And Browser Tool/Game Artifacts

Use the artifact's real job rather than dashboard conventions.

- A landing page is not an internal dashboard. Do not import KPI strips,
  persistent work rails, or admin-shell density unless the landing job requires
  them.
- Landing pages should make the value, identity, and primary action legible
  before decorative depth, and preserve that path on the intended phone width.
- HTML decks/slides must be inspected page by page at the exact projection or
  delivery canvas; a clean first slide or a 1440 desktop screenshot cannot prove
  a 1920 by 1080 presentation.
- Browser tools/games should privilege the primary interaction, controls, HUD,
  or work surface over marketing explanation. Exercise the affected state and
  recovery at the intended play/tool viewport.

## Dashboard And Enterprise Admin

Judge repeated operational use, not marketing polish.

Expected:

- a task-first table, matrix, queue, map, form, timeline, or inspector;
- compact filters and actions near the data they affect;
- overview metrics only where they help triage;
- addressable workspaces;
- details invoked by selection rather than a permanent generic rail;
- one intentional scroll owner per region;
- mobile alternatives preserving identity, status, decision fields, and action.
- charts and KPI views that expose units, data source/provenance, selected time
  range, and distinct loading, empty, permission, and error states.
- data-boundary or constraint copy attached to the affected data as a terse chip,
  column label, status tag, or inline note rather than a paragraph wall.

Flag:

- explanatory card waterfalls before the work surface;
- the same KPI strip copied onto every workspace;
- navigation that changes content but not addressable state;
- a generic permanent side rail that steals canvas width;
- a desktop table merely squeezed into a phone viewport;
- a drawer that blocks unrelated work by accident.

## Design-System Artifacts

First distinguish a static reference from a live artifact.

A static reference should expose scope, current version/artifact status when
claimed, principles, foundations/tokens, component anatomy, variants, states,
usage, do/don't, responsive behavior, accessibility, and governance. Include
motion, content, and data-visualization rules when they are in scope.

A live artifact may use tabs, drawers, forms, charts, or filters when each
interaction is framed as a specimen, pattern, state demo, or component contract.
Exercise at least one representative interaction per affected specimen family.

Flag:

- a specification that reads like a fake product dashboard;
- a live artifact stripped of useful interactivity;
- interactive modules with no specimen/state/usage framing;
- sample data presented as if the production workbench were complete;
- repeated cards replacing anatomy, rules, and comparison.

Do not apply a generic anti-card rule. Cards are legitimate for component
specimens, repeated items, and modal surfaces when they have a clear job.

## Map And GIS Workbenches

Treat the map as an interactive control, not a decorative image.

Verify:

- zoom in/out, wheel or gesture zoom, pan, reset/fit, and clear selection;
- marker/region hit targets and spacing at dense locations;
- hover, selected, focused, and disabled states;
- labels, legends, toolbars, popovers, and inspectors do not cover the clicked
  geography or nearby next targets;
- selection coordinates with adjacent table/inspector state;
- mobile drawer geometry and close/recovery behavior;
- route/deep-link behavior when the map is a real workspace.

Use a real device when gesture, performance, or device-specific map behavior is
material. Chrome Device Mode is only an approximation.

## Review And Annotation Tools

Review tools are user workflows even when they began as internal diagnostics.
Apply product standards to temporary scaffolds that may become lasting
infrastructure; “internal for now” does not excuse hostile defaults or raw
machine language.

Verify:

- primary labels use human nouns rather than raw clusters, IDs, JSON, or gate
  terminology;
- machine predictions appear as editable defaults, not work the user must repeat;
- the highest-value context, transcript, crop, or time range is visible before
  asking for a label;
- save, skip, finish-current-work, and resume paths are explicit;
- partial work persists;
- corrections feed a reusable supervision/preference path when the product
  promises learning;
- technical files and commands remain available in a secondary handoff surface,
  not as the primary completion action.
