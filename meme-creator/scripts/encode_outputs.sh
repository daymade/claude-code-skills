#!/usr/bin/env bash
# encode_outputs.sh — encode a rendered frame sequence to MP4 (+ audio) and a
# size-budgeted GIF (two-pass palette).
#
# Usage:
#   encode_outputs.sh --frames 'out/o_%04d.png' --fps 30 \
#       [--source full.mp4 --ss 393.5 --t 16.5] \   # audio + exact timing from source
#       --mp4 meme.mp4 [--crf 19] \
#       --gif meme.gif [--gif-width 400] [--gif-fps 10] [--gif-colors 96]
#
# GIF size is driven by dither noise x frame count, not palette size. To hit a
# ~10 MB chat-app budget, lower in this order: gif-fps, gif-width, gif-colors.
set -euo pipefail

FRAMES='' FPS=30 SOURCE='' SS='' T='' MP4='' GIF=''
CRF=19 GIF_WIDTH=400 GIF_FPS=10 GIF_COLORS=96

while [ $# -gt 0 ]; do
  case "$1" in
    --frames) FRAMES="$2"; shift 2;;
    --fps) FPS="$2"; shift 2;;
    --source) SOURCE="$2"; shift 2;;
    --ss) SS="$2"; shift 2;;
    --t) T="$2"; shift 2;;
    --mp4) MP4="$2"; shift 2;;
    --crf) CRF="$2"; shift 2;;
    --gif) GIF="$2"; shift 2;;
    --gif-width) GIF_WIDTH="$2"; shift 2;;
    --gif-fps) GIF_FPS="$2"; shift 2;;
    --gif-colors) GIF_COLORS="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$FRAMES" ] || { echo "--frames is required" >&2; exit 2; }
[ -n "$MP4$GIF" ] || { echo "nothing to do: pass --mp4 and/or --gif" >&2; exit 2; }

if [ -n "$MP4" ]; then
  if [ -n "$SOURCE" ]; then
    ffmpeg -v error -y -framerate "$FPS" -i "$FRAMES" ${SS:+-ss "$SS"} ${T:+-t "$T"} -i "$SOURCE" \
      -map 0:v -map "1:a?" -c:v libx264 -preset slow -crf "$CRF" -pix_fmt yuv420p \
      -c:a aac -b:a 128k -movflags +faststart "$MP4"
  else
    ffmpeg -v error -y -framerate "$FPS" -i "$FRAMES" \
      -c:v libx264 -preset slow -crf "$CRF" -pix_fmt yuv420p -movflags +faststart "$MP4"
  fi
  echo "mp4: $MP4 ($(du -h "$MP4" | cut -f1))"
fi

if [ -n "$GIF" ]; then
  PAL="$(mktemp -t meme-palette).png"
  VF="fps=$GIF_FPS,scale=$GIF_WIDTH:-1:flags=lanczos"
  ffmpeg -v error -y -framerate "$FPS" -i "$FRAMES" -vf "$VF,palettegen=max_colors=$GIF_COLORS:stats_mode=full" "$PAL"
  ffmpeg -v error -y -framerate "$FPS" -i "$FRAMES" -i "$PAL" \
    -lavfi "$VF [x]; [x][1:v] paletteuse=dither=sierra2_4a:diff_mode=rectangle" "$GIF"
  rm -f "$PAL"
  echo "gif: $GIF ($(du -h "$GIF" | cut -f1)) — over budget? lower --gif-fps, then --gif-width, then --gif-colors"
fi
