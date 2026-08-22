#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Harvest Corrections — turn a finished native pass into trap candidates.

The native AI pass fixes a transcript by editing it directly; those fixes
never enter Stage 1's correction_history, so the next transcript in the same
domain hits the same traps and the operator has to feed the same entities
again by hand. This script closes that leak mechanically:

    raw transcript  +  corrected transcript
        -> token-level diff (CJK runs / Latin runs / punct / whitespace)
        -> replace-opcode pairs (from, to)
        -> noise filter (punct-only, empty, over-long spans)
        -> dedupe + occurrence counts in the raw text
        -> candidate trap bullets, parseable by core.trap_scanner
           BY CONSTRUCTION (every emitted bullet is round-trip verified
           through the real parser before printing)

Output is a REVIEW artifact: the operator adjudicates which pairs are real
recurring traps vs one-off fixes. `--write` auto-appends only the recurring
(≥2 occurrences) non-bare candidates to the context file's dated harvest
section — recurrence is the trap signal, and one-off prose rewrites must not
land in a context file unreviewed; `--write-all` appends the full set.
Nothing here edits the dictionary — per the skill's Dictionary Addition
matrix, real-word traps belong to the domain context file, and a trap is a
cue for the next native pass, never permission to replace blindly.

Usage:
    uv run scripts/harvest_corrections.py RAW CORRECTED
    uv run scripts/harvest_corrections.py RAW CORRECTED --json
    uv run scripts/harvest_corrections.py RAW CORRECTED \
        --context-file ~/.transcript-fixer/contexts/<domain>.md --write
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.trap_scanner import extract_trap_entries  # noqa: E402

# Same token shape as generate_word_diff.py: CJK runs, Latin/digit runs,
# single punctuation chars, whitespace runs.
_TOKEN = re.compile(
    r"[一-鿿]+|[a-zA-Z0-9]+|[^一-鿿a-zA-Z0-9\s]|\s+"
)
# Characters the trap scanner rejects in a bare FROM variant / TO term.
# (mirror of trap_scanner._BAD_VARIANT — keep in sync; a bullet carrying
# any of these must wrap that side in backticks to stay parseable)
_BAD_BARE = re.compile(r"[\s，。；：、（）()\[\]【】\"'“”‘’`]")
_PUNCT_ONLY = re.compile(
    r"^[\s，。；：、（）()\[\]【】\"'“”‘’`.,;:!?…—\-/·]+$"
)
_PUNCT_CHARS = re.compile(r"[\s，。；：、（）()\[\]【】\"'“”‘’`.,;:!?…—\-/·]")
_MAX_SPAN_CHARS = 24  # trap_scanner TO cap is _MAX_TERM_LEN * 2 = 24


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text)


def _extract_pairs(raw: str, corrected: str) -> list[tuple[str, str]]:
    """Token-stream diff -> (from, to) spans from `replace` opcodes."""
    old = _tokenize(raw)
    new = _tokenize(corrected)
    pairs: list[tuple[str, str]] = []
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace":
            continue
        from_span = "".join(old[i1:i2]).strip()
        to_span = "".join(new[j1:j2]).strip()
        pairs.append((from_span, to_span))
    return pairs


# 高频语法黏着字：扩展 span 时碰到它说明已越过词边界（把「以/的/个」吸进
# trap 永远是错的）；此时改试另一侧，两侧都黏着就停在较短 span。
_GLUE_CHARS = set(
    "的了在有我你他她它把被以让去和或就是个这那哪呢吧吗啊呀哦嗯嘛啦"
    "只又也都还要会能可以说来对从向往前中后上下里外间问到最更很太极"
    "再越按曾正将及且而则即若虽因所为于之其此该各每某时当"
    "用做打搞弄拿给叫使令")

# trap 最短有效长度：CJK 2 字（生活/缺陷）误伤面太大，3 字（蓝活通/云国）
# 通常已带消歧邻字。扩展后仍 <3 的纯 CJK 候选标 ⚠️ 裸形——人工收紧前
# --write 不自动写入（裸词 trap 误伤面最大）。
_MIN_TRAP_LEN = 3


