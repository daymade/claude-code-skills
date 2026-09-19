# macOS 磁盘清理方案 — Phase 2

## 动作集（待确认执行清单）

| 优先级 | 候选 | 精确命令 | 预期物理释放 | 影响 | 恢复 | 后置条件 |
|---|---|---|---|---|---|---|
| 1 | pip 缓存（`~/Library/Caches/pip`） | `pip cache purge` | 2.0 GiB | 重下 wheel | 可重建 | `du -sk ~/Library/Caches/pip` 归零 |
| 2 | 已卸载应用残留（`~/Library/Application Support/OldApp`） | `rm -rf ~/Library/Application\ Support/OldApp` | 6.47 GiB | 无 | n/a | 目录消失 |

## 工具验证（版本与语义来源）

- pip 26.0.1（`pip3 --version` 实测）。语义来源：`pip3 cache purge --help` 原文："Inspect and manage pip's wheel cache."
- rm（macOS 自带）。语义来源：`/bin/rm --help`。confirmed 版本 15.6.1。
