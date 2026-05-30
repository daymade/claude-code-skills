"""SDK 没有的能力：用 bd._api 打 REST（逃生舱）
================================================

``bigdata_client`` 的 ``BigdataConnection`` 只 wrap 了 search / chunks /
KG / chat / watchlists / uploads。一整套 RavenPack 遗留的 ``/v1/*``
**结构化金融数据产品线** SDK 一个高层方法都没写。本模块用
``client.http.post(endpoint, json)`` 直打这些 endpoint，复用 SDK 的
JWT 认证 + 代理。

覆盖的 endpoint（概览）
----------------------
本模块用 ``client.http.post`` 直打 SDK 没封的 ``/v1/*`` 结构化金融数据：前瞻
（estimates / events-calendar / surprise / ratings / target）、财报三表 + TTM
指标比率、公司画像、行情、分红、分部营收、entity-sentiment、co-mention、
company-screener，加 reporting_period 回填（``cqs/query-chunks``，特殊、按 chunk
计费）。**完整方法清单 + 精确签名 + 验证等级（L3/L4）以
``references/verified_api_signatures.md`` 为单一权威**——此处只给覆盖范围,不复述
具体路径与等级（避免改一处漏同步,本周期就因这张复制表漏改过 ratings/target 的等级）。

关键修正（推翻早期 "Bigdata 中文/A股一刀切失效" 结论）
------------------------------------------------------
**必须拆成两个数据面分开讲：**

1. **结构化金融面**（本模块的 /v1/* 全家桶）——对大陆 A 股 + 港股 **可用**：
   - 茅台 ``914E1F`` events-calendar 返回前瞻日历、analyst-estimates 返回
     consensus、latest-surprise 返回 reporting_date + actual vs estimated
     （实测 A 股结构面数据有近月更新，非历史陈值）。
   - 经 rp_entity_id（英文名 or ISIN crosswalk 解析，见 kg.py）。
   - ⚠️ A 股结构数据有空洞：茅台 price-target 只返回 entity 无
     target_high/low/consensus（美股 AAPL 完整）。

2. **非结构化中文 NLP 面**（中文新闻实体检测 / 中文情绪）—— **确认死路**，
   SDK 和 REST 都救不了，数据源真没有。

路由 / 报错坑（避免后续踩）
--------------------------
- 业务面只对 ``POST + /query`` 注册；裸 ``GET /v1/<resource>`` 会 404。
- ``403 'Missing Authentication Token'`` = 该 auth path 上无此路由（不是
  权限拒绝）；``404`` = 路径不存在。
- analyst-estimates 的 ``period=quarter`` 实测 ``limit`` 上限约 20，
  ``limit=30`` 直接 400（报错信息极不友好，别误判为 endpoint 挂了）。
- company-screener 的 filter **必须嵌套在 ``"filters"`` 对象**里
  （market_cap_more_than / sector / industry / country / exchange / is_etf）；
  ``limit`` 在 top-level,≤1000。平铺 filter 不报错但被静默忽略、返回未过滤结果。

成本
----
这些 analyst/events/quota endpoint **不按 chunk 计费**（只 search 的
query-chunks 才 usage += chunks_count）。本模块默认 limit 极小，近乎零成本。
唯一例外：``fetch_reporting_period`` 走 ``cqs/query-chunks``，**按 chunk 计费**，
故默认 chunk_limit 很小。

只读说明
--------
本模块全部走只读查询（GET / POST query），无写入、无上传。
"""

from __future__ import annotations

from typing import Any, Optional

from .client import BigdataClient

__all__ = ["StructuredDataREST", "fields_values_to_records", "BatchSearch"]


def _entity_id_body(rp_entity_id: str | list[str], key: str = "rp_entity_id") -> dict:
    """统一构造 entity 维度 body（events-calendar 用 rp_entity_id 数组）。"""
    ids = rp_entity_id if isinstance(rp_entity_id, list) else [rp_entity_id]
    return {key: ids}


