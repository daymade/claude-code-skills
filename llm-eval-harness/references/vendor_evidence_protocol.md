# Vendor Evidence Protocol — reporting a provider bug without getting deflected

You have probe results that look damning. The distance between "my test failed"
and "the vendor's engineer can act on this" is a protocol, not a feeling. This
file is that protocol, distilled from real vendor escalations (a prompt-cache
instability case and a system-prompt-loss case, both against production
gateways). Follow it before anything leaves your machine.

## Contents
- Why observation-wording, never accusation
- The self-audit that must precede any report
- Evidence package: what to capture per request
- Pre-register the verdict thresholds
- Adversarial counter-review before sending
- Confidence tiers in the written report
- Template skeleton

## Why observation-wording, never accusation

You do not have the vendor's internal packet captures. From the client side you
can prove *what you sent* and *what came back* — never *what their gateway did
in between*. Writing "your gateway silently drops the field" invites a one-line
rebuttal ("how would you know?") that stalls the whole thread; writing "the
field does not take effect and is absent from `usage`; please trace these
request IDs outbound" gives their engineer a job they can actually do.

Rule: **observation + data + "please trace"**. Concretely:

| Don't write | Write instead |
|---|---|
| "system prompt is silently dropped" | "system prompt does not take effect (canary never echoed) and does not appear in `input_tokens`" |
| "your cache is broken" | "byte-identical requests show cache_write with no cache_read within a 41-second window" |
| "you are routing us to a fake model" | "the served behavior differs across repeats; request IDs attached for both cases" |

Mechanism language ("like partial channels not forwarding the field") is
acceptable only when explicitly marked as a hypothesis for THEM to verify.

## The self-audit that must precede any report

Every claim of "your side is broken" earns a rebuttal of "your client is
broken" — so close those doors first, and SAY you closed them in the report:

- **Payload identity**: hash the exact request body (SHA-256) and verify
  repeats are byte-identical. This single line kills the "your client mutated
  the payload" deflection.
- **Thresholds honored**: if the feature has documented minimums (e.g. a
  cacheable-prefix floor), show your payload exceeds them — pre-empts "your
  prefix is too short".
- **Client retries off**: confirm your HTTP client's retry count is zero, or
  your "duplicate" observations are self-inflicted.
- **Ambient network excluded**: probes ran with `trust_env=False` and fresh
  connections (disciplines §4–5), so no proxy or sticky LB is the variable.
- **The probe itself validated**: run the same probe against a known-good
  control (another model / another vendor). If the control also "fails", the
  probe is the bug — one real canary "outage" was the canary's own too-short
  sleep, not the pipeline.

## Evidence package: what to capture per request

- Full timestamp with explicit timezone (log sources differ; ambiguity kills
  cross-referencing).
- **Every id-like response header and body field** — match header names
  case-insensitively against `id / request / trace / reqid`, because vendors
  name these fields five different ways. These IDs are how their support
  finds your requests in THEIR logs; a report without them asks the vendor to
  search by vibes.
- The verbatim response body (truncated is fine, but keep error `type` fields
  exact — "upstream_error" vs "invalid_request_error" route to different teams).
- A minimal reproduction command (curl) that their engineer can paste and run.
  100%-reproducible entry points are gold: lead with the one model/config that
  fails every time, even if the interesting story is the intermittent one.
- The contrast pair when the failure is intermittent: two adjacent requests,
  same body, one working and one failing, both IDs. Nothing shortens a
  routing investigation like "these two, 25 seconds apart".

## Pre-register the verdict thresholds

Decide what PASS and FAIL mean **before** running the batch, and write the
thresholds into the probe/report header (e.g. `PASS: hit_rate ≥ 0.80 AND
both_zero_rate ≤ 0.05`). Choosing thresholds after seeing data is how motivated
reasoning ships; a pre-registered threshold also converts a mushy complaint
("feels flaky") into an SLO the vendor can accept or dispute ("trigger rate
≥ 99% or it's a contract violation").

## Adversarial counter-review before sending

Before the report leaves, have independent reviewers (subagents work well:
one methodology reviewer, one protocol expert, one adversarial defender playing
the vendor's side) attack the draft. In a real case this review demolished the
first draft's strongest wordings — "silently dropped / tokenization mutated" —
as unsupported by client-side evidence, and the surviving report was stronger
for it: every sentence the vendor reads is one they cannot push back on.

The reviewers' mandate: for each claim, ask "what would the vendor's engineer
say to dodge this?" and either close that door with evidence or soften the
claim to an observation.

## Confidence tiers in the written report

Never present excluded, supported, and speculative on the same line. Mark them:

- **Excluded (evidence attached)**: "not LB stickiness — new connections hit,
  same-connection repeats missed"
- **Supported but unconfirmed**: "consistent with partial channels not
  forwarding the field — needs your outbound trace"
- **Untested alternative**: listed at the end, clearly labeled

A report that flattens these tiers reads as either arrogant (everything stated
as fact) or mushy (everything hedged); tiering is what makes it read as
engineering.

## Template skeleton

```
Title: <feature> not taking effect on <model(s)> — 100% reproducible on <entry-point model>

Problem: <2-3 sentences: what was sent, what was observed, rate over N samples,
control group result>

Reproduction: <one curl, runnable as-is, expected vs actual>

Self-audit already done: <payload SHA-256 identical / thresholds exceeded /
retries=0 / trust_env off / probe validated on control>

Log pointers: <table: timestamp+TZ, model, key metric, request id> — include
one failing and one succeeding adjacent pair when intermittent

Prior related report: <if a same-channel issue was reported before: date,
contact, status — an unresolved prior case belongs in the new one>

Ask: please trace these request IDs outbound and confirm whether <field> is
present in what reaches the upstream; <entry-point> reproduces 100% for
verifying any fix.
```
