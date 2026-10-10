# Journey, Browser-Output, And Page-Type Contracts

Load this reference only when the audit includes state transitions, routes,
overlays, browser-owned output, native shells, complex page types, maps, or
review/annotation workflows, including summary-to-detail disclosure.

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

For a changed multi-item read or batch result, the executing auditor uses the
authorized project harness to fail one known item while the enclosing request
succeeds. Reconcile the expected identities with the visible successes, failures
and unread items; failed items must not disappear or be labelled complete. Read
the failure and its safe next action from the ordinary render, not a hidden DOM
node. If the product permits retry, trigger it and verify it targets the original
failed selection, replaces the failure with the correct content, and preserves
successful work. Keep uncertain writes behind the project's existing recovery
contract; this recipe does not authorize resubmission. Exercise an all-success
control as well. No generic sweep determines per-item completeness or safe retry;
retain the exact selection, visible outcome and recovery observations in the audit.

For nested zoomable workspaces, the executing auditor treats the ordinary entry,
enlarged mode, affected zoom levels and return-to-ordinary as separate states.
An enlarged canvas cannot certify the shallow ordinary pane. Record its rendered
node set, pane dimensions and settled viewport before judging fit; an empty or
transient canvas leaves that state unobserved. When sizing or fit changed, resize
the pane itself, including a resize that keeps the same column count.

For fixed cards with inverse-scaled text, inspect every visible title, date and
preview field. A contained box can still paint half a line. The sweep's
`paintedText` observation detects substantial vertical fragment clipping; whole
omitted lines, horizontal ellipsis, scroll windows and clip-paths need separate
pixel/journey judgement. Transparent captions can cover control icons while
clicks succeed: compare painted bounds, inspect the crop, then trigger the real
control. These checks support geometry, not comprehension or semantic fidelity.

Keep each state's verdict and limitations when composing the result. A passed
child return or enlarged view does not upgrade another state's partial verdict.
No automatic tool enforces this scope comparison; the executing auditor must
apply SKILL.md's completion gate to the original user contract.

Treat these as Major unless the project taxonomy says otherwise:

- a primary action blocks indefinitely with no recovery;
- success is shown when the operation failed or produced the wrong artifact;
- the UI returns to an unrelated feature or mode after error;
- a user can enter an advanced mode but cannot identify or leave it.

Before closing a nontrivial journey audit, repeat the main path without
developer context and ask what a tired or first-time user will misunderstand
first. Check trigger ownership, return-to-default, recovery, runtime truth,
internal language, manual burden, and which regression guard catches the miss.

### Refactor Preservation

Apply this recipe only to affected UI refactors, category splits, or navigation
changes. The auditor performs it through the existing project harness and
authorized Level A/B journeys; the bundled layout sweep does not inventory old
capabilities or decide data preservation. A copy-only edit does not require it.

1. Resolve a full immutable pre-change commit or release and read its relevant
   routes, controls, and consumers, for example with `git show <commit>:<path>`.
   List the original user operations and outputs in the existing audit contract.
   Compare product names and labels with the latest approved naming authority
   outside the refactor's write scope; neither old implementation labels nor new
   defaults can overturn an approved rename. An unavailable baseline leaves
   preservation unverified rather than letting the new UI define the old scope.
2. For each affected consumer, name its inclusion rule and expected record IDs
   from independent project data. A browsing list, source review, domain check,
   and relationship lookup may consume different sets. Trace a changed shared
   filter to each of those consumers; hiding a category from one list does not
   authorize removing its records from every check or query. Verify default and
   affected combined filters with a representative included/excluded record.
   For paginated or bounded views, include a known required record outside the
   initial or newest window and exercise its normal read path. Derive the expected
   set from the selected scope's authoritative record, not the returned page or
   visible list. A missing body may remain unknown only after its read coverage is
   established; inability to read is not evidence that the body does not exist.
3. Map each original operation to its current visible entry and exercise it.
   Confirm the resulting answer or output and reconcile record identities,
   relevant fields, relationships, and retained drafts through the ordinary
   read/reopen path. Compare IDs and values, not only counts or label matches.
   Mark approved retirements with their authority; an unreachable old action or
   an omitted record remains a regression even when the new screen looks clean.
4. For a confirmed regression, run the smallest project probe against saved old
   evidence or an authorized isolated faulty version, then the repair. Include a
   healthy near-boundary control. Inspect the same affected journey on the real
   current page at Level A/B; source, build, and handler assertions alone cannot
   close the rendered finding. Leave unavailable page or write evidence explicit.

