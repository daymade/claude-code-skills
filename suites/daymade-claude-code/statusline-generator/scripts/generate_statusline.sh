#!/usr/bin/env bash

# Read JSON input from stdin
input=$(cat)

# Extract values from JSON
model_full=$(echo "$input" | jq -r '.model.display_name' 2>/dev/null || echo "Claude")
cwd=$(echo "$input" | jq -r '.workspace.current_dir' 2>/dev/null || pwd)
transcript=$(echo "$input" | jq -r '.transcript_path' 2>/dev/null)

# Shorten model name: "Sonnet 4.5 (with 1M token context)" -> "Sonnet 4.5 [1M]"
model=$(echo "$model_full" | sed -E 's/(.*)\(with ([0-9]+[KM]) token context\)/\1[\2]/' | sed 's/ *$//')

# Get username
username=$(whoami)

# Shorten path (replace home with ~)
short_path="${cwd/#$HOME/~}"

# Git branch status
git_info=""
if [ -d "$cwd/.git" ] || git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
    branch=$(git -C "$cwd" --no-optional-locks branch --show-current 2>/dev/null || echo "detached")

    # Check for changes
    status=""
    if ! git -C "$cwd" --no-optional-locks diff --quiet 2>/dev/null || \
       ! git -C "$cwd" --no-optional-locks diff --cached --quiet 2>/dev/null; then
        status="*"
    fi

    # Check for untracked files
    if [ -n "$(git -C "$cwd" --no-optional-locks ls-files --others --exclude-standard 2>/dev/null)" ]; then
        status="${status}+"
    fi

    # Format git info with color
    if [ -n "$status" ]; then
        # Red for dirty
        git_info=$(printf ' \033[01;31m[git:%s%s]\033[00m' "$branch" "$status")
    else
        # Yellow for clean
        git_info=$(printf ' \033[01;33m[git:%s]\033[00m' "$branch")
    fi
fi

# Cost information using ccusage with caching
cost_info=""
cache_file="/tmp/claude_cost_cache_$(date +%Y%m%d_%H%M).txt"

# Clean old cache files (older than 2 minutes)
find /tmp -name "claude_cost_cache_*.txt" -mmin +2 -delete 2>/dev/null

if [ -f "$cache_file" ]; then
    # Use cached costs
    cost_info=$(cat "$cache_file")
else
    # Get costs from ccusage (in background to not block statusline on first run)
    {
        session=$(ccusage session --json --offline -o desc 2>/dev/null | jq -r '.sessions[0].totalCost' 2>/dev/null | xargs printf "%.2f")
        daily=$(ccusage daily --json --offline -o desc 2>/dev/null | jq -r '.daily[0].totalCost' 2>/dev/null | xargs printf "%.2f")

        if [ -n "$session" ] && [ -n "$daily" ] && [ "$session" != "" ] && [ "$daily" != "" ]; then
            printf ' \033[01;35m[$%s/$%s]\033[00m' "$session" "$daily" > "$cache_file"
        fi
    } &

    # Try to use previous cache while new one is being generated
    prev_cache=$(find /tmp -name "claude_cost_cache_*.txt" -mmin -10 2>/dev/null | head -1)
    if [ -f "$prev_cache" ]; then
        cost_info=$(cat "$prev_cache")
    fi
fi

# Print the final status line (multi-line format for portrait screens)
# Line 1: username (model) [costs]
# Line 2: path (bright white for better visibility)
# Line 3: [git:branch]
printf '\033[01;32m%s\033[00m \033[01;36m(%s)\033[00m%s\n\033[01;37m%s\033[00m\n%s' \
    "$username" "$model" "$cost_info" "$short_path" "$git_info"