#!/usr/bin/env python3
"""sync_delivery_gates.py — 把 data-visualization-discipline 的九条交付闸生成给 report-with-html。

为什么存在
    `report-with-html/scripts/delivery_gate.py` 要把那九条的标题与产物要求写进它生成的
    gate 文件里。此前它手抄了一份常量表，注释还写着「标题为该 skill 原文」——**那份副本
    已经漂过一次**：闸 3 的产物行丢了「每张图是否都遵守阶段 2 定下的那三个值」整个子项，
    由独立审计对着原文抓出。更难堪的是随后的「修复」也只是又一次转述，不是原文。

    手抄的副本没救。加一条「记得同步」的注释同样没救——那是散文，而散文挡不住。
    所以改成：**抄这个动作由脚本做。** 人不再有手抄的机会。

跑在哪
    仓级，本 generator 必须同时看见两个 skill。

为什么不是运行时直接读 SSOT
    两个 skill 是各自独立的 plugin，可以只装其中一个。让 delivery_gate.py 硬依赖隔壁
    skill 存在，会让「只装了 report-with-html」这个完全健康的安装当场判红——
    误杀健康输入比漏报更糟，它训练人反射性绕过整道闸。所以副本仍然存在，
    但它是**生成物**，而不是**手抄物 + 一句但愿有人记得**。

为什么用 markdown-it-py 而不是正则
    正则扫 markdown 会把**代码围栏里的示例**当真：SSOT 哪天在示例块里写一行
    「（产物：…）」，正则版就会把它当成第十条闸的产物。这不是假想——同一个 session 里
    刚因为手搓 HTML 深度计数器连栽五轮，换成合规解析器才一次端掉整类。

退出码
    0 = 一致 / 已写入   1 = 漂移（--check）   3 = 根本没跑起来（源文件缺失、结构不认识）
    3 与 1 分开是有意的：「没检查」和「检查了，是陈旧的」把人送去两个完全不同的地方。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data-visualization-discipline" / "SKILL.md"
TARGET = ROOT / "report-with-html" / "assets" / "delivery-gates.json"

SECTION_PREFIX = "交付前自检闸"
TITLE_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
DELIVERABLE_RE = re.compile(r"^（产物：(.+)）$")

EXPECTED_COUNT = 9


class SourceShapeError(RuntimeError):
    """源文件结构不是我们认识的样子——这时必须停，不能猜着往下生成。"""


def _section_tokens(tokens: list) -> list:
    """截出「## 交付前自检闸」到下一个同级标题之间的 token。"""
    start = None
    for i, t in enumerate(tokens):
        if t.type == "heading_open" and t.tag == "h2":
            title = tokens[i + 1].content if i + 1 < len(tokens) else ""
            if title.startswith(SECTION_PREFIX):
                start = i
            elif start is not None:
                return tokens[start:i]
    if start is None:
        raise SourceShapeError(f"源文件里找不到「## {SECTION_PREFIX}…」这一节")
    return tokens[start:]


def extract(md: str) -> list[dict]:
    """从 data-viz 的 SKILL.md 里取出九条闸的编号 / 标题 / 产物要求。

    严格到近乎苛刻是故意的：这个函数的产物会被当成另一个 skill 的权威文本用，
    它「差不多解析对了」和「解析对了」在下游长得一模一样。任何不认识的形状一律抛错。
    """
    from markdown_it import MarkdownIt  # noqa: PLC0415 — 只有生成时用得上

    tokens = _section_tokens(MarkdownIt().parse(md))

    # 走列表 token，而不是按行 grep：列表项的边界由解析器判定，
    # 代码围栏里的内容天然不会被当成正文（正则版会）。
    #
    # 用**栈**而不是一个计数器，两点都踩过：
    #   · 只数 ordered list 的话，条目里一个 `- ` 子列表的 list_item_open 会被当成
    #     顶层的下一条闸，把父条目已收集的内容整段冲掉；
    #   · 收集内容时不能按深度过滤——CommonMark 会把子列表后面同缩进的那一行
    #     **懒延续**进子列表项里，于是「（产物：…）」正好落在被过滤掉的那一层。
    #     所以：**边界只认最外层，内容照单全收**（嵌套行不匹配任何模式，无害）。
    gates: list[dict] = []
    stack: list[str] = []
    item_lines: list[str] | None = None
    for t in tokens:
        if t.type.endswith("_list_open"):
            stack.append(t.type)
        elif t.type.endswith("_list_close"):
            if stack:
                stack.pop()
        elif t.type == "list_item_open" and stack == ["ordered_list_open"]:
            item_lines = []
        elif t.type == "list_item_close" and len(stack) == 1 and item_lines is not None:
            gates.append(_one_gate(item_lines, len(gates) + 1))
            item_lines = None
        elif t.type == "inline" and item_lines is not None:
            item_lines.extend(t.content.splitlines())

    if len(gates) != EXPECTED_COUNT:
        raise SourceShapeError(
            f"解析出 {len(gates)} 条闸，期望 {EXPECTED_COUNT} 条"
            f"（拿到的是：{[g['n'] + '·' + g['title'] for g in gates]}）")
    return gates


