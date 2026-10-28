#!/usr/bin/env python3
"""Compare an explicit sent baseline with a returned DOCX; never change either input.

Use the existing OpenXML bridge. Reject unresolved revisions before comparison;
this is a text/table-structure aid, not a Word layout or legal-equivalence verdict.
"""
from __future__ import annotations

import argparse
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import sys

from bridge_lib.docx_bridge_client import comparison_snapshot


def _location(record: dict) -> str:
    return record["story"] + record["path"]


def _key(record: dict) -> tuple:
    return record["kind"], record["text"]


def _similarity(before: str, after: str) -> float:
    if not before.strip() or not after.strip():
        return 0
    if min(len(before), len(after)) >= 12 and (before in after or after in before):
        return 1
    return SequenceMatcher(None, before, after, autojunk=False).ratio()


def compare_records(before: dict, after: dict, anchors: list[str] | None = None) -> dict:
    """Align within stories, then suggest cross-position text matches for human review."""
    changes, removed, added, unchanged = [], [], [], []
    for story in dict.fromkeys(before["stories"] + after["stories"]):
        old = [r for r in before["records"] if r["story"] == story]
        new = [r for r in after["records"] if r["story"] == story]
        matcher = SequenceMatcher(None, [_key(r) for r in old],
                                  [_key(r) for r in new], autojunk=False)
        for tag, i, j, k, end in matcher.get_opcodes():
            if tag == "equal":
                unchanged.extend(zip(old[i:j], new[k:end]))
                continue
            # Keep changed records independent: a deletion may have moved into another block.
            removed.extend(old[i:j])
            added.extend(new[k:end])

    used = set()
    for old in removed:
        ranked = sorted(
            ((_similarity(old["text"], new["text"]), n, new)
             for n, new in enumerate(added)
             if n not in used and new["kind"] == old["kind"]
             and new["story"] == old["story"]),
            key=lambda item: item[0], reverse=True,
        )
        # Table geometry is directly comparable at the same table address.
        same_table = next(((1.0, n, r) for n, r in enumerate(added)
                           if n not in used and old["kind"] == "table_shape"
                           and r["kind"] == "table_shape" and _location(old) == _location(r)), None)
        if same_table:
            ranked.insert(0, same_table)
        if ranked and ranked[0][0] >= 0.55:
            score, n, new = ranked[0]
            used.add(n)
            exact = old["text"] == new["text"]
            same = _location(old) == _location(new)
            kind = "moved" if exact else ("rewritten" if same else "move_or_rewrite")
            changes.append({"kind": kind, "before": old, "after": new,
                            "similarity": round(score, 3)})
        else:
            changes.append({"kind": "removed", "before": old, "after": None})
    for n, new in enumerate(added):
        if n not in used:
            changes.append({"kind": "added", "before": None, "after": new})

    # A moved paragraph can become part of an otherwise matching rewritten paragraph.
    # Preserve every removal; show its best location clue without declaring it deleted in substance.
    for change in changes:
        if change["kind"] != "removed" or change["before"]["kind"] != "paragraph":
            continue
        text = change["before"]["text"]
        candidates = [r for r in after["records"] if r["kind"] == "paragraph"
                      and (len(text) >= 12 or ("/table" in change["before"]["path"]
                                              and len(text) >= 6)) and text in r["text"]]
        if candidates:
            change["kind"] = "possible_move_into_block"
            change["candidates"] = candidates
        else:
            fragments = [s.strip() for s in re.split(r"[。；;\n]", text) if len(s.strip()) >= 12]
            matches = [{"text": fragment, "locations": [r for r in after["records"]
                        if r["kind"] == "paragraph" and fragment in r["text"]]}
                       for fragment in fragments]
            matches = [match for match in matches if match["locations"]]
            if matches:
                change["kind"] = "possible_partial_move"
                change["matched_fragments"] = matches
                change["candidates"] = list({ _location(r): r for match in matches
                    for r in match["locations"] }.values())

    commitments = []
    for anchor in anchors or []:
        if not anchor.strip():
            raise ValueError("An unchanged commitment must contain non-whitespace text")
        old_hits = [r for r in before["records"] if r["kind"] == "paragraph"
                    and anchor in r["text"]]
        new_hits = [r for r in after["records"] if r["kind"] == "paragraph"
                    and anchor in r["text"]]
        exact_old = Counter(r["text"] for r in old_hits)
        exact_new = Counter(r["text"] for r in new_hits)
        status = ("baseline_missing" if not old_hits else
                  "unchanged_full_blocks" if exact_old == exact_new else
                  "changed_or_missing")
        commitments.append({"anchor": anchor, "status": status,
                            "before": old_hits, "after": new_hits})
    return {"changes": changes, "unchanged_full_block_count": len(unchanged),
            "commitments": commitments,
            "coverage": {"before": before["stories"], "after": after["stories"],
                         "before_records": len(before["records"]),
                         "after_records": len(after["records"])},
            "limitations": sorted(set(before.get("unsupported", [])
                                      + after.get("unsupported", [])))}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>").replace("\t", " ⇥ ")


