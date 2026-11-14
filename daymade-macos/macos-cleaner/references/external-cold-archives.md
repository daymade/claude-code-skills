# Relocate cold data to a removable disk

Use this for a selected inactive source whose bytes must survive on an SD card or
external disk. Keep the source until preservation and original-entry checks pass.
Relocation does not create a second independent backup or prove sustained free space.
For an existing copy, start at the lightweight verification section below; skip
copy creation and completed pilots.

## Bind the outcome and destination

1. Read [batch selection](batch-selection.md). Record the user's capacity unit,
   current internal free space, remaining gap and honest reclaim ceiling. Keep
   another authorized route moving when the candidate cannot close the gap.
2. Resolve the canonical source from the owning project/storage registry before
   guessing common workspace paths. Bind source, destination, host, requirements and current
   authorization. Preserve exclusions: a new SD decision for one asset does not
   supersede another asset's local-only or no-touch decision. A quiet `lsof` does
   not establish manual non-use. Use the owning application/VM lifecycle for its
   identity, state and consumer acceptance.
3. Inspect the selected mount with `diskutil info -plist <mount>` and its parent
   disk with `diskutil list`. Record physical device, capacity, volume UUID,
   filesystem, writable state and mount. Re-read the UUID before mutations;
   reject a missing volume or a different device at the same mountpoint. Names
   and device numbers are locators, not durable identity.
4. Check source readers, writers and scheduled writers. Coordinate rather than
   terminate unrelated processes. Recheck immediately before cutover; an earlier
   quiet observation does not cover the whole copy interval.

Probe installed copier, image and metadata-reader interfaces before using their
flags. Missing preservation support stops the affected transfer. Perform needed
preparation only within existing setup authorization, then resume at the first
unmet check; do not reinstall a working tool or weaken preservation to proceed.

## Choose storage that preserves the asset

Use a suitable native filesystem directly when available. For an exFAT card that
must remain unformatted while preserving Mac metadata, an APFS sparsebundle on
the card is one option. It is not the default for every external disk. Check the
installed commands and consumer compatibility with a small pilot. On systems
providing this `diskutil image` interface, the command shape is:

```bash
diskutil image create blank --format UDSB --size "$ARCHIVE_SIZE" \
  --volumeName "$ARCHIVE_NAME" --fs APFS "$IMAGE_PATH"
diskutil image attach --mountPoint "$ARCHIVE_MOUNT" "$IMAGE_PATH"
```

Set values from the selected task; require a new image path and unused mountpoint.
Do not overwrite an image, reformat the card or force-unmount an occupied volume.
A sparse image's maximum size does not reserve physical storage. Apply the entry's
copy budget to retained payloads and retry partials; keep the declared reserve on
both the outer filesystem and inner archive volume before every stage.

Store physical-volume and inner-archive UUIDs outside the Skill. Build the runtime
connection command from those identities: resolve the physical UUID to its current
mount, attach the selected image when needed, then verify the inner UUID before
consuming original entries. Refuse an occupied mountpoint with another UUID. Keep
parameters and the connection command with the runtime archive. Do not add an
automatic mount service without separate authorization.

## Pilot content and metadata before the full copy

Trial the real command on representative selected files: downloaded files with
quarantine attributes, symlinks, nested/read-only directories and sparse files
when present. Preserve originals and compare the actual result. For ordinary Mac
trees, the tested copy shape is:

```bash
ditto --nocache --noclone --rsrc --extattr --acl "$SOURCE" "$DESTINATION"
```

Require a new exact destination. For large sparse files, select a verified
sparse-aware copier instead; confirm installed flags and measure the pilot's
allocation separately from content equality. Never use a delete/mirror option
or flatten symlinks to make the pilot pass.

Capture a no-follow source inventory before copying: relative paths, entry types,
file sizes, mtimes and symlink targets. Include required modes, ownership, flags,
hard-link relationships, ACLs and xattrs according to the asset contract; use the
pilot to establish metadata fidelity rather than reading every payload. Keep raw
metadata needed for restoration in a private sidecar outside the payload. Fail on
unreadable required fields, unsupported entry types or incomplete traversal.
Do not require copied inode numbers, change times or unsupported timestamps to match.
Verify the resulting copy with the following procedure.

