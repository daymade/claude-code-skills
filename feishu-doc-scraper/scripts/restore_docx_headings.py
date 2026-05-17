#!/usr/bin/env python3
"""Restore heading hierarchy and highlights lost when pandoc converts a
Feishu-exported .docx (Path B).

Feishu-exported docx does not use Word heading styles — it lays out headings
with font size + bold on normal paragraphs, and marks emphasis with run
shading (`w:shd@fill`), not `w:highlight`. pandoc therefore produces zero
Markdown headings (every heading becomes flat `**bold**`) and drops every
highlight. A text-level check ("no errors, word count matches") passes while
the document's entire structure is gone — only visual verification catches it.

This script repairs the pandoc Markdown WITHOUT retyping the body:
  * heading levels are derived from the docx's own font-size distribution
    (largest sizes -> H1..Hn, descending) and applied as `#` prefixes;
  * run shading fills are restored as Obsidian `==highlight==`.

Body text is never reconstructed — only `#` prefixes and `==` wrappers are
added to the existing pandoc lines. This keeps the API/pandoc text byte-exact
(the fidelity invariant) while giving back the structure a human sees.

Usage:
    python3 restore_docx_headings.py --docx SRC.docx --md PANDOC.md --out FINAL.md
    python3 restore_docx_headings.py --docx SRC.docx --md PANDOC.md --dry-run

`--dry-run` prints the derived size->level mapping and match counts without
writing — verify the plan before applying it (plan / validate / execute).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

try:
    from docx import Document
    from docx.oxml.ns import qn
except ModuleNotFoundError:
    sys.exit(
        "error: python-docx is not installed.\n"
        "  run with uv:  uv run --with python-docx python3 "
        "scripts/restore_docx_headings.py ...\n"
        "  or:           pip install python-docx"
    )

# Run-shading fills that are page/background, not emphasis. Everything else
# applied at run level by Feishu is an intentional highlight. Deriving
# "highlight = any non-background run fill" from the document avoids
# hard-coding specific colors; the values verified in practice were
# ffe928 (yellow) and 935af6 (purple) — kept here only as the known examples,
# not as a closed allow-list.
_BACKGROUND_FILLS = {"auto", "ffffff", "000000", ""}
_ZERO_WIDTH = "​‌‍﻿"


def _norm(s: str) -> str:
    """Normalize a line for cross-format text matching.

    pandoc may wrap a heading as `**text**`; the source paragraph is `text`.
    Strip emphasis/heading markers, zero-width chars, and collapse whitespace
    so the same logical line matches across the two representations.
    """
    s = s.translate({ord(c): None for c in _ZERO_WIDTH})
    s = re.sub(r"[*_#`]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _doc_default_pt(doc) -> float:
    """Resolve the document's default body point size.

    Critical: body paragraphs in a Feishu/pandoc docx frequently carry NO
    explicit run size — they inherit from the Normal style or docDefaults.
    If such paragraphs are bucketed as "unknown" and excluded, the modal
    size becomes a *heading* size and every real heading is demoted to body
    (verified failure). So every paragraph must get a numeric size, falling
    back to this resolved default, so the modal size is the true body size.

    Resolution order: Normal style -> docDefaults rPr sz -> 11.0pt.
    11.0pt is the de-facto Word default for the .docx era (Calibri 11); it
    is only the last resort when the file declares no default at all.
    """
    try:
        sz = doc.styles["Normal"].font.size
        if sz is not None:
            return sz.pt
    except (KeyError, AttributeError, ValueError):
        pass
    try:
        sz_el = doc.styles.element.find(
            qn("w:docDefaults") + "/" + qn("w:rPrDefault")
            + "/" + qn("w:rPr") + "/" + qn("w:sz")
        )
        if sz_el is not None:
            val = sz_el.get(qn("w:val"))
            if val:
                return int(val) / 2.0  # OOXML sz is in half-points
    except (AttributeError, ValueError, TypeError):
        pass
    return 11.0


def _para_font_pt(para, default_pt: float) -> float:
    """Effective point size of a paragraph — never None.

    Headings here have all runs at one large size. Take the max run size;
    fall back to the paragraph style's size; finally to the resolved
    document default so unsized body paragraphs land in the body bucket
    (not the 'unknown' void that corrupts the modal-size heuristic).
    """
    sizes = [r.font.size.pt for r in para.runs if r.font.size is not None]
    if sizes:
        return max(sizes)
    try:
        if para.style and para.style.font and para.style.font.size:
            return para.style.font.size.pt
    except (AttributeError, ValueError):
        pass
    return default_pt


def _run_highlight_fill(run) -> str | None:
    """Return the run's shading fill if it is an emphasis highlight, else None."""
    rpr = run._element.rPr
    if rpr is None:
        return None
    shd = rpr.find(qn("w:shd"))
    if shd is None:
        return None
    fill = (shd.get(qn("w:fill")) or "").lower()
    if fill in _BACKGROUND_FILLS:
        return None
    return fill


