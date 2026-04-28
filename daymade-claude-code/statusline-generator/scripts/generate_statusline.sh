#!/usr/bin/env bash
# Statusline script — multi-line layout with context window, cost, git
# Dependencies: git, awk.  jq preferred; python3 used as fallback if jq missing.

input=$(cat)

# --- JSON field extraction (jq with python3 fallback) ---
if command -v jq &>/dev/null; then
    IFS=$'\t' read -r model_full cwd ctx_used_pct cost_raw ctx_size \
      ctx_input ctx_cache_read ctx_cache_create <<< \
    "$(echo "$input" | jq -r '
      [
        (.model.display_name // "Claude"),
        (.workspace.current_dir // ""),
        (.context_window.used_percentage // 0),
        (.cost.total_cost_usd // 0),
        (.context_window.context_window_size // 0),
        (.context_window.current_usage.input_tokens // 0),
        (.context_window.current_usage.cache_read_input_tokens // 0),
        (.context_window.current_usage.cache_creation_input_tokens // 0)
      ] | @tsv
    ')"
else
    # Windows / no-jq: fall back to python3 (stdlib only, no pip needed)
    IFS=$'\t' read -r model_full cwd ctx_used_pct cost_raw ctx_size \
      ctx_input ctx_cache_read ctx_cache_create <<< \
    "$(echo "$input" | python3 -c '
import json, sys
d = json.load(sys.stdin)
cw = d.get("context_window", {})
cu = cw.get("current_usage", {})
vals = [
    d.get("model", {}).get("display_name", "Claude"),
    d.get("workspace", {}).get("current_dir", ""),
    cw.get("used_percentage", 0),
    d.get("cost", {}).get("total_cost_usd", 0),
    cw.get("context_window_size", 0),
    cu.get("input_tokens", 0),
    cu.get("cache_read_input_tokens", 0),
    cu.get("cache_creation_input_tokens", 0),
]
print("\t".join(str(v) for v in vals))
')"
fi

# coerce percentage to int safely
ctx_used_pct=$(printf '%.0f' "${ctx_used_pct:-0}" 2>/dev/null || echo 0)

# --- derived values ---
cwd="${cwd:-$PWD}"
ctx_used=$((ctx_input + ctx_cache_read + ctx_cache_create))

# human-readable number formatter
human() {
    local n=${1:-0}
    if [ "$n" -ge 1000000 ]; then
        awk -v v="$n" 'BEGIN {printf "%.1fM", v/1000000}'
    elif [ "$n" -ge 1000 ]; then
        awk -v v="$n" 'BEGIN {printf "%.1fK", v/1000}'
    else
        echo "$n"
    fi
}

ctx_used_h=$(human $ctx_used)
ctx_size_h=$(human $ctx_size)
cost=$(echo "$cost_raw" | awk '{printf "%.2f", $1}')

# model name shortening
model=$(echo "$model_full" \
    | sed -E 's/\(with ([0-9]+[KM]) token context\)/[\1]/' \
    | sed -E 's/\[1m\]/[1M]/' \
    | sed 's/ *$//')

username=$(whoami)
short_path="${cwd/#$HOME/\~}"

# --- context color thresholds ---
ctx_color="\033[01;32m"   # green ≤50%
if [ "$ctx_used_pct" -gt 80 ]; then
    ctx_color="\033[01;31m"  # red >80%
elif [ "$ctx_used_pct" -gt 50 ]; then
    ctx_color="\033[01;33m"  # yellow 51-80%
fi

# --- git branch status ---
git_info=""
if [ -d "$cwd/.git" ] || git -C "$cwd" --no-optional-locks rev-parse --git-dir >/dev/null 2>&1; then
    branch=$(git -C "$cwd" --no-optional-locks branch --show-current 2>/dev/null || echo "detached")

    status=""
    if ! git -C "$cwd" --no-optional-locks diff --quiet 2>/dev/null || \
       ! git -C "$cwd" --no-optional-locks diff --cached --quiet 2>/dev/null; then
        status="*"
    fi
    if [ -n "$(git -C "$cwd" --no-optional-locks ls-files --others --exclude-standard 2>/dev/null)" ]; then
        status="${status}+"
    fi

    if [ -n "$status" ]; then
        git_info=$(printf ' \033[01;31m[git:%s%s]\033[00m' "$branch" "$status")
    else
        git_info=$(printf ' \033[01;33m[git:%s]\033[00m' "$branch")
    fi
fi

# --- cost via ccusage (async, non-blocking; requires jq or python3) ---
cost_info=""
if command -v jq &>/dev/null || command -v python3 &>/dev/null; then
    cache_file="/tmp/claude_cost_cache_$(date +%Y%m%d_%H%M).txt"
    find /tmp -name "claude_cost_cache_*.txt" -mmin +2 -delete 2>/dev/null

    if [ -f "$cache_file" ]; then
        cost_info=$(cat "$cache_file")
    else
        {
            if command -v jq &>/dev/null; then
                session=$(ccusage session --json --offline -o desc 2>/dev/null | jq -r '.sessions[0].totalCost' 2>/dev/null | xargs printf "%.2f" 2>/dev/null)
                daily=$(ccusage daily --json --offline -o desc 2>/dev/null | jq -r '.daily[0].totalCost' 2>/dev/null | xargs printf "%.2f" 2>/dev/null)
            else
                session=$(ccusage session --json --offline -o desc 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d['sessions'][0]['totalCost']:.2f}\")" 2>/dev/null)
                daily=$(ccusage daily --json --offline -o desc 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d['daily'][0]['totalCost']:.2f}\")" 2>/dev/null)
            fi
            if [ -n "$session" ] && [ -n "$daily" ] && [ "$session" != "" ] && [ "$daily" != "" ]; then
                printf ' \033[01;35m[$%s/$%s]\033[00m' "$session" "$daily" > "$cache_file"
            fi
        } &
        prev_cache=$(find /tmp -name "claude_cost_cache_*.txt" -mmin -10 2>/dev/null | head -1)
        if [ -f "$prev_cache" ]; then
            cost_info=$(cat "$prev_cache")
        fi
    fi
fi

# --- context display string ---
ctx_display=""
if [ "$ctx_size" -gt 0 ]; then
    ctx_display=$(printf "  ${ctx_color}ctx: %s/%s (%s%%)" "$ctx_used_h" "$ctx_size_h" "$ctx_used_pct")
fi

# --- output: 3-line layout ---
# Line 1: username (model) [costs]  ctx: used/total (pct%)
# Line 2: path
# Line 3: [git:branch]
printf '\033[01;32m%s\033[00m \033[01;36m(%s)\033[00m%s%s\n\033[01;37m%s\033[00m\n%s' \
    "$username" "$model" "$cost_info" "$ctx_display" "$short_path" "$git_info"
