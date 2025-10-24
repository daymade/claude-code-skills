#!/bin/bash
set -e

echo "================================================"
echo "Generating Claude Code Skills Demo GIFs"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if VHS is installed
if ! command -v vhs &> /dev/null; then
    echo -e "${RED}Error: VHS is not installed!${NC}"
    echo ""
    echo "Install VHS to generate demo GIFs:"
    echo ""
    echo "macOS:"
    echo "  brew install vhs"
    echo ""
    echo "Linux (with Go):"
    echo "  go install github.com/charmbracelet/vhs@latest"
    echo ""
    echo "Or download from: https://github.com/charmbracelet/vhs/releases"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ VHS found${NC}"
echo ""

# Find all .tape files
TAPE_FILES=$(find demos -name "*.tape" -type f | sort)
TOTAL=$(echo "$TAPE_FILES" | wc -l | tr -d ' ')
CURRENT=0

echo "Found $TOTAL demo tape files"
echo ""

# Generate each demo
for tape_file in $TAPE_FILES; do
    CURRENT=$((CURRENT + 1))
    SKILL=$(basename $(dirname "$tape_file"))
    DEMO=$(basename "$tape_file" .tape)

    echo -e "${YELLOW}[$CURRENT/$TOTAL]${NC} Generating: $SKILL/$DEMO"

    # Run VHS
    if vhs < "$tape_file" 2>&1 | grep -q "Error"; then
        echo -e "${RED}  ✗ Failed to generate $tape_file${NC}"
    else
        echo -e "${GREEN}  ✓ Generated successfully${NC}"
    fi
    echo ""
done

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}Demo generation complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Generated GIFs are located in:"
echo "  demos/skill-creator/*.gif"
echo "  demos/github-ops/*.gif"
echo "  demos/markdown-tools/*.gif"
echo ""
echo "To view a demo:"
echo "  open demos/skill-creator/init-skill.gif"
echo ""
echo "To regenerate a specific demo:"
echo "  vhs < demos/skill-creator/init-skill.tape"
echo ""
