"""bigdata_toolkit —— Bigdata.com 可复用工具库
================================================

一个 class 两种能力：SDK 高层封装 + ``bd._api`` REST 逃生舱直通。

基于对 ``bigdata-client`` SDK 的运行时实测（L4）构建，**不编 API**。
每个能力都标注走 SDK 还是走 REST 逃生舱，见各子模块 docstring。

快速开始
--------
>>> import os
>>> os.environ["BIGDATA_API_KEY"] = "bd_v2_xxx"        # doctest: +SKIP
>>> os.environ["HTTPS_PROXY"] = "http://127.0.0.1:8080"  # 仅在需要出站代理时  # doctest: +SKIP
>>> from bigdata_toolkit import BigdataClient, EntityResolver, StructuredDataREST
>>> client = BigdataClient()                            # doctest: +SKIP
>>> # 1) 实体解析（A 股用英文名/ISIN）
>>> resolver = EntityResolver(client)                   # doctest: +SKIP
>>> aapl = resolver.resolve_id("Apple")                 # doctest: +SKIP -> 'D8442A'
>>> # 2) SDK 没有的前瞻日历（走 REST 逃生舱）
>>> rest = StructuredDataREST(client)                   # doctest: +SKIP
>>> cal = rest.events_calendar(aapl, categories=["earnings-call"],
...                            start_date="2026-06-01", end_date="2026-12-31")  # doctest: +SKIP

模块速查
--------
- :mod:`~bigdata_toolkit.client`   —— 统一入口（SDK + REST 逃生舱）
- :mod:`~bigdata_toolkit.search`   —— 带标注 chunk 抽取（SDK）
- :mod:`~bigdata_toolkit.kg`       —— 实体解析 + ISIN crosswalk（SDK）
- :mod:`~bigdata_toolkit.rest_ext` —— SDK 缺失的结构化金融数据（REST 逃生舱）
- :mod:`~bigdata_toolkit.cost`     —— chunk 消耗追踪 + 配额意识
"""

from .client import BigdataClient, require_env
from .cost import (
    CHUNKS_PER_QUERY_UNIT,
    USD_PER_QUERY_UNIT,
    CostModel,
    CostTracker,
)
from .kg import EntityResolver, company_to_dict
from .rest_ext import BatchSearch, StructuredDataREST, fields_values_to_records
from .retry import RETRYABLE_MARKERS, rc, with_retry
from .search import (
    AnnotatedSearcher,
    chunk_to_dict,
    document_to_dict,
)

__version__ = "0.1.0"

__all__ = [
    # client
    "BigdataClient",
    "require_env",
    # search
    "AnnotatedSearcher",
    "chunk_to_dict",
    "document_to_dict",
    # kg
    "EntityResolver",
    "company_to_dict",
    # rest_ext
    "StructuredDataREST",
    "BatchSearch",
    "fields_values_to_records",
    # cost
    "CostTracker",
    "CostModel",
    "CHUNKS_PER_QUERY_UNIT",
    "USD_PER_QUERY_UNIT",
    # retry
    "rc",
    "with_retry",
    "RETRYABLE_MARKERS",
]
