#!/usr/bin/env python3
"""Enumerate every rich-media reference in a fetched Feishu Markdown body.

This is the recursion engine's core for Path A (lark-cli API extraction). A
collection/hub is a doc whose body references other docs; missing one
reference means a missing document — the single biggest hub-scraping failure.
Hand-rolled `grep | sed` pipelines repeatedly missed the `my.feishu.cn`
personal-space pattern, so this enumeration is centralized and tested here.

Input : a Markdown file produced by `lark-cli docs +fetch ... | jq -r .data.markdown`.
Output: JSON array on stdout, one object per *distinct* reference:
        {"type": ..., "ref": <token-or-url>, "title": ..., "dispatch": <hint>}
        plus a human summary on stderr.

It only *enumerates*. Dispatching/fetching each reference is the caller's job
(see references/lark-cli-api-extraction.md, Step 5 dispatch table).

Usage:
    python3 feishu_extract_refs.py FETCHED_BODY.md
    python3 feishu_extract_refs.py FETCHED_BODY.md --type docx   # filter
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

# Inline rich-media tags emitted by `docs +fetch` Markdown.
RE_MENTION_DOC = re.compile(
    r'<mention-doc\s+token="([^"]+)"\s+type="([^"]+)"\s*>([^<]*)</mention-doc>'
)
RE_SHEET_TAG = re.compile(r'<sheet\s+token="([^"]+)"\s*/?>')
RE_IMAGE_TAG = re.compile(r'<image\s+token="([^"]+)"')
RE_FILE_TAG = re.compile(r'<file\s+token="([^"]+)"[^>]*>([^<]*)</file>')
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
    "mention-doc-sheet": "sheets +read",
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
            f"--format json` and `jq -r .data.markdown`, do not 'fix' encoding here."
        )


def extract(text: str) -> list[dict]:
    refs: list[dict] = []

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

    for token in RE_SHEET_TAG.findall(text):
        refs.append({
            "type": "sheet-tag",
            "ref": token,
            "title": "",
            "dispatch": DISPATCH["sheet-tag"],
        })

    for token in RE_IMAGE_TAG.findall(text):
        refs.append({
            "type": "image",
            "ref": token,
            "title": "",
            "dispatch": DISPATCH["image"],
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
    ap.add_argument("markdown_file", help="fetched Feishu body (.md)")
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
