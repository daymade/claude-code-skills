# Interactive analysis and return to the conversation

Load this recipe for an existing calculator, filtered data browser or review
workbench when the reader needs to continue from their parameters or selection.
Keep it conditional: use static evidence when controls would not change the
reader's understanding or next action. Keep the existing delivery gates and
review budget; add the affected states to the existing browser journey.

## Make controls answer a question

Name what the reader can learn by changing an input before adding controls.
Expose meaningful parameters with units, allowed ranges, a baseline and reset.
Separate sourced observations from editable assumptions; label calculated
results as scenarios. Update the result, its explanation and any geometry from
the same calculation. Preserve the source baseline when trying another scenario.
Use the existing calculation-script and geometry contract in SKILL.md rather
than hand-maintaining a second formula in labels or drawings.

For a review workbench, keep stable record IDs through filtering and sorting.
Show whether a selection covers visible rows, all filtered rows or individually
marked records. Keep selected items inspectable when a filter hides them; make
clearing the selection explicit. Do not identify a record by its screen position.

## Carry the reader's context into the next question

Offer an explicit action to prepare a follow-up only when the task needs one.
Build a readable preview from the current state at that action, including:

- the report/dataset identity and source version or snapshot;
- the selected stable IDs and their evidence locators, or an explicit whole-view
  scope; include the filter when it explains that scope;
- current parameters with units, distinguishing observations from assumptions;
- the user's question or requested local change, and any unsaved edits that
  affect its interpretation.

Let the reader inspect and remove context before sending it. Keep unrelated
records and incidental UI state out of the packet. Treat preparing context,
persisting state and sending a message as separate actions. Do not start a model
request from a slider change, autosave, initial render or state restoration.

For a standalone HTML file, expose selectable text or a downloadable context
file that the reader can bring back to the conversation. Offer a copy button
only with a working permission/error path; retain manual selection when the
clipboard is unavailable. Report copy/export success only after that operation
succeeds, and never label it as a message sent or a source document saved.

## Separate view state from durable work

Keep filters, active tabs, scroll position and parameter drafts separate from
source data and review decisions. State what survives a reload, browser restart
and moving the file. Treat browser storage as an optional convenience cache;
do not promise portable recovery from localStorage under `file://`.
For work that must survive, provide an explicit export/import or the project's
existing persistence owner. Label the result accurately: a snapshot downloaded
by the browser is not a confirmed write to the underlying document.

Bind a saved state to its report/dataset identity, source revision and state
format version. Validate those identities, record IDs and input values before
applying a restore. Preserve the current draft when the state is malformed,
unsupported or belongs to another revision; explain the mismatch and offer a
fresh view or a separate copy. Do not silently map old row positions onto new
records. Keep a usable current-session view when storage is denied or full.

When a follow-up edits durable content, read its latest revision before applying
the requested change. Address the selected stable IDs, preserve unrelated human
edits and use the existing owner's conflict check. Retain a conflicting draft
for comparison or saving a copy; do not overwrite newer work to make the retry
succeed. Keep document persistence and concurrency with that owner rather than
building a database or sync service inside the report.

## Bind an optional host bridge to the actual host

Keep the default deliverable a locally opened HTML file. Add host communication
only for an explicitly selected, available integration, using that host's current
API and capability checks. Keep absent, declined, cancelled and failed results
visible; retain a manual context handoff when a bridge is unavailable.
Do not infer file access, model calls or durable storage from an embedded page.

Distinguish ZCode Gen UI's injected bridge from UI Plugin's MCP Apps connection
when that host is actually selected. Do not mix their state formats or assume
either exists in an ordinary browser. Recheck the selected host's current
contract before authoring API calls; keep protocol-specific implementations
with the integration owner. Do not add an SDK, plugin installation or service
as a prerequisite for an ordinary report.

## Exercise the continuation in the existing browser journey

Use the page's actual controls and exported/restored content as evidence:

1. Change a parameter away from the baseline; check the numeric result,
   explanation and graphic against an independent calculation, then reset.
2. Select records, sort/filter so some leave view, and prepare a follow-up.
   Read the preview/export: verify exact IDs, source revision, scope, units and
   current values. Verify clearing or changing a selection removes stale context.
3. Export state and restore it after a reload. Try a wrong dataset/revision,
   invalid values and malformed input; verify the current draft survives and
   the reader sees the failure. If caching is used, also deny storage.
4. Exercise keyboard access and the manual handoff without a bridge or clipboard.
   Observe that changes/restoration send no message and perform no source write.
   For a selected host integration, verify an explicit send and its failure path
   separately from local preparation; a mock proves only the local adapter.

Skip inapplicable states explicitly in the existing journey evidence. Keep a
static-report control case free of unnecessary controls, state or follow-up UI.
Keep this recipe a candidate method; do not promote an unapproved implementation
to the approved component shelf or corpus.

## Source boundary

Use [ZCode's UI Plugin guide, pinned revision](https://github.com/zai-org/ZCode/blob/0a1fc56d279fd1001f78387bd81aec1c26767411/UI_PLUGIN.md)
for the source design: selected-element continuation in Excalidraw, explicit
Gen UI follow-up, and separation of view state from plugin-owned documents.
Treat that guide as documented behavior observed on 2026-10-19, not evidence
of a released host's compatibility or measured benefit to report readers.
Adapt the workflow to local reports; leave the SDK, host quotas, installation
and plugin lifecycle with their original owners.
