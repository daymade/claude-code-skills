## Proposal

| Command | Exact target | Expected release |
|---|---|---|
| `npm cache clean --force` | `~/.npm/_cacache` | 12.90 GiB |

## Tool verification
- npm 10.9.0. `npm cache clean --force` semantics from `npm cache clean --help`.
- Known issue: none checked.
