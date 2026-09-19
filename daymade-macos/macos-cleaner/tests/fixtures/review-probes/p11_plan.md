## Proposal (leads with the row whose expected release is known)

| Command | Exact target |
|---|---|
| `brew cleanup -s` | `$(brew --cache)` |

## Tool verification
- brew 7.0.1; semantics from `brew cleanup --help`.
