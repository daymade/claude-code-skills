# macOS 磁盘清理方案 — Phase 2

## 动作集（待确认执行清单）

本轮不使用 `pip cache purge`，改用 `rm -rf ~/Library/Caches/pip` 直接清掉整个 wheel 缓存目录。

## 工具验证（版本与语义来源）

- rm（macOS 自带）。语义来源：`/bin/rm --help`。confirmed 版本 15.6.1。