def _expand(core_f: str, core_t: str, left_eq: str, right_eq: str,
            count, min_len: int = _MIN_TRAP_LEN) -> tuple[str, str]:
    """Widen a minimal char-diff region with matching equal context.

    A bare minimal region is systematically too narrow for CJK entity traps:
    缺陷→确幸 drops the 小 that keeps the trap from being a bare-word
    disaster; 息→希 would flag every 息. Both context strings are drawn from
    `equal` regions, so they are identical on the from/to sides and can be
    moved into the span without changing the edit's meaning. Expansion never
    absorbs a _GLUE_CHARS char — that is the word boundary, not the term.

    Direction is chosen by a frequency oracle, not fixed left-priority: the
    side whose expanded form appears MORE often in the raw text is the real
    term shape (蓝活通 recurs across contexts; 器蓝活/用蓝活 are locked to
    one neighbor char each). Fixed left-priority fragmented one trap into
    per-context variants and split its occurrence count (2026-08-23 review).
    `count` is a callable raw_text.count. Ties are undecidable at count=1
    (the corpus cannot tell which neighbor belongs to the term) and fall
    back left deterministically — a single-occurrence candidate may carry a
    stray neighbor char; the operator trims it at adjudication. High-frequency
    glue/verb chars (_GLUE_CHARS) never get absorbed, which resolves the
    common 用蓝活→用蓝付 shape before the tiebreak is even consulted.
    """
    while len(core_f) < min_len:
        options = []
        if left_eq and left_eq[-1] not in _GLUE_CHARS:
            options.append((count(left_eq[-1] + core_f), "L"))
        if right_eq and right_eq[0] not in _GLUE_CHARS:
            options.append((count(core_f + right_eq[0]), "R"))
        if not options:
            break
        options.sort(key=lambda x: -x[0])  # 同分稳定序 → L 先列先赢
        if options[0][1] == "L":
            core_f = left_eq[-1] + core_f
            core_t = left_eq[-1] + core_t
            left_eq = left_eq[:-1]
        else:
            core_f = core_f + right_eq[0]
            core_t = core_t + right_eq[0]
            right_eq = right_eq[1:]
    return (core_f, core_t)


def _latin_cut(s: str, cut: int) -> bool:
    """Would a cut at ``cut`` split an ASCII-alnum run?"""
    return (0 < cut < len(s)
            and s[cut - 1].isascii() and s[cut - 1].isalnum()
            and s[cut].isascii() and s[cut].isalnum())


def _common_affixes(from_span: str, to_span: str) -> tuple[int, int]:
    """Shared prefix/suffix lengths, never splitting a Latin/number run."""
    p = 0
    while p < min(len(from_span), len(to_span)) and from_span[p] == to_span[p]:
        p += 1
    while p and (_latin_cut(from_span, p) or _latin_cut(to_span, p)):
        p -= 1
    s = 0
    while s < min(len(from_span), len(to_span)) - p \
            and from_span[-1 - s] == to_span[-1 - s]:
        s += 1
    while s and (_latin_cut(from_span, len(from_span) - s)
                 or _latin_cut(to_span, len(to_span) - s)):
        s -= 1
    return p, s


_WORD_RUN = re.compile(r"[A-Za-z0-9]+|[一-鿿]+")


def _split_fused(core_f: str, core_t: str) -> list[tuple[str, str]] | None:
    """Split a fused region (entity fix + punct/paragraph change adjacent)
    into per-word-run sub-pairs.

    Adjacent edits fuse into ONE char-diff region (缺陷。\\n\\n新→确幸，旧 has no
    equal chars between the term change and the prose change). Zipping the
    word runs recovers the term pair (缺陷→确幸); when the two sides' word-run
    counts or separating punct-run counts disagree it is a prose rewrite that
    cannot be aligned — return None and drop the region rather than emit a
    newline-carrying unparsable bullet (the exit-2 all-or-nothing accident).
    """
    fw, tw = _WORD_RUN.findall(core_f), _WORD_RUN.findall(core_t)
    if not fw or len(fw) != len(tw):
        return None
    # 词 run 计数相等 → 标点 run 计数必相等（无捕获组时 split 件数恒为
    # 匹配数+1），无需二次检查
    return list(zip(fw, tw))


