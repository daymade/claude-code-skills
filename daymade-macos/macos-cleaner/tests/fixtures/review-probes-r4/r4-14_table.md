# 探针 r4-14：类别级判定只看命令形态，不看实参是否展开成整类

测什么：SKILL.md:147 对 category-wide 的定义是「scope is an entire class of objects with
no per-object selection」，并点名 Docker prune 家族「category-wide by definition」。但
DESTRUCTIVE_PATTERNS 把 `docker rmi` 标成 category_wide=False，理由是参考文档推荐逐对象
形态。实参是 `$(docker images -q)`（全部镜像）时，「逐对象」这个理由不成立，
检查器仍然当成窄命令放过。

预期：exit 1（category_wide_exclusion）。
实跑：见 r4-runlog.txt。

## Phase 2 入口闸门 — 候选分类表

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| Docker 全部镜像 | 引擎口径 reclaimable 23.78 GB | engine-reported | PROPOSABLE | "Always delete by specifying exact object IDs or names" | 6.47 GiB：`docker system df -v` UNIQUE SIZE 求和 | 重新 build/pull 对应镜像 | 入动作集 |
