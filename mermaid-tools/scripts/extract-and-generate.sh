#!/bin/bash
# Enhanced Mermaid diagram extraction and PNG generation script
# Extracts diagrams from markdown and numbers them sequentially
# Supports: macOS and WSL2/Linux
#
# Usage: ./extract-and-generate.sh <markdown_file> [output_directory]
# Example: ./extract-and-generate.sh "~/workspace/document.md" "~/workspace/diagrams"

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRACTOR_SCRIPT="$SCRIPT_DIR/extract_diagrams.py"

# Parse arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <markdown_file> [output_directory]"
    echo "Example: $0 '~/workspace/document.md' '~/workspace/diagrams'"
    exit 1
fi

MARKDOWN_FILE="$1"
OUTPUT_DIR="${2:-$(dirname "$MARKDOWN_FILE")/diagrams}"

# ── OS 检测 ──────────────────────────────────────────────────────────────────
OS_TYPE="$(uname -s)"
IS_MACOS=false

if [ "$OS_TYPE" = "Darwin" ]; then
    IS_MACOS=true
    CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    CONFIG_FILE="$SCRIPT_DIR/puppeteer-config-macos.json"
    ENV_DESC="macOS"
else
    # Linux / WSL
    if grep -qEi "microsoft|wsl" /proc/version 2>/dev/null; then
        ENV_DESC="WSL2 Ubuntu"
    else
        ENV_DESC="Linux"
    fi
    CHROME_PATH="/usr/bin/google-chrome-stable"
    CONFIG_FILE="$SCRIPT_DIR/puppeteer-config.json"
fi

echo "=== Enhanced Mermaid Diagram Processor ==="
echo "Source markdown: $MARKDOWN_FILE"
echo "Output directory: $OUTPUT_DIR"
echo "Environment: $ENV_DESC"
echo

# Validate inputs
if [ ! -f "$MARKDOWN_FILE" ]; then
    echo "ERROR: Markdown file not found: $MARKDOWN_FILE"
    exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Check dependencies
echo "Checking dependencies..."
if ! command -v mmdc &> /dev/null; then
    echo "ERROR: @mermaid-js/mermaid-cli not installed"
    echo "Install with: npm install -g @mermaid-js/mermaid-cli"
    exit 1
fi

if [ ! -f "$CHROME_PATH" ]; then
    echo "ERROR: Google Chrome not found at: $CHROME_PATH"
    if $IS_MACOS; then
        echo "Please install Google Chrome from https://www.google.com/chrome/"
    else
        echo "Install Chrome and dependencies with the setup commands"
    fi
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Puppeteer config not found: $CONFIG_FILE"
    exit 1
fi

if [ ! -f "$EXTRACTOR_SCRIPT" ]; then
    echo "ERROR: Python extractor script not found: $EXTRACTOR_SCRIPT"
    exit 1
fi

echo "✅ Dependencies verified (Chrome: $CHROME_PATH)"
echo

# Extract Mermaid diagrams from markdown
echo "Extracting Mermaid diagrams from markdown..."
python3 "$EXTRACTOR_SCRIPT" "$MARKDOWN_FILE" "$OUTPUT_DIR"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to extract diagrams from markdown"
    exit 1
fi

echo

# Now generate PNGs using the existing generation logic
echo "Generating PNG files..."
cd "$OUTPUT_DIR"

# Default dimensions - can be overridden with environment variables  
DEFAULT_WIDTH="${MERMAID_WIDTH:-1200}"
DEFAULT_HEIGHT="${MERMAID_HEIGHT:-800}"
SCALE_FACTOR="${MERMAID_SCALE:-2}"

# Process all .mmd files in order
mmd_files=(*.mmd)

if [ ${#mmd_files[@]} -eq 1 ] && [ "${mmd_files[0]}" = "*.mmd" ]; then
    echo "No .mmd files found in output directory"
    exit 0
fi

# Sort files numerically by their prefix
IFS=$'\n' mmd_files=($(sort -V <<< "${mmd_files[*]}"))

echo "Found ${#mmd_files[@]} Mermaid diagram(s) to process"
echo

for mmd_file in "${mmd_files[@]}"; do
    if [ ! -f "$mmd_file" ]; then
        continue
    fi
    
    # Extract filename without extension
    diagram="${mmd_file%.mmd}"
    
    # Use smart defaults based on diagram content or filename patterns
    width="$DEFAULT_WIDTH"
    height="$DEFAULT_HEIGHT"
    
    # Smart sizing based on filename patterns
    if [[ "$diagram" =~ timeline|gantt ]]; then
        width=$((DEFAULT_WIDTH * 2))  # Wider for timelines
        height=$((DEFAULT_HEIGHT / 2))  # Shorter for timelines
    elif [[ "$diagram" =~ architecture|system ]]; then
        width=$((DEFAULT_WIDTH * 2))  # Larger for complex diagrams
        height=$((DEFAULT_HEIGHT * 2))
    elif [[ "$diagram" =~ caching ]]; then
        width=$((DEFAULT_WIDTH * 2))  # Larger for caching flowcharts
        height=$((DEFAULT_HEIGHT * 2))
    elif [[ "$diagram" =~ monitoring|workflow|sequence|api ]]; then
        width=$((DEFAULT_WIDTH * 2))  # Wider for workflows and sequences
        height="$DEFAULT_HEIGHT"
    fi
    
    echo "Generating $diagram.png (${width}x${height}, scale: ${SCALE_FACTOR}x)..."
    PUPPETEER_EXECUTABLE_PATH="$CHROME_PATH" mmdc \
        -i "$mmd_file" \
        -o "$diagram.png" \
        --puppeteerConfigFile "$CONFIG_FILE" \
        -w "$width" \
        -H "$height" \
        -s "$SCALE_FACTOR"
    
    if [ $? -eq 0 ]; then
        echo "  ✅ Generated successfully"
    else
        echo "  ❌ Generation failed"
        continue
    fi
    
    # Validate PNG — 跨平台兼容的 stat 命令
    if test -s "$diagram.png" && file "$diagram.png" | grep -q "PNG image"; then
        if $IS_MACOS; then
            size=$(stat -f%z "$diagram.png")
        else
            size=$(stat -c%s "$diagram.png")
        fi
        dimensions_actual=$(identify -format "%wx%h" "$diagram.png" 2>/dev/null || echo "unknown")
        echo "  ✅ Validated PNG (${size} bytes, ${dimensions_actual})"
    else
        echo "  ❌ PNG validation failed"
    fi
    echo
done

echo "=== Generation Complete ==="
echo "All PNG diagrams generated and validated successfully!"
echo

echo "Generated files (in sequence order):"
ls -la [0-9][0-9]-*.png 2>/dev/null | awk '{printf "  %s (%s bytes)\n", $9, $5}' || echo "  No numbered PNG files found"

echo
echo "Generated files (all):"
ls -la *.png 2>/dev/null | awk '{printf "  %s (%s bytes)\n", $9, $5}' || echo "  No PNG files found"