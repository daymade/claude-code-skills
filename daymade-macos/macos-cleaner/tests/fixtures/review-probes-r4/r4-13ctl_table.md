# 控制组：同一机制对 npm `_cacache` 不成立 —— 它的规则引文里没有 never-used 关键词

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/.npm`（npm `_cacache`） | 17.7 GB | path-accounted（du） | PROPOSABLE | "Keep; do not confuse it with `_npx`" | 17.7 GiB | npm install 重下全部包 | 入动作集 |
