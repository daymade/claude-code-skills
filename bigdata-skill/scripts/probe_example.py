"""bigdata_toolkit 可跑示例
============================

演示五大能力，全部小样本（成本意识），并用 CostTracker 量化每段消耗。

运行
----
::

    export BIGDATA_API_KEY=bd_v2_xxx            # 你的 Bigdata API key
    export HTTPS_PROXY=http://127.0.0.1:8080    # 仅在需要出站代理时
    # 用装好 bigdata-client 的 Python 环境跑（见 SKILL.md 装包步骤）：
    python scripts/probe_example.py            # 加 --with-search 额外测 chunk 检索

设计原则
--------
- 实体解析 / events / estimates / quota 这些 endpoint **不按 chunk 计费**，
  近乎零成本，所以默认演示它们。
- search（query-chunks）**按 chunk 计费**，示例用 ``chunk_limit=10``（≈1 qu），
  并用 ``--with-search`` 显式开启，避免误烧配额。
"""

from __future__ import annotations

import argparse
import json
import sys

from bigdata_toolkit import (
    AnnotatedSearcher,
    BigdataClient,
    CostModel,
    CostTracker,
    EntityResolver,
    StructuredDataREST,
    rc,
)


def _show(title: str, obj, max_chars: int = 600) -> None:
    print(f"\n{'='*60}\n{title}\n{'='*60}")
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except TypeError:
        s = str(obj)
    print(s[:max_chars] + (" ..." if len(s) > max_chars else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="bigdata_toolkit probe example")
    ap.add_argument(
        "--with-search",
        action="store_true",
        help="额外跑一次 search（按 chunk 计费，~1 query_unit）",
    )
    args = ap.parse_args()

    # ---- 0. 统一客户端（key 从 env 读，绝不硬编码） ----
    client = BigdataClient()  # 缺 BIGDATA_API_KEY 会 fail-fast
    tracker = CostTracker(client)
    resolver = EntityResolver(client)
    rest = StructuredDataREST(client)

    quota0 = rc(lambda: tracker.quota())
    _show("[0] 起始配额（chunk 级，1 qu = 10 chunks）", quota0)

    # ---- 1. 实体解析（SDK KG）：美股英文名 + A 股 ISIN crosswalk ----
    aapl_id = rc(lambda: resolver.resolve_id("Apple"))
    print(f"\n[1a] Apple -> rp_entity_id = {aapl_id}")

    # A 股：中文名直查会 0 命中，演示用 ISIN crosswalk（茅台）
    moutai = rc(lambda: resolver.resolve_by_isin(["CNE0000018R8"]))
    _show("[1b] 贵州茅台 ISIN(CNE0000018R8) crosswalk", moutai)
    moutai_id = moutai[0].get("id") if moutai and moutai[0] else None

    # ---- 2. SDK 缺失的前瞻财报日历（REST 逃生舱） ----
    if aapl_id:
        cal = rc(lambda: rest.events_calendar(
            aapl_id,
            categories=["earnings-call"],
            start_date="2026-06-01",
            end_date="2026-12-31",
            limit=3,
        ))
        # 只看顶层结构 + 第一条，避免刷屏
        top_keys = list(cal.keys()) if isinstance(cal, dict) else type(cal).__name__
        _show("[2] 前瞻财报日历 events-calendar（REST）顶层 keys", top_keys)

    # ---- 3. SDK 缺失的前瞻一致预期（REST 逃生舱） ----
    if aapl_id:
        try:
            est = rc(lambda: rest.analyst_estimates(aapl_id, period="quarter", limit=3))
            top = list(est.keys()) if isinstance(est, dict) else type(est).__name__
            _show("[3] 前瞻一致预期 analyst-estimates（REST）顶层 keys", top)
        except Exception as e:  # endpoint 半文档化，schema 可能漂移
            print(f"\n[3] analyst-estimates 调用异常（半文档化 endpoint）: "
                  f"{type(e).__name__}: {str(e)[:160]}")

    # ---- 4. A 股结构化数据可用性验证（茅台 surprise） ----
    if moutai_id:
        try:
            surp = rc(lambda: rest.latest_surprise(moutai_id))
            top = list(surp.keys()) if isinstance(surp, dict) else type(surp).__name__
            _show("[4] 茅台 latest-surprise（REST，验证 A 股结构面可用）顶层 keys", top)
        except Exception as e:
            print(f"\n[4] 茅台 surprise 异常: {type(e).__name__}: {str(e)[:160]}")

    # ---- 5. 成本外推模型（纯计算，演示冷启动预算否决判断） ----
    model = CostModel(chunk_limit_per_query=500, tier="fast")
    est_poc = model.estimate(n_entities=20, n_windows=1)
    est_full = model.estimate(n_entities=100, n_windows=12)  # 100 标的 × 3 年季度
    _show("[5a] 冷启动成本外推 · PoC（20 标的单快照）", est_poc)
    _show("[5b] 冷启动成本外推 · 全量（100 标的 × 3 年季度）", est_full)
    if est_full["pct_of_trial_quota"] > 100:
        print(f"  ⚠️ 全量 backfill 需 {est_full['pct_of_trial_quota']}% trial 配额 "
              f"→ trial 做不了，需要更大的付费配额")

    # ---- 6.（可选）带标注 chunk 抽取（按 chunk 计费，显式开启） ----
    if args.with_search and aapl_id:
        rc(lambda: tracker.snapshot())
        searcher = AnnotatedSearcher(client)
        docs = rc(lambda: searcher.search_entity(aapl_id, keyword="revenue", chunk_limit=10))
        n_chunks = sum(len(d.get("chunks", [])) for d in docs)
        print(f"\n[6] search 返回 {len(docs)} docs / {n_chunks} chunks")
        if docs and docs[0].get("chunks"):
            ch = docs[0]["chunks"][0]
            text = ch.get("text") or ""
            print(f"    首 chunk sentiment={ch.get('sentiment')} "
                  f"entities={len(ch.get('entities') or [])} text[:80]={text[:80]!r}")
        _show("[6] search 实际消耗 delta", rc(lambda: tracker.delta()))
    else:
        print("\n[6] search 已跳过（加 --with-search 开启，按 chunk 计费）")

    quota1 = rc(lambda: tracker.quota())
    print(f"\n[*] 结束配额 used_chunks={quota1['used_chunks']} "
          f"(起始 {quota0['used_chunks']}, 本次净增 "
          f"{quota1['used_chunks'] - quota0['used_chunks']} chunks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
