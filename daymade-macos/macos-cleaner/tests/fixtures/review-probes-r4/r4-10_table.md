# 探针 r4-10：释放格里一句「不是 du 名义值」把最大行整格作废 → 小鱼领队通过

测什么：table_release_cell 对释放格用 `if RESERVATION_RE.search(cell): return None`
—— **整格**作废，不是只作废被标注的那个数字。RESERVATION_RE 含通用词 `不是`，
于是一句诚实的口径澄清（"引擎 UNIQUE SIZE 求和，不是 du 名义值"）就把这一行
从排序里整个拿掉，剩下的小鱼自动成为「最大」，小鱼领队 PASS。

本例是 2026-09-19 那条事故的形态（2 GB 项排在 9 GB 候选前），
差别只在于大行多加了一句口径说明。

预期：exit 1（lead_rule）。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/Library/Caches/pip` | 308.7 MB | path-accounted（du） | REBUILDABLE | "pip cache purge # or for pip3 pip3 cache purge" | 2.0 GiB | 重下 Python wheel 包 | 入动作集 |
| `~/Library/Application Support/OldApp` | 9.0 GB | path-accounted（du） | REBUILDABLE | "Folder belongs to trial software no longer used" | 6.47 GiB（引擎 UNIQUE SIZE 求和，不是 du 名义值） | 应用数据，无需恢复 | 入动作集（应用已卸载） |
