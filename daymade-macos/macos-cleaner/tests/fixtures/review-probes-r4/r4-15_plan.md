# macOS 磁盘清理方案 — Phase 2

## 动作集（待确认执行清单）

| 优先级 | 候选 | 精确命令 | 预期物理释放 | 影响 | 恢复 | 后置条件 |
|---|---|---|---|---|---|---|
| 1 | Docker dangling 镜像 `c5810ff4b86a` | `docker rmi c5810ff4b86a` | 1.976 kB | 需重新 build | 可重建 | `docker images` 中无该 ID |

先 `docker ps -a --filter "ancestor=c5810ff4b86a" --format "{{.Names}}"` 确认无容器引用。

## 工具验证（版本与语义来源）

- Docker 29.4.0（`docker --version` 实测）。语义来源：`docker rmi --help` 原文，已用活工具核对（system df 实测）。
