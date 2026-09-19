## Proposal

| Command | Exact target | Expected release |
|---|---|---|
| `yarn cache clean` | yarn cache root | 6.10 GiB |
| `conda clean --all -y` | `~/miniconda3/pkgs` | 12.4 GiB |

## Tool verification
- yarn 1.22.22; semantics from `yarn cache clean --help`.
- conda 24.7.1; semantics from `conda clean --help`.
