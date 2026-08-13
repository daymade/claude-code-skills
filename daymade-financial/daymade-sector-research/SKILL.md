---
name: daymade-sector-research
description: |-
  A股行业投研工作流：全板块 Top N 涨幅标的计算、公告窗口检索（周/月）、市场情绪证据分级判断，并以 Agent Team 并行执行 + fresh-context 对抗验证。

  触发场景（命中任一即读本 skill）：
  - 「XX 行业 Top N / Top 10 标的」（如「医药行业今天的 Top 10 标的」）
  - 「这些标的最近一周 / 一个月发过哪些公告」
  - 「判断 XX 行业 / 板块现在的市场情绪怎么样」
  - 「用 Agent Team / 多 agent 做行业投研」或要求对行业研究结论做对抗性验证
  - 需要「基于证据、基于数据」的板块级研究交付（成分股 → 行情 → 公告 → 情绪 → 验证 → 报告）

  核心能力：东财 push2 成分股 → 新浪实时快照涨幅排序（scripts/top_n_pipeline.py）；巨潮 cninfo + 东财公告双源交叉，沪深+北交所统一通道（scripts/ann_query.py）；情绪证据 L1（一手行情）/L2（带时间戳媒体）/L3（未核实标题）分级；Agent Team 并行编排与验证纪律。全程国内公开数据源，无付费依赖；Gangtise 官方 skill 为可选增强（需积分，缺失时走公开源 pivot）。

  最高纪律（用户原话）：没有十足把握的事，宁可标注不确定，不可给错误答案。
---

# A股行业投研 Skill

对某个申万行业/东财板块做一次完整投研交付：**Top N 涨幅标的 → 公告窗口检索 → 市场情绪判断 → Agent Team 对抗验证 → 综合报告**。

## 铁律（每次执行都必须遵守，违反代价最高）

1. **宁可标注不确定，不可给错误答案**（用户原话，最高纪律）。没有十足把握的事实写「不确定/未核实」，不编、不猜、不省略来源。推断与观察必须分开表述。
2. **基于证据、基于数据**。每个结论 trace 到一手数据源（API 返回 / CSV 落盘 / 官方公告）；汇报数值时从工具输出原文照抄，禁凭印象转写。
3. **证据分级 L1–L3**：L1 一手行情（交易所/行情接口实时值）；L2 带时间戳的媒体/公告报道；L3 未核实标题或传闻。判断情绪时只允许 L1/L2 承重，L3 只能作为「待核实线索」列出。
4. **0 条双向读**：月窗口公告 0 条 ≠ 真无公告。必须扩宽窗（90 天）+ 第二数据源核对，证明「真无」或发现参数错误，才能下结论。
5. **双源交叉**：公告检索必须巨潮 + 东财两源对照；单一数据源发现的「重要公告」也要在另一源确认存在，不一致必须如实标注。
6. **盘中快照标注漂移**：盘中取的行情数值是瞬时快照会漂移，任何引用必须带快照时间戳，报告里注明「盘中快照」。
7. **数值照抄落盘 CSV**：中间数值必须落盘（脚本输出 CSV / agent 落盘文件），报告引用时照抄 CSV 值，不凭对话记忆。
8. **Agent Team 编排纪律**：见 [references/agent-orchestration.md](references/agent-orchestration.md)——子代理显式 `model:'sonnet'`；SendMessage 交付协议；每条 finding 带可证伪锚点；验证用 fresh-context 对抗性 agent；禁 spawn 重复 agent。

## 工作流（五阶段）

```
Phase 0  数据能力侦察 → 必要时 pivot 公开源
Phase 1  并行三 agent：Top N 名单 / 涨跌幅分桶分布 / 情绪证据清单
Phase 2  公告检索：Top N 全标的 × 周窗口 + 月窗口，双源交叉
Phase 3  对抗验证：fresh-context agent 复核假设（用户原话：「看哪些假设是错的」）
Phase 4  综合报告：名单 + 公告 + 情绪分级 + 显式不确定标注
```

### Phase 0 — 数据能力侦察（Gangtise pivot 决策）

若用户点名 Gangtise（或其官方 skill），先侦察可用性再决定数据源：

1. **对照实验判「额度」**：同一凭据某些端点可用（如 `quote.py`、`stockpool.py`、`get_industries.py`）而内容搜索端点全报 `POINT_NOT_ENOUGH` → 这是积分不足的整体性解释，同一凭据一通一挂已否定「网络/配置问题」；若不同端点表现不一致，别急着下「额度耗尽」结论，做对照实验（换端点/换参数/最小请求）。
2. **pivot 决策表**：内容搜索不可用 → Top N 改东财成分股+新浪快照；公告改 cninfo+东财；情绪改公开行情+媒体。侦察结论与 pivot 决策**必须告知用户**，不静默切换数据源。
3. 完整侦察矩阵（各端点实测形态、积分报错、对照实验）→ [references/gangtise-scout.md](references/gangtise-scout.md)

