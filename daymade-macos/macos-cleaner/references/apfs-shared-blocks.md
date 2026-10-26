# Preserve local paths with APFS copy-on-write

Use only for an explicitly authorized, bounded set of inactive identical local
files whose paths, bytes and offline availability must remain. This changes the
target inode and ctime; it is not a backup or a generic release-retention policy.
Excluded data, credentials, chat records, active releases and in-use application
state remain excluded. Obtain the owning application's inactive/reference evidence
before preparing pairs. An arbitrary lock file does not prove that evidence.

## Prepare and inspect

Requires macOS/APFS, system `lsof` and the bundled native helpers. The executor
uses forced APFS clone creation, metadata overlay and atomic swap; unsupported
native operations fail without a byte-copy fallback. It refuses hard links,
symlinks, protected paths, cross-device pairs and already-shared target streams.
No recursive discovery or deletion of source paths is provided.

From this skill directory, create an exact pair list outside the bundle:

```json
[{"source":"/absolute/retained/file","target":"/absolute/duplicate/file","kind":"ordinary"}]
```

```bash
python3 scripts/apfs_cow.py prepare --pairs /absolute/pairs.json --output /absolute/candidate.json --reserve-bytes 20000000000
python3 scripts/apfs_cow.py check /absolute/candidate.json
```

Choose reserve bytes for this host, not from the example. Budget a full target-sized
temporary copy in addition to reserve even though cloning is expected to share
blocks. Native clone-state prescreen precedes full hashing. Compare full content,
identity, owner/mode, timestamps, flags, ACL and xattrs; resource-fork/unsupported
metadata cases fail closed. The target's access time may advance during checking;
the executor preserves its actual pre-operation value. Other frozen metadata and
source identity remain strict. Tools and parent-directory identities are bound.

Ordinary pairs use exact-pair occupancy checks. Do not apply a global Git-LFS veto
to unrelated ordinary files. For LFS use `kind: "lfs"`, `repo`, `pointer_ref` and
`work_relative`; bind the immutable Git pointer, full object hash and cooldown.
The LFS branch additionally requires the global LFS-activity guard. Never weaken
that guard to finish a batch. Pilot first, then follow [batch selection](batch-selection.md).

## Execute and yield safely

Resolve authorization for the exact prepared targets and inode-changing effect.
A manifest hash binds input; possession of it grants no permission.

```bash
python3 scripts/apfs_cow.py execute /absolute/candidate.json --approved-manifest-sha256 <full-sha256> --run-dir /absolute/new-run --pause-file /absolute/pause-request
```

Every item rechecks identity, bytes, metadata, native state, free-space reserve
and fresh `lsof`. Nonempty stderr or ambiguous process visibility is unknown,
not proof of inactivity. These checks cannot provide a kernel-wide compare-and-
swap guarantee against arbitrary concurrent writers; do not use on active state.

If the application's existing lock protocol permits this operation, supply its
existing lock to `prepare --lock-file /absolute/existing.lock`. The executor takes
a nonblocking exclusive lock per item and releases it at the item boundary.
Never create a substitute lock to bypass a publisher. Request a pause by creating
the declared marker; the next boundary writes a paused summary. Confirm that
summary and independently probe the official lock before promising a publication
window. Do not kill processes, remove locks or assume silence grants a window.

## Recovery and readback

An atomic swap retains the exact old inode until postconditions pass. A failed
postcondition swaps it back only while both path identities still match; an
external replacement stops recovery instead of being overwritten. Successful
completion removes only the executor's pinned temporary inode.

```bash
python3 scripts/apfs_cow.py remainder /absolute/candidate.json --summary /absolute/new-run/summary.json --output /absolute/remainder.json
```

The remainder verifies the completed prefix's identity, metadata and shared clone
state before selecting the exact pending subset. It never reruns the prefix or
refreshes mismatched pending evidence. A rollback can itself change ctime and
therefore refuse automatic resume: inspect that item and prepare a separately
reviewed batch rather than silently accepting drift. A new manifest digest needs
authorization under the existing exact-scope conditions.

After a hard interruption, inspect the run's receipts, both path identities and
any retained temporary inode before any retry. Do not infer rollback or success
from a missing summary. No automatic crash-recovery command is provided.
Verify retained paths/bytes/metadata and source identity, native stream sharing,
no owned temporary leftovers, and unchanged Git HEAD/branch/WIP when relevant.
Report path-accounted bytes, native allocation bounds and actual host free-space
change separately; concurrent writes can conceal savings or produce a net decline.
