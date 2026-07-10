#!/usr/bin/env bash
# setup_supersede_hook.sh — install / uninstall / status for the
# generated skill's supersede hook.
#
# The hook is installed ONLY when the competing plugin
# coexists with the generated skill. On
# machines without the competing plugin, `install` is a refusal no-op:
# nothing is copied, nothing is registered, zero footprint.
#
# What `install` does (after the coexistence check passes):
#   1. copies supersede-routing-hook.sh to <claude-config>/hooks/
#   2. backs up settings.json, then appends one SessionStart command hook
#      entry to it (idempotent — a second install is a no-op)
# `uninstall` reverses both steps. `status` reports the current state.
#
# Respects CLAUDE_CONFIG_DIR (defaults to ~/.claude). Requires python3 for
# safe JSON editing of settings.json.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_SOURCE="$SCRIPT_DIR/supersede-routing-hook.sh"
SKILL_NAME=skill-creator
COMPETITOR_PLUGIN_ID=skill-creator@claude-plugins-official
HOOK_BASENAME=skill-creator-supersede-hook.sh

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
MANIFEST="$CLAUDE_DIR/plugins/installed_plugins.json"
SETTINGS="$CLAUDE_DIR/settings.json"
HOOK_DEST="$CLAUDE_DIR/hooks/$HOOK_BASENAME"

competitor_installed() {
  [ -f "$MANIFEST" ] && grep -Fq -- "\"$COMPETITOR_PLUGIN_ID\"" "$MANIFEST" 2>/dev/null
}

settings_entry_state() {
  # prints "present" / "absent" / "no-settings"
  python3 - "$SETTINGS" "$HOOK_BASENAME" <<'PY'
import json, sys
path, marker = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        d = json.load(f)
except FileNotFoundError:
    print("no-settings"); sys.exit(0)
except (OSError, json.JSONDecodeError) as exc:
    print("cannot read settings.json: %s" % exc, file=sys.stderr); sys.exit(1)

if not isinstance(d, dict):
    print("settings.json root must be an object", file=sys.stderr); sys.exit(1)
hooks = d.get("hooks", {})
if not isinstance(hooks, dict):
    print("settings.json hooks must be an object", file=sys.stderr); sys.exit(1)
groups = hooks.get("SessionStart", [])
if not isinstance(groups, list):
    print("settings.json hooks.SessionStart must be an array", file=sys.stderr); sys.exit(1)
for group in groups:
    if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
        print("invalid SessionStart hook group", file=sys.stderr); sys.exit(1)
    for h in group.get("hooks", []):
        if not isinstance(h, dict):
            print("invalid SessionStart hook entry", file=sys.stderr); sys.exit(1)
        if marker in h.get("command", ""):
            print("present"); sys.exit(0)
print("absent")
PY
}

cmd_status() {
  local state
  if ! state="$(settings_entry_state)"; then
    echo "settings.json: unreadable or invalid; status aborted" >&2
    return 1
  fi
  echo "claude config dir : $CLAUDE_DIR"
  if competitor_installed; then
    echo "competing plugin  : installed (coexistence — hook is applicable)"
  else
    echo "competing plugin  : not installed (hook not needed)"
  fi
  if [ -f "$HOOK_DEST" ]; then
    echo "hook script       : $HOOK_DEST"
  else
    echo "hook script       : not installed"
  fi
  echo "settings.json     : SessionStart entry $state"
}

