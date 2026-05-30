"""chunk 消耗追踪 + 配额意识（成本承重模块）
=============================================

Bigdata 按 **chunk** 计费。这个模块把计量单位、单价、配额查询、消耗
delta 追踪、冷启动成本外推全部固化下来，让任何批量任务都带成本意识。

计量单位（运行时三处独立佐证坐实）
----------------------------------
- ``1 query_unit = 10 chunks``（精确，SDK 把 raw chunk 数 ÷10 包装）。
  - ``search.py:166``: ``usage += query_chunks_response.chunks_count``（raw chunk 数）
  - ``search.py:157``: ``get_usage()`` return ``usage / 10``
  - ``subscription.py:40``: ``query_unit_used = contextual_units_read / 10``
- REST raw 计数器：``get_my_quota().organization_consumed.contextual_units_read``
  是 chunk 数（不是 query_unit）。

单价（来自 docs.bigdata.com 公开 pricing，均为 list price）
--------------------------------------------------------------------------
- Fast Search:   $0.015 / query_unit
- Smart Search:  $0.03  / query_unit
- Batch Search (async): $0.0075 / query_unit（50% 折扣）

成本铁律（NO FALLBACK 类风险）
------------------------------
``Search.run(limit)`` 的 ``limit`` 是 ``int`` 时走 **doc-limit**，按"每页
返回的 chunk 数"计费；``ChunkLimit(n)`` 才按 chunk 计费。我们实测曾见
run(1) ≈ run(10) ≈ ~52 query_unit 的差距——**但这是单点实测,官方计费文档
未印证此倍数**,当方向性参考即可（倍数随标的/窗口浮动）。规则本身成立:
``max_chunks`` 是官方计费单位,务必走 ``ChunkLimit`` 而非裸 int。

> 一个默认参数就能静默烧光配额。冷启动脚本必须 code-review 保证零裸
> ``run(int)``，全部走 ``ChunkLimit``。

trial 配额现实
--------------
一个典型的 1 周 full-content trial ≈ 67000 query_unit = 670000 chunks
≈ $1005（list price 名义值，以你账号实际 quota 为准）。机构级 universe
（100-200 标的）做一次多年回溯 backfill 即接近或超过整个 trial 配额
（3 年季度 100 标的 = 89.6%；200 标的 = 180%）。**trial 只够 PoC 级
抽样（≤20 标的单快照）**，全量上线需要更大的付费配额。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .client import BigdataClient

__all__ = ["CostTracker", "CostModel", "CHUNKS_PER_QUERY_UNIT", "USD_PER_QUERY_UNIT"]

#: 计量换算常量（运行时坐实）
CHUNKS_PER_QUERY_UNIT = 10

#: 单价表（USD / query_unit，public list price）
USD_PER_QUERY_UNIT = {
    "fast": 0.015,
    "smart": 0.03,
    "batch": 0.0075,
}


@dataclass
class CostModel:
    """成本外推模型（纯计算，无 IO）。

    用于冷启动 backfill 前估算配额消耗，**禁止用代码行数等无关指标**，
    只按 chunk 真实计费口径算。
    """

    chunk_limit_per_query: int = 500
    """每次 search 的 chunk 上限（必须配合 ChunkLimit 使用，否则估算无效）。"""

    tier: str = "fast"
    """计费档：fast / smart / batch。"""

    trial_query_units: int = 67000
    """trial 配额基数（query_unit），用于 ``pct_of_trial_quota`` 估算。默认
    67000 = 典型 1 周 full-content trial ≈ $1005 list。换成你账号的实际额度
    （看 ``CostTracker.quota()`` 的 max_query_units）即可让百分比准确。"""

    def query_units_per_query(self) -> float:
        """单次查询消耗的 query_unit = chunk_limit / 10。"""
        return self.chunk_limit_per_query / CHUNKS_PER_QUERY_UNIT

    def estimate(
        self,
        n_entities: int,
        n_windows: int = 1,
    ) -> dict:
        """估算一次冷启动 backfill 的总成本。

        Parameters
        ----------
        n_entities:
            标的数量。
        n_windows:
            时间窗数量（如 3 年 × 季度 = 12 个窗）。

        Returns
        -------
        dict
            total_query_units / total_chunks / usd / pct_of_trial_quota。
        """
        qu_per_query = self.query_units_per_query()
        total_queries = n_entities * n_windows
        total_qu = qu_per_query * total_queries
        unit_price = USD_PER_QUERY_UNIT.get(self.tier, USD_PER_QUERY_UNIT["fast"])
        return {
            "n_entities": n_entities,
            "n_windows": n_windows,
            "chunk_limit_per_query": self.chunk_limit_per_query,
            "query_units_per_query": qu_per_query,
            "total_queries": total_queries,
            "total_query_units": total_qu,
            "total_chunks": total_qu * CHUNKS_PER_QUERY_UNIT,
            "tier": self.tier,
            "usd": round(total_qu * unit_price, 2),
            "pct_of_trial_quota": round(total_qu / self.trial_query_units * 100, 1),
        }


@dataclass
class CostTracker:
    """实时配额追踪 + 消耗 delta 计量（带 IO，查真实配额）。

    用法：操作前 ``snapshot()`` 记起点，操作后 ``delta()`` 看实际烧了多少
    chunk —— 用真实用量校准 :class:`CostModel` 的外推（替代纯估算）。
    """

    client: BigdataClient
    _baseline_chunks: Optional[int] = field(default=None, init=False)

    # ------------------------------------------------------------------ #
    # 配额查询                                                            #
    # ------------------------------------------------------------------ #
    def quota(self) -> dict:
        """当前 chunk 级配额（走 SDK ``get_my_quota`` 封装）。

        Returns
        -------
        dict
            max_chunks / used_chunks / remaining_chunks / used_query_units /
            remaining_query_units / pct_used。
        """
        raw = self.client.get_quota_raw()
        max_chunks = raw["organization_quota"]["contextual_units_max_read"]
        used_chunks = raw["organization_consumed"]["contextual_units_read"]
        remaining = max_chunks - used_chunks
        return {
            "max_chunks": max_chunks,
            "used_chunks": used_chunks,
            "remaining_chunks": remaining,
            "used_query_units": round(used_chunks / CHUNKS_PER_QUERY_UNIT, 1),
            "remaining_query_units": round(remaining / CHUNKS_PER_QUERY_UNIT, 1),
            "max_query_units": round(max_chunks / CHUNKS_PER_QUERY_UNIT, 1),
            "pct_used": round(used_chunks / max_chunks * 100, 2) if max_chunks else None,
        }

    def quota_detailed_raw(self) -> Any:
        """实时细分配额（REST ``v1/subscription/quotas``，免费旁路）。

        含 billing 周期 + units 细分。可在冷启动中途轮询此 endpoint 实测
        chunk→credit 换算率做校准。**这个 endpoint SDK 没有高层方法**。
        """
        return self.client.get_quotas_v1()

    # ------------------------------------------------------------------ #
    # 消耗 delta 追踪                                                     #
    # ------------------------------------------------------------------ #
    def snapshot(self) -> int:
        """记录当前已用 chunk 数为基线，返回该值。"""
        self._baseline_chunks = self.quota()["used_chunks"]
        return self._baseline_chunks

    def delta(self) -> dict:
        """相对上次 ``snapshot()`` 的消耗 delta（chunk + query_unit + USD 估算）。

        必须先调 ``snapshot()``，否则抛错（不猜基线，NO FALLBACK）。
        """
        if self._baseline_chunks is None:
            raise RuntimeError("call snapshot() before delta()")
        now_chunks = self.quota()["used_chunks"]
        delta_chunks = now_chunks - self._baseline_chunks
        delta_qu = delta_chunks / CHUNKS_PER_QUERY_UNIT
        return {
            "delta_chunks": delta_chunks,
            "delta_query_units": round(delta_qu, 2),
            "usd_fast": round(delta_qu * USD_PER_QUERY_UNIT["fast"], 4),
            "usd_smart": round(delta_qu * USD_PER_QUERY_UNIT["smart"], 4),
            "baseline_chunks": self._baseline_chunks,
            "now_chunks": now_chunks,
        }