## Verify an already-copied directory lightly

Fix the acceptance before measuring: preserve local work and required data at the
destination, keep the original pathname usable, and retire only its internal copy.
Do not compute full-file hashes for every file or perform a full-byte readback of
the directory in this workflow. Metadata inventories and bounded content checks
support this relocation decision; they do not prove byte-for-byte equality.

1. Compare one complete no-follow entry inventory on each side: relative paths,
   types, sizes and symlink targets. State counts, logical bytes, missing/extra
   entries and traversal errors. Normalize names only with collision detection;
   account for filesystem timestamp precision separately from meaningful changes.
   Explicitly explain OS-generated extras such as `.DS_Store`; never ignore an
   arbitrary missing file. Reuse existing inventories while their inputs are stable.
2. For Git trees, compare repository presence, HEAD and refs, local branches,
   unpushed/staged/dirty work and untracked files. Check relevant Git control files
   and preserve local-only commits/objects before retirement. Treat regenerable
   dependencies and build caches separately. A `.git` directory does not establish
   that ignored media, LFS objects, managed evidence or other data exist remotely.
3. For data trees, consult the project's storage contract. Compare small manifests,
   registries and other control files by content; sample selected large assets at
   bounded positions and parse/decode representative files through their consumer.
   Record the selected paths and actual bytes read. Preserve local-only or
   unexplained material; do not replace managed-data interfaces with Git guesses.
4. Synchronize only the missing/changed set using a non-deleting copy. Verify that
   set and affected controls, then reconcile the inventory. Reuse unchanged checks;
   do not restart the entire verification after a metadata-only repair or a lost reply.
5. Save the evidence outside both payloads: exact identities, inventory coverage,
   local-only and metadata decisions, checks, resolved differences and remaining
   limits. Require positive coverage and explicit empty unresolved mismatch lists.
   A phase name or an empty command result is not proof.

Keep Finder's displayed folder total separate from filesystem evidence. Do not
claim an unfinished count or cache fault without evidence. Attribute an Agent's
changes only when a bounded authorized history/index query can identify them;
if attribution cannot change the exact delta to sync, stop that investigation and
complete the synchronization. Keep unknown attribution unknown.

Handle differences before cutover:

| Difference | Required action before cutover |
|---|---|
| Missing entry, content, size, type, symlink target or topology | Preserve the source; repair/re-copy and verify the affected set, then reconcile the inventory |
| Quarantine value, permissions, ACLs, timestamps or other required metadata | Restore the exact captured value and compare again; do not strip quarantine or weaken the whole comparison |
| Understood OS-generated provenance | Retain the original raw value and observed difference; allow only that specifically understood field, not arbitrary xattr loss |
| Changed source, unreadable field, missing coverage or stale proof | Preserve the source and mark proof incomplete; establish stable inputs before resuming |

Symlink mtime differs from its target's mtime; use a no-follow operation for an
exact timestamp repair. Treat a repair as metadata-only only when its bounded
operation, before/after identities and data-relevant state establish that no
payload changed. Otherwise recheck the affected content. Bind reusable evidence
to its source/destination identities and inputs; unexplained drift invalidates
the affected result, not every unchanged result in the archive.

## Switch the entry and retire only the redundant internal copy

1. Recheck UUIDs, the completed lightweight verification, source stability, holders and
   applicable source-retirement authority. Rename the source to an exact
   task-owned sibling on the same internal filesystem and retain it for rollback.
   Journal its identity, original entry and recovery path.
2. Create the agreed original entry to the verified external destination. A
   symlink preserves a pathname only for consumers that follow it. Read through
   that entry with the real consumer: decode media, read a project, or use the
   owning application control plane. On failure, remove only the newly created
   alias and rename the retained source back; do not delete either payload or
   overwrite a path changed by another writer.
