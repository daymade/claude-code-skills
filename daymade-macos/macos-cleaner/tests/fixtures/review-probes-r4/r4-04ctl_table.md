# 探针 r4-04：PRESERVE 行的「用户方向引用」被规则引文冒充

测什么：SKILL.md:136 — 「Accepting a cost you stated is not (b): the user must name the
target themselves」。check_action_set_classes 与 check_preserve_downgrade 都用
has_quoted_direction(row.verdict_cells()) 判断有无引用用户原话；verdict_cells() 在没有
「裁决/判定/verdict」列时退化为**最后一个单元格**。只要表把管辖规则列排在最后，必填的
规则引文就落在 verdict_cells() 里 → 「引用了用户方向」恒为真。

本表第 6 列明确写着用户没有逐字点名，只是接受了 agent 陈述的成本 —— 正是 SKILL.md 点名
禁止的那一种。行内引文用不含 never-used 关键词的版本，以隔离出这条机制本身
（obsolete 那条路径见 r4-01）。

预期：exit 1（action_set_classes / preserve_by_default）。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 预期物理释放 | 恢复成本 | 裁决 | 管辖规则（逐字引用） |
|---|---|---|---|---|---|---|
| `.cache/huggingface` | 28.2 GB | path-accounted（du） | PRESERVE | 28.0 GiB：模型目录整体清空 | 模型权重重下（小时级）。模型权重重下（小时级）。用户未逐字点名该目标，仅接受了 agent 陈述的成本 | 用户解锁 | "Large models may take hours to redownload and may be unavailable offline" |
| `~/Library/Caches/pip` | 308.7 MB | path-accounted（du） | REBUILDABLE | ≤308.7 MB | 重下 Python wheel 包 | "pip cache purge # or for pip3 pip3 cache purge" |
