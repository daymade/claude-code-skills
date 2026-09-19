# 探针 r4-05：规则列定位被「依据」列抢走 → 伪造的管辖规则永不被核验

测什么：SKILL.md:155 承诺「every governing-rule quote appears verbatim in the reference
(this is what forces the reference open — a fabricated quote fails)」。但
Table.column(*RULE_COLUMN_KEYWORDS) 返回**第一个**命中关键词的表头单元格，而关键词表里
有「依据」。SKILL.md 自己的模板列名「Expected physical release + basis」译成中文就是
「预期物理释放 + 依据」—— 只要它排在管辖规则列**之前**，规则列就解析到释放列上，
quote_fidelity 去核验释放列里的引文（本例放一条真引文），真正的管辖规则列里写什么都不查。

本例：真正的管辖规则列是一条**编造的规则**（"Cache directories are always safe to
delete, regeneration is instantaneous"——cleanup_targets.md 从未这么说过），却被放行。

预期：exit 1（quote_fidelity 报伪造引文）。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据（含逐字引用） | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/Library/Caches/Google` | 2.4 GB | path-accounted（du） | REBUILDABLE | "Cache directories are always safe to delete, regeneration is instantaneous" | 2.4 GiB：依据 "Inventory exact application-owned subdirectories first and prefer the application's supported cache-management command when one exists" | 应用重建缓存 | 入动作集 |
