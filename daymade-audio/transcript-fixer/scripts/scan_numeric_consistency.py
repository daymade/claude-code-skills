#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Flag places where a transcript's digits look damaged rather than merely wrong.

Two detectors, both narrow by design:
  * numeric-slot — a canonical term is sitting inside a number, which is what a
    replacement looks like when it overshoots its target (relabelling a speaker
    whose diarization label is a bare digit, or a dictionary rule that is too
    greedy). Needs --domain to know which terms count.
  * orphan-plus — "30+" in a transcript, where a spoken measure word ("30 家")
    or 多 ("三十多") most likely was.

Why a script rather than dictionary rules: a dictionary maps one wrong string to
one right string, which requires the error to be *stable*. Damaged digits are
not stable — the same replacement corrupts "21" and "3+1" and a date into three
different shapes — so only a scan over the text can find them. Numbers are worth
the trouble: the entity-level ASR literature consistently ranks numbers and
named entities as the worst-performing categories, with a numeral's continuation
tokens worse than its leading digit. (Exact percentages were not verified
against primary sources and are deliberately not quoted here.) The leading digit
is usually right and the tail is where it breaks, which is why a wrong number
still reads fluently.

What this deliberately does NOT do: judge whether two numbers *disagree*
("80 … also known as 800"). That was tried and rejected — on a 222-transcript
corpus it produced 280 hits and one true positive, because a speaker contrasting
two magnitudes is arithmetically identical to a dropped zero. It needs a
semantic read, which is the native AI pass's job; SKILL.md carries the reading
protocol for it.

Everything printed is a *candidate to read*, never an edit to apply. A check
that fires on healthy input teaches its operator to stop running it, so both
detectors are calibrated against a real 222-transcript corpus to stay quiet:
0.004 numeric-slot findings per file while still catching every known damage
shape. Three constraints came out of that calibration rather than the design —
bounded widening, digit-before-term only, metadata lines skipped — and each is
documented where it is enforced.

Prior art checked before writing this (so the next reader need not re-litigate it):
  - NVIDIA NeMo-text-processing (ITN) converts spoken form to written form
    ("eighty" -> 80). Our input already arrives as digits, and ITN does not
    compare two claims for agreement — different problem.
  - NIST SCTK / ROVER combines N>=2 aligned recognizer outputs by voting. That
    covers the *cross-system* half of this failure class, and it is the right
    tool for it — which is why this script does not reimplement it; SKILL.md
    points at the two-recording workflow instead.
  - belambert/asr-evaluation scores a hypothesis against a reference transcript.
    Having no reference is the premise of the problem.
No library was found that flags damaged digits inside a single transcript;
published practice is a manual "numbers QA pass".

Usage:
    # orphan-plus only (no dictionary needed)
    uv run scripts/scan_numeric_consistency.py transcript.md [more.md ...]
    # both detectors — --domain selects which canonical terms count as needles
    uv run scripts/scan_numeric_consistency.py transcript.md --domain myproject
    uv run scripts/scan_numeric_consistency.py transcript.md --domain a,b --json
    # point at a non-default dictionary
    uv run scripts/scan_numeric_consistency.py transcript.md --domain x --db /path/corrections.db

Without --domain the numeric-slot detector is silent (no needles are loaded);
this is a real result, not an error, so pass --domain when you want it.

Exit codes: 0 = no candidates, 1 = candidates found (not an error), 2 = bad usage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator

# A digit group immediately followed by '+'. In written Chinese this is a real
# idiom ("30+ 岁"), but in a *spoken* transcript nobody says "plus" — so it is
# almost always ASR standing in for a dropped measure word ("30家") or for 多
# ("三十多"). Both readings change the meaning, so it is worth one look.
#
# The trailing (?!\d) is load-bearing and was added after calibration, not
# designed in: without it every timezone offset in a frontmatter block
# ("15:34:25+0800", "13:29:42+08:00") reads as an orphan plus, which put two
# false positives on *every* file in the corpus. A check that fires on healthy
# input is the one people learn to stop running.
# NOTE the character class is spelled out instead of using \w: in Python 3 the
# \w class matches CJK, so (?<![\w.]) silently refused to match whenever a digit
# was preceded by a Chinese character — "总共30+家" scanned clean while
# "total 30+ customers" matched. In a Chinese transcript that is most of the
# real inputs; the corpus this was calibrated on happened to put spaces around
# its numbers, which is exactly how a hole like this stays invisible.
ORPHAN_PLUS = re.compile(r"(?<![0-9A-Za-z_.])(\d+(?:\.\d+)?)\+(?!\d)")

# Modal/polarity words that invert a numeric claim's meaning. NOT auto-flagged —
# see module docstring and the SKILL.md section; they are listed here so the
# report can name them when a human asks "what else should I read for?".
POLARITY_MARKERS = ("只能", "最多", "至多", "封顶", "不超过", "至少", "起码", "超过", "保底", "最少")


@dataclass
class Finding:
    kind: str
    line: int
    detail: str
    excerpt: str


