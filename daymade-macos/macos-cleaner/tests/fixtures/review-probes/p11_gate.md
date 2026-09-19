| Target | Nominal size | Physical confidence | Class | Governing rule (verbatim quote) | Expected physical release + basis | Restoration cost | Verdict |
|---|---|---|---|---|---|---|---|
| `~/Library/Developer/Xcode/DerivedData/ProjA` | 30.0 GiB | path-accounted | PROPOSABLE | "Quit Xcode; prefer removing an exact inactive project child." | unknown — APFS shared extents, release unknown until deletion and `df` readback | rebuild | in action set |
| `$(brew --cache)` | 2.00 GiB | path-accounted | PROPOSABLE | "Cleanup after the exact Homebrew impact is approved: `brew cleanup -s`" | ≈2.00 GiB from `du -sk` | reinstall | in action set |
