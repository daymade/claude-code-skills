#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: package_images.sh <image-directory> [zip-path]" >&2
  exit 2
fi

image_dir=$1
if [[ ! -d "$image_dir" ]]; then
  echo "image directory does not exist: $image_dir" >&2
  exit 1
fi

if [[ $# -eq 2 ]]; then
  zip_path=$2
else
  zip_path="${image_dir%/}.zip"
fi

parent_dir=$(cd "$(dirname "$image_dir")" && pwd)
base_name=$(basename "$image_dir")

image_count=$(
  find "$image_dir" -maxdepth 1 -type f \
    \( -iname 'image_*.jpg' -o -iname 'image_*.jpeg' -o -iname 'image_*.png' -o -iname 'image_*.webp' \) |
    wc -l | tr -d ' '
)

if [[ "$image_count" == "0" ]]; then
  echo "no ordered image files found in $image_dir" >&2
  exit 1
fi

rm -f "$zip_path"
(
  cd "$parent_dir"
  zip -qr "$zip_path" "$base_name"
)

zip -T "$zip_path" >/dev/null

zip_count=$(
  zipinfo -1 "$zip_path" |
    grep -E '/image_[0-9][0-9]\.(jpg|jpeg|png|webp)$' |
    wc -l | tr -d ' '
)

if [[ "$zip_count" != "$image_count" ]]; then
  echo "zip image count mismatch: directory=$image_count zip=$zip_count" >&2
  exit 1
fi

printf 'zip_path=%s\nimage_count=%s\n' "$zip_path" "$image_count"
