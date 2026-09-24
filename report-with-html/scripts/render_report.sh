#!/usr/bin/env bash
# render_report.sh — 把汇报页渲染成 PNG，供 Read 自验。
# 用法:
#   render_report.sh report.html [out.png] [width] [height]     # HTML 直渲(默认 1300 宽)
#   render_report.sh diagram.d2  [out.png]                      # d2 关系图: d2→SVG→按真实尺寸→PNG
# 依赖: Google Chrome(headless)。d2 模式另需 `brew install d2`。
# CI/共享环境可显式传 CHROME_BIN=/absolute/path/to/managed-chrome；不可执行则直接失败。
# d2 模式统一走 SVG→Chrome，复用同一份受控渲染与产物校验。
set -euo pipefail

SRC="${1:?用法: render_report.sh <html|d2> [out.png] [w] [h]}"
OUT="${2:-${SRC%.*}.png}"
if [ -n "${CHROME_BIN:-}" ]; then
  [ -x "$CHROME_BIN" ] || { echo "❌ CHROME_BIN 不可执行: $CHROME_BIN"; exit 1; }
  CHROME="$CHROME_BIN"
else
  CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  [ -x "$CHROME" ] || CHROME="$(command -v google-chrome || command -v chromium || true)"
fi
[ -n "$CHROME" ] || { echo "找不到 Chrome"; exit 1; }
[ -f "$SRC" ] || { echo "❌ 源文件不存在: $SRC"; exit 1; }

SHOT_TMP=""
SHOT_TMP_DIR=""
D2_TMP_DIR=""
cleanup() {
  if [ -n "$SHOT_TMP" ] && [ -f "$SHOT_TMP" ]; then
    rm -f -- "$SHOT_TMP"
  fi
  if [ -n "$SHOT_TMP_DIR" ] && [ -d "$SHOT_TMP_DIR" ]; then
    rmdir "$SHOT_TMP_DIR" 2>/dev/null || true
  fi
  if [ -n "$D2_TMP_DIR" ] && [ -d "$D2_TMP_DIR" ]; then
    rm -f -- "$D2_TMP_DIR/diagram.svg"
    rmdir "$D2_TMP_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT

positive_integer() {
  case "$1" in
    ''|*[!0-9]*|0) return 1 ;;
    *) return 0 ;;
  esac
}

validate_png() {
  python3 - "$1" <<'PY'
import binascii
import struct
import sys
import zlib
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"PNG validation failed: {message}")


path = Path(sys.argv[1])
data = path.read_bytes()
if data[:8] != b"\x89PNG\r\n\x1a\n":
    fail("bad signature")

position = 8
chunks: list[tuple[bytes, bytes]] = []
while position < len(data):
    if position + 12 > len(data):
        fail("truncated chunk header")
    length = struct.unpack(">I", data[position : position + 4])[0]
    chunk_type = data[position + 4 : position + 8]
    end = position + 12 + length
    if end > len(data):
        fail("truncated chunk payload")
    payload = data[position + 8 : position + 8 + length]
    expected_crc = struct.unpack(">I", data[position + 8 + length : end])[0]
    actual_crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
    if expected_crc != actual_crc:
        fail(f"CRC mismatch in {chunk_type!r}")
    chunks.append((chunk_type, payload))
    position = end
    if chunk_type == b"IEND":
        break

if position != len(data):
    fail("bytes after IEND")
if not chunks or chunks[0][0] != b"IHDR" or len(chunks[0][1]) != 13:
    fail("missing 13-byte IHDR")
if chunks[-1] != (b"IEND", b""):
    fail("missing empty IEND")
if sum(chunk_type == b"IHDR" for chunk_type, _ in chunks) != 1:
    fail("IHDR must occur exactly once")
if sum(chunk_type == b"IEND" for chunk_type, _ in chunks) != 1:
    fail("IEND must occur exactly once")

width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
    ">IIBBBBB", chunks[0][1]
)
if width == 0 or height == 0:
    fail("zero-sized image")
valid_depths = {
    0: {1, 2, 4, 8, 16},
    2: {8, 16},
    3: {1, 2, 4, 8},
    4: {8, 16},
    6: {8, 16},
}
if color_type not in valid_depths or bit_depth not in valid_depths[color_type]:
    fail("invalid color type / bit depth")
if compression != 0 or filtering != 0 or interlace not in {0, 1}:
    fail("unsupported PNG method")
if color_type == 3 and not any(chunk_type == b"PLTE" for chunk_type, _ in chunks):
    fail("indexed image has no palette")

idat_payloads: list[bytes] = []
idat_closed = False
for chunk_type, payload in chunks[1:-1]:
    if chunk_type == b"IDAT":
        if idat_closed:
            fail("non-consecutive IDAT chunks")
        idat_payloads.append(payload)
    elif idat_payloads:
        idat_closed = True
if not idat_payloads:
    fail("missing IDAT")

decoder = zlib.decompressobj()
pixels = decoder.decompress(b"".join(idat_payloads)) + decoder.flush()
if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
    fail("invalid or trailing zlib stream")

channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
bits_per_pixel = channels * bit_depth


def pass_size(start: int, stop: int, step: int) -> int:
    return 0 if stop <= start else (stop - start + step - 1) // step


