## Proposal

| Command | Exact target | Expected release |
|---|---|---|
| `docker volume rm project-mysql-data` | `docker volume project-mysql-data` | 8.20 GiB |

## Tool verification
- docker 27.3.1; semantics from `docker volume rm --help`.
