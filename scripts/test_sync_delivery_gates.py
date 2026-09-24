#!/usr/bin/env python3
"""test_sync_delivery_gates.py — 给 delivery-gates 同步器的双向标定。

「一道没人测过的漂移闸，它的绿是没有含义的」。
这套测试因此两个方向都测：**合规源必须解析出九条**，
**每一种坏形状必须抛错**（否则它会生成一份看起来很正常的错东西）。

跑法:  uv run --with markdown-it-py python3 scripts/test_sync_delivery_gates.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("sdg", Path(__file__).with_name("sync_delivery_gates.py"))
sdg = importlib.util.module_from_spec(_spec)
sys.modules["sdg"] = sdg
_spec.loader.exec_module(sdg)


def gate(n: int, title: str, product: str, extra: str = "") -> str:
    body = f"{n}. **{title}**\n   一句正文。\n"
    if extra:
        body += f"{extra}\n"
    if product is not None:
        body += f"   （产物：{product}）\n"
    return body + "\n"


def doc(*items: str, heading: str = "## 交付前自检闸（9 条 · 本 skill 的脊柱）") -> str:
    return f"# T\n\n{heading}\n\n" + "".join(items) + "\n## 下一节\n\n结束。\n"


NINE = doc(*[gate(i, f"闸{i}", f"产物{i}") for i in range(1, 10)])

PASS, FAIL = [], []


def ok(label: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(label)
    print(f"{'✅' if cond else '❌'}  {label}" + (f"   {detail}" if detail and not cond else ""))


def raises(label: str, md: str) -> None:
    try:
        sdg.extract(md)
    except sdg.SourceShapeError as e:
        ok(label, True)
        return
    except Exception as e:                                    # noqa: BLE001
        ok(label, False, f"抛了 {type(e).__name__} 而不是 SourceShapeError: {e}")
        return
    ok(label, False, "没有抛错——它会生成一份看起来正常的错东西")


# ── 正向：合规的源必须解析得出来（这一半防的是「闸门永久红→被绕过」） ──────────
g = sdg.extract(NINE)
ok("正向 · 九条齐 → 解析出 9 条", len(g) == 9)
ok("正向 · 编号 1..9 有序", [x["n"] for x in g] == [str(i) for i in range(1, 10)])
ok("正向 · 标题与产物逐条对上",
   all(x["title"] == f"闸{x['n']}" and x["deliverable"] == f"产物{x['n']}" for x in g))
ok("正向 · 产物行里的 **粗体** 原样保留（下游要的是原文不是净化过的）",
   sdg.extract(doc(*[gate(i, f"闸{i}", "a + **b** + c") for i in range(1, 10)]))[0]["deliverable"]
   == "a + **b** + c")
ok("正向 · 条目内的嵌套子列表不被当成第十条闸",
   len(sdg.extract(doc(*([gate(1, "闸1", "产物1", "   1. 子项一\n   2. 子项二")]
                        + [gate(i, f"闸{i}", f"产物{i}") for i in range(2, 10)])))) == 9)

# ── 反向：每一种坏形状都必须抛错（这一半防的是「静默生成错东西」） ──────────────
raises("反向 · 只有 8 条", doc(*[gate(i, f"闸{i}", f"产物{i}") for i in range(1, 9)]))
raises("反向 · 多出第 10 条", doc(*[gate(i, f"闸{i}", f"产物{i}") for i in range(1, 11)]))
raises("反向 · 某条缺「（产物：…）」行",
       doc(*([gate(1, "闸1", None)] + [gate(i, f"闸{i}", f"产物{i}") for i in range(2, 10)])))
raises("反向 · 某条有两行「（产物：…）」",
       doc(*([gate(1, "闸1", "产物1", "   （产物：又一行）")]
             + [gate(i, f"闸{i}", f"产物{i}") for i in range(2, 10)])))
raises("反向 · 首行不是粗体标题",
       doc(*(["1. 没有粗体的标题\n   （产物：x）\n\n"]
             + [gate(i, f"闸{i}", f"产物{i}") for i in range(2, 10)])))
raises("反向 · 产物行是空的",
       doc(*([gate(1, "闸1", "")] + [gate(i, f"闸{i}", f"产物{i}") for i in range(2, 10)])))
raises("反向 · 整节标题被改名/删掉", NINE.replace("## 交付前自检闸（9 条 · 本 skill 的脊柱）", "## 别的东西"))

# ── 这一条是换掉正则、改用 markdown-it 的**唯一理由**，所以必须有它 ─────────────
fenced = doc(*([gate(1, "闸1", "产物1",
                     "   ```\n   1. **假闸**\n   （产物：这是代码块里的示例，不是真的）\n   ```")]
               + [gate(i, f"闸{i}", f"产物{i}") for i in range(2, 10)]))
try:
    gf = sdg.extract(fenced)
    ok("代码围栏 · 围栏里的示例不被当成真闸（正则版会当真）",
       len(gf) == 9 and gf[0]["deliverable"] == "产物1", f"拿到 {len(gf)} 条")
except sdg.SourceShapeError as e:
    ok("代码围栏 · 围栏里的示例不被当成真闸（正则版会当真）", False, f"误抛：{e}")

# ── 真实 SSOT：解析得出、且不是空壳 ─────────────────────────────────────────
real = sdg.extract(sdg.SOURCE.read_text(encoding="utf-8"))
ok("真实 SSOT · 解析出 9 条且标题产物均非空",
   len(real) == 9 and all(x["title"] and x["deliverable"] for x in real))

print(f"\n{len(PASS)} 通过 / {len(FAIL)} 失败")
sys.exit(1 if FAIL else 0)
