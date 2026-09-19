# 探针 r4-01：preserve 自解锁 —— 「必填的规则引文本身」充当 never-used 证据

测什么：check_preserve_downgrade 把 NEVER_USED_RE 搜在**整行文本**上，而 quote_fidelity
强制每一行都必须带一条逐字引文。uv cache 的权威规则引文（cleanup_targets.md:188）里含
"obsolete" —— 于是把 preserve 目标改标 PROPOSABLE 放进动作集，不需要任何 never-used 证据，
gate 自己要求的引文就把证据检测满足了。

预期（若 gate 健全）：exit 1，preserve_by_default FAIL。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/.cache/uv` | 42.3 GB | path-accounted（du） | PROPOSABLE | "Environments may need to fetch or rebuild dependencies again" | 42.0 GiB：清空后整个目录可回收 | 重新下载/重建 Python 依赖 | 入动作集 |
| `~/Library/Caches/pip` | 308.7 MB | path-accounted（du） | REBUILDABLE | "pip cache purge # or for pip3 pip3 cache purge" | ≤308.7 MB | 重下 Python wheel 包 | 入动作集 |

动作集：`~/.cache/uv`（PROPOSABLE）+ pip 缓存。
