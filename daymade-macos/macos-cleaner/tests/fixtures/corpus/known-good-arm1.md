# macOS 磁盘诊断与清理方案

调用 `macos-cleaner` skill 完成。**全程只读诊断，没有执行任何清理/删除/状态变更命令**（未跑 `npm cache clean`、`brew cleanup`、`uv cache clean/prune`、任何 `docker rmi`/`prune`、任何 `rm`、任何写操作的 `osascript`）。下面每条命令都停在确认闸门口。

---

## 一、当前状态

- 时间戳：2026-09-19 12:36:52 CST +0800
- 目标身份：HostName `Example Mac` / HostLabel `Example-Mac`（本机直连，非远端）
- 系统：macOS 26.6.2 (25G83)，aarch64
- 卷：`/System/Volumes/Data`
- 磁盘：1.8 Ti 总 / 1.7 Ti 已用 / **106 Gi 可用** / **95% 容量**
- 运行时：OrbStack（`orbctl status` = Running，`orbctl list` = `[]`），Docker 29.4.0，overlay2，Docker Root Dir `/var/lib/docker`
- 工具版本：uv 0.12.17、node v24.14.0、npm 11.9.0、pnpm 10.33.2、Homebrew 7.0.1
- 遵守的范围排除：未扫描 `~/Downloads`、`~/Desktop`、`~/Pictures`、`~/Documents` 等个人目录（本机 home-scan-guard 明确禁止以家目录为根的递归遍历，`analyze_large_files.py` 需要你先点名路径才跑）；未用 Mole；未做重复文件扫描；未查看任何凭据/数据库内容

## 二、证据

| 嫌疑对象 | 观测值 | 逻辑还是物理？ | 权威来源 | 置信度 |
|---|---:|---|---|---|
| `~/.cache/uv` | 41.45 GiB（archive-v0 38.44 GiB / environments-v2 95 MiB / wheels-v6 32 MiB） | path-accounted | `uv cache dir` + `du -sk` | 完整 |
| `~/.npm` | 17.75 GiB = `_cacache` 12.90 GiB + `_npx` 4.84 GiB + index-v5 57 MiB | path-accounted | `npm config get cache` + `du -sk` | 完整 |
| `~/Library/pnpm` | 17.21 GiB = store/v11 9.81 + v10 6.19 + v3 1.22 | path-accounted | `pnpm store path` + `du -sk` | 完整 |
| `~/Library/Caches/pnpm` | 3.80 GiB（v11 1.79 / metadata-v1.3 1.08 / dlx 0.48 / metadata-full 0.43） | path-accounted | `du -sk` | 完整 |
| Docker images | 引擎口径 51.48 GB，"RECLAIMABLE 23.78 GB (46%)" | 引擎口径，非主机物理 | `docker system df` / `df -v` | 完整（但口径需拆解，见下） |
| Docker build cache | 21.82 GB，371 条，0 条 active | 引擎口径 | `docker builder du` | 完整 |
| Docker containers | 1.668 GB，63 个（45 已停止），可回收 1.661 GB | 引擎可写层口径 | `docker system df` | 完整 |
| Docker local volumes | 25.8 GB，73 个（26 挂载中），可回收 2.339 GB | 引擎卷口径 | `docker system df -v` | 完整 |
| `~/Library/Caches` | 24.5 GB（42 个应用子目录） | path-accounted | `analyze_caches.py --user-only` | 完整 |
| `~/Library/Logs` | 360.2 MB | path-accounted | `analyze_caches.py --user-only` | 完整 |
| `~/Library/Caches/pypoetry` | 2.56 GiB（virtualenvs 1.59 / cache 0.52 / artifacts 0.45） | path-accounted | `du -sk` | 完整 |
| 5 个 updater 残留 | 2.23 GiB（flowzero 824 MB / kimi-desktop 821 MB / granola 252 MB / typeless 218 MB / cherrystudio 170 MB） | path-accounted | `du -sk` | 完整 |
| `find_app_remnants.py` | 未完成——300 s 超时转入后台，输出文件 0 字节 | n/a | 脚本自身 | **不完整**，不构成"无残留"结论 |

**三个必须点出的口径陷阱**（都是"看着大、实际释放不确定"的）：

