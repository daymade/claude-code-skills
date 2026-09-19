# macOS 磁盘清理方案 — Phase 2（停在确认闸门，本轮不执行任何命令）

## 当前状态

- 时间：2026-09-19 14:0x CST
- 机器：Example Mac，macOS 26.6.2 (25G83)，本地机（非远程）
- 磁盘：`/System/Volumes/Data` 共 1.8Ti，已用 1.7Ti，**可用 106Gi，95% 容量**
- 用户声明：重度开发用户（Python/Node/Docker 日常用）

## 关于释放目标（入口闸门第 1 步）

你未提供具体释放目标。当前可用空间 106Gi，所以"快满了"更多是容量百分比意义上的（95%），而非绝对空间耗尽。本方案按**可辩护物理释放**排序，不声称满足某个未声明的目标。如果你心里有目标（比如"再腾出 X GiB"或"降到 85% 容量以下"），告诉我，我按目标重排优先级。

## 动作集（待确认执行清单）

这两项已逐条核对：不在 preserve-by-default 表内、有官方管理命令、恢复成本明确。命令按顺序单独执行，每条跑完先读结果再跑下一条。

| 优先级 | 候选 | 精确命令 | 预期物理释放 | 影响 | 恢复 | 后置条件 |
|---|---|---|---|---|---|---|
| 1 | pip 缓存（`~/Library/Caches/pip`） | `pip cache purge` | ≤308.7 MB（du 路径口径上界；purge 清空整个 wheel 缓存，内容全部是可重建的下载物） | 下次 pip install 需重下 wheel；本机网络良好，成本低 | 缓存可完全重建，无需备份 | `du -sk ~/Library/Caches/pip` 归零或接近零；`pip cache info` 显示缓存为 0 |
| 2 | Homebrew 下载缓存 | `brew cleanup -s` | unknown（`-s` 即 --scrub：连最新版本下载也清，但已安装 formula 的下载保留；实际释放取决于缓存构成，本次未逐对象测量，不给出数字承诺；路径口径总量见分类表） | 下次 brew install/upgrade 需重下包 | 可完全重建 | `brew cleanup -s -n`（dry-run）输出为空或显著缩小；df -k 立即可见变化（真实文件） |

建议先 `brew cleanup -s -n` 预览删除清单再决定。

## Docker：本机最大的可辩护候选，但需要你逐对象确认（不在自动动作集）

实测（2026-09-19，`docker system df` / `docker system df -v` / `docker images -f dangling=true` + 逐对象 ancestor 验证）：

- **57 个 dangling 镜像，其中 55 个无任何容器引用**（含 stopped 容器）。
- 可辩护释放上界：**6.47 GiB**（57 行 UNIQUE SIZE 求和）。引擎视角的 "reclaimable 23.78 GB" 含共享层，**不能按单次删除分配**——例如 `c5810ff4b86a` 显示 260MB，UNIQUE 仅 1.976kB，删它几乎不释放空间。
- **当前 Docker 引擎是 OrbStack**：`docker rmi` 释放的是 VM 内部空间，主机 `df` 不会立即变化，需要 OrbStack 设置里的 "Reclaim disk space"（稀疏镜像 compaction）才反映到 macOS。
- 执行形态（每步只读验证后再删，一次一个 ID）：

```bash
docker ps -a --filter "ancestor=<IMAGE_ID>" --format "{{.Names}}\t{{.Status}}"
# 输出为空 → docker rmi <IMAGE_ID>
```

- 另注意到 `aicms-local-uat` 仓库有 5 个 build hash tag（每个 unique 289.7MB，只有最新一个被容器引用），符合 "构建管线每跑一次打一个新 tag" 模式；这些是有 tag 的旧镜像（非 dangling），删除前建议确认你的构建保留策略。

## 决策清单（需要你点名才能解锁）

按路径口径大小排序。每项都保留默认，解锁成本如实列出：

