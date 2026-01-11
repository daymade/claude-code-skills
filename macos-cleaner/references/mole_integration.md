# Mole Integration Guide

How to integrate [Mole](https://github.com/tw93/Mole) with the macOS Cleaner skill.

## About Mole

**Mole** is a command-line interface (CLI) tool for macOS disk cleanup. It provides:

- Interactive terminal-based disk usage analysis
- Comprehensive cleanup for caches, logs, and application remnants
- Developer environment cleanup (Docker, npm, pip, Homebrew, etc.)
- Safe deletion with preview (`--dry-run`)

**Repository**: https://github.com/tw93/Mole

## Critical: TTY Environment Required

**IMPORTANT**: Mole requires a TTY (terminal) environment for interactive commands. When running Mole from automated environments (scripts, Claude Code, CI/CD), use `tmux` to provide a proper TTY.

```bash
# Create tmux session for Mole commands
tmux new-session -d -s mole -x 120 -y 40

# Send command to tmux session
tmux send-keys -t mole 'mo analyze' Enter

# Capture output
tmux capture-pane -t mole -p

# Clean up when done
tmux kill-session -t mole
```

## Installation

### Check if Mole is Installed

```bash
# Check if mole command exists
which mo && mo --version
```

Expected output:
```
/opt/homebrew/bin/mo
Mole version X.Y.Z
macOS: XX.X
Architecture: arm64
...
```

### Installation via Homebrew (Recommended)

```bash
brew install tw93/tap/mole
```

### Version Check and Update

**IMPORTANT**: Always check if Mole is up-to-date before use. The tool updates frequently with bug fixes and new features.

```bash
# Check current vs latest version
brew info tw93/tap/mole | head -5

# If outdated, upgrade
brew upgrade tw93/tap/mole
```

## Available Commands

**CRITICAL**: Only use `mo --help` to view help. Do NOT append `--help` to other commands as it may cause unexpected behavior.

```bash
# View all commands (SAFE - the only help command)
mo --help
```

Available commands from `mo --help`:

| Command | Description | Safety |
|---------|-------------|--------|
| `mo` | Interactive main menu | Requires TTY |
| `mo clean` | Free up disk space | **DANGEROUS** - deletes files |
| `mo clean --dry-run` | Preview cleanup (no deletion) | Safe |
| `mo analyze` | Explore disk usage | Safe (read-only) |
| `mo status` | Monitor system health | Safe (read-only) |
| `mo uninstall` | Remove apps completely | **DANGEROUS** |
| `mo purge` | Remove old project artifacts | **DANGEROUS** |
| `mo optimize` | Check and maintain system | Caution required |
| `mo installer` | Find and remove installer files | Caution required |

## mo analyze vs mo clean --dry-run

**CRITICAL**: These are two different tools with different purposes. Use the right tool for the job.

### Comparison Table

| Aspect | `mo analyze` | `mo clean --dry-run` |
|--------|--------------|---------------------|
| **Primary Purpose** | Explore disk usage interactively | Preview cleanup categories |
| **Use When** | Understanding what consumes space | Ready to see cleanup options |
| **Interface** | Interactive TUI with tree navigation | Static list output |
| **Navigation** | Arrow keys to drill into directories | No navigation |
| **Detail Level** | Full directory breakdown | Only cleanup-eligible items |
| **Recommended Order** | **Use FIRST** | Use SECOND (after analyze) |

### When to Use Each

**Use `mo analyze` when:**
- User asks "What's taking up space?" or "Where is my disk space going?"
- Need to understand storage consumption patterns
- Want to explore specific directories interactively
- Investigating unexpected disk usage

**Use `mo clean --dry-run` when:**
- Already know what's consuming space (after `mo analyze`)
- User is ready to see cleanup recommendations
- Need a quick preview of what can be cleaned
- Preparing to run `mo clean` for actual cleanup

### Workflow Recommendation

```
Step 1: mo analyze (understand the problem)
    ↓
Step 2: Present findings to user
    ↓
Step 3: mo clean --dry-run (show cleanup options)
    ↓
Step 4: User confirms cleanup categories
    ↓
Step 5: User runs mo clean (actual cleanup)
```

### Common Mistake

```bash
# ❌ WRONG: Jumping straight to cleanup preview
tmux send-keys -t mole 'mo clean --dry-run' Enter
# This only shows cleanup-eligible items, not the full picture

# ✅ CORRECT: Start with disk analysis
tmux send-keys -t mole 'mo analyze' Enter
# This shows where ALL disk space is going
```

### Interactive TUI Navigation (mo analyze)

`mo analyze` provides an interactive tree view. Navigate using tmux key sequences:

```bash
# Start analysis
tmux send-keys -t mole 'mo analyze' Enter

# Wait for scan to complete (5-10 minutes for Home directory!)
sleep 300  # 5 minutes for large directories

# Capture current view
tmux capture-pane -t mole -p

# Navigate down to next item
tmux send-keys -t mole Down

# Expand/enter selected directory
tmux send-keys -t mole Enter

# Go back up
tmux send-keys -t mole Up

# Quit the TUI
tmux send-keys -t mole 'q'
```

## Safe Analysis Workflow

### Step 1: Check Version First

```bash
# Always ensure latest version
brew info tw93/tap/mole | head -3
```

### Step 2: Create TTY Environment

```bash
# Start tmux session
tmux new-session -d -s mole -x 120 -y 40
```

### Step 3: Run Analysis (Safe Commands Only)

```bash
# Disk analysis - SAFE, read-only
tmux send-keys -t mole 'mo analyze' Enter

# Wait for scan to complete (be patient!)
sleep 30  # Home directory scanning can take several minutes

# Capture results
tmux capture-pane -t mole -p
```

### Step 4: Preview Cleanup (No Actual Deletion)

```bash
# Preview what would be cleaned - SAFE
tmux send-keys -t mole 'mo clean --dry-run' Enter
sleep 10
tmux capture-pane -t mole -p
```

### Step 5: User Confirmation Required

**NEVER** execute `mo clean` without explicit user confirmation. Always:
1. Show the `--dry-run` preview results to user
2. Wait for user to confirm each category
3. User runs the actual cleanup command themselves

## Safety Principles

### 0. Value Over Vanity (Most Important)

**Your goal is NOT to maximize cleaned space.** Your goal is to identify truly useless items while preserving valuable caches.

**The vanity trap**: Showing "Cleaned 50GB!" feels impressive but:
- User spends 2 hours redownloading npm packages
- Next Xcode build takes 30 minutes instead of 30 seconds
- AI project fails because models need redownload

**Items that should usually be KEPT:**
| Item | Why Keep It |
|------|-------------|
| Xcode DerivedData | Saves 10-30 min per rebuild |
| npm _cacache | Avoids re-downloading all packages |
| ~/.cache/uv | Python package cache |
| Playwright browsers | Avoids 2GB+ redownload |
| iOS DeviceSupport | Needed for device debugging |
| Docker stopped containers | May restart anytime |

**Items that are truly safe to delete:**
| Item | Why Safe |
|------|----------|
| Trash | User already deleted |
| Homebrew old versions | Replaced by newer |
| npm _npx | Temporary executions |

### 1. Never Execute Dangerous Commands Automatically

```bash
# ❌ NEVER do this automatically
mo clean
mo uninstall
mo purge
docker system prune -a --volumes
docker volume prune -f
rm -rf ~/Library/Caches/*

# ✅ ALWAYS use preview/dry-run first
mo clean --dry-run
```

### 2. Patience is Critical

- `mo analyze` on large home directories can take 5-10 minutes
- Do NOT interrupt or skip slow scans
- Report progress to user regularly
- Wait for complete results before making decisions

### 3. User Executes Cleanup

After analysis and confirmation:
```
Present findings to user, then provide command for them to run:

"Based on the analysis, you can reclaim approximately 30GB.
To proceed, please run this command in your terminal:

    mo clean

You will be prompted to confirm each category interactively."
```

## Mole Command Details

### mo analyze

Interactive disk usage explorer. Scans these locations:
- Home directory (`~`)
- App Library (`~/Library/Application Support`)
- Applications (`/Applications`)
- System Library (`/Library`)
- Volumes

**Usage in tmux**:
```bash
tmux send-keys -t mole 'mo analyze' Enter

# Navigate with arrow keys (send via tmux)
tmux send-keys -t mole Down  # Move to next item
tmux send-keys -t mole Enter # Select/expand item
tmux send-keys -t mole 'q'   # Quit
```

### mo clean --dry-run

Preview cleanup without deletion. Shows:
- User essentials (caches, logs, trash)
- macOS system caches
- Browser caches
- Developer tool caches (npm, pip, uv, Homebrew, Docker, etc.)

**Whitelist**: Mole maintains a whitelist of protected patterns. Check with:
```bash
mo clean --whitelist
```

### mo status

System health monitoring (CPU, memory, disk, network). Requires TTY for real-time display.

### mo purge

Cleans old project build artifacts (node_modules, target, venv, etc.) from configured directories.

Check/configure scan paths:
```bash
mo purge --paths
```

## Integration with Claude Code

### Recommended Workflow

1. **Version check**: Ensure Mole is installed and up-to-date
2. **TTY setup**: Create tmux session for interactive commands
3. **Analysis**: Run `mo analyze` or `mo clean --dry-run`
4. **Progress reporting**: Inform user of scan progress
5. **Present findings**: Show structured results to user
6. **User confirmation**: Wait for explicit approval
7. **Provide command**: Give user the command to run themselves

### Example Session

```python
# 1. Check version
$ brew info tw93/tap/mole | head -3
# Output: tw93/tap/mole: stable 1.20.0
# Installed: 1.13.13 -> needs upgrade

# 2. Upgrade if needed
$ brew upgrade tw93/tap/mole

# 3. Create tmux session
$ tmux new-session -d -s mole -x 120 -y 40

# 4. Run dry-run analysis
$ tmux send-keys -t mole 'mo clean --dry-run' Enter

# 5. Wait and capture output
$ sleep 15 && tmux capture-pane -t mole -p

# 6. Present to user:
"""
📊 Cleanup Preview (dry-run - no files deleted)

User essentials:
  - User app cache: 16.67 GB
  - User app logs: 102.3 MB
  - Trash: 642.9 MB

Developer tools:
  - uv cache: 9.96 GB
  - npm cache: (pending)
  - Docker: (pending)

Total recoverable: ~27 GB

To proceed with cleanup, please run in your terminal:
    mo clean
"""
```

## Troubleshooting

### "device not configured" Error

**Cause**: Command run without TTY environment.

**Solution**: Use tmux:
```bash
tmux new-session -d -s mole
tmux send-keys -t mole 'mo status' Enter
```

### Scan Stuck on "pending"

**Cause**: Large directories take time to scan.

**Solution**: Be patient. Home directory with many files can take 5-10 minutes. Monitor progress:
```bash
# Check if still scanning (spinner animation in output)
tmux capture-pane -t mole -p | tail -10
```

### Non-Interactive Mode Auto-Executes

**WARNING**: Some Mole commands may auto-execute in non-TTY environments without confirmation!

**Solution**: ALWAYS use tmux for ANY Mole command, even help:
```bash
# ❌ DANGEROUS - may auto-execute
mo clean --help  # Might run cleanup instead of showing help!

# ✅ SAFE - use mo --help only
mo --help  # The ONLY safe help command
```

### Version Mismatch

**Cause**: Local version outdated.

**Solution**:
```bash
# Check versions
brew info tw93/tap/mole

# Upgrade
brew upgrade tw93/tap/mole
```

## Summary

**Key Points**:
1. Mole is a **CLI tool**, not a GUI application
2. Install via `brew install tw93/tap/mole`
3. **Always check version** before use
4. **Use tmux** for all interactive commands
5. `mo --help` is the **ONLY safe help command**
6. **Never auto-execute** cleanup commands
7. **Be patient** - scans take time
8. **User runs cleanup** - provide command, don't execute
