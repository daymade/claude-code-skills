## Proposal

| Command | Exact target | Expected release | Note |
|---|---|---|---|
| `npm cache clean --force` | `~/.npm` | 12.90 GiB | 不删除其他缓存 |

## Tool verification
- npm 10.9.0; semantics from `npm cache clean --help`.
