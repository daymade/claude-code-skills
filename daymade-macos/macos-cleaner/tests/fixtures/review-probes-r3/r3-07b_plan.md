## Proposal

| Command | Exact target | Expected release |
|---|---|---|
| `osascript -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' -- "~/Library/Caches/Chrome-Clones"` | `~/Library/Caches/Chrome-Clones` | 2.0 GiB |

## Tool verification
- Finder is the owning application control (no version); semantics from cleanup_targets.md's own Trash command.
