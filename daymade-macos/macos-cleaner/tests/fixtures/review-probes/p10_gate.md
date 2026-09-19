| Target | Nominal size | Physical confidence | Class | Governing rule (verbatim quote) | Expected physical release + basis | Restoration cost | Verdict |
|---|---|---|---|---|---|---|---|
| `~/Library/Caches/Chromium-x`（41.45 GiB） | 41.45 GiB | path-accounted | PROPOSABLE | "shared extents can be attributed to every path, so actual release remains unknown until deletion and `df` readback" | unknown — APFS shared extents, release unknown until deletion | n/a | in action set |
| `~/Library/Caches/pip` | 301 MiB | path-accounted | PROPOSABLE | "Cleanup after the redownload impact is approved: `pip cache purge`" | ≈301 MiB from `du -sk` | reinstall | in action set |
