"""
Corpus Probe — measure a term's real-meaning frequency across a corpus.

SINGLE RESPONSIBILITY: count every occurrence of a term across a directory of
markdown transcripts and print per-file counts plus sampled context windows.

Why this exists: the dictionary's false-positive validators (jieba word
checks, common-word lists) can only answer "is this a real word in Chinese".
They cannot answer the question that actually decides a project-domain rule:
"when this word appears IN THIS PROJECT'S transcripts, is it ever the real
meaning?" That is an empirical question, and the evidence is one grep away —
but doing it by hand is two greps per candidate term (count + sample), which
is exactly the friction that made operators skip the measurement and argue
from intuition instead. Real case: four terms were asserted "safe to add as
bare rules" from intuition; a 30-second corpus sweep falsified all four (a
city name, a greeting word, a verb with heavy real usage). Measuring first is
now the documented gate; this command makes the measurement one invocation.

Advisory by design: the probe prints evidence, never a verdict. The decision
(all-error → bare rule OK / mixed → anchored form / real usage dominates →
do not add) stays with the operator reading the samples.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ProbeSample:
    file: str  # corpus-relative path
    line: int  # 1-based
    context: str  # snippet around the occurrence


@dataclass
class ProbeResult:
    term: str
    total: int = 0
    per_file: List[tuple[str, int]] = field(default_factory=list)
    samples: List[ProbeSample] = field(default_factory=list)


def probe_corpus(
    term: str,
    corpus_dir: Path,
    *,
    sample_per_file: int = 2,
    sample_total: int = 8,
    window: int = 15,
) -> ProbeResult:
    """Count `term` in every *.md under `corpus_dir` (recursive), sampling
    context windows for the operator to judge real-meaning vs ASR-error.

    Substring counting via str.count / str.find — terms are literal words,
    and a regex would invite metacharacter surprises for no benefit at this
    scale (dozens of files, tens of MB).
    """
    result = ProbeResult(term=term)
    corpus_dir = Path(corpus_dir)
    for path in sorted(corpus_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        count = text.count(term)
        if count == 0:
            continue
        rel = str(path.relative_to(corpus_dir))
        result.total += count
        result.per_file.append((rel, count))
        taken = 0
        for line_no, line in enumerate(text.splitlines(), start=1):
            if taken >= sample_per_file or len(result.samples) >= sample_total:
                break
            idx = line.find(term)
            if idx < 0:
                continue
            lo = max(0, idx - window)
            hi = idx + len(term) + window
            result.samples.append(ProbeSample(rel, line_no, line[lo:hi]))
            taken += 1
    return result


def format_probe(result: ProbeResult, corpus_dir: Path) -> str:
    """Human-readable probe report with the decision rule attached — the
    output is the gate, so the gate's criterion travels with the evidence.

    The sampling coverage is printed as part of the verdict aid: samples are
    capped (per-file and total) and drawn in file order, so "every sample is
    an ASR error" must never read as "every occurrence is" — an unsampled
    tail of the corpus was never shown, and the operator deserves to see how
    much of it there is."""
    out: List[str] = []
    out.append(f"probe: 「{result.term}」 in {corpus_dir}")
    out.append(f"  total: {result.total} occurrence(s) across {len(result.per_file)} file(s)")
    for rel, count in result.per_file:
        out.append(f"    {count:>4}  {rel}")
    if result.samples:
        sampled_files = {s.file for s in result.samples}
        out.append(f"  samples ({len(result.samples)} shown — from {len(sampled_files)} of "
                   f"{len(result.per_file)} file(s); caps: 2/file, 8 total, in file order):")
        for s in result.samples:
            out.append(f"    {s.file}:{s.line}: …{s.context}…")
    out.append("")
    if result.total == 0:
        out.append("  verdict aid: 0 occurrences — a bare rule is zero-risk here, but also "
                   "compounds nothing; confirm the term actually recurs before spending a rule. "
                   "(If you expected hits, check the corpus path — this result cannot tell "
                   "'absent' from 'never searched'.)")
    else:
        out.append("  verdict aid: read the samples — if every SAMPLED occurrence is an ASR "
                   "error, a bare rule is likely safe (mind the coverage line above: occurrences "
                   "in unsampled files were never inspected); ANY real meaning → anchored form "
                   "or do-not-add (record the trap in the domain context file instead).")
    return "\n".join(out)


def probe_to_json(result: ProbeResult) -> dict:
    return {
        "term": result.term,
        "total": result.total,
        "per_file": [{"file": f, "count": c} for f, c in result.per_file],
        "samples": [
            {"file": s.file, "line": s.line, "context": s.context}
            for s in result.samples
        ],
    }
