#!/usr/bin/env python3
"""Enumerate every rich-media reference in a fetched Feishu document body.

This is the recursion engine's core for Path A (lark-cli API extraction). A
collection/hub is a doc whose body references other docs; missing one
reference means a missing document — the single biggest hub-scraping failure.
Hand-rolled `grep | sed` pipelines repeatedly missed the `my.feishu.cn`
personal-space pattern, so this enumeration is centralized and tested here.

Covers: mention-doc (real raw tag is `<cite doc-id=... file-type=...
title=...>`, verified 2026-08-17 — see RE_CITE_TAG), sheet, image (real raw
tag is `<img src=... alt=...>`, verified 2026-08-17 — see RE_IMG_TAG), file,
whiteboard (`<whiteboard token=...>` — an inline diagram block, NOT a
followable reference, see DISPATCH["whiteboard"]), lark-table, and
cross-tenant / personal-space / Minutes / Tencent-Meeting URLs.

Input : the fetched Feishu body. On lark-cli builds where `.data.markdown` is
        non-null (<=1.0.32; unconfirmed whether still reachable on any
        current build, see SKILL.md Path A step 3), that Markdown is a valid
        input. Otherwise (`.data.markdown` is null -- the current default,
        verified null in 11/11 real documents checked including the
        currently-installed lark-cli 1.0.80) the body only reaches disk as
        raw HTML via `.data.document.content`; run this script on THAT saved
        `source.html`, never on the pandoc-converted `source.md` -- pandoc
        silently strips several of these tags with zero trace (whiteboard
        and mention-doc confirmed; see SKILL.md Path A step 3's callout).
Output: JSON array on stdout, one object per *distinct* reference:
        {"type": ..., "ref": <token-or-url>, "title": ..., "dispatch": <hint>}
        plus a human summary on stderr.

It only *enumerates*. Dispatching/fetching each reference is the caller's job
(see references/lark-cli-api-extraction.md, Step 5 dispatch table) -- except
`whiteboard`, which is never fetched or recursed, only exported and read as
an image (see SKILL.md Path A step 4).

Usage:
    python3 feishu_extract_refs.py FETCHED_BODY.html   # prefer the raw HTML
    python3 feishu_extract_refs.py FETCHED_BODY.md      # only if no .html was saved
    python3 feishu_extract_refs.py FETCHED_BODY.html --type docx   # filter
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Feishu/Lark hosts. feishu.cn = mainland tenants + my.feishu.cn personal space;
# larksuite.com = international Lark. Both serve the same /docx /wiki /sheets
# /minutes /base /file path scheme.
_HOST = r"[a-z0-9-]+\.(?:feishu\.cn|larksuite\.com)"

# Inline rich-media tags. Two eras coexist here: the pre-1.0.55 `.data.markdown`
# pseudo-tags this script originally assumed (RE_MENTION_DOC, RE_IMAGE_TAG --
# never observed in real raw HTML, but retained since nothing was verified
# about what that branch emits when it fires) and the verified 1.0.55+ raw
# `.data.document.content` HTML shapes (RE_CITE_TAG, RE_IMG_TAG) that replace
# them on the current default (pandoc) path. Run this script on source.html
# for the latter -- see the module docstring.

# --- mention-doc references -------------------------------------------------
# Verified 2026-08-17 (lark-cli 1.0.80, fresh fetch of a real hub doc; the
# same byte-identical tag structure independently corroborated in an
# archived 2026-07-25 fetch of a different doc -- 6 weeks apart, same
# doc-id) against real `.data.document.content` raw HTML: the tag is NOT
# `<mention-doc token="..." type="...">Title</mention-doc>`. It is an
# empty-bodied <cite> tag with the title in an ATTRIBUTE, not inner text:
#   <cite doc-id="FRigwwIkWiy5PSkBNiMcwN98nsY" file-type="wiki"
#         title="手工记录反馈维度" type="doc"></cite>
# Confirmed file-type values: "wiki", "docx" (both independently verified
# against real documents). `pandoc -f html -t gfm` makes this tag VANISH
# WITH ZERO TRACE -- not even the bare title text survives (worse than
# losing just the token/type) -- so this pattern is only useful against raw
# HTML (source.html), never against a pandoc-converted .md.
RE_CITE_TAG = re.compile(r'<cite\b(?=[^>]*\bdoc-id=)[^>]*>')
_ATTR_DOC_ID = re.compile(r'\bdoc-id="([^"]*)"')
_ATTR_FILE_TYPE = re.compile(r'\bfile-type="([^"]*)"')
_ATTR_TITLE = re.compile(r'\btitle="([^"]*)"')

# Legacy `<mention-doc token="..." type="...">Title</mention-doc>` pseudo-tag.
# Never observed in raw `.data.document.content` HTML across 11 real
# documents checked (2026-08-17) -- but nothing was verified about what the
# <=1.0.32 `.data.markdown` branch emits when it fires (no non-null
# `.data.markdown` response was found to inspect). Retained, not removed, as
# that branch's only coverage; costs zero false positives since this literal
# shape does not occur in raw HTML.
RE_MENTION_DOC = re.compile(
    r'<mention-doc\s+token="([^"]+)"\s+type="([^"]+)"\s*>([^<]*)</mention-doc>'
)

# --- sheet references --------------------------------------------------
# UNVERIFIED -- no real document containing an actual sheet/spreadsheet
# reference was found (9 real documents inspected, 2026-08-17). Left
# unchanged: do not guess-fix a pattern with no positive evidence. If sheet
# references turn out to use the same <cite file-type="sheet"> shape as
# mention-doc (a plausible but unconfirmed extrapolation), the
# "mention-doc-other" bucket below will still surface them with the real
# file-type value visible for manual triage, rather than silently
# mis-tagging them as a confirmed fact.
RE_SHEET_TAG = re.compile(r'<sheet\s+token="([^"]+)"\s*/?>')

# --- image references -------------------------------------------------------
# Verified 2026-08-17 (fresh fetch of a real docx, byte-identical to an
# archived 2026-07-25 fetch of the same doc) against real raw HTML: the tag
# is NOT `<image token="...">`. It is a standard-shaped self-closing <img>
# element with the drive token in `src=`, not `token=`:
#   <img id="..." name="filename.jpeg" alt="<long AI-generated description>"
#        height="1920" href="https://internal-api-drive-stream.feishu.cn/..."
#        mime="image/jpeg" scale="0.288889" src="TP29bjDJSoUsilxKjiLcGi3UnTh"
#        width="1080"/>
# Unlike mention-doc, this does NOT vanish under pandoc: `pandoc -f html -t
# gfm` re-serializes the whole <img> as raw HTML passthrough (src/id/href/
# width/height/alt survive verbatim; `name=` is dropped; `mime=`/`scale=` are
# renamed `data-mime=`/`data-scale=` -- observed once cleanly, not proven
# universal across pandoc versions). So this pattern also works against a
# pandoc-converted source.md in practice, but source.html remains the one to
# trust (unlike RE_CITE_TAG above, which does NOT survive pandoc at all).
RE_IMG_TAG = re.compile(r'<img\b(?=[^>]*\bsrc=)[^>]*>')
_ATTR_SRC = re.compile(r'\bsrc="([^"]*)"')

# Legacy `<image token="...">` pseudo-tag. Never observed in raw HTML (same
# caveat as RE_MENTION_DOC above: retained as the <=1.0.32 `.data.markdown`
# branch's only coverage, not removed).
RE_IMAGE_TAG = re.compile(r'<image\s+token="([^"]+)"')

# NOT independently researched (out of the 2026-08-17 investigation's
# scope). Left unchanged pending real evidence, same posture as
# RE_SHEET_TAG above.
RE_FILE_TAG = re.compile(r'<file\s+token="([^"]+)"[^>]*>([^<]*)</file>')

# --- whiteboard (inline diagram, NOT a followable reference) ----------------
# Verified 2026-08-16 against a real document (3 tags in raw HTML, 0 trace
# in the pandoc-converted .md of the same doc). This is Feishu's native
# diagram/flowchart block, inlined in the current doc -- it is never
# fetched/recursed like mention-doc/sheet; see DISPATCH["whiteboard"] and
# SKILL.md Path A step 4 for the export+Read handling.
RE_WHITEBOARD = re.compile(r'<whiteboard\s+token="([^"]+)"')

# --- inline tables -----------------------------------------------------
# Verified 2026-08-17: ordinary docx tables use plain, standard HTML5
# `<table>` markup, NOT a custom `<lark-table>` tag (0 occurrences of
# `<lark-table` across 9 real documents inspected). Contrary to the original
# assumption, pandoc does NOT collapse them into unstructured run-together
# text: tables whose cells hold single-paragraph content convert cleanly to
# GFM pipe-table syntax; tables with multi-paragraph cells fall back to a
# single embedded raw `<table>...</table>` HTML block (still structurally a
# table, just not pipe-syntax) -- observed in one real document (8 tables),
# not proven universal (colspan/rowspan not present in that sample). Because
# ordinary tables are common and mostly survive intact, this regex is
# deliberately NOT repointed at bare `<table` -- every healthy document has
# `<table>` tags, so that would turn the acceptance-gate check (SKILL.md
# Path A step 5) into constant false positives on completely healthy
# extractions. Left matching the literal (and, per this evidence, likely
# nonexistent-in-this-form) `<lark-table` tag, which costs nothing since it
# was already never observed to fire on real content; it may name an
# embedded Bitable/Base-view object not yet encountered, or may not exist in
# the current Feishu docx export format at all.
RE_LARK_TABLE = re.compile(r"<lark-table\b")

# URLs that appear in the body (cross-tenant / personal space / minutes /
# Tencent Meeting). One regex covers mainland, international and personal
# (my.feishu.cn) because the host group accepts any sub-domain.
RE_FEISHU_URL = re.compile(
    r"https://(" + _HOST + r")/(docx|wiki|sheets|base|file|minutes)/([A-Za-z0-9]+)"
)
RE_TENCENT_MEETING = re.compile(
    r"https://meeting\.tencent\.com/crm/([A-Za-z0-9]+)"
)

# How the caller should handle each type (mirrors the reference's dispatch
# table, surfaced here so the caller does not have to re-derive it).
DISPATCH = {
    "mention-doc-docx": "docs +fetch --doc <token>",
    "mention-doc-wiki": "wiki spaces get_node then docs +fetch",
    "mention-doc-sheet": "sheets +read",  # not currently produced -- see mention-doc-other; kept for when sheet's real <cite> shape is confirmed
    "mention-doc-other": "unconfirmed file-type on a real <cite> tag — inspect manually (sheet/bitable is a plausible but UNVERIFIED guess, see RE_SHEET_TAG comment)",
    "url-docx": "docs +fetch --doc <token>",
    "url-wiki": "wiki spaces get_node then docs +fetch",
    "url-sheets": "sheets +read (split token on '_' -> SP, SID)",
    "url-base": "Bitable API (outside this skill) — record token",
    "url-file": "attachment — record token + name; treat like image gap",
    "url-minutes": "native transcript API (feishu-minutes-transcript.md)",
    "sheet-tag": "sheets +read (split token on '_' -> SP, SID)",
    "image": "register token; lark-cli cannot download docx images",
    "file": "attachment — record token + name; treat like image gap",
    "tencent-meeting": "Tencent Meeting native transcript (never download+re-ASR)",
    "lark-table": "inline content — render in place to a Markdown table",
    "whiteboard": "export preview + Read image (see SKILL.md Path A step 4) — NOT a followable reference",
}


def _read_text(path: Path) -> str:
    """Read the body strictly as UTF-8.

    We deliberately do NOT use errors='replace': a decode failure means an
    upstream step corrupted the text, and the skill's acceptance contract
    checks for U+FFFD. Masking it here would hide exactly the failure the
    pipeline is trying to detect, so fail loudly instead.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        sys.exit(f"error: file not found: {path}")
    except PermissionError:
        sys.exit(f"error: cannot read (permission): {path}")
    if not raw.strip():
        sys.exit(f"error: file is empty: {path} (fetch likely failed upstream)")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        sys.exit(
            f"error: {path} is not valid UTF-8 ({exc}); an upstream extraction "
            f"step corrupted the body — re-fetch with `lark-cli docs +fetch "
            f"--format json` and re-derive source.html/.md per SKILL.md Path A "
            f"step 3, do not 'fix' encoding here."
        )


