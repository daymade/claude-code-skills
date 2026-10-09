---
name: native-job-readback
description: >-
  Compare an explicit expected plist with one loaded GUI job's native launchctl
  configuration. Read before declaring a plist edit active or diagnosing environment drift.
---

# Read back native job configuration

1. Select the exact expected plist from the owning installer's current contract.
   Do not infer it from a first matching label, a log path, or a shell environment.
2. Run the bundled stdlib helper from the current GUI user's session:

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
   `disabled` to be false before describing the job as enabled.
5. Verify the owning job's completed native round and business output separately.
   Do not use `loaded: true`, a matching configuration or a running process as
   proof of successful work, public-output freshness or failure-path health.

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
- Use `--timeout <seconds>` only within `(0, 30]`; retain the default 5 seconds
  per command otherwise. Expect exactly two read-only native commands:
  `launchctl print` for the service and `launchctl print-disabled` for its GUI
  domain. Do not install, reload, restart or signal jobs through this helper.
  Accept native disabled-state entries expressed as `enabled` / `disabled` or
  `false` / `true`; preserve unknown for other forms or duplicate entries.
- Keep output limited to status, label and boolean/null flags. Do not print
  native output, expected argv, environment values, exceptions or logs to
  compensate for an unknown result. Expected argv may itself contain secrets.

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
