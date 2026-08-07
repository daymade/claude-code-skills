#!/usr/bin/env python3
"""Verbatim whole-section sink for CLAUDE.md progressive disclosure (SKILL.md Step 3).

For each section in the spec: extract [start_heading, end_heading) from the source
(exact-line match, code-fence-aware) -> append verbatim to the target reference under
a dated provenance header (new files get an intro) -> replace the L1 range with the
compressed snippet, bottom-up so earlier line numbers stay valid -> verify every
original is a WHOLE-STRING substring of its target (grep ORs per line and would pass
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
      "snippet_file": "compressed replacement. MUST retain the section's original start_heading line verbatim — the post-splice verifier checks every heading survived; a renamed heading fails and rolls back",
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
transactional contract this script exists for. Stdlib-only by design.

Usage:
    python3 sink_sections.py <spec.json> [--min-snippet-bytes 200]
"""
import argparse
import datetime
import json
import os
import shutil
import sys


def find_heading(lines, heading):
    """All exact full-line matches, skipping fenced code blocks."""
    in_fence = False
    hits = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith('```'):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.rstrip() == heading:
            hits.append(i)
    return hits


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

    spec = json.load(open(args.spec, encoding='utf-8'))
    src_path = spec['source']
    sections = spec['sections']

    # ---- fail-fast preflight: snippets exist & are not stubs -------------------
    snippets = {}
    for s in sections:
        p = s['snippet_file']
        if not os.path.isfile(p):
            sys.exit(f"ABORT: snippet missing: {p}")
        text = open(p, encoding='utf-8').read()
        if len(text.strip().encode()) < args.min_snippet_bytes:
            sys.exit(f"ABORT: snippet suspiciously small (<{args.min_snippet_bytes}B): {p}")
        snippets[s['key']] = text.rstrip() + '\n\n'

    src = open(src_path, encoding='utf-8').read()
    lines = src.split('\n')

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

    # ---- symlink guard (file OR any parent dir) + backups -----------------------
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
    shutil.copy2(src_path, f'{src_path}.bak.presink.{ts}')
    for tgt in {s['target_ref'] for s, _, _ in bounds}:
        if os.path.isfile(tgt):
            shutil.copy2(tgt, f'{tgt}.bak.{ts}')

    # ---- 1) append originals verbatim ------------------------------------------
    today = datetime.date.today().isoformat()
    extracted = {}
    for s, a, b in bounds:
        orig = '\n'.join(lines[a:b])
        extracted[s['key']] = (orig, s['target_ref'])
        header = (f"\n\n---\n\n# [{today} 下沉] {s['provenance_title']} —— 原文 verbatim 存档\n\n")
        if not os.path.isfile(s['target_ref']):
            intro = s.get('new_file_intro', f"# {s['provenance_title']}\n")
            open(s['target_ref'], 'w', encoding='utf-8').write(intro)
        with open(s['target_ref'], 'a', encoding='utf-8') as f:
            f.write(header + orig.rstrip() + '\n')
        print(f"appended [{s['key']}] {len(orig.encode()):>8}B -> {os.path.basename(s['target_ref'])}")

    # ---- 2) splice compressed snippets, bottom-up ------------------------------
    for s, a, b in sorted(bounds, key=lambda x: -x[1]):
        lines[a:b] = snippets[s['key']].split('\n')
    new = '\n'.join(lines)
    open(src_path, 'w', encoding='utf-8').write(new)

    # ---- 3) verify: whole-string substring, headings survive -------------------
    fails = []
    for key, (orig, tgt) in extracted.items():
        if orig.rstrip() not in open(tgt, encoding='utf-8').read():
            fails.append(f"[{key}] original not whole-string-present in {tgt}")
    cur = open(src_path, encoding='utf-8').read()
    for s, _, _ in bounds:
        if s['start_heading'] not in cur:
            fails.append(f"[{s['key']}] L1 heading lost: {s['start_heading'][:40]}")
    if fails:
        print('\nVERIFY FAIL:', *('  ' + f for f in fails), sep='\n')
        shutil.copy2(f'{src_path}.bak.presink.{ts}', src_path)
        sys.exit('source rolled back (reference appends kept for inspection)')

    ob, nb = len(src.encode()), len(cur.encode())
    print(f"\nOK {len(bounds)}/{len(bounds)} sections verified (whole-string) | "
          f"source {ob} -> {nb} bytes | backup: {src_path}.bak.presink.{ts}")


if __name__ == '__main__':
    main()
