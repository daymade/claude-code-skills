# 探针 r4-07：假阳 —— 合规的非 preserve 目标被 preserve 交叉检查错杀

测什么：假阳方向。preserve_match 只取目标单元格里**路径的 basename** 做词元比对，
tokens_overlap 对 >=4 字符的词元用**前缀包含**（one.startswith(other)）。preserve 表里
「Hugging Face cache」的判别词元含 `face`，于是任何 basename 以 face 开头的普通应用缓存
都被判成「这就是 Hugging Face cache 这一条」，交叉检查随即要求它出示 never-used 证据或
用户逐字方向 —— 而 REBUILDABLE 行按 SKILL.md:138 本不需要任何 never-used 证据。

本例行内**没有任何** never-used 措辞，是 gate 文本明确允许的动作集成员
（不在 preserve 表内 / 有重建路径 / 恢复成本已写）。

预期：exit 0。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| `~/Library/Caches/FaceTime` | 1.2 GB | path-accounted（du） | REBUILDABLE | "Inventory exact application-owned subdirectories first and prefer the application's supported cache-management command when one exists" | 1.2 GiB：目录清空即可回收 | 应用自行重建缓存 | 入动作集 |
| `~/Library/Caches/pip` | 308.7 MB | path-accounted（du） | REBUILDABLE | "pip cache purge # or for pip3 pip3 cache purge" | ≤308.7 MB | 重下 Python wheel 包 | 入动作集 |