def _excerpt(text: str, start: int, end: int, pad: int = 28) -> str:
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    return text[lo:hi].replace("\n", " ⏎ ").strip()


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def load_canonical_terms(db_path: Path, domains: list[str] | None = None) -> set[str]:
    """The canonical strings this toolchain writes INTO transcripts.

    Using them as the detector's needle list is the trick that makes the next
    scan precise instead of guessy: a replacement that overshot its target left
    one of *our own* canonical strings sitting where a digit belongs. Nobody has
    to enumerate "things that shouldn't touch a number" — the dictionary already
    is that list.
    """
    import sqlite3
    if not db_path.exists():
        # Deliberately NOT an empty set: "no needles loaded" and "loaded, found
        # nothing" print the same clean report, and a clean report on a scan
        # that never ran is the worst output this script could produce.
        raise FileNotFoundError(db_path)
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise RuntimeError(f"字典无法打开：{db_path}（{exc}）") from exc
    try:
        if domains:
            q = "SELECT DISTINCT to_text FROM active_corrections WHERE domain IN (%s)" % ",".join("?" * len(domains))
            try:
                rows = con.execute(q, domains).fetchall()
            except sqlite3.Error as exc:
                # A corrupt or schema-less file used to raise straight through
                # with exit 1 — the same code as "found candidates", so a caller
                # reading $? could not tell a crash from a result.
                raise RuntimeError(f"字典无法读取：{db_path}（{exc}）") from exc
        else:
            # Every domain's terms at once would let one project's vocabulary
            # judge another's numbers; the needle list has to be scoped the same
            # way the corrections that created it were.
            return set()
    finally:
        con.close()
    # Multi-character CJK only. A 1-char needle collides with ordinary text, and
    # a Latin one collides with units and IDs; both would reintroduce exactly the
    # noise that got the first version of this scanner deleted.
    return {r[0] for r in rows if r[0] and len(r[0]) >= 2 and re.fullmatch(r"[一-鿿]{2,}", r[0])}


def _body_only(text: str) -> str:
    """Blank out frontmatter and metadata lines, keeping offsets stable.

    Titles and filenames carry a leading date ("0620北岸分馆库存盘点"), which is
    a digit immediately followed by a term — structurally identical to the
    damage this looks for, and never actually damage.
    """
    out, in_fm = [], False
    for i, line in enumerate(text.split("\n")):
        if i == 0 and line.strip() == "---":
            in_fm = True
        elif in_fm and line.strip() == "---":
            in_fm = False
            out.append(" " * len(line)); continue
        if in_fm or re.match(r"\s*(title|date|note|participants|source|owner|duration)\s*:", line):
            out.append(" " * len(line))
        else:
            out.append(line)
    return "\n".join(out)


def scan_numeric_slot(text: str, terms: set[str]) -> Iterator[Finding]:
    """A canonical term is sitting where a digit should be.

    Shape of the real failure: someone relabels a speaker whose diarization label
    was the bare digit "1" by replacing that string globally. Speaker lines get
    fixed — and so does every 1 inside "3+1", "8.8 折", "21 册" and the date
    in the title. The transcript still reads fluently, which is why nobody
    notices: only the digits are wrong, and only where a number happened to
    contain that digit.

    The same signature covers a dictionary rule that overshot, and an ASR that
    heard a numeral as a word.
    """
    seen: set[int] = set()
    text = _body_only(text)
    for term in terms:
        for m in re.finditer(re.escape(term), text):
            # Widen to the surrounding CJK run before looking at the neighbours.
            # Without this the detector silently depends on the dictionary having
            # registered the *exact* injected form: a project that records the
            # short name ("辰社") while the writeback injects the full one
            # ("星辰社") would see every "2星辰社 册" as clean, because the
            # characters touching 辰社 are 王 and a space. Widening to the CJK
            # boundary makes the check depend on the text, not on which alias
            # someone happened to file.
            # Widening is BOUNDED to two characters per side, and that bound is
            # the whole ballgame. An unbounded walk to the CJK-run edge looked
            # more thorough and was catastrophically worse: "北岸分馆季度盘点前1页纸"
            # swallows the entire phrase, lands next to the 1, and reports a
            # clean line. Chinese puts digits after a run of characters
            # constantly, so an unbounded rule fires on ordinary text — 97 hits
            # across a healthy 222-file corpus, versus 46 real ones. Two
            # characters is enough for the surname prefix this needs to cross
            # ("辰社" registered, "星辰社" injected) and short enough that an
            # ordinary phrase cannot reach a neighbouring number.
            lo, hi = m.start(), m.end()
            for _ in range(2):
                if lo > 0 and re.match(r"[一-鿿]", text[lo - 1]):
                    lo -= 1
            for _ in range(2):
                if hi < len(text) and re.match(r"[一-鿿]", text[hi]):
                    hi += 1
            # A digit must sit immediately outside the widened span on the side
            # we widened toward — checked per side, so a number far off to the
            # left cannot license a match created by widening rightward.
            left_ok = any(
                re.match(r"[0-9.+]", text[i - 1: i])
                for i in range(lo, m.start() + 1)
                if i > 0 and text[i:m.start()] == text[i:m.start()].strip()
            )
            # Direction matters, and only one direction is evidence. Damage
            # looks like "2星辰社 册" — a digit followed by a term that split
            # the number from its measure word. The mirror image, a term
            # followed by a digit ("本季项目6周", "关键词出现38次"), is simply how
            # Chinese is written; matching it drowned the detector in ordinary
            # prose. So: digit-before-term only.
            if not left_ok:
                continue
            if lo in seen:          # one report per damaged slot, not per alias
                continue
            seen.add(lo)
            run = text[lo:hi]
            yield Finding(
                kind="numeric-slot",
                line=_line_of(text, lo),
                detail=f"「{run}」紧邻数字 — 数字位很可能被替换越界（如 21→2{run}、3+1→5+{run}）",
                excerpt=_excerpt(text, lo, hi),
            )


