#!/usr/bin/env python3
"""A股板块 Top N 涨幅标的管线（stdlib only，无第三方依赖）。

数据链:
    东方财富 push2 板块成分股 -> 新浪 hq.sinajs.cn 实时快照 -> 涨幅排序 -> CSV 落盘

    注：2026-08-13 医药实战的原链是 Gangtise skill 的 quote.py 批量快照（前复权日K，
    落盘 raw_quote/quote_NN.csv）；本脚本新浪链为 skill 自带的公开源替代，
    创建当日实测跑通（508 只成分股全量、Top 10 落盘）。

调用（国内站点，必须去除代理环境变量，否则请求走翻墙代理失败）:
    env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
      python3 top_n_pipeline.py --board BK1216 --top 10 --out-dir /path/to/out

注意事项:
    - 盘中运行时数值是实时快照，会漂移；stdout 打印快照时间，报告中必须标注「盘中快照」
    - B 股（900 开头沪 B、200 开头深 B）新浪有行情，正常纳入；B 股涨跌幅规则与 A 股不同
      （10% 封顶），如需剔除由使用者显式过滤
    - 北交所代码（43/83/87/92 开头）新浪用 bj 前缀
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def http_get(url, headers=None, timeout=20, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:  # 公开行情接口偶发断连，重试
            last = e
            time.sleep(1 + attempt)
    raise last


def fetch_board_constituents(board_code):
    """东方财富 push2 板块成分股，返回 [(code, name), ...]。

    实测：pz 请求 >100 时服务端只回 100 条（BK1216 total=508），必须按 pz=100 翻页，
    翻页终止只看 len(out) >= total，不看单页长度。
    fid=f3 盘中实时排序会导致跨页边界漂移（实测 508 条中 2 只跨页重复），必须按代码去重。
    """
    out, seen, pn = [], set(), 1
    while True:
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get"
            f"?pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
            f"&fs=b:{board_code}&fields=f12,f14"
        )
        data = json.loads(http_get(url, headers={
            "User-Agent": UA,
            "Referer": "https://quote.eastmoney.com/",
        }))
        diff = (data.get("data") or {}).get("diff") or []
        total = (data.get("data") or {}).get("total") or 0
        if not diff or not total:
            break
        before = len(out)
        for d in diff:
            if d["f12"] not in seen:
                seen.add(d["f12"])
                out.append((d["f12"], d["f14"]))
        if len(out) >= total or len(out) == before:
            break
        pn += 1
    return out


def sina_symbol(code):
    """市场前缀：6 开头=沪 sh；900 开头=沪 B sh；200 开头=深 B sz；
    43/83/87/92 开头=北交所 bj；其余=深 sz。"""
    if code.startswith("6") or code.startswith("900"):
        return "sh" + code
    if code.startswith(("4", "8", "9")):
        return "bj" + code
    return "sz" + code


def market_suffix(code):
    if code.startswith("6") or code.startswith("900"):
        return "SH"
    if code.startswith(("4", "8", "9")):
        return "BJ"
    return "SZ"


def bucket_of(pct):
    """涨跌幅分桶（与 2026-08-13 实战产物口径一致）：
    >5% / 2-5% / 0-2% / 0% / -2-0% / <-2%，边界含上不含下（5% 归 >5%）。"""
    if pct >= 5:
        return ">5%"
    if pct >= 2:
        return "2-5%"
    if pct > 0:
        return "0-2%"
    if pct == 0:
        return "0%"
    if pct >= -2:
        return "-2-0%"
    return "<-2%"


def fetch_sina_snapshot(codes, batch=80):
    """新浪实时快照。返回 {code: {name, pct_change, price, preclose, amount}}；无行情代码缺失。

    新浪返回 GBK 编码，字段序: 0名称 1今开 2昨收 3现价 4最高 5最低 8成交量(股) 9成交额(元)。
    """
    out = {}
    for i in range(0, len(codes), batch):
        chunk = codes[i:i + batch]
        url = "https://hq.sinajs.cn/list=" + ",".join(sina_symbol(c) for c in chunk)
        raw = http_get(url, headers={
            "User-Agent": UA,
            "Referer": "https://finance.sina.com.cn",
        })
        for line in raw.decode("gbk", errors="replace").splitlines():
            if '="' not in line:
                continue
            symbol = line.split("=", 1)[0].replace("var hq_str_", "").strip()
            code = symbol[2:]
            payload = line.split('="', 1)[1].rstrip('";')
            if not payload:
                continue  # 无行情（如停牌股），自动剔除
            f = payload.split(",")
            try:
                preclose, price, amount = float(f[2]), float(f[3]), float(f[9])
            except (ValueError, IndexError):
                continue
            pct = (price - preclose) / preclose * 100 if preclose else 0.0
            out[code] = {
                "name": f[0],
                "pct_change": round(pct, 4),
                "price": price,
                "preclose": preclose,
                "amount": amount,
            }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--board", required=True, help="东财板块代码，如 BK1216（医药生物）")
    ap.add_argument("--top", type=int, default=10, help="取涨幅前 N（默认 10）")
    ap.add_argument("--out-dir", required=True, help="输出目录")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    fetched = datetime.now().strftime("%Y-%m-%d %H:%M:%S CST")
    os.makedirs(args.out_dir, exist_ok=True)
    cons = fetch_board_constituents(args.board)
    print(f"[{stamp}] 板块 {args.board} 成分股 {len(cons)} 只")

    upath = f"{args.out_dir}/universe_{args.board}_{stamp}.csv"
    with open(upath, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "name", "source", "fetched_at"])
        src = f"http://push2.eastmoney.com/api/qt/clist/get?fs=b:{args.board}&fields=f12,f14"
        for code, name in cons:
            w.writerow([code, name, src, fetched])
    print(f"成分股已落盘 {upath}（{len(cons)} 只）")

    codes = [c for c, _ in cons]
    snap = fetch_sina_snapshot(codes)
    missing = [(c, n) for c, n in cons if c not in snap]
    if missing:
        print(f"无行情数据 {len(missing)} 只（停牌等），未计入: " + ", ".join(f"{c} {n}" for c, n in missing[:20]),
              file=sys.stderr)

    rows = [
        (code, snap[code]["name"], snap[code])
        for code, _ in cons if code in snap
    ]
    rows.sort(key=lambda r: -r[2]["pct_change"])
    top = rows[:args.top]

    for i, (code, name, q) in enumerate(top, 1):
        print(f"  {i:>2}. {code}.{market_suffix(code)} {name} "
              f"{q['pct_change']:+.2f}% price={q['price']}")

    def write_csv(fname, table_rows):
        with open(fname, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["rank", "code", "name", "pct_change", "price", "preclose", "amount"])
            for j, (code, name, q) in enumerate(table_rows, 1):
                w.writerow([j, f"{code}.{market_suffix(code)}", name,
                            q["pct_change"], q["price"], q["preclose"], q["amount"]])

    path = f"{args.out_dir}/top{args.top}_{args.board}_{stamp}.csv"
    write_csv(path, top)
    print(f"Top {len(top)} 已写入 {path}（盘中快照 {stamp}，数值会漂移）")

    # 全板块行情落盘：市场宽度统计（上涨/下跌家数、分桶分布）的数据源
    apath = f"{args.out_dir}/all_quotes_{args.board}_{stamp}.csv"
    write_csv(apath, rows)
    print(f"全板块行情 {len(rows)} 只已写入 {apath}")

    # 涨跌幅分桶分布（表头与 2026-08-13 实战产物一致：bucket,count,total,pct_of_total）
    order = [">5%", "2-5%", "0-2%", "0%", "-2-0%", "<-2%"]
    counts = {b: 0 for b in order}
    for _, _, q in rows:
        counts[bucket_of(q["pct_change"])] += 1
    total = len(rows)
    up = sum(1 for _, _, q in rows if q["pct_change"] > 0)
    down = sum(1 for _, _, q in rows if q["pct_change"] < 0)
    flat = total - up - down

    dpath = f"{args.out_dir}/distribution_{args.board}_{stamp}.csv"
    with open(dpath, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["bucket", "count", "total", "pct_of_total"])
        for b in order:
            w.writerow([b, counts[b], total, round(counts[b] / total * 100, 2)])
        w.writerow(["up", up, total, round(up / total * 100, 2)])
        w.writerow(["down", down, total, round(down / total * 100, 2)])
        w.writerow(["flat", flat, total, round(flat / total * 100, 2)])
    print(f"涨跌分桶已写入 {dpath}（up {up} / down {down} / flat {flat}）")


if __name__ == "__main__":
    main()
