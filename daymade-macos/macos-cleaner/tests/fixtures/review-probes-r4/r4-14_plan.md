# macOS 磁盘清理方案 — Phase 2

## 动作集（待确认执行清单）

| 优先级 | 候选 | 精确命令 | 预期物理释放 | 影响 | 恢复 | 后置条件 |
|---|---|---|---|---|---|---|
| 1 | Docker 全部镜像 | `docker rmi $(docker images -q)` | 6.47 GiB | 需重新 build/pull | 可重建 | `docker images` 为空 |

## 工具验证（版本与语义来源）

- Docker 29.4.0（`docker --version` 实测）。语义来源：`docker rmi --help` 原文，已用活工具核对（system df 实测）。