def _ident(rp_entity_id: str | list[str]) -> dict:
    """单标的 endpoint 的 identifier 形态（analyst / financials / market-data 系列共用）。

    OpenAPI spec + contract test 确认:这一大批 endpoint 用
    ``{"identifier": {"type": "rp_entity_id", "value": id}}``,
    与 events-calendar 的 ``{"rp_entity_id": [...]}`` 数组形态不同（各自固定）。
    """
    return {"identifier": {"type": "rp_entity_id", "value": rp_entity_id}}


def fields_values_to_records(result: Any) -> Any:
    """把 ``{fields: [...], values: [[...]]}`` 拼成 ``[{field: val}]`` 方便消费。

    财报（income/balance/cash-flow）、行情（daily-prices）、分红、分部营收
    等 endpoint 的 ``results`` 是 ``{fields, values}``（单实体）或其 list（多实体）。
    TTM / profile 系列已是扁平 ``[{...}]``,原样返回。
    """
    res = result.get("results", result) if isinstance(result, dict) else result

    def _one(d):
        if isinstance(d, dict) and d.get("fields") and d.get("values") is not None:
            return [dict(zip(d["fields"], row)) for row in d["values"]]
        return d

    if isinstance(res, dict):
        return _one(res)
    if isinstance(res, list):
        records = [_one(d) for d in res]
        # 单实体（最常见的单标的查询，如 daily_prices / dividends 的
        # ``results`` 是含一个实体的 list）直接 flatten 成记录列表,与
        # dict-results（income/balance 等）行为一致;多实体才返回每实体一组。
        return records[0] if len(records) == 1 else records
    return res


