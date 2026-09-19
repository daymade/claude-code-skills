# 探针 r4-13：PROPOSABLE 类的「已验证不再使用」证据，非 preserve 目标完全没人查

测什么：SKILL.md:137「PROPOSABLE — verified never-used evidence (a dead project, an
explicit user statement, an artifact check). Size ratios are not evidence」。检测器的证据
检查只在 preserve_downgrade 里，且只对命中了 preserve 表的目标生效（check_preserve_downgrade
的第一道 continue 就是 `if name is None: continue`）。非 preserve 目标标成 PROPOSABLE
放进动作集，不需要任何证据、不需要任何用户方向。

本例：Spotify 缓存，行内**没有任何**不再使用证据，也没有用户点名。

预期：exit 1。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/Library/Caches/Spotify` | 5.1 GB | path-accounted（du） | PROPOSABLE | "Local cache copies are regenerated, but redownload time, bandwidth, authentication, and offline availability may matter" | 5.1 GiB：目录整体可回收 | 离线曲库需重下 | 入动作集 |
