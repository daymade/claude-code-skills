"""实体解析 + crosswalk（SDK 高层路径）
=======================================

封装 ``bd.knowledge_graph``，把"公司名 / ISIN / 交易所代码"解析成
**rp_entity_id**（6 位字母数字，如 Apple = ``D8442A``、贵州茅台 =
``914E1F``）。

为什么这是 gateway
------------------
Bigdata 几乎所有能力都以 rp_entity_id 为主键：
- search 的 ``Entity(id)``（见 search.py）
- rest_ext 的 events-calendar / analyst-estimates / surprise（见 rest_ext.py）

**A 股标的的唯一可用解析路径**（实测）：
- 中文名直查 ``find_companies('贵州茅台')`` → **0 命中**（数据源中文实体层空）
- 英文官方名 ``find_companies('Kweichow Moutai')`` → 命中 ``914E1F``
- ISIN crosswalk ``get_companies_by_isin(['CNE0000018R8'])`` → ``914E1F``

所以 A 股请用 **英文官方名** 或 **ISIN** 解析，不要用中文名。

方法签名（运行时确认）
----------------------
- ``kg.find_companies(values, /, type=None, country=None, limit=20)``
- ``kg.find_topics(values, /, limit=20)``
- ``kg.find_sources(values, /, limit=20, country=None, rank=None, retention=None)``
- ``kg.get_companies_by_isin(isins: list[str]) -> list[Company | None]``
- ``kg.get_companies_by_cusip / _by_sedol / _by_listing``
- ``kg.get_entities(ids: list[str], /)`` —— **同时解 COMP 实体 + TOPC 话题**
  （不是 ENTITY-only）
- ``kg.find_topics`` —— 中文话题（如 '人工智能'）实测 0 命中，TOPIC 解析
  同样卡在中文层

注意
----
``kg.autosuggest`` 在 API-key 模式下 ``NotImplementedError``（与 uploads
同族），交互式补全用不了；实体解析只能走 ``find_*`` 系列。
"""

from __future__ import annotations

from typing import Any, Optional

from .client import BigdataClient

__all__ = ["EntityResolver", "company_to_dict"]


def company_to_dict(company: Any) -> dict:
    """``Company`` 实体 → 精简 dict（id + 名称 + 国家 + ticker）。

    字段名做防御性提取（不同 SDK 版本属性名可能微调）。
    """
    if company is None:
        return {}
    return {
        "id": getattr(company, "id", None),               # rp_entity_id
        "name": getattr(company, "name", None),
        "ticker": getattr(company, "ticker", None),
        "country": getattr(company, "country", None),
        "sector": getattr(company, "sector", None),
        "industry": getattr(company, "industry", None),
        "isin": getattr(company, "isin", None),
        "entity_type": getattr(company, "entity_type", None),
    }


class EntityResolver:
    """公司 / 话题实体解析（SDK 高层）。"""

    def __init__(self, client: BigdataClient) -> None:
        self.client = client

    @property
    def kg(self):
        return self.client.bd.knowledge_graph

    # ------------------------------------------------------------------ #
    # 公司解析                                                            #
    # ------------------------------------------------------------------ #
    def find_companies(
        self,
        name: str,
        *,
        country: Optional[str] = None,
        limit: int = 5,
        as_dict: bool = True,
    ):
        """按名称解析公司。

        ⚠️ A 股请用 **英文官方名**（'Kweichow Moutai' 而非 '贵州茅台'）。
        ``country`` 用 ISO-2（'CN' / 'US' / 'HK'）。
        """
        result = self.kg.find_companies(name, country=country, limit=limit)
        # find_companies 单值返回 list；多值返回 dict[str, list]
        companies = result if isinstance(result, list) else result.get(name, [])
        if as_dict:
            return [company_to_dict(c) for c in companies]
        return companies

    def resolve_id(
        self,
        name: str,
        *,
        country: Optional[str] = None,
    ) -> Optional[str]:
        """解析公司名 → 单个 rp_entity_id（取第一个命中）。

        命中 0 个返回 None（**不猜、不 fallback**，NO FALLBACK 原则）。
        A 股中文名大概率返回 None —— 改用英文名或 ``resolve_by_isin``。
        """
        companies = self.find_companies(name, country=country, limit=1, as_dict=True)
        if not companies:
            return None
        return companies[0].get("id")

    # ------------------------------------------------------------------ #
    # crosswalk：ISIN / CUSIP / SEDOL / 交易所代码 → rp_entity_id         #
    # ------------------------------------------------------------------ #
    def resolve_by_isin(self, isins: list[str], *, as_dict: bool = True):
        """ISIN crosswalk（A 股最可靠路径，如 茅台 CNE0000018R8 → 914E1F）。

        返回与输入等长的 list（未命中位置为 None / {}）。
        """
        companies = self.kg.get_companies_by_isin(isins)
        if as_dict:
            return [company_to_dict(c) for c in companies]
        return companies

    def resolve_by_cusip(self, cusips: list[str], *, as_dict: bool = True):
        """CUSIP crosswalk（美股）。"""
        companies = self.kg.get_companies_by_cusip(cusips)
        return [company_to_dict(c) for c in companies] if as_dict else companies

    def resolve_by_sedol(self, sedols: list[str], *, as_dict: bool = True):
        """SEDOL crosswalk。"""
        companies = self.kg.get_companies_by_sedol(sedols)
        return [company_to_dict(c) for c in companies] if as_dict else companies

    # ------------------------------------------------------------------ #
    # 话题 / 通用实体解析                                                 #
    # ------------------------------------------------------------------ #
    def find_topics(self, values, *, limit: int = 5, as_dict: bool = False):
        """解析话题（TOPC）。⚠️ 中文话题实测 0 命中。"""
        result = self.kg.find_topics(values, limit=limit)
        return result

    def get_entities(self, ids: list[str]):
        """按 id 批量解实体。**同时解 COMP（公司）+ TOPC（话题）**，非 ENTITY-only。

        实测：传 dotted topic id 返回 ``Topic(...)``，传 rp_entity_id 返回
        ``Company(...)``。
        """
        return self.kg.get_entities(ids)
