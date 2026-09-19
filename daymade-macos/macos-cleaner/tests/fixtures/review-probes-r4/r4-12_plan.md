# macOS 磁盘清理方案 — Phase 2

## 动作集（待确认执行清单）

| 优先级 | 候选 | 目标 | 精确命令 | 预期物理释放 | 影响 | 恢复 | 后置条件 |
|---|---|---|---|---|---|---|---|
| 1 | 已卸载应用沙盒残留 | `~/Library/Containers/com.old.app1` | `/usr/bin/osascript -e 'on run argv' -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' -e 'end run' -- "~/Library/Containers/com.old.app1"` | 6.4 GiB | 无 | Trash 可取回 | Trash 内出现该目录 |

## 工具验证（版本与语义来源）

- Finder（macOS 15.6.1）。语义来源：`osascript` 自带帮助，已用活工具核对（status 已核对）。
