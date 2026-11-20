#!/usr/bin/env python3
"""Render a live, zero-dependency business decision cockpit HTML from calibrate_quota JSON.

Zero hardcoded snapshots, zero external CDNs, zero decorative fluff.
Designed purely around 3 business questions:
  1. What can I use right now? (Live pool states, pool independence / waste risk, subscription ROI)
  2. Where did my quota actually go? (Window spend breakdown: normal cache read vs 5m TTL 20x miss vs concurrent subagents + lossless savings)
  3. How should I route work next? (Live state-driven workload routing + same-machine Codex standby accounts)
"""

from __future__ import annotations

import html
import json
from typing import Any


def _esc(val: Any) -> str:
    return html.escape(str(val if val is not None else ""))


def _fmt_usd(val: float | None, digits: int = 2) -> str:
    if val is None:
        return "待校准"
    if digits == 0:
        return f"${round(val):,}"
    return f"${val:,.{digits}f}"


def _fmt_pct(val: float | None, digits: int = 1) -> str:
    if val is None:
        return "—"
    return f"{val:.{digits}f}%"


def _pool_badge(b: dict[str, Any]) -> tuple[str, str]:
    state = b.get("lockout_state", "OPEN")
    if state == "LOCKED":
        return "已锁死", "badge-alert"
    if state == "SOFT_LOCKOUT":
        return "软锁死 (<1%)", "badge-alert"
    if b.get("boundary_hour_overcount"):
        return "刚刷新 · 待校准", "badge-warn"
    rem = float(b.get("remaining_fraction") or 0.0) * 100.0
    if rem < 20.0:
        return "余量紧张", "badge-warn"
    return "可用", "badge-safe"