passes = (
    ((0, 0, 1, 1),)
    if interlace == 0
    else (
        (0, 0, 8, 8),
        (4, 0, 8, 8),
        (0, 4, 4, 8),
        (2, 0, 4, 4),
        (0, 2, 2, 4),
        (1, 0, 2, 2),
        (0, 1, 1, 2),
    )
)
cursor = 0
for start_x, start_y, step_x, step_y in passes:
    pass_width = pass_size(start_x, width, step_x)
    pass_height = pass_size(start_y, height, step_y)
    if pass_width == 0 or pass_height == 0:
        continue
    row_bytes = (pass_width * bits_per_pixel + 7) // 8
    for _ in range(pass_height):
        if cursor + row_bytes + 1 > len(pixels):
            fail("truncated scanline data")
        if pixels[cursor] > 4:
            fail("invalid scanline filter")
        cursor += row_bytes + 1
if cursor != len(pixels):
    fail("unexpected decompressed scanline length")
PY
}

file_uri() {
  python3 - "$1" <<'PY'
import sys
from pathlib import Path

print(Path(sys.argv[1]).resolve(strict=True).as_uri())
PY
}

shot(){ # $1=file-url $2=out $3=w $4=h
  local file_url="$1" out="$2" width="$3" height="$4"
  local out_dir out_base chrome_output

  positive_integer "$width" || { echo "❌ width 必须是正整数: $width"; return 1; }
  positive_integer "$height" || { echo "❌ height 必须是正整数: $height"; return 1; }
  [ ! -L "$out" ] || { echo "❌ 输出路径不能是符号链接: $out"; return 1; }
  if [ -e "$out" ] && [ ! -f "$out" ]; then
    echo "❌ 输出路径已存在且不是普通文件: $out"
    return 1
  fi

  out_dir="$(dirname "$out")"
  out_base="$(basename "$out")"
  [ -d "$out_dir" ] || { echo "❌ 输出目录不存在: $out_dir"; return 1; }
  out_dir="$(cd "$out_dir" && pwd)"
  SHOT_TMP_DIR="$(mktemp -d "$out_dir/.${out_base}.rendering.XXXXXX")" || {
    echo "❌ 输出目录不可写: $out_dir"
    return 1
  }
  SHOT_TMP="$SHOT_TMP_DIR/output.png"

  if ! chrome_output=$(
    "$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
      --force-device-scale-factor=2 --window-size="$width,$height" \
      --screenshot="$SHOT_TMP" "$file_url" 2>&1
  ); then
    echo "❌ Chrome 渲染失败"
    [ -n "$chrome_output" ] && echo "$chrome_output"
    return 1
  fi

  [ -s "$SHOT_TMP" ] || { echo "❌ Chrome 未生成截图"; return 1; }
  if ! validate_png "$SHOT_TMP"; then
    echo "❌ Chrome 产物不是有效 PNG"
    return 1
  fi

  # 截断检测不在这里做，理由是实测出来的：唯一不改动产物的测高办法是再开一次
  # Chrome 用 --dump-dom 读 scrollHeight，而 --dump-dom 在部分页面上会稳定挂起
  # （2026-08-04 实测，同一现象也让 reconcile_content_diff 对同类输入连续超时）。
  # 一道「总是测不到、于是总是跳过」的闸比没有闸更糟——它让人以为查过了。
  # 改成在 crop_segments.py 里判：它本来就要找内容真实底部，那一步顺带就能看出
  # 内容是否一直贴到画布最后一行（贴到 = 被 window-size 切了）。
  mv -f -- "$SHOT_TMP" "$out"
  SHOT_TMP=""
  rmdir "$SHOT_TMP_DIR"
  SHOT_TMP_DIR=""
  [ -f "$out" ] && [ -s "$out" ] || {
    echo "❌ 最终输出不是非空普通文件: $out"
    return 1
  }
  if ! validate_png "$out"; then
    echo "❌ 最终输出不是有效 PNG: $out"
    return 1
  fi
}

case "$SRC" in
  *.d2)
    command -v d2 >/dev/null || { echo "需要 d2: brew install d2"; exit 1; }
    D2_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/report-with-html-d2.XXXXXX")"
    SVG="$D2_TMP_DIR/diagram.svg"
    d2 --layout elk --pad 30 "$SRC" "$SVG" >/dev/null
    W="$(grep -oE 'width="[0-9]+"' "$SVG" | head -1 | grep -oE '[0-9]+')" || {
      echo "❌ 无法从 d2 SVG 读取 width"
      exit 1
    }
    H="$(grep -oE 'height="[0-9]+"' "$SVG" | head -1 | grep -oE '[0-9]+')" || {
      echo "❌ 无法从 d2 SVG 读取 height"
      exit 1
    }
    shot "$(file_uri "$SVG")" "$OUT" "$W" "$H"
    echo "d2 尺寸 ${W}x${H} · 若 aspect 过宽/过高: 顶层改 direction、容器内保持 right (见 SKILL 反查经验)"
    ;;
  *)
    W="${3:-1300}"; H="${4:-2400}"
    shot "$(file_uri "$SRC")" "$OUT" "$W" "$H"
    echo "HTML 渲染 ${W}x${H} · Chrome 按 window-size 裁切、不自动增高: 底部留白→调小 H; 内容被切→调大 H(超长页传大 H 截一张, 再 scripts/crop_segments.py 切段逐张 Read); 页面写死 width>W 会横向切边"
    ;;
esac
if [ -f "$OUT" ] && [ -s "$OUT" ]; then
  echo "✅ $OUT ($(du -h "$OUT" | cut -f1)) —— 现在必须 Read 这张 PNG 核对再交付"
else
  echo "❌ 渲染失败"
  exit 1
fi
