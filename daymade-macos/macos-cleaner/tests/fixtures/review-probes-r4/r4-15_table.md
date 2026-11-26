# 探针 r4-15：假阳 —— skill 唯一 sanctioned 的 Docker 逐对象删除形态被判成 category-wide

测什么：假阳方向。DESTRUCTIVE_PATTERNS 把 `docker image rm` 标成 category_wide=True，
只有 `--no-prune` + 完整 sha256 image ID 的逐对象形态可以窄化。于是
`docker image rm --no-prune <exact-full-image-id>` —— references/docker_analysis.md
「精确镜像退役形态」—— 在动作集里不应 FAIL。

本例：单对象、有 ancestor 引用校验、引擎口径逐对象释放，是参考文档原文要求的形态。

预期：exit 0。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| Docker dangling 镜像 `sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc` | 260 MB（unique 1.976 kB） | engine-reported | PROPOSABLE | "Before deleting ANY Docker object, perform independent verification." | 1.976 kB：该行 UNIQUE SIZE | 重新 build 该镜像 | 入动作集（用户逐对象勾选） |
