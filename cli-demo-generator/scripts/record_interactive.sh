#!/bin/bash
#
# Record interactive CLI demos using asciinema and convert to GIF
#
# Usage:
#   record_interactive.sh output.gif
#   record_interactive.sh output.gif --theme Dracula --width 1200
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default values
OUTPUT=""
THEME="Dracula"
WIDTH=1400
HEIGHT=700
FONT_SIZE=16

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --theme)
            THEME="$2"
            shift 2
            ;;
        --width)
            WIDTH="$2"
            shift 2
            ;;
        --height)
            HEIGHT="$2"
            shift 2
            ;;
        --font-size)
            FONT_SIZE="$2"
            shift 2
            ;;
        *)
            OUTPUT="$1"
            shift
            ;;
    esac
done

if [ -z "$OUTPUT" ]; then
    echo -e "${RED}Error: Output file required${NC}" >&2
    echo "Usage: $0 output.gif [--theme Theme] [--width 1200] [--height 700]"
    exit 1
fi

# Check dependencies
if ! command -v asciinema &> /dev/null; then
    echo -e "${RED}Error: asciinema not installed${NC}" >&2
    echo "Install it with:"
    echo "  macOS: brew install asciinema"
    echo "  Linux: sudo apt install asciinema"
    exit 1
fi

if ! command -v vhs &> /dev/null; then
    echo -e "${RED}Error: VHS not installed${NC}" >&2
    echo "Install it with: brew install vhs"
    exit 1
fi

# Generate temp files
CAST_FILE="${OUTPUT%.gif}.cast"
TAPE_FILE="${OUTPUT%.gif}.tape"

echo -e "${GREEN}===========================================================${NC}"
echo -e "${GREEN}Interactive Demo Recording${NC}"
echo -e "${GREEN}===========================================================${NC}"
echo ""
echo -e "${YELLOW}Instructions:${NC}"
echo "1. Type your commands naturally"
echo "2. Press ENTER after each command"
echo "3. Press Ctrl+D when finished"
echo ""
echo -e "${YELLOW}Output:${NC} $OUTPUT"
echo -e "${YELLOW}Theme:${NC} $THEME"
echo -e "${YELLOW}Size:${NC} ${WIDTH}x${HEIGHT}"
echo ""
echo -e "${GREEN}Starting recording in 3 seconds...${NC}"
sleep 3
echo ""

# Record with asciinema
asciinema rec "$CAST_FILE"

echo ""
echo -e "${GREEN}✓ Recording saved to: $CAST_FILE${NC}"
echo ""
echo -e "${YELLOW}Converting to GIF...${NC}"

# Convert asciinema cast to VHS tape format
cat > "$TAPE_FILE" << EOF
Output $OUTPUT

Set FontSize $FONT_SIZE
Set Width $WIDTH
Set Height $HEIGHT
Set Theme "$THEME"
Set Padding 20

Play $CAST_FILE
EOF

echo -e "${GREEN}✓ Generated tape file: $TAPE_FILE${NC}"

# Generate GIF with VHS
vhs < "$TAPE_FILE"

if [ -f "$OUTPUT" ]; then
    FILE_SIZE=$(du -h "$OUTPUT" | cut -f1)
    echo ""
    echo -e "${GREEN}===========================================================${NC}"
    echo -e "${GREEN}✓ Demo generated successfully!${NC}"
    echo -e "${GREEN}===========================================================${NC}"
    echo -e "${YELLOW}Output:${NC} $OUTPUT"
    echo -e "${YELLOW}Size:${NC} $FILE_SIZE"
    echo ""
    echo "Generated files:"
    echo "  - $CAST_FILE (asciinema recording)"
    echo "  - $TAPE_FILE (VHS tape file)"
    echo "  - $OUTPUT (GIF demo)"
    echo ""
else
    echo -e "${RED}✗ Failed to generate GIF${NC}" >&2
    exit 1
fi
