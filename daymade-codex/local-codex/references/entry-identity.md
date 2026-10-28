# Entry identity baseline and check

An opt-in seam for claims that depend on *which* codex entry is in play. It
records, once, how the owning shell dispatches `codex` and which external
executable the wrapper resolves, then compares the frozen observation at the
moment of an expensive build, resume or recovery claim.

## Contents

- [Scope and boundaries](#scope-and-boundaries)
- [The two identities](#the-two-identities)
- [Commands](#commands)
- [Exit codes](#exit-codes)
- [Baseline fields (schema `entry-identity-baseline-v1`)](#baseline-fields-schema-entry-identity-baseline-v1)
- [Unknown, never unchanged](#unknown-never-unchanged)
- [Interpreting a check](#interpreting-a-check)
- [Startup report example](#startup-report-example)
- [Limits](#limits)

## Scope and boundaries

- This seam answers one question: **did the codex entry identity change since
  the frozen baseline?** It runs only the selected external executable's
  `--version`, submits no model turn and invokes no account or network query.
- The wrapper's resolution order (`CODEX_BIN` > PATH > ChatGPT.app bundle) and
  its bad-override refusal are unchanged; this script reuses
  `codex_wrapper.find_codex_binary()` as-is.
- The `/bin/zsh -lic` inspection runs shell initialization and inspects the
  `codex` name with `whence`/`functions`/`alias` — it never executes the codex
  function, alias or binary outside the single `--version` rule below.
- Identity is one input among several. A live runtime, authentication, quota,
  process-adoption and model health stay separate facts with their own owners
  (see [the OAuth guide](oauth-guide.md)); this seam contributes no evidence
  about them.

## The two identities

| Identity | Observer | Recorded |
|---|---|---|
| **Dispatch** (caller-selected owning shell) | one bounded `/bin/zsh -lic` probe | kind (`external`/`function`/`alias`/`builtin`/`reserved`/`hashed`/`not_found`), the PATH-resolved external path when the kind has one, and for functions/aliases the definition's SHA-256 and size — hashed in memory, never emitted or stored |
| **Executable** (wrapper-selected) | `find_codex_binary()` reuse | source, path, realpath, symlink target, streamed SHA-256, size, and a bounded recognized `--version` token |

A function or alias consumer stays opaque. The definition is hashed, never
executed, so the executable it would ultimately run cannot be derived here;
verify its target through the launcher's owner. `CODEX_BIN` selects the wrapper
and does not establish an independent function's target. A PATH-resolved path
under a function is what the wrapper would select, not what the interactive
shell would run.

## Commands

```bash
# Freeze once, before the work.
python3 scripts/entry_identity.py snapshot --output <task-owned-baseline.json> \
  [--watch-file <owner-selected-config> ...]

# Compare at claim time. Shell and watched set come only from the baseline;
# check accepts no other selections and never writes the baseline.
python3 scripts/entry_identity.py check --baseline <task-owned-baseline.json>
```

- `--output` is task-selected and exclusive: an existing file is never
  overwritten (`output_exists`, exit 3). Refreshing a baseline is an explicit
  owner action (delete or rename first).
- `--watch-file` (repeatable) fingerprints owner-selected configuration files
  with the same content/symlink rules as executables. It is a generic
  file-identity option with no private schema.
- Without `--output`, snapshot prints the envelope to stdout only.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | snapshot fully observed / check: identity unchanged |
| `1` | check: drift — at least one identity component changed |
| `2` | snapshot or check: unknown — a component could not be established (timeout, noise, refused override, failed or unrecognized version, unobservable dispatch) |
| `3` | usage error, unsupported shell, refusing to overwrite output, or a malformed/incompatible baseline |

`snapshot` exits `2` when its own observation is incomplete; do not freeze such
a baseline for later comparison without recording why. `check` reports
`result: drift` when any component drifted, even alongside unknowns.

## Baseline fields (schema `entry-identity-baseline-v1`)

Strict, fail-closed reader: missing, null, empty, extra or wrongly typed
fields are usage errors (exit 3), and required fields are enforced per status —
an `observed` executable must carry path, realpath, content SHA-256 and size,
while the same fields must be null on a `not_found` observation. The persisted
file contains exactly: `schema`, `captured_utc`, `shell`, `code_name`,
`watch_files`, `dispatch`, `executable`, `watch`.

| Field | Present when | Meaning |
|---|---|---|
| `dispatch.kind` | observed | `external`, `function`, `alias`, `builtin`, `reserved`, `hashed`, `not_found` |
| `dispatch.reported_path` | external/hashed | PATH-resolved external path the probe saw |
| `dispatch.definition_sha256` / `definition_bytes` | function/alias | definition hash and size, hashed in memory only |
| `executable.source` | observed | `codex_bin_override`, `path`, `app_bundle` |
| `executable.path` / `realpath` | observed | selected path and its resolved real path (symlinks preserved in `is_symlink`/`symlink_target`) |
| `executable.content_sha256` / `size_bytes` | observed | streamed content fingerprint |
| `executable.version` / `version_status` | observed | recognized codex version token; `unknown` when the `--version` probe failed, timed out or was unrecognized |
| `watch` | selected files | per-file status, realpath, symlink target, content hash, size |

Comparison fields: dispatch kind, reported path and definition hash; executable
source, path, realpath, symlink target, content hash and size, plus version
when both sides recognized it. mtime never participates: touching a file
without changing bytes is `unchanged`, and retargeting a symlink is drift even
when the pointed-to content is identical.

## Unknown, never unchanged

Mark unsupported, unreadable, ambiguous, noisy, truncated and missing-payload
shell observations as `unknown`; never compare them as unchanged. Reasons
include `unsupported_shell`, `shell_not_executable`, `shell_probe_timeout`,
`shell_probe_failed`, `noisy_output`, `ambiguous_markers`, `missing_payload`,
`malformed_payload`, `ambiguous_definition` (a function and an alias both
defined for `codex`), `definition_too_large`. A clean `whence -w` report of
absence is recorded as `not_found` — a definite observation, comparable to a
later `not_found`.

## Interpreting a check

- **Compare before the claim, never after the fact.** Run `check` immediately
  before an expensive build, resume or recovery action. `never refresh
  automatically`: a passing check must not be manufactured by re-snapshotting.
- **Drift means re-attribute.** A content/version drift between baseline and
  now is the mid-task entry-switch shape: claims stay attributed to the build
  that actually ran, not the baseline build.
- **`function`/`alias` dispatch means bind before build.** The wrapper-selected
  executable is evidence about the wrapper, not about the interactive entry;
  the owner must verify the function's downstream executable before any
  build/resume claim that names the ordinary entry.
- **Unchanged is narrow.** It never proves downstream runtime, authentication,
  quota or model health, adoption by a running TUI, or that a candidate build
  was deployed; keep those with their owners (see
  [the OAuth guide](oauth-guide.md)'s [existing-session recipe](oauth-guide.md#check-existing-sessions-separately)
  and [verification route](oauth-guide.md#verification)).

### Startup report example

Illustration with placeholder values only; run the commands to get real ones.

```text
$ python3 scripts/entry_identity.py check --baseline /tmp/task/entry-baseline.json
{"result": "drift", "exit_code": 1,
 "findings": [
   {"component": "executable", "field": "version",
    "baseline": "0.160.0", "current": "0.165.0"},
   {"component": "executable", "field": "content_sha256",
    "baseline": "61b0…", "current": "9a2c…"}],
 "unknowns": [],
 "dispatch": {"status": "observed", "kind": "function", ...},
 "executable": {"status": "observed", "source": "path", "path": "<install-prefix>/bin/codex", ...},
 "watch": {...},
 "scope_note": "identity_only: unchanged does not establish wrapper downstream runtime, authentication, quota or model health"}
```

Keep the report's evidence claims separate:

1. **Entry moved mid-task.** The frozen baseline named one build; the wrapper
   now resolves a different one (0.160.0 → 0.165.0). Any stale-native-build
   claim made against the baseline build is unattributed until re-established.
2. **Dispatch is a function — the interactive consumer stays opaque.** The
   wrapper-selected path is wrapper evidence only; bind the function's
   executable through its launcher's owner before a build claim that names
   the ordinary entry. `CODEX_BIN` selects the wrapper; it does not redirect
   or verify an independent shell function.
3. **Restored externally is not adoption.** A later `unchanged` after the owner
   restored an install proves identity only; whether a running TUI adopted the
   restored entry is the OAuth guide's separate session-evidence question.
4. **Agent edits and undeployed candidates are different facts.** An agent
   rewriting a launcher shows up as definition drift; a candidate build sitting
   in a build directory changes nothing here — unchanged never proves a
   candidate was deployed. And identity evidence is neither TUI-only nor
   model-turn proof: server-side access stays with the OAuth guide's
   verification route.
5. **Keep incident attribution separate.** Report a lifecycle unit test as a
   reproduced mechanism. Without a matching trace or reproduction through the
   original owning entry, retain the cause of the user's startup crash as
   unconfirmed. A later healthy entry does not establish that cause.

## Limits

- Only `/bin/zsh` is supported; other shells are refused instead of
  approximated. The probe depends on zsh's `whence`/`functions`/`alias` and on
  bounded capture with markers; noisy init output above the capture cap, timed
  out init, or non-unique markers are `unknown`, never a best guess.
- Every subprocess is finite (shell probe 20 s, `--version` 15 s) and
  output-bounded (1 MiB shell capture, 64 KiB definition, 2 GiB hash budget);
  hashes stream in chunks. stderr of the shell probe and the version probe is
  counted, never printed, and no environment values are exposed beyond the
  identity paths themselves.
- `--watch-file` is a generic owner-selected file-identity list; it carries no
  private schema and reuses the executable fingerprint rules.
