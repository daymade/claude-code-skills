#!/usr/bin/env bash
# Statusline health check — verify configuration end-to-end.
#
# Runs four layers of verification:
#   1. Script exists and is executable (chmod +x).
#   2. settings.json points to the script and uses type=command.
#   3. Mock stdin tests (minimal + edge cases) — script must output expected shape.
#   4. Real stdin replay (if /tmp/.claude-statusline-last-stdin.json exists from CLAUDE_STATUSLINE_DEBUG).
#
# Usage:
#   bash health_check.sh                     # checks ~/.claude/statusline.sh
#   bash health_check.sh /custom/path.sh     # checks custom script

set -u

SCRIPT_PATH="${1:-$HOME/.claude/statusline.sh}"
SETTINGS_FILE="$HOME/.claude/settings.json"
DEBUG_DUMP="/tmp/.claude-statusline-last-stdin.json"

# Color output only if stdout is a terminal
if [ -t 1 ]; then
    G='\033[01;32m'; R='\033[01;31m'; Y='\033[01;33m'; B='\033[01;36m'; N='\033[00m'
else
    G=''; R=''; Y=''; B=''; N=''
fi

PASS=0
FAIL=0
WARN=0

ok()   { printf "${G}✓${N} %s\n" "$1"; PASS=$((PASS+1)); }
fail() { printf "${R}✗${N} %s\n" "$1"; [ -n "${2:-}" ] && printf "  ${B}fix:${N} %s\n" "$2"; FAIL=$((FAIL+1)); }
warn() { printf "${Y}⚠${N} %s\n" "$1"; [ -n "${2:-}" ] && printf "  ${B}note:${N} %s\n" "$2"; WARN=$((WARN+1)); }
section() { printf "\n${B}== %s ==${N}\n" "$1"; }

# ---------- 1. Script existence + permissions ----------
section "1. Script file"

if [ ! -f "$SCRIPT_PATH" ]; then
    fail "Script not found: $SCRIPT_PATH" "copy generate_statusline.sh from this skill to that path"
    echo
    printf "${R}HARD FAIL — cannot continue checks${N}\n"
    exit 1
fi
ok "Script exists: $SCRIPT_PATH"

if [ ! -x "$SCRIPT_PATH" ]; then
    fail "Script not executable (this is the #1 silent-failure cause)" "chmod +x '$SCRIPT_PATH'"
else
    ok "Script is executable (chmod +x)"
fi

# ---------- 2. settings.json wiring ----------
section "2. settings.json wiring"

if [ ! -f "$SETTINGS_FILE" ]; then
    fail "settings.json not found: $SETTINGS_FILE" "create it with statusLine block, see SKILL.md Quick Start"
elif command -v jq >/dev/null 2>&1; then
    sl_type=$(jq -r '.statusLine.type // "MISSING"' "$SETTINGS_FILE" 2>/dev/null)
    sl_cmd=$(jq -r '.statusLine.command // "MISSING"' "$SETTINGS_FILE" 2>/dev/null)

    if [ "$sl_type" = "MISSING" ]; then
        fail "settings.json has no statusLine block" "run install_statusline.sh"
    elif [ "$sl_type" != "command" ]; then
        fail "statusLine.type is '$sl_type', expected 'command'" "set statusLine.type to \"command\""
    else
        ok "statusLine.type = command"
    fi

    if [ "$sl_cmd" = "MISSING" ]; then
        fail "statusLine.command is missing" "set it to a path or shell command"
    else
        # Expand ~ for comparison
        sl_cmd_expanded="${sl_cmd/#\~/$HOME}"
        # Strip leading "bash " if user wrapped it
        sl_cmd_stripped="${sl_cmd_expanded#bash }"
        if [ "$sl_cmd_stripped" = "$SCRIPT_PATH" ] || [ "$sl_cmd_expanded" = "$SCRIPT_PATH" ]; then
            ok "statusLine.command points to $SCRIPT_PATH"
        else
            warn "statusLine.command = '$sl_cmd' (expected to reference $SCRIPT_PATH)" \
                 "edit settings.json statusLine.command if you intended to use this script"
        fi
    fi
else
    warn "jq not installed — cannot validate settings.json structure" "brew install jq (or apt install jq)"
fi

# ---------- 3. Mock stdin tests ----------
section "3. Mock stdin tests (minimal layout)"

run_mock() {
    local label="$1" json="$2" expect_pattern="$3"
    local out
    out=$(echo "$json" | "$SCRIPT_PATH" 2>&1)
    if echo "$out" | grep -Eq "$expect_pattern"; then
        ok "$label"
        printf "    output: %s\n" "$out"
    else
        fail "$label — output didn't match expected shape" "expected pattern: $expect_pattern; got: $out"
    fi
}

# Test 1: complete data
run_mock "complete data → renders cwd + model + ctx" \
    '{"workspace":{"current_dir":"/tmp/test"},"model":{"display_name":"TestModel"},"context_window":{"context_window_size":1000000,"current_usage":{"input_tokens":50000,"cache_read_input_tokens":0,"cache_creation_input_tokens":50000}}}' \
    'TestModel.*ctx: 100K / 1M'

# Test 2: zero tokens (session start)
run_mock "0 tokens (session just started)" \
    '{"workspace":{"current_dir":"/tmp/test"},"model":{"display_name":"M"},"context_window":{"context_window_size":1000000,"current_usage":{"input_tokens":0,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}' \
    'ctx: 0 / 1M'

# Test 3: missing context_window entirely
run_mock "missing context_window field → no ctx segment" \
    '{"workspace":{"current_dir":"/tmp/test"},"model":{"display_name":"M"}}' \
    '/tmp/test  M'

# Test 4: cwd in HOME → tilde shortening
run_mock "cwd in HOME → ~ short path" \
    "{\"workspace\":{\"current_dir\":\"$HOME/x/y\"},\"model\":{\"display_name\":\"M\"}}" \
    '~/x/y'

# ---------- 4. Real stdin replay (if available) ----------
section "4. Real stdin replay"

if [ -f "$DEBUG_DUMP" ]; then
    out=$(cat "$DEBUG_DUMP" | "$SCRIPT_PATH" 2>&1)
    if [ -n "$out" ]; then
        ok "Real stdin from $DEBUG_DUMP renders successfully"
        printf "    output: %s\n" "$out"
    else
        fail "Real stdin produced empty output" "inspect $DEBUG_DUMP and run: cat $DEBUG_DUMP | $SCRIPT_PATH"
    fi
else
    warn "No real stdin dump available at $DEBUG_DUMP" \
         "to capture: export CLAUDE_STATUSLINE_DEBUG=1, send any message in Claude Code, re-run this check"
fi

# ---------- Summary ----------
section "Summary"
printf "Pass: ${G}%d${N}    Fail: ${R}%d${N}    Warn: ${Y}%d${N}\n" "$PASS" "$FAIL" "$WARN"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