| 候选 | 路径口径 | 解锁成本 |
|---|---|---|
| `.cache/uv` | 42.3 GB | 重建全部 Python 依赖。本 skill 硬排除 `uv cache prune`（reachability 语义问题 + 0.12 以下 symlink bug；你的 uv 已是 0.12.17，bug 已修但语义问题仍在）。唯一 sanctioned 形式是 `uv cache clean <exact-package>`，仍需你点名具体包 |
| `.cache/huggingface` | 28.2 GB | 模型权重重下（小时级，可能离线不可得） |
| `~/.npm`（_cacache） | 17.7 GB | npm install 重下全部包；受限制网络下可能变成漫长重装 |
| Docker build cache | 21.82 GB（private 20.26 GB） | 本 skill 只报不删：Docker 对 build cache 只有 prune 家族控制，无法表达逐对象意图。你若要用 `docker builder prune` 属自行决定 |
| `.cache/modelscope` | 4.2 GB | 模型重下 |
| `~/Library/Caches/pnpm` | 3.8 GB | pnpm 包重下。**cleanup_targets.md 无 pnpm 条目（no rule found）**，需要你决定是否清理 |
| `~/Library/Caches/ms-playwright` | 3.1 GB | 浏览器二进制重下；你有自动化项目，默认保留 |
| `~/Library/Caches` 应用缓存 top 项（Google 2.4 / LarkShell 2.1 / pypoetry 2.6 / VSCode ShipIt 1.4 / tencent workbuddy 1.0 GB） | 合计约 9.5 GB | 多为活跃应用缓存，需逐目录 lsof 验证不在用；updater 类缓存（flowzero/kimi/typeless 等，合计约 2 GB）风险较低 |
| Docker stopped containers | 49 个 | 容器状态丢失、无法 docker start 复用 |
| Docker dangling volumes（匿名卷） | 2.339 GB 引擎口径 | 卷内数据不可恢复；**无引用不等于无价值**，内容检查需单独授权（会创建临时容器），本轮未做 |
| `~/Library/Logs` | 364.4 MB | 诊断历史丢失；取决于你当前有无进行中的排查 |

## 明确排除（本轮不提议）

- `uv cache prune`：不进方案（cleanup_targets.md 硬排除）
- `npm cache clean --force`：不使用（_cacache 保留默认）
- docker prune 家族（image/volume/system/builder/buildx）：不执行任何一条
- `docker builder prune`：不执行（build cache 删除超出本 skill 执行范围，只报不删）

## 确认闸门

以上命令**均未执行**（本轮为只读诊断 + 方案）。请回复：

1. 是否执行动作集两项（pip cache purge / brew cleanup -s）？
2. 是否逐对象清理 Docker dangling 镜像（我会逐个列出 55 个 ID 供你勾选）？
3. 决策清单里有没有你想点名解锁的项（特别是 pnpm 3.8 GB——它是唯一无规则覆盖的候选）？
4. 你的释放目标是多少？

## 工具验证（版本与语义来源）

- Homebrew 7.0.1（`brew --version` 实测）。`brew cleanup --help` 原文："Remove stale lock files and outdated downloads for all formulae and casks, and remove old versions of installed formulae."；"-s, --scrub Scrub the cache, including downloads for even the latest versions. Note that downloads for any installed formulae or casks will still be kept"；"Removes all downloads more than 120 days old"；支持 `-n, --dry-run` 预览。语义来源：brew 自带帮助（非 skill 转录）。
- pip 26.0.1（`pip3 --version` 实测，python 3.9）。`pip3 cache purge --help` 原文："Inspect and manage pip's wheel cache."，purge 清空缓存目录。语义来源：pip 自带帮助（非 skill 转录）。
- Docker 29.4.0（`docker --version` 实测），context 为 OrbStack。`docker system df -v` 的 UNIQUE SIZE 列为逐对象释放上界依据；semantics 来源：docker_analysis.md 的物理释放报告规则 + 实测 system df -v 输出。
- uv 0.12.17（`uv --version` 实测）——仅记录版本，用于说明 prune 硬排除中 "0.12 以下 symlink bug" 在你机器上已不适用。