def _candidates_from_pair(from_span: str, to_span: str,
                          count=None) -> list[tuple[str, str]]:
    """Clause-level diff span -> minimal term-level candidate(s).

    - Common affixes are trimmed first (with Latin-run protection), so a
      mixed span like 点云小星派还没部署上去→点example还没部署上去 yields the
      term pair 云小星派→example, not the whole clause.
    - Cores still containing Latin/digits are emitted whole: Latin tokens
      carry their own word boundaries and finer trimming mangles them.
    - Pure-CJK cores are char-diffed; each replace region becomes its own
      candidate (a clause with two entity fixes yields two traps), widened
      by _expand so the disambiguating neighbor char (小/三/商…) survives.
    - Regions with interior punct/whitespace are split into word-run
      sub-pairs first (_split_fused); unalignable prose is dropped.
    """
    if count is None:
        count = lambda s: 0
    p, s = _common_affixes(from_span, to_span)
    end_f = len(from_span) - s if s else len(from_span)
    end_t = len(to_span) - s if s else len(to_span)
    core_f, core_t = from_span[p:end_f], to_span[p:end_t]
    if not core_f or not core_t:
        return []
    if re.search(r"[A-Za-z0-9]", core_f + core_t):
        return [(core_f, core_t)]
    lctx, rctx = from_span[:p], from_span[end_f:]
    sm = difflib.SequenceMatcher(None, core_f, core_t, autojunk=False)
    ops = sm.get_opcodes()
    out: list[tuple[str, str]] = []
    for idx, (op, i1, i2, j1, j2) in enumerate(ops):
        if op != "replace":
            continue
        # 可扩展上下文 = 紧邻的 equal 块本身（from/to 两侧内容一致），
        # 不是 prev.i2→cur.i1 的缝隙（相邻 opcode 的缝隙恒为空串）。
        if idx == 0:
            left_eq = lctx
        else:
            pop, pi1, pi2, _, _ = ops[idx - 1]
            left_eq = core_f[pi1:pi2] if pop == "equal" else ""
        if idx == len(ops) - 1:
            right_eq = rctx
        else:
            nop, ni1, ni2, _, _ = ops[idx + 1]
            right_eq = core_f[ni1:ni2] if nop == "equal" else ""
        region_f, region_t = core_f[i1:i2], core_t[j1:j2]
        if _PUNCT_CHARS.search(region_f) or _PUNCT_CHARS.search(region_t):
            sub_pairs = _split_fused(region_f, region_t)
            if sub_pairs is None:
                continue   # 散文改写，词 run 对不齐，丢弃该区域
        else:
            sub_pairs = [(region_f, region_t)]
        for k, (sf, st) in enumerate(sub_pairs):
            if _PUNCT_ONLY.match(sf) or _PUNCT_ONLY.match(st):
                continue
            # 只有区域的首/尾子对能借外侧 equal 上下文；中间子对的邻居
            # 两侧内容不同，不可作扩展上下文
            le = left_eq if k == 0 else ""
            re_ = right_eq if k == len(sub_pairs) - 1 else ""
            out.append(_expand(sf, st, le, re_, count))
    return out


# parser 对 TO 的硬拒字符（含其一整个 entry 不解析 → 自检 exit 2）。
# FROM 侧可带（反引号 quoted literal 是合法路径），TO 侧不行。
_TO_HARD_REJECT = re.compile(r"[，。；：、（）()\[\]【】\"'“”‘’`]")


