# Chromium code-sign clones: targeted diagnosis and cleanup

Use this reference when Chrome, ChromeDriver, Playwright, Codex Computer Use,
Microsoft Edge, Chromium, or another Chromium-based browser leaves
`*.code_sign_clone/code_sign_clone.*` directories under the current user's
`/private/var/folders/.../X/` directory.

## Contents

- What these directories are
- Read-only inventory
- Interpret size and activity evidence
- Plan an exact cleanup
- Execute only the approved manifest
- Verify actual release and recurrence
- Prevent recurrence
- Failure handling
- Sources

## What these directories are

Chromium creates one temporary clone per browser instance so an in-use app
bundle remains reachable and code-signature-valid while an installed browser
update is staged. Chromium's implementation uses an APFS copy-on-write clone of
the app bundle plus a hard link for the main executable. It expects the cleanup
helper to delete that instance-specific directory after the browser exits.

APFS clones share unchanged blocks. A clone can therefore present as a complete
multi-gigabyte app tree without owning that many unique blocks. Treat `du -sk`
as **path-accounted allocation**, not as a prediction that deleting the path
will increase `df` by the same amount. The only authoritative result for the
cleanup is the before/after `df -k /System/Volumes/Data` delta.

The clone contains an application bundle, not the browser profile. Do not widen
this branch to the installed browser app, `--user-data-dir`, downloads,
credentials, or any other browser state.

## Read-only inventory

Run the bundled analyzer from the skill directory:

```bash
uv run scripts/analyze_code_sign_clones.py
```

The default scope is deliberately narrow. It resolves the current user's
`DARWIN_USER_TEMP_DIR`, inspects only sibling `X/*.code_sign_clone` roots owned
by that user, validates the expected `code_sign_clone.XXXXXX` child shape, reads
the bundle version, measures path-accounted blocks, and performs one canonical
root `lsof +D` scan. It does not delete, stop, or configure anything and does
not write a manifest.

For an already-known exact root, avoid discovery:

```bash
uv run scripts/analyze_code_sign_clones.py \
  --root "/private/var/folders/<bucket>/<user>/X/<bundle-id>.code_sign_clone"
```

Use `--json` when a machine-readable evidence record is helpful. Preserve the
command output in the report; redirecting it to a file is a local write and
belongs in an explicitly listed plan when the phase must remain read-only.

## Interpret size and activity evidence

Read the analyzer's three independent signals:

| Signal | Meaning | Decision use |
|---|---|---|
| `path-accounted total` | Blocks attributed to paths by `du`; APFS shared extents may be counted repeatedly | Surface the hotspot, but never promise this amount as physical release |
| `active` | `lsof` named an open file below that exact child | Preserve; do not delete it |
| `inactive` | The root scan completed and named no open file below a structurally valid, current-user-owned child | Eligible for an exact user decision, not automatically disposable |
| `unknown` | The `lsof` scan was incomplete or structure/ownership/size evidence failed | Preserve and investigate; never convert unknown to inactive |

Do not infer activity from `lsof`'s exit code alone. Apply these rules:

- Treat every output record naming a target path as definitive evidence that
  the target is active, even if the command later exits nonzero.
- Treat exit 1 with empty stdout and stderr as the no-open-files result.
- The bundled `lsof` 4.91 observed during validation returned 1 while printing
  valid `+D` matches. Treat exit 0 or 1 with empty stderr as a completed scan;
  named paths are active and unmatched validated children are inactive.
- Treat a timeout, stderr, or an exit outside 0/1 as an incomplete scan. Named
  paths remain active; unmatched paths become unknown rather than inactive.
- Canonicalize `/var` to `/private/var` before matching. Otherwise the same file
  can appear under two spellings and produce misleading selection behavior.

Also capture browser and launcher process command lines. A running browser is
not itself proof that every old child is active; the path-level open-file result
decides each child. Conversely, an empty process-name search does not replace
the path-level scan.

### Rank this hotspot honestly

Show both columns whenever this hotspot competes with Docker, package caches,
or other large candidates:

1. **Observed path-accounted size** — the large number the user can see.
2. **Expected physical release and confidence** — `unknown` for APFS clone
   sets until deletion and `df` readback.

Rank executable cleanup candidates by defensible expected physical release,
safety, and effort, but never hide or silently demote the largest nominal
hotspot. Explain the uncertainty before choosing a smaller candidate. A path
that looks ten times larger may physically release less than a smaller cache;
that is a measurement boundary, not a reason to omit the path from the report.

## Plan an exact cleanup

Before asking for approval, report:

- the exact canonical clone root;
- each exact inactive candidate, or the candidate count plus SHA-256 and an
  attached/displayed exact path list;
- every active, unknown, or otherwise preserved child;
- the path-accounted total, clearly labeled as nominal;
- expected physical release as unknown until `df` readback;
- permanent-deletion impact and recovery: the browser can recreate its clone,
  but the deleted directories do not go to Trash;
- the exact manifest-creation and dedicated deletion commands;
- protected browser/automation process invariants;
- postconditions and a bounded refill observation.

For a nominal batch above 10 GiB, recommend a current backup before permanent
deletion even though the content is reconstructible. Do not describe it as
“absolutely safe”; a mistaken target is still permanent.

If one child is active or unknown, explicitly preserve it in the approved plan.
Its later transition to inactive does not expand the approved target set.

## Execute only the approved manifest

After explicit approval, create the content-bound manifest by repeating every
read-only check. Pass every preserved child through `--exclude`, even if it may
have exited since the plan was shown:

