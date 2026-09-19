## Proposal

| Command | Exact target | Expected release |
|---|---|---|
| `osascript -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' -- "~/Library/Caches/ms-playwright"` | `~/Library/Caches/ms-playwright` | 5.20 GiB |

## Tool verification
- Finder is the owning application control (no version); semantics from cleanup_targets.md's own Trash command.
