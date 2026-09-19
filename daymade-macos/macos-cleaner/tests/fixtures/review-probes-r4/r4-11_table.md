# 探针 r4-11：一行里一个否定词豁免同行的真命令

测什么：declared_unused 对 prose 的作用域是**整行**（scope = lines[lineno-1]），
DECLARED_UNUSED_RE 只要在这一行任何位置命中（不使用 / 不执行 / 排除 / 不提议 …），
这一行里**所有**被识别出的命令都从 commands 列表里消失 —— 于是
target_coverage / category_wide_exclusion / tool_verification / lead_rule 全部看不到它们。

「不使用 A，改用 B」是最自然的写法之一。本例用
「不使用 `pip cache purge`，改用 `rm -rf ~/Library/Caches/pip`」，
真命令是 rm（宽根删除），但它和否定词同在一行 → 检测器输出 0 条破坏性命令。

预期：exit 1。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/Library/Caches/pip` | 308.7 MB | path-accounted（du） | REBUILDABLE | "pip cache purge # or for pip3 pip3 cache purge" | ≤308.7 MB | 重下 Python wheel 包 | 不入动作集（本轮不提议） |
