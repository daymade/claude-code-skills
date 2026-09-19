## Proposal

| Command | Exact target | Expected release |
|---|---|---|
| `brew cleanup --prune=all` | `$(brew --cache)` | 2.00 GiB |

## Tool verification
- brew 7.0.1; semantics from `brew cleanup --help`.
