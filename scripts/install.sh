#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo "================================================"
echo "Claude Code Skills Marketplace Installer"
echo "================================================"
echo ""

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     MACHINE=Linux;;
    Darwin*)    MACHINE=macOS;;
    *)          MACHINE="UNKNOWN:${OS}"
esac

echo "Detected OS: ${MACHINE}"
echo ""

# Check if Claude Code is installed
if ! command -v claude &> /dev/null; then
    echo -e "${RED}Error: Claude Code not found!${NC}"
    echo "Please install Claude Code first: https://claude.com/code"
    exit 1
fi

echo -e "${GREEN}✓ Claude Code detected${NC}"
echo ""

# Check if running interactively
if [ -t 0 ]; then
    # Interactive mode
    echo "What would you like to install?"
    echo ""
    echo "1) skill-creator only (RECOMMENDED - enables you to create your own skills)"
    echo "2) All skills"
    echo "3) Custom selection"
    echo "4) Exit"
    echo ""
    read -p "Enter your choice (1-4): " choice
else
    # Non-interactive mode (piped from curl)
    echo -e "${YELLOW}Running in non-interactive mode.${NC}"
    echo "Defaulting to option 1: skill-creator only (RECOMMENDED)"
    echo ""
    echo "To run interactively, download and run directly:"
    echo "  curl -fsSL https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.sh -o install.sh"
    echo "  bash install.sh"
    echo ""
    choice=1
fi

case $choice in
    1)
        echo ""
        echo -e "${CYAN}Installing skill-creator...${NC}"
        echo ""
        echo "Run these commands in Claude Code:"
        echo ""
        echo -e "${YELLOW}claude plugin marketplace add https://github.com/daymade/claude-code-skills${NC}"
        echo -e "${YELLOW}claude plugin install skill-creator@daymade-skills${NC}"
        echo ""
        echo -e "${GREEN}After installation, ask Claude Code:${NC}"
        echo "  \"Create a new skill called my-awesome-skill in ~/my-skills\""
        echo "  \"Validate my skill at ~/my-skills/my-awesome-skill\""
        echo "  \"Package my skill at ~/my-skills/my-awesome-skill\""
        echo ""
        echo "Claude Code will guide you through the skill creation process!"
        ;;
    2)
        echo ""
        echo -e "${CYAN}Installing all skills...${NC}"
        echo ""
        echo "Run these commands in Claude Code:"
        echo ""
        echo -e "${YELLOW}claude plugin marketplace add https://github.com/daymade/claude-code-skills${NC}"
        echo ""
        for skill in skill-creator github-ops markdown-tools mermaid-tools statusline-generator teams-channel-post-writer repomix-unmixer llm-icon-finder; do
            echo -e "${YELLOW}claude plugin install ${skill}@daymade-skills${NC}"
        done
        ;;
    3)
        echo ""
        echo "Available skills:"
        echo "  1) skill-creator (meta-skill for creating skills)"
        echo "  2) github-ops (GitHub operations)"
        echo "  3) markdown-tools (document conversion)"
        echo "  4) mermaid-tools (diagram generation)"
        echo "  5) statusline-generator (statusline customization)"
        echo "  6) teams-channel-post-writer (Teams communication)"
        echo "  7) repomix-unmixer (repomix extraction)"
        echo "  8) llm-icon-finder (AI/LLM icons)"
        echo ""

        if [ -t 0 ]; then
            read -p "Enter skill numbers separated by spaces (e.g., '1 2 3'): " selections
        else
            echo -e "${YELLOW}Non-interactive mode: Installing skill-creator only${NC}"
            selections="1"
        fi

        echo ""
        echo "Run these commands in Claude Code:"
        echo ""
        echo -e "${YELLOW}claude plugin marketplace add https://github.com/daymade/claude-code-skills${NC}"
        echo ""
        SKILLS=(skill-creator github-ops markdown-tools mermaid-tools statusline-generator teams-channel-post-writer repomix-unmixer llm-icon-finder)
        for num in $selections; do
            idx=$((num-1))
            if [ $idx -ge 0 ] && [ $idx -lt 8 ]; then
                echo -e "${YELLOW}claude plugin install ${SKILLS[$idx]}@daymade-skills${NC}"
            fi
        done
        ;;
    4)
        echo "Installation cancelled."
        exit 0
        ;;
    *)
        echo -e "${RED}Invalid choice!${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}Installation commands generated!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Next steps:"
echo "1. Copy the commands above"
echo "2. Paste them into Claude Code"
echo "3. Restart Claude Code"
echo "4. Start using your skills!"
echo ""
echo "Documentation: https://github.com/daymade/claude-code-skills"
echo ""
