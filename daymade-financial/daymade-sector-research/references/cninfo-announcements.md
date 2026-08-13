# 公告检索接口（cninfo 巨潮 + 东财，实测形态 2026-08-13）

## 巨潮 cninfo（沪深 + 北交所统一主源）

```
POST http://www.cninfo.com.cn/new/hisAnnouncement/query
body（form-encoded）:
  pageNum=1&pageSize=30&column=szse|sse&tabName=fulltext
  &stock=<代码>,<orgId>&searchkey=&seDate=<start>~<end>
```

- 返回 JSON：`totalAnnouncement` 总数、`announcements` 数组（`announcementTitle` / `announcementTime` 毫秒时间戳 / `adjunctUrl` / `announcementTypeName`）
- **announcementTime 是毫秒时间戳，按北京时间（UTC+8）换算**成 `YYYY-MM-DD`，不是 UTC
- 公告 URL = `http://static.cninfo.com.cn/` + `adjunctUrl`
- 深市 column=szse、沪市 column=sse

### ⚠️ orgId 陷阱（2026-08-13 当日实测修正：orgId 一律 topSearch，禁自拼）

**orgId 一律用 topSearch 接口返回值，禁止按市场规则自拼**——不同市场/板块的 orgId 形态不一致，且存在多个拼错点，自拼必踩「查 0 条」假阴：

| 市场 | 实测样本 | topSearch 返回的 orgId | 自拼为何错 |
|---|---|---|---|
| 深市主板 | 000001 平安银行 | `gssz0000001` | 深市存在**两种形态**：gssz+补零 与 `9900xxxxxx`（002219 → `9900004301`），按股票不同，无规律可自拼 |
| 沪市主板 | 600613 神奇制药 | `gssh0600613` | 7 位补零位置易拼错：自拼 `gssh6000613` 实测 0 条（前导零在「0600613」） |
| 沪市科创板 | 688265 南模生物 | `gfbj0839728` | 数字部分（0839728）与代码**无关**，自拼 `gssh0688265` 实测 0 条 |
| 北交所 | 920946 森萱医药 | `gfbj0830946` | 同左，gfbj 前缀 + 补零代码 |

**全市场查真实 orgId**（沪深主板/科创/北交所统一走此接口）：

```
POST http://www.cninfo.com.cn/new/information/topSearch/query
body: keyWord=<6位代码>&maxNum=10
```

返回 JSON 数组，取 `code` 以目标代码开头的项的 `orgId` 字段。

- 标定实验：000001 能正常返回公告 = 接口本身正常；某股月窗 0 条先怀疑 orgId 参数错，不是「无公告」
- column 参数 sse/szse 实测对查询结果无影响（同 orgId 交叉测试结果相同），按市场填写即可
- **北交所（43/83/87/92 开头）巨潮覆盖**：topSearch 返回 `gfbj` 前缀 orgId（实测 920946 → `gfbj0830946`），与沪深同一查询通道。bse.cn 官网接口实测不可用（见下），勿再试
- 返回 `hasMore` 字段可判断翻页（pageSize=30）；公告数超 30 条必须翻页取全，不能只取第一页

### ⚠️ B 股公告挂在对应 A 股代码下（2026-08-13 实测）

巨潮与东财的 stock 参数**都不接受 B 股代码**（900904/200028 实测恒 0 条，即使 orgId 正确）。B 股公司的公告以 A 股代码发布，须用对应 A 股代码检索：

- topSearch 对 B 股代码返回的 orgId 是其 A 股公司的，沪/深 B 的 orgId 为 `gssh`/`gssz` 前缀 + **A 股代码** 7 位补零，反推可得 A 股代码：
  - 900904（神奇B股）→ orgId `gssh0600613` → A 股 **600613**（神奇制药），巨潮/东财月窗各 2 条 ✓
  - 200028（一致B）→ orgId `gssz0000028` → A 股 **000028**（国药一致），月窗各 12 条 ✓
- 脚本 `ann_query.py` 已内置自动转换（`b_share_a_code`），输出 stderr 标注「公告经 A 股 XXXX 检索」；orgId 反推失败（非 gssh/gssz 前缀）显式报出需人工确认，不静默

## 东财公告（交叉验证 + 类型回填）

