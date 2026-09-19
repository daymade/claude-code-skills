# macOS 磁盘清理方案 — Phase 2

## 动作集（待确认执行清单）

```bash
/usr/bin/osascript \
  -e 'on run argv' \
  -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' \
  -e 'end run' -- "~/Library/Containers/com.old.app1"  # 不使用 rm，也不使用 safe_delete.py
```

## 工具验证（版本与语义来源）

- Finder（macOS 15.6.1）。语义来源：`osascript` 自带帮助，已用活工具核对。