1. **Docker 的 "RECLAIMABLE 23.78 GB" 不能当节省承诺。** 逐对象拆 `docker system df -v` 后，57 个 dangling image 里多数 `UNIQUE SIZE` 是 kB 级：`c5810ff4b86a` SIZE 260 MB 但 UNIQUE 仅 1.976 kB；`claude4dev-frontend:review-20260815` SIZE 53.1 MB、UNIQUE 0B；4 个 `vsc-devcontainerproject-*-features` SIZE 2.35 GB 但 UNIQUE 0B、SHARED 2.352 GB。按 skill 的物理释放规则，`UNIQUE SIZE` 才是"删除最后一个引用"的上界，所以删这些 dangling image 的实际释放接近 0。
2. **`store/v11`（9.81 GiB）是活的，不是死残留。** `pnpm store path` 返回 `v10`，很容易推出"v11/v3 是旧版本残留、共 11 GiB 可删"——错了：`~/.cache/node/corepack/v1/pnpm/` 里有 11.7.0 和 12.3.4，v11 目录 mtime 是 **昨天 21:38**，三个 store 世代各自对应一组在用的 pnpm 版本。用版本名推断"没人在用"正是 skill 闸门点名的失败模式。
3. **OrbStack 上删 Docker 对象不会立刻反映到主机 `df`。** 对象删除释放的是 VM 内空间，主机 APFS 要等稀疏镜像压缩。所以主机侧 `df` 不变不等于失败——这两个是必须分开写的两个后置条件。本机 `~/.orbstack` 只有 612 KB、`~/Library/OrbStack` 不存在、`orbctl list` 返回 `[]`，**主机侧稀疏镜像路径未能定位**，因此主机物理释放量记为 unknown。

**在用状态实测**（这一项推翻了两个"看起来很肥"的候选）：

- `com.microsoft.VSCode.ShipIt`（1.43 GiB）：**`ShipIt` 进程 PID 2076 正持有该目录下的 `ShipIt_stdout.log` / `ShipIt_stderr.log`** —— VS Code 此刻正在更新，这不是死残留。进程名检索在这条上不可靠（规则原文："an empty process-name search alone does not prove a path is inactive"），判定在用以打开文件句柄为准。
- `~/Library/Caches/Google`（2.4 GB）：Chrome PID 1969 持有一个 `129w` 写句柄打开 `Cache/No_Vary_Search/journal.baj` —— 在用。
- `com.tencent.workbuddy.mac.BundleMigration`（1.0 GB）：4 个打开文件句柄 —— 在用。
- **本机 `lsof +D` 每次都在 stderr 打 `WARNING: can't stat() nfs file system ~/OrbStack`（159 字节）**，按 skill 标定规则 stderr 非空即"扫描 incomplete"，`+D` 的空 stdout **不能**读成"不在用"。这台机器上可用的在用判定仪器是整机 `lsof -nP` 全量清单（exit 0）再做路径名匹配。

## 三、Phase 2 入口闸门（先于任何方案文字）

**闸门检查 1 —— 空闲空间目标：未设定。** 你没给目标值，我按纪律不自己发明一个。现状是 **106 Gi 可用 / 95% 容量**。请在方案末尾告诉我目标（GiB 或容量百分比，或两者）。没有目标，"扫出什么算什么"就变成按体积排序的噪音。

**闸门检查 2 —— 已打开 `references/cleanup_targets.md` 并逐条分类**（下面这张表就是产物，不是我的记忆）。

