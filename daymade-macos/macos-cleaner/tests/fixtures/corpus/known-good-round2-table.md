# Phase 2 入口闸门 — 候选分类表

基线：2026-09-19 14:0x CST，Example Mac，macOS 26.6.2 (25G83)，
`/System/Volumes/Data` 1.8Ti / 已用 1.7Ti / 可用 106Gi / 95% 容量。
用户声明：重度开发用户（Python/Node/Docker 日常用）。用户未提供释放目标。

| 目标 | Nominal size | Physical confidence | Class | 管辖规则（逐字引用） | 预期物理释放 + 依据 | 恢复成本 | 裁决 |
|---|---|---|---|---|---|---|---|
| Docker dangling images（57 个，55 个无任何容器引用，含 stopped） | 引擎口径 reclaimable 上界 23.78 GB（含共享层，不可按单次删除分配） | engine-reported | PROPOSABLE | "Always delete by specifying exact object IDs or names" | 6.47 GiB：`docker system df -v` 57 行 UNIQUE SIZE 求和（引擎 1024 进制）；OrbStack 稀疏镜像下删除后主机 df 需再 compaction 才变化 | 重新 build/pull 对应镜像 | 不入动作集（用户逐对象确认后作为 directed action，一次一个 ID） |
| `.cache/uv` | 42.3 GB | path-accounted（du） | PRESERVE | "Environments may need to fetch or rebuild dependencies again" | 未逐对象测量；du 路径口径 42.3 GB 不构成释放承诺 | 重新下载/重建 Python 依赖 | 不入动作集（用户未点名该目标） |
| `.cache/huggingface` | 28.2 GB | path-accounted（du） | PRESERVE | "Large models may take hours to redownload and may be unavailable offline" | 未逐对象测量；模型目录需逐个核对才能定释放 | 模型权重重下（小时级，可能离线不可得） | 不入动作集（用户未点名该目标） |
| `~/.npm`（npm `_cacache`） | 17.7 GB | path-accounted（du） | PRESERVE | "npm install redownloads packages; constrained networks can turn this into a long reinstall" | 未逐对象测量 | npm install 重下全部包 | 不入动作集（用户未点名该目标） |
| Docker build cache | 21.82 GB（private 20.26 GB） | engine-reported | USER-DECISION | "This skill does not use docker builder prune or docker buildx prune" | 只报不删：本 skill 不执行 build cache 删除（可用控制全属 prune 家族） | 重建构建层耗时 | 不入动作集（skill 明确只报不删） |
| `.cache/modelscope` | 4.2 GB | path-accounted（du） | PRESERVE | "Keep unless exact artifacts are obsolete" | 未逐对象测量 | 模型重下 | 不入动作集（用户未点名该目标） |
| `~/Library/Caches/pnpm` | 3.8 GB | path-accounted（du） | USER-DECISION | no rule found（cleanup_targets.md 的 Package Manager Caches 章节无 pnpm 条目） | 未逐对象测量 | pnpm 包重下 | 不入动作集（无规则覆盖，须问用户） |
| `~/Library/Caches/ms-playwright` | 3.1 GB | path-accounted（du） | PRESERVE | "Browsers must be downloaded again; this can be several GiB" | 未逐对象测量 | 浏览器二进制重下 | 不入动作集（用户未点名该目标） |
| Docker stopped containers（49 个 stopped/created） | 1.661 GB 可写层上界 | engine-reported | PRESERVE | "Inspect every container; never classify by stopped status alone" | 引擎口径 1.661 GB reclaimable 上界；OrbStack 下删除后 df 延迟 | 容器状态丢失、无法 docker start 复用 | 不入动作集 |
| Docker dangling volumes（匿名卷） | 2.339 GB 引擎口径 reclaimable | engine-reported | USER-DECISION | "only content inspection tells you the second one" | 未测量内容；无引用不等于无价值 | 卷内数据不可恢复 | 不入动作集（内容检查需 Phase 1b 单独授权，本轮未做） |
| pip 缓存（`~/Library/Caches/pip`） | 308.7 MB | path-accounted（du） | REBUILDABLE | "pip cache purge # or for pip3 pip3 cache purge" | ≤308.7 MB（du 路径口径上界；purge 清空整个 wheel 缓存，内容全部是可重建的下载物） | 重下 Python wheel 包 | 入动作集 |
| Homebrew 下载缓存（brew 缓存目录） | 2.0 GB | path-accounted（du） | REBUILDABLE | "brew cleanup -s # Safe cleanup (removes old versions)" | unknown（`brew cleanup -s` 即 --scrub：连最新版本下载也清，但已安装 formula 的下载保留；实际释放取决于缓存构成，未逐对象测量） | 重下旧版本包 | 入动作集 |
| `~/Library/Caches` 应用缓存 top 项（Google 2.4 GB / LarkShell 2.1 GB / pypoetry 2.6 GB / VSCode ShipIt 1.4 GB / tencent workbuddy 1.0 GB） | 合计约 9.5 GB | path-accounted（du，逐项相加） | REBUILDABLE | "Inventory exact application-owned subdirectories first and prefer the application's supported cache-management command when one exists" | unknown（多为活跃应用缓存，未逐目录 lsof 验证 in-use；updater 类风险低但需用户逐个点名） | 应用重建缓存/重下更新包 | 不入动作集（需逐目录 in-use 验证与用户逐个批准） |
| `~/Library/Logs` | 364.4 MB | path-accounted（du） | USER-DECISION | "Diagnostic history; inspect before deletion" | 未逐文件检查 | 诊断历史丢失 | 不入动作集（取决于当前有无进行中的排查） |

动作集：pip 缓存（REBUILDABLE）+ Homebrew 下载缓存（REBUILDABLE）。
