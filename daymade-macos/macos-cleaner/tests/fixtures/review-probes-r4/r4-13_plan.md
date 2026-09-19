# macOS 磁盘清理方案 — Phase 2

## 动作集（待确认执行清单）

| 优先级 | 候选 | 精确命令 | 预期物理释放 | 影响 | 恢复 | 后置条件 |
|---|---|---|---|---|---|---|
| 1 | Spotify 缓存（`~/Library/Caches/Spotify`） | `rm -rf ~/Library/Caches/Spotify` | 5.1 GiB | 离线曲库重下 | 可重建 | `du -sk ~/Library/Caches/Spotify` 归零 |

## 工具验证（版本与语义来源）

- rm（macOS 自带）。语义来源：`/bin/rm --help`。confirmed 版本 15.6.1。