cmd_install() {
  local state result hook_backup="" hook_created=0
  if ! competitor_installed; then
    echo "The competing plugin ($COMPETITOR_PLUGIN_ID) is NOT installed on this machine."
    echo "There is no routing ambiguity to fix — refusing to install the hook."
    echo "Nothing was copied or registered."
    exit 0
  fi

  # Validate settings before creating or copying anything. A malformed file
  # must leave zero installation footprint.
  if ! state="$(settings_entry_state)"; then
    echo "settings.json is unreadable or invalid; install aborted" >&2
    return 1
  fi

  if ! mkdir -p "$CLAUDE_DIR/hooks"; then
    echo "cannot create Claude hooks directory" >&2
    return 1
  fi
  if [ -f "$HOOK_DEST" ]; then
    if ! hook_backup="$(mktemp "${HOOK_DEST}.backup.XXXXXX")" \
       || ! cp "$HOOK_DEST" "$hook_backup"; then
      [ -n "$hook_backup" ] && rm -f "$hook_backup"
      echo "cannot back up existing hook script" >&2
      return 1
    fi
  else
    hook_created=1
  fi
  if ! cp "$HOOK_SOURCE" "$HOOK_DEST" || ! chmod +x "$HOOK_DEST"; then
    if [ "$hook_created" -eq 1 ]; then
      rm -f "$HOOK_DEST"
    else
      mv "$hook_backup" "$HOOK_DEST"
      hook_backup=""
    fi
    echo "cannot install hook script" >&2
    return 1
  fi
  echo "hook script installed: $HOOK_DEST"

  if ! result=$(python3 - "$SETTINGS" "$HOOK_DEST" "$HOOK_BASENAME" <<'PY'
import json, sys, time, shutil, os
settings_path, hook_dest, marker = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(settings_path) as f:
        d = json.load(f)
except FileNotFoundError:
    d = {}
except (OSError, json.JSONDecodeError) as exc:
    print("cannot read settings.json: %s" % exc, file=sys.stderr); sys.exit(1)

if not isinstance(d, dict):
    print("settings.json root must be an object", file=sys.stderr); sys.exit(1)
hooks = d.setdefault("hooks", {})
if not isinstance(hooks, dict):
    print("settings.json hooks must be an object", file=sys.stderr); sys.exit(1)
groups = hooks.setdefault("SessionStart", [])
if not isinstance(groups, list):
    print("settings.json hooks.SessionStart must be an array", file=sys.stderr); sys.exit(1)

for group in groups:
    if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
        print("invalid SessionStart hook group", file=sys.stderr); sys.exit(1)
    for h in group.get("hooks", []):
        if not isinstance(h, dict):
            print("invalid SessionStart hook entry", file=sys.stderr); sys.exit(1)
        if marker in h.get("command", ""):
            print("already-registered")
            sys.exit(0)

backup = None
if os.path.exists(settings_path):
    backup = settings_path + ".bak-supersede-hook-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(settings_path, backup)
groups.append({
    "hooks": [
        {"type": "command", "command": 'bash "%s"' % hook_dest, "timeout": 10}
    ]
})
tmp = settings_path + ".tmp-supersede-hook"
try:
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, settings_path)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
print("registered" + (" (backup: %s)" % backup if backup else ""))
PY
  ); then
    if [ "$hook_created" -eq 1 ]; then
      rm -f "$HOOK_DEST"
    else
      mv "$hook_backup" "$HOOK_DEST"
      hook_backup=""
    fi
    echo "settings.json update failed; hook installation rolled back" >&2
    return 1
  fi
  [ -n "$hook_backup" ] && rm -f "$hook_backup"
  echo "settings.json: $result"
  if [ "$result" != "already-registered" ]; then
    echo "Done. The routing hook takes effect from the NEXT Claude Code session."
  fi
}

cmd_uninstall() {
  local result
  if ! result=$(python3 - "$SETTINGS" "$HOOK_BASENAME" <<'PY'
import json, sys, time, shutil, os
settings_path, marker = sys.argv[1], sys.argv[2]
try:
    with open(settings_path) as f:
        d = json.load(f)
except FileNotFoundError:
    print("no-settings"); sys.exit(0)
except (OSError, json.JSONDecodeError) as exc:
    print("cannot read settings.json: %s" % exc, file=sys.stderr); sys.exit(1)

if not isinstance(d, dict):
    print("settings.json root must be an object", file=sys.stderr); sys.exit(1)
hooks = d.get("hooks", {})
if not isinstance(hooks, dict):
    print("settings.json hooks must be an object", file=sys.stderr); sys.exit(1)
groups = hooks.get("SessionStart", [])
if not isinstance(groups, list):
    print("settings.json hooks.SessionStart must be an array", file=sys.stderr); sys.exit(1)

kept, removed = [], 0
for group in groups:
    if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
        print("invalid SessionStart hook group", file=sys.stderr); sys.exit(1)
    entries = group.get("hooks", [])
    if any(not isinstance(entry, dict) for entry in entries):
        print("invalid SessionStart hook entry", file=sys.stderr); sys.exit(1)
    filtered = [entry for entry in entries if marker not in entry.get("command", "")]
    removed_here = len(entries) - len(filtered)
    removed += removed_here
    if not removed_here:
        kept.append(group)
    elif filtered:
        updated_group = dict(group)
        updated_group["hooks"] = filtered
        kept.append(updated_group)
if not removed:
    print("not-registered"); sys.exit(0)

backup = settings_path + ".bak-supersede-hook-" + time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(settings_path, backup)
d["hooks"]["SessionStart"] = kept
if not d["hooks"]["SessionStart"]:
    del d["hooks"]["SessionStart"]
if not d["hooks"]:
    del d["hooks"]
tmp = settings_path + ".tmp-supersede-hook"
try:
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, settings_path)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
print("removed %d hook entr%s (backup: %s)" % (removed, "y" if removed == 1 else "ies", backup))
PY
  ); then
    echo "settings.json is unreadable or invalid; uninstall aborted" >&2
    return 1
  fi
  echo "settings.json: $result"
  if [ -f "$HOOK_DEST" ]; then
    if ! rm -f "$HOOK_DEST"; then
      echo "cannot remove hook script" >&2
      return 1
    fi
    echo "hook script removed: $HOOK_DEST"
  else
    echo "hook script: not present"
  fi
}

case "${1:-}" in
  install)   cmd_install ;;
  uninstall) cmd_uninstall ;;
  status)    cmd_status ;;
  *)
    echo "Usage: $0 {install|uninstall|status}"
    echo "Installs the $SKILL_NAME supersede hook — only applicable when"
    echo "$COMPETITOR_PLUGIN_ID coexists with the $SKILL_NAME skill."
    echo "Respects CLAUDE_CONFIG_DIR."
    exit 1
    ;;
esac
