## Proposal

| Command | Exact target | Expected release |
|---|---|---|
| `osascript -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' -- "~/.npm/_cacache"` | `~/.npm/_cacache` | 12.90 GiB |

## Tool verification
- Finder is the owning application control (no version); semantics from `cleanup_targets.md`'s own Trash command.
- Known-issue check: not performed.
