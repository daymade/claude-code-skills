#!/usr/bin/env bash
#
# ab_compare.sh — compare two directories of mp3 files (size + duration).
#
# Typical use: after regenerating a voice corpus with stepaudio-2.5-tts into a
# parallel `zh_v25/` directory, compare against the step-tts-2 baseline `zh/`.
# Outputs a GitHub-flavored markdown table so you can paste it into a report.
#
# Usage:
#   ./ab_compare.sh <dir_a_baseline> <dir_b_candidate>
#   ./ab_compare.sh ./voice/zh ./voice/zh_v25
#
# Only files present in BOTH directories are compared. Files unique to either
# side are reported separately at the end.
#
# Dependencies: ffprobe (from ffmpeg), GNU-style stat OR BSD stat (macOS).

set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Usage: $0 <baseline_dir> <candidate_dir>" >&2
    echo "  Compares mp3 files present in both directories by size and duration." >&2
    exit 2
fi

DIR_A="$1"
DIR_B="$2"

if [ ! -d "$DIR_A" ]; then
    echo "ERROR: baseline dir not found: $DIR_A" >&2
    exit 2
fi
if [ ! -d "$DIR_B" ]; then
    echo "ERROR: candidate dir not found: $DIR_B" >&2
    exit 2
fi

if ! command -v ffprobe >/dev/null 2>&1; then
    echo "ERROR: ffprobe not found. Install ffmpeg: brew install ffmpeg (macOS)" >&2
    exit 2
fi

# Portable byte-size function (macOS stat vs GNU stat)
filesize() {
    if stat -f%z "$1" >/dev/null 2>&1; then
        stat -f%z "$1"   # BSD / macOS
    else
        stat -c%s "$1"   # GNU / Linux
    fi
}

duration() {
    ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$1"
}

# Compute the intersection (files present in both)
common_files=$(comm -12 \
    <(cd "$DIR_A" && ls *.mp3 2>/dev/null | sort) \
    <(cd "$DIR_B" && ls *.mp3 2>/dev/null | sort) || true)

only_a=$(comm -23 \
    <(cd "$DIR_A" && ls *.mp3 2>/dev/null | sort) \
    <(cd "$DIR_B" && ls *.mp3 2>/dev/null | sort) || true)

only_b=$(comm -13 \
    <(cd "$DIR_A" && ls *.mp3 2>/dev/null | sort) \
    <(cd "$DIR_B" && ls *.mp3 2>/dev/null | sort) || true)

if [ -z "$common_files" ]; then
    echo "ERROR: no .mp3 files common to both directories." >&2
    exit 1
fi

# Header
printf "| %-28s | %10s | %10s | %9s | %8s | %8s | %7s |\n" \
    "id" "A bytes" "B bytes" "Δsize%" "A dur" "B dur" "Δdur%"
printf "|%s|%s|%s|%s|%s|%s|%s|\n" \
    "-----------------------------" "------------" "------------" "-----------" "----------" "----------" "---------"

total_a_size=0
total_b_size=0
total_a_dur=0
total_b_dur=0
n=0

while IFS= read -r fname; do
    [ -z "$fname" ] && continue
    a_path="$DIR_A/$fname"
    b_path="$DIR_B/$fname"
    a_size=$(filesize "$a_path")
    b_size=$(filesize "$b_path")
    a_dur=$(duration "$a_path")
    b_dur=$(duration "$b_path")

    if [ "$a_size" -gt 0 ]; then
        dsize=$(awk -v a="$a_size" -v b="$b_size" 'BEGIN{printf "%.1f", (b-a)*100/a}')
    else
        dsize="N/A"
    fi
    ddur=$(awk -v a="$a_dur" -v b="$b_dur" 'BEGIN{if(a+0==0){print "N/A"}else{printf "%.1f", (b-a)*100/a}}')

    id_only="${fname%.mp3}"
    printf "| %-28s | %10d | %10d | %8s%% | %7.2fs | %7.2fs | %6s%% |\n" \
        "$id_only" "$a_size" "$b_size" "$dsize" "$a_dur" "$b_dur" "$ddur"

    total_a_size=$((total_a_size + a_size))
    total_b_size=$((total_b_size + b_size))
    total_a_dur=$(awk -v s="$total_a_dur" -v d="$a_dur" 'BEGIN{printf "%.3f", s+d}')
    total_b_dur=$(awk -v s="$total_b_dur" -v d="$b_dur" 'BEGIN{printf "%.3f", s+d}')
    n=$((n + 1))
done <<< "$common_files"

echo ""
echo "**Totals (${n} common files):**"
echo ""
if [ "$total_a_size" -gt 0 ]; then
    size_delta=$(awk -v a="$total_a_size" -v b="$total_b_size" 'BEGIN{printf "%.1f", (b-a)*100/a}')
    dur_delta=$(awk -v a="$total_a_dur" -v b="$total_b_dur" 'BEGIN{printf "%.1f", (b-a)*100/a}')
    echo "- Size: A=${total_a_size} B=${total_b_size} (Δ ${size_delta}%)"
    echo "- Duration: A=${total_a_dur}s B=${total_b_dur}s (Δ ${dur_delta}%)"
fi

if [ -n "$only_a" ]; then
    echo ""
    echo "**Only in A (${DIR_A}):**"
    echo "$only_a" | sed 's/^/  - /'
fi
if [ -n "$only_b" ]; then
    echo ""
    echo "**Only in B (${DIR_B}):**"
    echo "$only_b" | sed 's/^/  - /'
fi
