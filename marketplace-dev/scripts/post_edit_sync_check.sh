#!/usr/bin/env bash
# PostToolUse hook: warn when SKILL.md is edited but marketplace.json version not bumped
# Detects skill content changes that need a corresponding version bump in marketplace.json

set -euo pipefail

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except:
    print('')
" 2>/dev/null)

# Only care about SKILL.md edits
[[ "$FILE_PATH" != *"SKILL.md"* ]] && exit 0

# Find the skill name from path (e.g., /repo/skills/dbs-hook/SKILL.md → dbs-hook)
SKILL_DIR=$(dirname "$FILE_PATH")
SKILL_NAME=$(basename "$SKILL_DIR")

# Search for marketplace.json upward from the edited file
SEARCH_DIR="$SKILL_DIR"
MARKETPLACE_JSON=""
while [[ "$SEARCH_DIR" != "/" ]]; do
    if [[ -f "$SEARCH_DIR/.claude-plugin/marketplace.json" ]]; then
        MARKETPLACE_JSON="$SEARCH_DIR/.claude-plugin/marketplace.json"
        break
    fi
    SEARCH_DIR=$(dirname "$SEARCH_DIR")
done

[[ -z "$MARKETPLACE_JSON" ]] && exit 0

# Check if this skill is registered and if version needs bumping
python3 -c "
import json, sys

with open('$MARKETPLACE_JSON') as f:
    data = json.load(f)

skill_name = '$SKILL_NAME'
found = False
for p in data.get('plugins', []):
    skills = p.get('skills', [])
    for s in skills:
        if s.rstrip('/').split('/')[-1] == skill_name:
            found = True
            version = p.get('version', 'unknown')
            print(json.dumps({
                'result': f'SKILL.md for \"{skill_name}\" was modified. Remember to bump its version in marketplace.json (currently {version}). Users on the old version won\\'t receive this update otherwise.'
            }))
            break
    if found:
        break

if not found:
    print(json.dumps({
        'result': f'SKILL.md for \"{skill_name}\" was modified but this skill is NOT registered in marketplace.json. Add it if you want it installable via plugin marketplace.'
    }))
" 2>/dev/null
