#!/bin/bash
# SessionStart hook: Load MCP Skills Registry into context
# This provides 90%+ context savings compared to native MCP loading

# PLUGIN_DIR is provided by Claude Code when running plugin hooks
# Fallback to script directory if not set
if [[ -z "$PLUGIN_DIR" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
fi

# Read stdin (hook receives JSON with session info)
input=$(cat)

# First, try to find the project's mcp-skills registry
# This is where converted skills are stored
PROJECT_SKILLS_REGISTRY=".claude/skills/mcp-skills/SKILL.md"

if [[ -f "$PROJECT_SKILLS_REGISTRY" ]]; then
  # Use the project's own registry (contains converted skills)
  cat "$PROJECT_SKILLS_REGISTRY"
elif [[ -f "${PLUGIN_DIR}/skills/mcp-to-skill-converter/templates/registry-SKILL.md" ]]; then
  # Fall back to template registry if no project registry exists
  cat "${PLUGIN_DIR}/skills/mcp-to-skill-converter/templates/registry-SKILL.md"
else
  echo "MCP Skills Registry not found. Use mcp-to-skill-converter to create skills."
fi
