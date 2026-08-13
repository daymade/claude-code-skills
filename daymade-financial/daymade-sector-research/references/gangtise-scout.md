# Gangtise 数据能力侦察与 Pivot 决策

2026-08-13 医药行业投研实战沉淀。Gangtise 官方 skills 位于 `~/.claude/skills/gangtise-*`（dashboard/data/file/kb/private 五件套）。

## 侦察结论（2026-08-13 实测）

| 能力 | 端点/脚本 | 实测结果 |
|---|---|---|
| 实时行情 | `quote.py` | ✅ 可用 |
| 股票池 | `stockpool.py` | ✅ 可用 |
| 行业列表 | `get_industries.py` | ✅ 可用 |
| 内容搜索（全部） | 各 search 端点 | ❌ 一律 `POINT_NOT_ENOUGH`（积分不足） |

## 「积分不足」的判定方法：对照实验

同一凭据出现「某些端点一通、某些端点一挂」时，**不要直接下「额度耗尽」结论**——那是一个整体性解释，而部分端点正常本身就与它矛盾。正确动作：

1. **同一凭据换端点**：内容搜索全挂但行情类可用 → 是积分体系对内容搜索的单独限制，不是账号整体问题
2. **把参数缩到最小**：最小化请求体确认不是参数错
3. **读提示文本 vs 读判定逻辑分开**：「积分不足」是运营话术，判断根因要靠上述对照实验，不靠文案

实测结论：内容搜索端点积分不足是稳定的，无法通过换参数绕过。**不等待充值，直接 pivot。**

## Pivot 映射表

| 原 Gangtise 用途 | 公开源替代 |
|---|---|
| 板块 Top N 涨幅 | 东财 push2 成分股（`b:BKxxxx`）+ 新浪 hq.sinajs.cn 实时快照 → [market-data.md](market-data.md) |
| 个股公告 | 巨潮 cninfo + 东财 np-anotice 双源 → [cninfo-announcements.md](cninfo-announcements.md) |
| 行业情绪/新闻 | 公开行情指数 + 媒体检索 → [sentiment-evidence.md](sentiment-evidence.md) |

## 铁律

- **Pivot 必须告知用户**：侦察出「某数据源不可用」并切换后，在报告开篇披露「用了哪些源、哪些不可用、为何 pivot」。静默切换数据源 = 用户以为数据来自 Gangtise 实际来自别处，破坏可追溯性。
- 侦察是 Phase 0 的固定步骤，不是「遇到报错再处理」：用户点名 Gangtise 时先跑一遍可用性矩阵（几分钟），再定 Phase 1 数据链。
