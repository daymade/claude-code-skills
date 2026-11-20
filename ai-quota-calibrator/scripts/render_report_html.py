#!/usr/bin/env python3
"""Render a live, zero-dependency Architectural Ceramic HTML business cockpit from calibrate_quota JSON.

Combines live business-first decision clarity with tactile non-flat precision-instrument craft:
  - 12-o'clock top-lit Architectural Ceramic chassis, beveled plates, recessed wells, jewel LEDs
  - Recessed sapphire-glass live quartz countdown chronometer (auto-freezes past reset_time)
  - Strict Lie Factor = 1.00 borosilicate sight-glass reservoir + clickable optical magnification loupe
    with 真实美元尺度 / 单池 100% 归一化水位 toggle (pure inline SVG + vanilla JS, zero CDNs)
  - Glass-spectrometer window loss attribution (normal burn vs 5m TTL 20x miss vs concurrent subagents)
  - Live state-driven workload routing + calibrated recessed Codex standby gauges + collapsible glossary
"""

from __future__ import annotations

import datetime as dt
import html
import json
import math
from typing import Any


def _esc(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=True)


def _finite_float(val: Any, default: float = 0.0) -> float:
    if isinstance(val, bool) or val is None:
        return default
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _opt_finite_float(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _safe_int(val: Any, default: int = 0) -> int:
    if isinstance(val, bool) or val is None:
        return default
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    return int(f) if math.isfinite(f) else default


def _valid_iso_timestamp(val: Any) -> str:
    s = str(val or "").strip()
    if len(s) < 19:
        return ""
    try:
        dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return s


def _safe_json_for_script(obj: Any) -> str:
    return (
        json.dumps(obj, ensure_ascii=False, allow_nan=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _fmt_usd(val: float | None, digits: int = 2) -> str:
    f = _opt_finite_float(val)
    if f is None:
        return "待校准"
    if digits == 0:
        return f"${round(f):,}"
    return f"${f:,.{digits}f}"


def _pool_badge(b: dict[str, Any]) -> tuple[str, str]:
    state = b.get("lockout_state", "OPEN")
    if state == "LOCKED":
        return "已锁死", "badge-alert"
    if state == "SOFT_LOCKOUT":
        return "软锁死 (<1%)", "badge-alert"
    if b.get("boundary_hour_overcount"):
        return "刚刷新 · 待校准", "badge-warn"
    if b.get("confidence") == "UNTOUCHED":
        return "满额未用", "badge-safe"
    rem = max(0.0, min(100.0, _finite_float(b.get("remaining_fraction"), 0.0) * 100.0))
    if rem < 20.0:
        return "余量紧张", "badge-warn"
    return "可用", "badge-safe"


def _pick_chronometer_bucket(buckets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the most actionable countdown target: binding locked bucket first, else shortest active 5h reset.

    When both weekly and 5h are locked for the same group_key, weekly is the binding lockout
    (matching build_business_summary), so 5h never falsely promises an early unlock.
    """
    locked_by_group: dict[str, list[dict[str, Any]]] = {}
    for b in buckets:
        if b.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT"):
            gk = str(b.get("group_key") or b.get("bucket_id") or "")
            locked_by_group.setdefault(gk, []).append(b)
    if locked_by_group:
        binding_locked: list[dict[str, Any]] = []
        for grp_buckets in locked_by_group.values():
            weekly_locked = [b for b in grp_buckets if b.get("window") == "weekly"]
            binding_locked.append(weekly_locked[0] if weekly_locked else grp_buckets[0])
        with_ttr = [b for b in binding_locked if _opt_finite_float(b.get("time_to_reset_seconds")) is not None]
        if with_ttr:
            return min(with_ttr, key=lambda b: _safe_int(b.get("time_to_reset_seconds"), 10**9))
        return binding_locked[0]

    with_reset = [
        b for b in buckets
        if _valid_iso_timestamp(b.get("reset_time_local"))
        and _opt_finite_float(b.get("time_to_reset_seconds")) is not None
    ]
    if not with_reset:
        return buckets[0] if buckets else None
    five_h = [b for b in with_reset if b.get("window") == "5h"]
    pool = five_h if five_h else with_reset
    return min(pool, key=lambda b: _safe_int(b.get("time_to_reset_seconds"), 10**9))


def _pick_default_loupe_index(buckets: list[dict[str, Any]]) -> int:
    """Default optical loupe target: binding locked bucket first, else smallest calibrated non-empty pool."""
    binding = _pick_chronometer_bucket(buckets)
    if binding is not None and binding.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT"):
        for idx, b in enumerate(buckets):
            if b is binding:
                return idx
    calibrated = [
        (idx, cap)
        for idx, b in enumerate(buckets)
        for cap in [_opt_finite_float(b.get("implied_pool_base_usd"))]
        if cap is not None and cap > 0.0 and not b.get("boundary_hour_overcount")
    ]
    if calibrated:
        return min(calibrated, key=lambda item: item[1])[0]
    return 0


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

    headline = summary.get("headline") or (
        "当前存在配额锁死池，请按下方实时分流表切换" if any_locked else "所有配额池当前均处于可用状态"
    )
    subline = summary.get("subline") or f"观测快照：{observed} · 数据源：{provider}"
    banner_tag = "当前存在锁死池" if any_locked else "全池运行正常"
    led_cls = "led-alert" if any_locked else "led-safe"

    # Recessed Braun Quartz Chronometer target
    chrono_b = _pick_chronometer_bucket(buckets)
    chrono_html = ""
    chrono_payload: dict[str, Any] = {}
    if chrono_b is not None:
        c_locked = chrono_b.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT")
        c_used = max(0.0, min(100.0, _finite_float(chrono_b.get("used_pct"), 0.0)))
        c_rem_pct = max(0.0, min(100.0, _finite_float(chrono_b.get("remaining_fraction"), 0.0) * 100.0))
        c_reset_raw = str(chrono_b.get("reset_time_local") or "")
        c_reset_iso = _valid_iso_timestamp(c_reset_raw)
        c_reset_short = c_reset_iso[11:19] if c_reset_iso else (c_reset_raw or "—")
        c_ttr_sec = max(0, _safe_int(chrono_b.get("time_to_reset_seconds"), 0))
        c_ttr = str(chrono_b.get("time_to_reset") or "—")
        h0, rem0 = divmod(c_ttr_sec, 3600)
        m0, s0 = divmod(rem0, 60)
        init_digits = f"{h0:02d}:{m0:02d}:{s0:02d}" if c_ttr_sec > 0 else "00:00:00"
        ghost_digits = "888:88:88" if h0 >= 100 else "88:88:88"
        is_live_chrono = bool(c_reset_iso)
        c_label = f"{chrono_b.get('group_name')} ({chrono_b.get('window')}) · {'距解锁' if c_locked else '距下次刷新'}"
        c_rem_tag = f"余 {c_rem_pct:.2f}%"
        c_tone = "chrono-alert" if c_locked else "chrono-safe"

        vernier_html = ""
        if c_locked or c_used >= 90.0:
            # Show 95% -> 100% precision lock-pin micro-vernier when near/at lockout
            fill_mv = max(0.0, min(100.0, ((c_used - 95.0) / 5.0) * 100.0))
            vernier_html = f"""<div class="mv-box">
              <div class="mv-head">
                <span>末端 95%→100% 锁销微距游标</span>
                <span class="mono txt-alert"><strong>{c_used:.2f}%</strong> vs 99.0% 锁线</span>
              </div>
              <div class="mv-track">
                <div class="mv-fill" style="width:{fill_mv:.2f}%"></div>
                <div class="mv-pin" title="99.0% 预扣物理锁销"></div>
              </div>
              <div class="mv-ticks">
                <span style="left:0;">95%</span>
                <span style="left:40%;transform:translateX(-50%);">97%</span>
                <span style="left:80%;transform:translateX(-50%);color:var(--ink-1);font-weight:700;">99% 锁销</span>
                <span style="right:0;">100%</span>
              </div>
            </div>"""
        else:
            vernier_html = f"""<div class="mv-box">
              <div class="mv-head">
                <span>当前窗口水位</span>
                <span class="mono txt-safe"><strong>已用 {c_used:.1f}%</strong> · 余 {c_rem_pct:.1f}%</span>
              </div>
              <div class="mv-track mv-track-safe">
                <div class="mv-fill-safe" style="width:{c_used:.2f}%"></div>
              </div>
            </div>"""

        chrono_payload = {
            "resetIso": c_reset_iso,
            "ttrSec": c_ttr_sec,
            "ttrLabel": c_ttr,
            "isLocked": c_locked,
        }
        chrono_html = f"""<div class="chrono-well {c_tone}">
          <div class="chrono-top">
            <span class="chrono-lbl">{_esc(c_label)}</span>
            <span class="live-pill" id="liveBadge"><span class="led-dot {led_cls}"></span><span id="liveModeTxt">{'LIVE 实时' if is_live_chrono else '静态快照'}</span></span>
          </div>
          <div class="chrono-face">
            <div class="chrono-digits-wrap">
              <div class="chrono-ghost" id="quartzGhost" aria-hidden="true">{ghost_digits}</div>
              <div class="chrono-digits" id="quartzClock">{_esc(init_digits)}</div>
            </div>
            <div class="chrono-target">
              <span id="chronoTag">{'自动解锁' if c_locked else '窗口刷新'}</span>
              <strong>{_esc(c_reset_short)}</strong>
            </div>
          </div>
          {vernier_html}
          <div class="chrono-foot">
            <span>{_esc(c_rem_tag)}</span>
            <span class="mono">快照时距重置 {_esc(c_ttr)}</span>
          </div>
        </div>"""

    # Build 4 concise business KPIs
    kpi_cards: list[tuple[str, str, str, str]] = []
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
        b0_rem = max(0.0, min(100.0, _finite_float(b0.get("remaining_fraction"), 0.0) * 100.0))
        kpi_cards.append((
            "主配额池状态",
            f"余 {b0_rem:.1f}%",
            f"{_esc(b0.get('group_name'))} ({_esc(b0.get('window'))}) · 重置 {_esc(b0.get('time_to_reset') or '—')}",
            "kpi-neutral",
        ))

    watch_pool = summary.get("watched_pool")
    if watch_pool:
        kpi_cards.append((
            _esc(watch_pool.get("label", "受限池状态")),
            _esc(watch_pool.get("value", "—")),
            _esc(watch_pool.get("detail", "")),
            "kpi-alert" if watch_pool.get("is_locked") else "kpi-safe",
        ))

    waste = summary.get("waste_risk")
    if waste:
        w_cls = "kpi-warn" if waste.get("status") == "HIGH_WASTE_RISK" else "kpi-neutral"
        kpi_cards.append((
            "双池独立 · 不用亏不亏",
            _esc(waste.get("headline", "—")),
            _esc(waste.get("detail", "")),
            w_cls,
        ))

    roi = summary.get("plan_roi")
    if roi:
        roi_mult = _opt_finite_float(roi.get("roi_multiple"))
        roi_val = (
            f"{roi_mult:.1f}× 回本"
            if roi_mult is not None
            else _fmt_usd(_opt_finite_float(roi.get("weekly_spend_usd")), 2)
        )
        kpi_cards.append((
            "本周实耗等效 API 与回本",
            roi_val,
            _esc(roi.get("detail", "")),
            "kpi-safe" if (roi_mult or 0.0) >= 1.0 else "kpi-neutral",
        ))

    kpi_html = "".join(
        f"""<div class="kpi {cls}">
          <div class="kpi-k">{k}</div>
          <div class="kpi-v">{v}</div>
          <div class="kpi-s">{s}</div>
        </div>"""
        for k, v, s, cls in kpi_cards
    )

    # Prepare live reservoir payload (strict Lie Factor = 1.00, pure SVG + vanilla JS, zero D3!)
    valid_caps = [
        cap
        for b in buckets
        for cap in [_opt_finite_float(b.get("implied_pool_base_usd"))]
        if cap is not None and cap > 0.0 and not b.get("boundary_hour_overcount")
    ]
    max_cap = max(valid_caps) if valid_caps else 0.0
    min_cap = min(valid_caps) if valid_caps else 0.0
    default_loupe_idx = _pick_default_loupe_index(buckets)

    reservoir_pools: list[dict[str, Any]] = []
    for idx, b in enumerate(buckets):
        badge_txt, badge_cls = _pool_badge(b)
        cap_raw = _opt_finite_float(b.get("implied_pool_base_usd"))
        cap_val = cap_raw if (cap_raw is not None and cap_raw > 0.0 and not b.get("boundary_hour_overcount")) else None
        cap_up_raw = _opt_finite_float(b.get("implied_pool_upper_usd"))
        cap_upper = cap_up_raw if (cap_up_raw is not None and cap_up_raw > 0.0 and cap_val is not None) else cap_val
        spend_raw = _opt_finite_float(b.get("spend_base_usd"))
        rem_usd_raw = _opt_finite_float(b.get("remaining_usd_base"))
        used_pct = max(0.0, min(100.0, _finite_float(b.get("used_pct"), 0.0)))
        rem_pct = max(0.0, min(100.0, _finite_float(b.get("remaining_fraction"), 0.0) * 100.0))
        locked = b.get("lockout_state") in ("LOCKED", "SOFT_LOCKOUT")
        reset_raw = str(b.get("reset_time_local") or "")
        reset_iso = _valid_iso_timestamp(reset_raw)
        reset_short = reset_iso[11:19] if reset_iso else (reset_raw or "—")
        rem_msgs_raw = _opt_finite_float(b.get("estimated_remaining_msgs"))
        reservoir_pools.append({
            "idx": idx,
            "id": str(b.get("bucket_id") or f"pool-{idx}"),
            "groupKey": str(b.get("group_key") or "other"),
            "name": str(b.get("group_name") or "Pool"),
            "window": str(b.get("window") or ""),
            "confidence": str(b.get("confidence") or ""),
            "badge": badge_txt,
            "badgeCls": badge_cls,
            "capUsd": round(cap_val, 2) if cap_val is not None else None,
            "capUpperUsd": round(cap_upper, 2) if cap_upper is not None else None,
            "spendUsd": round(spend_raw, 2) if spend_raw is not None else None,
            "remUsd": round(rem_usd_raw, 2) if rem_usd_raw is not None else None,
            "usedPct": round(used_pct, 2),
            "remPct": round(rem_pct, 2),
            "locked": locked,
            "lockoutState": str(b.get("lockout_state") or "OPEN"),
            "overcount": bool(b.get("boundary_hour_overcount")),
            "untouched": b.get("confidence") == "UNTOUCHED",
            "ttr": str(b.get("time_to_reset") or "—"),
            "resetShort": reset_short,
            "remMsgs": int(rem_msgs_raw) if rem_msgs_raw is not None and rem_msgs_raw >= 0 else None,
            "ratioVsMin": round(cap_val / min_cap, 1) if (cap_val is not None and min_cap > 0.0) else None,
            "pctOfMax": round((cap_val / max_cap) * 100.0, 3) if (cap_val is not None and max_cap > 0.0) else None,
        })

    client_payload = {
        "maxCap": round(max_cap, 2),
        "defaultLoupeIdx": default_loupe_idx,
        "pools": reservoir_pools,
        "chrono": chrono_payload,
    }

    # Section 2: Real Spend Forensics & Zero-Compression Lossless Savings
    sec_num = 2
    forensics_section_html = ""
    if forensics or top_sessions:
        breakdown_html = ""
        savings_html = ""
        if forensics and _finite_float(forensics.get("window_total_usd"), 0.0) > 0.0:
            tot_w = _finite_float(forensics.get("window_total_usd"), 0.0)
            sub_usd = max(0.0, _finite_float((forensics.get("concurrent_subagents") or {}).get("cost_usd"), 0.0))
            ttl_waste = max(0.0, _finite_float((forensics.get("ttl_cold_misses") or {}).get("avoidable_waste_usd"), 0.0))
            sub_usd_disp = min(tot_w, sub_usd)
            ttl_waste_disp = min(max(0.0, tot_w - sub_usd_disp), ttl_waste)
            norm_usd = max(0.0, tot_w - sub_usd_disp - ttl_waste_disp)
            p_norm = (norm_usd / tot_w) * 100.0
            p_ttl = (ttl_waste_disp / tot_w) * 100.0
            p_sub = (sub_usd_disp / tot_w) * 100.0

            zero_save = max(0.0, _finite_float(forensics.get("zero_compression_savings_usd"), 0.0))
            zero_pct = max(0.0, min(100.0, _finite_float(forensics.get("zero_compression_savings_pct"), 0.0)))
            sub_cnt = max(0, _safe_int((forensics.get("concurrent_subagents") or {}).get("count"), 0))
            ttl_cnt = max(0, _safe_int((forensics.get("ttl_cold_misses") or {}).get("count"), 0))
            prim = forensics.get("primary_session") or {}
            avg_k = _opt_finite_float(prim.get("avg_context_k"))
            avg_k_txt = f"{avg_k:.1f}k" if avg_k is not None else "—"
            peak_k = _finite_float(prim.get("peak_context_k"), 0.0)

            breakdown_html = f"""<div class="well forensics-well">
              <div class="fb-head">
                <div>
                  <strong>当前窗口真实开销拆解（{_esc(forensics.get('group_key', ''))} 池 · 实测 ${_esc(f'{tot_w:.2f}')}）</strong>
                  <span class="muted">主会话 <code>{_esc(prim.get('short_id', '—'))}</code> 峰值上下文 <strong>{_esc(f'{peak_k:.1f}')}k</strong> / 均上下文 {_esc(avg_k_txt)}</span>
                </div>
                <div class="fb-save">不压缩主会话即可无损省 <strong>${zero_save:.2f}（{zero_pct:.1f}%）</strong></div>
              </div>
              <div class="spec-bar" role="img" aria-label="窗口花费结构：主会话正常缓存读、5分钟缓存过期20倍重传损耗、并发子代理消耗">
                <div class="sb-seg sb-norm" style="width:{p_norm:.2f}%" title="主会话正常缓存读与输出：${norm_usd:.2f} ({p_norm:.1f}%)"></div>
                <div class="sb-seg sb-ttl" style="width:{p_ttl:.2f}%" title="5 分钟缓存过期 20× 冷重传损耗：${ttl_waste_disp:.2f} ({p_ttl:.1f}%)"></div>
                <div class="sb-seg sb-sub" style="width:{p_sub:.2f}%" title="并发子代理消耗：${sub_usd_disp:.2f} ({p_sub:.1f}%)"></div>
              </div>
              <div class="sb-legend">
                <span><i class="sw sw-opus"></i>主会话正常缓存读与推理：<strong>${norm_usd:.2f}</strong>（{p_norm:.1f}%）</span>
                <span><i class="sw sw-alert"></i>5 分钟缓存过期 20× 冷重传损耗（{ttl_cnt} 次）：<strong class="txt-alert">${ttl_waste_disp:.2f}</strong>（{p_ttl:.1f}%）</span>
                <span><i class="sw sw-warn"></i>并发子代理消耗（{sub_cnt} 个会话）：<strong class="txt-warn">${sub_usd_disp:.2f}</strong>（{p_sub:.1f}%）</span>
              </div>
            </div>"""

            ttl_events = (forensics.get("ttl_cold_misses") or {}).get("events") or []
            ttl_detail = (
                "；".join(
                    f"{e.get('time', '—')} ({_finite_float(e.get('input_k'), 0.0):.0f}k 冷重传, 多花 ${_finite_float(e.get('waste_usd'), 0.0):.2f})"
                    for e in ttl_events[:3]
                )
                if ttl_events else "本窗未检出 >50k 冷重传"
            )
            savings_html = f"""<div class="savings-grid">
              <div class="sav-card">
                <div class="sav-tag">杠杆 1 · 零损最高收益</div>
                <div class="sav-title">并发子代理全部分流至 Gemini</div>
                <div class="sav-num txt-safe">直省 ${sub_usd_disp:.2f}（{p_sub:.1f}%）</div>
                <p>不碰主会话上下文。当前窗口检出 {sub_cnt} 个并发子代理会话直接吃掉 Opus 迷你 5h 池。</p>
              </div>
              <div class="sav-card">
                <div class="sav-tag">杠杆 2 · 避开 20× 隐形税</div>
                <div class="sav-title">避免 250k+ 高上下文静置 &gt;5 分钟</div>
                <div class="sav-num txt-safe">直省 ${ttl_waste_disp:.2f}（{p_ttl:.1f}%）</div>
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
                if sub.get("session_id"):
                    role_map[sub["session_id"]] = ("并发子代理", "badge-warn")

        sess_rows = []
        for s in top_sessions:
            sid = str(s.get("session_id") or "")
            role_txt, role_cls = role_map.get(sid, ("常规会话", "badge-neutral"))
            if s.get("context_snowball"):
                role_txt = f"{role_txt} · 长上下文雪球"
                role_cls = "badge-alert"
            avg_ctx = _opt_finite_float(s.get("avg_context_k"))
            avg_ctx_str = f"{avg_ctx:.1f}k" if avg_ctx is not None else "—"
            sess_rows.append(f"""<tr>
              <td><code>{_esc(sid[:8])}</code></td>
              <td>{_esc(s.get('model'))}</td>
              <td><span class="badge {role_cls}">{_esc(role_txt)}</span></td>
              <td class="num">{avg_ctx_str}</td>
              <td class="num">{_finite_float(s.get('cache_read_pct'), 0.0):.1f}%</td>
              <td class="num">{_safe_int(s.get('message_count'), 0)}</td>
              <td class="num"><strong>${_finite_float(s.get('cost_usd'), 0.0):.2f}</strong></td>
              <td class="num">{_finite_float(s.get('share_of_group_spend_pct'), 0.0):.1f}%</td>
            </tr>""")

        sess_table_html = (
            f"""<div class="plot-bed" style="padding:4px 10px;">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>会话 ID</th><th>模型</th><th>归因角色</th>
                    <th class="num">单轮均上下文</th><th class="num">缓存命中</th>
                    <th class="num">轮次</th><th class="num">花费</th><th class="num">池占比</th>
                  </tr>
                </thead>
                <tbody>{''.join(sess_rows)}</tbody>
              </table>
            </div>"""
            if sess_rows else ""
        )

        if breakdown_html or savings_html or sess_table_html:
            forensics_section_html = f"""<section class="plate">
              <div class="sec-head">
                <h2>{sec_num}. 钱花哪去了？实时窗口归因与零压缩省钱账单</h2>
                <span class="muted">基于本地实时日志自动拆解 · 零硬编码 · 绝不建议 &lt;250k 反常识压缩</span>
              </div>
              {breakdown_html}
              {savings_html}
              {sess_table_html}
            </section>"""
            sec_num += 1

    # Section 3 (or 2): Live Routing + Calibrated Recessed Codex Standby Gauges
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
        cx_slots = []
        for c in codex_accounts:
            used_p = max(0.0, min(100.0, _finite_float(c.get("used_pct"), 0.0)))
            rem_p = max(0.0, 100.0 - used_p)
            is_lock = used_p >= 99.9
            st_badge = (
                '<span class="badge badge-alert">⊘ 已用 100% · 锁死</span>'
                if is_lock else
                f'<span class="badge badge-safe">✓ 已用 {used_p:.0f}% · 余 {rem_p:.0f}%</span>'
            )
            act = '<span class="badge badge-opus" style="margin-right:5px;">激活</span>' if c.get("is_active") else ""
            credit_val = _finite_float(c.get("credit_usd"), 0.0)
            bal = f" · 余额 ${credit_val:.2f}" if credit_val > 0.0 else ""
            empty_lbl = '<span class="cx-empty-lbl">0% 已用 · 100% 空载可用</span>' if used_p < 1.0 else ""
            cx_slots.append(f"""<div class="codex-slot">
              <div class="cx-top">
                <span class="cx-mail">{_esc(c.get('email'))}</span>
                <span>{act}{st_badge}</span>
              </div>
              <div class="cx-bar{' open-rim' if not is_lock else ''}">
                <div class="cx-fill {'locked' if is_lock else 'partial'}" style="width:{used_p:.1f}%;"></div>
                {empty_lbl}
              </div>
              <div class="cx-meta">
                <span>{_esc(c.get('plan'))} · {_esc(c.get('window'))}{bal}</span>
                <span>重置 {_esc(c.get('reset_local_short') or '—')}</span>
              </div>
            </div>""")
        codex_html = f"""<div class="sub-block">
          <div class="sub-head">
            <h3>同机 Codex 备用池监控（统一极性：条长 = 已用 %）</h3>
            <span class="muted">来源：<code>tokscale usage</code> · 红斜纹为 100% 锁死，空白绿框刻度槽为 0% 空载可用</span>
          </div>
          <div class="codex-grid">{''.join(cx_slots)}</div>
        </div>"""

    routing_section_html = ""
    if routing_rows or codex_html:
        routing_table_html = (
            f"""<div class="plot-bed" style="padding:4px 10px;">
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
            </div>"""
            if routing_rows else ""
        )
        routing_section_html = f"""<section class="plate">
          <div class="sec-head">
            <h2>{sec_num}. 接下来怎么配最值？（实时状态驱动分流与备用池）</h2>
            <span class="muted">随此刻配额池状态自动切换，解锁后再次运行自动更新为绿灯建议</span>
          </div>
          {routing_table_html}
          {codex_html}
        </section>"""

    # Collapsible glossary + live calibration caveats
    all_warnings = list(result.get("warnings") or [])
    for b in buckets:
        for w in b.get("warnings") or []:
            all_warnings.append(f"[{b.get('bucket_id')}] {w}")
    warnings_ul = (
        f'<div class="warn-block"><strong>本次实时校准提示（{len(all_warnings)} 条）</strong><ul>'
        + "".join(f"<li>{_esc(w)}</li>" for w in all_warnings)
        + "</ul></div>"
        if all_warnings else ""
    )

    reservoir_well_html = (
        """<div class="well">
      <div class="res-head">
        <div class="legend-strip">
          <span><strong id="resTitle">1:N 真实物理尺度储液槽</strong>（点击任意液管切换下方光学放大镜）</span>
          <span><i class="sw sw-gemini"></i>Gemini 通道</span>
          <span><i class="sw sw-opus"></i>Claude/GPT 常规</span>
          <span><i class="sw sw-alert"></i>锁死 / &lt;1% 软锁</span>
        </div>
        <div class="key-group" role="group" aria-label="储液槽比例尺切换">
          <button type="button" class="keycap active" data-scale="true" aria-pressed="true">真实美元尺度</button>
          <button type="button" class="keycap" data-scale="norm" aria-pressed="false">单池 100% 归一化</button>
        </div>
      </div>
      <div class="plot-bed" style="padding:10px 10px 8px;">
        <div id="reservoirHost"></div>
      </div>
      <div class="loupe-caption" id="loupeCaption"></div>
    </div>"""
        if buckets
        else '<div class="well"><span class="muted">当前快照未返回可用配额池数据。</span></div>'
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 配额精密决策台 · {_esc(provider)}</title>
<style>
  :root {{
    --r-plate: 6px;
    --r-well: 4px;
    --r-key: 3px;
    --surface-chassis: #E9EDF1;
    --surface-well: #DCE2E9;
    --surface-well-deep: #CDD5DF;
    --surface-plate-grad: linear-gradient(180deg, #FDFEFF 0%, #F7F9FB 100%);
    --surface-keycap-grad: linear-gradient(180deg, #FFFFFF 0%, #F4F6F9 100%);
    --surface-plot-bed: #F9FBFD;
    --ink-1: #161B22;
    --ink-2: #4B5563;
    --ink-3: #6B7280;
    --rule: #CBD3DC;
    --gemini: #1C5C87;
    --opus: #52463D;
    --safe: #156D50;
    --safe-bg: #E7F5EF;
    --alert: #C8321B;
    --alert-bg: #FDECE9;
    --warn: #B45309;
    --warn-bg: #FEF4E4;
    --bevel-plate:
      inset 0 1px 0 rgba(255,255,255,0.98),
      inset 0 -1px 0 rgba(140,152,168,0.26),
      0 1px 1px rgba(22,27,34,0.06),
      0 4px 10px -2px rgba(22,27,34,0.07),
      0 16px 32px -18px rgba(22,27,34,0.14);
    --bevel-well:
      inset 0 2px 4px rgba(22,27,34,0.12),
      inset 0 1px 1px rgba(22,27,34,0.07),
      inset 0 0 0 1px rgba(45,55,68,0.10),
      0 1px 0 rgba(255,255,255,0.88);
    --bevel-plot-bed:
      inset 0 1.5px 4px rgba(22,27,34,0.06),
      inset 0 0 0 1px rgba(145,158,174,0.38),
      0 1px 0 rgba(255,255,255,0.86);
    --bevel-keycap:
      inset 0 1px 0 rgba(255,255,255,0.98),
      inset 0 -1px 0 rgba(175,184,196,0.40),
      0 1.5px 0 #B6BFC9,
      0 2px 4px rgba(22,27,34,0.10);
    --bevel-keycap-pressed:
      inset 0 2px 4px rgba(10,14,20,0.32),
      inset 0 0 0 1px rgba(10,14,20,0.20),
      0 1px 0 rgba(255,255,255,0.55);
    --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    --sans: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background-color: var(--surface-chassis);
    background-image:
      url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='96' height='96'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='96' height='96' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E"),
      linear-gradient(to right, rgba(22,27,34,0.024) 1px, transparent 1px),
      linear-gradient(to bottom, rgba(22,27,34,0.024) 1px, transparent 1px);
    background-size: 96px 96px, 24px 24px, 24px 24px;
    color: var(--ink-1);
    font-family: var(--sans);
    font-size: 13.5px;
    line-height: 1.55;
    font-variant-numeric: tabular-nums;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 1180px; margin: 0 auto; padding: 18px 20px 44px; }}
  .topbar {{
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;
    margin-bottom: 14px; padding: 8px 14px;
    background: var(--surface-plate-grad);
    border: 1px solid #C6CFD9; border-radius: var(--r-plate);
    box-shadow: var(--bevel-plate);
  }}
  .brand {{ display: flex; align-items: center; gap: 8px; font-size: 13.5px; font-weight: 700; letter-spacing: -0.01em; }}
  .meta-ts {{ font-family: var(--mono); font-size: 11.5px; color: var(--ink-3); }}
  code {{ font-family: var(--mono); font-size: 11.5px; background: #ECEFF3; padding: 1px 5px; border-radius: 2px; color: var(--ink-1); }}
  .mono {{ font-family: var(--mono); }}

  /* Jewel LEDs */
  .led-dot {{
    display: inline-block; width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
    box-shadow: inset 0 1px 1px rgba(0,0,0,0.32), 0 1px 0 rgba(255,255,255,0.65);
  }}
  .led-safe {{ background: radial-gradient(circle at 32% 28%, #6EE7B7 0%, #156D50 65%, #0D4B36 100%); box-shadow: 0 0 0 2px rgba(21,109,80,0.16), 0 0 5px rgba(21,109,80,0.35); }}
  .led-alert {{ background: radial-gradient(circle at 32% 28%, #FCA5A5 0%, #C8321B 65%, #7F1D1D 100%); box-shadow: 0 0 0 2px rgba(200,50,27,0.18), 0 0 6px rgba(200,50,27,0.38); }}

  /* Plates & Wells */
  .plate {{
    background: var(--surface-plate-grad);
    border: 1px solid #C6CFD9; border-top-color: #D6DEE7; border-bottom-color: #B4BECA;
    border-radius: var(--r-plate); box-shadow: var(--bevel-plate);
    padding: 18px 20px; margin-bottom: 16px;
  }}
  .well {{
    background: var(--surface-well);
    border-radius: var(--r-well); box-shadow: var(--bevel-well);
    padding: 12px 14px;
  }}
  .plot-bed {{
    background: var(--surface-plot-bed);
    border-radius: 3px; box-shadow: var(--bevel-plot-bed);
    padding: 8px 10px;
  }}

  /* Hero Grid */
  .hero-grid {{
    display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(290px, 0.85fr);
    gap: 16px; align-items: stretch; margin-bottom: 14px;
  }}
  @media (max-width: 900px) {{ .hero-grid {{ grid-template-columns: 1fr; }} }}
  .hero-tag {{
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 3px; margin-bottom: 8px;
  }}
  .hero-tag-alert {{ background: var(--alert); color: #FFF; }}
  .hero-tag-safe {{ background: var(--safe); color: #FFF; }}
  .hero-main h1 {{ margin: 0 0 6px; font-size: 22px; line-height: 1.28; letter-spacing: -0.02em; }}
  .hero-main p {{ margin: 0 0 14px; color: var(--ink-2); font-size: 13.5px; }}
  .kpi-grid {{
    display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px;
  }}
  .kpi {{
    background: var(--surface-well); border-radius: var(--r-well); box-shadow: var(--bevel-well);
    padding: 10px 12px; border-top: 2px solid transparent;
  }}
  .kpi-safe {{ border-top-color: var(--safe); }}
  .kpi-alert {{ border-top-color: var(--alert); }}
  .kpi-warn {{ border-top-color: var(--warn); }}
  .kpi-k {{ font-size: 11px; color: var(--ink-3); font-weight: 600; margin-bottom: 2px; }}
  .kpi-v {{ font-size: 17.5px; font-weight: 700; font-family: var(--mono); letter-spacing: -0.02em; white-space: nowrap; }}
  .kpi-safe .kpi-v {{ color: var(--safe); }}
  .kpi-alert .kpi-v {{ color: var(--alert); }}
  .kpi-warn .kpi-v {{ color: var(--warn); }}
  .kpi-s {{ font-size: 11.5px; color: var(--ink-2); margin-top: 2px; }}

  /* Braun Recessed Quartz Chronometer */
  .chrono-well {{
    background: var(--surface-well); border-radius: var(--r-well); box-shadow: var(--bevel-well);
    padding: 12px 14px; display: flex; flex-direction: column; justify-content: space-between; gap: 10px;
    border-left: 3px solid var(--safe);
  }}
  .chrono-well.chrono-alert {{ border-left-color: var(--alert); }}
  .chrono-top {{ display: flex; justify-content: space-between; align-items: center; gap: 6px; }}
  .chrono-lbl {{ font-size: 11.5px; font-weight: 700; color: var(--ink-2); }}
  .chrono-alert .chrono-lbl {{ color: var(--alert); }}
  .live-pill {{
    display: inline-flex; align-items: center; gap: 5px;
    font-family: var(--mono); font-size: 10px; font-weight: 700; color: var(--ink-2);
    background: rgba(255,255,255,0.75); border: 1px solid #C2CBD5; border-radius: 3px; padding: 1.5px 6px;
  }}
  .chrono-face {{
    position: relative; overflow: hidden;
    display: flex; justify-content: space-between; align-items: center; gap: 10px;
    background: linear-gradient(180deg, #E6ECF1 0%, #F2F5F8 40%, #F8FAFC 100%);
    border: 1px solid #A9B4C2; border-top-color: #8E9BAC; border-bottom-color: #CFD7E0;
    border-radius: 3px;
    box-shadow: inset 0 3px 6px rgba(22,27,34,0.15), inset 0 1px 1px rgba(22,27,34,0.09), 0 1px 0 rgba(255,255,255,0.9);
    padding: 10px 12px;
  }}
  .chrono-face::after {{
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background: linear-gradient(112deg, rgba(255,255,255,0.48) 0%, rgba(255,255,255,0.08) 41%, transparent 41.5%);
  }}
  .chrono-digits-wrap {{ position: relative; }}
  .chrono-ghost {{
    position: absolute; inset: 0; font-family: var(--mono); font-size: 28px; font-weight: 700;
    line-height: 1; letter-spacing: -0.02em; color: rgba(22,27,34,0.055); user-select: none; pointer-events: none;
  }}
  .chrono-digits {{
    position: relative; font-family: var(--mono); font-size: 28px; font-weight: 700;
    line-height: 1; letter-spacing: -0.02em; color: var(--safe);
  }}
  .chrono-alert .chrono-digits {{ color: var(--alert); }}
  .chrono-target {{ text-align: right; font-size: 11px; color: var(--ink-3); }}
  .chrono-target strong {{ display: block; font-family: var(--mono); font-size: 12px; color: var(--ink-1); margin-top: 1px; }}
  .mv-box {{
    background: rgba(255,255,255,0.62); border: 1px solid #C8D1DC; border-radius: 3px; padding: 7px 9px;
  }}
  .mv-head {{ display: flex; justify-content: space-between; font-size: 10.5px; color: var(--ink-2); margin-bottom: 5px; }}
  .mv-track {{
    position: relative; height: 9px; border-radius: 2px; background: #E3E8EE;
    box-shadow: inset 0 1.5px 3px rgba(22,27,34,0.16);
  }}
  .mv-fill {{
    height: 100%; border-radius: 2px;
    background: repeating-linear-gradient(-45deg, #C8321B, #C8321B 4px, #DC513B 4px, #DC513B 8px);
  }}
  .mv-fill-safe {{ height: 100%; border-radius: 2px; background: linear-gradient(180deg, #1E8A67, #156D50); }}
  .mv-pin {{
    position: absolute; left: 80%; top: -3px; bottom: -3px; width: 2.5px;
    background: linear-gradient(90deg, #3A434F, #161B22); box-shadow: 1px 0 2px rgba(22,27,34,0.28);
  }}
  .mv-ticks {{ position: relative; height: 13px; font-family: var(--mono); font-size: 9.5px; color: var(--ink-3); margin-top: 3px; }}
  .mv-ticks span {{ position: absolute; top: 0; white-space: nowrap; }}
  .chrono-foot {{ display: flex; justify-content: space-between; font-size: 11px; color: var(--ink-2); }}

  /* Tactile Keycaps */
  .key-group {{
    display: inline-flex; gap: 3px; padding: 3px;
    background: var(--surface-well-deep); border-radius: var(--r-well); box-shadow: var(--bevel-well);
  }}
  .keycap {{
    appearance: none; border: 1px solid #BDC6D1; border-radius: var(--r-key);
    background: var(--surface-keycap-grad); box-shadow: var(--bevel-keycap);
    color: var(--ink-1); font-family: var(--sans); font-size: 11.5px; font-weight: 600;
    padding: 4px 10px; cursor: pointer;
    transition: transform 90ms ease, background 120ms ease, box-shadow 120ms ease;
  }}
  .keycap:active {{ transform: scale(0.97); }}
  .keycap.active {{
    background: #1B222C; color: #FFFFFF; border-color: #0E131A; box-shadow: var(--bevel-keycap-pressed);
  }}
  .keycap:focus-visible {{ outline: 2px solid var(--gemini); outline-offset: 2px; }}

  /* Section Headers & Reservoir */
  .sec-head {{
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;
    margin-bottom: 12px; padding-bottom: 9px; border-bottom: 1px solid var(--rule);
  }}
  .sec-head h2 {{ margin: 0; font-size: 15.5px; font-weight: 700; letter-spacing: -0.01em; }}
  .muted {{ font-size: 11.5px; color: var(--ink-3); }}
  .res-head {{
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;
    margin-bottom: 8px;
  }}
  .legend-strip {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; font-size: 11.5px; color: var(--ink-2); }}
  .sw {{ display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; vertical-align: middle; }}
  .sw-gemini {{ background: var(--gemini); }}
  .sw-opus {{ background: var(--opus); }}
  .sw-alert {{ background: repeating-linear-gradient(-45deg, #C8321B, #C8321B 2.5px, #E06B58 2.5px, #E06B58 5px); }}
  .sw-warn {{ background: #D97706; }}
  .res-svg {{ width: 100%; height: auto; display: block; }}
  .res-row-g {{ cursor: pointer; }}
  .res-row-g .row-hover {{ fill: transparent; transition: fill 120ms ease; }}
  .res-row-g:hover .row-hover {{ fill: rgba(28, 92, 135, 0.055); }}
  .loupe-caption {{
    margin-top: 8px; padding-top: 8px; border-top: 1px dashed #BEC8D3;
    display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
    font-size: 12px; color: var(--ink-2);
  }}

  /* Tables & Badges */
  .data-table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  .data-table th {{
    text-align: left; font-size: 11px; font-weight: 700; color: var(--ink-3);
    padding: 8px 8px; border-bottom: 1px solid var(--rule); white-space: nowrap;
  }}
  .data-table td {{ padding: 9px 8px; border-bottom: 1px solid #E5EAF0; vertical-align: middle; }}
  .data-table tr:last-child td {{ border-bottom: none; }}
  .num {{ text-align: right; font-family: var(--mono); white-space: nowrap; }}
  .pool-meta {{ font-size: 11px; color: var(--ink-3); margin-top: 2px; }}
  .badge {{
    display: inline-block; font-size: 11px; font-weight: 700; padding: 2px 7px;
    border-radius: 3px; white-space: nowrap;
  }}
  .badge-safe {{ background: var(--safe-bg); color: var(--safe); }}
  .badge-alert {{ background: var(--alert-bg); color: var(--alert); }}
  .badge-warn {{ background: var(--warn-bg); color: var(--warn); }}
  .badge-opus {{ background: #EFECE9; color: var(--opus); }}
  .badge-neutral {{ background: #EAEFF4; color: var(--ink-2); }}
  .txt-alert {{ color: var(--alert); }}
  .txt-safe {{ color: var(--safe); }}
  .txt-warn {{ color: var(--warn); }}

  /* Glass-Spectrometer Loss Breakdown */
  .forensics-well {{ margin-bottom: 12px; }}
  .fb-head {{ display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; margin-bottom: 9px; }}
  .fb-head .muted {{ margin-left: 8px; }}
  .fb-save {{ font-size: 12.5px; color: var(--safe); }}
  .spec-bar {{
    position: relative; display: flex; height: 18px; border-radius: 3px; overflow: hidden;
    background: #CBD4DE; box-shadow: inset 0 1.5px 3px rgba(22,27,34,0.22); margin-bottom: 8px;
  }}
  .spec-bar::after {{
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background: linear-gradient(180deg, rgba(255,255,255,0.40) 0%, rgba(255,255,255,0.04) 45%, rgba(0,0,0,0.14) 100%);
  }}
  .sb-seg {{ height: 100%; border-right: 1px solid rgba(255,255,255,0.45); }}
  .sb-seg:last-child {{ border-right: none; }}
  .sb-norm {{ background: var(--opus); }}
  .sb-ttl {{ background: var(--alert); }}
  .sb-sub {{ background: #D97706; }}
  .sb-legend {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 12px; color: var(--ink-2); }}
  .savings-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; margin-bottom: 12px;
  }}
  .sav-card {{
    background: var(--surface-plot-bed); border-radius: 4px; box-shadow: var(--bevel-plot-bed);
    padding: 11px 13px;
  }}
  .sav-tag {{ font-size: 10.5px; font-weight: 700; color: var(--ink-3); letter-spacing: 0.02em; }}
  .sav-title {{ font-size: 13.5px; font-weight: 700; margin: 2px 0 3px; }}
  .sav-num {{ font-family: var(--mono); font-size: 15.5px; font-weight: 700; margin-bottom: 5px; }}
  .sav-card p {{ margin: 0; font-size: 12px; color: var(--ink-2); }}

  /* Calibrated Codex Standby Gauges */
  .sub-block {{ margin-top: 16px; padding-top: 12px; border-top: 1px dashed #BEC8D3; }}
  .sub-head {{ display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }}
  .sub-head h3 {{ margin: 0; font-size: 13.5px; font-weight: 700; }}
  .codex-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px; }}
  .codex-slot {{
    background: var(--surface-well); border-radius: var(--r-well); box-shadow: var(--bevel-well);
    padding: 10px 12px;
  }}
  .cx-top {{ display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 7px; }}
  .cx-mail {{ font-family: var(--mono); font-size: 11.5px; font-weight: 700; color: var(--ink-1); overflow: hidden; text-overflow: ellipsis; }}
  .cx-bar {{
    position: relative; height: 14px; border-radius: 2px; background: #F5F8FA;
    border: 1px solid #B5C0CC; box-shadow: inset 0 1.5px 3px rgba(22,27,34,0.14);
    overflow: hidden; margin-bottom: 6px;
    background-image: repeating-linear-gradient(90deg, transparent 0 calc(25% - 1px), rgba(22,27,34,0.09) calc(25% - 1px) 25%);
  }}
  .cx-bar.open-rim {{ border-color: rgba(21,109,80,0.45); }}
  .cx-fill {{ height: 100%; }}
  .cx-fill.locked {{ background: repeating-linear-gradient(-45deg, #C8321B, #C8321B 5px, #DC513B 5px, #DC513B 10px); }}
  .cx-fill.partial {{ background: linear-gradient(180deg, #1E8A67, #156D50); }}
  .cx-empty-lbl {{
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    font-family: var(--mono); font-size: 10px; font-weight: 600; color: var(--safe);
  }}
  .cx-meta {{ display: flex; justify-content: space-between; font-size: 11px; color: var(--ink-3); font-family: var(--mono); }}

  /* Collapsible Glossary & Caveats */
  .glossary {{
    background: var(--surface-plate-grad); border: 1px solid #C6CFD9; border-radius: var(--r-plate);
    box-shadow: var(--bevel-plate); padding: 10px 16px; font-size: 12px; color: var(--ink-2);
  }}
  .glossary summary {{ cursor: pointer; font-weight: 700; color: var(--ink-1); }}
  .glossary-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px;
    margin: 12px 0 4px;
  }}
  .glossary dt {{ font-weight: 700; color: var(--ink-1); margin-bottom: 3px; }}
  .glossary dd {{ margin: 0; font-size: 11.5px; color: var(--ink-2); }}
  .warn-block {{ margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--rule); }}
  .warn-block ul {{ margin: 6px 0 0; padding-left: 18px; }}
  .warn-block li {{ margin-bottom: 3px; font-family: var(--mono); font-size: 11px; }}
  .foot {{
    margin-top: 14px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
    font-size: 11px; color: var(--ink-3); font-family: var(--mono);
  }}
  @media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ transition: none !important; animation: none !important; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="brand">
      <span class="led-dot {led_cls}"></span>
      <span>AI 配额精密决策台</span>
      <code>ai-quota-calibrator</code>
    </div>
    <div class="meta-ts">实时观测：{_esc(observed)} · 数据源：{_esc(provider)}</div>
  </div>

  <!-- BLOCK 1: LIVE DECISION + QUARTZ CHRONOMETER + 1:N RESERVOIR & OPTICAL LOUPE -->
  <section class="plate">
    <div class="hero-grid">
      <div class="hero-main">
        <div class="hero-tag {'hero-tag-alert' if any_locked else 'hero-tag-safe'}">{banner_tag}</div>
        <h1>{_esc(headline)}</h1>
        <p>{_esc(subline)}</p>
        <div class="kpi-grid">{kpi_html}</div>
      </div>
      {chrono_html}
    </div>

    {reservoir_well_html}
  </section>

  {forensics_section_html}

  {routing_section_html}

  <details class="glossary">
    <summary>口径说明与本次校准提示（4 项核心口径 · {len(all_warnings)} 条实时提示）</summary>
    <dl class="glossary-grid">
      <div>
        <dt>1:N 真实物理尺度 + 光学放大镜</dt>
        <dd>每条校准成功的液管严格从 0 基线按隐含 API 美元上限等比绘制（Lie Factor = 1.00，零 min-width 虚胖）；点击任意液管可在下方拉丝铝放大镜中全宽检视百分比与 99% 预扣线。</dd>
      </div>
      <div>
        <dt>1% 预扣软锁死（SOFT_LOCKOUT）</dt>
        <dd>Antigravity 单次请求发出前临时预扣 1%（0.01）配额，余量跌破 1% 即触发软锁死无法发起新请求。</dd>
      </div>
      <div>
        <dt>5 分钟缓存过期 20× 冷重传（TTL Miss）</dt>
        <dd>当 250k+ 长上下文静置超 5 分钟后 Prompt Cache 失效，下一轮须按 $4/M 全价输入重传（缓存读 $0.20/M 的 20 倍），单轮即可多花 $1.3–$1.5。</dd>
      </div>
      <div>
        <dt>跨整点刷新防误算（MID_HOUR_RESET_OVERCOUNT）</dt>
        <dd>5 小时窗口刚在非整点刷新时，小时级账单会混入重置前消耗；当朴素反推的 5h 上限超过周池上限时自动扣留美元外推，仅展示准确剩余 %。</dd>
      </div>
    </dl>
    {warnings_ul}
  </details>

  <div class="foot">
    <span>由 ai-quota-calibrator 实时生成 · 零外链 CDN · 离线单文件</span>
    <span>任意时刻运行即基于当下实时配额与本地日志重算</span>
  </div>
</div>

<script>
(function () {{
  const DATA = {_safe_json_for_script(client_payload)};
  const SVG_NS = "http://www.w3.org/2000/svg";

  function elSvg(tag, attrs, parent) {{
    const el = document.createElementNS(SVG_NS, tag);
    if (attrs) {{
      for (const [k, v] of Object.entries(attrs)) {{
        if (v !== null && v !== undefined) el.setAttribute(k, String(v));
      }}
    }}
    if (parent) parent.appendChild(el);
    return el;
  }}

  function fmtUsd(v, d) {{
    if (v === null || v === undefined) return "待校准";
    if (d === 0) return "$" + Math.round(v).toLocaleString();
    return "$" + Number(v).toLocaleString(undefined, {{ minimumFractionDigits: d, maximumFractionDigits: d }});
  }}

  /* 1. Live Quartz Chronometer (graceful post-reset freeze) */
  (function initChronometer() {{
    const c = DATA.chrono;
    const digitsEl = document.getElementById("quartzClock");
    const ghostEl = document.getElementById("quartzGhost");
    const modeEl = document.getElementById("liveModeTxt");
    const tagEl = document.getElementById("chronoTag");
    if (!c || !digitsEl || !c.resetIso) {{
      if (modeEl) modeEl.textContent = "静态快照";
      return;
    }}
    const resetMs = Date.parse(c.resetIso);
    if (Number.isNaN(resetMs)) {{
      if (modeEl) modeEl.textContent = "静态快照";
      return;
    }}

    function pad2(n) {{ return String(Math.max(0, Math.floor(n))).padStart(2, "0"); }}
    function tick() {{
      const remSec = Math.floor((resetMs - Date.now()) / 1000);
      if (remSec > 0 && remSec <= (c.ttrSec || 0) + 120) {{
        const h = Math.floor(remSec / 3600);
        const m = Math.floor((remSec % 3600) / 60);
        const s = remSec % 60;
        digitsEl.textContent = pad2(h) + ":" + pad2(m) + ":" + pad2(s);
        if (ghostEl) ghostEl.textContent = h >= 100 ? "888:88:88" : "88:88:88";
        if (modeEl) modeEl.textContent = "LIVE 实时";
      }} else if (remSec <= 0) {{
        digitsEl.textContent = "00:00:00";
        if (ghostEl) ghostEl.textContent = "88:88:88";
        if (modeEl) modeEl.textContent = "已到重置点";
        if (tagEl) tagEl.textContent = "重跑刷新";
      }}
    }}
    tick();
    window.setInterval(tick, 1000);
  }})();

  /* 2. Live 1:N Borosilicate Reservoir + Interactive Optical Magnification Loupe */
  let scaleMode = "true";
  let selectedIdx = Math.min(DATA.defaultLoupeIdx || 0, Math.max(0, DATA.pools.length - 1));

  function renderReservoir() {{
    const host = document.getElementById("reservoirHost");
    const capEl = document.getElementById("loupeCaption");
    const titleEl = document.getElementById("resTitle");
    if (!host || !DATA.pools.length) return;
    host.textContent = "";

    const pools = DATA.pools;
    const n = pools.length;
    const W = 1100;
    const L = 188, R = 178;
    const trackW = W - L - R;
    const rowH = 38;
    const barH = 22;
    const topY = 26;
    const beamGap = 42;
    const loupeH = 34;
    const loupeY = topY + n * rowH + beamGap;
    const H = loupeY + loupeH + 26;

    const maxCap = DATA.maxCap > 0 ? DATA.maxCap : 1;
    const sel = pools[selectedIdx] || pools[0];
    if (titleEl) {{
      titleEl.textContent = scaleMode === "norm" ? "单池 100% 归一化水位槽" : "1:N 真实物理尺度储液槽";
    }}

    const svg = elSvg("svg", {{ viewBox: `0 0 ${{W}} ${{H}}`, class: "res-svg", role: "img", "aria-label": "配额池物理比例储液槽与光学放大镜" }}, host);
    const defs = elSvg("defs", null, svg);

    // Borosilicate glass cylinder sheen & fluid gradients
    const gTrough = elSvg("linearGradient", {{ id: "troughGrad", x1: "0", y1: "0", x2: "0", y2: "1" }}, defs);
    elSvg("stop", {{ offset: "0%", "stop-color": "#D4DCE4" }}, gTrough);
    elSvg("stop", {{ offset: "30%", "stop-color": "#EEF2F6" }}, gTrough);
    elSvg("stop", {{ offset: "100%", "stop-color": "#F7F9FB" }}, gTrough);

    const gSheen = elSvg("linearGradient", {{ id: "glassSheen", x1: "0", y1: "0", x2: "0", y2: "1" }}, defs);
    elSvg("stop", {{ offset: "0%", "stop-color": "#FFFFFF", "stop-opacity": "0.52" }}, gSheen);
    elSvg("stop", {{ offset: "24%", "stop-color": "#FFFFFF", "stop-opacity": "0.22" }}, gSheen);
    elSvg("stop", {{ offset: "45%", "stop-color": "#FFFFFF", "stop-opacity": "0.0" }}, gSheen);
    elSvg("stop", {{ offset: "100%", "stop-color": "#0E141B", "stop-opacity": "0.20" }}, gSheen);

    const gGem = elSvg("linearGradient", {{ id: "gemFluid", x1: "0", y1: "0", x2: "0", y2: "1" }}, defs);
    elSvg("stop", {{ offset: "0%", "stop-color": "#246E9E" }}, gGem);
    elSvg("stop", {{ offset: "55%", "stop-color": "#1C5C87" }}, gGem);
    elSvg("stop", {{ offset: "100%", "stop-color": "#134263" }}, gGem);

    const gOpus = elSvg("linearGradient", {{ id: "opusFluid", x1: "0", y1: "0", x2: "0", y2: "1" }}, defs);
    elSvg("stop", {{ offset: "0%", "stop-color": "#695A4F" }}, gOpus);
    elSvg("stop", {{ offset: "55%", "stop-color": "#52463D" }}, gOpus);
    elSvg("stop", {{ offset: "100%", "stop-color": "#3B312A" }}, gOpus);

    const gAlum = elSvg("linearGradient", {{ id: "alumBezel", x1: "0", y1: "0", x2: "0", y2: "1" }}, defs);
    elSvg("stop", {{ offset: "0%", "stop-color": "#F1F4F8" }}, gAlum);
    elSvg("stop", {{ offset: "48%", "stop-color": "#D4DCE5" }}, gAlum);
    elSvg("stop", {{ offset: "100%", "stop-color": "#B8C3CF" }}, gAlum);

    const gBolt = elSvg("linearGradient", {{ id: "steelBolt", x1: "0", y1: "0", x2: "1", y2: "0" }}, defs);
    elSvg("stop", {{ offset: "0%", "stop-color": "#5A6574" }}, gBolt);
    elSvg("stop", {{ offset: "50%", "stop-color": "#F4F7FA" }}, gBolt);
    elSvg("stop", {{ offset: "100%", "stop-color": "#262E38" }}, gBolt);

    const pLock = elSvg("pattern", {{ id: "patLock", width: "8", height: "8", patternUnits: "userSpaceOnUse", patternTransform: "rotate(-45)" }}, defs);
    elSvg("rect", {{ width: "8", height: "8", fill: "#C8321B" }}, pLock);
    elSvg("line", {{ x1: "0", y1: "0", x2: "0", y2: "8", stroke: "rgba(255,255,255,0.28)", "stroke-width": "2.4" }}, pLock);

    const pWarn = elSvg("pattern", {{ id: "patWarn", width: "8", height: "8", patternUnits: "userSpaceOnUse", patternTransform: "rotate(-45)" }}, defs);
    elSvg("rect", {{ width: "8", height: "8", fill: "#FEF4E4" }}, pWarn);
    elSvg("line", {{ x1: "0", y1: "0", x2: "0", y2: "8", stroke: "rgba(180,83,9,0.24)", "stroke-width": "2" }}, pWarn);

    const beamCol = sel.locked ? "#C8321B" : (sel.groupKey === "gemini" ? "#1C5C87" : "#52463D");
    const gBeam = elSvg("linearGradient", {{ id: "beamGrad", x1: "0", y1: "0", x2: "0", y2: "1" }}, defs);
    elSvg("stop", {{ offset: "0%", "stop-color": beamCol, "stop-opacity": "0.18" }}, gBeam);
    elSvg("stop", {{ offset: "100%", "stop-color": beamCol, "stop-opacity": "0.035" }}, gBeam);

    // Top Ruler
    if (scaleMode === "true" && DATA.maxCap > 0) {{
      const ticks = [0, 0.25, 0.5, 0.75, 1.0];
      ticks.forEach((f) => {{
        const tx = L + f * trackW;
        elSvg("line", {{ x1: tx, x2: tx, y1: topY - 8, y2: topY - 3, stroke: "#9BA6B4" }}, svg);
        const t = elSvg("text", {{
          x: tx, y: topY - 12, "text-anchor": f === 0 ? "start" : (f === 1 ? "end" : "middle"),
          fill: "#6B7280", "font-family": "var(--mono)", "font-size": "10"
        }}, svg);
        t.textContent = "$" + Math.round(f * maxCap).toLocaleString();
      }});
    }} else {{
      [0, 25, 50, 75, 100].forEach((pct) => {{
        const tx = L + (pct / 100) * trackW;
        elSvg("line", {{ x1: tx, x2: tx, y1: topY - 8, y2: topY - 3, stroke: "#9BA6B4" }}, svg);
        const t = elSvg("text", {{
          x: tx, y: topY - 12, "text-anchor": pct === 0 ? "start" : (pct === 100 ? "end" : "middle"),
          fill: "#6B7280", "font-family": "var(--mono)", "font-size": "10"
        }}, svg);
        t.textContent = pct + "%";
      }});
    }}

    // Compute exact tube geometry (Lie Factor = 1.00!)
    function tubeWidthFor(p) {{
      if (scaleMode === "norm") return trackW;
      if (p.capUsd !== null && DATA.maxCap > 0) return Math.max(0, (p.capUsd / maxCap) * trackW);
      return 0;
    }}

    // Optical refraction beam from selected row down to machined loupe
    const selY = topY + selectedIdx * rowH;
    const selTubeW = tubeWidthFor(sel) || trackW;
    const beamX2 = L + Math.max(4, selTubeW);
    elSvg("polygon", {{
      points: `${{L}},${{selY + barH}} ${{beamX2}},${{selY + barH}} ${{L + trackW}},${{loupeY - 3}} ${{L}},${{loupeY - 3}}`,
      fill: "url(#beamGrad)"
    }}, svg);
    elSvg("line", {{ x1: L, y1: selY + barH, x2: L, y2: loupeY - 3, stroke: beamCol, "stroke-opacity": "0.42", "stroke-dasharray": "4,3" }}, svg);
    elSvg("line", {{ x1: beamX2, y1: selY + barH, x2: L + trackW, y2: loupeY - 3, stroke: beamCol, "stroke-opacity": "0.42", "stroke-dasharray": "4,3" }}, svg);

    // Draw each pool row
    pools.forEach((p, idx) => {{
      const y = topY + idx * rowH;
      const isSel = idx === selectedIdx;
      const g = elSvg("g", {{
        class: "res-row-g",
        tabindex: "0",
        role: "button",
        "aria-label": `${{p.name}} (${{p.window}}) 已用 ${{p.usedPct.toFixed(1)}}%，点击在放大镜中检视`
      }}, svg);
      g.addEventListener("click", () => {{ selectedIdx = idx; renderReservoir(); }});
      g.addEventListener("keydown", (ev) => {{
        if (ev.key === "Enter" || ev.key === " ") {{ ev.preventDefault(); selectedIdx = idx; renderReservoir(); }}
      }});

      elSvg("rect", {{ class: "row-hover", x: 0, y: y - 5, width: W, height: barH + 10, rx: 3 }}, g);
      if (isSel) {{
        elSvg("rect", {{ x: 2, y: y - 4, width: 174, height: barH + 8, rx: 3, fill: p.locked ? "rgba(200,50,27,0.08)" : "rgba(28,92,135,0.08)" }}, g);
        elSvg("rect", {{ x: 2, y: y - 4, width: 3, height: barH + 8, rx: 1.5, fill: p.locked ? "#C8321B" : (p.groupKey === "gemini" ? "#1C5C87" : "#52463D") }}, g);
      }}

      const nameEl = elSvg("text", {{ x: 12, y: y + 10, fill: isSel ? "#161B22" : "#374151", "font-size": "12", "font-weight": isSel ? "700" : "600" }}, g);
      nameEl.textContent = p.name;
      const subEl = elSvg("text", {{ x: 12, y: y + 22, fill: "#6B7280", "font-family": "var(--mono)", "font-size": "10" }}, g);
      subEl.textContent = `${{p.window}} · ${{p.confidence}}`;

      // Full background trough
      elSvg("rect", {{ x: L, y: y, width: trackW, height: barH, rx: 2.5, fill: "url(#troughGrad)", stroke: "#D5DDE6" }}, g);

      const tW = tubeWidthFor(p);
      if (tW > 0 && (p.capUsd !== null || scaleMode === "norm")) {{
        const fillW = (p.usedPct / 100) * tW;
        const fillPaint = p.locked
          ? "url(#patLock)"
          : (p.overcount ? "rgba(217,119,6,0.45)" : (p.groupKey === "gemini" ? "url(#gemFluid)" : "url(#opusFluid)"));
        elSvg("rect", {{
          class: "true-cap-tube", x: L, y: y, width: tW.toFixed(2), height: barH, rx: 2.5,
          fill: p.overcount ? "url(#patWarn)" : "#FFFFFF",
          stroke: isSel ? (p.locked ? "#C8321B" : "#161B22") : (p.overcount ? "#D97706" : "#8D99A8"),
          "stroke-width": isSel ? "1.6" : "1.1"
        }}, g);
        if (fillW > 0) {{
          elSvg("rect", {{ x: L, y: y, width: fillW.toFixed(2), height: barH, rx: 2, fill: fillPaint }}, g);
          if (fillW >= 3 && !p.overcount) {{
            // Strict Lie Factor = 1.00 interior concave meniscus
            elSvg("rect", {{ x: (L + fillW - 2).toFixed(2), y: y + 1, width: "1", height: barH - 2, fill: "rgba(255,255,255,0.62)" }}, g);
            elSvg("rect", {{ x: (L + fillW - 1).toFixed(2), y: y + 1, width: "1", height: barH - 2, fill: "rgba(15,20,28,0.34)" }}, g);
          }}
        }}
        elSvg("rect", {{ x: L, y: y, width: tW.toFixed(2), height: barH, rx: 2.5, fill: "url(#glassSheen)", "pointer-events": "none" }}, g);

        let callout = "";
        if (p.capUsd !== null) {{
          const capTxt = (p.capUpperUsd && Math.abs(p.capUpperUsd - p.capUsd) > 1.0)
            ? `${{fmtUsd(p.capUsd, 0)}}–${{fmtUsd(p.capUpperUsd, 0)}}`
            : (p.capUsd < 100 ? fmtUsd(p.capUsd, 2) : fmtUsd(p.capUsd, 0));
          const multTxt = (p.ratioVsMin && p.ratioVsMin > 1.05) ? ` · ${{p.ratioVsMin}}×` : "";
          callout = scaleMode === "norm"
            ? `已用 ${{p.usedPct.toFixed(1)}}% · ${{p.spendUsd !== null ? fmtUsd(p.spendUsd, 2) : "—"}} / ${{capTxt}}`
            : `${{capTxt}}${{multTxt}} · 已用 ${{p.usedPct.toFixed(1)}}%`;
        }} else if (p.overcount) {{
          callout = `已用 ${{p.usedPct.toFixed(1)}}% · 跨整点刷新暂不外推美元上限`;
        }} else if (p.untouched) {{
          callout = `已用 ${{p.usedPct.toFixed(1)}}% · 满额未用 (尚无花费可反推上限)`;
        }} else if (p.locked) {{
          callout = `已用 ${{p.usedPct.toFixed(1)}}% · 已锁死 (未校准美元上限)`;
        }} else {{
          callout = `已用 ${{p.usedPct.toFixed(1)}}% · 尚无有效美元上限 (待校准)`;
        }}

        const placeInside = scaleMode === "norm" || tW > trackW - 230;
        let txtX = L + tW + 10;
        let txtFill = p.locked ? "#C8321B" : (p.overcount ? "#B45309" : (p.groupKey === "gemini" ? "#1C5C87" : "#161B22"));
        if (placeInside) {{
          if (tW - fillW >= 240) {{
            txtX = L + fillW + 10;
          }} else if (fillW >= 240 && !p.overcount) {{
            txtX = L + 10;
            txtFill = "#FFFFFF";
          }} else {{
            txtX = L + 10;
            if (fillW > 180 && !p.overcount) txtFill = "#FFFFFF";
          }}
        }}
        const cEl = elSvg("text", {{ x: txtX, y: y + 14.5, fill: txtFill, "font-family": "var(--mono)", "font-size": "10.5", "font-weight": "700" }}, g);
        cEl.textContent = callout;
      }} else {{
        // Honest uncalibrated / mid-hour reset / untouched / uncalibrated-locked slot (zero fabricated USD bar!)
        const fillPaint = p.overcount ? "url(#patWarn)" : (p.locked ? "#FDECE9" : "#EDF2F7");
        const strokeCol = p.overcount ? "#D97706" : (p.locked ? "#C8321B" : (p.untouched ? "#156D50" : "#8D99A8"));
        elSvg("rect", {{ x: L, y: y, width: trackW, height: barH, rx: 2.5, fill: fillPaint, stroke: strokeCol, "stroke-dasharray": "4,3" }}, g);
        const pctW = (p.usedPct / 100) * trackW;
        if (pctW > 0) {{
          const subFill = p.locked
            ? "url(#patLock)"
            : (p.overcount ? "rgba(217,119,6,0.22)" : (p.untouched ? "rgba(21,109,80,0.18)" : "rgba(75,85,99,0.20)"));
          elSvg("rect", {{ x: L, y: y, width: pctW.toFixed(2), height: barH, rx: 2, fill: subFill }}, g);
        }}
        let noteTxt = `已用 ${{p.usedPct.toFixed(1)}}% · 尚无有效美元上限 (待校准)`;
        let noteFill = "#4B5563";
        if (p.overcount) {{
          noteTxt = `刚刷新已用 ${{p.usedPct.toFixed(1)}}% · 跨整点刷新暂不外推美元上限`;
          noteFill = "#B45309";
        }} else if (p.untouched) {{
          noteTxt = `满额未用 (0.0%) · 尚无花费可反推上限`;
          noteFill = "#156D50";
        }} else if (p.locked) {{
          noteTxt = `已用 ${{p.usedPct.toFixed(1)}}% · 已锁死 (未校准美元上限)`;
          noteFill = pctW >= 240 ? "#FFFFFF" : "#C8321B";
        }}
        const note = elSvg("text", {{ x: L + 10, y: y + 14.5, fill: noteFill, "font-family": "var(--mono)", "font-size": "10.5", "font-weight": "700" }}, g);
        note.textContent = noteTxt;
      }}

      // Right-hand remaining readout
      const rTop = elSvg("text", {{
        x: W - 8, y: y + 10, "text-anchor": "end",
        fill: p.locked ? "#C8321B" : "#156D50", "font-family": "var(--mono)", "font-size": "11.5", "font-weight": "700"
      }}, g);
      rTop.textContent = p.locked
        ? "⊘ $0 · 锁死"
        : (p.remUsd !== null ? `余 ${{fmtUsd(p.remUsd, 0)}} (${{p.remPct.toFixed(1)}}%)` : `余 ${{p.remPct.toFixed(1)}}%`);
      const rSub = elSvg("text", {{
        x: W - 8, y: y + 22, "text-anchor": "end",
        fill: "#6B7280", "font-family": "var(--mono)", "font-size": "9.5"
      }}, g);
      rSub.textContent = `重置 ${{p.ttr}}`;
    }});

    // Machined Brushed-Aluminum Optical Magnification Loupe
    const mag = (scaleMode === "true" && sel.capUsd && DATA.maxCap > 0)
      ? (maxCap / sel.capUsd)
      : 1.0;
    const magStr = mag > 1.05 ? `${{mag.toFixed(1)}}×` : "1.0×";

    const lName = elSvg("text", {{ x: 12, y: loupeY + 14, fill: sel.locked ? "#C8321B" : "#161B22", "font-size": "11.5", "font-weight": "700" }}, svg);
    lName.textContent = `光学放大检视 (${{magStr}})`;
    const lSub = elSvg("text", {{ x: 12, y: loupeY + 27, fill: "#6B7280", "font-size": "10.5" }}, svg);
    lSub.textContent = `${{sel.name}} (${{sel.window}})`;

    // 3px machined outer bezel
    elSvg("rect", {{ x: L - 3, y: loupeY - 3, width: trackW + 6, height: loupeH + 6, rx: 4.5, fill: "url(#alumBezel)", stroke: "#94A0AE" }}, svg);
    elSvg("rect", {{ x: L, y: loupeY, width: trackW, height: loupeH, rx: 2.5, fill: "#FFFFFF", stroke: "#B5C0CC" }}, svg);

    const loupeFillW = (sel.usedPct / 100) * trackW;
    const loupePaint = sel.locked ? "url(#patLock)" : (sel.groupKey === "gemini" ? "url(#gemFluid)" : "url(#opusFluid)");
    if (loupeFillW > 0) {{
      elSvg("rect", {{ x: L, y: loupeY, width: loupeFillW.toFixed(2), height: loupeH, rx: 2, fill: loupePaint }}, svg);
      if (loupeFillW >= 3) {{
        elSvg("rect", {{ x: (L + loupeFillW - 2).toFixed(2), y: loupeY + 1, width: "1", height: loupeH - 2, fill: "rgba(255,255,255,0.65)" }}, svg);
        elSvg("rect", {{ x: (L + loupeFillW - 1).toFixed(2), y: loupeY + 1, width: "1", height: loupeH - 2, fill: "rgba(15,20,28,0.38)" }}, svg);
      }}
    }}
    elSvg("rect", {{ x: L, y: loupeY, width: trackW, height: loupeH, rx: 2.5, fill: "url(#glassSheen)", "pointer-events": "none" }}, svg);

    // 99.0% pre-reservation lock-pin: machined steel bolt ONLY when locked, quiet dashed line when healthy!
    const lockX = L + 0.99 * trackW;
    if (sel.locked) {{
      elSvg("rect", {{ x: (lockX - 1.5).toFixed(1), y: loupeY - 6, width: "3", height: loupeH + 12, rx: "1", fill: "url(#steelBolt)" }}, svg);
      elSvg("circle", {{ cx: lockX.toFixed(1), cy: loupeY - 7, r: "4", fill: "#C8321B", stroke: "#7F1D1D", "stroke-width": "0.8" }}, svg);
      const bx = lockX - 182, by = loupeY - 26;
      elSvg("rect", {{ x: bx, y: by, width: "172", height: "18", rx: "3", fill: "#FFFFFF", stroke: "#C8321B", "stroke-width": "1" }}, svg);
      elSvg("line", {{ x1: bx + 172, y1: by + 9, x2: lockX - 4, y2: loupeY - 7, stroke: "#C8321B", "stroke-width": "1.1" }}, svg);
      const bt = elSvg("text", {{ x: bx + 86, y: by + 12.5, "text-anchor": "middle", fill: "#C8321B", "font-family": "var(--mono)", "font-size": "9.5", "font-weight": "700" }}, svg);
      bt.textContent = "⊘ 99.0% 预扣物理锁销 (剩 1% 停)";
    }} else {{
      elSvg("line", {{ x1: lockX, x2: lockX, y1: loupeY - 3, y2: loupeY + loupeH + 3, stroke: "#8D99A8", "stroke-dasharray": "3,2" }}, svg);
      const lt = elSvg("text", {{ x: lockX - 5, y: loupeY - 7, "text-anchor": "end", fill: "#6B7280", "font-family": "var(--mono)", "font-size": "9.5" }}, svg);
      lt.textContent = "99% 预扣线";
    }}

    const lLabelStr = sel.capUsd !== null
      ? `已用 ${{sel.usedPct.toFixed(2)}}% · ${{sel.spendUsd !== null ? fmtUsd(sel.spendUsd, 2) : "—"}} / ${{fmtUsd(sel.capUsd, 2)}}`
      : `已用 ${{sel.usedPct.toFixed(2)}}% · 剩余 ${{sel.remPct.toFixed(2)}}%`;
    let lTxtX = L + 10;
    let lTxtFill = "#161B22";
    if (loupeFillW >= 300) {{
      lTxtX = L + 10;
      lTxtFill = "#FFFFFF";
    }} else if (trackW - loupeFillW >= 300) {{
      lTxtX = L + loupeFillW + 10;
      lTxtFill = sel.locked ? "#C8321B" : (sel.groupKey === "gemini" ? "#1C5C87" : "#161B22");
    }}
    const lTxt = elSvg("text", {{
      x: lTxtX, y: loupeY + 21,
      fill: lTxtFill,
      "font-family": "var(--mono)", "font-size": "11.5", "font-weight": "700"
    }}, svg);
    lTxt.textContent = lLabelStr;

    // Bottom 0%-100% scale ticks under loupe
    [0, 25, 50, 75, 100].forEach((pct) => {{
      const tx = L + (pct / 100) * trackW;
      const t = elSvg("text", {{
        x: tx, y: loupeY + loupeH + 16, "text-anchor": pct === 0 ? "start" : (pct === 100 ? "end" : "middle"),
        fill: "#6B7280", "font-family": "var(--mono)", "font-size": "9.5"
      }}, svg);
      t.textContent = pct + "%";
    }});

    const lRightTop = elSvg("text", {{
      x: W - 8, y: loupeY + 14, "text-anchor": "end",
      fill: sel.locked ? "#C8321B" : "#156D50", "font-family": "var(--mono)", "font-size": "12", "font-weight": "700"
    }}, svg);
    lRightTop.textContent = sel.locked ? `余 ${{sel.remPct.toFixed(2)}}% (锁死)` : (sel.remUsd !== null ? `余 ${{sel.remPct.toFixed(1)}}% (${{fmtUsd(sel.remUsd, 0)}})` : `余 ${{sel.remPct.toFixed(1)}}%`);
    const lRightSub = elSvg("text", {{
      x: W - 8, y: loupeY + 27, "text-anchor": "end",
      fill: "#6B7280", "font-size": "10.5"
    }}, svg);
    lRightSub.textContent = sel.locked ? `${{sel.resetShort}} 解锁` : (sel.remMsgs ? `约可跑 ${{sel.remMsgs.toLocaleString()}} 轮` : `重置 ${{sel.ttr}}`);

    // Caption underneath loupe (textContent only — zero XSS!)
    if (capEl) {{
      capEl.textContent = "";
      const leftSpan = document.createElement("span");
      const rightSpan = document.createElement("span");
      rightSpan.className = "mono";
      if (sel.overcount) {{
        leftSpan.textContent = `当前检视：${{sel.name}} (${{sel.window}}) — 刚于窗口内刷新，小时账单含重置前消耗，暂仅展示准确剩余比例 (${{sel.remPct.toFixed(1)}}%)。`;
      }} else if (sel.capUsd !== null && DATA.maxCap > 0 && scaleMode === "true") {{
        leftSpan.textContent = `物理尺度真相：${{sel.name}} (${{sel.window}}) 隐含上限 ${{fmtUsd(sel.capUsd, 2)}}，占最大池的 ${{sel.pctOfMax.toFixed(2)}}% (${{magStr}} 放大检视)，当前已用 ${{sel.usedPct.toFixed(2)}}%。`;
      }} else {{
        leftSpan.textContent = `当前检视：${{sel.name}} (${{sel.window}})，已用 ${{sel.usedPct.toFixed(2)}}%，剩余 ${{sel.remPct.toFixed(2)}}%${{sel.remUsd !== null ? "（约 " + fmtUsd(sel.remUsd, 2) + "）" : ""}}。`;
      }}
      rightSpan.textContent = "点击上方任一液管切换检视";
      capEl.appendChild(leftSpan);
      capEl.appendChild(rightSpan);
    }}
  }}

  document.querySelectorAll("[data-scale]").forEach((btn) => {{
    btn.addEventListener("click", () => {{
      scaleMode = btn.dataset.scale;
      document.querySelectorAll("[data-scale]").forEach((b) => {{
        const on = b === btn;
        b.classList.toggle("active", on);
        b.setAttribute("aria-pressed", String(on));
      }});
      renderReservoir();
    }});
  }});
  renderReservoir();
}})();
</script>
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
