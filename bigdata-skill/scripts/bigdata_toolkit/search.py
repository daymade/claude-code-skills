"""带标注的 chunk 抽取（SDK 高层路径）
=====================================

封装 ``bd.search`` 的语义检索，把每个返回 chunk 的 **sentiment + 实体
span + 定位** 拍平成普通 dict，方便下游消费。

走 SDK 高层（``bd.search.new(...).run(...)``），不是 REST 逃生舱。

⚠️ 中文/A股注意
----------------
实测：中文新闻实体检测 ≈0，CJK chunk 的 sentiment 是 doc-level 继承值
（chunk sentiment == doc sentiment），且 ``language`` 字段会把含中文的
filing 误标成 English。**这是数据源层硬伤，不是 SDK 封装问题**——
A 股标的请先用英文官方名 / ISIN 解析成 rp_entity_id（见 kg.py），再做
entity-scoped 检索；纯中文 keyword 检索基本 0 命中。结构化金融面
（前瞻日历 / 一致预期 / surprise）走 rest_ext.py，对 A 股可用。

字段来源（运行时确认的 SDK model）
-----------------------------------
- ``Document``: id, headline, sentiment, document_scope, source, timestamp,
  chunks, language, cluster, reporting_period, document_type,
  reporting_entities, url
  （注意 ``reporting_period`` 字段存在但 SDK 反序列化时不填，永远 None —
  要拿真值走 rest_ext.fetch_reporting_period）
- ``DocumentChunk``: text, chunk, entities, sentences, relevance, sentiment,
  section_metadata, speaker
- ``DocumentSentenceEntity``: key（rp_entity_id）, start, end（字符 span 位置）,
  query_type

成本铁律（详见 cost.py）
------------------------
``Search.run(limit)`` 接受 ``int``（doc-limit）或 ``ChunkLimit(n)``。
**doc-limit 不省钱**：run(1) 和 run(10) 成本几乎一样（~52 query_unit），
因为后端按"每页返回的 chunk 数"计费。真正省钱的是 ``ChunkLimit(n)``
（实测 ChunkLimit(10) 仅 1 query_unit，52x 差距）。所以本模块默认走
ChunkLimit，强制成本意识。
"""

from __future__ import annotations

from typing import Any, Optional, Union

from bigdata_client.daterange import AbsoluteDateRange, RollingDateRange
from bigdata_client.query import Entity, Keyword
from bigdata_client.search import ChunkLimit
from bigdata_client.models.search import DocumentType, SortBy

from .client import BigdataClient

__all__ = [
    "AnnotatedSearcher",
    "chunk_to_dict",
    "document_to_dict",
]


def _entity_to_dict(ent: Any) -> dict:
    """``DocumentSentenceEntity`` → dict（key + 字符 span + query_type）。"""
    return {
        "key": getattr(ent, "key", None),          # rp_entity_id
        "start": getattr(ent, "start", None),       # 字符起始位置
        "end": getattr(ent, "end", None),           # 字符结束位置
        "query_type": getattr(ent, "query_type", None),
    }


def chunk_to_dict(chunk: Any) -> dict:
    """``DocumentChunk`` → 拍平 dict，保留标注。

    每个 entity 的 ``(start, end)`` 是该 chunk ``text`` 内的字符 span，可用
    ``text[start:end]`` 取出被标注的实体表面词。
    """
    entities = [_entity_to_dict(e) for e in (getattr(chunk, "entities", None) or [])]
    return {
        "chunk_index": getattr(chunk, "chunk", None),
        "text": getattr(chunk, "text", None),
        "sentiment": getattr(chunk, "sentiment", None),
        "relevance": getattr(chunk, "relevance", None),
        "speaker": getattr(chunk, "speaker", None),
        "section_metadata": getattr(chunk, "section_metadata", None),
        "entities": entities,
    }


def document_to_dict(doc: Any, *, with_chunks: bool = True) -> dict:
    """``Document`` → 拍平 dict。

    ``source`` 是 ``DocumentSource``（key/name/rank），这里展开成可读字段。
    ``reporting_period`` 大概率是 None（SDK 解析 bug，见模块 docstring）。
    """
    source = getattr(doc, "source", None)
    out = {
        "id": getattr(doc, "id", None),
        "headline": getattr(doc, "headline", None),
        "sentiment": getattr(doc, "sentiment", None),
        "document_scope": getattr(doc, "document_scope", None),
        "document_type": getattr(doc, "document_type", None),
        "timestamp": getattr(doc, "timestamp", None),
        "language": getattr(doc, "language", None),
        "url": getattr(doc, "url", None),
        "reporting_period": getattr(doc, "reporting_period", None),  # 多半 None
        "reporting_entities": getattr(doc, "reporting_entities", None),
        "source_key": getattr(source, "key", None) if source else None,
        "source_name": getattr(source, "name", None) if source else None,
        "source_rank": getattr(source, "rank", None) if source else None,
    }
    if with_chunks:
        out["chunks"] = [chunk_to_dict(c) for c in (getattr(doc, "chunks", None) or [])]
    return out