| 候选 | 名义大小 | 物理置信度 | 类别 | 管辖规则（原文引用） | 恢复代价 | 判定 |
|---|---:|---|---|---|---|---|
| `~/.cache/uv`（41.45 GiB） | 41.45 GiB | path-accounted | **PRESERVE** | "uv cache \| Downloaded/built Python packages \| Environments may need to fetch or rebuild dependencies again \| **Keep unless the user accepts dependency restoration cost**" | 重新拉取/重建依赖，可能很长 | 不入动作集，除非你接受 |
| `~/.npm/_cacache`（12.90 GiB） | 12.90 GiB | path-accounted | **PRESERVE** | "npm `_cacache` \| Downloaded package content \| `npm install` redownloads packages; constrained networks can turn this into a long reinstall \| **Keep; do not confuse it with `_npx`**" | `npm install` 重新下载全量包 | 不入动作集，除非你接受 |
| `~/.npm/_npx`（4.84 GiB） | 4.84 GiB | path-accounted | **PROPOSABLE** | "**`_npx` may go to Trash after confirming no `npx` process.** Keep `_cacache` by default; whole-cache removal requires explicit redownload approval." + "Never replace this narrow target with the whole npm cache." | 下次 `npx` 重新下载那些包 | **入动作集** |
| `~/Library/Caches/ms-playwright`（3.1 GB） | 3.1 GB | path-accounted | **PRESERVE** | "Playwright browser cache \| Browser binaries used by automation \| Browsers must be downloaded again; this can be several GiB \| **Keep when tests or automation use Playwright**" | 重下浏览器二进制，数 GiB | 不入动作集 |
| `~/Library/pnpm/store/{v10,v11,v3}`（17.21 GiB） | 17.21 GiB | path-accounted | **PRESERVE**（实证推翻"死残留"假设） | 无直接条目；适用 "Do not reopen a broad Mole scan for a named developer cache. **Resolve one exact path from the current tool/application configuration**" + 类别定义 "Size ratios are not evidence" | 重下所有依赖 | 不入动作集 |
| `~/Library/Caches/pnpm`（3.80 GiB） | 3.80 GiB | path-accounted | **USER-DECISION** | 无直接条目（"no rule found" 本身是发现）；适用 `~/Library/Caches` 通则 "Inventory exact application-owned subdirectories first and prefer the application's supported cache-management command when one exists." | `pnpm install` 元数据重取 | 不入动作集，等你定 |
| `~/Library/Caches/pypoetry`（2.56 GiB） | 2.56 GiB | path-accounted | **PROPOSABLE** | "no rule found"（本身是发现）；适用 "an exact application-owned cache directory may be removed only after verifying its owner, confirming the application is stopped or the directory is otherwise inactive, explaining rebuild/redownload impact, and receiving approval" | 若 poetry 回归则重下包与 venv | **入动作集** |
| `~/Library/Caches/Homebrew`（2.00 GiB） | 2.00 GiB | path-accounted | **PROPOSABLE**（但预期释放很小，见下） | "Cleanup after the exact Homebrew impact is approved: `brew cleanup -s` # Safe cleanup (removes old versions)" | 重下旧版本包 | **入动作集（低预期）** |
| `~/Library/Caches/Google`（2.4 GB） | 2.4 GB | path-accounted | **PRESERVE**（此刻在用） | "Do not remove an exact cache directory while its owning application or service is using it." | n/a | 不入动作集 |
| `~/Library/Caches/LarkShell`（2.1 GB） | 2.1 GB | path-accounted | **PRESERVE**（Lark 12 个进程在跑） | 同上 | n/a | 不入动作集 |
| `com.microsoft.VSCode.ShipIt`（1.43 GiB） | 1.43 GiB | path-accounted | **PRESERVE**（ShipIt PID 2076 持有文件句柄） | 同上 + "an empty process-name search alone does not prove a path is inactive" | n/a | 不入动作集 |
| `com.tencent.workbuddy.mac.BundleMigration`（1.0 GB） | 1.0 GB | path-accounted | **PRESERVE**（4 个打开句柄） | 同上 | n/a | 不入动作集 |
| 5 个 `*-updater`（2.23 GiB） | 2.23 GiB | path-accounted | **USER-DECISION** | "If none exists, verify the owning application is stopped or the directory is otherwise inactive." —— 我完成了 inactive 检查（0 打开文件），**未完成属主是否仍安装的核查** | 下次更新重新下载 | 不入动作集，等你确认 |
| Docker build cache（21.82 GB） | 21.82 GB | 引擎口径 | **报告但不可执行** | "This skill does not use `docker builder prune` or `docker buildx prune`. They are category-wide prune commands and conflict with this skill's explicit prune prohibition." + "**Do not advertise the build-cache number as reclaimable space this skill can automatically deliver.**" | 重建缓存 | **不入动作集** |
| Docker 4 个未引用 `aicms-local-uat` image | 4 × 289.7 MB UNIQUE | UNIQUE = 删除上界 | **USER-DECISION** | "If empty → eligible for an explicit user decision; exact command: `docker rmi <IMAGE_ID>`" | 重新 build/拉取 | 等你逐个确认 |
| Docker 45 个已停止 container | 1.66 GB 可写层 | 引擎口径 | **USER-DECISION** | "Stopped containers may be restarted -- verify with user" + "Inspect every container; **never classify by stopped status alone**" | 容器内状态丢失 | 等你逐个确认 |
| Docker 47 个 dangling volume | 含 `supabase_db_YOUR_PROJECT_REF` 83 MB、`act-toolcache` 197 MB、约 40 个匿名 40-50 MB | 引擎卷口径 | **USER-DECISION**（含数据库红旗） | "\"Not referenced by any current container\" is tempting to treat as sufficient evidence they're safe to remove. **It isn't**: a real inspection of 10 randomly sampled anonymous volumes found **5 of the 10 were live PostgreSQL data directories**" | 可能不可逆丢数据 | 等你确认，且需内容检查 |
| `~/Library/Logs`（360.2 MB） | 360.2 MB | path-accounted | **USER-DECISION** | "After confirming no active investigation needs the logs, move exact named files/directories through the recoverable Finder Trash path" | 丢失诊断历史 | 等你确认 |
| `~/Library/Caches/pip`（301 MiB） | 301 MiB | path-accounted | **PROPOSABLE** | "Cleanup after the redownload impact is approved: `pip cache purge`" | 重下 wheel | **入动作集** |