Retain a compact map in the existing report:
`old operation -> current entry -> expected IDs/values -> observed result -> evidence/verdict`.
Reuse unchanged passing checks bound to the same content and inputs; rerun only
changed or failed checks, unresolved cases, and repository-required checks. Stop
when the affected operations, consumer sets, and retained work are accounted for;
this recipe does not require a full-product regression on every edit.

### Delayed Completion And Reopened Work

Use these recipes when an affected editor or batch workflow can outlive a
selection, navigation, or component instance. Cover the affected journey, not
every asynchronous operation in the product. Use an authorized isolated project
fixture with synthetic objects A and B and the existing response-holding harness.
Hold delivery of a response without cancelling or replaying the submitted write;
record its original target, request identity, and server result. If that harness
or write authority is unavailable, specify the missing prerequisite and leave
execution unverified. Do not manufacture races in production.

**Editor save, leave, and reopen**

1. Open A through the visible control, enter a recognizable first draft, and
   submit once. Hold its success response after the fixture server accepts the
   write. Record the original object target and submitted value.
2. Before releasing it, navigate A -> B -> A, reopen the editor, and enter a
   distinct second draft for the same A. Separately exercise browser Back out
   of the pending editor and reopening that same object; matching object IDs
   alone must not make the old editor own the new draft.
3. Release the old response. Inspect the actual current page: its selected
   object, route, editor, and second draft must remain the newer state. Close
   and reopen through the product's draft-preserving path and verify the second
   draft is still visible. Do not use an explicit discard action for this check.
   Read the fixture server independently: the already submitted write may
   finish on its original A, but must not target B or be submitted again.
4. Repeat the late-response branch with a real fixture failure or conflict.
   Its stale error must not replace the new editor or erase its draft. Confirm
   a normal, still-current save succeeds and clears only its own accepted draft;
   a current failure retains editable input and an actionable recovery path.

**Batch preparation, leave, and recover**

1. Start maintenance of a selected synthetic batch and hold its preparatory
   GET. Leave that workflow, reopen it, and enter a new batch. Submit the new
   batch once, capturing its text, request identity, and real server result;
   hold its response as needed to keep recovery pending.
2. Release the old GET. It must not initiate a POST for the retired preparation,
   overwrite the new batch text, or replace the new pending request identity.
   Observe emitted requests as well as the current page; an unchanged draft
   can hide an unintended server write.
3. Leave and reopen while the new POST is pending, then release its response.
   Inspect the displayed batch and resume through the normal recovery control.
   Read back the original request identity from the fixture server and verify
   its result belongs to the submitted new batch. Recovery must not create a
   fresh identity or duplicate an already submitted POST.
4. Exercise ordinary batch preparation and recovery without delayed responses
   as a healthy control. Where the component runs under React StrictMode,
   also use its actual setup -> cleanup -> setup lifecycle and confirm the
   second live setup still permits a current save or preparation. A permanently
   retired guard that blocks all writes does not pass either recipe.

Retain a compact map of `held response -> navigation/new input -> release ->
current visible state -> reopened draft -> server readback`. Handler tests,
storage contents, DOM flags, and request counts support this map; none alone
proves that the user's reopened editor displays the correct work. For fix
closure, use the same bounded recipe against saved old evidence or an isolated
old implementation as a negative control. Keep server-side object-period/version
write contracts in the project's own specification and tests.

## Summary-To-Detail Disclosure

When an affected control reveals an explanation, breakdown, inspector, or other
detail, audit the questions each state lets the actor answer. The auditor executes
this through the authorized Level A/B interaction and the project's independent
reference; no bundled text-count or DOM-node metric decides whether detail is useful.

1. Freeze the actor's question for the collapsed view and the question promised
   by the expanded view from the user/task contract, before clicking. Keep facts
   needed for the ordinary task visible initially; a concise disclosure label
   should identify what the secondary view adds.
2. Inspect the collapsed render and answer its question from that render alone.
   Record the visible values, relationships, or evidence used. A correct grand
   total cannot establish that a requested contribution breakdown is visible.
   For contribution views, quote the visible work or result that answers who did
   what. Names, lifecycle events and repeated missing-content warnings cannot
   establish that answer. A verified source gap may be shown with an actionable
   coverage state; record the unanswered question rather than granting a pass.