def render_markdown(report: dict) -> str:
    labels = {"moved": "移位", "rewritten": "改写", "move_or_rewrite": "移位或改写候选",
              "removed": "原位置移除（核对其他位置）", "added": "新增",
              "possible_move_into_block": "疑似并入其他段落",
              "possible_partial_move": "部分文字疑似移入；其余待核"}
    lines = ["# 回稿全文对比", "", f"变化 {len(report['changes'])} 项；"
             f"完全相同的文本/表格结构记录 {report['unchanged_full_block_count']} 项。",
             "", "| 类型 | 原位置 / 原文 | 新位置 / 新文 |", "|---|---|---|"]
    for change in report["changes"]:
        sides = []
        for side in ("before", "after"):
            r = change[side]
            sides.append(_cell(_location(r) + " · " + r["text"]) if r else "—")
        if change.get("candidates"):
            sides[1] = "；".join(_cell(_location(r) + " · " + r["text"])
                                for r in change["candidates"])
        lines.append(f"| {labels[change['kind']]} | {sides[0]} | {sides[1]} |")
    if report["commitments"]:
        lines.extend(["", "## 指定承诺复核", ""])
        states = {"unchanged_full_blocks": "所在完整文本块及出现次数相同",
                  "changed_or_missing": "所在文本块有变化或缺失，需核对前后全文",
                  "baseline_missing": "基线未找到，不能判为不变"}
        for item in report["commitments"]:
            lines.append(f"- {_cell(item['anchor'])}：{states[item['status']]}。")
    lines.extend(["", "移位/改写匹配是线索，须结合前后全文核对；文字相同不证明承诺语义或法律效力不变。",
                  "范围：正文、页眉页脚、脚注尾注及表格文本/合并结构；"
                  "不比较字体、分页、图片内容或超链接目标。字段只比较已存显示文字，不重新计算。"])
    if report["limitations"]:
        lines.append("覆盖缺口（须另行核对）：" + "、".join(report["limitations"]) + "。")
    return "\n".join(lines)


def _identity(path: Path) -> dict:
    return {"file": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description="已发基线与回稿的全文对比（只读，拒绝未决修订）")
    parser.add_argument("baseline", type=Path, help="明确已发出的基线 DOCX")
    parser.add_argument("returned", type=Path, help="收到的回稿 DOCX")
    parser.add_argument("--json", action="store_true", help="输出全文记录和变化 JSON")
    parser.add_argument("--unchanged", action="append", default=[], metavar="TEXT",
                        help="逐项核对关键承诺所在完整文本块，支持重复传入")
    args = parser.parse_args()
    try:
        identities = {"baseline": _identity(args.baseline), "returned": _identity(args.returned)}
        old = comparison_snapshot(args.baseline)
        new = comparison_snapshot(args.returned)
        report = compare_records(old, new, args.unchanged)
        if identities != {"baseline": _identity(args.baseline), "returned": _identity(args.returned)}:
            raise RuntimeError("Input changed during comparison; result discarded")
        report["inputs"] = identities
        if args.json:
            report["snapshots"] = {"baseline": old, "returned": new}
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(render_markdown(report))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"比较未执行或结果已丢弃；原件未改：{exc}", file=sys.stderr)
        if "Unresolved revisions" in str(exc):
            print("先用 extract_review.py 读取修订；由已验证的修订感知工具在独立副本中"
                  "落实已确认的接受/拒绝视图，再比较副本。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
