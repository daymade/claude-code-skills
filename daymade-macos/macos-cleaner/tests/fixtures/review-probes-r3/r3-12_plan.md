## 现状与已知问题（semantics 已核对）

| 命令 | 目标 | 预期释放 |
|---|---|---|
| `rm -rf /private/var/log/legacy-import.log` | `/private/var/log/legacy-import.log` | 0.5 GiB |

## 建议执行顺序

| 命令 | 目标 | 预期释放 |
|---|---|---|
| `pip cache purge` | `~/.cache/pip-wheels` | 41.0 GiB |

## 工具验证
- pip 24.0; semantics from `pip cache purge --help`.
- rm 9.0; semantics from `man rm`.
