# Read-only storage diagnosis CLI

Keep logical length, path allocation, native private allocation and proposed
actions separate. Neither existing CLI entry deletes data or authorizes cleanup.

## Observe exact files without another scan

Run from the installed skill directory on the target host:

```bash
set -o pipefail
python3 -B scripts/analyze_large_files.py --files "<exact-physical-file>" --json |
  python3 -B scripts/cleanup_report.py --inventory - --json
```

Selection limits are enforced by the [analyzer](../scripts/analyze_large_files.py).
This mode does not run `find`, `du`, Docker, payload
hashing or a recursive walk. It opens physical parents without following
symlinks, observes `st_size` and `st_blocks * 512`, and reuses
`_apfs_native.private_size_fd` on a pinned regular-file descriptor. Native
permission/unsupported results stay unknown with a reason. A changed file or
selected directory is incomplete. Reuse a bounded directory inventory for its
aggregate instead.

Keep the existing `--path`, `--threshold` and `--limit` search when that scan is
approved. The threshold is logical file length; the limit ranks by allocated
bytes when known. This does not measure directory aggregates or all small files
in a large cache. Omit `--json` for human-readable output.

## Consume existing inventory without probing its paths

```bash
python3 -B scripts/cleanup_report.py --inventory "<existing-inventory.json>"
```

Supply a UTF-8 JSON object; its input boundary is defined by the
[inventory parser](../scripts/storage_diagnosis.py):

```json
{
  "schema": "macos-storage-inventory-v1",
  "observed_at": "2026-01-01T00:00:00+00:00",
  "scope": {"source": "existing bounded inventory"},
  "collection_complete": true,
  "issues": [],
  "volume_observation": {"device": 1, "available_bytes": 8589934592},
  "entries": [
    {
      "path": "/Volumes/Example/cache",
      "kind": "directory",
      "device": 1,
      "inode": 123,
      "logical_bytes": null,
      "allocated_bytes": 20000000000,
      "private_bytes": null,
      "private_reason": "not measured",
      "role": "cache",
      "reference_status": "unknown"
    }
  ]
}
```

Preserve original timestamps and sample boundaries when projecting evidence.
Set row `sample_id` for another collection; otherwise top-level `observed_at`
identifies its collection. Supply nonnegative integer byte metrics or `null`;
omit an unmeasured metric instead of writing zero. Keep errors in `issues` and
set `collection_complete` false. Roles/references are supplied evidence, never
inferred from filenames. Use `active`, `inactive` or `unknown` references;
use `source`, `user_data`, `protected`, `runtime_state`, `generated`,
`duplicate`, `cache` or `unknown` roles.
An optional `category` must be a string or `null`; omitted, null and empty
categories have no label. Invalid category/reference types fail with exit 2 in
both text and JSON output.

Read `hotspots` before subtotals. Every row remains visible, including protected
data and unknown private allocation. Within each sample/device,
`accounting_groups` sums a path frontier: measured directory ancestors cover
listed descendants; identical paths and device/inode aliases count once.
Different samples/devices stay separate. Distinct inodes can still share APFS
extents. A known subtotal beside unknown rows is incomplete coverage, not a
complete volume total.

Retain `volume_observation` separately. The inventory report does not query `df`
or subtract path totals from APFS volume use. Use same-volume timestamped `df`
observations and the [attribution procedure](growth_attribution.md#target-allocation-and-mixed-free-space-windows)
for unexplained differences. Legacy `--snapshot before` and
`--snapshot after --compare` still write local snapshots; their deltas are
observations, not per-action cleanup credit.

Use `next_step` to select a deciding action. Active consumers, source, user data
and runtime state require preservation. Inactive generated/cache rows direct
review of the exact owner, recovery cost and existing authorization. Resolve
unknowns through the creating job and current consumers. This diagnostic keeps
`cleanup_authorized` false and `reclaimable_bytes` null.

Interpret exit 0 as complete input collection, not complete physical knowledge;
exit 1 retains incomplete evidence and visible hotspots; exit 2 rejects invalid
input/invocation. Inventory mode reads only its JSON input and creates no
snapshot state or additional path observations.

## Representative allocation cases

Use these synthetic allocation cases to judge reporting, not another machine's
allocation or cleanup eligibility:

| Observation | Interpretation and next action |
|---|---|
| VM image: logical 256 GiB; allocated/private 24 GiB; open holders unknown. | Keep the 24 GiB host hotspot visible. The 256 GiB virtual capacity is not occupancy. Single-file private size is not batch release. Bind guest objects and consumers before choosing an owning action. |
| pnpm samples: different inodes, `nlink=1`, same APFS clone ID, 4,096 B allocated and 0 B private each. | These samples share blocks without hard links. Preserve the measured zeros and path allocation; keep the rest of the store and batch release unknown. Verify exact store-version/project references before lifecycle action. |
| Same sample/device: parent 96 GB, listed child 30 GB. | Display both, count the parent once instead of 126 GB. Deepen only the largest unexplained branch that can change the next action. |

