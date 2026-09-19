# 探针 r4-12：skill 自己规定的 Finder Trash 形态无法通过 target_coverage

测什么：假阳方向 + 覆盖盲区。SKILL.md:200-204 把 `/usr/bin/osascript … -- "<exact-path>"`
定为本 skill 唯一 sanctioned 的删除形态。但 DESTRUCTIVE_PATTERNS 的 osascript 规则是裸
`\boscript\b`，它命中的是**命令行所在那一格**（里面没有路径），而真正带
`-- "<exact-path>"` 的那一行因为在 fenced block 里且不含 osascript 字样，从未被当作命令。
于是 quoted_target() 那条专门为 osascript 写的取参路径，只在命令与目标同处一格时才生效。

本例按 SKILL.md 的命令表模板（含 目标 列）逐字照抄 Trash 形态。

预期：exit 0。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/Library/Containers/com.old.app1`（已卸载应用沙盒残留） | 6.4 GB | path-accounted（du） | REBUILDABLE | "Sandboxed application data (for App Store apps)" | 6.4 GiB | 应用已卸载，无需恢复 | 入动作集 |