def _keep(from_span: str, to_span: str) -> bool:
    """Noise filter: only term-level, content-changing replacements."""
    if not from_span or not to_span:
        return False
    if from_span == to_span:
        return False
    # term 级候选不含换行；跨段内容先经 _split_fused 对齐回收
    if "\n" in from_span or "\n" in to_span:
        return False
    if len(from_span) > _MAX_SPAN_CHARS or len(to_span) > _MAX_SPAN_CHARS:
        return False
    if _PUNCT_ONLY.match(from_span) or _PUNCT_ONLY.match(to_span):
        return False
    if _TO_HARD_REJECT.search(to_span):
        return False
    # parser 的 FROM 按 / 拆多 variant——含 / 的对无法表达，硬写会变成
    # 扫描裸 API/SDK 的错误 trap（_parses 只验「可解析」不验语义保真）
    if "/" in from_span or "/" in to_span:
        return False
    # 裸数字是数据不是词汇：3→2 / 401→402 进 context 后扫一切「3」
    if from_span.isdigit():
        return False
    # 1-2 字符纯 ASCII 同样无区分度
    if from_span.isascii() and len(from_span) < 3:
        return False
    # 一侧是另一侧子串 = 插入型错位（你好→你好世界），不是替换修正
    if from_span in to_span or to_span in from_span:
        return False
    # Punctuation/whitespace-only difference (e.g. comma swaps, spacing) —
    # the native pass normalizes these constantly; they are not traps.
    if _PUNCT_CHARS.sub("", from_span) == _PUNCT_CHARS.sub("", to_span):
        return False
    # 对齐幻影：长度悬殊且零相似 = difflib 把不相关文本配成对
    # （世界→然后走了）。等长全换是 CJK 实体错误的正常形态（缺陷→确幸
    # 音近但零共同字），不能按相似度杀；跨脚本口述→ASCII 转换
    # （点三溪派点→.example）无相似度地板，豁免。
    if not re.search(r"[A-Za-z0-9]", from_span + to_span):
        if abs(len(from_span) - len(to_span)) >= 2 and \
                difflib.SequenceMatcher(None, from_span, to_span).ratio() < 0.3:
            return False
    return True


def _quote(side: str) -> str:
    """Wrap in backticks iff the scanner's bare-variant contract needs it.

    Two triggers: special characters (_BAD_BARE), or length beyond the
    parser's bare-term cap (_MAX_TERM_LEN=12) — a quoted variant is an
    explicit literal and exempt from the cap, so quoting long forms keeps
    the bullet parseable instead of tripping the exit-2 self-check.
    """
    return f"`{side}`" if _BAD_BARE.search(side) or len(side) > 12 else side


def _bullet(from_span: str, to_span: str, cue: str) -> str:
    return f"- **{_quote(from_span)} → {_quote(to_span)}** — {cue}"


def _parses(bullet: str) -> bool:
    """Round-trip through the REAL parser: an emitted bullet that does not
    parse is a generator bug, not a context-file authoring error."""
    entries = extract_trap_entries(bullet + "\n")
    return len(entries) == 1 and entries[0].kind == "trap"


def _snippet(text: str, needle: str, width: int = 30) -> str:
    idx = text.find(needle)
    if idx < 0:
        return ""
    lo = max(0, idx - width)
    hi = min(len(text), idx + len(needle) + width)
    frag = text[lo:hi].replace("\n", " ").strip()
    return ("…" if lo > 0 else "") + frag + ("…" if hi < len(text) else "")


_TRAIL_PUNCT = ".,;:!?。，、；：？！…—·"


