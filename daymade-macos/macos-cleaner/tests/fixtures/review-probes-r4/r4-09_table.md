# 探针 r4-09：排序规则整条蒸发 —— 释放列换个名字就没人排序

测什么：SKILL.md:146「The plan leads with the in-action-set row holding the largest
expected physical release … Any other lead row fails this gate; that is the small-fish
failure」。table_release_cell 只认 'expected physical release' / '预期物理释放' /
'预期释放' / 'release' 这几个列名；plan_release_table 同样只认三个名字。两处都叫
「预计回收空间」时，所有行的 release 都是 None → check_lead_rule 直接
return PASS('every in-action-set release is unknown')。

这正是 2026-09-19 那条被点名的事故形态（2 GB 项排在 91 GB 候选前面），
只是把列名从模板的中文写法改了一个同义词。

预期：exit 1（lead_rule）。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预计回收空间 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/Library/Caches/pip` | 308.7 MB | path-accounted（du） | REBUILDABLE | "pip cache purge # or for pip3 pip3 cache purge" | ≤308.7 MB | 重下 Python wheel 包 | 入动作集 |
| `~/Library/Application Support/OldApp` | 9.0 GB | path-accounted（du） | REBUILDABLE | "Folder belongs to trial software no longer used" | 9.0 GiB：目录整体可回收 | 应用数据，无需恢复 | 入动作集（应用已卸载） |
