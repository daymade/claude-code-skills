## Proposal

| Command | Exact target | Expected release |
|---|---|---|
| `find ~/Library/Logs -name "*.log" -mtime +30 -delete` | `~/Library/Logs` | 3.40 GiB |
| `diskutil secureErase freespace 0` | `/System/Volumes/Data` | 3.40 GiB |

## Tool verification
- find (BSD findutils, macOS 15.6); semantics from `man find`.
- diskutil 24.0; semantics from `diskutil --help`.