def scan_orphan_plus(text: str) -> Iterator[Finding]:
    for m in ORPHAN_PLUS.finditer(text):
        yield Finding(
            kind="orphan-plus",
            line=_line_of(text, m.start()),
            detail=f"「{m.group(0)}」— 口语不说「加号」，多半是量词被吞（30家/30个）或「多」（三十多）",
            excerpt=_excerpt(text, m.start(), m.end()),
        )


def scan(text: str, terms: set[str] | None = None) -> list[Finding]:
    found = list(scan_orphan_plus(text))
    if terms:
        found += list(scan_numeric_slot(text, terms))
    return sorted(found, key=lambda f: (f.line, f.kind))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--domain", action="append", default=None,
                    help="domain(s) whose canonical terms become numeric-slot needles; "
                         "repeatable AND comma-separated (--domain a,b), matching how "
                         "fix_transcription.py takes sibling domains")
    ap.add_argument("--db", type=Path, default=Path.home() / ".transcript-fixer" / "corrections.db")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    # Comma-separated form is accepted because SKILL.md teaches it for sibling
    # domains elsewhere; without this, "--domain a,b" silently looked up one
    # nonexistent domain named "a,b" and produced an empty, clean-looking scan.
    domains = [d for spec in (args.domain or []) for d in spec.split(",") if d.strip()] or None
    try:
        terms = load_canonical_terms(args.db, domains)
    except (RuntimeError, FileNotFoundError) as exc:
        msg = (f"字典不存在：{exc}" if isinstance(exc, FileNotFoundError) else str(exc))
        print(f"{msg}\nnumeric-slot 需要字典提供 needle 列表；这里退出，而不是打印一份\n"
              f"看起来干净、实际没扫的报告。orphan-plus 可单独跑：去掉 --domain。",
              file=sys.stderr)
        if args.json:
            # A caller parsing stdout unconditionally would otherwise get an
            # empty string here and have to guess whether that meant "clean".
            print(json.dumps({"_scan": {"error": msg, "needles_loaded": 0},
                              "findings": {}}, ensure_ascii=False, indent=2))
        return 2
    if domains and not terms:
        print(f"⚠️ domain {domains} 在字典里没有可用作 needle 的规范词"
              f"（需 >=2 字中文）；numeric-slot 这一轮等于没跑。", file=sys.stderr)
    if not domains:
        print("ℹ️ 未指定 --domain：只跑 orphan-plus。numeric-slot 需要 --domain "
              "指定用哪个项目的规范词做 needle。", file=sys.stderr)
    all_findings: dict[str, list[Finding]] = {}
    for path in args.files:
        if not path.is_file():
            print(f"skip (not a file): {path}", file=sys.stderr)
            continue
        findings = scan(path.read_text(encoding="utf-8", errors="replace"), terms)
        if findings:
            all_findings[str(path)] = findings

    if args.json:
        print(json.dumps({
            # Without this the caller cannot distinguish "scanned, nothing found"
            # from "scanned with zero needles loaded" — identical empty output.
            "_scan": {"domains": domains or [], "needles_loaded": len(terms),
                      "files_scanned": len(args.files)},
            "findings": {p: [asdict(f) for f in fs] for p, fs in all_findings.items()},
        }, ensure_ascii=False, indent=2))
    else:
        total = sum(len(v) for v in all_findings.values())
        if not total:
            print("✅ 未发现数字位受损或量词缺失的候选")
        for path, findings in all_findings.items():
            print(f"\n=== {path} ===")
            for f in findings:
                print(f"  L{f.line} [{f.kind}] {f.detail}")
                print(f"      …{f.excerpt}…")
        if total:
            print(f"\n{total} 个候选 — 这些是**待读**不是待改；"
                  f"逐条回到原句判断。拿不准时：同一场若有第二路独立 ASR，"
                  f"比对它；否则用 fetch_minute_audio.py 取音频听那个时间点。")
            print(f"极性反转（{'/'.join(POLARITY_MARKERS)}）本脚本不自动判，"
                  f"须人读：同场若另有语义相反的表述，以带限定词的那句为准。")

    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