def _one_gate(lines: list[str], n: int) -> dict:
    """一条闸 = 首行的粗体标题 + 唯一一行「（产物：…）」。"""
    head = next((ln for ln in lines if ln.strip()), "")
    m = TITLE_RE.match(head.strip())
    if not m:
        raise SourceShapeError(f"第 {n} 条的首行不是 **粗体标题**，实际是：{head.strip()[:60]!r}")
    title = m.group(1).strip()

    hits = [d.group(1).strip() for ln in lines
            if (d := DELIVERABLE_RE.match(ln.strip()))]
    if not hits:
        raise SourceShapeError(f"第 {n} 条「{title}」没有「（产物：…）」行")
    if len(hits) > 1:
        raise SourceShapeError(f"第 {n} 条「{title}」有 {len(hits)} 行「（产物：…）」，只能有一行")
    if not hits[0]:
        raise SourceShapeError(f"第 {n} 条「{title}」的产物行是空的")
    return {"n": str(n), "title": title, "deliverable": hits[0]}


def render(gates: list[dict]) -> str:
    """生成 JSON。**不写时间戳、不写版本号**——那是派生值，会让每次生成的字节都不同，
    而字节比对正是这套机制唯一的判据。"""
    doc = {
        "_ssot": "data-visualization-discipline/SKILL.md §交付前自检闸",
        "_generated_by": "scripts/sync_delivery_gates.py",
        "_do_not_edit": "要改内容去改上面那个 SSOT，然后重跑 generator。",
        "gates": gates,
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true", help="重新生成并写入目标文件")
    g.add_argument("--check", action="store_true", help="只比对，不写；漂移则退出 1")
    args = ap.parse_args()

    if not SOURCE.is_file():
        print(f"❌ 找不到 SSOT：{SOURCE}", file=sys.stderr)
        return 3
    try:
        fresh = render(extract(SOURCE.read_text(encoding="utf-8")))
    except SourceShapeError as e:
        print(f"❌ 源文件结构不认识，没有生成任何东西：{e}", file=sys.stderr)
        print("   （这是「没检查」不是「检查通过」——去看 SSOT 的九条是不是改了形状）",
              file=sys.stderr)
        return 3

    if args.write:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(fresh, encoding="utf-8")
        print(f"✅ 已写入 {TARGET.relative_to(ROOT)}（{EXPECTED_COUNT} 条）")
        return 0

    if not TARGET.is_file():
        print(f"❌ 目标文件不存在：{TARGET.relative_to(ROOT)}——跑 --write 生成它", file=sys.stderr)
        return 1
    committed = TARGET.read_text(encoding="utf-8")
    if committed == fresh:
        print(f"✅ {TARGET.relative_to(ROOT)} 与 SSOT 一致（{EXPECTED_COUNT} 条）")
        return 0

    import difflib
    print(f"🔴 {TARGET.relative_to(ROOT)} 已与 SSOT 漂移。跑 "
          f"`python3 scripts/sync_delivery_gates.py --write` 重新生成。", file=sys.stderr)
    for ln in list(difflib.unified_diff(committed.splitlines(), fresh.splitlines(),
                                        "committed", "regenerated", lineterm=""))[:40]:
        print("   " + ln, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