```bash
uv run scripts/analyze_code_sign_clones.py \
  --root "/private/var/folders/<bucket>/<user>/X/<bundle-id>.code_sign_clone" \
  --exclude "/private/var/folders/<bucket>/<user>/X/<bundle-id>.code_sign_clone/code_sign_clone.<kept>" \
  --expect-candidate-sha "<approved-sha256>" \
  --write-manifest "/private/tmp/macos-cleaner-code-sign-clones.txt"
```

The analyzer refuses to overwrite a manifest, rejects a changed candidate hash,
and emits no active or unknown child. A newly active approved target disappears
from the candidate set and changes the hash, so execution stops. A preserved
active child that has since become inactive remains excluded and does **not**
cause a false plan-expiry failure.

If the command stops, do not weaken the check or regenerate a wider manifest.
Re-run the read-only report and ask again only when the exact approved target
set must change.

Start the generic exact-path helper only after the manifest count and SHA are
read back:

```bash
/usr/bin/wc -l /private/tmp/macos-cleaner-code-sign-clones.txt
/usr/bin/shasum -a 256 /private/tmp/macos-cleaner-code-sign-clones.txt
uv run scripts/safe_delete.py \
  --batch /private/tmp/macos-cleaner-code-sign-clones.txt
```

When `safe_delete.py` reaches its interactive selection prompt, leave that
prompt waiting. In another shell, repeat the analyzer command with the same
`--root`, every approved `--exclude`, and `--expect-candidate-sha`, but omit
`--write-manifest`. Enter `all` only if that final read-only check passes. If it
fails, enter `none` or cancel; do not regenerate a different list inside the
approved execution phase.

This is a normal local-maintenance guard, not an adversarial deletion engine. It
assumes no hostile same-user or privileged process is replacing clone paths or
changing mount topology in the gap between the final check and deletion. If
automation is actively relaunching browsers, a privileged maintenance process
is changing mounts, or that assumption is otherwise false, stop: quit the
owning browser/launcher or reboot, then restart diagnosis from a stable state.

The helper rejects a changed manifest with missing paths and stops after the
first deletion failure, leaving later targets untouched. Its measured total is
still `du` path accounting rather than physical release. Never replace the
manifest with the clone root, a wildcard, `find -delete`, or a recursive shell
deletion.

## Verify actual release and recurrence

Independently verify all clauses:

1. Confirm every manifest path is absent by reading the manifest one exact line
   at a time. Do not use a shell glob.
2. Confirm preserved paths were not deleted by this operation. Record if the
   browser's own cleanup removed one naturally.
3. Re-run the analyzer and record remaining/new clone counts and statuses.
4. Re-read `df -k` and `df -h` on `/System/Volumes/Data`. Calculate actual
   physical release from the `Available` KiB delta, not from `du` or the delete
   helper.
5. Re-resolve protected Chrome/Chromium/Edge and automation processes. Confirm
   the user-visible browser and required sessions remain healthy.
6. Observe at 0, 15, and 30 seconds. A new clone associated with a currently
   running browser may be legitimate; repeated inactive growth means the
   launcher/lifecycle source remains unfixed.

Report nominal reduction and physical release side by side. A large nominal
reduction with little `df` movement is a valid result that demonstrates block
sharing; do not relabel it as a large physical cleanup.

## Prevent recurrence

Trace the current launcher and executable before changing configuration. For
automation that supports an explicit browser executable, prefer Chrome for
Testing when it meets the user's compatibility needs: current Chromium source
disables this auto-update-specific clone feature in Chrome for Testing because
that build does not support auto-updates. Verify the configured executable and
the next real process command line; a configuration edit alone is not proof.

If the workflow must use an installed auto-updating Chromium browser, fix the
source by reusing the managed browser where appropriate and awaiting graceful
browser shutdown so Chromium's cleanup helper can run. Do not kill a user's
interactive browser, change their default browser, install another runtime, or
enable unattended recurring deletion without a separate explicit plan and
approval.

## Failure handling

| Observation | Response |
|---|---|
| No clone root exists | Report no current target; do not create one |
| `lsof` incomplete | Preserve unmatched children as unknown; retry read-only or stop |
| Candidate SHA changed | Plan expired; do not write or delete from a regenerated wider list |
| An approved candidate became active | Stop; preserve it and obtain a new decision for the reduced set if cleanup should continue |
| A preserved child became inactive | Keep it excluded; proceed only if the approved candidate SHA still matches |
| Final analyzer recheck fails while the delete prompt waits | Cancel the prompt; return to read-only diagnosis and do not widen the manifest |
| A manifest target disappears before the helper prepares the batch | The helper stops before confirmation; record the changed state and re-plan if needed |
| A deletion fails after the batch starts | The helper stops after that first failure; verify the failing and completed paths before any retry |
| Browser automation or privileged mount changes can continue during deletion | Stop; stabilize or reboot the owning environment before restarting diagnosis |
| Delete helper reports tens of GiB but `df` moves little | Report nominal vs physical truth; do not claim the helper's number |
| Clone count refills quickly | Diagnose the launcher and shutdown lifecycle before another cleanup |

## Sources

Verified 2026-08-31:

- Apple, [About Apple File System](https://developer.apple.com/documentation/foundation/about-apple-file-system): clones share unchanged blocks; APFS volumes share container free space.
- Chromium, [`code_sign_clone_manager.h`](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/mac/code_sign_clone_manager.h): lifecycle, per-instance clone purpose, expected cleanup, and copy-on-write behavior.
- Chromium, [`code_sign_clone_manager.mm`](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/mac/code_sign_clone_manager.mm): current implementation, clone-count telemetry, and Chrome for Testing exclusion.
- Chromium issue [379125944](https://issues.chromium.org/issues/379125944): ChromeDriver cleanup defect tracked by the implementation.