def render_html_report(result: dict[str, Any]) -> str:
    provider = str(result.get("provider") or "unknown")
    observed = str(result.get("observed_at_local") or "")
    buckets: list[dict[str, Any]] = result.get("buckets") or []
    summary: dict[str, Any] = result.get("business_summary") or {}
    forensics: dict[str, Any] | None = result.get("window_forensics")
    top_sessions: list[dict[str, Any]] = result.get("top_sessions") or []
    codex_accounts: list[dict[str, Any]] = result.get("codex_standby_accounts") or []

    locked_buckets = [b for b in buckets if b.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT")]
    any_locked = bool(locked_buckets)

    # Headline status banner (adapts automatically to live locked vs unlocked state)
    headline = summary.get("headline") or (
        "当前存在配额锁死池，请按下方实时分流表切换" if any_locked else "所有配额池当前均处于可用状态"
    )
    subline = summary.get("subline") or f"观测快照：{observed} · 数据源：{provider}"
    banner_cls = "banner-alert" if any_locked else "banner-safe"
    banner_tag = "当前存在锁死池" if any_locked else "全池运行正常"

    # Build 4 concise business KPI cards
    kpi_cards: list[tuple[str, str, str, str]] = []

    # KPI 1: Primary available pool right now
    open_hero = summary.get("primary_open_pool")
    if open_hero:
        kpi_cards.append((
            "当前主力可用池",
            _esc(open_hero.get("headline", "—")),
            _esc(open_hero.get("detail", "")),
            "kpi-safe",
        ))
    elif buckets:
        b0 = buckets[0]
        kpi_cards.append((
            "主配额池状态",
            f"余 {b0['remaining_fraction']*100:.1f}%",
            f"{b0['group_name']} ({b0['window']}) · 重置 {b0.get('time_to_reset') or '—'}",
            "kpi-neutral",
        ))

    # KPI 2: Binding / watched pool status (e.g. Opus 5h)
    watch_pool = summary.get("watched_pool")
    if watch_pool:
        kpi_cards.append((
            _esc(watch_pool.get("label", "受限池状态")),
            _esc(watch_pool.get("value", "—")),
            _esc(watch_pool.get("detail", "")),
            "kpi-alert" if watch_pool.get("is_locked") else "kpi-safe",
        ))

    # KPI 3: Pool independence & waste risk ("不用亏不亏？")
    waste = summary.get("waste_risk")
    if waste:
        w_cls = "kpi-warn" if waste.get("status") == "HIGH_WASTE_RISK" else "kpi-neutral"
        kpi_cards.append((
            "双池独立 · 不用亏不亏",
            _esc(waste.get("headline", "—")),
            _esc(waste.get("detail", "")),
            w_cls,
        ))

    # KPI 4: Weekly API-equivalent spend & Subscription ROI
    roi = summary.get("plan_roi")
    if roi:
        roi_val = (
            f"{roi['roi_multiple']:.1f}× 回本"
            if roi.get("roi_multiple") is not None
            else _fmt_usd(roi.get("weekly_spend_usd"), 2)
        )
        kpi_cards.append((
            "本周实耗等效 API 与回本",
            roi_val,
            _esc(roi.get("detail", "")),
            "kpi-safe" if (roi.get("roi_multiple") or 0) >= 1.0 else "kpi-neutral",
        ))

    kpi_html = "".join(
        f"""<div class="kpi {cls}">
          <div class="kpi-k">{k}</div>
          <div class="kpi-v">{v}</div>
          <div class="kpi-s">{s}</div>
        </div>"""
        for k, v, s, cls in kpi_cards
    )

    # Strict Lie Factor = 1.00 capacity bars across buckets with valid implied USD
    valid_caps = [
        float(b["implied_pool_base_usd"])
        for b in buckets
        if b.get("implied_pool_base_usd") is not None and not b.get("boundary_hour_overcount")
    ]
    max_cap = max(valid_caps) if valid_caps else 1.0

    pool_rows_html = []
    for b in buckets:
        badge_txt, badge_cls = _pool_badge(b)
        gk = str(b.get("group_key") or "")
        cap_val = b.get("implied_pool_base_usd")
        cap_upper = b.get("implied_pool_upper_usd")
        is_overcount = bool(b.get("boundary_hour_overcount"))
        used_pct = float(b.get("used_pct") or 0.0)
        rem_pct = float(b.get("remaining_fraction") or 0.0) * 100.0
        ttr = b.get("time_to_reset") or "—"
        reset_at = (b.get("reset_time_local") or "")[11:19] or (b.get("reset_time_local") or "—")

        if is_overcount or cap_val is None:
            cap_str = "刚刷新 · 待满 1h 校准" if is_overcount else "待更多用量校准"
            bar_html = f"""<div class="bar-wrap bar-uncalibrated">
              <div class="bar-pct-fill" style="width:{min(100.0, used_pct):.2f}%"></div>
              <span class="bar-inline-note">窗口内已用 {used_pct:.1f}% · 跨整点刷新暂不外推美元上限</span>
            </div>"""
        else:
            if cap_upper is not None and abs(float(cap_upper) - float(cap_val)) > 1.0:
                cap_str = f"${float(cap_val):,.0f} ~ ${float(cap_upper):,.0f}"
            else:
                cap_str = f"${float(cap_val):,.2f}" if float(cap_val) < 100 else f"${float(cap_val):,.0f}"
            # Strict proportional width (Lie Factor = 1.00, zero min-width inflation!)
            tube_pct = max(0.0, min(100.0, (float(cap_val) / max_cap) * 100.0))
            fill_pct = max(0.0, min(100.0, used_pct))
            fill_cls = "fill-alert" if b.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT") else ("fill-gemini" if gk == "gemini" else "fill-opus")
            bar_html = f"""<div class="bar-track-prop" title="严格等比容量条（Lie Factor = 1.00）：相对最大池占 {tube_pct:.2f}%">
              <div class="bar-prop-inner">
                <div class="bar-tube" style="width:{tube_pct:.3f}%">
                  <div class="bar-fill {fill_cls}" style="width:{fill_pct:.2f}%"></div>
                </div>
              </div>
              <span class="bar-cap-tag">{cap_str}</span>
            </div>"""

        if b.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT"):
            runway_str = f"<strong class='txt-alert'>$0</strong>（{ttr} 后解锁 · {reset_at}）"
        elif is_overcount:
            runway_str = f"余 <strong>{rem_pct:.1f}%</strong>（重置 {ttr}）"
        elif b.get("remaining_usd_base") is not None:
            runway_str = f"<strong>${float(b['remaining_usd_base']):,.0f}</strong>（余 {rem_pct:.1f}% · 重置 {ttr}）"
        else:
            runway_str = f"余 {rem_pct:.1f}%（重置 {ttr}）"

        pool_rows_html.append(f"""<tr>
          <td>
            <div class="pool-name">{_esc(b.get('group_name'))}</div>
            <div class="pool-meta"><code>{_esc(b.get('bucket_id'))}</code> · {_esc(b.get('window'))} · 置信度 {_esc(b.get('confidence'))}</div>
          </td>
          <td><span class="badge {badge_cls}">{badge_txt}</span></td>
          <td class="col-bar">{bar_html}</td>
          <td class="num">{used_pct:.2f}%</td>
          <td>{runway_str}</td>
        </tr>""")

    # Section 2: Real Spend Forensics & Zero-Compression Lossless Savings
    forensics_section_html = ""
    if forensics or top_sessions:
        breakdown_html = ""
        savings_html = ""
        if forensics:
            tot_w = max(0.01, float(forensics.get("window_total_usd") or 0.0))
            sub_usd = float((forensics.get("concurrent_subagents") or {}).get("cost_usd") or 0.0)
            ttl_waste = float((forensics.get("ttl_cold_misses") or {}).get("avoidable_waste_usd") or 0.0)
            norm_usd = max(0.0, tot_w - sub_usd - ttl_waste)
            p_norm = (norm_usd / tot_w) * 100.0
            p_ttl = (ttl_waste / tot_w) * 100.0
            p_sub = (sub_usd / tot_w) * 100.0

            zero_save = float(forensics.get("zero_compression_savings_usd") or 0.0)
            zero_pct = float(forensics.get("zero_compression_savings_pct") or 0.0)
            sub_cnt = int((forensics.get("concurrent_subagents") or {}).get("count") or 0)
            ttl_cnt = int((forensics.get("ttl_cold_misses") or {}).get("count") or 0)
            prim = forensics.get("primary_session") or {}

            breakdown_html = f"""<div class="forensics-box">
              <div class="fb-head">
                <div>
                  <strong>当前窗口真实开销拆解（{_esc(forensics.get('group_key', ''))} 池 · 实测 ${_esc(f'{tot_w:.2f}')}）</strong>
                  <span class="muted">主会话 <code>{_esc(prim.get('short_id', '—'))}</code> 峰值上下文 <strong>{_esc(prim.get('peak_context_k', 0))}k</strong> / 均上下文 {_esc(prim.get('avg_context_k', 0))}k</span>
                </div>
                <div class="fb-save">不压缩主会话即可无损省 <strong>${zero_save:.2f}（{zero_pct:.1f}%）</strong></div>
              </div>
              <div class="stacked-bar" role="img" aria-label="窗口花费结构：主会话正常缓存读、5分钟缓存过期20倍重传损耗、并发子代理消耗">
                <div class="sb-seg sb-norm" style="width:{p_norm:.2f}%" title="主会话正常缓存读与输出：${norm_usd:.2f} ({p_norm:.1f}%)"></div>
                <div class="sb-seg sb-ttl" style="width:{p_ttl:.2f}%" title="5 分钟缓存过期 20× 冷重传损耗：${ttl_waste:.2f} ({p_ttl:.1f}%)"></div>
                <div class="sb-seg sb-sub" style="width:{p_sub:.2f}%" title="并发子代理消耗：${sub_usd:.2f} ({p_sub:.1f}%)"></div>
              </div>
              <div class="sb-legend">
                <span><i class="dot dot-norm"></i>主会话正常缓存读与推理：<strong>${norm_usd:.2f}</strong>（{p_norm:.1f}%）</span>
                <span><i class="dot dot-ttl"></i>5 分钟缓存过期 20× 冷重传损耗（{ttl_cnt} 次）：<strong class="txt-alert">${ttl_waste:.2f}</strong>（{p_ttl:.1f}%）</span>
                <span><i class="dot dot-sub"></i>并发子代理消耗（{sub_cnt} 个会话）：<strong class="txt-warn">${sub_usd:.2f}</strong>（{p_sub:.1f}%）</span>
              </div>
            </div>"""

            ttl_events = (forensics.get("ttl_cold_misses") or {}).get("events") or []
            ttl_detail = (
                "；".join(f"{e['time']} ({e['input_k']:.0f}k 冷重传, 多花 ${e['waste_usd']:.2f})" for e in ttl_events[:3])
                if ttl_events else "本窗未检出 >50k 冷重传"
            )
            savings_html = f"""<div class="savings-grid">
              <div class="sav-card">
                <div class="sav-tag">杠杆 1 · 零损最高收益</div>
                <div class="sav-title">并发子代理全部分流至 Gemini</div>
                <div class="sav-num txt-safe">直省 ${sub_usd:.2f}（{(sub_usd/tot_w*100):.1f}%）</div>
                <p>不碰主会话上下文。当前窗口检出 {sub_cnt} 个并发子代理会话直接吃掉 Opus 迷你 5h 池。</p>
              </div>
              <div class="sav-card">
                <div class="sav-tag">杠杆 2 · 避开 20× 隐形税</div>
                <div class="sav-title">避免 250k+ 高上下文静置 &gt;5 分钟</div>
                <div class="sav-num txt-safe">直省 ${ttl_waste:.2f}（{(ttl_waste/tot_w*100):.1f}%）</div>
                <p>Prompt Cache 5 分钟过期后重传按 $4/M 计费（缓存读的 20 倍）。实测命中：{_esc(ttl_detail)}。</p>
              </div>
              <div class="sav-card">
                <div class="sav-tag">杠杆 3 · 符合 1M 工程常识</div>
                <div class="sav-title">主会话保真，绝不设 &lt;250k 压缩</div>
                <div class="sav-num">≥300k 再按需 /compact</div>
                <p>仅靠杠杆 1 + 杠杆 2，主会话 <strong>零压缩</strong> 即可降低 <strong>{zero_pct:.1f}%</strong> 消耗；只有上下文突破 300k–350k 时才值得手动收口。</p>
              </div>
            </div>"""

        role_map = {}
        if forensics:
            psid = (forensics.get("primary_session") or {}).get("session_id")
            if psid:
                role_map[psid] = ("主会话", "badge-opus")
            for sub in (forensics.get("concurrent_subagents") or {}).get("sessions") or []:
                role_map[sub["session_id"]] = ("并发子代理", "badge-warn")

        sess_rows = []
        for s in top_sessions:
            sid = str(s.get("session_id") or "")
            role_txt, role_cls = role_map.get(sid, ("常规会话", "badge-neutral"))
            if s.get("context_snowball"):
                role_txt = f"{role_txt} · 长上下文雪球"
                role_cls = "badge-alert"
            avg_ctx = s.get("avg_context_k")
            avg_ctx_str = f"{avg_ctx:.1f}k" if avg_ctx is not None else "—"
            sess_rows.append(f"""<tr>
              <td><code>{_esc(sid[:8])}</code></td>
              <td>{_esc(s.get('model'))}</td>
              <td><span class="badge {role_cls}">{_esc(role_txt)}</span></td>
              <td class="num">{avg_ctx_str}</td>
              <td class="num">{float(s.get('cache_read_pct') or 0):.1f}%</td>
              <td class="num">{int(s.get('message_count') or 0)}</td>
              <td class="num"><strong>${float(s.get('cost_usd') or 0):.2f}</strong></td>
              <td class="num">{float(s.get('share_of_group_spend_pct') or 0):.1f}%</td>
            </tr>""")

        sess_table_html = (
            f"""<table class="data-table">
              <thead>
                <tr>
                  <th>会话 ID</th><th>模型</th><th>归因角色</th>
                  <th class="num">单轮均上下文</th><th class="num">缓存命中</th>
                  <th class="num">轮次</th><th class="num">花费</th><th class="num">池占比</th>
                </tr>
              </thead>
              <tbody>{''.join(sess_rows)}</tbody>
            </table>"""
            if sess_rows else ""
        )

        forensics_section_html = f"""<section class="card">
          <div class="sec-head">
            <h2>2. 钱花哪去了？实时窗口归因与零压缩省钱账单</h2>
            <span class="muted">基于本地实时日志自动拆解 · 零硬编码 · 绝不建议 &lt;250k 反常识压缩</span>
          </div>
          {breakdown_html}
          {savings_html}
          {sess_table_html}
        </section>"""

    # Section 3: Dynamic Live Routing + Same-Machine Codex Standby Accounts
    routing_rows = []
    for r in summary.get("live_routing") or []:
        r_cls = "badge-safe" if r.get("tone") == "safe" else ("badge-warn" if r.get("tone") == "warn" else "badge-neutral")
        routing_rows.append(f"""<tr>
          <td><strong>{_esc(r.get('workload'))}</strong><div class="pool-meta">{_esc(r.get('pattern'))}</div></td>
          <td><span class="badge {r_cls}">{_esc(r.get('channel'))}</span></td>
          <td>{_esc(r.get('reason'))}</td>
          <td>{_esc(r.get('rule'))}</td>
        </tr>""")

    codex_html = ""
    if codex_accounts:
        cx_rows = []
        for c in codex_accounts:
            used_p = float(c.get("used_pct") or 0.0)
            rem_p = max(0.0, 100.0 - used_p)
            is_lock = used_p >= 99.9
            st_badge = (
                '<span class="badge badge-alert">已用 100% · 锁死</span>'
                if is_lock else
                f'<span class="badge badge-safe">可用 · 余 {rem_p:.0f}%</span>'
            )
            act = ' <span class="badge badge-neutral">当前激活</span>' if c.get("is_active") else ""
            bal = f" · 余额 ${float(c['credit_usd']):.2f}" if (c.get("credit_usd") or 0) > 0 else ""
            cx_rows.append(f"""<tr>
              <td><strong>{_esc(c.get('email'))}</strong>{act}<div class="pool-meta">{_esc(c.get('plan'))} · {_esc(c.get('window'))}{bal}</div></td>
              <td>{st_badge}</td>
              <td class="num">{used_p:.0f}%</td>
              <td>{_esc(c.get('reset_local_short') or '—')}</td>
            </tr>""")
        codex_html = f"""<div class="sub-block">
          <h3>同机 Codex 备用账号实时状态（来源：<code>tokscale usage</code>）</h3>
          <table class="data-table">
            <thead><tr><th>账号 / 套餐</th><th>状态</th><th class="num">已用</th><th>重置时间</th></tr></thead>
            <tbody>{''.join(cx_rows)}</tbody>
          </table>
        </div>"""

    # Transparent caveats / warnings
    all_warnings = list(result.get("warnings") or [])
    for b in buckets:
        for w in b.get("warnings") or []:
            all_warnings.append(f"[{b.get('bucket_id')}] {w}")
    warnings_html = ""
    if all_warnings:
        items = "".join(f"<li>{_esc(w)}</li>" for w in all_warnings)
        warnings_html = f"""<details class="caveats">
          <summary>口径说明与实时校准提示（{len(all_warnings)} 条）</summary>
          <ul>{items}</ul>
        </details>"""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 配额实时业务决策台 · {_esc(provider)}</title>
<style>
  :root {{
    --bg: #F4F6F8;
    --card: #FFFFFF;
    --ink: #111827;
    --ink-2: #4B5563;
    --ink-3: #6B7280;
    --line: #E5E7EB;
    --line-strong: #D1D5DB;
    --safe: #0F766E;
    --safe-bg: #ECFDF5;
    --alert: #B91C1C;
    --alert-bg: #FEF2F2;
    --warn: #B45309;
    --warn-bg: #FFFBEB;
    --gemini: #1D4ED8;
    --opus: #44403C;
    --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    --sans: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 1120px; margin: 0 auto; padding: 24px 20px 44px; }}
  .topbar {{
    display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 12px;
    margin-bottom: 16px;
  }}
  .brand {{ font-size: 15px; font-weight: 700; letter-spacing: -0.01em; }}
  .meta-ts {{ font-family: var(--mono); font-size: 12px; color: var(--ink-3); }}
  .banner {{
    border-radius: 8px; padding: 16px 20px; margin-bottom: 18px;
    border: 1px solid var(--line); background: var(--card);
    border-left-width: 4px;
  }}
  .banner-alert {{ border-left-color: var(--alert); background: linear-gradient(90deg, #FEF2F2 0%, #FFFFFF 36%); }}
  .banner-safe {{ border-left-color: var(--safe); background: linear-gradient(90deg, #ECFDF5 0%, #FFFFFF 36%); }}
  .banner-tag {{
    display: inline-block; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 3px; margin-bottom: 6px;
  }}
  .banner-alert .banner-tag {{ background: var(--alert); color: #fff; }}
  .banner-safe .banner-tag {{ background: var(--safe); color: #fff; }}
  .banner h1 {{ margin: 0 0 4px; font-size: 21px; line-height: 1.3; letter-spacing: -0.02em; }}
  .banner p {{ margin: 0; color: var(--ink-2); font-size: 13.5px; }}

  .kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 12px; margin-bottom: 18px;
  }}
  .kpi {{
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    padding: 14px 16px; border-top: 3px solid var(--line-strong);
  }}
  .kpi-safe {{ border-top-color: var(--safe); }}
  .kpi-alert {{ border-top-color: var(--alert); }}
  .kpi-warn {{ border-top-color: var(--warn); }}
  .kpi-k {{ font-size: 12px; color: var(--ink-3); font-weight: 600; margin-bottom: 4px; }}
  .kpi-v {{ font-size: 19px; font-weight: 700; font-family: var(--mono); letter-spacing: -0.02em; margin-bottom: 4px; white-space: nowrap; }}
  .kpi-safe .kpi-v {{ color: var(--safe); }}
  .kpi-alert .kpi-v {{ color: var(--alert); }}
  .kpi-warn .kpi-v {{ color: var(--warn); }}
  .kpi-s {{ font-size: 12px; color: var(--ink-2); }}

  .card {{
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    padding: 18px 20px; margin-bottom: 18px;
  }}
  .sec-head {{
    display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px;
    margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid var(--line);
  }}
  .sec-head h2 {{ margin: 0; font-size: 16px; font-weight: 700; }}
  .muted {{ font-size: 12px; color: var(--ink-3); }}
  .sub-block {{ margin-top: 18px; padding-top: 14px; border-top: 1px dashed var(--line-strong); }}
  .sub-block h3 {{ margin: 0 0 10px; font-size: 14px; font-weight: 700; }}

  .data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .data-table th {{
    text-align: left; font-size: 11.5px; font-weight: 600; color: var(--ink-3);
    padding: 8px 10px; border-bottom: 1px solid var(--line-strong); white-space: nowrap;
  }}
  .data-table td {{ padding: 10px; border-bottom: 1px solid var(--line); vertical-align: middle; }}
  .data-table tr:last-child td {{ border-bottom: none; }}
  .num {{ text-align: right; font-family: var(--mono); white-space: nowrap; }}
  .pool-name {{ font-weight: 600; }}
  .pool-meta {{ font-size: 11.5px; color: var(--ink-3); margin-top: 2px; }}
  code {{ font-family: var(--mono); font-size: 11.5px; background: #F3F4F6; padding: 1px 5px; border-radius: 3px; }}

  .badge {{
    display: inline-block; font-size: 11.5px; font-weight: 600; padding: 2px 8px;
    border-radius: 4px; white-space: nowrap;
  }}
  .badge-safe {{ background: var(--safe-bg); color: var(--safe); }}
  .badge-alert {{ background: var(--alert-bg); color: var(--alert); }}
  .badge-warn {{ background: var(--warn-bg); color: var(--warn); }}
  .badge-opus {{ background: #F5F5F4; color: var(--opus); }}
  .badge-neutral {{ background: #F3F4F6; color: var(--ink-2); }}
  .txt-alert {{ color: var(--alert); }}
  .txt-safe {{ color: var(--safe); }}
  .txt-warn {{ color: var(--warn); }}

  .col-bar {{ width: 35%; min-width: 260px; }}
  .bar-track-prop {{
    display: flex; align-items: center; gap: 10px;
    background: #F3F4F6; border-radius: 4px; padding: 4px 8px;
  }}
  .bar-prop-inner {{
    flex: 1; min-width: 0; height: 14px; display: flex; align-items: center;
  }}
  .bar-tube {{
    height: 14px; background: #FFFFFF; border: 1px solid #9CA3AF; border-radius: 2px;
    overflow: hidden; flex-shrink: 0;
  }}
  .bar-fill {{ height: 100%; }}
  .fill-gemini {{ background: var(--gemini); }}
  .fill-opus {{ background: var(--opus); }}
  .fill-alert {{ background: var(--alert); }}
  .bar-cap-tag {{ font-family: var(--mono); font-size: 11.5px; color: var(--ink-2); white-space: nowrap; flex-shrink: 0; min-width: 72px; text-align: right; }}
  .bar-uncalibrated {{
    position: relative; height: 22px; background: var(--warn-bg);
    border: 1px dashed #D97706; border-radius: 4px; overflow: hidden;
    display: flex; align-items: center; padding: 0 8px;
  }}
  .bar-pct-fill {{ position: absolute; left: 0; top: 0; bottom: 0; background: rgba(217,119,6,0.18); }}
  .bar-inline-note {{ position: relative; font-size: 11px; color: var(--warn); font-weight: 600; }}

  .forensics-box {{
    background: #F9FAFB; border: 1px solid var(--line); border-radius: 6px;
    padding: 14px 16px; margin-bottom: 14px;
  }}
  .fb-head {{
    display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px;
    margin-bottom: 10px;
  }}
  .fb-head .muted {{ margin-left: 8px; }}
  .fb-save {{ font-size: 13px; color: var(--safe); }}
  .stacked-bar {{
    display: flex; height: 18px; border-radius: 4px; overflow: hidden;
    background: #E5E7EB; margin-bottom: 8px;
  }}
  .sb-seg {{ height: 100%; }}
  .sb-norm {{ background: var(--opus); }}
  .sb-ttl {{ background: var(--alert); }}
  .sb-sub {{ background: #D97706; }}
  .sb-legend {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 12.5px; color: var(--ink-2); }}
  .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; vertical-align: middle; }}
  .dot-norm {{ background: var(--opus); }}
  .dot-ttl {{ background: var(--alert); }}
  .dot-sub {{ background: #D97706; }}

  .savings-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 12px; margin-bottom: 16px;
  }}
  .sav-card {{
    border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; background: #FFFFFF;
  }}
  .sav-tag {{ font-size: 11px; font-weight: 700; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.03em; }}
  .sav-title {{ font-size: 14px; font-weight: 700; margin: 3px 0 4px; }}
  .sav-num {{ font-family: var(--mono); font-size: 16px; font-weight: 700; margin-bottom: 6px; }}
  .sav-card p {{ margin: 0; font-size: 12.5px; color: var(--ink-2); }}

  .caveats {{
    margin-top: 12px; background: var(--card); border: 1px solid var(--line);
    border-radius: 6px; padding: 10px 14px; font-size: 12px; color: var(--ink-2);
  }}
  .caveats summary {{ cursor: pointer; font-weight: 600; color: var(--ink); }}
  .caveats ul {{ margin: 8px 0 0; padding-left: 18px; }}
  .caveats li {{ margin-bottom: 4px; }}
  .foot {{
    margin-top: 16px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
    font-size: 11.5px; color: var(--ink-3); font-family: var(--mono);
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="brand">AI 配额实时业务决策台 · <code>ai-quota-calibrator</code></div>
    <div class="meta-ts">实时观测：{_esc(observed)} · 数据源：{_esc(provider)}</div>
  </div>

  <div class="banner {banner_cls}">
    <div class="banner-tag">{banner_tag}</div>
    <h1>{_esc(headline)}</h1>
    <p>{_esc(subline)}</p>
  </div>

  <div class="kpi-grid">{kpi_html}</div>

  <section class="card">
    <div class="sec-head">
      <h2>1. 实测配额账本（双池独立 · 严格 1:1 真实物理比例）</h2>
      <span class="muted">条长严格按隐含 API 美元上限等比绘制（Lie Factor = 1.00，绝不虚胖）；跨整点刚刷新的池标注待校准</span>
    </div>
    <table class="data-table">
      <thead>
        <tr>
          <th>配额池 / 窗口</th>
          <th>状态</th>
          <th>真实容量比例与上限（API 等效美元）</th>
          <th class="num">已用</th>
          <th>剩余可用与重置</th>
        </tr>
      </thead>
      <tbody>{''.join(pool_rows_html)}</tbody>
    </table>
  </section>

  {forensics_section_html}

  <section class="card">
    <div class="sec-head">
      <h2>3. 接下来怎么配最值？（实时状态驱动分流表）</h2>
      <span class="muted">随此刻配额池状态自动切换，解锁后再次运行自动更新为绿灯建议</span>
    </div>
    <table class="data-table">
      <thead>
        <tr>
          <th>工程任务类型</th>
          <th>此刻推荐通道</th>
          <th>实时依据</th>
          <th>防撞墙 / 防浪费纪律</th>
        </tr>
      </thead>
      <tbody>{''.join(routing_rows)}</tbody>
    </table>
    {codex_html}
  </section>

  {warnings_html}

  <div class="foot">
    <span>由 ai-quota-calibrator 实时生成 · 零外链 CDN · 离线单文件</span>
    <span>任意时刻运行即可基于当下真实配额与日志重算</span>
  </div>
</div>
</body>
</html>
"""


def main() -> int:
    import argparse
    from pathlib import Path

    p = argparse.ArgumentParser(description="Render calibrate_quota JSON into a live HTML business cockpit.")
    p.add_argument("input_json", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    args = p.parse_args()
    data = json.loads(args.input_json.read_text(encoding="utf-8"))
    args.output.write_text(render_html_report(data), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