**闸门检查 3 —— 工具验证**（每条破坏性命令的版本 / 语义来源 / 已知问题）：

- `brew cleanup -s`：brew **7.0.1**，语义取自 `brew cleanup --help` 原文："Remove stale lock files and outdated downloads for all formulae and casks, and remove old versions of installed formulae… Removes all downloads more than 120 days old"；`-s/--scrub` 原文："Scrub the cache, including downloads for even the latest versions. **Note that downloads for any installed formulae or casks will still not be deleted.**"
  - **已知问题实测**：`brew cleanup -s -n`（只读 dry-run）跑出 136 行全是 `Warning: Skipping <formula>: most recent version X not installed`。也就是说 `-s` 在这台机器上会跳过绝大部分条目——2.00 GiB 的 Homebrew 缓存主要是**已安装** formula 的下载，而 `-s` 明确不删这些。**预期释放很小且不可精确预估**，我把它从"2 GB 立得"降级。
- `pnpm store prune`（未入动作集，仅备案）：pnpm **10.33.2**，`pnpm store prune --help` 原文："Removes unreferenced (extraneous, orphan) packages from the store. Pruning the store is not harmful, but might slow down future installations." 注意这与 `uv cache prune` 的本质差别：pnpm 的"unreferenced"是它自己内容寻址图里的引用关系，uv 的"unreachable"不是 venv 存活关系。因为活跃 store 实际是 `v11`（corepack pnpm 11.7.0/12.3.4 在用），这条我**不**放进方案。
- `uv`：**0.12.17**（≥0.12.x，所以 symlink-following prune 那个 bug #19542 在此版本已修）。但 `cleanup_targets.md` 写明 `uv cache prune` 不被本 skill 认可："\"Unreachable\" is cache-graph reachability, not venv liveness… **Check `uv --version` before proposing any cache-graph command; prefer the sanctioned `uv cache clean <exact-package>` above.**" 所以我不提 `prune`，只在你解锁 uv 缓存时给 `uv cache clean <exact-package>`。
- `docker rmi <exact-ID>`：Docker **29.4.0**，逐对象已核 `docker ps -a --filter ancestor=<ID>` 为空（不是类别级命令）。
  - **已知问题**：OrbStack 上主机 `df` 不随对象删除立即变化（稀疏镜像未压缩），且 `du` 对 APFS clone 是 path-accounted 不是物理。
- Finder Trash 分支：`npm` 11.9.0 为属主权威（`npm config get cache` → `~/.npm`）；`_npx` 属主已验证，inactive 已验证（**0 个 npx 进程、0 个打开文件句柄**）。

## 四、候选排序

