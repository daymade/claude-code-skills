# /// script
# requires-python = ">=3.9"
# ///
"""
Overlap-merge transcription for long audio files.

Splits audio into 18-minute chunks with 2-minute overlap, transcribes each chunk
via a configurable ASR endpoint, then merges using punctuation-stripped fuzzy
matching to eliminate sentence truncation at boundaries.

Usage:
    python3 scripts/overlap_merge_transcribe.py INPUT_AUDIO OUTPUT.txt --config CONFIG.json
    python3 scripts/overlap_merge_transcribe.py INPUT_AUDIO OUTPUT.txt --endpoint URL --model MODEL
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile


def get_duration(audio_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def split_audio(audio_path: str, chunk_dir: str, chunk_duration: int, overlap: int) -> list[tuple[int, int, str]]:
    """Split audio into overlapping chunks. Returns list of (start_sec, duration_sec, chunk_path)."""
    total = int(get_duration(audio_path))
    chunks = []
    start = 0

    while start < total:
        duration = min(chunk_duration, total - start)
        chunk_path = os.path.join(chunk_dir, f"chunk_{len(chunks):02d}.mp3")

        subprocess.run(
            ["ffmpeg", "-i", audio_path, "-ss", str(start), "-t", str(duration),
             "-acodec", "copy", chunk_path, "-y"],
            capture_output=True
        )
        chunks.append((start, duration, chunk_path))
        print(f"  Chunk {len(chunks)-1}: {start//60}:{start%60:02d} - {(start+duration)//60}:{(start+duration)%60:02d}", file=sys.stderr)

        start += duration - overlap
        if start + duration >= total and duration == chunk_duration:
            start = total - duration  # ensure last chunk covers the end
            if start <= chunks[-1][0]:
                break

    return chunks


def transcribe(audio_path: str, endpoint: str, model: str, noproxy: bool = True) -> str:
    """Send audio to ASR endpoint and return text."""
    noproxy_args = ["--noproxy", "*"] if noproxy else []
    result = subprocess.run(
        ["curl", "-s", "--max-time", "600"] + noproxy_args + [
            endpoint,
            "-F", f"file=@{audio_path}",
            "-F", f"model={model}"
        ],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    return data["text"]


def strip_punct(text: str) -> str:
    """Remove all punctuation, keep only CJK chars, letters, and digits."""
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text)


def fuzzy_merge(text_a: str, text_b: str, search_chars: int = 600, min_match: int = 15) -> str:
    """
    Merge two overlapping transcription segments using punctuation-stripped fuzzy matching.

    The ASR model produces slightly different punctuation for the same audio segment
    across different runs, so exact string matching fails. By stripping punctuation
    before matching, we find the true overlap region reliably.

    Uses text_b's version at the merge point because text_a truncates its final sentence
    while text_b has the complete version.
    """
    tail_a_clean = strip_punct(text_a[-search_chars:])
    text_b_clean = strip_punct(text_b)

    best_match_len = 0
    best_b_clean_end = 0

    # Search for longest matching substring (punctuation-stripped)
    for start in range(len(tail_a_clean)):
        substr = tail_a_clean[start:start + min_match]
        if len(substr) < min_match:
            break
        pos = text_b_clean.find(substr)
        if pos >= 0:
            # Extend the match as far as possible
            match_len = min_match
            while (start + match_len < len(tail_a_clean)
                   and pos + match_len < len(text_b_clean)
                   and tail_a_clean[start + match_len] == text_b_clean[pos + match_len]):
                match_len += 1

            if match_len > best_match_len:
                best_match_len = match_len
                best_b_clean_end = pos + match_len
                best_a_clean_start = start

    if best_match_len >= min_match:
        # Map clean positions back to raw text positions
        # For text_a: find where the match starts in raw text
        a_offset = len(text_a) - search_chars
        clean_count = 0
        a_cut_pos = len(text_a)
        for idx, ch in enumerate(text_a[-search_chars:]):
            if strip_punct(ch):
                clean_count += 1
            if clean_count > best_a_clean_start:
                a_cut_pos = a_offset + idx
                break

        # For text_b: find where the match ends in raw text
        clean_count = 0
        b_start_pos = 0
        for idx, ch in enumerate(text_b):
            if strip_punct(ch):
                clean_count += 1
            if clean_count >= best_b_clean_end:
                b_start_pos = idx + 1
                break

        print(f"  Merged: {best_match_len} chars matched (punct-stripped)", file=sys.stderr)
        return text_a[:a_cut_pos] + text_b[b_start_pos:]
    else:
        print(f"  Warning: no overlap found ({best_match_len} chars), concatenating directly", file=sys.stderr)
        return text_a + text_b


def main():
    parser = argparse.ArgumentParser(description="Overlap-merge ASR transcription")
    parser.add_argument("input", help="Input audio/video file")
    parser.add_argument("output", help="Output text file")
    parser.add_argument("--config", help="Path to config.json (from CLAUDE_PLUGIN_DATA)")
    parser.add_argument("--endpoint", default="http://workstation-4090-wsl:8002/v1/audio/transcriptions", help="ASR endpoint URL")
    parser.add_argument("--model", default="Qwen/Qwen3-ASR-1.7B", help="Model name")
    parser.add_argument("--noproxy", action="store_true", default=True, help="Use --noproxy with curl")
    parser.add_argument("--chunk-duration", type=int, default=1080, help="Chunk duration in seconds (default: 1080 = 18min)")
    parser.add_argument("--overlap", type=int, default=120, help="Overlap duration in seconds (default: 120 = 2min)")
    args = parser.parse_args()

    # Load config from file if provided, otherwise use CLI args
    if args.config and os.path.exists(args.config):
        with open(args.config) as f:
            cfg = json.load(f)
        args.endpoint = cfg.get("endpoint", args.endpoint)
        args.model = cfg.get("model", args.model)
        args.noproxy = cfg.get("noproxy", args.noproxy)

    print(f"Input: {args.input}", file=sys.stderr)
    total_duration = get_duration(args.input)
    print(f"Duration: {total_duration:.0f}s ({total_duration/60:.1f}min)", file=sys.stderr)

    with tempfile.TemporaryDirectory() as chunk_dir:
        # Split
        print(f"\nSplitting into {args.chunk_duration}s chunks with {args.overlap}s overlap...", file=sys.stderr)
        chunks = split_audio(args.input, chunk_dir, args.chunk_duration, args.overlap)
        print(f"Created {len(chunks)} chunks\n", file=sys.stderr)

        # Transcribe each chunk
        texts = []
        for i, (start, dur, path) in enumerate(chunks):
            print(f"Transcribing chunk {i} ({start//60}:{start%60:02d})...", end=" ", file=sys.stderr, flush=True)
            text = transcribe(path, args.endpoint, args.model, args.noproxy)
            texts.append(text)
            print(f"{len(text)} chars", file=sys.stderr)

        # Merge
        print(f"\nMerging {len(texts)} segments...", file=sys.stderr)
        merged = texts[0]
        for i in range(1, len(texts)):
            print(f"  Merging chunk {i-1} + {i}:", file=sys.stderr)
            merged = fuzzy_merge(merged, texts[i])

    # Save
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(merged)

    print(f"\nDone! {len(merged)} chars saved to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