class AnnotatedSearcher:
    """语义检索 + 标注抽取（SDK 高层）。

    Parameters
    ----------
    client:
        :class:`~bigdata_toolkit.client.BigdataClient` 实例。
    """

    def __init__(self, client: BigdataClient) -> None:
        self.client = client

    # ------------------------------------------------------------------ #
    # 查询构造辅助                                                        #
    # ------------------------------------------------------------------ #
    @staticmethod
    def entity_query(rp_entity_id: str, keyword: Optional[str] = None):
        """构造 "实体（+ 可选关键词）" 查询。

        entity-scoped 检索是 A 股唯一可用路径（纯 keyword 中文检索 ≈0）。
        rp_entity_id 由 kg.py 的实体解析得到。
        """
        ent = Entity(rp_entity_id)
        if keyword:
            # 用 `&` 运算符组合（SDK 重载的 __and__）；不要用 All(a, b)——
            # All 只接受单个 iterable，传两个位置参数会 TypeError。
            return ent & Keyword(keyword)
        return ent

    # ------------------------------------------------------------------ #
    # 检索执行                                                            #
    # ------------------------------------------------------------------ #
    def search(
        self,
        query,
        *,
        chunk_limit: int = 10,
        date_range: Optional[Union[AbsoluteDateRange, RollingDateRange]] = None,
        scope: DocumentType = DocumentType.ALL,
        sortby: SortBy = SortBy.RELEVANCE,
        rerank_threshold: Optional[float] = None,
        as_dict: bool = True,
    ):
        """跑一次检索，返回 Document 列表（默认拍平成 dict）。

        Parameters
        ----------
        query:
            ``bigdata_client.query`` 的 QueryComponent（用 ``entity_query``
            或自己拼 ``Entity`` / ``Keyword`` / ``All`` / ``Any``）。
        chunk_limit:
            **chunk 上限**（成本承重参数）。内部包成 ``ChunkLimit(n)``，
            即 n 个 chunk = n/10 query_unit。默认 10（≈1 qu）。
            **绝不**直接传整数 doc-limit（会 52x 超支，见模块 docstring）。
        date_range:
            ``AbsoluteDateRange(start, end)`` 或 ``RollingDateRange.*``。
            窗口越窄越省钱（同 limit 下 1 天窗 vs 周窗 ~2.6x 差距）。
        scope:
            ``DocumentType.ALL / NEWS / FILINGS / TRANSCRIPTS`` 等。
        as_dict:
            True 返回拍平 dict（含标注）；False 返回原始 Document 对象。

        Returns
        -------
        list[dict] | list[Document]
        """
        search = self.client.bd.search.new(
            query=query,
            date_range=date_range,
            scope=scope,
            sortby=sortby,
            rerank_threshold=rerank_threshold,
        )
        # 关键：用 ChunkLimit 而非裸 int，强制 chunk 计费而非整页计费
        docs = search.run(ChunkLimit(chunk_limit))

        if as_dict:
            return [document_to_dict(d) for d in docs]
        return docs

    def search_entity(
        self,
        rp_entity_id: str,
        *,
        keyword: Optional[str] = None,
        chunk_limit: int = 10,
        **kwargs,
    ):
        """便捷方法：按 rp_entity_id（+ 可选关键词）检索。"""
        query = self.entity_query(rp_entity_id, keyword)
        return self.search(query, chunk_limit=chunk_limit, **kwargs)

    # ------------------------------------------------------------------ #
    # 标注字典下载（SDK 封装方法，按 id 拉完整标注）                      #
    # ------------------------------------------------------------------ #
    def download_annotated_dict(self, search_id: str) -> dict:
        """对已保存的 search 拉完整标注字典。

        走 SDK 封装方法 ``bd._api.download_annotated_dict(id_)``（不是 raw
        http）。返回完整的 chunk-level 标注。适合先 save 一个 search 再批量
        回拉标注的场景。
        """
        return self.client.conn.download_annotated_dict(search_id)
