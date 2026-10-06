---
name: sls-recurring-notifications
description: >-
  Adapt an existing Alibaba Cloud SLS pipeline to recurring WeCom reports.
  Read for SLS webhook templates, fire_results truncation, daily report dates,
  dedicated notification policies or scheduler-to-recipient verification.
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

Select the newest sample in the query and project only the required scalar fields
before the notification stage. Splitting a large JSON object into short result
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
