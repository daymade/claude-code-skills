# macOS 磁盘清理方案 — Phase 2

## 动作集（待确认执行清单）

| 优先级 | 候选 | 精确命令 | 预期物理释放 | 影响 | 恢复 | 后置条件 |
|---|---|---|---|---|---|---|
| 1 | pip 缓存（`~/Library/Caches/pip`） | `pip cache purge` | ≤308.7 MB | 重下 wheel | 可重建 | `du -sk ~/Library/Caches/pip` 归零 |
| 2 | uv 缓存 | `uv cache prune` | 42.0 GiB：清掉不可达对象 | 部分依赖需重建 | 重下依赖 | `uv cache dir` 体积显著下降 |
| 3 | npm 缓存 | `npm cache clean --force` | 17.7 GiB | npm install 重下全部包 | 可重建 | `du -sk ~/.npm` 归零 |

## 工具验证（版本与语义来源）

- uv 0.12.17（`uv --version` 实测）。语义来源：`uv cache prune --help` 原文。
- npm 10.9.0（`npm --version` 实测）。语义来源：`npm cache clean --help` 原文。
- pip 26.0.1（`pip3 --version` 实测）。语义来源：`pip3 cache purge --help` 原文："Inspect and manage pip's wheel cache."
