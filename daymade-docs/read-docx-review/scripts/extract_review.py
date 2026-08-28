#!/usr/bin/env python3
"""extract_review.py — 一条命令把 docx 的批注 + 修订读成对账表。

用途：收到对方审阅过的 docx（Word / WPS 批注、修订模式），出一张可逐条裁决的
markdown 对账表；`--json` 给机器可读全量。只读，不改文件。

用法（在 skill 根目录执行，或把 scripts/ 写成绝对路径）：
    uv run python scripts/extract_review.py <docx>
    uv run python scripts/extract_review.py <docx> --json
    uv run python scripts/extract_review.py <docx> --include-resolved

依赖：dotnet + dotnet-script（修订感知引擎，见 SKILL.md 依赖节）。
Python 侧纯 stdlib，无第三方包。

输出契约：
- 批注按文档顺序列出；回复（replyToCommentId 非空）缩进挂在其根批注之后。
- 锚定列取批注所在段落的 display 视图文本（修订感知，不丢 w:ins 内容）。
- 修订明细逐段列出删除/插入文本。
- 「处置」列刻意留空——对账表的用途是给人逐条裁决，脚本不预填。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bridge_lib.docx_bridge_client import extract_views, list_comments, list_revisions


def _short(text: str, limit: int = 60) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _md_cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _date_short(iso: str) -> str:
    return (iso or "")[:16].replace("T", " ")


def build_report(docx: str) -> dict:
    comments = list_comments(docx)
    revisions = list_revisions(docx)
    para_text: dict[int, str] = {}
    # 锚定段落文本用修订感知的 display 视图；extract_views 一次拿全量
    for v in extract_views(docx):
        para_text[v["index"]] = v["display"]
    for c in comments["comments"]:
        idx = c.get("anchorParagraphIndex")
        c["anchorText"] = para_text.get(idx, "") if idx is not None else ""
    return {"file": docx, "comments": comments, "revisions": revisions}


def render_markdown(report: dict, include_resolved: bool) -> str:
    lines: list[str] = []
    cs = report["comments"]["summary"]
    rs = report["revisions"]["summary"]
    fname = Path(report["file"]).name
    lines.append(f"# 审阅对账 · {fname}")
    lines.append("")
    # csx 已统一零批注/有批注两条路径的 summary 形状（五键），.get 仅作纵深防御留着
    lines.append(
        f"批注 {cs.get('total', 0)} 条（未处理 {cs.get('unresolved', 0)} / 已处理 {cs.get('resolved', 0)}"
        f"，其中回复 {cs.get('replies', 0)} 条）；修订段落 {rs.get('revisedParagraphsCount', 0)} 个"
        f"（删除元素 {rs.get('totalDelElements', 0)}、插入元素 {rs.get('totalInsElements', 0)}）。"
    )
    lines.append("")

    all_comments = report["comments"]["comments"]

    def visible(c: dict) -> bool:
        return include_resolved or not c["resolved"]

    # 先对全量分组（不能先按 resolved 过滤再分组：已处理根下可能挂着未处理回复，
    # 过滤在前会让那条回复既不进表也不进「另有 N 条」计数——静默消失，2026-08-29
    # 构造用例复现过。规则：根的保留条件 = 自己可见 或 有可见回复）
    replies_by_root: dict[str, list[dict]] = {}
    for c in all_comments:
        root_id = c.get("replyToCommentId")
        if root_id is not None:
            replies_by_root.setdefault(str(root_id), []).append(c)
    roots = [
        c for c in all_comments
        if not c.get("replyToCommentId")
        and (visible(c) or any(visible(r) for r in replies_by_root.get(str(c["id"]), [])))
    ]
    roots.sort(key=lambda c: (c.get("anchorParagraphIndex") is None,
                              c.get("anchorParagraphIndex") or 0))
    printed = 0
    if roots:
        lines.append("## 批注")
        lines.append("")
        lines.append("| # | 批注人 | 时间 | 锚定段落 | 批注内容 | 状态 | 处置 |")
        lines.append("|---|---|---|---|---|---|---|")
        for c in roots:
            status = "已处理" if c["resolved"] else "未处理"
            if c["resolved"] and not include_resolved:
                status = "已处理（因下方回复保留）"
            lines.append(
                f"| {c['id']} | {_md_cell(c['author'])} | {_date_short(c['date'])} "
                f"| {_md_cell(_short(c.get('anchorText', '')))} "
                f"| {_md_cell(c['content'])} | {status} |  |"
            )
            printed += 1
            for r in replies_by_root.get(str(c["id"]), []):
                if not visible(r):
                    continue
                lines.append(
                    f"| ↳{r['id']} | {_md_cell(r['author'])} | {_date_short(r['date'])} "
                    f"| （回复 #{c['id']}） | {_md_cell(r['content'])} "
                    f"| {'已处理' if r['resolved'] else '未处理'} |  |"
                )
                printed += 1
        lines.append("")
    hidden = len(all_comments) - printed
    if hidden:
        lines.append(f"（另有 {hidden} 条已处理批注未列出，`--include-resolved` 可见。）")
        lines.append("")

    details = report["revisions"]["details"]
    if details:
        lines.append("## 修订（track changes）")
        lines.append("")
        lines.append("| 段落 | 删除 | 插入 | 处置 |")
        lines.append("|---|---|---|---|")
        for d in details:
            mark = []
            if d["paraMarkDel"]:
                mark.append("整段删")
            if d["paraMarkIns"]:
                mark.append("整段增")
            tag = f"（{'/'.join(mark)}）" if mark else ""
            lines.append(
                f"| {d['paragraphIndex']}{tag} | {_md_cell(_short(d['deletedText'], 80))} "
                f"| {_md_cell(_short(d['insertedText'], 80))} |  |"
            )
        lines.append("")
    if cs.get("total", 0) == 0 and not details:
        lines.append("（无批注、无修订——这份 docx 没有携带任何审阅痕迹。若对方确认已批注，")
        lines.append("检查拿到的是不是导出时丢了批注的副本，或对方批在了在线版而未导出。）")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="docx 批注+修订 → 对账表（只读）")
    ap.add_argument("file", help="docx 文件路径")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON 全量")
    ap.add_argument("--include-resolved", action="store_true",
                    help="markdown 表包含已处理批注（默认只列未处理）")
    args = ap.parse_args()
    if not Path(args.file).is_file():
        print(f"文件不存在: {args.file}", file=sys.stderr)
        sys.exit(2)
    report = build_report(args.file)
    if args.json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(render_markdown(report, args.include_resolved))


if __name__ == "__main__":
    main()
