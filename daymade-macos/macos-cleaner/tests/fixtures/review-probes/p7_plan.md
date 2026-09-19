## 方案

| 命令 | 精确目标 |
|---|---|
| `osascript -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' -- "~/.npm/_cacache"` | `~/.npm/_cacache` |

## 工具验证
- Finder 为属主应用控制（无版本号），语义取自 cleanup_targets.md 自身的 Trash 命令。