3. Trigger the actual control, then read and extract the newly visible granular
   rows, relationships, explanations, or supporting evidence. Answer the expanded
   question using that evidence, naming what was unavailable while collapsed.
   An open flag, changed text, extra nodes, or more pixels cannot supply the answer.
   Nonfinancial detail may supply an explanation or source evidence rather than a table.
4. Reconcile the observed answers against an independent project-authoritative
   fixture, record, or calculation. For quantitative breakdowns, check component
   identities, exact quantities, units, inclusion rules, and time ranges/cutoff,
   as well as their relationship to the summary. Distinguish each period's value
   from a cumulative value and an unfinished period from a complete one. Agreement
   between two UI states is not independent evidence; unavailable reference
   leaves that claim unverified.
5. Close and reopen as relevant, and retain a compact evidence map:
   `state -> actor question -> observed answer/evidence -> reference -> verdict`.
   Fail the promised detail when it merely repeats the summary and leaves its
   question unanswered. Retain a repeated summary/total when it anchors the new
   breakdown or permits reconciliation; repetition alone is not a defect.

For fix closure, exercise the rejected old state as a negative control and a
healthy near-boundary case: a real breakdown that also repeats its total should
pass. Use saved old evidence or an authorized isolated fixture when needed, label
synthetic evidence, and do not mutate the live target to manufacture the defect.
Stop after the affected questions and relevant existing journey regressions are
resolved; do not turn this check into a whole-page redesign.

The split and expectation checks apply
[NN/g's progressive-disclosure guidance](https://www.nngroup.com/articles/progressive-disclosure/).
The essential-content boundary follows
[GOV.UK's details guidance](https://design-system.service.gov.uk/components/details/).
These sources do not prescribe one detail format or prove this target's correctness.

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

### Cited Source Inspection

When a citation marker promises original evidence, inspect what the reader can
actually read after opening it. Compare the displayed source with the citation's
bound identity and locator; a visible surface or loaded frame alone is insufficient.

- Text: read the cited original wording and surrounding context at the promised
  speaker, timestamp, clause or message locator.
- Image: inspect the bound original or explicitly named quality variant, original
  message/batch/ordinal and proportions. A filtered gallery's first item must not
  silently become the original's first image.
- PDF: read the actual cited document and page, including the relevant words or
  marks at usable size. A filename, iframe chrome, matching bytes or a page-count
  label does not prove the page content is readable. Exercise the preview's scroll
  or zoom when the whole page does not fit.

Close the source and verify focus returns to its marker and the page and scrolling
ancestors retain the reading position. For hover/focus previews, exercise pointer
movement into the card, Escape dismissal without immediate reopening, activation
that hides the preview, and a fresh focus that can reopen it. If an adapter partly
opens and fails, verify its surface and background lock are cleaned up before
reporting the failure.

Use a synthetic empty or wrong source to prove this inspection can reject a
misbinding. Run only affected source types. Mark unavailable original-content or
native-viewer evidence unverified; a successful DOM sweep cannot replace it.

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
- status chips whose tone comes from the project's status dictionary, with
  alarm/error tones reserved for genuine failures.

Flag:

- explanatory card waterfalls before the work surface;
- the same KPI strip copied onto every workspace;
- navigation that changes content but not addressable state;
- a generic permanent side rail that steals canvas width;
- a desktop table merely squeezed into a phone viewport;
- a drawer that blocks unrelated work by accident.

Also audit **status-semantic density** on list/queue pages — each row can pass
its own component checks while the page reads as a disaster:

- an alarm-toned (red/error) chip repeated on most rows. Either the fleet is
  genuinely on fire, or a neutral fact was misclassified upstream into a failure
  state — "the platform does not provide this metric" is `not supported`, not
  `check failed`. Read the chip's copy against what actually happened and trace
  the classification before treating the styling as correct; a page of red reads
  as an incident and trains users to ignore alarms.
- the same global fact (data not yet imported, module not connected, feature
  flag off) re-rendered as a per-row chip on every row. One page-level notice or
  a column-header annotation carries the same information without turning a
  ledger into a wall of warnings.
- a numeric or graphic cell with no visible label — sparkline triplets, bare
  counts, unlabeled gauges. An aria-label satisfies the accessibility tree but
  not the sighted reader; if the audit cannot say what a number means from the
  rendered page alone, neither can the user.

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
