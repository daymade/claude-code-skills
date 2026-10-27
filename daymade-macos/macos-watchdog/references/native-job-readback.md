---
name: native-job-readback
description: >-
  Compare an explicit expected plist with one loaded GUI job's native launchctl
  configuration. Read before declaring a plist edit active or diagnosing environment drift.
---

# Read back native job configuration

1. Select the exact expected plist from the owning installer's current contract.
   Do not infer it from a first matching label, a log path, or a shell environment.
2. Run the bundled stdlib helper with Python 3.10+ from the current GUI user's session:

   ```bash
   python3 "<skill-directory>/scripts/inspect_native_job.py" --plist "<expected-plist>"
   ```

3. Read one JSON result and its exit code: `match` / 0, `mismatch` / 1,
   `unknown` / 2. Treat command failure, timeout, invalid plist, unsupported text
   shape, wrong service target and ambiguous sections as incomplete evidence.
   Keep the result unknown; do not repeat a disruptive action to obtain green.
4. Compare the returned flags with the changed configuration. Require
   `program_match`, `arguments_match` and `environment_match` to be true;
   require each configured working-directory/output-path flag to be true.
   Treat null path flags as unconfigured, rather than verified matches. Require
   `disabled` to be false before describing the job as enabled. Require the
   scheduling comparisons in § Scheduling flags to be true, including when
   an expected key is absent. Null scheduling flags mean incomplete evidence.
5. Complete [ordinary-entry and recovery acceptance](../SKILL.md#bind-the-ordinary-entry-before-choosing-a-mechanism)
   separately from this configuration comparison. Before declaring the job healthy,
   follow the [failure-path checks](../SKILL.md#troubleshooting-quick-map).

## Apply the helper's supported boundary

- Supply a plist with a valid `Label` and nonempty `ProgramArguments` whose first
  element is absolute. Use this helper only for `gui/<current uid>/<Label>`;
  use the owning daemon procedure for system jobs or another user's domain.
- Compare argument order and the effective program (`Program` when supplied,
  otherwise the first argument). Compare only configured `WorkingDirectory`,
  `StandardOutPath` and `StandardErrorPath` values.
- Read explicit ENV exclusively from the direct job `environment = { … }`
  block. Compare its complete key/value map with `EnvironmentVariables`;
  disregard launchd's `OSLogRateLimit` only when the expected plist did not
  configure it. Disregard `XPC_SERVICE_NAME` equal to the job label only when
  that key is unconfigured. Compare either key exactly when it is configured.
  Do not borrow values from
  `default environment` or `inherited environment`. Treat missing/empty explicit
  ENV as an empty map, which fails any nonempty expected ENV.
- Preserve unknown for values this text format cannot represent unambiguously
  (for example multiline arguments). Do not normalize them into a match.
- Leave `--timeout` unset unless the task needs an override; the
  [helper](../scripts/inspect_native_job.py) defines its accepted range and default.
  The read-only native commands are
  `launchctl print` for the service and `launchctl print-disabled` for its GUI
  domain. Do not install, reload, restart or signal jobs through this helper.
  Accept native disabled-state entries expressed as `enabled` / `disabled` or
  `false` / `true`; preserve unknown for other forms or duplicate entries.
- Compare scheduling through the scheduling flags below, read from
  the same service print. Preserve unknown for scheduling shapes the native
  text cannot represent unambiguously.
- Keep output limited to status, label and boolean/null flags. Do not print
  native output, expected argv, environment values, exceptions or logs to
  compensate for an unknown result. Expected argv may itself contain secrets.

## Scheduling flags

Read `start_interval_match`,
`watch_paths_match`, `run_at_load_match` and `keep_alive_match` as boolean/null
comparisons, not copies of the loaded values.

- Configured expected key: require the flag to be true only when the loaded
  job's scheduling equals the expected value. A changed StartInterval, a
  missing/extra/replaced WatchPaths entry, or a flipped RunAtLoad or KeepAlive
  is a mismatch.
- A missing expected key is meaningful: a stale loaded timer against no
  expected StartInterval is a mismatch, not a pass. Apply the same rule to
  every scheduling key — an absent expected key never waives a stale loaded
  value. Compare against launchd defaults: RunAtLoad and KeepAlive default to
  false, so a loaded true against an absent expected key is a mismatch;
  StartInterval and WatchPaths have no default, so any loaded value against an
  absent expected key is a mismatch.
- Treat null as unreadable or unsupported. An absent expected key with a
  provably absent/default loaded value is a verified match, not null.
- Supply a positive integer `StartInterval`, strict boolean `RunAtLoad`, and
  either a boolean `KeepAlive` or the single-condition dictionary
  `{SuccessfulExit: <boolean>}`. Compare that conditional form through the
  captured `semaphores` / `successful exit => 0|1` representation; leave other
  or combined conditions unknown. A conditional native block never proves a
  boolean-off expectation matches merely because the `keepalive` flag is absent.
- Supply `WatchPaths` as a nonempty list of absolute single-line paths without
  quotes or backslashes. An empty, null or malformed configured value is invalid
  input, not the absent-key default. Require the indexed quoted descriptor,
  correct service and FSEvents stream; unfamiliar representations stay unknown.
- Require the native `properties` line to establish both enabled and disabled
  boolean flags. Do not infer false from a missing line. Read `StartInterval`
  through `run interval = N seconds`; unparsed trigger families or timer
  descriptors leave that comparison unknown. An expected `StartCalendarInterval`
  also prevents an overall match: this helper does not compare calendar rules.
- Within a parsed service, a definite field mismatch takes precedence over an
  unrelated unresolved scheduling field. Preserve the existing caller boundary:
  an unreadable disabled-state probe makes the overall result unknown even if
  a service-field flag is false; an explicit disabled override is a mismatch.
- Unknown/unsupported native format is never success: when the loaded
  scheduling state cannot be read unambiguously from the native text (for
  example a KeepAlive dictionary form the format cannot represent), keep the
  flag null and the result unknown. Do not normalize it into a match.

Limit a `match` claim to these compared fields. Other plist policies and trigger
families are outside the helper's coverage; inspect them through their owning
procedure when the task depends on them. Configuration equality does not prove
that a service stays idle or that a filesystem event reaches its consumer.

## Reuse and verify the parser

Import `inspect_job_print(expected, text, uid)` for an existing caller that
already owns native readback; use `inspect_disabled_print(text, label)` for the
disabled-state output. Keep capture, timeout and nondisclosure responsibilities
with that caller rather than adding a second scheduler.

Run the synthetic native-shape regression suite after changing the helper:

```bash
python3 -m unittest discover -s "<skill-directory>/tests" -v
```

Require both the healthy explicit-ENV control and the default-first,
missing/empty explicit-ENV, wrong-target, ambiguous-section, command-failure and
sensitive-value nondisclosure controls to pass. Obtain live native acceptance
through an authorized owned job; synthetic parsing tests do not establish that
the host's current launchctl format or business output was accepted.