| 排名 | 精确候选 | 名义/path-accounted | 预期物理释放 | 置信度 | 为什么排这里 |
|---:|---|---:|---:|---|---|
| 1 | `~/.npm/_npx` | 4.84 GiB | ≈4.84 GiB（路径独立、无共享层） | 高 | 规则点名的窄目标；inactive 已实测；代价只是下次 npx 重下 |
| 2 | `~/Library/Caches/pypoetry` | 2.56 GiB | ≈2.56 GiB | 中高 | 属主已不在 PATH（无 poetry 模块/二进制）+ 0 打开句柄；残留风险见下 |
| 3 | 4 个未引用 `aicms-local-uat` image | 4 × 289.7 MB UNIQUE | ≤1.16 GB（上界，且受共享层影响） | 中 | 逐对象核过无容器引用；OrbStack 主机释放需再压缩 |
| 4 | 5 个 `*-updater` 残留 | 2.23 GiB | ≤2.23 GiB | 中 | inactive 已测，但属主是否仍安装未核，故不进动作集 |
| 5 | `~/Library/Caches/Homebrew` | 2.00 GiB | **未知，实测倾向很小** | 低 | `-s` 拒绝删已安装 formula 的下载，dry-run 全是 skip |
| 6 | `~/Library/Caches/pip` | 301 MiB | ≈301 MiB | 高 | skill 认可的命令，量小 |
| — | **`~/.cache/uv` 41.45 GiB / `~/.npm/_cacache` 12.90 GiB / pnpm 17.21 GiB / build cache 21.82 GB** | 见证据表 | **不确定，且按规则默认保留** | — | 这是你最大的可见热点，但都属于 PRESERVE 或不可执行。**放出来让你自己决定解锁，不是替你决定** |

## 五、建议命令（尚未执行任何一条）

| # | 精确命令 | 精确目标 | 改什么 | 可恢复性 | 预期物理释放 | 用户/服务影响 | 必需后置条件 |
|---:|---|---|---|---|---:|---|---|
| 1 | `/usr/bin/osascript -e 'on run argv' -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' -e 'end run' -- "~/.npm/_npx"` | 仅 `_npx` 这一个目录 | 把 npx 临时包缓存移入废纸篓 | 废纸篓可恢复；**未清空废纸篓前不释放物理空间** | ≈4.84 GiB | 下次 `npx <pkg>` 需重新下载那些包 | `ls -d ~/.npm/_npx` 已不在原路径（在废纸篓内）；`_cacache` 12.90 GiB 仍原地未动 |
| 2 | 同上 Finder 命令，目标 `"~/Library/Caches/pypoetry"` | 仅 pypoetry 缓存目录 | 移入废纸篓 | 废纸篓可恢复 | ≈2.56 GiB | poetry 若回归需重下包与 venv | 目录已不在原路径；`du -sk` 前/后对比 |
| 3 | `brew cleanup -s` | 整个 Homebrew 缓存（类别级，但 brew 自带护栏） | 删过期下载与已安装 formula 的旧版本 | 仅重下 | **未知，dry-run 显示大量 skip，倾向远小于 2.00 GiB** | 下次装/升级需重下旧版本 | `du -sk "$(brew --cache)"` 前后对比 |
| 4 | `docker rmi 4c9784ec363d b25d0595013c 9674c22e71fb 82ed507d050e` | 仅这 4 个**未被任何容器引用**的 `aicms-local-uat` tag（保留正在用的 `10235343b373`） | 删除这 4 个镜像 tag | 仅重新 build/拉取 | ≤1.16 GB（UNIQUE 口径上界；VM 内） | 那 4 个 SHA tag 的镜像不再可 `docker run` | `docker images aicms-local-uat` 只剩 1 个 tag；主机 `df -k` **可能不变**，需另行执行 OrbStack 压缩 |
| 5 | `pip cache purge` | pip 缓存 | 清空 wheel 缓存 | 仅重下 | ≈301 MiB | 下次装包需重下 | `du -sk ~/Library/Caches/pip` 显著下降 |
| 6 | （仅在你明确要求后）OrbStack → Settings → Reclaim disk space | 稀疏镜像压缩 | VM 内已释放空间回收到主机 APFS | 不可逆（压缩不可回退） | 承接 #4 的实际主机释放 | 需要 OrbStack 重启/短暂停顿 | `du -k` 稀疏镜像 + `df -k /System/Volumes/Data` 前后对比 |

