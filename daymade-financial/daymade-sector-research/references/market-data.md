# 行情与板块数据接口（实测形态，2026-08-13）

## 东财 push2 板块成分股

```
GET https://push2.eastmoney.com/api/qt/clist/get
  ?pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs=b:BK1216&fields=f12,f14
```

- `f12` = 股票代码，`f14` = 名称；`fid=f3` 按涨幅排序（分页取成分股时排序无意义，靠 `data.total` 判断翻页）
- `data.diff` 是数组，`data.total` 是总数（BK1216 = 508 只）
- **⚠️ pz 请求 >100 时服务端也只回 100 条**（2026-08-13 实测：pz=500 实际 diff 长度 100）——必须 pz=100 + 按 `len(已取) >= total` 翻页，不能按「单页 < pz 即止」判断
- 板块代码用东财 BK 前缀：BK1216 = 医药生物。其他板块代码从东财行情页 URL 或板块列表接口获取
- 需要 Referer: `https://quote.eastmoney.com/`

## 新浪实时快照

```
GET https://hq.sinajs.cn/list=sh600613,sz002219,bj920946
Referer: https://finance.sina.com.cn
```

- 返回 **GBK 编码**，每行 `var hq_str_<symbol>="<payload>";`
- payload 逗号分隔字段序：`0名称,1今开,2昨收,3现价,4最高,5最低,6买一价,7卖一价,8成交量(股),9成交额(元)`
- 涨幅 = (现价 - 昨收) / 昨收 × 100
- **代码→市场前缀**：6 开头 → `sh`；900 开头（沪 B）→ `sh`；200 开头（深 B）→ `sz`；43/83/87/92 开头（北交所）→ `bj`；其余 → `sz`
- **B 股（200/900 开头）新浪有行情，正常纳入**（2026-08-13 实测 900904/900917/900943/200028 四只医药 B 股全有行情）。曾误断言「B 股无行情」——真因是 9 开头被误映射成 bj 前缀。B 股涨跌幅规则与 A 股不同（10% 封顶），如需剔除由使用者显式过滤
- 无数据时返回 `var hq_str_sh600613="";`，靠空 payload 判断

## 指数行情（情绪判断用）

```
GET https://hq.sinajs.cn/list=sh000933,sz399989,sh000037,sz399394
Referer: https://finance.sina.com.cn
```

- `sh000933` = 中证医药卫生指数、`sz399989` = 中证医疗指数、`sh000037` = 上证医药指数、`sz399394` = 国证医药指数（2026-08-13 实测可用）。曾把 000933 误写成上证医药、399989 误写成国证医药——两组指数易混，引用时以代码为准
- 指数快照同样 GBK、同样字段序

## 已知不可得的公开数据（如实记录，勿再硬试）

- **申万一级行业指数（801150 医药生物）实时值**：公开接口不可得（2026-08-13 试过，未找到稳定公开端点）。用中证医药卫生/中证医疗指数作 L1 替代，并标注「申万指数不可得，用替代指数」
- **板块资金流**：东财资金流接口抓取失败（2026-08-13 实测）。报告中如实标注「资金流数据未能获取」，不编造

## 涨跌幅分桶分布（市场宽度统计）

全板块快照落盘后按涨跌幅分桶，作为市场宽度/情绪证据（表头与 2026-08-13 实战产物一致）：

| bucket | 口径 |
|---|---|
| `>5%` | pct >= 5 |
| `2-5%` | 2 <= pct < 5 |
| `0-2%` | 0 < pct < 2 |
| `0%` | pct == 0 |
| `-2-0%` | -2 <= pct < 0 |
| `<-2%` | pct < -2 |

加 `up`/`down`/`flat` 三行汇总（>0 / <0 / =0 家数）。CSV 表头：`bucket,count,total,pct_of_total`，六桶 count 加和必须等于 total，pct_of_total 以 total 为分母。

## 落盘产物规范（2026-08-13 实战基线）

`scripts/top_n_pipeline.py` 一次运行落盘四件套：

1. **universe**：`universe_{board}_{日期}.csv`，表头 `code,name,source,fetched_at`——成分股全量 + 数据来源 URL + 抓取时间，成分股清单的证据链
2. **top N**：`top{N}_{board}_{日期}.csv`，表头 `rank,code,name,pct_change,price,preclose,amount`
3. **all_quotes**：`all_quotes_{board}_{日期}.csv`，表头同 top N——全板块行情，涨跌家数比分桶统计的数据源
4. **distribution**：`distribution_{board}_{日期}.csv`，表头见上一节

## 数据链说明（Gangtise 原链 vs 新浪替代链）

2026-08-13 医药实战的原链是 Gangtise skill 的 quote.py 批量快照（前复权日K，落盘 raw_quote/quote_NN.csv）；本 skill 脚本的新浪链为公开源替代，创建当日实测跑通（508 只成分股全量、Top 10 落盘、四只 B 股覆盖）。两条链的涨跌幅口径可能不同（前复权日K vs 实时快照），报告中引用时必须说明用的是哪条链、哪个时点的数据。

## 本机网络坑：push2 域名被代理 TUN 劫持

若 `push2.eastmoney.com` 解析进 198.18.0.0/15 段（fake-IP，本机实测 198.18.0.128），说明被 Shadowrocket TUN 劫持，去代理环境变量无效，Python 请求会 RemoteDisconnected。接口本身正常，修法（按序试）：

1. 修本机代理分流规则（SOP 见 CLAUDE.md Shadowrocket 节），或
2. `curl --resolve "push2.eastmoney.com:443:<真实IP>"` 直连真实 IP 抓数据落盘。**真实 IP 会变，先 `dig +short push2.eastmoney.com` 查当前值再用**（2026-08-13 实测：上午 101.226.30.206 可用，当日下午已失效，公开 DNS 返回的新 IP 也可能空响应——先 curl 快验再批量抓）

## 盘中快照纪律

- 行情是瞬时值：stdout 打印快照时间戳，CSV 文件名带 `YYYYMMDD-HHMMSS`
- 报告引用任何行情数值必须带快照时间，并注明「盘中快照，数值会漂移」
- 收盘后重跑可得稳定值；盘中与收盘数据禁止混用比较