class StructuredDataREST:
    """SDK 缺失的结构化金融数据（全部走 bd._api.http REST 逃生舱）。

    所有方法返回 **原始 dict/list**（不做强 schema 解析）——因为这些是
    半文档化的 RavenPack 遗留 endpoint，schema 可能随后端变更。消费者按
    实际返回的 key 取值，并自行加 schema 防御。
    """

    def __init__(self, client: BigdataClient) -> None:
        self.client = client

    @property
    def http(self):
        return self.client.http

    # ------------------------------------------------------------------ #
    # 1) 前瞻财报/电话会日历（L4 实打）                                   #
    # ------------------------------------------------------------------ #
    def events_calendar(
        self,
        rp_entity_id: Optional[str | list[str]] = None,
        *,
        categories: Optional[list[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        countries: Optional[list[str]] = None,
        limit: int = 5,
        cursor: Optional[str] = None,
    ) -> Any:
        """前瞻财报/电话会日历。``POST v1/events-calendar/query``。

        两种用法：
        - **单/多标的**：传 ``rp_entity_id``（前瞻该标的财报日历）。
        - **全市场广扫**：不传 entity，传 ``countries=['US']`` + 日期窗，
          配合 ``cursor`` 分页扫全市场（回答"下周谁发财报"/冷启动筛选）。

        Parameters
        ----------
        categories:
            如 ``['earnings-call']`` / ``['conference-call']``。
        start_date, end_date:
            ``'YYYY-MM-DD'``。
        limit:
            ≤1000。默认 5（成本意识，且本 endpoint 不按 chunk 计费）。

        Returns
        -------
        dict
            ``{'results': ..., 'pagination': ...}``（实测顶层 key）。
            event 项含 category / event_datetime / title / fiscal_year /
            fiscal_period / updated_at 等（前瞻数据，event_datetime 为未来日期）。
        """
        body: dict[str, Any] = {}
        if rp_entity_id is not None:
            body.update(_entity_id_body(rp_entity_id))
        if categories is not None:
            body["categories"] = categories
        if start_date is not None:
            body["start_date"] = start_date
        if end_date is not None:
            body["end_date"] = end_date
        if countries is not None:
            body["countries"] = countries
        if cursor is not None:
            body["cursor"] = cursor
        body["limit"] = limit
        return self.http.post("v1/events-calendar/query", body)

    # ------------------------------------------------------------------ #
    # 2) 前瞻一致预期（L4 实打）                                          #
    # ------------------------------------------------------------------ #
    def analyst_estimates(
        self,
        rp_entity_id: str,
        *,
        period: str = "quarter",
        limit: int = 5,
    ) -> Any:
        """前瞻逐期一致预期。``POST v1/analyst-estimates/query``。

        返回 FISCAL_PERIOD_END_DATE + REVENUE/EBITDA/EBIT/NET_INCOME/SGA/EPS
        各 LOW/HIGH/AVG + NUM_ANALYSTS_REVENUE/EPS。实测美股可给到 ~2.5 年
        前瞻（Apple 到 2028Q3）。

        Parameters
        ----------
        period:
            ``'quarter'`` 或 ``'annual'``。
        limit:
            ⚠️ ``period=quarter`` 实测上限约 20，超出报 400。默认 5。

        Notes
        -----
        OpenAPI spec + contract test 确认 identifier 形态为
        ``{"type": "rp_entity_id", "value": id}``（analyst / financials /
        market-data 系列统一,与 events-calendar 的 ``rp_entity_id`` 数组不同,
        各自固定——不是"两种都试")。
        """
        body = {
            "identifier": {"type": "rp_entity_id", "value": rp_entity_id},
            "period": period,
            "limit": limit,
        }
        return self.http.post("v1/analyst-estimates/query", body)

    # ------------------------------------------------------------------ #
    # 3) 最近一期财报 surprise（L4 实打）                                 #
    # ------------------------------------------------------------------ #
    def latest_surprise(self, rp_entity_id: str) -> Any:
        """最近一期财报 surprise。``POST v1/latest-surprise/query``。

        返回 reporting_date + eps_actual/eps_estimated/eps_surprise_pct +
        revenue_actual/revenue_estimated/revenue_surprise_pct + last_updated。

        ⚠️ 名字是 "latest" —— 只返回最近一期（实测单条）。历史 surprise
        序列本方法拿不到（可能需翻 analyst-estimates 历史行自算）。
        """
        body = {"identifier": {"type": "rp_entity_id", "value": rp_entity_id}}
        return self.http.post("v1/latest-surprise/query", body)

    # ------------------------------------------------------------------ #
    # 4) 分析师评级一致（L3 文档证实，未运行时实打）                      #
    # ------------------------------------------------------------------ #
    def analyst_ratings(self, rp_entity_id: str) -> Any:
        """买卖评级一致。``POST v1/analyst-ratings/query``。

        文档：返回 strong_buy/buy/hold/sell/strong_sell + consensus。
        验证等级 L4（2026-05-31 实跑确认返回 ``{results}``，升自 L3）。
        identifier 形态同 analyst_estimates（spec 确认的 identifier 对象）。
        """
        body = {"identifier": {"type": "rp_entity_id", "value": rp_entity_id}}
        return self.http.post("v1/analyst-ratings/query", body)

    # ------------------------------------------------------------------ #
    # 5) 目标价 consensus（L3 文档证实）                                  #
    # ------------------------------------------------------------------ #
    def price_target(self, rp_entity_id: str) -> Any:
        """目标价一致预期。``POST v1/price/target/query``。

        文档：返回 target high/low/consensus/median + currency。
        ⚠️ A 股有空洞：部分 A 股只返回 entity 无 target 数值（美股如 AAPL
        则完整返回 target high/low/consensus 数值）。
        验证等级 L4（2026-05-31 实跑，升自 L3）。identifier 形态同 analyst_estimates（spec 确认的 identifier 对象）。
        """
        body = {"identifier": {"type": "rp_entity_id", "value": rp_entity_id}}
        return self.http.post("v1/price/target/query", body)

    # ------------------------------------------------------------------ #
    # 6) universe 构建：公司筛选器（L4 endpoint 可达）                    #
    # ------------------------------------------------------------------ #
    def company_screener(
        self,
        *,
        market_cap_more_than: Optional[float] = None,
        market_cap_lower_than: Optional[float] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        country: Optional[str] = None,
        exchange: Optional[str] = None,
        is_etf: Optional[bool] = None,
        limit: int = 10,
        **extra_filters: Any,
    ) -> Any:
        """股票池筛选器。``POST v1/company-screener/query``。

        ⚠️ filter **必须嵌套在 ``"filters"`` 对象**里
        （``{"filters": {...}, "limit": n}``）。平铺在 top-level **不报错但被后端
        静默忽略、返回未过滤结果**（实测裁决 2026-05-30,见 known_pitfalls #6）。
        ``limit`` 在 top-level,≤1000。

        ``extra_filters`` 透传其它 flat filter（如 ``beta_more_than`` 等，
        以文档为准）。
        """
        filters: dict[str, Any] = {}
        if market_cap_more_than is not None:
            filters["market_cap_more_than"] = market_cap_more_than
        if market_cap_lower_than is not None:
            filters["market_cap_lower_than"] = market_cap_lower_than
        if sector is not None:
            filters["sector"] = sector
        if industry is not None:
            filters["industry"] = industry
        if country is not None:
            filters["country"] = country
        if exchange is not None:
            filters["exchange"] = exchange
        if is_etf is not None:
            filters["is_etf"] = is_etf
        filters.update(extra_filters)
        # ⚠️ filter 必须嵌套在 "filters" 对象里；平铺 top-level 不报错但被后端
        # 静默忽略（返回未过滤结果）。实测裁决 2026-05-30,见 known_pitfalls #6。
        return self.http.post(
            "v1/company-screener/query", {"filters": filters, "limit": limit}
        )

    # ================================================================== #
    # 历史财务报表（三大表 + 分部营收，identifier + period + limit）       #
    # 不按 chunk 计费；contract-tested 2026-05-30；results 为             #
    # {fields, values}，用 fields_values_to_records() 拼成记录。         #
    # ================================================================== #
    def income_statement(self, rp_entity_id: str, *, period: str = "annual", limit: int = 5) -> Any:
        """历史利润表。``POST v1/income-statement/query``。

        ``results.fields`` 含 REVENUE / GROSS_PROFIT / OPERATING_INCOME /
        EBITDA / EBIT / NET_INCOME / R&D / SG&A 等。``period``: ``annual`` / ``quarter``。
        """
        body = _ident(rp_entity_id)
        body.update(period=period, limit=limit)
        return self.http.post("v1/income-statement/query", body)

    def balance_sheet(self, rp_entity_id: str, *, period: str = "annual", limit: int = 5) -> Any:
        """历史资产负债表。``POST v1/balance-sheet/query``。

        ``results.fields`` 含 TOTAL_ASSETS / TOTAL_LIABILITIES / TOTAL_DEBT /
        NET_DEBT / CASH_AND_CASH_EQUIVALENTS / TOTAL_STOCKHOLDERS_EQUITY 等。
        """
        body = _ident(rp_entity_id)
        body.update(period=period, limit=limit)
        return self.http.post("v1/balance-sheet/query", body)

    def cash_flow_statement(self, rp_entity_id: str, *, period: str = "annual", limit: int = 5) -> Any:
        """历史现金流量表。``POST v1/cash-flow-statement/query``。

        ``results.fields`` 含 OPERATING_CASH_FLOW / FREE_CASH_FLOW /
        CAPITAL_EXPENDITURE / NET_INCOME / STOCK_BASED_COMPENSATION 等。
        """
        body = _ident(rp_entity_id)
        body.update(period=period, limit=limit)
        return self.http.post("v1/cash-flow-statement/query", body)

    def revenue_geographic_segments(self, rp_entity_id: str, *, period: str = "annual", limit: int = 10) -> Any:
        """分地区营收。``POST v1/company-revenue-geographic-segments/query``。

        ``results.values`` 每行 ``[FISCAL_YEAR, PERIOD, CURRENCY, {地区: 营收}]``。
        """
        body = _ident(rp_entity_id)
        body.update(period=period, limit=limit)
        return self.http.post("v1/company-revenue-geographic-segments/query", body)

    def revenue_product_segments(self, rp_entity_id: str, *, period: str = "annual", limit: int = 10) -> Any:
        """分产品营收。``POST v1/company-revenue-product-segments/query``。

        ``results.values`` 每行 ``[FISCAL_YEAR, PERIOD, CURRENCY, {产品线: 营收}]``
        （如 NVDA 的 GPU / Tegra ...）。
        """
        body = _ident(rp_entity_id)
        body.update(period=period, limit=limit)
        return self.http.post("v1/company-revenue-product-segments/query", body)

    # ================================================================== #
    # TTM 指标 / 比率 / 公司画像（identifier；results 为扁平 [{...}]）    #
    # 不按 chunk 计费；contract-tested 2026-05-30。                       #
    # ================================================================== #
    def key_metrics_ttm(self, rp_entity_id: str) -> Any:
        """TTM 关键指标。``POST v1/key-metrics-ttm/query``。

        扁平字段含 enterprise_value_ttm / ev_to_ebitda_ttm /
        return_on_equity_ttm / return_on_invested_capital_ttm /
        free_cash_flow_yield_ttm / earnings_yield_ttm 等。
        """
        return self.http.post("v1/key-metrics-ttm/query", _ident(rp_entity_id))

    def company_ratios_ttm(self, rp_entity_id: str) -> Any:
        """TTM 财务比率。``POST v1/company-ratios-ttm/query``。

        扁平字段含 gross_profit_margin_ttm / net_profit_margin_ttm /
        price_to_earnings_ratio_ttm / price_to_book_ratio_ttm /
        debt_to_equity_ratio_ttm / dividend_yield_ttm 等。
        """
        return self.http.post("v1/company-ratios-ttm/query", _ident(rp_entity_id))

    def company_profile(self, rp_entity_id: str) -> Any:
        """公司画像。``POST v1/company-profile/query``。

        扁平字段含 company_name / ceo / sector / industry / website /
        description / full_time_employees / ipo_date / isin / cusip / exchange 等。
        """
        return self.http.post("v1/company-profile/query", _ident(rp_entity_id))

    # ================================================================== #
    # 市场数据（行情 / 分红，identifier + date_range）                    #
    # 不按 chunk 计费；contract-tested 2026-05-30；results 为 {fields, values}。#
    # ================================================================== #
    def daily_prices(self, rp_entity_id: str, *, start_date: str, end_date: str) -> Any:
        """日线 OHLC。``POST v1/price/daily/query``。

        ``results.fields`` = DATE / OPEN / LOW / HIGH / CLOSE / VOLUME /
        CHANGE / CHANGE_PERCENT / VWAP / CURRENCY。日期 ``YYYY-MM-DD``。
        """
        body = _ident(rp_entity_id)
        body["date_range"] = {"start": start_date, "end": end_date}
        return self.http.post("v1/price/daily/query", body)

    def dividends(self, rp_entity_id: str, *, start_date: str, end_date: str) -> Any:
        """分红历史。``POST v1/dividends/query``（注意:不是 ``v1/price/dividends``）。

        ``results.fields`` = DATE / DIVIDEND / ADJ_DIVIDEND / RECORD_DATE /
        PAYMENT_DATE / DECLARATION_DATE / YIELD / FREQUENCY。
        """
        body = _ident(rp_entity_id)
        body["date_range"] = {"start": start_date, "end": end_date}
        return self.http.post("v1/dividends/query", body)

    # ================================================================== #
    # 聚合情感时间序列（identifier + timestamp，不按 chunk 计费）          #
    # ================================================================== #
    def entity_sentiment(self, rp_entity_id: str, *, start_date: str, end_date: str) -> Any:
        """日频聚合情感时间序列。``POST v1/entity-sentiment/``（**尾斜杠，非 /query**）。

        ``results[].values`` 每点含 date / daily_sentiment（日均事件情感）/
        sentiment_pressure（异常情感强度）/ abnormal_media_attention（异常关注量）。
        **这是官方现成的日频情感序列——不必从 chunk 自聚合**。contract-tested 2026-05-30。
        """
        body = _ident(rp_entity_id)
        body["timestamp"] = {"start": start_date, "end": end_date}
        return self.http.post("v1/entity-sentiment/", body)

    # ================================================================== #
    # 实体共现关系图（⚠️ 走 search 系，**按 chunk 计费**！）              #
    # ================================================================== #
    def connected_entities(
        self,
        rp_entity_id: str,
        *,
        date_range: Optional[dict] = None,
        limit: int = 10,
    ) -> Any:
        """实体共现（co-mention）关系图。``POST v1/search/co-mentions/entities``。

        ``results`` 按类别（places / companies / organizations / people /
        products / concepts）分组,每个实体含 ``total_chunks_count`` /
        ``total_headlines_count``（按共现量排序）—— 用于建供应链 / 竞品 / 客户
        共现网络。**要某一类就直接读对应分组**（结果本就按类分好）。

        Parameters
        ----------
        date_range:
            可选,``{"start": "2024-01-01T00:00:00Z", "end": "2024-12-31T23:59:59Z"}``
            （ANSI date-time + UTC,**带时分秒,非 YYYY-MM-DD**）→ 透传到
            ``query.filters.timestamp``,看某时间窗内的共现（关系随时间演化）。

        ⚠️ **本方法按 chunk 计费**（响应含 ``usage.api_query_units``）,与
        financials / market-data 那批免费 endpoint 不同,默认 limit 小。

        Notes
        -----
        co-mentions/entities 的 body **没有 ``entity_categories`` 参数**（OpenAPI
        spec 确认；早期版本曾透传它做类别过滤,实测无效、已移除——按类别就直接读
        返回的分组）。``date_range`` 走 ``query.filters.timestamp``,contract-tested。
        """
        filters: dict[str, Any] = {"entity": {"any_of": [rp_entity_id]}}
        if date_range is not None:
            filters["timestamp"] = date_range
        body = {"query": {"filters": filters}, "limit": limit}
        return self.http.post("v1/search/co-mentions/entities", body)

    # ================================================================== #
    # 特殊:reporting_period 回填（SDK 砍字段，REST 有，**按 chunk 计费**！）#
    # ================================================================== #
    def fetch_reporting_period_raw(self, payload: dict) -> Any:
        """直打 ``cqs/query-chunks`` 拿原始 ``stories[].reportingPeriod``。

        **根因**：``reporting_period`` 在 REST wire 上存在且填充率约 75%
        （filings），但 SDK 的 ``ChunkedDocumentResponse`` 模型没有这个字段，
        pydantic 默认丢弃 → ``Document.reporting_period`` 永远 None。绕过
        SDK 模型、直读 raw JSON 的 ``reportingPeriod`` 才能回填。

        格式两类共存：绝对财年 ``'2026FY'`` + 相对财季 ``'FQ1'-'FQ4'``。
        ⚠️ ``'FQ1'`` 无年份锚点，需结合同 story 的 ``'YYYYFY'`` 或 timestamp
        二次推断，直接当结构化季度键有歧义。

        ⚠️ **本方法按 chunk 计费**（走 query-chunks）。``payload`` 请自行
        控制 chunk 规模。payload 即 ``POST cqs/query-chunks`` 的 body
        （可先 monkeypatch ``http.post`` 抓 SDK 真实 payload 拿 schema，
        见 examples）。

        Returns
        -------
        dict
            原始 query-chunks 响应；``stories[].reportingPeriod`` /
            ``reportingEntities`` / ``documentType`` 为 camelCase wire 字段。
        """
        return self.http.post("cqs/query-chunks", payload)


class BatchSearch:
    """Batch search 异步流程（chunk 计费，但比 fast 便宜 **50%**）。

    适合一次性打包大量 search query（如给单标的做多主题 × 多时间窗的海量
    证据流回填）—— N 个 search 打成一个 batch，单价从 ``$0.015`` 降到
    ``$0.0075`` / query_unit。

    流程（2026-05-31 contract-tested：``create_job`` / ``upload_input`` /
    ``get_status`` 轮询 = **L4 实跑**（含 upload 的 Content-Type 403 bug 修复，
    实测状态流转 pending→processing）；``download_results`` 是标准 S3 GET，因
    smart batch 处理 >10min 未跑到 completed 而**未端到端验**——用时若异常照本
    docstring 自查）::

        bs = BatchSearch(client)
        job = bs.create_job()                              # {batch_id, presigned_url}
        jsonl = bs.build_input_jsonl([{...search1...}, {...search2...}])
        bs.upload_input(job["presigned_url"], jsonl)       # PUT 到 S3 presigned
        st = bs.get_status(job["batch_id"])                # poll 到 completed
        rows = bs.download_results(st["output_file_url"])

    每行 jsonl = 一个 ``POST v1/search`` 的 body（``search_mode`` fast/smart +
    query/filters）。轮询 ``status`` 到 ``completed``（``output_file_url`` 可用）
    或 ``failed``。
    """

    def __init__(self, client: BigdataClient) -> None:
        self.client = client

    @property
    def http(self):
        return self.client.http

    def create_job(self) -> dict:
        """创建 batch job。``POST v1/search/batches``（无需 body）。

        返回 ``{batch_id, presigned_url}`` —— 把 .jsonl 输入 PUT 到 presigned_url。
        """
        return self.http.post("v1/search/batches", {})

    def get_status(self, batch_id: str) -> dict:
        """查 batch 状态。``GET v1/search/batches/{batch_id}``。

        返回 ``{batch_id, status, output_file_url}``。轮询直到 ``status`` 为
        ``completed``（此时 ``output_file_url`` 可用）或 ``failed``。
        """
        return self.http.get(f"v1/search/batches/{batch_id}")

    @staticmethod
    def build_input_jsonl(search_requests: list[dict]) -> str:
        """把 search request dict 列表拼成 .jsonl 文本（每行一个 ``v1/search`` body）。"""
        import json as _json

        return "\n".join(_json.dumps(r, ensure_ascii=False) for r in search_requests)

    @staticmethod
    def upload_input(presigned_url: str, jsonl_text: str) -> int:
        """PUT .jsonl 到 ``create_job`` 返回的 presigned_url（S3，非 Bigdata API）。

        ⚠️ **Content-Type 必须匹配 presigned 签名**：URL query 的 ``content-type``
        参数（实测后端签的是 ``application/jsonl``）正是 S3 计算签名用的值，PUT
        必须带完全相同的 Content-Type，否则 ``403 SignatureDoesNotMatch``。这里从
        URL query 解析出来用上，不写死（后端若换 type 也跟得上）。contract-tested
        2026-05-31。
        ⚠️ 走裸 ``requests``（presigned 是 S3 直连签名 URL，不经 Bigdata 认证层）；
        ``requests`` 读 ``HTTPS_PROXY`` 走代理，代理对 S3 大 host 偶发 ``503 Tunnel``，
        故内置瞬时重试（``rc()`` 的 marker 大小写匹配不到 ``ProxyError``，单独处理）。
        """
        import time
        import urllib.parse

        import requests

        qs = urllib.parse.parse_qs(urllib.parse.urlparse(presigned_url).query)
        content_type = qs.get("content-type", ["application/jsonl"])[0]
        last_exc: Optional[Exception] = None
        for _ in range(5):
            try:
                resp = requests.put(
                    presigned_url,
                    data=jsonl_text.encode("utf-8"),
                    headers={"Content-Type": content_type},
                    timeout=120,
                )
                resp.raise_for_status()
                return resp.status_code
            except requests.exceptions.ProxyError as exc:
                last_exc = exc  # 代理对 S3 偶发 503 Tunnel，退避重试
                time.sleep(2)
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def download_results(output_file_url: str) -> list[dict]:
        """GET ``output_file_url``（status=completed 时）下载 .jsonl 结果，解析成 dict 列表。"""
        import json as _json

        import requests

        resp = requests.get(output_file_url, timeout=120)
        resp.raise_for_status()
        return [_json.loads(line) for line in resp.text.splitlines() if line.strip()]
