#!/usr/bin/env bash
# Claude Code statusline — single source of truth.
#
# Default (minimal):  ~/short/path  Model Name  ctx: 108K / 1M
# Full layout:
#   user (Model) [$session/$daily]  ctx: 108K / 1M (11%)
#   ~/short/path
#   [git:branch*+]
#
# Configuration via environment variables (no flags — Claude Code passes JSON on stdin):
#   CLAUDE_STATUSLINE_LAYOUT=full     enable multi-line cost/git/percentage layout
#   CLAUDE_STATUSLINE_DEBUG=1         dump stdin to /tmp/.claude-statusline-last-stdin.json
#                                     (for end-to-end verification, see health_check.sh)
#
# Dependencies: jq preferred (python3 fallback). awk for number formatting.
# Optional: git (for full layout's git status), ccusage (for cost display in full layout).

input=$(cat)

if [ -n "$CLAUDE_STATUSLINE_DEBUG" ]; then
    printf '%s' "$input" > /tmp/.claude-statusline-last-stdin.json 2>/dev/null
fi

LAYOUT="${CLAUDE_STATUSLINE_LAYOUT:-minimal}"

# ---------- JSON field extraction (jq preferred, python3 fallback) ----------
parse_with_jq() {
    echo "$input" | jq -r '
      [
        (.model.display_name // "Claude"),
        (.workspace.current_dir // ""),
        (.context_window.context_window_size // 0),
        (.context_window.current_usage.input_tokens // 0),
        (.context_window.current_usage.cache_read_input_tokens // 0),
        (.context_window.current_usage.cache_creation_input_tokens // 0),
        (.context_window.used_percentage // 0),
        (.cost.total_cost_usd // 0)
      ] | @tsv
    '
}

parse_with_python() {
    echo "$input" | python3 -c '
import json, sys
d = json.load(sys.stdin)
cw = d.get("context_window") or {}
cu = cw.get("current_usage") or {}
print("\t".join(str(v) for v in [
    d.get("model", {}).get("display_name", "Claude"),
    d.get("workspace", {}).get("current_dir", ""),
    cw.get("context_window_size", 0) or 0,
    cu.get("input_tokens", 0) or 0,
    cu.get("cache_read_input_tokens", 0) or 0,
    cu.get("cache_creation_input_tokens", 0) or 0,
    cw.get("used_percentage", 0) or 0,
    (d.get("cost") or {}).get("total_cost_usd", 0) or 0,
]))
'
}

if command -v jq >/dev/null 2>&1; then
    parsed=$(parse_with_jq)
elif command -v python3 >/dev/null 2>&1; then
    parsed=$(parse_with_python)
else
    # No JSON parser — degrade to bare cwd
    echo "$PWD"
    exit 0
fi

IFS=$'\t' read -r model_full cwd ctx_size ctx_input ctx_cache_read ctx_cache_create ctx_pct cost_raw <<< "$parsed"

cwd="${cwd:-$PWD}"
ctx_size="${ctx_size:-0}"
ctx_used=$((${ctx_input:-0} + ${ctx_cache_read:-0} + ${ctx_cache_create:-0}))
ctx_pct_int=$(printf '%.0f' "${ctx_pct:-0}" 2>/dev/null || echo 0)
short_path="${cwd/#$HOME/~}"

# ---------- Helpers ----------
# Format token counts: 999 / 108K / 1M / 1.5M
human_tokens() {
    awk -v n="${1:-0}" 'BEGIN {
        n = n + 0
        if (n >= 1000000) {
            m = n / 1000000
            if (m == int(m)) printf "%dM", m
            else printf "%.1fM", m
        } else if (n >= 1000) {
            printf "%dK", int(n/1000 + 0.5)
        } else {
            printf "%d", n
        }
    }'
}

# ---------- Minimal layout (default) ----------
render_minimal() {
    local out="$short_path"
    [ -n "$model_full" ] && out="${out}  ${model_full}"
    if [ "${ctx_size:-0}" -gt 0 ] 2>/dev/null; then
        out="${out}  ctx: $(human_tokens "$ctx_used") / $(human_tokens "$ctx_size")"
    fi
    echo "$out"
}

# ---------- Full layout (multi-line: cost + git + percentage) ----------
render_full() {
    local username
    username=$(whoami)

    # Color threshold by ctx percentage
    local ctx_color="\033[01;32m"   # green ≤50%
    if [ "${ctx_pct_int:-0}" -gt 80 ]; then
        ctx_color="\033[01;31m"     # red >80%
    elif [ "${ctx_pct_int:-0}" -gt 50 ]; then
        ctx_color="\033[01;33m"     # yellow 51-80%
    fi

    # Model name shortening: "Sonnet 4.5 (with 1M token context)" -> "Sonnet 4.5 [1M]"
    local model
    model=$(echo "$model_full" \
        | sed -E 's/\(with ([0-9]+[KM]) token context\)/[\1]/' \
        | sed -E 's/\[1m\]/[1M]/' \
        | sed 's/ *$//')

    # Git status (best-effort; silent if not a git repo or git missing)
    local git_info=""
    if command -v git >/dev/null 2>&1 && \
       git -C "$cwd" --no-optional-locks rev-parse --git-dir >/dev/null 2>&1; then
        local branch status=""
        branch=$(git -C "$cwd" --no-optional-locks branch --show-current 2>/dev/null || echo "detached")
        if ! git -C "$cwd" --no-optional-locks diff --quiet 2>/dev/null || \
           ! git -C "$cwd" --no-optional-locks diff --cached --quiet 2>/dev/null; then
            status="*"
        fi
        if [ -n "$(git -C "$cwd" --no-optional-locks ls-files --others --exclude-standard 2>/dev/null)" ]; then
            status="${status}+"
        fi
        if [ -n "$status" ]; then
            git_info=$(printf '\033[01;31m[git:%s%s]\033[00m' "$branch" "$status")
        else
            git_info=$(printf '\033[01;33m[git:%s]\033[00m' "$branch")
        fi
    fi

    # Cost via ccusage (cached, async; silent if ccusage unavailable)
    local cost_info=""
    if command -v ccusage >/dev/null 2>&1; then
        local cache_file="/tmp/claude_cost_cache_$(date +%Y%m%d_%H%M).txt"
        find /tmp -maxdepth 1 -name "claude_cost_cache_*.txt" -mmin +2 -delete 2>/dev/null
        if [ -f "$cache_file" ]; then
            cost_info=$(cat "$cache_file")
        else
            {
                local session daily
                if command -v jq >/dev/null 2>&1; then
                    session=$(ccusage session --json --offline -o desc 2>/dev/null | jq -r '.sessions[0].totalCost // 0' | xargs printf "%.2f" 2>/dev/null)
                    daily=$(ccusage daily --json --offline -o desc 2>/dev/null | jq -r '.daily[0].totalCost // 0' | xargs printf "%.2f" 2>/dev/null)
                else
                    session=$(ccusage session --json --offline -o desc 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); s=d.get('sessions',[{}])[0]; print(f\"{s.get('totalCost',0):.2f}\")" 2>/dev/null)
                    daily=$(ccusage daily --json --offline -o desc 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); s=d.get('daily',[{}])[0]; print(f\"{s.get('totalCost',0):.2f}\")" 2>/dev/null)
                fi
                if [ -n "$session" ] && [ -n "$daily" ]; then
                    printf ' \033[01;35m[$%s/$%s]\033[00m' "$session" "$daily" > "$cache_file"
                fi
            } &
            local prev_cache
            prev_cache=$(find /tmp -maxdepth 1 -name "claude_cost_cache_*.txt" -mmin -10 2>/dev/null | head -1)
            [ -f "$prev_cache" ] && cost_info=$(cat "$prev_cache")
        fi
    fi

    # Context display
    local ctx_display=""
    if [ "${ctx_size:-0}" -gt 0 ] 2>/dev/null; then
        ctx_display=$(printf "  ${ctx_color}ctx: %s/%s (%s%%)\033[00m" \
            "$(human_tokens "$ctx_used")" "$(human_tokens "$ctx_size")" "$ctx_pct_int")
    fi

    # Three lines: header / path / git
    printf '\033[01;32m%s\033[00m \033[01;36m(%s)\033[00m%s%s\n\033[01;37m%s\033[00m\n%s' \
        "$username" "$model" "$cost_info" "$ctx_display" "$short_path" "$git_info"
}

case "$LAYOUT" in
    full) render_full ;;
    minimal|*) render_minimal ;;
esac
