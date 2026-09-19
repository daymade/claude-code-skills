## Proposal

| Command | Exact target |
|---|---|
| `osascript -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' -- "~/.npm/_cacache"` | `~/.npm/_cacache` |

## Tool verification
- Finder is the owning application control; semantics per cleanup_targets.md.