def extract(text: str) -> list[dict]:
    refs: list[dict] = []

    # Legacy `.data.markdown`-era pseudo-tag (never observed in real raw
    # HTML — see RE_MENTION_DOC comment). Retained for that branch only.
    for token, doc_type, title in RE_MENTION_DOC.findall(text):
        t = doc_type.strip().lower()
        kind = "mention-doc-sheet" if t in ("sheet", "bitable") else (
            "mention-doc-wiki" if t == "wiki" else "mention-doc-docx"
        )
        refs.append({
            "type": kind,
            "ref": token,
            "title": title.strip(),
            "dispatch": DISPATCH[kind],
        })

    # Verified 1.0.55+ raw-HTML shape (see RE_CITE_TAG comment above). This
    # is what actually fires against real source.html today.
    for tag in RE_CITE_TAG.findall(text):
        doc_id_m = _ATTR_DOC_ID.search(tag)
        if not doc_id_m:
            continue  # lookahead guarantees doc-id is present; stay defensive
        doc_id = doc_id_m.group(1)
        file_type_m = _ATTR_FILE_TYPE.search(tag)
        file_type = file_type_m.group(1).strip().lower() if file_type_m else ""
        title_m = _ATTR_TITLE.search(tag)
        title = title_m.group(1).strip() if title_m else ""

        if file_type == "wiki":
            kind, dispatch = "mention-doc-wiki", DISPATCH["mention-doc-wiki"]
        elif file_type == "docx":
            kind, dispatch = "mention-doc-docx", DISPATCH["mention-doc-docx"]
        else:
            # Includes the unverified "sheet"/"bitable" hypothesis (see
            # RE_SHEET_TAG comment above) and any other value — surfaced for
            # manual triage rather than guess-classified as a confirmed fact.
            kind = "mention-doc-other"
            dispatch = f"unconfirmed file-type={file_type!r} on a real <cite> tag — inspect manually"

        refs.append({
            "type": kind,
            "ref": doc_id,
            "title": title,
            "dispatch": dispatch,
        })

    for token in RE_SHEET_TAG.findall(text):
        refs.append({
            "type": "sheet-tag",
            "ref": token,
            "title": "",
            "dispatch": DISPATCH["sheet-tag"],
        })

    # Legacy `.data.markdown`-era pseudo-tag (never observed in real raw
    # HTML — see RE_IMAGE_TAG comment). Retained for that branch only.
    for token in RE_IMAGE_TAG.findall(text):
        refs.append({
            "type": "image",
            "ref": token,
            "title": "",
            "dispatch": DISPATCH["image"],
        })

    # Verified 1.0.55+ raw-HTML shape (see RE_IMG_TAG comment above). This
    # is what actually fires against real source.html/source.md today.
    for tag in RE_IMG_TAG.findall(text):
        src_m = _ATTR_SRC.search(tag)
        if not src_m:
            continue  # lookahead guarantees src is present; stay defensive
        refs.append({
            "type": "image",
            "ref": src_m.group(1),
            "title": "",
            "dispatch": DISPATCH["image"],
        })

    for token in RE_WHITEBOARD.findall(text):
        refs.append({
            "type": "whiteboard",
            "ref": token,
            "title": "",
            "dispatch": DISPATCH["whiteboard"],
        })

    for token, name in RE_FILE_TAG.findall(text):
        refs.append({
            "type": "file",
            "ref": token,
            "title": name.strip(),
            "dispatch": DISPATCH["file"],
        })

    for host, seg, token in RE_FEISHU_URL.findall(text):
        kind = f"url-{seg}"
        refs.append({
            "type": kind,
            "ref": f"https://{host}/{seg}/{token}",
            "title": "",
            "dispatch": DISPATCH.get(kind, "record token"),
        })

    for mid in RE_TENCENT_MEETING.findall(text):
        refs.append({
            "type": "tencent-meeting",
            "ref": f"https://meeting.tencent.com/crm/{mid}",
            "title": "",
            "dispatch": DISPATCH["tencent-meeting"],
        })

    n_tables = len(RE_LARK_TABLE.findall(text))
    if n_tables:
        # Inline content, not a link to follow — surfaced so the caller knows
        # to render it in place (pandas.read_html handles colspan/rowspan).
        refs.append({
            "type": "lark-table",
            "ref": f"(inline x{n_tables})",
            "title": "",
            "dispatch": DISPATCH["lark-table"],
        })

    # De-duplicate on (type, ref); keep first title seen.
    seen: dict[tuple[str, str], dict] = {}
    for r in refs:
        key = (r["type"], r["ref"])
        if key not in seen:
            seen[key] = r
    return list(seen.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("markdown_file", help="fetched Feishu body (.html preferred, .md if no .html was saved)")
    ap.add_argument("--type", help="only emit refs of this type (e.g. docx, image)")
    args = ap.parse_args()

    text = _read_text(Path(args.markdown_file))
    refs = extract(text)
    if args.type:
        refs = [r for r in refs if args.type in r["type"]]

    json.dump(refs, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")

    # Summary to stderr so stdout stays pure JSON for piping.
    by_type: dict[str, int] = {}
    for r in refs:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    if by_type:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(by_type.items()))
        print(f"[feishu_extract_refs] {len(refs)} distinct refs: {summary}",
              file=sys.stderr)
    else:
        print("[feishu_extract_refs] no references found — this is a leaf doc "
              "(nothing further to recurse).", file=sys.stderr)


if __name__ == "__main__":
    main()
