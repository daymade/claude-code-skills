# Select a batch against the capacity goal

Use this before starting or extending a long cleanup/deduplication batch. Stop
selection when a bounded next action has an observed cost, an honest reclaim
ceiling and authorization; this is not permission to widen the scan or delete.

Copy the user's capacity unit exactly. Keep emergency relief, reaching a free-space
watermark and sustained headroom separate. A completed item count proves none of
them. Record in the existing plan: current same-volume free bytes, target bytes,
remaining gap, the candidate's reclaim upper bound (or explicit unknown), pilot
items/time, estimated remaining time, and the next independent authorized action.
Use a representative pilot with the production checks; dropping those checks to
make the estimate faster changes the measured job.

Run the supplied-evidence calculator from this skill directory:

```bash
python3 scripts/batch_budget.py /absolute/path/budget.json
```

Example input (synthetic, bytes and seconds):

```json
{"available_bytes":159000000000,"target_available_bytes":200000000000,
 "remaining_items":2500,"pilot_items":10,"pilot_seconds":100,
 "reclaim_upper_bytes":4000000000}
```

This leaves at least 37 GB of the gap after the candidate's upper bound, with an
estimated 25,000 seconds for its remaining items. The estimate assumes the pilot
remains representative; it is not a deadline or a physical-release promise.
Missing/null reclaim evidence stays unknown, never zero or planned savings.
The calculator neither measures disk state nor authorizes an action.

If the upper bound cannot close the gap, keep another authorized route moving
instead of reporting batch completion as goal completion. Compare remaining time
with the next useful checkpoint and observed opportunity cost. Do not invent a
fixed duration cap or bypass safety checks. Preserve work already completed; use
the executor's supported checkpoint/pause and explicit remainder rather than
restarting a batch. Coordinate a concrete window when another authorized task
needs its lock, then independently verify release before claiming availability.

At handoff, report actual same-volume `df`, the remaining gap and protected
consumers' readback. A mixed activity window cannot attribute net host change to
this batch alone. Sustained headroom requires a user-relevant observation window
and the growing writers' own retention policies; a watermark reading alone does
not establish it or authorize new periodic cleanup.