def build_plan(docx_path: Path):
    """Walk the docx once, returning the heading plan and highlight plan.

    heading_plan : list of (normalized_text, level, raw_text) in doc order
    highlight_plan: list of (normalized_text, [run_text, ...]) in doc order
    size_to_level: derived mapping for --dry-run reporting
    """
    try:
        doc = Document(str(docx_path))
    except Exception as exc:  # python-docx raises various errors for bad files
        sys.exit(f"error: cannot open docx ({exc}). Confirm with `file -b`; an "
                 f"exported .docx is sometimes mislabeled.")

    paras = list(doc.paragraphs)
    default_pt = _doc_default_pt(doc)

    # Every non-empty paragraph gets a numeric size (unsized -> resolved
    # default), so the modal size is the true body size. Sizes strictly
    # larger than body, descending, become H1..Hn.
    size_counts = Counter(
        round(_para_font_pt(p, default_pt), 1)
        for p in paras if p.text.strip()
    )
    if not size_counts:
        # No text paragraphs at all — nothing to restore; let the caller
        # pass the markdown through unchanged rather than abort.
        print("[restore] no text paragraphs in docx — passthrough.",
              file=sys.stderr)
        return [], [], {}, default_pt
    body_size = size_counts.most_common(1)[0][0]
    heading_sizes = sorted((s for s in size_counts if s > body_size), reverse=True)
    size_to_level = {s: i + 1 for i, s in enumerate(heading_sizes)}
    if not size_to_level:
        # One distinct size only: the doc has no font-size heading hierarchy
        # (it likely already uses Word heading styles, which doc-to-markdown
        # converts natively). Highlights may still need restoring, so warn
        # and continue rather than exit.
        print(f"[restore] no font-size hierarchy above body {body_size}pt — "
              f"doc likely uses Word heading styles already; restoring "
              f"highlights only.", file=sys.stderr)

    heading_plan, highlight_plan = [], []
    for p in paras:
        text = p.text.strip()
        if not text:
            continue
        lvl = size_to_level.get(round(_para_font_pt(p, default_pt), 1))
        if lvl:
            heading_plan.append((_norm(text), lvl, text))
        hi = [r.text for r in p.runs
              if r.text.strip() and _run_highlight_fill(r) is not None]
        if hi:
            highlight_plan.append((_norm(text), hi))

    return heading_plan, highlight_plan, size_to_level, body_size


def apply_plan(md_lines, heading_plan, highlight_plan):
    """Apply heading prefixes and highlight wrappers to the pandoc lines.

    Matching is by normalized text, in document order, with a forward-only
    cursor so repeated identical strings map to successive occurrences.
    Returns (new_lines, n_headings_applied, n_unmatched_headings,
    n_highlights_applied).
    """
    norm_lines = [_norm(l) for l in md_lines]
    out = list(md_lines)

    cursor = 0
    applied_h = unmatched_h = 0
    for ntext, level, _raw in heading_plan:
        if not ntext:
            continue
        found = -1
        for i in range(cursor, len(out)):
            if norm_lines[i] == ntext:
                found = i
                break
        if found == -1:
            unmatched_h += 1
            continue
        # Replace the whole line with a clean heading — drop pandoc's bold
        # since a heading must not also be `**...**`.
        out[found] = "#" * level + " " + ntext
        norm_lines[found] = ntext  # keep in sync for subsequent matches
        cursor = found + 1
        applied_h += 1

    cursor = 0
    applied_hl = 0
    for ntext, run_texts in highlight_plan:
        if not ntext:
            continue
        found = -1
        for i in range(cursor, len(out)):
            if norm_lines[i] == ntext:
                found = i
                break
        if found == -1:
            continue
        line = out[found]
        for rt in run_texts:
            rt = rt.strip()
            if not rt or rt not in line:
                continue
            if ("==" + rt + "==") in line:  # already wrapped
                continue
            line = line.replace(rt, "==" + rt + "==", 1)
        out[found] = line
        cursor = found + 1
        applied_hl += 1

    return out, applied_h, unmatched_h, applied_hl


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docx", required=True, help="the owner-exported source .docx")
    ap.add_argument("--md", required=True, help="first-pass pandoc/doc-to-markdown .md")
    ap.add_argument("--out", help="output path (required unless --dry-run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the size->level mapping and counts; do not write")
    args = ap.parse_args()

    docx_path, md_path = Path(args.docx), Path(args.md)
    if not docx_path.exists():
        sys.exit(f"error: docx not found: {docx_path}")
    if not md_path.exists():
        sys.exit(f"error: markdown not found: {md_path}")
    if not args.dry_run and not args.out:
        sys.exit("error: --out is required unless --dry-run")

    heading_plan, highlight_plan, size_to_level, body_size = build_plan(docx_path)

    print(f"[restore] body size = {body_size}pt (normal text)", file=sys.stderr)
    for sz, lvl in sorted(size_to_level.items(), key=lambda kv: -kv[0]):
        n = sum(1 for t in heading_plan if t[1] == lvl)
        print(f"[restore] {sz}pt -> H{lvl}  ({n} paragraphs)", file=sys.stderr)
    print(f"[restore] {len(highlight_plan)} paragraphs carry run highlights",
          file=sys.stderr)

    md_lines = md_path.read_text(encoding="utf-8").splitlines()
    new_lines, applied_h, unmatched_h, applied_hl = apply_plan(
        md_lines, heading_plan, highlight_plan
    )
    print(f"[restore] headings applied={applied_h} unmatched={unmatched_h}; "
          f"highlight lines applied={applied_hl}", file=sys.stderr)
    if unmatched_h:
        print(f"[restore] WARNING: {unmatched_h} heading paragraph(s) had no "
              f"matching Markdown line — inspect the source vs pandoc output "
              f"for those (often a table caption or an image-only paragraph).",
              file=sys.stderr)

    if args.dry_run:
        print("[restore] dry-run: nothing written.", file=sys.stderr)
        return

    out_path = Path(args.out)
    out_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[restore] wrote {out_path}. Next: visually verify against the docx "
          f"render (qlmanage / soffice --convert-to pdf) before accepting.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
