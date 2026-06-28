#!/usr/bin/env python3
"""
Uncertain ASR Extractor

SINGLE RESPONSIBILITY: Find likely ASR errors in transcripts without changing text.

Heuristics:
- Short all-caps tokens embedded in Chinese text (e.g. APR, EM, WELL)
- Chinese transliteration fragments that don't form real words
- Repeated words / filler stacks
- Mixed Chinese-English gibberish
- Numbers that look like misheard terms
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class UncertainCandidate:
    """A candidate ASR error with context."""
    line_number: int
    text: str
    reason: str
    suggestion: str | None = None


class UncertainExtractor:
    """Extract likely ASR errors from transcript text."""

    # Short all-caps tokens that are suspicious in Chinese text.
    # Excludes common legitimate acronyms (AI, API, UI, OK, CEO, CTO, etc.).
    SUSPICIOUS_ACRONYM_RE = re.compile(
        r"(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])"
    )
    ALLOWED_ACRONYMS = {
        "AI", "API", "UI", "UX", "OK", "CEO", "CTO", "CFO", "COO",
        "PM", "QA", "DB", "SQL", "HTTP", "HTTPS", "URL", "JSON",
        "YAML", "XML", "HTML", "CSS", "JS", "TS", "SDK", "CLI",
        "GPU", "CPU", "RAM", "SSD", "OSS", "SaaS", "PaaS", "IaaS",
        "VPN", "DNS", "IP", "TCP", "UDP", "SSH", "FTP", "SMTP",
        "AWS", "GCP", "Azure", "IBM", "SAP", "Oracle", "Microsoft",
        "PDF", "PNG", "JPG", "GIF", "MP3", "MP4", "CSV", "TSV",
        "LLM", "ML", "NLP", "CV", "RL", "RAG", "MCP",
        "PR", "MR", "CI", "CD", "IDE", "REPL", "CRUD", "MVP",
        "OKR", "KPI", "ROI", "GMV", "SKU", "SPU", "SOP",
    }

    # Chinese transliteration-like patterns: foreign-sounding combos or 音译 markers.
    TRANSLITERATION_RE = re.compile(
        r"[一-鿿]{2,4}[一-鿿]?(?:\s+)[a-zA-Z]{2,}"  # e.g. 爱马仕 Agent
        r"|[a-zA-Z]{2,}(?:\s+)[一-鿿]{2,4}"  # e.g. Agent 团队
        r"|阿[a-zA-Z一-鿿]{1,4}"  # e.g. 阿帕奇, 阿 Peer
        r"|(?:克劳|科劳|科劳德|克劳德|克劳锐)"  # Claude variants
    )

    # Repeated words (filler or ASR stutter)
    REPEATED_WORD_RE = re.compile(
        r"([一-鿿]{1,4})\1{2,}"  # 这个这个这个
        r"|(\w{2,})\2{2,}"  # okokok
    )

    def __init__(self, known_terms: dict[str, str] | None = None):
        """
        Args:
            known_terms: Optional mapping of already-known ASR variants to correct terms.
                         Used to mark candidates with suggestions.
        """
        self.known_terms = known_terms or {}

    def extract(self, text: str) -> List[UncertainCandidate]:
        """
        Extract uncertain candidates from text.

        Returns:
            List of candidates sorted by line number, deduplicated.
        """
        candidates: dict[Tuple[int, str], UncertainCandidate] = {}

        for line_num, line in enumerate(text.split("\n"), start=1):
            line_candidates = self._extract_from_line(line_num, line)
            for c in line_candidates:
                key = (c.line_number, c.text)
                if key not in candidates:
                    candidates[key] = c

        return sorted(candidates.values(), key=lambda c: c.line_number)

    def _extract_from_line(self, line_number: int, line: str) -> List[UncertainCandidate]:
        """Extract candidates from a single line."""
        candidates: List[UncertainCandidate] = []

        # 1. Suspicious all-caps tokens
        for match in self.SUSPICIOUS_ACRONYM_RE.finditer(line):
            token = match.group(1)
            if token in self.ALLOWED_ACRONYMS:
                continue
            # Skip if surrounded by English sentence (probably legit)
            if self._is_in_english_context(line, match.start(), match.end()):
                continue
            candidates.append(UncertainCandidate(
                line_number=line_number,
                text=token,
                reason="短全大写标记，可能是英文术语被 ASR 误听",
                suggestion=self.known_terms.get(token),
            ))

        # 2. Transliteration-like fragments
        for match in self.TRANSLITERATION_RE.finditer(line):
            fragment = match.group(0)
            # Skip if it exactly matches a known correction source
            if fragment in self.known_terms:
                continue
            candidates.append(UncertainCandidate(
                line_number=line_number,
                text=fragment,
                reason="中英混杂或音译片段，可能是 ASR 错误",
                suggestion=self.known_terms.get(fragment),
            ))

        # 3. Repeated words
        for match in self.REPEATED_WORD_RE.finditer(line):
            word = match.group(1) or match.group(2)
            candidates.append(UncertainCandidate(
                line_number=line_number,
                text=word,
                reason="重复堆叠，可能是口癖或 ASR 抖动",
            ))

        return candidates

    @staticmethod
    def _is_in_english_context(line: str, start: int, end: int) -> bool:
        """
        Heuristic: if the token is in a mostly-English phrase, it's probably legit.
        Check if neighbors are ASCII words/spaces.
        """
        window = 30
        left = max(0, start - window)
        right = min(len(line), end + window)
        context = line[left:right]
        ascii_chars = sum(1 for c in context if ord(c) < 128)
        if len(context) == 0:
            return False
        return ascii_chars / len(context) > 0.7


def format_uncertain_report(candidates: List[UncertainCandidate]) -> str:
    """Format candidates as a markdown report."""
    if not candidates:
        return "# Uncertain ASR Candidates\n\nNo uncertain candidates found.\n"

    lines = ["# Uncertain ASR Candidates", ""]
    lines.append(f"Found {len(candidates)} candidate(s) that may need human review.\n")

    for i, c in enumerate(candidates, start=1):
        lines.append(f"## {i}. Line {c.line_number}")
        lines.append(f"- **Text**: `{c.text}`")
        lines.append(f"- **Reason**: {c.reason}")
        if c.suggestion:
            lines.append(f"- **Suggestion**: `{c.suggestion}`")
        lines.append("")

    return "\n".join(lines)
