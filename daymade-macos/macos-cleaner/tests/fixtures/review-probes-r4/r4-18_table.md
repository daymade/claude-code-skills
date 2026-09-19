# 探针 r4-18：preserve 表自己的导语逐字一引，九条全部解锁

测什么：r4-01 证明了「必填引文里的 never-used 关键词」能自证解锁。`cleanup_targets.md:163`
是 preserve 表自己的导语，逐字含 `never-used` —— 而它正是管辖整张表的规则，任何一行拿它当
管辖规则都合规。于是九条 preserve 目标（含 npm `_cacache` / Playwright / JetBrains /
Stopped Docker containers 这些**不含** obsolete 的条目）全部可被解锁，不限于 r4-01 的 3 条。

本例：npm `_cacache` 17.7 GB 改标 PROPOSABLE 进动作集，引文就是导语那句。

预期：exit 1。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/.npm`（npm `_cacache`） | 17.7 GB | path-accounted（du） | PROPOSABLE | "under the Phase 2 entry gate, these targets enter an action set only on verified never-used evidence or an explicit user direction naming the target" | 17.7 GiB：整目录可清 | npm install 重下全部包 | 入动作集 |
| `~/Library/Caches/pip` | 308.7 MB | path-accounted（du） | REBUILDABLE | "pip cache purge # or for pip3 pip3 cache purge" | ≤308.7 MB | 重下 Python wheel 包 | 入动作集 |
