---
name: statusline-generator
description: Configures and customizes Claude Code statuslines with multi-line layouts, cost tracking via ccusage, git status indicators, and customizable colors. Activates for statusline setup, installation, configuration, customization, color changes, cost display, git status integration, or troubleshooting statusline issues.
---

# Statusline Generator

## Overview

This skill provides tools and guidance for creating and customizing Claude Code statuslines. It generates multi-line statuslines optimized for portrait screens, integrates with `ccusage` for session/daily cost tracking, displays git branch status, and supports color customization.

## When to Use This Skill

This skill activates for:
- Statusline configuration requests for Claude Code
- Cost information display (session/daily costs)
- Multi-line layouts for portrait or narrow screens
- Statusline color or format customization
- Statusline display or cost tracking issues
- Git status or path shortening features

## Quick Start

### Basic Installation

Install the default multi-line statusline:

1. Run the installation script:
   ```bash
   bash scripts/install_statusline.sh
   ```

2. Restart Claude Code to see the statusline

The default statusline displays:
- **Line 1**: `username (model) [session_cost/daily_cost]`
- **Line 2**: `current_path`
- **Line 3**: `[git:branch*+]`

### Manual Installation

Alternatively, manually install by:

1. Copy `scripts/generate_statusline.sh` to `~/.claude/statusline.sh`
2. Make it executable: `chmod +x ~/.claude/statusline.sh`
3. Update `~/.claude/settings.json`:
   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "bash /home/username/.claude/statusline.sh",
       "padding": 0
     }
   }
   ```

## Statusline Features

### Multi-Line Layout

The statusline uses a 3-line layout optimized for portrait screens:

```
username (Sonnet 4.5 [1M]) [$0.26/$25.93]
~/workspace/java/ready-together-svc
[git:feature/branch-name*+]
```

**Benefits:**
- Shorter lines fit narrow screens
- Clear visual separation of information types
- No horizontal scrolling needed

### Cost Tracking Integration

Cost tracking via `ccusage`:
- **Session Cost**: Current conversation cost
- **Daily Cost**: Total cost for today
- **Format**: `[$session/$daily]` in magenta
- **Caching**: 2-minute cache to avoid performance impact
- **Background Fetch**: First run loads costs asynchronously

**Requirements:** `ccusage` must be installed and in PATH. See `references/ccusage_integration.md` for installation and troubleshooting.

### Model Name Shortening

Model names are automatically shortened:
- `"Sonnet 4.5 (with 1M token context)"` → `"Sonnet 4.5 [1M]"`
- `"Opus 4.1 (with 500K token context)"` → `"Opus 4.1 [500K]"`

This saves horizontal space while preserving key information.

### Git Status Indicators

Git branch status shows:
- **Yellow**: Clean branch (no changes)
- **Red**: Dirty branch (uncommitted changes)
- **Indicators**:
  - `*` - Modified or staged files
  - `+` - Untracked files
  - Example: `[git:main*+]` - Modified files and untracked files

### Path Shortening

Paths are shortened:
- Home directory replaced with `~`
- Example: `/home/username/workspace/project` → `~/workspace/project`

### Color Scheme

Default colors optimized for visibility:
- **Username**: Bright Green (`\033[01;32m`)
- **Model**: Bright Cyan (`\033[01;36m`)
- **Costs**: Bright Magenta (`\033[01;35m`)
- **Path**: Bright White (`\033[01;37m`)
- **Git (clean)**: Bright Yellow (`\033[01;33m`)
- **Git (dirty)**: Bright Red (`\033[01;31m`)

## Customization

### Changing Colors

Customize colors by editing `~/.claude/statusline.sh` and modifying the ANSI color codes in the final `printf` statement. See `references/color_codes.md` for available colors.

**Example: Change username to blue**
```bash
# Find this line:
printf '\033[01;32m%s\033[00m \033[01;36m(%s)\033[00m%s\n\033[01;37m%s\033[00m\n%s' \

# Change \033[01;32m (green) to \033[01;34m (blue):
printf '\033[01;34m%s\033[00m \033[01;36m(%s)\033[00m%s\n\033[01;37m%s\033[00m\n%s' \
```

### Single-Line Layout

Convert to single-line layout by modifying the final `printf`:

```bash
# Replace:
printf '\033[01;32m%s\033[00m \033[01;36m(%s)\033[00m%s\n\033[01;37m%s\033[00m\n%s' \
    "$username" "$model" "$cost_info" "$short_path" "$git_info"

# With:
printf '\033[01;32m%s\033[00m \033[01;36m(%s)\033[00m:\033[01;37m%s\033[00m%s%s' \
    "$username" "$model" "$short_path" "$git_info" "$cost_info"
```

### Disabling Cost Tracking

If `ccusage` is unavailable or not desired:

1. Comment out the cost section in the script (lines ~47-73)
2. Remove `%s` for `$cost_info` from the final `printf`

See `references/ccusage_integration.md` for details.

### Adding Custom Elements

Add custom information (e.g., hostname, time):

```bash
# Add variable before final printf:
hostname=$(hostname -s)
current_time=$(date +%H:%M)

# Update printf to include new elements:
printf '\033[01;32m%s@%s\033[00m \033[01;36m(%s)\033[00m%s [%s]\n...' \
    "$username" "$hostname" "$model" "$cost_info" "$current_time" ...
```

## Troubleshooting

### Costs Not Showing

**Check:**
1. Is `ccusage` installed? Run `which ccusage`
2. Test `ccusage` manually: `ccusage session --json --offline -o desc`
3. Wait 5-10 seconds after first display (background fetch)
4. Check cache: `ls -lh /tmp/claude_cost_cache_*.txt`

**Solution:** See `references/ccusage_integration.md` for detailed troubleshooting.

### Colors Hard to Read

**Solution:** Adjust colors for your terminal background using `references/color_codes.md`. Bright colors (`01;3X`) are generally more visible than regular (`00;3X`).

### Statusline Not Updating

**Check:**
1. Verify settings.json points to correct script path
2. Ensure script is executable: `chmod +x ~/.claude/statusline.sh`
3. Restart Claude Code

### Git Status Not Showing

**Check:**
1. Are you in a git repository?
2. Test git commands: `git branch --show-current`
3. Check git permissions in the directory

## Resources

### scripts/generate_statusline.sh
Main statusline script with all features (multi-line, ccusage, git, colors). Copy this to `~/.claude/statusline.sh` for use.

### scripts/install_statusline.sh
Automated installation script that copies the statusline script and updates settings.json.

### references/color_codes.md
Complete ANSI color code reference for customizing statusline colors. Load when users request color customization.

### references/ccusage_integration.md
Detailed explanation of ccusage integration, caching strategy, JSON structure, and troubleshooting. Load when users experience cost tracking issues or want to understand how it works.