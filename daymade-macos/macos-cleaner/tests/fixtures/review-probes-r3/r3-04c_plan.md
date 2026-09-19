## Proposal

| Command | Exact target | Expected release |
|---|---|---|
| `uv cache prune` | `~/.cache/uv` | 41.45 GiB — 排除在低风险组合之外 |

## Tool verification
- uv 0.11.21 的 `uv cache dir` 实测输出已记录；语义见 uv 文档。
