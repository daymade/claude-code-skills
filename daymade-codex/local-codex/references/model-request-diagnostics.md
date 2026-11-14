# Codex model-request failures and original-session recovery

Use this procedure when a specific Codex session fails at the model endpoint,
including `400 Bad Request`. Diagnosis is read-only by default. A user request to
repair covers the necessary reversible fix and verification; account changes,
shared-service interruption and external side effects retain their own boundaries.

## Bind the failure before probing

Apply the [session identity gate](oauth-guide.md#check-existing-sessions-separately)
to the exact SID and cwd. Record the failing turn's time, runtime/PID, actual
executable and its version, endpoint, selected provider, model and configuration
overrides. A shell's newer `codex --version` does not identify an older running
daemon. Use the current host's native thread/log tools or the exact-session entry
in `read-codex-history`; do not scan unrelated histories or resume the target just
to inspect it.

Determine the **actual transport from that attempt's request/connection logs**.
An HTTP-like error message or `supports_websockets=false` in a config fragment does
not prove the active provider used HTTP. Before comparing requests, check that
each attempt reached the intended endpoint over the same transport. Keep a failed
attempt to force HTTP as a failed setup check, not a compression result.

## Exhaust the error evidence

Keep evidence in a task-owned private directory. Request bodies and trace logs
can contain complete prompts, images and credentials; publish only sanitized
extracts or synthetic equivalents.

For the exact failed attempt, retain:

- UTC timestamp, status, complete response headers and **full response body with
  its byte count**; inspect the body even when the UI says only Bad Request.
- Request/correlation identifiers and error-detail headers actually present,
  including `x-request-id`, `x-oai-request-id`, `cf-ray` or `x-error-json` where emitted. Their absence
  is an observation, not evidence of a particular backend failure.
- Client error chain and native model-request trace, with the selected binary,
  provider and transport attached. Correlate by attempt/ID, not adjacent log time
  alone.
- Input-item and image counts, raw/encoded body lengths and the selected context
  settings when available. These are hypothesis inputs, not proof of an input
  limit or a bad image.

If the capture contains only a small generic JSON response, report its exact
sanitized content and length. Say **which evidence sources were checked** before
concluding that no more detail was captured. Do not invent a hidden validation
message. An unavailable request body remains unavailable.

When existing logs omit the decisive signal, inspect the selected build's help
and source before enabling a bounded trace on an authorized isolated invocation.
Builds have exposed `CODEX_ROLLOUT_TRACE_ROOT` and the
`codex_http_client::transport` tracing target; confirm their current behavior,
capture point and redaction before using them. A JSON inference-trace object may
have been reserialized; a transport log of the serialized JSON may be pre-compression.
Neither label alone establishes that the original encoded HTTP entity was saved.
Do not restart a shared daemon merely to enable logging.

## Design the smallest discriminating comparison

Use the existing `debugging-network-issues` Skill's
[same-byte HTTP compression comparison](https://github.com/daymade/claude-code-skills/blob/main/debugging-network-issues/references/compressed-request-comparison.md)
for the experiment. Preserve the distinction between:

| Artifact | What it supports |
| --- | --- |
| Original failed HTTP entity bytes and sent headers | Replaying the captured original representation |
| Original serialized JSON before compression | Matching the original logical bytes; a newly encoded entity can differ |
| Parsed native trace serialized again | A reconstruction, even if its JSON values match |
| Synthetic fixture | A failure of that fixture; relevance to the original needs its own evidence |

Keep credentials in the [selected OAuth store](oauth-guide.md), outside prompts
and fixtures. Do not switch accounts, change models, remove images and disable
compression in one comparison. Use the selected build's supported native
provider/configuration interface, then verify the resulting transport in logs.
Do not overwrite the user's normal provider table to make a temporary probe run.

A synthetic HTTP request returning 400 with zstd and 200 without it establishes
a compression-related failure for that tested representation and path. A full
original-history fork succeeding with compression falsifies “this history always
fails when compressed.” If the original failed entity is missing, the synthetic
contrast cannot establish the exact cause of that original 400. Report both
observations, and leave the backend component unknown unless server evidence
identifies it. A later compressed success does not erase an earlier controlled
failure or prove every compressed request is healthy.

## Mitigate and verify at the actual consumer

After isolating compression as a relevant failure axis, use the selected build's
native feature interface if an authorized mitigation is warranted. Check its
current help and feature listing first. On builds exposing it, the native command
is `codex features disable enable_request_compression`. Read back the exact
configuration written by that executable; do not blindly edit TOML or assume a
feature default from another version.

Verify separately:

1. The saved setting is boolean false at the actual `CODEX_HOME`.
2. A fresh invocation, without a CLI compression override, loads that setting,
   uses the intended transport and completes a bounded representative request.
3. The original SID completes a new model turn under its actual runtime. Confirm
   the original task's relevant result separately if business completion is in
   scope.

The first two checks do not prove an already-loaded daemon adopted the setting.
Record effective adoption as unknown until observed there. A successful isolated
fork proves the fork works, not that the original SID recovered. An ephemeral
fork/copy must preserve the source history; use the current native help to select
the supported isolation mode and verify source preservation after the probe.

Before a diagnostic message to the original session, use `peer-message`'s
diagnostic-coordination guidance. “Only reply with a marker; do not use tools” in
peer text is not tool isolation. Prefer an isolated ephemeral consumer or a pure
HTTP replay that never executes returned tool calls. If resuming the original is
authorized, inspect its actual actions and distinguish responsiveness, compliance
with the diagnostic request and completion of the business task.

Stop when the authorized repair has been verified on the original consumer and
the remaining uncertainty is explicit. Without captured original entity bytes or
server diagnostics, retain that causal gap; an escalation packet should include
sanitized timestamps, request IDs, complete error evidence and the bounded
comparison, not an asserted internal decoder cause.
