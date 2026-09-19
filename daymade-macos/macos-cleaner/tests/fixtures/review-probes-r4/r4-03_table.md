# 探针 r4-03：「no rule found」行没有被约束成 USER-DECISION

测什么：SKILL.md:140 规定 no-rule-found 的目标归 USER-DECISION，方案「asks before
proposing anything for them」。check_quote_fidelity 只把 no rule found 当作「免引文」
放行（tests/test_gate_checker.py:478 只测了这一半），没有任何检查把
no-rule-found 行和它的 Class 关联起来 → PROPOSABLE + 入动作集 全绿。

本例：pnpm 缓存，cleanup_targets.md 确实没有 pnpm 条目（真 no rule found）。

预期：exit 1。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/Library/Caches/pnpm` | 3.8 GB | path-accounted（du） | PROPOSABLE | no rule found（cleanup_targets.md 的 Package Manager Caches 章节无 pnpm 条目） | 3.8 GiB：目录可清 | pnpm 包重下 | 入动作集 |
| `~/Library/Caches/pip` | 308.7 MB | path-accounted（du） | REBUILDABLE | "pip cache purge # or for pip3 pip3 cache purge" | ≤308.7 MB | 重下 Python wheel 包 | 入动作集 |
