#!/usr/bin/env python3
"""
医药行业日报 — 数据管线
一条命令完成：抓取新浪实时行情 → 分析赛道排名 → 生成飞书日报 → 发送

用法：
  python3 daily_pipeline.py --feishu-profile <你的profile> --feishu-chat-id oc_xxx
"""

import json
import subprocess
import os
import sys
import urllib.request
from datetime import datetime

# ── 默认股票池（20 只核心医药股）──
STOCK_POOL = {
    "600276": "恒瑞医药", "688235": "百济神州", "300122": "智飞生物",
    "603259": "药明康德", "300347": "泰格医药", "002821": "凯莱英", "300759": "康龙化成",
    "300760": "迈瑞医疗", "688271": "联影医疗", "002223": "鱼跃医疗",
    "600436": "片仔癀", "000538": "云南白药", "600085": "同仁堂",
    "600196": "复星医药", "000963": "华东医药", "002422": "科伦药业",
    "002001": "新和成", "002007": "华兰生物", "300015": "爱尔眼科", "600161": "天坛生物",
}

STOCK_SECTOR = {
    "600276": "创新药", "688235": "创新药", "300122": "创新药",
    "603259": "CXO", "300347": "CXO", "002821": "CXO", "300759": "CXO",
    "300760": "医疗器械", "688271": "医疗器械", "002223": "医疗器械",
    "600436": "中药", "000538": "中药", "600085": "中药",
    "600196": "综合医药", "000963": "综合医药", "002422": "综合医药",
    "002001": "综合医药", "002007": "综合医药",
    "300015": "医疗服务", "600161": "生物制品",
}

# 新浪个别返回名称含空格，归一化
STOCK_NAME_NORM = {"新 和 成": "新和成"}

HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def sina_code(stock_id):
    """6 → sh, 其他 → sz"""
    return f"sh{stock_id}" if stock_id.startswith(("6", "5")) else f"sz{stock_id}"


def fetch_url(url, encoding=None):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return raw.decode(encoding) if encoding else raw
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return None


def fetch_realtime():
    """从新浪抓取实时行情"""
    print("📊 抓取实时行情...")
    codes = [sina_code(sid) for sid in STOCK_POOL]
    results = []

    for i in range(0, len(codes), 10):
        batch = codes[i:i + 10]
        url = f"http://hq.sinajs.cn/list={','.join(batch)}"
        raw = fetch_url(url, encoding="gbk")
        if not raw:
            continue

        for line in raw.strip().split("\n"):
            if "=" not in line:
                continue
            try:
                code_part = line.split("=")[0].split("_")[-1]
                stock_id = code_part[2:]
                values = line.split('"')[1].split(",")
                if len(values) < 32:
                    continue

                price = float(values[3]) if values[3] else None
                prev_close = float(values[2]) if values[2] else None
                chg_pct = None
                if price and prev_close and prev_close > 0:
                    chg_pct = round((price - prev_close) / prev_close * 100, 2)

                name = values[0]
                name = STOCK_NAME_NORM.get(name, name)

                results.append({
                    "股票代码": stock_id,
                    "股票名称": name,
                    "细分赛道": STOCK_SECTOR.get(stock_id, "其他"),
                    "最新价": price,
                    "涨跌幅%": chg_pct,
                    "今日最高": float(values[4]) if values[4] else None,
                    "今日最低": float(values[5]) if values[5] else None,
                    "成交金额": float(values[9]) if values[9] else 0,
                    "数据时间": f"{values[30]} {values[31]}",
                })
            except Exception:
                continue

    print(f"  ✅ 获取 {len(results)} 只实时行情")
    return results


def analyze(data):
    """分析赛道排名、涨跌榜、资金流向"""
    changes = [r["涨跌幅%"] for r in data if r["涨跌幅%"] is not None]
    amounts = [r["成交金额"] for r in data if r["成交金额"]]
    up = sum(1 for c in changes if c > 0)
    down = sum(1 for c in changes if c < 0)

    overview = {
        "股票数": len(data),
        "平均涨跌幅%": round(sum(changes) / len(changes), 2) if changes else 0,
        "上涨": up, "下跌": down,
        "平": sum(1 for c in changes if c == 0),
        "总成交亿": round(sum(amounts) / 1e8, 2) if amounts else 0,
    }

    # 赛道聚合
    sectors = {}
    for r in data:
        s = r["细分赛道"]
        if s not in sectors:
            sectors[s] = {"chgs": [], "amt": 0}
        if r["涨跌幅%"] is not None:
            sectors[s]["chgs"].append(r["涨跌幅%"])
        sectors[s]["amt"] += r["成交金额"] / 1e8 if r["成交金额"] else 0

    sector_rank = []
    for name, sd in sectors.items():
        avg = round(sum(sd["chgs"]) / len(sd["chgs"]), 2) if sd["chgs"] else 0
        sector_rank.append({
            "赛道": name, "股票数": len(sd["chgs"]),
            "平均涨跌幅%": avg, "总成交亿": round(sd["amt"], 2),
        })
    sector_rank.sort(key=lambda r: r["平均涨跌幅%"], reverse=True)

    sorted_stocks = sorted(
        [r for r in data if r["涨跌幅%"] is not None],
        key=lambda r: r["涨跌幅%"], reverse=True,
    )

    inflow = sum(r["成交金额"] for r in data if (r["涨跌幅%"] or 0) > 0)
    outflow = sum(r["成交金额"] for r in data if (r["涨跌幅%"] or 0) < 0)

    return {
        "概览": overview,
        "赛道排名": sector_rank,
        "领涨": sorted_stocks[:3],
        "领跌": sorted_stocks[-3:][::-1],
        "净流向亿": round((inflow - outflow) / 1e8, 2),
    }


