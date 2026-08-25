# Mole Integration Guide

How to integrate [Mole](https://github.com/tw93/Mole) with the macOS Cleaner skill.

Enter this reference only after the main skill's router determines that the source is genuinely unknown and a broad interactive scan is within scope. A named suspect such as Apple Content Caching should stay on its targeted path.

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

Installation changes the machine. Do not install Mole during a read-only phase. If it is missing, continue with built-in bounded checks or include installation as a separately approved plan item.

```bash
brew install tw93/tap/mole
```

### Version Check and Update

Checking the installed and available versions is read-only. Upgrading is not:

```bash
# Check current vs latest version
brew info tw93/tap/mole | head -5

# Only after the user approves the upgrade as a state change
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
| **Detail Level** | Breakdown within Mole's fixed broad scan roots | Only cleanup-eligible items |
| **Recommended Order** | Use in the read-only evidence phase | Optional planning input after findings are presented |

### When to Use Each

**Use `mo analyze` when:**
- User asks "What's taking up space?" or "Where is my disk space going?"
- Need to understand storage consumption patterns
- The user has approved Mole's fixed broad roots: home, application data, applications, system library, and volumes
- Investigating unexpected disk usage

Do not use `mo analyze` when the user approved only one narrow path. Selecting a branch in the TUI changes what is displayed, not what Mole scanned. Use `analyze_large_files.py --path "<approved-path>"` for an exact approved path, or stop and report that the broader Mole evidence branch was not authorized.

**Use `mo clean --dry-run` when:**
- Already know what's consuming space (after `mo analyze`)
- User has accepted expanding the planning scope to Mole's cleanup categories
- Need a quick preview of what can be cleaned
- Preparing an impact-and-recovery plan; it is not cleanup authorization

### Workflow Recommendation

```
Step 1: After broad scan authorization, mo analyze (understand the problem)
    ↓
Step 2: Present findings to user
    ↓
Step 3: If useful and in scope, mo clean --dry-run (planning evidence only)
    ↓
Step 4: Present exact categories, impact, recovery, and success criteria
    ↓
Step 5: Stop and wait for explicit confirmation
    ↓
Step 6: If the user chooses Mole, the user drives mo clean interactively and selects only the approved categories
```

`mo clean` does not encode category choices in the command line. Therefore the agent must not automate it as execution of an exact approved plan. It is a separate user-driven interactive handoff. Agent-executed cleanup must use commands or exact object IDs that encode the approved targets.

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
# Read-only version inventory; do not upgrade in this phase
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

### Step 4: Optional Planning Preview (No Actual Deletion)

Run this only after the read-only findings are presented and the preview's category scope is acceptable:

```bash
# Preview what would be cleaned - SAFE
tmux send-keys -t mole 'mo clean --dry-run' Enter
sleep 10
tmux capture-pane -t mole -p
```

### Step 5: User Confirmation Required

**NEVER** execute `mo clean` without explicit user confirmation. Always:
1. Show the `--dry-run` preview results to user
2. Explain each category's impact, recovery, and expected physical release
3. Wait for user to confirm the exact categories
4. If the user chooses Mole, hand off the interactive TUI and instruct them to select only those categories; do not automate the selections
5. Verify disk and protected-service postconditions after the user reports that the interactive run finished

## Safety Principles

### 0. Value Over Vanity (Most Important)

**Your goal is NOT to maximize cleaned space.** Your goal is to identify truly useless items while preserving valuable caches.

**The vanity trap**: Showing "Cleaned 50GB!" feels impressive but:
- User spends 2 hours redownloading npm packages
- Next Xcode build takes 30 minutes instead of 30 seconds
- AI project fails because models need redownload

Read `references/cleanup_targets.md` for target-specific rebuild, redownload, ownership, and recovery trade-offs.

### 1. Never Execute Dangerous Commands Automatically

```bash
# ❌ NEVER do this automatically
mo clean
mo uninstall
mo purge
docker system prune -a --volumes
docker volume prune -f
rm -rf ~/Library/Caches/*

# ✅ Planning only, after read-only findings and scope review
mo clean --dry-run
```

### 2. Patience is Critical

- `mo analyze` on large home directories can take 5-10 minutes
- Do NOT interrupt or skip slow scans
- Report progress to user regularly
- Wait for complete results before making decisions

### 3. User-Driven Mole Cleanup Is a Separate Handoff

After analysis and category confirmation, the agent may provide this user-driven option. Do not represent it as agent execution of the exact-command plan, because the command itself does not encode the confirmed choices:
```
Present the named approved categories and their impact, then provide:

"If you want to use Mole's interactive cleaner, run:

    mo clean

Select only these approved categories: <exact category names>.
Do not select any additional category. Tell me when the run finishes so I can verify disk space and protected services."
```

If the user asked the agent to perform the cleanup, choose exact target-addressable commands from the relevant reference instead of `mo clean`.

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

1. **Route first**: Use Mole only when the source is unknown and the user approved Mole's documented fixed broad scan roots
2. **Version inventory**: Check what is installed; do not install or upgrade inside read-only diagnosis
3. **TTY setup**: Create tmux session for interactive commands
4. **Observe**: Run `mo analyze`; report progress
5. **Plan**: Present findings; optionally add `mo clean --dry-run` as scoped planning evidence
6. **Confirm**: List exact choices and wait for explicit approval
7. **Execute and verify**: The user drives `mo clean` and selects only approved categories, or the agent uses exact target-addressable commands outside Mole; then measure disk and protected services independently

### Example Session

```python
# 1. Check version
$ brew info tw93/tap/mole | head -3
# Output: installed and available versions
# If missing/outdated, report it; do not install/upgrade in read-only diagnosis

# 2. Create tmux session
$ tmux new-session -d -s mole -x 120 -y 40

# 3. Run read-only analysis
$ tmux send-keys -t mole 'mo analyze' Enter

# 4. Wait and capture output
$ sleep 15 && tmux capture-pane -t mole -p

# 5. Present evidence and stop before any cleanup preview or mutation:
"""
📊 Mole read-only analysis

Largest approved-scope categories:
  - <category>: <physical size>

No cleanup command has run. Next I will prepare a scoped plan.
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

# Upgrade only after explicit approval
brew upgrade tw93/tap/mole
```

## Summary

**Key Points**:
1. Mole is a **CLI tool**, not a GUI application
2. Installation or upgrade is a separate state change, never part of read-only diagnosis
3. Check the version before use and report drift
4. **Use tmux** for all interactive commands
5. `mo --help` is the **ONLY safe help command**
6. Run `mo analyze` before any optional cleanup preview
7. **Be patient** - scans take time
8. Stop at a scoped confirmation gate before handing off user-driven `mo clean`; never automate its interactive category selections

## Multi-Layer Deep Exploration with Mole

For comprehensive analysis, perform multi-layer exploration, not just top-level scans. This section documents the proven workflow for navigating Mole's TUI.

### Navigation Commands

```bash
# Create session
tmux new-session -d -s mole -x 120 -y 40

# Start analysis
tmux send-keys -t mole 'mo analyze' Enter

# Wait for initial scan
sleep 8 && tmux capture-pane -t mole -p

# Navigation keys (send via tmux)
tmux send-keys -t mole Enter    # Enter/expand selected directory
tmux send-keys -t mole Left     # Go back to parent directory
tmux send-keys -t mole Down     # Move to next item
tmux send-keys -t mole Up       # Move to previous item
tmux send-keys -t mole 'q'      # Quit TUI

# Capture current view
tmux capture-pane -t mole -p
```

### Multi-Layer Exploration Workflow

**Step 1: Top-level overview**
```bash
# Start mo analyze, wait for initial menu
tmux send-keys -t mole 'mo analyze' Enter
sleep 8 && tmux capture-pane -t mole -p

# Example output:
# 1. Home           289.4 GB (58.5%)
# 2. App Library    145.2 GB (29.4%)
# 3. Applications    49.5 GB (10.0%)
# 4. System Library  10.3 GB (2.1%)
```

**Step 2: Enter largest directory (Home)**
```bash
tmux send-keys -t mole Enter
sleep 10 && tmux capture-pane -t mole -p

# Example output:
# 1. Library       144.4 GB (49.9%)
# 2. Workspace      52.0 GB (18.0%)
# 3. .cache         19.3 GB (6.7%)
# 4. Applications   17.0 GB (5.9%)
# ...
```

**Step 3: Drill into specific directories**
```bash
# Go to .cache (3rd item: Down Down Enter)
tmux send-keys -t mole Down Down Enter
sleep 5 && tmux capture-pane -t mole -p

# Example output:
# 1. uv           10.3 GB (55.6%)
# 2. modelscope    5.5 GB (29.5%)
# 3. huggingface   887.8 MB (4.7%)
```

**Step 4: Navigate back and explore another branch**
```bash
# Go back to parent
tmux send-keys -t mole Left
sleep 2

# Navigate to different directory
tmux send-keys -t mole Down Down Down Down Enter  # Go to .npm
sleep 5 && tmux capture-pane -t mole -p
```

**Step 5: Deep dive into Library**
```bash
# Back to Home, then into Library
tmux send-keys -t mole Left
tmux send-keys -t mole Up Up Up Up Up Up Enter  # Go to Library
sleep 10 && tmux capture-pane -t mole -p

# Example output:
# 1. Application Support  37.1 GB
# 2. Containers          35.4 GB
# 3. Developer           17.8 GB  ← Xcode is here
# 4. Caches               8.2 GB
```

### Recommended Exploration Path

For comprehensive analysis, follow this exploration tree:

```
mo analyze
├── Home (Enter)
│   ├── Library (Enter)
│   │   ├── Developer (Enter) → Xcode/DerivedData, iOS DeviceSupport
│   │   ├── Caches (Enter) → Playwright, JetBrains, etc.
│   │   └── Application Support (Enter) → App data
│   ├── .cache (Enter) → uv, modelscope, huggingface
│   ├── .npm (Enter) → _cacache, _npx
│   ├── Downloads (Enter) → Large files to review
│   ├── .Trash (Enter) → Confirm trash contents
│   └── miniconda3/other dev tools (Enter) → Check last used time
├── App Library → Usually overlaps with ~/Library
└── Applications → Installed apps
```

### Time Expectations

| Directory | Scan Time | Notes |
|-----------|-----------|-------|
| Top-level menu | 5-8 seconds | Fast |
| Home directory | 5-10 minutes | Large, be patient |
| ~/Library | 3-5 minutes | Many small files |
| Subdirectories | 2-30 seconds | Varies by size |

### Example Complete Session

```bash
# 1. Create session
tmux new-session -d -s mole -x 120 -y 40

# 2. Start analysis and get overview
tmux send-keys -t mole 'mo analyze' Enter
sleep 8 && tmux capture-pane -t mole -p

# 3. Enter Home
tmux send-keys -t mole Enter
sleep 10 && tmux capture-pane -t mole -p

# 4. Enter .cache to see dev caches
tmux send-keys -t mole Down Down Enter
sleep 5 && tmux capture-pane -t mole -p

# 5. Back to Home, then to .npm
tmux send-keys -t mole Left
sleep 2
tmux send-keys -t mole Down Down Down Down Enter
sleep 5 && tmux capture-pane -t mole -p

# 6. Back to Home, enter Library
tmux send-keys -t mole Left
sleep 2
tmux send-keys -t mole Up Up Up Up Up Up Enter
sleep 10 && tmux capture-pane -t mole -p

# 7. Enter Developer to see Xcode
tmux send-keys -t mole Down Down Down Enter
sleep 5 && tmux capture-pane -t mole -p

# 8. Enter Xcode
tmux send-keys -t mole Enter
sleep 5 && tmux capture-pane -t mole -p

# 9. Enter DerivedData to see projects
tmux send-keys -t mole Enter
sleep 5 && tmux capture-pane -t mole -p

# 10. Cleanup
tmux kill-session -t mole
```

### Key Insights from Exploration

After multi-layer exploration, you will discover:

1. **What projects are using DerivedData** - specific project names
2. **Which caches are actually large** - uv vs npm vs others
3. **Age of files** - Mole shows ">3mo", ">7mo", ">1yr" markers
4. **Specific volumes and their purposes** - Docker project data
5. **Downloads that can be cleaned** - old dmgs, duplicate files
