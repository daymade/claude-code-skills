#!/usr/bin/env python3
"""Shared ATX-heading scan for the profile and whole-section sink scripts."""
import re
import sys


HEADING_RE = re.compile(r'^(#{1,6}) (.+)$')
FENCE_RE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')


def split_markdown_lines(text):
    """Split only LF, CRLF and CR, retaining every original character.

    str.splitlines() also splits Unicode separators and control characters;
    those are inline Markdown content and must not expose new headings.
    """
    return re.findall(r'[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+\Z', text)


def line_text(line):
    """Remove only a line terminator, never heading/content whitespace."""
    if line.endswith('\r\n'):
        return line[:-2]
    return line[:-1] if line.endswith(('\n', '\r')) else line


def parse_headings(lines):
    """Return [(line_idx, level, title)], ignoring backtick and tilde fences.

    A closing fence must use the opening character, be at least as long, and
    contain only optional whitespace after the fence. Longer outer fences may
    therefore contain shorter fences without exposing their example headings.
    """
    fence = None
    heads = []
    for i, raw_line in enumerate(lines):
        line = line_text(raw_line)
        marker = FENCE_RE.match(line)
        if fence:
            if (marker and marker[1][0] == fence[0]
                    and len(marker[1]) >= fence[1] and not marker[2].strip()):
                fence = None
            continue
        if marker and not (marker[1][0] == '`' and '`' in marker[2]):
            fence = (marker[1][0], len(marker[1]))
            continue
        heading = HEADING_RE.match(line)
        if heading:
            heads.append((i, len(heading[1]), heading[2].strip()))
    if fence:
        print('WARN: unbalanced code fence — fence-aware parsing may be off', file=sys.stderr)
    return heads
