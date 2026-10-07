---
name: sls-recurring-notifications
description: >-
  Adapt an existing Alibaba Cloud SLS pipeline to recurring WeCom reports and
  meaningful state changes. Read for grouping, deduplication, low-frequency
  heartbeats, native webhook rendering or scheduler-to-recipient verification.
---

# SLS recurring reports

Keep sampling and execution with the project's existing owners. This reference
defines the SLS-to-WeCom seam; it does not install a cloud client, create a bot or
authorize a production change.

## Reuse the actual pipeline

Inspect the current sampler's records, SLS store/index, live report rule, webhook
integration and sync command. Use the current implementation rather than a retired
Terraform declaration or historical helper path. A configured scheduler is not
proof that its latest run succeeded.

Confirm the intended group using the [recipient contract](../SKILL.md#send-a-message).
When adapting a shared alert pipeline, use a dedicated report template and
webhook-only action policy so routine reports do not inherit SMS/voice escalation
or change existing alerts. Keep scheduling timezone explicit. Read-only inspection
and local rendering do not authorize installing a rule or sending an example.

## Project before rendering

SLS `alert.fire_results` returns at most 100 rows. It truncates a field over 1 KB
or the result variable over 2 KB; raw query results have the same byte limits.
See [SLS template variables](https://help.aliyun.com/en/sls/variables-in-new-alert-templates).

For a snapshot report, select the newest sample in the query and project only the
required scalar fields before the notification stage. A change rule needs the
sample sequence and a baseline before its event window; the newest sample alone
can hide a transition that returns to the original state. Splitting a large JSON object into short result
rows can preserve each account without parsing already-truncated JSON in Jinja.
Verify the actual projected result's field and total sizes, including unknown/error
cases; a miniature fixture cannot establish that a real multi-account record fits.
Add required analytic index fields through the project's normal release path,
preserving existing index definitions. Missing/stale samples or failed account
queries must remain visible as unknown, not zero or healthy.

## Dates and JSON

Use `alert.alert_time` for the current evaluation's date. `alert.fire_time` is the
first firing timestamp and may remain unchanged across successive daily reports.
Test two evaluations on different days with the same first firing time.

Serialize the rendered message with SLS's `to_json`, rather than relying on quote
wrapping or a local replacement with different escaping behavior. For an already
rendered `summary` string, the template envelope is:

```jinja
{"msgtype":"markdown","markdown":{"content":{{ to_json(summary) }}}}
```

Read [SLS template functions](https://www.alibabacloud.com/help/en/sls/built-in-functions-in-alert-templates)
for the native function contract. The project's SLS template/sync owner handles
this Markdown envelope; the bundled plain-text sender is not its renderer.

## Meaningful changes and quiet-period health

The executing agent/operator first defines which observed changes affect the
recipient's use or next action. A switch, exhausted quota, verified recovery or
persistent sampling failure can qualify; routine percentage drift does not need
a message. Report what recovered: quota, sampling, isolation and successful
service are distinct observations. A window expiring is not a recovery.

Reuse the existing scheduler to group changes into complete, non-overlapping
windows, with a declared allowance for log arrival. Keep the window end as a
stable event identity so reevaluating that window does not send it again. Compare
the full sequence, retaining reverse transitions such as A→B→A and deduplicating
repeated samples. Test a boundary event, a repeated evaluation, duplicate samples
and a reverse transition against the actual query engine; keep unsampled or
too-late changes outside the stated coverage.

Use a low-frequency heartbeat when the user wants reassurance during quiet
periods. It should report a fresh sample and its age; missing or stale data stays
unknown. Detect missing producer samples independently of that producer, using
the existing monitoring owner. A producer that stopped cannot send its own
failure notification. Keep heartbeat and change cadence in project configuration,
rather than adding a per-minute test-message loop or another notification daemon.

## Combine results before the webhook

WeCom expects one message object. SLS native batch delivery can render each item
and assemble an array, which is a different payload. For an existing single-object
WeCom integration, combine the event text in the query/template owner's path and
use its single-message delivery setting. Exercise a multi-event native evaluation
and inspect the dispatched JSON shape; local rendering of a hand-built `alerts`
variable does not prove native batching. Retain the existing result-size checks.

## Acceptance at the consumer

The executing agent/operator verifies each stage separately:

1. Read back the live rule's enabled state, cron, timezone and exact policy/template.
2. Execute an authorized, clearly labelled sample through that native rule and
   template with real-sized data. Local Jinja tests or a direct bot call are not
   substitutes for the SLS rendering path.
3. Inspect native evaluation and dispatch records for that event. Dispatch success
   does not establish the receiver's response body or group receipt.
4. Verify the intended message in the intended group; preserve unresolved receipt
   as unknown. Follow [worker receipts](../SKILL.md#automatic-worker-receipts) for
   accepted/rejected/unknown outcomes and ambiguous-event replay boundaries.

Report source/CI completion, deployed scheduling, native dispatch and recipient
receipt as separate stages. Stop when the authorized path is verified; do not
add another scheduler, replay an ambiguous event or widen notification targets
to replace missing evidence.
