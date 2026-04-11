#!/usr/bin/env bash
# check_marketplace.sh — One-shot validation for a plugin marketplace repo.
#
# Usage:
#   bash scripts/check_marketplace.sh              # validate current repo
#   bash scripts/check_marketplace.sh /path/to/repo
#
# Runs four checks:
#   1. JSON syntax of .claude-plugin/marketplace.json
#   2. `claude plugin validate .` (skipped if claude CLI missing)
#   3. source+skills resolution (every plugin path points to a real SKILL.md)
#   4. reverse sync (warns when a disk SKILL.md is not registered)
#
# Exit codes:
#   0  all required checks passed (check 4 is warn-only)
#   1  at least one required check failed
#
# Zero external dependencies beyond bash + python3 (ships with macOS and Linux).

set -uo pipefail

REPO="${1:-.}"
if [[ ! -d "$REPO" ]]; then
  echo "FAIL: repo path '$REPO' is not a directory" >&2
  exit 1
fi
REPO="$(cd "$REPO" && pwd)"
MANIFEST="$REPO/.claude-plugin/marketplace.json"

if [[ ! -f "$MANIFEST" ]]; then
  echo "FAIL: $MANIFEST not found" >&2
  exit 1
fi

echo "Validating marketplace at: $REPO"
echo ""

FAILED=0

# --- Check 1: JSON syntax ------------------------------------------------
if python3 -m json.tool "$MANIFEST" >/dev/null 2>&1; then
  echo "PASS [1/4] JSON syntax"
else
  echo "FAIL [1/4] JSON syntax: marketplace.json is not valid JSON"
  python3 -m json.tool "$MANIFEST" 2>&1 | head -5 | sed 's/^/    /'
  FAILED=1
fi

# --- Check 2: claude plugin validate -------------------------------------
if command -v claude >/dev/null 2>&1; then
  if output=$(cd "$REPO" && claude plugin validate . 2>&1); then
    echo "PASS [2/4] claude plugin validate"
  else
    echo "FAIL [2/4] claude plugin validate:"
    echo "$output" | sed 's/^/    /'
    FAILED=1
  fi
else
  echo "SKIP [2/4] claude plugin validate (claude CLI not installed)"
fi

# --- Check 3: source + skills resolution ---------------------------------
if python3 - "$MANIFEST" "$REPO" <<'PY'
import json, os, sys
manifest_path, repo = sys.argv[1], sys.argv[2]
with open(manifest_path) as f:
    data = json.load(f)

errors = []
for plugin in data.get("plugins", []):
    name = plugin.get("name", "<unnamed>")
    source = plugin.get("source", "")
    # Remote sources (github/git/npm) can't be resolved on disk
    if isinstance(source, dict):
        continue
    if not isinstance(source, str) or not source.startswith("./"):
        continue
    root = source.lstrip("./").rstrip("/") or "."
    skills = plugin.get("skills")
    if skills is None:
        skill_dirs = [""]
    else:
        skill_dirs = [s.lstrip("./").rstrip("/") or "" for s in skills]
    for sd in skill_dirs:
        skill_md = os.path.join(repo, root, sd, "SKILL.md")
        if not os.path.isfile(skill_md):
            errors.append(f"    {name}: source={source!r} skill={sd!r} -> missing {os.path.relpath(skill_md, repo)}")

if errors:
    print("FAIL [3/4] source+skills resolution:")
    for e in errors:
        print(e)
    sys.exit(1)
print("PASS [3/4] source+skills resolution")
PY
then
  :
else
  FAILED=1
fi

# --- Check 4: reverse sync (warn-only) -----------------------------------
python3 - "$MANIFEST" "$REPO" <<'PY'
import json, os, sys
manifest_path, repo = sys.argv[1], sys.argv[2]
with open(manifest_path) as f:
    data = json.load(f)

registered = set()
for plugin in data.get("plugins", []):
    source = plugin.get("source", "")
    if isinstance(source, dict) or not isinstance(source, str) or not source.startswith("./"):
        continue
    root = source.lstrip("./").rstrip("/") or "."
    skills = plugin.get("skills") or [""]
    for s in skills:
        sd = s.lstrip("./").rstrip("/") or ""
        full = os.path.normpath(os.path.join(repo, root, sd))
        registered.add(full)

ignored = {".git", "node_modules", "dist", "build", ".claude-plugin", ".githooks", "backups"}
disk = set()
for root_dir, dirs, files in os.walk(repo):
    # Prune hidden and ignored directories
    dirs[:] = [d for d in dirs if d not in ignored and not d.startswith(".")]
    if "SKILL.md" in files:
        disk.add(os.path.normpath(root_dir))

unregistered = disk - registered
if unregistered:
    print("WARN [4/4] disk SKILL.md files not registered in marketplace.json:")
    for u in sorted(unregistered):
        print(f"    {os.path.relpath(u, repo)}")
else:
    print("PASS [4/4] reverse sync")
PY

echo ""
if [[ $FAILED -eq 1 ]]; then
  echo "RESULT: FAILED"
  exit 1
fi
echo "RESULT: PASSED"