def build_markdown(data, analysis, today_str):
    """生成飞书 markdown 日报"""
    ov = analysis["概览"]
    avg = ov["平均涨跌幅%"]

    md = f"""# 💊 医药行业日报
**{today_str}**  |  数据来源：新浪财经  |  覆盖 {ov['股票数']} 只核心医药股

---

## 📊 板块概览
{ov['股票数']} 只股票 ｜ 平均涨跌幅 **{avg:+.2f}%** ｜ 上涨 {ov['上涨']} 家 / 下跌 {ov['下跌']} 家
总成交 **{ov['总成交亿']} 亿** ｜ 资金净流向估算 **{analysis['净流向亿']:+.2f} 亿**

---

## 🏆 赛道排名
"""

    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    for i, s in enumerate(analysis["赛道排名"]):
        icon = medals.get(i, "  ")
        color = "red" if s["平均涨跌幅%"] > 0 else "green"
        sign = "+" if s["平均涨跌幅%"] > 0 else ""
        md += f"{icon} **{s['赛道']}**（{s['股票数']}只）：<font color='{color}'> {sign}{s['平均涨跌幅%']}%</font>  ｜ 成交 {s['总成交亿']} 亿\n"

    md += "\n---\n\n## 📈 今日领涨 TOP 3\n"
    for r in analysis["领涨"]:
        md += f"- **{r['股票名称']}**（{r['股票代码']}） <font color='red'>+{r['涨跌幅%']}%</font>  ￥{r['最新价']}  ｜ {r['细分赛道']}\n"

    md += "\n## 📉 今日领跌 TOP 3\n"
    for r in analysis["领跌"]:
        md += f"- **{r['股票名称']}**（{r['股票代码']}） <font color='green'>{r['涨跌幅%']}%</font>  ￥{r['最新价']}  ｜ {r['细分赛道']}\n"

    md += f"""\n---
> 📌 数据时间：{datetime.now().strftime('%Y/%m/%d %H:%M')}  ｜  来源：新浪财经公开行情接口
> ⚠️ 本报告仅供信息参考，不构成任何投资建议。股市有风险，入市需谨慎。
"""

    # 飞书 markdown 约 4096 字节限制
    if len(md.encode("utf-8")) > 4000:
        md = md[:3500] + "\n\n> ⚠️ 内容过长已截断，完整数据请查看快照文件"

    return md


def send_feishu(markdown_text, profile, chat_id):
    """通过 lark-cli 发送飞书消息"""
    print("📨 发送飞书日报...")

    import shutil

    lark_cli = shutil.which("lark-cli")
    if not lark_cli:
        print("❌ 找不到 lark-cli，请先安装: npm install -g @larksuite/cli")
        return False
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"

    result = subprocess.run(
        [lark_cli, "--profile", profile, "im", "+messages-send",
         "--chat-id", chat_id, "--markdown", markdown_text],
        capture_output=True, text=True, timeout=30, env=env,
    )

    try:
        data = json.loads(result.stdout)
        if data.get("ok"):
            print(f"  ✅ 发送成功: {data['data']['message_id']}")
            return True
        else:
            print(f"  ❌ 发送失败: {data.get('error', {}).get('message', 'unknown')}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ 解析响应失败: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="医药行业日报管线")
    parser.add_argument("--feishu-profile", required=True, help="飞书 lark-cli profile 名")
    parser.add_argument("--feishu-chat-id", required=True, help="飞书 chat_id")
    parser.add_argument("--output-dir", default=".", help="快照输出目录")
    args = parser.parse_args()

    today_str = datetime.now().strftime("%Y年%m月%d日（%A）")
    print(f"\n{'='*50}")
    print(f"  医药行业日报")
    print(f"  时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    # 1. 抓数据
    realtime = fetch_realtime()
    if not realtime:
        print("❌ 实时行情抓取失败")
        sys.exit(1)

    # 2. 分析
    analysis = analyze(realtime)

    # 3. 快照
    snap_path = os.path.join(args.output_dir, f"pharma_snapshot_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump({"时间": today_str, "分析": analysis, "原始数据": realtime},
                  f, ensure_ascii=False, indent=2, default=str)
    print(f"💾 快照: {snap_path}")

    # 4. 发飞书
    md = build_markdown(realtime, analysis, today_str)
    ok = send_feishu(md, args.feishu_profile, args.feishu_chat_id)

    # 5. 总结
    ov = analysis["概览"]
    top_sector = analysis["赛道排名"][0] if analysis["赛道排名"] else {"赛道": "—", "平均涨跌幅%": 0}
    print(f"\n{'='*50}")
    print(f"  {ov['股票数']}只 | 均{ov['平均涨跌幅%']:+.2f}% | ↑{ov['上涨']} ↓{ov['下跌']}")
    print(f"  最强: {top_sector['赛道']} {top_sector['平均涨跌幅%']:+.2f}%")
    if analysis["领涨"]:
        print(f"  领涨: {analysis['领涨'][0]['股票名称']} +{analysis['领涨'][0]['涨跌幅%']}%")
    if analysis["领跌"]:
        print(f"  领跌: {analysis['领跌'][0]['股票名称']} {analysis['领跌'][0]['涨跌幅%']}%")
    print(f"  飞书: {'✅ 已发送' if ok else '❌ 失败'}")
    print(f"{'='*50}\n")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
