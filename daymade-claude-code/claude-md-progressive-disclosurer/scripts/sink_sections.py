#!/usr/bin/env python3
"""Verbatim whole-section sink for CLAUDE.md progressive disclosure (SKILL.md Step 3).

For each section in the spec: extract [start_heading, end_heading) from the source
(exact-line match, code-fence-aware) -> append verbatim to the target reference under
a dated provenance header (new files get an intro) -> replace the L1 range with the
compressed snippet, bottom-up so earlier line numbers stay valid -> verify every
original is a WHOLE-BYTE-STRING substring of its target (grep ORs per line and would pass
a lossy move) -> roll the source back if any check fails.

Hard rules encoded here (each learned in real use — Case 19):
  - REFUSES targets whose path crosses a symlink at ANY component — the file
    itself OR any parent directory (checked as realpath != abspath; a file-only
    islink() check was bypassed in review by a symlinked parent dir). A symlinked
    target means your "local" append actually edits whatever repo it points into
    (its version-bump/commit obligations, possibly public). Sink to a local
    sibling file instead and note the merge-later — or pass
    --allow-symlinked-target when the hop is deliberate (e.g. macOS /tmp).
  - Extract everything first (original line numbers), then splice bottom-up.
  - Fail-fast on missing/suspiciously-small snippets BEFORE writing anything.
  - Each snippet retains its start heading exactly once outside code fences.
  - All target parents/types are checked before any reference is written.
  - Timestamped backups of the source and every touched existing target.
  - Headings used as boundaries must be UNIQUE in the source (ambiguity aborts).

Spec (JSON):
{
  "source": "path/to/CLAUDE.md",
  "sections": [
    {
      "key": "short-id",
      "start_heading": "### Exact Heading Line",
      "end_heading": "### Next Heading Line (exclusive; OMIT for a last-section-to-EOF sink)",
      "snippet_file": "compressed replacement. MUST retain the original start_heading as exactly one complete heading line outside code fences; checked before writing and after splicing",
      "target_ref": "path/to/reference.md",
      "provenance_title": "Section name for the archive header",
      "new_file_intro": "# Title\\n\\n> optional; written only when target_ref is new\\n"
    }
  ]
}

Prior art (searched 2026-08): mdsplit (github.com/markusstraub/mdsplit) splits a
whole file into per-heading files with fidelity guarantees, but has no notion of
sinking SELECTED sections into EXISTING topical references, in-place L1
replacement, whole-string verification, rollback, or the symlink guard — the
migration contract this script exists for. This is not a multi-file transaction:
verification failure restores the source but keeps reference appends for inspection;
unexpected I/O failures may also leave partial appends. Stdlib-only by design.

Usage:
    python3 sink_sections.py <spec.json> [--min-snippet-bytes 200]
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import sys

from markdown_headings import line_text, parse_headings, split_markdown_lines


def find_heading(lines, heading):
    """All exact full-line matches, skipping fenced code blocks."""
    return [i for i, _, _ in parse_headings(lines) if line_text(lines[i]) == heading]


def find_unique_heading(lines, heading, key, role):
    hits = find_heading(lines, heading)
    if not hits:
        sys.exit(f"ABORT: {role} heading not found [{key}]: {heading[:60]}")
    if len(hits) > 1:
        sys.exit(f"ABORT: {role} heading ambiguous [{key}] — appears {len(hits)}x "
                 f"(lines {', '.join(str(h+1) for h in hits)}): {heading[:60]}")
    return hits[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('spec')
    ap.add_argument('--min-snippet-bytes', type=int, default=200,
                    help='abort if a compressed snippet is smaller than this (default 200)')
    ap.add_argument('--allow-symlinked-target', action='store_true',
                    help='permit a target whose path crosses a symlink (deliberate hops only, '
                         'e.g. macOS /tmp -> /private/tmp); default aborts')
    args = ap.parse_args()

    with open(args.spec, encoding='utf-8') as spec_file:
        spec = json.load(spec_file)
    src_path = spec['source']
    sections = spec['sections']

    # ---- fail-fast preflight: snippets exist & are not stubs -------------------
    snippets = {}
    for s in sections:
        p = s['snippet_file']
        if not os.path.isfile(p):
            sys.exit(f"ABORT: snippet missing: {p}")
        text = Path(p).read_bytes().decode('utf-8')
        if len(text.strip().encode('utf-8')) < args.min_snippet_bytes:
            sys.exit(f"ABORT: snippet suspiciously small (<{args.min_snippet_bytes}B): {p}")
        find_unique_heading(split_markdown_lines(text), s['start_heading'],
                            s['key'], 'snippet start')
        snippets[s['key']] = text

    src = Path(src_path).read_bytes()
    lines = split_markdown_lines(src.decode('utf-8'))
    # New separator lines follow the source convention. Existing source and
    # snippet lines retain their own terminators and trailing whitespace.
    newline = next((line[len(line_text(line)):] for line in lines
                    if line_text(line) != line), '\n')

    # ---- locate all boundaries in ORIGINAL coordinates -------------------------
    bounds = []
    for s in sections:
        a = find_unique_heading(lines, s['start_heading'], s['key'], 'start')
        if s.get('end_heading'):
            b = find_unique_heading(lines, s['end_heading'], s['key'], 'end')
        else:
            b = len(lines)  # omitted end_heading = sink through EOF
        if b <= a:
            sys.exit(f"ABORT: boundary fail [{s['key']}]: start={a} end={b}")
        bounds.append((s, a, b))
    for (s1, a1, b1), (s2, a2, b2) in zip(sorted(bounds, key=lambda x: x[1]),
                                          sorted(bounds, key=lambda x: x[1])[1:]):
        if b1 > a2:
            sys.exit(f"ABORT: overlap [{s1['key']}] and [{s2['key']}]")

    # ---- preflight ALL target paths before any backup or reference write -------
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    for s, _, _ in bounds:
        tgt = s['target_ref']
        literal, resolved = os.path.abspath(tgt), os.path.realpath(tgt)
        if resolved != literal and not args.allow_symlinked_target:
            sys.exit(f"ABORT: target path crosses a symlink: {tgt}\n"
                     f"  literal : {literal}\n"
                     f"  resolves: {resolved}\n"
                     f"  A symlinked component (file OR parent dir) silently edits whatever repo it\n"
                     f"  points into. Sink to a local sibling file and note the merge-later task —\n"
                     f"  or re-run with --allow-symlinked-target if this hop is deliberate.")
        if not os.path.isdir(os.path.dirname(literal)):
            sys.exit(f"ABORT: target parent is not an existing directory: {tgt}")
        if os.path.lexists(tgt) and not os.path.isfile(tgt):
            sys.exit(f"ABORT: target is not a regular file: {tgt}")

    # Backups preserve the existing recovery boundary: failed verification
    # restores the source; appended references remain available for inspection.
    shutil.copy2(src_path, f'{src_path}.bak.presink.{ts}')
    for tgt in {s['target_ref'] for s, _, _ in bounds}:
        if os.path.isfile(tgt):
            shutil.copy2(tgt, f'{tgt}.bak.{ts}')

    # ---- 1) append originals verbatim ------------------------------------------
    today = datetime.date.today().isoformat()
    extracted = {}
    for s, a, b in bounds:
        orig = ''.join(lines[a:b]).encode('utf-8')
        extracted[s['key']] = (orig, s['target_ref'])
        header = (f"\n\n---\n\n# [{today} 下沉] {s['provenance_title']} —— 原文 verbatim 存档\n\n")
        if not os.path.isfile(s['target_ref']):
            intro = s.get('new_file_intro', f"# {s['provenance_title']}\n")
            Path(s['target_ref']).write_bytes(intro.encode('utf-8'))
        with open(s['target_ref'], 'ab') as f:
            f.write(header.encode('utf-8') + orig)
        print(f"appended [{s['key']}] {len(orig):>8}B -> {os.path.basename(s['target_ref'])}")

    # ---- 2) splice compressed snippets, bottom-up ------------------------------
    for s, a, b in sorted(bounds, key=lambda x: -x[1]):
        snippet = snippets[s['key']]
        if not snippet.endswith(('\r', '\n')):
            snippet += newline
        # Keep the existing blank separation without stripping snippet content.
        if not snippet.endswith(('\n\n', '\r\n\r\n', '\r\r')):
            snippet += newline
        lines[a:b] = split_markdown_lines(snippet)
    new = ''.join(lines).encode('utf-8')
    Path(src_path).write_bytes(new)

    # ---- 3) verify: whole-string substring, headings survive -------------------
    fails = []
    for key, (orig, tgt) in extracted.items():
        if orig not in Path(tgt).read_bytes():
            fails.append(f"[{key}] original not whole-string-present in {tgt}")
    cur = Path(src_path).read_bytes()
    cur_lines = split_markdown_lines(cur.decode('utf-8'))
    for s, _, _ in bounds:
        hits = find_heading(cur_lines, s['start_heading'])
        if len(hits) != 1:
            fails.append(f"[{s['key']}] L1 heading must appear exactly once outside fences "
                         f"(found {len(hits)}): {s['start_heading'][:40]}")
    if fails:
        print('\nVERIFY FAIL:', *('  ' + f for f in fails), sep='\n')
        shutil.copy2(f'{src_path}.bak.presink.{ts}', src_path)
        sys.exit('source rolled back (reference appends kept for inspection)')

    ob, nb = len(src), len(cur)
    print(f"\nOK {len(bounds)}/{len(bounds)} sections verified (whole-string) | "
          f"source {ob} -> {nb} bytes | backup: {src_path}.bak.presink.{ts}")


if __name__ == '__main__':
    main()
