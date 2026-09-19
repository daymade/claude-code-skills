# macOS 磁盘清理方案 — Phase 2

## 动作集（待确认执行清单）

| 优先级 | 候选 | 精确命令 | 预期物理释放 | 影响 | 恢复 | 后置条件 |
|---|---|---|---|---|---|---|
| 1 | uv 缓存（`~/.cache/uv`） | `rm -rf ~/.cache/uv` | 42.0 GiB：目录清空即可回收 | 全部 Python 环境需重建依赖 | 重下/重建依赖 | `du -sk ~/.cache/uv` 归零 |
| 2 | pip 缓存（`~/Library/Caches/pip`） | `pip cache purge` | ≤308.7 MB | 重下 wheel | 可重建 | `du -sk ~/Library/Caches/pip` 归零 |

本方案不提议 `uv cache prune`（reachability 语义问题），改用精确路径 rm。

## 工具验证（版本与语义来源）

- pip 26.0.1（`pip3 --version` 实测）。`pip3 cache purge --help` 原文："Inspect and manage pip's wheel cache." 语义来源：pip 自带帮助。
- rm（macOS 自带）。`/bin/rm --help` 语义来源：系统自带帮助。confirmed 版本 15.6.1。