### Phase 1 — 并行三 agent

派 3 个并行 agent（显式 sonnet），每个 prompt 附可证伪锚点要求：

| Agent | 交付物 | 数据链 |
|---|---|---|
| Top N 名单 | `top{N}_{board}_{日期}.csv` | `scripts/top_n_pipeline.py`（东财成分股 → 新浪快照 → 涨幅排序） |
| 涨跌分桶分布 | `distribution_{board}_{日期}.csv` + 市场宽度结论 | 全板块快照按 6 分桶（>5%/2-5%/0-2%/0%/-2-0%/<-2%）+ up/down/flat 汇总，六桶 count 加和必须等于 total |
| 情绪证据清单 | 分层证据表（L1/L2/L3 各列） | 一手行情 + 媒体检索 |

行情与板块接口细节 → [references/market-data.md](references/market-data.md)；情绪证据方法与信源 → [references/sentiment-evidence.md](references/sentiment-evidence.md)。

### Phase 2 — 公告检索

对 Top N 全标的查公告，周窗口（近 7 天）与月窗口（近 31 天）互斥分桶：

```bash
# 脚本路径按本 skill 安装目录（SKILL.md 同级目录下的 scripts/）执行，示例用相对路径仅指 skill 包内
cd <本 skill 安装目录>
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  python3 scripts/ann_query.py --codes 002219,600613,920946 \
  --end 2026-08-13 --out-dir /path/out \
  --universe-csv /path/top10_xxx.csv
```

脚本内置：巨潮 orgId 一律 topSearch 解析（禁按市场自拼，深市双形态/沪市前导零/科创板 gfbj 均实测拼错即假阴）、B 股（900/200 开头）自动转对应 A 股代码检索、双源交叉与类型回填、两源翻页、月窗 0 条自动扩宽窗判据（宽窗最新日期 vs 月窗起点）、URL 抽查。orgId 陷阱与接口形态 → [references/cninfo-announcements.md](references/cninfo-announcements.md)。

**分桶规则**：公告日期落在周窗口内标 `1周`，否则（仍在月窗口内）标 `1月`，互斥不重复。输出表头：`股票代码,股票名称,公告标题,公告日期,公告类型(如有),公告URL,时间窗口(1周|1月)`。

**必做验证**：① 双源交叉（巨潮 vs 东财）计数一致；② 0 条标的扩宽窗确认「真无」；③ 两源覆盖不完全一致（部分投关类公告仅东财有、部分巨潮也收录），东财独有条目补并集并按 URL 域名标注来源。

### Phase 3 — 对抗验证（用户原话：「看哪些假设是错的」）

派 2 个 **fresh-context** 对抗性 agent（不 fork，不共享本会话上下文），各自带验证轴：

- **验证轴 1 · 方法论与数值**：Top N 名单重算（独立重跑数据链）、分桶统计重算（六桶 count 加和 = total）、快照时间戳核对
- **验证轴 2 · 公告完整性与情绪证据强度**：抽查公告月窗口是否漏检、情绪结论逐条检查是否 L1/L2 承重、有无未标注的推断

每个 agent 的 finding 必须带可证伪锚点（具体数值/URL/命令输出），prompt 中明令「编造不如标不确定」。验证结果在综合报告中单独成节：**哪些假设被推翻、哪些被确认、哪些无法验证**。编排细节 → [references/agent-orchestration.md](references/agent-orchestration.md)。

### Phase 4 — 综合报告

交付结构：

1. **数据源与 pivot 披露**：用了哪些源、哪些不可用、为何 pivot
2. **Top N 名单**：表格（排名/代码/名称/涨幅/价格/成交额）+ 快照时间戳
3. **公告清单**：周/月分桶，按标的聚合，标注来源与交叉验证结果
4. **情绪判断**：L1–L3 分层呈现，结论明确标注证据等级；证据不足的维度写「不确定：无 L1/L2 证据」
5. **验证结果**：对抗验证发现、假设推翻清单
6. **不确定项清单**：所有未达「十足把握」的条目显式列出

报告数值一律照抄落盘 CSV，禁止凭记忆转写。

## 环境约束

- 国内站点（东财/新浪/巨潮）curl/脚本必须去代理：`env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY`
- Python 用 `uv run --no-project` 或系统 python3（脚本 stdlib only）
- 新浪快照返回 GBK 编码，需 Referer `https://finance.sina.com.cn`；东财公告接口可不带 Referer（实测）；北交所公告不单独走 bse.cn（官网接口三重失效，走巨潮 gfbj 通道）
- 若 push2 域名解析进 198.18.0.0/15（代理 TUN fake-IP），去代理无效，须修代理分流或用 `curl --resolve` 直连真实 IP（见 references/market-data.md）
