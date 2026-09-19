## Proposal

| Command | Exact target | Expected release |
|---|---|---|
| `osascript -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' -- "~/.cache/uv"` | `~/.cache/uv` | 41.45 GiB |

## Tool verification
- Finder is the owning application control (no version); semantics from cleanup_targets.md's own Trash command.