**不在方案里的**（明确写清楚，不留悬空承诺）：

- **不使用任何 prune 家族命令**：`docker system prune` / `image prune` / `volume prune` / `container prune` / `builder prune` / `buildx prune` / `npm cache clean` / `uv cache prune`。
- **Docker build cache 的 21.82 GB 我不承诺能交付**：本 skill 明令不用 `builder prune`，所以这个数字只报告、不可执行。要拿这 21.82 GB，得由你自己决定并手动执行，或另行授权一条显式方案。
- **不删 `.git`**：`cleanup_targets.md` "Do not recommend deleting only `.git`: it silently converts a repository into an unversioned folder"。
- **不做内容目录大文件/重复文件扫描**：你没点名任何路径，按纪律跳过这一证据分支并在此声明未获授权，而不是拿 `~` 或 Downloads 顶替。
- **`find_app_remnants.py` 未完成**（300 s 超时、输出 0 字节）：卸载残留这一分支证据不完整，不能当作"没有残留"。

## 六、建议

**先做 #1 + #2（废纸篓，可恢复），预计 ≤7.4 GiB，零不可逆风险**，因为它们是你唯一两个"规则点名 + inactive 实测 + 只付重下代价"的候选。#3–#5 是低风险补充但预期释放小（#3 尤其，dry-run 已经证明 `-s` 在这台机器上基本会跳过）。

**但如果你要的是"一次拿到几十 GiB"，可选路径是解锁 PRESERVE，代价是重下：**

- `uv cache clean`（整缓存）：41.45 GiB 里 38.44 GiB 是 `archive-v0` 的包归档。规则要求你显式接受依赖恢复代价。**不要用 `uv cache prune`**（unreachable ≠ venv 存活）。
- `npm cache clean --force`：12.90 GiB，代价是 `npm install` 全量重下。
- 这两条我一条都没放进动作集，因为规则要求"这个对话里你接受该目标的恢复代价"才升级。

**顺带一个根因发现（Step 2D）**：`aicms-local-uat` 有 5 个 tag，命名是 `local-uat-<git-sha>-<sha>` 这种程序化格式，其中 4 个无任何容器引用、只有 1 个在用——这是 dev-loop 每次 build 都打新 tag 且从不回收旧 tag 的典型形态。清掉这 4 个只是清积压；要根治得在 build 成功后加保留策略（保留最近 N 个按 `docker image inspect --format '{{.Created}}'` 验证的真实创建时间排序的镜像）。**这类自动化保留逻辑需要你单独授权**，因为它会在未来每次 build 成功时无人值守地删镜像——这跟"你在我面前逐个确认"是不同 scope。建议先 dry-run/只记日志跑几次。

**关于 Docker 口径的一句实话**：`docker system df` 头条那个 "23.78 GB RECLAIMABLE" 是这台机器上最容易误读的数字。逐对象拆开后，dangling image 的实际 UNIQUE 释放接近 0，真正的大头在 build cache（21.82 GB，本 skill 不删）和卷（25.8 GB 里大部分在用或有数据库风险）。

**预期结果**（假设你只批准 #1–#5，且不含 OrbStack 压缩）：可用空间约从 106 Gi 升到 ~113 Gi，容量 95% → ~93%。**这个数字我标为假设，因为废纸篓未清空前不释放物理空间，而 OrbStack 主机侧释放需要单独执行压缩。**

## 七、确认闸门

**没有任何改变状态的命令已经执行。**

我缺少一项必要输入才能收尾：**你的空闲空间目标是多少？**（GiB、容量百分比，或两者）——现状 106 Gi 可用 / 95%。没有这个目标，上面的排序只是"按防御性物理释放排"，不是"达成你的目标"。

请回复：

1. 目标（例如"要 200 Gi 可用"或"降到 85%"）
2. 批准哪些编号（#1–#6），或说"全部" / "只做 #1 #2"
3. 是否解锁 uv 缓存（41.45 GiB）或 npm `_cacache`（12.90 GiB）——解锁即表示接受重下代价
4. 是否授权我针对 `aicms-local-uat` 写保留逻辑（另需 dry-run 先行）

只有你明确回复后我才会执行，并且会逐条单独跑、跑完读回后置条件。
