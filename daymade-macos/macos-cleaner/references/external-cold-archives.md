# Relocate cold data to a removable disk

Use this for a selected inactive source whose bytes must survive on an SD card or
external disk. Keep the source until preservation and original-entry checks pass.
Relocation does not create a second independent backup or prove sustained free space.

## Bind the outcome and destination

1. Read [batch selection](batch-selection.md). Record the user's capacity unit,
   current internal free space, remaining gap and honest reclaim ceiling. Keep
   another authorized route moving when the candidate cannot close the gap.
2. Bind the exact source, destination, host, preservation requirements and current
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

Capture a source manifest before copying. Bind it to host/source identity; record
the complete relative entry set, types, modes, ownership, flags, modification times,
symlink targets, hard-link relationships where present, ACLs and xattr names and
values. Use no-follow metadata reads, including symlink attributes. Record size
and full SHA-256 for every regular file. Save original raw metadata needed for
exact restoration in a private sidecar outside the payload. Fail on unreadable
metadata, unsupported entry types or incomplete traversal; unknown is not empty.
Preserve other timestamps only when required by the asset contract and supported
by the destination; do not require copied inode numbers or change times to match.

Independently read every destination entry and full file content. Check missing
and extra entries and whether the source changed during copying. Handle differences:

| Difference | Required action before cutover |
|---|---|
| Content, type, symlink target or topology | Preserve the source; repair/re-copy the affected set, verify its content and the complete entry inventory |
| Quarantine value, permissions, ACLs, timestamps or other required metadata | Restore the exact captured value and compare again; do not strip quarantine or weaken the whole comparison |
| Understood OS-generated provenance | Retain the original raw value and observed difference; allow only that specifically understood field, not arbitrary xattr loss |
| Changed source, unreadable field, missing coverage or stale proof | Preserve the source and mark proof incomplete; establish stable inputs before resuming |

Symlink mtime differs from its target's mtime; use a no-follow operation for an
exact timestamp repair. Treat a repair as metadata-only only when its bounded
operation, before/after identities and data-relevant state establish that no
payload changed. Otherwise hash the affected payload again.

Reuse full-content evidence only while its exact manifest, complete coverage,
source/destination identities and unchanged payload remain established. Bind that
proof to its digest and record metadata reconciliation separately. Require explicit
counts and empty mismatch lists; reject missing, null, partial or stale evidence.
Recheck changed fields and the entry set instead of rehashing the entire unchanged
archive. A size/mtime sample alone cannot establish content equality or justify
reuse after an unexplained change. A phase label is not a successful verification.

## Switch the entry and retire only the redundant internal copy

1. Recheck UUIDs, complete preservation proof, source stability, holders and
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
