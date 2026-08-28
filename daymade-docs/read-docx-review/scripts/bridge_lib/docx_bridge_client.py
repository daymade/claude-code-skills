"""docx_bridge_client.py — 调 csharp/tasks/*.csx 拿带修订感知的 docx 数据

为什么必须走这里：
  python-docx 的 paragraph.text 通过 paragraph.runs 实现，runs 只取直接子 <w:r>
  不递归 <w:ins>，所以漏读所有作者插入的内容。OpenXML SDK 走 XML 树，能正确
  分类 inline ins/del、段落级 ins/del、各种文本视图。

入口函数：
  list_revisions(docx)        — 修订清单（含段落级 ins/del 索引）
  list_comments(docx)         — 批注清单（含 thread 关系、anchor 段）
  extract_views(docx, range)  — 每段三视图（accepted/rejected/display）+ 修订状态
  paragraph_text(docx, idx)   — 单段 accepted 文本（替代 paragraph.text 的最小单元）
  paragraphs_text(docx, view) — 全文段落文本数组（替代遍历 doc.paragraphs）

依赖：
  - dotnet-script 全局工具（一次安装：dotnet tool install -g dotnet-script）
  - DOTNET_ROLL_FORWARD=Major 环境变量（如本机只有 net10 而 csx 引用 net8）
  - 自动 NuGet restore DocumentFormat.OpenXml 3.2.0

缓存：
  按 (docx 路径 + mtime) 做内存级 LRU 缓存。docx 改动后自动失效。
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Literal, TypedDict

# ── 路径配置 ─────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
TASKS_DIR = _HERE.parent / "csharp" / "tasks"

LIST_REVISIONS_CSX = TASKS_DIR / "list_revisions.csx"
LIST_COMMENTS_CSX = TASKS_DIR / "list_comments.csx"
EXTRACT_VIEWS_CSX = TASKS_DIR / "extract_views.csx"


# ── 类型契约 ─────────────────────────────────────────────────────────
TextView = Literal["accepted", "rejected", "display"]


class RevisionDetail(TypedDict):
    paragraphIndex: int
    paraMarkDel: bool
    paraMarkIns: bool
    inlineDelCount: int
    inlineInsCount: int
    deletedText: str
    insertedText: str


class RevisionsSummary(TypedDict):
    totalParagraphs: int
    totalDelElements: int
    totalInsElements: int
    paragraphsWithInlineDel: int
    paragraphsWithInlineIns: int
    paragraphsWithParaMarkDel: int
    paragraphsWithParaMarkIns: int
    revisedParagraphsCount: int


class RevisionsResult(TypedDict):
    summary: RevisionsSummary
    paraMarkDelIndices: list[int]
    paraMarkInsIndices: list[int]
    details: list[RevisionDetail]


class CommentInfo(TypedDict):
    id: str
    author: str
    date: str
    content: str
    resolved: bool
    replyToCommentId: str | None
    anchorParagraphIndex: int | None
    anchorParagraphRange: list[int] | None


class CommentsSummary(TypedDict):
    total: int
    resolved: int
    unresolved: int
    threadRoots: int
    replies: int


class CommentsResult(TypedDict):
    summary: CommentsSummary
    comments: list[CommentInfo]


class ParagraphView(TypedDict):
    index: int
    styleId: str
    outlineLevel: int | None
    accepted: str
    rejected: str
    display: str
    paraMarkDel: bool
    paraMarkIns: bool
    hasInlineDel: bool
    hasInlineIns: bool


# ── 内部：dotnet-script 调用 ─────────────────────────────────────────
def _ensure_dotnet_script_on_path() -> None:
    """如果 PATH 里没有 dotnet-script，加上 ~/.dotnet/tools。"""
    if subprocess.run(["which", "dotnet-script"], capture_output=True).returncode == 0:
        return
    extra = str(Path.home() / ".dotnet" / "tools")
    if extra not in os.environ.get("PATH", ""):
        os.environ["PATH"] = os.environ.get("PATH", "") + ":" + extra


def _run_csx(script: Path, docx: str | Path, *extra_args: str) -> str:
    _ensure_dotnet_script_on_path()
    env = os.environ.copy()
    env.setdefault("DOTNET_ROLL_FORWARD", "Major")  # 兼容本机只有 net10 的情况
    cmd = ["dotnet-script", str(script), "--", str(docx), *extra_args]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(
            f"csx script failed: {script.name}\n"
            f"  stderr: {proc.stderr.strip()[:500]}"
        )
    return proc.stdout


# ── 缓存键 ───────────────────────────────────────────────────────────
def _cache_key(docx: str | Path) -> tuple[str, float]:
    p = Path(docx).resolve()
    return (str(p), p.stat().st_mtime)


# ── 公共 API ─────────────────────────────────────────────────────────
@lru_cache(maxsize=8)
def _list_revisions_cached(key: tuple[str, float]) -> RevisionsResult:
    return json.loads(_run_csx(LIST_REVISIONS_CSX, key[0]))


def list_revisions(docx: str | Path) -> RevisionsResult:
    """列出 docx 中所有修订（内联 ins/del + 段落级 ins/del）。"""
    return _list_revisions_cached(_cache_key(docx))


@lru_cache(maxsize=8)
def _list_comments_cached(key: tuple[str, float]) -> CommentsResult:
    return json.loads(_run_csx(LIST_COMMENTS_CSX, key[0]))


def list_comments(docx: str | Path) -> CommentsResult:
    """列出 docx 中所有批注 + thread 关系 + 段落锚定。"""
    return _list_comments_cached(_cache_key(docx))


@lru_cache(maxsize=4)
def _extract_views_full_cached(key: tuple[str, float]) -> list[ParagraphView]:
    """全文 NDJSON 一次性读入并缓存（4 个 docx 切换自由）。"""
    out = _run_csx(EXTRACT_VIEWS_CSX, key[0])
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def extract_views(
    docx: str | Path,
    paragraph_range: tuple[int, int] | None = None,
) -> list[ParagraphView]:
    """每段三视图 + 修订状态。

    paragraph_range: (start, end) 闭区间，用于按需切片（不影响缓存——总是缓存全文）
    """
    full = _extract_views_full_cached(_cache_key(docx))
    if paragraph_range is None:
        return full
    s, e = paragraph_range
    return [pv for pv in full if s <= pv["index"] <= e]


def paragraph_text(
    docx: str | Path,
    index: int,
    view: TextView = "accepted",
) -> str:
    """单段文本，替代 docx.paragraphs[i].text 的最小单元。

    view='accepted' 是默认推荐视图：作者接受所有修订后会看到的真实段落文本。
    """
    full = _extract_views_full_cached(_cache_key(docx))
    if not 0 <= index < len(full):
        raise IndexError(f"paragraph index {index} out of range (total={len(full)})")
    return full[index][view]


def paragraphs_text(
    docx: str | Path,
    view: TextView = "accepted",
) -> list[str]:
    """全文段落文本数组，替代 [p.text for p in doc.paragraphs]。"""
    full = _extract_views_full_cached(_cache_key(docx))
    return [pv[view] for pv in full]


def iter_paragraphs(
    docx: str | Path,
) -> Iterator[ParagraphView]:
    """流式迭代所有段落视图（含 styleId / outlineLevel / 修订状态）。"""
    yield from _extract_views_full_cached(_cache_key(docx))


# ── 衍生工具 ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ParagraphRevisionStatus:
    """段落综合修订状态分类。"""
    is_paragraph_marked_for_deletion: bool   # 接受修订后整段消失
    is_paragraph_marked_for_insertion: bool  # 整段是作者新插入
    has_inline_revisions: bool               # 段内有 ins/del
    is_pristine: bool                         # 完全无修订


def get_revision_status(pv: ParagraphView) -> ParagraphRevisionStatus:
    inline = pv["hasInlineDel"] or pv["hasInlineIns"]
    return ParagraphRevisionStatus(
        is_paragraph_marked_for_deletion=pv["paraMarkDel"],
        is_paragraph_marked_for_insertion=pv["paraMarkIns"],
        has_inline_revisions=inline,
        is_pristine=not (pv["paraMarkDel"] or pv["paraMarkIns"] or inline),
    )


def is_truly_empty(pv: ParagraphView) -> bool:
    """段落是不是'真的空'——既不被作者标记 ins/del，也无内联修订，accepted 文本为空。

    用这个判断时排除"被作者标记删除的段"（paraMarkDel）和"被作者插入的空段"（paraMarkIns），
    避免把合法修订误报为'格式残骸'。
    """
    if pv["paraMarkDel"] or pv["paraMarkIns"]:
        return False  # 作者明确处理过的段，不算"真空"
    if pv["hasInlineDel"] or pv["hasInlineIns"]:
        return False
    return not pv["accepted"].strip()


# ── CLI 自检 ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python docx_bridge_client.py <docx_path>")
        sys.exit(1)
    docx = sys.argv[1]
    rev = list_revisions(docx)
    com = list_comments(docx)
    print(f"docx: {docx}")
    print(f"revisions summary: {json.dumps(rev['summary'], indent=2)}")
    print(f"comments summary: {json.dumps(com['summary'], indent=2)}")
    print(f"sample paragraph: {paragraph_text(docx, 0)!r}")
