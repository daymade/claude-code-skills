#!/usr/bin/env python3
"""
Multi-tool markdown output merger with segment-level comparison.

Merges markdown outputs from multiple conversion tools by selecting
the best version of each segment (tables, images, headings, paragraphs).

Usage:
    python merge_outputs.py output1.md output2.md -o merged.md
    python merge_outputs.py --from-json results.json -o merged.md
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Segment:
    """A segment of markdown content."""
    type: str  # 'heading', 'table', 'image', 'list', 'paragraph', 'code'
    content: str
    level: int = 0  # For headings
    score: float = 0.0


@dataclass
class MergeResult:
    """Result from merging multiple markdown files."""
    markdown: str
    sources: list[str] = field(default_factory=list)
    segment_sources: dict = field(default_factory=dict)  # segment_idx -> source


def parse_segments(markdown: str) -> list[Segment]:
    """Parse markdown into typed segments."""
    segments = []
    lines = markdown.split('\n')
    current_segment = []
    current_type = 'paragraph'
    current_level = 0
    in_code_block = False
    in_table = False

    def flush_segment():
        nonlocal current_segment, current_type, current_level
        if current_segment:
            content = '\n'.join(current_segment).strip()
            if content:
                segments.append(Segment(
                    type=current_type,
                    content=content,
                    level=current_level
                ))
        current_segment = []
        current_type = 'paragraph'
        current_level = 0

    for line in lines:
        # Code block detection
        if line.startswith('```'):
            if in_code_block:
                current_segment.append(line)
                flush_segment()
                in_code_block = False
                continue
            else:
                flush_segment()
                in_code_block = True
                current_type = 'code'
                current_segment.append(line)
                continue

        if in_code_block:
            current_segment.append(line)
            continue

        # Heading detection
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading_match:
            flush_segment()
            current_type = 'heading'
            current_level = len(heading_match.group(1))
            current_segment.append(line)
            flush_segment()
            continue

        # Table detection
        if '|' in line and re.match(r'^\s*\|.*\|\s*$', line):
            if not in_table:
                flush_segment()
                in_table = True
                current_type = 'table'
            current_segment.append(line)
            continue
        elif in_table:
            flush_segment()
            in_table = False

        # Image detection
        if re.match(r'!\[.*\]\(.*\)', line):
            flush_segment()
            current_type = 'image'
            current_segment.append(line)
            flush_segment()
            continue

        # List detection
        if re.match(r'^[\s]*[-*+]\s+', line) or re.match(r'^[\s]*\d+\.\s+', line):
            if current_type != 'list':
                flush_segment()
                current_type = 'list'
            current_segment.append(line)
            continue
        elif current_type == 'list' and line.strip() == '':
            flush_segment()
            continue

        # Empty line - potential paragraph break
        if line.strip() == '':
            if current_type == 'paragraph' and current_segment:
                flush_segment()
            continue

        # Default: paragraph
        if current_type not in ['list']:
            current_type = 'paragraph'
        current_segment.append(line)

    flush_segment()
    return segments


def score_segment(segment: Segment) -> float:
    """Score a segment for quality comparison."""
    score = 0.0
    content = segment.content

    if segment.type == 'table':
        # Count rows and columns
        rows = [l for l in content.split('\n') if '|' in l]
        if rows:
            cols = rows[0].count('|') - 1
            score += len(rows) * 0.5  # More rows = better
            score += cols * 0.3  # More columns = better
            # Penalize separator-only tables
            if all(re.match(r'^[\s|:-]+$', r) for r in rows):
                score -= 5.0
            # Bonus for proper header separator
            if len(rows) > 1 and re.match(r'^[\s|:-]+$', rows[1]):
                score += 1.0

    elif segment.type == 'heading':
        # Prefer proper heading hierarchy
        score += 1.0
        # Penalize very long headings
        if len(content) > 100:
            score -= 0.5

    elif segment.type == 'image':
        # Prefer images with alt text
        if re.search(r'!\[.+\]', content):
            score += 1.0
        # Prefer local paths over base64
        if 'data:image' not in content:
            score += 0.5

    elif segment.type == 'list':
        items = re.findall(r'^[\s]*[-*+\d.]+\s+', content, re.MULTILINE)
        score += len(items) * 0.3
        # Bonus for nested lists
        if re.search(r'^\s{2,}[-*+]', content, re.MULTILINE):
            score += 0.5

    elif segment.type == 'code':
        lines = content.split('\n')
        score += min(len(lines) * 0.2, 3.0)
        # Bonus for language specification
        if re.match(r'^```\w+', content):
            score += 0.5

    else:  # paragraph
        words = len(content.split())
        score += min(words * 0.05, 2.0)
        # Penalize very short paragraphs
        if words < 5:
            score -= 0.5

    return score


def find_matching_segment(
    segment: Segment,
    candidates: list[Segment],
    used_indices: set
) -> Optional[int]:
    """Find a matching segment in candidates by type and similarity."""
    best_match = None
    best_similarity = 0.3  # Minimum threshold

    for i, candidate in enumerate(candidates):
        if i in used_indices:
            continue
        if candidate.type != segment.type:
            continue

        # Calculate similarity
        if segment.type == 'heading':
            # Compare heading text (ignore # symbols)
            s1 = re.sub(r'^#+\s*', '', segment.content).lower()
            s2 = re.sub(r'^#+\s*', '', candidate.content).lower()
            similarity = _text_similarity(s1, s2)
        elif segment.type == 'table':
            # Compare first row (header)
            h1 = segment.content.split('\n')[0] if segment.content else ''
            h2 = candidate.content.split('\n')[0] if candidate.content else ''
            similarity = _text_similarity(h1, h2)
        else:
            # Compare content directly
            similarity = _text_similarity(segment.content, candidate.content)

        if similarity > best_similarity:
            best_similarity = similarity
            best_match = i

    return best_match


def _text_similarity(s1: str, s2: str) -> float:
    """Calculate simple text similarity (Jaccard on words)."""
    if not s1 or not s2:
        return 0.0

    words1 = set(s1.lower().split())
    words2 = set(s2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    return intersection / union if union > 0 else 0.0


def merge_markdown_files(
    files: list[Path],
    source_names: Optional[list[str]] = None
) -> MergeResult:
    """Merge multiple markdown files by selecting best segments."""
    if not files:
        return MergeResult(markdown="", sources=[])

    if source_names is None:
        source_names = [f.stem for f in files]

    # Parse all files into segments
    all_segments = []
    for i, file_path in enumerate(files):
        content = file_path.read_text()
        segments = parse_segments(content)
        # Score each segment
        for seg in segments:
            seg.score = score_segment(seg)
        all_segments.append((source_names[i], segments))

    if len(all_segments) == 1:
        return MergeResult(
            markdown=files[0].read_text(),
            sources=[source_names[0]]
        )

    # Use first file as base structure
    base_name, base_segments = all_segments[0]
    merged_segments = []
    segment_sources = {}

    for i, base_seg in enumerate(base_segments):
        best_segment = base_seg
        best_source = base_name

        # Find matching segments in other files
        for other_name, other_segments in all_segments[1:]:
            used = set()
            match_idx = find_matching_segment(base_seg, other_segments, used)

            if match_idx is not None:
                other_seg = other_segments[match_idx]
                if other_seg.score > best_segment.score:
                    best_segment = other_seg
                    best_source = other_name

        merged_segments.append(best_segment)
        segment_sources[i] = best_source

    # Check for segments in other files that weren't matched
    # (content that only appears in secondary sources)
    base_used = set(range(len(base_segments)))
    for other_name, other_segments in all_segments[1:]:
        for j, other_seg in enumerate(other_segments):
            match_idx = find_matching_segment(other_seg, base_segments, set())
            if match_idx is None and other_seg.score > 0.5:
                # This segment doesn't exist in base - consider adding
                merged_segments.append(other_seg)
                segment_sources[len(merged_segments) - 1] = other_name

    # Reconstruct markdown
    merged_md = '\n\n'.join(seg.content for seg in merged_segments)

    return MergeResult(
        markdown=merged_md,
        sources=source_names,
        segment_sources=segment_sources
    )


def merge_from_json(json_path: Path) -> MergeResult:
    """Merge from JSON results file (from convert.py)."""
    with open(json_path) as f:
        data = json.load(f)

    results = data.get('results', [])
    if not results:
        return MergeResult(markdown="", sources=[])

    # Filter successful results
    successful = [r for r in results if r.get('success') and r.get('markdown')]
    if not successful:
        return MergeResult(markdown="", sources=[])

    if len(successful) == 1:
        return MergeResult(
            markdown=successful[0]['markdown'],
            sources=[successful[0]['tool']]
        )

    # Parse and merge
    all_segments = []
    for result in successful:
        tool = result['tool']
        segments = parse_segments(result['markdown'])
        for seg in segments:
            seg.score = score_segment(seg)
        all_segments.append((tool, segments))

    # Same merge logic as merge_markdown_files
    base_name, base_segments = all_segments[0]
    merged_segments = []
    segment_sources = {}

    for i, base_seg in enumerate(base_segments):
        best_segment = base_seg
        best_source = base_name

        for other_name, other_segments in all_segments[1:]:
            match_idx = find_matching_segment(base_seg, other_segments, set())
            if match_idx is not None:
                other_seg = other_segments[match_idx]
                if other_seg.score > best_segment.score:
                    best_segment = other_seg
                    best_source = other_name

        merged_segments.append(best_segment)
        segment_sources[i] = best_source

    merged_md = '\n\n'.join(seg.content for seg in merged_segments)

    return MergeResult(
        markdown=merged_md,
        sources=[r['tool'] for r in successful],
        segment_sources=segment_sources
    )


def main():
    parser = argparse.ArgumentParser(
        description="Merge markdown outputs from multiple conversion tools"
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Input markdown files to merge"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output merged markdown file"
    )
    parser.add_argument(
        "--from-json",
        type=Path,
        help="Merge from JSON results file (from convert.py)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show segment source attribution"
    )

    args = parser.parse_args()

    if args.from_json:
        result = merge_from_json(args.from_json)
    elif args.inputs:
        # Validate inputs
        for f in args.inputs:
            if not f.exists():
                print(f"Error: File not found: {f}", file=sys.stderr)
                sys.exit(1)
        result = merge_markdown_files(args.inputs)
    else:
        parser.error("Either input files or --from-json is required")

    if not result.markdown:
        print("Error: No content to merge", file=sys.stderr)
        sys.exit(1)

    # Output
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.markdown)
        print(f"Merged output: {args.output}")
        print(f"Sources: {', '.join(result.sources)}")
    else:
        print(result.markdown)

    if args.verbose and result.segment_sources:
        print("\n--- Segment Attribution ---", file=sys.stderr)
        for idx, source in result.segment_sources.items():
            print(f"  Segment {idx}: {source}", file=sys.stderr)


if __name__ == "__main__":
    main()