def harvest(raw: str, corrected: str) -> tuple[list[dict], int]:
    count = raw.count
    kept: dict[tuple[str, str], int] = {}
    dropped = 0
    for from_span, to_span in _extract_pairs(raw, corrected):
        for f, t in _candidates_from_pair(from_span, to_span, count):
            # 归一化：尾部游离标点（口述句读吸入 span，mch.example.）；反引号
            # 会破坏 bullet 语法，先剥掉
            f = f.rstrip(_TRAIL_PUNCT).replace("`", "").strip()
            t = t.rstrip(_TRAIL_PUNCT).replace("`", "").strip()
            if _keep(f, t):
                kept[(f, t)] = kept.get((f, t), 0) + 1
            else:
                dropped += 1
    # 包含聚类：f1 严格短于 f2 且 t1⊂t2 时（同一实体错误的宽窄两形），计数并入
    # 更短的那条——更短 = 复用面更大。from 相同而 to 不同的对**不**并入：
    # 那是两个不同修正，必须各自呈现给裁决。⚠️ 裸形（<_MIN_TRAP_LEN 纯 CJK）
    # 不作吸收方：否则好候选被并进裸形，--write 跳过裸形后两形全丢。
    merged: dict[tuple[str, str], int] = {}
    for (f, t), n in sorted(kept.items(), key=lambda kv: len(kv[0][0])):
        absorbed = False
        for (kf, kt) in merged:
            if len(kf) >= _MIN_TRAP_LEN or kf.isascii():
                if len(kf) < len(f) and kf in f and kt in t:
                    merged[(kf, kt)] += n
                    absorbed = True
                    break
        if not absorbed:
            merged[(f, t)] = merged.get((f, t), 0) + n
    out = []
    for (f, t), fixed in sorted(merged.items(), key=lambda kv: -kv[1]):
        out.append({
            "from": f,
            "to": t,
            "fixed": fixed,
            "raw_occurrences": raw.count(f),
            "remaining": corrected.count(f),
            "sample": _snippet(raw, f),
            # 扩展后仍 <3 的纯 CJK 候选 = 裸形（两侧都是黏着字扩不动），
            # 误伤面最大：--write 不自动写入，人工收紧后再入
            "bare": len(f) < _MIN_TRAP_LEN and not f.isascii(),
        })
    return out, dropped


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Harvest native-pass corrections into trap candidates.")
    ap.add_argument("raw", help="原始 ASR transcript")
    ap.add_argument("corrected", help="native pass 修完的 transcript")
    ap.add_argument("--context-file",
                    help="域 context 文件；提供时跳过已是文档化 trap 的对")
    ap.add_argument("--write", action="store_true",
                    help="把**高频组**候选追加进 --context-file（需要同时给该参数）")
    ap.add_argument("--write-all", action="store_true",
                    help="高频+单发全部追加（散文形伪候选也会进，慎用于未裁决批次）")
    ap.add_argument("--min-count", type=int, default=2,
                    help="高频组阈值（默认 2 = 出现 ≥2 次）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args()

    raw = Path(args.raw).read_text(encoding="utf-8")
    corrected = Path(args.corrected).read_text(encoding="utf-8")
    if raw == corrected:
        print("harvest: raw 与 corrected 完全一致，无可收获", file=sys.stderr)
        return 0

    candidates, dropped = harvest(raw, corrected)

    # 已在 context 文件里的 trap 不再报。双向包含即覆盖：context 有
    # 恒阳→恒央，候选 恒阳科→恒央科 是宽形，跳过；反向（已知宽 trap、
    # 候选窄形）同理——宽窄同体，哪边先命中都一样。
    known: list[tuple[str, str]] = []
    ctx_path: Path | None = None
    skipped_known = 0
    if args.context_file:
        ctx_path = Path(args.context_file).expanduser()
        if ctx_path.exists():
            ctx_text = ctx_path.read_text(encoding="utf-8")
            for e in extract_trap_entries(ctx_text):
                for v in e.from_variants:
                    if e.to_text:   # confirmed-correct（无 TO）不参与去重
                        known.append((v, e.to_text))
            before = len(candidates)
            candidates = [
                c for c in candidates
                if not any((kf in c["from"] or c["from"] in kf)
                           and (kt in c["to"] or c["to"] in kt)
                           for kf, kt in known)
            ]
            skipped_known = before - len(candidates)
        elif not args.write:
            print(f"harvest: ⚠️ --context-file 不存在：{ctx_path}"
                  f"（去重未生效；路径打错了？--write 会创建它）",
                  file=sys.stderr)

    today = date.today().isoformat()
    raw_name = Path(args.raw).name

    def to_bullet(c: dict) -> str:
        cue = (f"harvest {today} · raw 出现 {c['raw_occurrences']} 次、"
               f"已修 {c['fixed']}"
               + (f"、残留 {c['remaining']}" if c["remaining"] else ""))
        return _bullet(c["from"], c["to"], cue)

    bullets = [to_bullet(c) for c in candidates]
    # 自检：生成的每条 bullet 必须能被真 parser 解析——生成器 bug 当场炸，
    # 不允许把不可解析的行写进 context 文件（2026-08-22 某支付域 表格不解析
    # 事故的机械防线）。
    bad = [b for b in bullets if not _parses(b)]
    if bad:
        print("harvest BUG: 生成的 bullet 未通过 trap_scanner 解析：",
              file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        return 2

    hot = [c for c in candidates if c["fixed"] >= args.min_count]
    cold = [c for c in candidates if c["fixed"] < args.min_count]
    bare = [c for c in candidates if c["bare"]]

    if args.json:
        print(json.dumps({
            "candidates": candidates,
            "skipped_known": skipped_known,
            "dropped": dropped,
            "bullets": bullets,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"harvest: {len(candidates)} 个候选"
              f"（高频 {len(hot)} / 单发 {len(cold)}"
              + (f"，已跳过 context 已有 trap ×{skipped_known}" if skipped_known else "")
              + (f"，过滤丢弃 ×{dropped}" if dropped else "")
              + "）")
        if hot:
            print(f"\n## 高频（≥{args.min_count} 次）— 强候选")
            for c in hot:
                print(to_bullet(c) + ("  ⚠️ 裸形" if c["bare"] else ""))
                if c["sample"]:
                    print(f"    语境: {c['sample']}")
        if cold:
            print("\n## 单发 — 人工判断是否一次性")
            for c in cold:
                print(to_bullet(c) + ("  ⚠️ 裸形" if c["bare"] else ""))
                if c["sample"]:
                    print(f"    语境: {c['sample']}")
        if candidates:
            print("\n裁决后：真实反复 trap → 保留进 context 文件（--write 或手工）；"
                  "一次性改写 → 丢弃。残留 >0 的说明本轮没修干净，先回 transcript。"
                  + (f"\n⚠️ {len(bare)} 条裸形候选（<3 字纯 CJK，两侧黏着字扩不动）"
                     "误伤面大，--write 不自动写入，人工收紧后再入。" if bare else ""))

    if args.write or args.write_all:
        if ctx_path is None:
            print("Error: --write/--write-all 需要 --context-file", file=sys.stderr)
            return 2
        # 默认只自动写高频组：复现 = trap 的信号本身；单发候选（散文改写、
        # 一次性修正、真伪难辨）必须经人裁决——未裁决的单发被 --write 落进
        # context 后，下轮 trap-scan 会在干净文本上误报（二轮审阅实测）。
        pool = candidates if args.write_all else hot
        write_bullets = [to_bullet(c) for c in pool if not c["bare"]]
        skipped_cold = len([c for c in candidates if c not in pool]) if not args.write_all else 0
        if not write_bullets:
            print("\n--write: 无可写候选（高频组为空或全部裸形被跳过），"
                  "未改动 context 文件")
            return 0
        section = f"\n## Harvest 候选（{today} · {raw_name}）\n\n" + \
                  "\n".join(write_bullets) + "\n"
        if ctx_path.exists():
            prior = ctx_path.read_text(encoding="utf-8")
        else:
            prior = (f"# {ctx_path.stem} 语境\n\n"
                     f"（由 harvest_corrections.py 自动创建；"
                     f"业务背景/实体正字/人名源请补充）\n")
        ctx_path.parent.mkdir(parents=True, exist_ok=True)
        ctx_path.write_text(prior.rstrip("\n") + "\n" + section, encoding="utf-8")
        print(f"\n--write: {len(write_bullets)} 条候选已追加到 {ctx_path}"
              f"（Harvest 候选节；下一轮 --scan-traps 即可命中）"
              + (f"；跳过裸形 ×{len(bare)}" if bare else "")
              + (f"；单发 ×{skipped_cold} 未写（裁决后手工补或 --write-all）"
                 if skipped_cold else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