3. Under applicable relocation/deletion authority, retire only the exact verified
   redundant internal tree. Recheck identity and references immediately before
   retirement. Preserve unknown or changed objects. Never use the alias or the
   resolved archive destination as the deletion target.
4. Independently read internal same-volume `df` and the original entry. Separate
   timestamped final free space, mixed-window net change and logical archived
   bytes. Continue authorized work if the capacity gap remains. One watermark
   does not establish sustained headroom.
5. Check archive filesystem holders. When quiet, safely eject the exact image,
   confirm its mount is absent, run the connection command, verify its UUID and
   consume the original entry again. Do not force an occupied volume. State
   whether the evidence covers image reattachment, physical card reinsertion or
   reboot; one does not establish the others. Keep unavailable checks pending.

Keep verification and recovery evidence on the archive and in the existing task
record. Explain which assets need the mounted card, how to reconnect, and how to
eject the inner archive before the outer card. After interruption, inspect actual
paths/UUIDs and the journal: resume copying/verification with source retained,
roll back a failed switch, or finish only pending retirement/readback. Never repeat
a completed copy or delete a retained tree solely because a process lost its reply.

## Execute and resume the cutover

Use `scripts/relocate_directory.py` after the lightweight checks above, under
existing exact-path relocation and permanent-retirement authority. Keep the proof,
journal, inventory sidecar and lock in a private directory outside both payloads.
Require macOS `diskutil`, `lsof`, Python 3.10+ and a destination on another device.
Coordinate scheduled writers and application owners first. The helper checks
current-user open handles; it cannot establish non-use by other users or future jobs.

Write a JSON proof from the completed observations, with these fields:

| Field | Required value |
|---|---|
| `schema`, `status`, `method` | `1`, `"passed"`, `"lightweight"` |
| `source`, `destination` | Exact absolute physical directory paths |
| `source_identity`, `destination_identity` | `[st_dev, st_ino]` from no-follow root stats |
| `coverage` | Object with `entries` including the root, `files` counting regular files, and `logical_bytes` summing their sizes; match the source inventory |
| `mismatches` | Empty list only after unresolved differences are cleared |
| `local_only_review`, `metadata_review` | Nonempty conclusions identifying preserved local-only work and required metadata checks; retain detailed observations beside the proof |
| `allowed_destination_extras` | Optional exact relative `.DS_Store` paths; default empty; no arbitrary extra files |

Do not manufacture a passing proof from directory totals. The helper checks its
shape, identities and metadata coverage; it does not perform Git remote recovery,
semantic data verification, or the selected content checks on the operator's behalf.
Pass a read-only real consumer as a JSON argv list, with an absolute executable and
`{source}` in an argument. Require meaningful positive output and exit 0; use a
consumer that fails on missing/invalid input. Do not use a shell command string.

Run from the Skill directory, replacing task parameters from those observations:

```bash
uv run scripts/relocate_directory.py plan \
  --source "$SOURCE" --destination "$DESTINATION" \
  --volume-uuid "$VOLUME_UUID" --proof "$PROOF" --state "$STATE" \
  --consumer-json "$CONSUMER_ARGV_JSON"
uv run scripts/relocate_directory.py cutover --state "$STATE"
uv run scripts/relocate_directory.py retire --state "$STATE"
```

Use `plan` to bind evidence and snapshot metadata without changing either payload.
Use `cutover` to rename internally, create the original-entry symlink, and test the
consumer; it stops before deletion. On consumer failure, restore the original
directory only if the paths still belong to this operation. Use `retire` only for
the recorded internal sibling. It does not follow symlinks and adds owner access
only to owned read-only directories in that retired tree. Never chmod the archive.

After interruption, read the journal and actual paths, then run:

```bash
uv run scripts/relocate_directory.py resume --state "$STATE"
```

Treat `resume` as continuation through permanent retirement, not a read-only status
command. It reuses a recorded successful consumer check and resumes remaining
entries. Preserve state on a nonzero exit; resolve the named failure before retry.
Read JSON progress and the final `complete` state, then independently inspect the
original symlink, absence of the retired sibling, destination UUID and real consumer.
Report timestamped internal free space separately from logical bytes relocated.