```
GET https://np-anotice-stock.eastmoney.com/api/security/ann
  ?sr=-1&page_size=50&page_index=1&ann_type=A&client_source=web&stock_list=<代码>
```

- 返回 `data.list[]`：`title` / `notice_date`（YYYY-MM-DD HH:mm:ss）/ `art_code` / `columns[]`（公告类型数组）
- **⚠️ 类型在 `columns[0].column_name` 里，顶层 `column_name` 字段恒为 null**（2026-08-13 实测）——多类型时多个 columns 元素用「、」连接（如「股东大会决议公告、高管人员任职变动」）
- 公告 URL = `https://data.eastmoney.com/notices/detail/<代码>/<art_code>.html`
- **巨潮 `announcementTypeName` 常为 null** → 用东财 columns[].column_name 按「日期 + 标题」匹配回填；标题比对前归一化（全/半角括号归一化 + 去空格 + **剥离东财「公司名:」前缀**），日期允许 ±1 天容差（实测样本多为同日，容差只防两源口径偶发差异）
- **投资者关系活动记录表：两源覆盖不完全一致**（2026-08-13 实测）——002437 的 07-23 投资者关系管理信息仅东财有；920946 的 05-14「投资者关系活动记录表」巨潮有收录（在 90 天宽窗之外、约 135 天窗口可得——巨潮也收录部分投关表）。东财独有条目补并集；来源区分看 URL 域名（cninfo.com.cn vs data.eastmoney.com），无需单独来源列
- 响应 `data.total_hits` 为总数，`page_size=50`；公告数超 50 条必须按 `page_index` 翻页取全（脚本已内置，上限 20 页保护）
- 2026-08-13 实测：东财公告接口可不带 Referer（带 `https://data.eastmoney.com/` 亦可）

## 北交所 bse.cn 官网接口（已知不可用，勿再试）

2026-08-13 实测三重失效，已弃用（北交所改走巨潮 gfbj 通道 + 东财交叉）：

1. **WAF**：直接 POST 返回 403，需先 GET 拿 cookie 且稳定性差
2. **结构过期**：文档写 `data[0].listInfo.content[]`，实测返回结构已变
3. **参数被忽略**：`companyCd` 被服务端忽略，返回全市场公告流，无法按公司过滤

```
POST https://www.bse.cn/disclosureInfoController/initDisclosureList.do
...
```

另一端点 `companyAnnouncement.do` 多组参数组合均返回空。以上均为「已试过、不可用」的记录，不是可用路径。

## 0 条双向读（月窗口 0 条 ≠ 真无公告）

月窗口返回 0 条时，必须同时做两件事再下结论：

1. **扩宽窗**：同参数查 90 天窗口。**判据 = 宽窗最新公告日期 vs 月窗起点**：宽窗最新公告落在月窗内 → 月窗 0 条是参数/orgId 问题，不是「真无」；宽窗最新公告早于月窗起点（或宽窗也 0）→ 真无公告，继续第 2 步
2. **第二源核对**：东财接口查最新公告日期。两源都说「最近无公告」→ 才可写「该标的近一月无公告」

实战案例：002172 月窗 0 条，宽窗（90 天）仅 1 条（07-09 质押公告）、东财确认最新公告 07-09 → 真无公告，参数正确。920946 月窗 0 条，宽窗 8 条但最新 05-21（早于月窗起点）→ 同样是真无，不是参数错——**「宽窗有公告」本身不构成参数错误证据，必须看宽窗最新日期**。

## 脚本

`scripts/ann_query.py` 已内置以上全部逻辑（orgId 一律 topSearch 解析、B 股自动转 A 股代码、双源交叉、类型回填、两源翻页、0 条扩宽窗判据、URL 抽查）。调用前必须去代理环境变量（国内站点）。输出表头：`股票代码,股票名称,公告标题,公告日期,公告类型(如有),公告URL,时间窗口(1周|1月)`，utf-8-sig 编码（Excel 兼容）。

**分桶规则**：周窗口（近 7 天）内的标 `1周`，月窗口（近 31 天）其余标 `1月`，互斥不重复。注意：某些手动/半自动产物出现过同一公告同时标两个窗口的重复行（错误示例），分桶必须互斥。
