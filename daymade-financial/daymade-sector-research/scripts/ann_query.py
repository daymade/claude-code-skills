#!/usr/bin/env python3
"""A股上市公司公告窗口查询（stdlib only）。

数据链（2026-08-13 医药 Top10 公告检索实战验证；北交所通道同日修正并实测）:
    巨潮 cninfo hisAnnouncement（沪深 + 北交所统一主源；北交所 orgId 为 gfbj+补零代码）
    -> 东方财富 np-anotice-stock（交叉验证 + 公告类型回填 + 独有条目并集）

调用（国内站点，必须去除代理环境变量）:
    env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
      python3 ann_query.py --codes 002219,600613,920946 --end 2026-08-13 --out-dir /path/out

已验证陷阱（全部来自 2026-08-13 实战，勿再踩）:
    - orgId 一律用 topSearch 接口返回值，禁止按市场自拼：深市存在两种形态
      （gssz+补零如 000001 -> gssz0000001；9900xxxxxx 如 002219 -> 9900004301），
      沪市 600613 -> gssh0600613（前导零位置易拼错，自拼 gssh6000613 实测 0 条），
      科创板 688265 -> gfbj0839728（数字部分与代码无关）。自拼必踩假阴。
    - column 参数 sse/szse 实测对查询结果无影响（同 orgId 交叉测试结果相同），
      按市场填写即可。
    - 北交所（43/83/87/92 开头）巨潮覆盖：topSearch 返回 gfbj 前缀 orgId
      （实测 920946 -> gfbj0830946），与沪深同一查询通道；bse.cn 官网接口实测不可用
      （companyCd 被服务端忽略、返回全市场公告流），勿再试。
    - B 股（900/200 开头）公告挂在对应 A 股代码下：巨潮与东财的 stock 参数都不
      接受 B 股代码（900904/200028 实测恒 0 条）。topSearch 对 B 股代码返回的
      orgId 是其 A 股公司的（gssh/gssz 前缀 + A 股代码 7 位补零），反推 A 股代码
      查询（900904 -> 600613、200028 -> 000028，均实测）。
    - 月窗口 0 条必须扩宽窗验证是「真无公告」还是参数错（0 条双向读）：
      判据 = 宽窗最新公告日期是否落在月窗内（落在月窗内 = 参数/orgId 错；早于月窗
      起点 = 真无公告，如实写「该标的近一月无公告」，不编造公告）。
    - 两源覆盖不完全一致：部分公告类型仅其中一源有（如 002437 的 07-23 投资者
      关系管理信息仅东财有；920946 的 05-14 投资者关系活动记录表巨潮有收录，在
      90 天宽窗之外、约 135 天窗口可得），东财独有条目补并集，不因主源没有而漏掉。
    - announcementTime 是毫秒时间戳，按北京时间（UTC+8）换算。
    - 巨潮 announcementTypeName 常为 null，类型用东财 column_name 按「日期+标题」
      匹配回填（全/半角括号归一化后比对）。
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BJ_TZ = timezone(timedelta(hours=8))

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
CNINFO_QUERY = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_TOPS = "http://www.cninfo.com.cn/new/information/topSearch/query"
EM_ANN = "https://np-anotice-stock.eastmoney.com/api/security/ann"


def _request(req, timeout, retries):
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:  # 公开公告接口偶发断连，重试
            last = e
            time.sleep(1 + attempt)
    raise last


def http_post(url, data, headers=None, timeout=20, retries=3):
    body = urllib.parse.urlencode(data)
    req = urllib.request.Request(url, data=body.encode("utf-8"),
                                 headers=headers or {"User-Agent": UA})
    return _request(req, timeout, retries)


def http_get(url, headers=None, timeout=20, retries=3):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    return _request(req, timeout, retries)


def market_of(code):
    if code.startswith("900"):
        return "sh"  # 沪 B：公告查询另见 b_share_a_code（巨潮/东财均不接受 B 股代码）
    if code.startswith(("4", "8", "9")):
        return "bj"
    if code.startswith("6"):
        return "sh"
    return "sz"  # 含 200 深 B


def norm_title(t):
    """标题归一化：去全/半角括号差异 + 去空格 + 剥离东财「公司名:」前缀。"""
    t = t.replace("（", "(").replace("）", ")")
    t = "".join(t.split())
    colon = max(t.find(":"), t.find("："))
    if colon > 0 and colon < len(t) - 1:
        t = t[colon + 1:]
    return t


def date_near(d1, d2, days=1):
    """两源日期匹配：实测样本多为同日；保留 ±1 天容差防两源口径偶发差异。"""
    dt1 = datetime.strptime(d1, "%Y-%m-%d")
    dt2 = datetime.strptime(d2, "%Y-%m-%d")
    return abs((dt1 - dt2).days) <= days


def match_em(em_items, date, title):
    """在东财列表里按「日期(±1天) + 归一化标题」找对应条目。"""
    for e in em_items:
        if date_near(e["date"], date) and norm_title(e["title"]) == norm_title(title):
            return e
    return None


def topsearch_orgid(code):
    """巨潮真实 orgId（全市场一律 topSearch，禁自拼——深市双形态、沪市前导零
    位置、科创板 gfbj 数字部分均无法可靠自拼，实测自拼必踩假阴）。"""
    data = json.loads(http_post(CNINFO_TOPS, {
        "keyWord": code, "maxNum": 10,
    }))
    for item in (data or []):
        if str(item.get("code", "")).startswith(code):
            return item.get("orgId")
    return None


def b_share_a_code(code, orgid):
    """B 股公告挂在对应 A 股代码下：巨潮与东财的 stock 参数都不接受 B 股代码
    （900904/200028 实测恒 0 条），须用 A 股代码查询。
    topSearch 对 B 股代码返回的 orgId 是其 A 股公司的，沪/深 B 的 orgId 为
    gssh/gssz 前缀 + A 股代码 7 位补零，反推可得 A 股代码
    （900904 -> gssh0600613 -> 600613；200028 -> gssz0000028 -> 000028，均实测）。
    反推失败返回 None：显式报出需人工确认，不静默。"""
    if not (code.startswith("900") or code.startswith("200")):
        return code
    if orgid and orgid[:4] in ("gssh", "gssz") and orgid[4:].isdigit():
        a_code = orgid[4:].lstrip("0") or "0"
        a_code = a_code.zfill(6)
        if a_code != code:
            return a_code
    return None


def cninfo_query(code, orgid, column, start, end):
    """巨潮公告查询（自动翻页，pageSize=30）。返回 {total, items:[{title, date, url, type_name}]}。"""
    items, page = [], 1
    while True:
        data = json.loads(http_post(CNINFO_QUERY, {
            "pageNum": page,
            "pageSize": 30,
            "column": column,
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{code},{orgid}",
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": f"{start}~{end}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }))
        for a in data.get("announcements") or []:
            ts_ms = a.get("announcementTime")
            d = datetime.fromtimestamp(ts_ms / 1000, tz=BJ_TZ)
            items.append({
                "title": a.get("announcementTitle", ""),
                "date": d.strftime("%Y-%m-%d"),
                "url": "http://static.cninfo.com.cn/" + (a.get("adjunctUrl") or ""),
                "type_name": a.get("announcementTypeName") or "",
            })
        total = data.get("totalAnnouncement", 0)
        if not data.get("hasMore") or len(items) >= total:
            break
        page += 1
    return {"total": len(items) or data.get("totalAnnouncement", 0), "items": items}


def eastmoney_ann(code):
    """东财公告列表（自动翻页，page_size=50；交叉验证 + column_name 类型回填）。

    返回 {total, items}。响应 data.total_hits 为总数；类型在 columns[] 数组的
    column_name 里（顶层 column_name 恒为 null，实测）。
    """
    items, page = [], 1
    while True:
        url = (EM_ANN + f"?sr=-1&page_size=50&page_index={page}&ann_type=A"
               f"&client_source=web&stock_list={code}")
        data = json.loads(http_get(url, headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"}))
        lst = (data.get("data") or {}).get("list") or []
        total_hits = (data.get("data") or {}).get("total_hits") or 0
        for a in lst:
            cols = a.get("columns") or []
            type_name = "、".join(c.get("column_name", "") for c in cols
                                  if c.get("column_name"))
            items.append({
                "title": a.get("title", ""),
                "date": (a.get("notice_date") or "")[:10],
                "url": (a.get("art_code")
                        and f"https://data.eastmoney.com/notices/detail/{code}/{a['art_code']}.html"),
                "type_name": type_name,
            })
        if not lst or len(items) >= total_hits or page >= 20:
            break
        page += 1
    return {"total": total_hits, "items": items}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--codes", required=True, help="6 位股票代码，逗号分隔")
    ap.add_argument("--end", required=True, help="查询截止日 YYYY-MM-DD")
    ap.add_argument("--month-window", type=int, default=31)
    ap.add_argument("--week-window", type=int, default=7)
    ap.add_argument("--names", default="", help="股票名称，逗号分隔，与 --codes 对齐；缺省用空名")
    ap.add_argument("--universe-csv", default="", help="从成分股 CSV 读名称（列: code,name）")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    names = [n.strip() for n in args.names.split(",")] if args.names else []
    name_map = {}
    if args.universe_csv:
        with open(args.universe_csv, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                name_map[row.get("code", "").split(".")[0]] = row.get("name", "")
    end = datetime.strptime(args.end, "%Y-%m-%d")
    # 周窗口 = end-7 天（含边界当日），月窗口 = end-31 天；与实战基线一致
    month_start = end - timedelta(days=args.month_window)
    week_start = end - timedelta(days=args.week_window)
    ms, ws = month_start.strftime("%Y-%m-%d"), week_start.strftime("%Y-%m-%d")
    es = args.end

    rows = []
    for i, code in enumerate(codes):
        name = names[i] if i < len(names) else name_map.get(code, "")
        mk = market_of(code)
        orgid = topsearch_orgid(code)
        if not orgid:
            # 无兜底通道：如实跳过并显式报出，不静默丢标的
            print(f"[{code}] topSearch 未返回 orgId，该标的公告未覆盖", file=sys.stderr)
            continue
        q_code = code
        if code.startswith(("900", "200")):
            q_code = b_share_a_code(code, orgid)
            if q_code is None:
                print(f"[{code}] B 股 orgId {orgid} 无法反推 A 股代码，"
                      f"该标的公告需人工确认", file=sys.stderr)
                continue
            print(f"[{code}] B 股：公告经 A 股 {q_code} 检索（orgId {orgid}）",
                  file=sys.stderr)
        column = "sse" if mk == "sh" else "szse"
        r = cninfo_query(q_code, orgid, column, ms, es)
        em = eastmoney_ann(q_code)
        em_month = [e for e in em["items"] if e["date"] >= ms]
        print(f"[{code}] cninfo 月窗 total={r['total']}, 东财月窗 {len(em_month)} 条"
              f"（全量 {em['total']} 条）")
        if r["total"] == 0:
            # 0 条双向读：扩宽窗验证是「真无公告」还是参数错。
            # 判据 = 宽窗最新公告日期 vs 月窗起点：落在月窗内 → 参数/orgId 错；
            # 早于月窗起点 → 真无公告（如 920946 宽窗 8 条但最新 05-21，早于月窗起点）。
            wide = cninfo_query(q_code, orgid, column,
                                (end - timedelta(days=90)).strftime("%Y-%m-%d"), es)
            latest_em = em["items"][0]["date"] if em["items"] else "无"
            latest_wide = wide["items"][0]["date"] if wide["items"] else "无"
            print(f"[{code}] 月窗 0 条 -> 宽窗(90d) {wide['total']} 条（最新 {latest_wide}），"
                  f"东财最新公告 {latest_em}", file=sys.stderr)
            if wide["total"] > 0 and latest_wide >= ms:
                print(f"[{code}] ⚠️ 宽窗最新公告 {latest_wide} 落在月窗内，"
                      f"月窗 0 条疑为参数/orgId 问题，非「真无公告」", file=sys.stderr)
            else:
                print(f"[{code}] ✅ 宽窗最新公告 {latest_wide} 早于月窗起点 {ms}"
                      f" = 「真无公告」（参数正确，如实标注）", file=sys.stderr)
        for it in r["items"]:
            m = match_em(em["items"], it["date"], it["title"])
            it["type_name"] = it["type_name"] or (m["type_name"] if m else "")
        items = r["items"]
        # 东财独有条目补并集：两源覆盖不完全一致（部分类型仅一源有，如 002437 的
        # 07-23 投资者关系管理信息仅东财有），不能因为主源没有就漏掉。
        # 东财 URL 域 data.eastmoney.com 本身即来源标注。
        known = {(it["date"], norm_title(it["title"])) for it in items}
        for e in em["items"]:
            if e["date"] >= ms and not any(
                    date_near(e["date"], k[0]) and norm_title(e["title"]) == k[1]
                    for k in known):
                items.append({"title": e["title"], "date": e["date"],
                              "url": e["url"], "type_name": e["type_name"]})
        items.sort(key=lambda x: (x["date"], x["title"]), reverse=True)

        for it in items:
            window = "1周" if it["date"] >= ws else "1月"
            rows.append([code, name, it["title"], it["date"],
                         it["type_name"], it["url"], window])

    path = f"{args.out_dir}/announcements_{args.end}.csv"
    os.makedirs(args.out_dir, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["股票代码", "股票名称", "公告标题", "公告日期",
                    "公告类型(如有)", "公告URL", "时间窗口(1周|1月)"])
        w.writerows(rows)
    print(f"共 {len(rows)} 行已写入 {path}")

    # URL 抽查：跨股票各取 1 条（最多 3 只），避免全部落在第一只股票上
    sample, seen_codes = [], set()
    for r in rows:
        if r[0] not in seen_codes:
            seen_codes.add(r[0])
            sample.append(r)
        if len(sample) >= 3:
            break
    for r in sample:
        try:
            code = http_get(r[5])
            print(f"URL 抽查 [{r[0]} {r[2][:20]}...] -> {len(code)} bytes OK")
        except Exception as e:
            print(f"URL 抽查 [{r[0]} {r[2][:20]}...] -> 失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
