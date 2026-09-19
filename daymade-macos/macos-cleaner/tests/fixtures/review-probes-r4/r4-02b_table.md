# 探针 r4-02：硬排除的类别级命令从「未归因」路径整体逃逸

测什么：SKILL.md:148 规定 `uv cache prune` / `npm cache clean` 「may not appear in the
action set even when every other rule passes」。但 check_target_coverage 把
「命令没有可解析目标」算作 unattributed（显式不判违规），check_category_wide_exclusion
又对 attribute()==None 的命令直接跳过。裸形式（无对象参数）的 prune 家族永远
resolvable=False → 两条检查同时失效。

本例：分类表完全没有 uv 这一行（step 2 要求「classify every candidate」，但检测器无从知道
全集），方案的命令表里直接放 `uv cache prune`（+ `npm cache clean --force`）。

预期：exit 1（category_wide_exclusion）。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/Library/Caches/pip` | 308.7 MB | path-accounted（du） | REBUILDABLE | "pip cache purge # or for pip3 pip3 cache purge" | ≤308.7 MB | 重下 Python wheel 包 | 入动作集 |
| `~/Library/Logs` | 364.4 MB | path-accounted（du） | USER-DECISION | "Diagnostic history; inspect before deletion" | 未逐文件检查 | 诊断历史丢失 | 不入动作集 |
