# Development preview CPU and safe reuse

Use when a Node development server consumes CPU while its page is idle. First
bind the port to its PID, command, working directory, start identity and current
owner. A `node` label or a listening port alone does not establish ownership.

Inspect the actual watcher implementation and effective options. In the observed
Vite case, a missing native-event dependency selected frequent polling; a shared
dependency symlink widened the work. Do not diagnose every Node CPU incident as
that case or require one native dependency across all watcher versions.

## Repair the watched work

- Prefer native file events when supported by the actual platform/version.
  Reject unexpected environment-forced polling rather than silently accepting
  it. If polling is genuinely required, scope it and measure its cost explicitly.
- Watch source directories and necessary root configuration by allowlist.
  Keep dependencies, generated copies, caches and large media outside it; check
  resolved symlink targets as well as lexical paths. Disabling symlink traversal
  is appropriate only when linked source is not part of the supported workflow.
- Verify effective runtime options. Config text alone does not prove a running
  server adopted them. Use an existing supported reload path only when it
  preserves current work and the owner's authorization permits it.

## Reuse and retire the exact instance

Keep start/reuse/status/check/stop under the project's existing launcher. Bind
instance reuse to the project root, port, PID/start identity and owner. Unknown
or foreign services occupying the port must fail closed; do not adopt or stop
them. An owner field or local stop token authenticates an instance, not the
user's permission to interrupt someone else's work.

Failed startup may retire only the child it just created. For an authorized
stop, revalidate the binding, request graceful exit and confirm port release.
Leave a shared preview running when continued use is the requested deliverable;
report its owner and consuming URL. Do not add an automatic kill watchdog.

## Verify the result without losing the page

Measure CPU-time delta over a fixed interval, expressed as percent of one core:
`100 × CPU seconds / wall seconds`. Keep PID identity stable across the interval.
Distinguish startup/build/HMR activity from an actual idle window. Missing,
null, stale or non-finite samples are unknown, not zero. Set the idle budget
from this project's workload; the observed case's budget is not a global limit.

Require both reduced idle work and preserved behavior: real page, media and
selection state still work, an actual source edit triggers HMR, and temporary
test edits are restored. Exercise unexpected polling, foreign-port reuse,
missing measurements, excessive idle CPU and failed-start child cleanup.
An HTTP 200, safe-looking config or one instantaneous CPU reading is insufficient.
