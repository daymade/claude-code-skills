#!/usr/bin/env python3
"""Profile a CLAUDE.md before proposing any optimization (SKILL.md Step 2.0).

Outputs, in one pass:
  1. Per-section byte/line table (code-fence-aware), sorted by size — the work
     order for hotspot-first optimization IS this table's descending order.
  2. Line-length distribution — lines >1KB are the signature of "rule + war
     story fused into one bullet".
  3. The longest N lines with previews, to locate the giant bullets.

Instrument calibration notes (both pitfalls were hit in real use — Case 19):
  - Headings are parsed fence-aware: a `# comment` inside a code fence is NOT
    a heading. A naive regex once fabricated a phantom 45.9KB section and
    distorted the entire hotspot ranking.
  - Token estimates: chars/4 UNDERESTIMATES CJK-dense files by >2x. Measured
    ratio on a real CJK-heavy CLAUDE.md was ~0.42 tokens/byte. Prefer scaling
    from a live `/context` measurement; always label estimates "est.".

Prior art (searched 2026-08, none fits): mrkdwn-analysis / markdown word-count
tools do element counts and word/char stats, not per-section BYTE attribution
with hotspot ordering — which is this skill's Step 2.0 artifact. Stdlib-only
by design (skill scripts must run with no installs).

Usage:
    python3 profile_claude_md.py <path/to/CLAUDE.md> [--top N] [--tokens-per-byte R]
"""
import argparse
import re
import sys

HEADING_RE = re.compile(r'^(#{1,6}) (.+)$')


def parse_headings(lines):
    """Return [(line_idx, level, title)], skipping fenced code blocks."""
    in_fence = False
    heads = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith('```'):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    if in_fence:
        print('WARN: unbalanced code fence — fence-aware parsing may be off', file=sys.stderr)
    return heads


def section_table(lines, heads, max_level=3):
    """Each heading owns [its line, next heading of same-or-higher level)."""
    rows = []
    for idx, (ln, lvl, title) in enumerate(heads):
        if lvl > max_level:
            continue
        end = len(lines)
        for j in range(idx + 1, len(heads)):
            if heads[j][1] <= lvl:
                end = heads[j][0]
                break
        body = '\n'.join(lines[ln:end])
        rows.append((lvl, title, len(body.encode('utf-8')), end - ln))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path')
    ap.add_argument('--top', type=int, default=20, help='longest lines to list (default 20)')
    ap.add_argument('--tokens-per-byte', type=float, default=None,
                    help='ratio from a live /context measurement; omit to skip token estimates')
    args = ap.parse_args()

    src = open(args.path, encoding='utf-8').read()
    lines = src.split('\n')
    total = len(src.encode('utf-8'))
    heads = parse_headings(lines)

    print(f'TOTAL {total} bytes / {len(lines)} lines / {len(heads)} headings')
    if args.tokens_per_byte:
        print(f'est. tokens: ~{int(total * args.tokens_per_byte):,} '
              f'(ratio {args.tokens_per_byte} from live measurement)')
    else:
        print('token estimate skipped — pass --tokens-per-byte from a live /context '
              'measurement (chars/4 underestimates CJK by >2x)')

    print(f'\n== 分节字节表（降序 = 热点工作顺序） ==')
    print('   （父节字节含全部子节——降序在**同层之间**比较；容器节跳过、看它最大的子节）')
    print(f"{'lvl':<5}{'bytes':>9}{'lines':>7}{'%':>7}  title")
    for lvl, title, b, nl in sorted(section_table(lines, heads), key=lambda r: -r[2]):
        print(f"{'#'*lvl:<5}{b:>9}{nl:>7}{100*b/total:>6.1f}%  {title[:64]}")

    print('\n== 行长分布 ==')
    buckets = [('<200B', 0, 200), ('200-500B', 200, 500), ('500B-1KB', 500, 1000),
               ('1-2KB', 1000, 2000), ('>2KB', 2000, 10**9)]
    for name, lo, hi in buckets:
        sel = [len(l.encode()) for l in lines if lo <= len(l.encode()) < hi]
        by = sum(sel)
        print(f"{name:<10} {len(sel):>6} 行 {by:>9} B {100*by/total:>6.1f}%")

    print(f'\n== 最长 {args.top} 行（巨型 bullet 定位） ==')
    ranked = sorted(((len(l.encode()), i + 1, l) for i, l in enumerate(lines)), reverse=True)
    for b, i, l in ranked[:args.top]:
        print(f'{b:>7}B  L{i:<6} {l[:90]}')


if __name__ == '__main__':
    main()
