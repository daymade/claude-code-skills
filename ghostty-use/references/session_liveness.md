# Session liveness and recovery candidate selection

## Resolve artifacts and identity

Use the shared [inventory and liveness implementation](../scripts/ghostty_session.py)
for storage lookup, filename/cwd encoding, process-to-artifact assignment, metadata
bounds and classification settings. Its `list_sessions`, `_assign_transcripts`,
`_claude_candidates` and `_codex_candidates` define the current identity checks;
`claude_liveness`, `codex_liveness` and `classify` define the emitted grades.
Do not maintain another filename pattern, timing tolerance or status catalogue here.

When inspecting original history, load the installed `read-claude-code-history`
or `read-codex-history` owner for that provider. Resolve the actual configuration
home and symlink target rather than assuming profiles share one storage pool.
For Codex, use the reader's indexed physical-rollout selection and verify internal
identity; a filename, underscore, matching cwd or newest file alone proves neither
logical identity nor subagent status. Keep missing, ambiguous or mismatched evidence
unknown; do not substitute an older physical segment.

Resolve live TUI identity through the shared inventory, including UUID-less and
forked processes; process-name matching alone cannot establish absence.
A parent selector is not proof of the child's identity; use the
resolver's verified assignment. Preserve unresolved rows when no unique identity
can be established, and do not treat them as replayable commands.

## Classification

Read the implementation above when diagnosing an emitted grade or changing its
threshold/error handling. Grades describe captured evidence, not substantive work
inside a requested activity window or the user's current restore preference.
Use the [restore selection rules](../SKILL.md#quick-start) for the requested set.

Inspect original event timestamps and structured errors through the selected
reader. File mtime, quoted error prose and a credential's future expiry do not
establish conversation activity or account health. A verified identity with an
unavailable artifact and an identity that cannot be verified are different evidence
boundaries; preserve the distinction reported by the reader and shared resolver.

## Select recovery candidates by a time window

Enter this recipe before choosing a recovery set when the snapshot is absent,
outdated or partial (unresolved TUIs or retained-unverified rows), without waiting
for a count challenge. Also use it when a user questions a snapshot's size or asks
which sessions were active after a time. The executing agent uses the installed
history readers; the automatic watcher reads only bounded identity metadata,
not conversation-body activity (see [automatic snapshots](automatic-snapshots.md)).
This is a read-only selection step, not authorization to reopen or continue every
candidate.

1. Bind the date, timezone and end of the requested window before querying. For
   reboot recovery, stop at the reboot boundary so the current recovery conversation
   cannot enter the old set. State an inferred date explicitly; do not silently
   replace the user's window with the default `active` threshold.
   If no activity cutoff was requested, use the recovery context to bound lookup,
   not to declare older tabs closed. Inspect known snapshot/retained IDs separately
   from time-window additions; early last activity does not exclude those IDs.
2. Report automatic backup coverage separately: recorded IDs, identified at
   capture, retained-unverified IDs, and unresolved TUIs. A retained row is neither
   confirmed live nor confirmed closed. Use the
   [observation-health check](automatic-snapshots.md#verify-observation-health)
   before drawing conclusions about backup freshness.
3. Load `read-codex-history` and use its indexed inventory with explicit bounds:

   ```bash
   python3 <codex-reader-dir>/scripts/list_local_history.py \
     --source codex --index-only --all-projects --include-archived \
     --from-date <FROM_ISO_WITH_ZONE> --to-date <TO_ISO_WITH_ZONE> \
     --limit <candidate-cap> --format json
   ```

   Read coverage, warnings and truncation. The index's created/updated interval
   selects candidates only; an older session resumed during the window remains
   eligible. Verify selected rollout identity and original records through that
   reader. Exclude automated/noninteractive work from terminal candidates using
   verified metadata. Preserve unknown when the index or selected artifact is
   unavailable; do not replace it with a raw-history scan.
4. For Claude rows already named in the snapshot, load `read-claude-code-history`
   and read those exact IDs. The Codex inventory above cannot establish Claude
   continuation coverage. Keep absent/unexamined Claude membership explicitly unknown.
5. Qualify activity by original event timestamps inside the window: user or agent
   messages, reasoning, and tool calls/results can establish activity. File mtime,
   index update time, metadata-only records and token/heartbeat events cannot.
   Distinguish substantive work, scheduled status reports and peer coordination;
   the latter two do not establish continued work on the business task. Use the
   latest relevant exchange to name the work, rather than an old title or prompt.
6. Return last qualifying activity with timezone, current topic, session ID and
   membership evidence. Separate past-snapshot rows from additional verified
   terminal-origin candidates: terminal origin does not prove Ghostty membership
   or that the tab remained open at shutdown. Do not infer either from a matching cwd.
7. Once the user selects the wanted IDs, freeze that exact set with the existing
   `reconstruct --only ... --out ...` route and carry the same manifest through
   preview, restore and reconciliation. Keep the original snapshot unchanged.
   Do not automatically discard waiting or older sessions when no time filter was
   requested. Stop selection when the requested set and coverage gaps are clear.
