#!/usr/bin/env bash
# md2pdf.sh — Convert Markdown files to professionally styled PDFs
# Part of claude-skill-pdf
# Usage: md2pdf.sh [OPTIONS] <file.md> [file2.md ...]
#        md2pdf.sh [OPTIONS] *.md
#
# Options:
#   -t, --template NAME   Template name: report (default), minimal, branded-example
#                          Or path to a custom .css file
#   -o, --output PATH     Output file path (only for single file mode)
#   --title TITLE          Document title for HTML metadata
#   -h, --help             Show this help message

set -euo pipefail

# --- Configuration ---
PANDOC="${PANDOC:-pandoc}"
WEASYPRINT="${WEASYPRINT:-weasyprint}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATES_DIR="${SKILL_DIR}/templates"

# --- Defaults ---
TEMPLATE="report"
OUTPUT=""
TITLE=""
FILES=()

# --- Functions ---
usage() {
  sed -n '3,12p' "$0" | sed 's/^# //' | sed 's/^#//'
  exit 0
}

find_css() {
  local name="$1"

  # If it's an absolute or relative path to a .css file, use directly
  if [[ "$name" == *.css ]] && [[ -f "$name" ]]; then
    echo "$name"
    return
  fi

  # Check project-local templates first
  local project_css="comms/templates/${name}.css"
  if [[ -f "$project_css" ]]; then
    echo "$project_css"
    return
  fi

  # Check skill-bundled templates
  local skill_css="${TEMPLATES_DIR}/${name}.css"
  if [[ -f "$skill_css" ]]; then
    echo "$skill_css"
    return
  fi

  echo ""
}

convert_one() {
  local input="$1"
  local output="$2"
  local css="$3"
  local title="$4"

  local tmp_html
  tmp_html=$(mktemp /tmp/md2pdf_XXXXXX.html)

  # Step 1: MD -> HTML via pandoc
  "$PANDOC" "$input" \
    -o "$tmp_html" \
    --standalone \
    --metadata "title=${title}" \
    --css "$css" \
    --embed-resources \
    2>/dev/null

  # Step 2: HTML -> PDF via weasyprint
  "$WEASYPRINT" "$tmp_html" "$output" 2>/dev/null

  # Cleanup
  rm -f "$tmp_html"
}

# --- Parse Arguments ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--template)
      TEMPLATE="$2"
      shift 2
      ;;
    -o|--output)
      OUTPUT="$2"
      shift 2
      ;;
    --title)
      TITLE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    -*)
      echo "Error: Unknown option $1" >&2
      exit 1
      ;;
    *)
      FILES+=("$1")
      shift
      ;;
  esac
done

# --- Validate ---
if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "Error: No input files specified." >&2
  echo "Usage: md2pdf.sh [OPTIONS] <file.md> [file2.md ...]" >&2
  exit 1
fi

if [[ ${#FILES[@]} -gt 1 ]] && [[ -n "$OUTPUT" ]]; then
  echo "Error: --output can only be used with a single input file." >&2
  exit 1
fi

# Find CSS template
CSS_PATH=$(find_css "$TEMPLATE")
if [[ -z "$CSS_PATH" ]]; then
  echo "Error: Template '${TEMPLATE}' not found." >&2
  echo "Available templates in ${TEMPLATES_DIR}:" >&2
  ls -1 "${TEMPLATES_DIR}"/*.css 2>/dev/null | xargs -I{} basename {} .css >&2
  exit 1
fi

# --- Check dependencies ---
if ! command -v "$PANDOC" &>/dev/null; then
  echo "Error: pandoc not found. Install with: brew install pandoc" >&2
  exit 1
fi

if ! command -v "$WEASYPRINT" &>/dev/null; then
  # Try common locations
  for candidate in \
    /Users/"$(whoami)"/Library/Python/3.13/bin/weasyprint \
    /Users/"$(whoami)"/Library/Python/3.12/bin/weasyprint \
    /opt/homebrew/bin/weasyprint; do
    if [[ -x "$candidate" ]]; then
      WEASYPRINT="$candidate"
      break
    fi
  done
  if ! command -v "$WEASYPRINT" &>/dev/null && [[ ! -x "$WEASYPRINT" ]]; then
    echo "Error: weasyprint not found. Install with: pip3 install --user weasyprint" >&2
    exit 1
  fi
fi

# --- Convert ---
SUCCESS=0
FAIL=0
RESULTS=()

for file in "${FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Warning: '$file' not found, skipping." >&2
    ((FAIL++))
    RESULTS+=("SKIP|$file|not found")
    continue
  fi

  # Determine output path
  if [[ -n "$OUTPUT" ]]; then
    out="$OUTPUT"
  else
    basename_no_ext=$(basename "${file}" .md)
    out="${HOME}/Desktop/${basename_no_ext}.pdf"
  fi

  # Determine title
  if [[ -n "$TITLE" ]]; then
    doc_title="$TITLE"
  else
    doc_title=$(basename "${file}" .md)
  fi

  echo "Converting: ${file} -> ${out}"

  if convert_one "$file" "$out" "$CSS_PATH" "$doc_title"; then
    size=$(du -h "$out" | cut -f1 | xargs)
    ((SUCCESS++))
    RESULTS+=("OK|$out|${size}")
    echo "  Done: ${out} (${size})"
  else
    ((FAIL++))
    RESULTS+=("FAIL|$file|conversion error")
    echo "  FAILED: ${file}" >&2
  fi
done

# --- Summary ---
if [[ ${#FILES[@]} -gt 1 ]]; then
  echo ""
  echo "=== Batch Conversion Summary ==="
  printf "%-6s %-50s %s\n" "Status" "File" "Size"
  printf "%-6s %-50s %s\n" "------" "--------------------------------------------------" "----"
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r status path info <<< "$r"
    printf "%-6s %-50s %s\n" "$status" "$path" "$info"
  done
  echo ""
  echo "Total: ${SUCCESS} succeeded, ${FAIL} failed out of ${#FILES[@]} files."
fi
