---
name: macos-cleaner
description: Analyze and reclaim macOS disk space through intelligent cleanup recommendations. This skill should be used when users report disk space issues, need to clean up their Mac, or want to understand what's consuming storage. Focus on safe, interactive analysis with user confirmation before any deletions.
---

# macOS Cleaner

## Overview

Intelligently analyze macOS disk usage and provide actionable cleanup recommendations to reclaim storage space. This skill follows a **safety-first philosophy**: analyze thoroughly, present clear findings, and require explicit user confirmation before executing any deletions.

**Target users**: Users with basic technical knowledge who understand file systems but need guidance on what's safe to delete on macOS.

## Core Principles

1. **Safety First, Never Bypass**: NEVER execute dangerous commands (`rm -rf`, `mo clean`, etc.) without explicit user confirmation. No shortcuts, no workarounds.
2. **Precision Deletion Only**: Delete by specifying exact object IDs/names. Never use batch prune commands.
3. **Every Object Listed**: Reports must show every specific image, volume, container — not just "12 GB of unused images".
4. **Value Over Vanity**: Your goal is NOT to maximize cleaned space. Your goal is to identify what is **truly useless** vs **valuable cache**. Clearing 50GB of useful cache just to show a big number is harmful.
5. **Network Environment Awareness**: Many users (especially in China) have slow/unreliable internet. Re-downloading caches can take hours. A cache that saves 30 minutes of download time is worth keeping.
6. **Impact Analysis Required**: Every cleanup recommendation MUST include "what happens if deleted" column. Never just list items without explaining consequences.
7. **Double-Check Before Delete**: Verify each Docker object with independent cross-checks before deletion (see references/docker_analysis.md).
8. **Patience Over Speed**: Disk scans can take 5-10 minutes. NEVER interrupt or skip slow operations. Report progress to user regularly.
9. **User Executes Cleanup**: After analysis, provide the cleanup command for the user to run themselves. Do NOT auto-execute cleanup.
10. **Conservative Defaults**: When in doubt, don't delete. Err on the side of caution.

**ABSOLUTE PROHIBITIONS:**
- ❌ NEVER use `docker image prune`, `docker volume prune`, `docker system prune`, or ANY prune-family command (exception: `docker builder prune` is safe — build cache contains only intermediate layers, never user data)
- ❌ NEVER use `docker container prune` — stopped containers may be restarted at any time
- ❌ NEVER run `rm -rf` on user directories without explicit confirmation
- ❌ NEVER run `mo clean` without `--dry-run` preview first
- ❌ NEVER skip analysis steps to save time
- ❌ NEVER append `--help` to Mole commands (only `mo --help` is safe)
- ❌ NEVER present cleanup reports with only categories — every object must be individually listed
- ❌ NEVER recommend deleting useful caches just to inflate cleanup numbers

## Workflow Decision Tree

```
User reports disk space issues
           ↓
    Quick Diagnosis
           ↓
    ┌──────┴──────┐
    │             │
Immediate    Deep Analysis
 Cleanup      (continue below)
    │             │
    └──────┬──────┘
           ↓
  Present Findings
           ↓
   User Confirms
           ↓
   Execute Cleanup
           ↓
  Verify Results
```

## Step 1: Quick Diagnosis with Mole

**Primary tool**: Use Mole for disk analysis. It provides comprehensive, categorized results.

### 1.1 Pre-flight Checks

```bash
# Check Mole installation and version
which mo && mo --version

# If not installed
brew install tw93/tap/mole

# Check for updates (Mole updates frequently)
brew info tw93/tap/mole | head -5

# Upgrade if outdated
brew upgrade tw93/tap/mole
```

### 1.2 Choose Analysis Method

**IMPORTANT**: Use `mo analyze` as the primary analysis tool, NOT `mo clean --dry-run`.

| Command | Purpose | Use When |
|---------|---------|----------|
| `mo analyze` | Interactive disk usage explorer (TUI tree view) | **PRIMARY**: Understanding what's consuming space |
| `mo clean --dry-run` | Preview cleanup categories | **SECONDARY**: Only after `mo analyze` to see cleanup preview |

**Why prefer `mo analyze`:**
- Dedicated disk analysis tool with interactive tree navigation
- Allows drilling down into specific directories
- Shows actual disk usage breakdown, not just cleanup categories
- More informative for understanding storage consumption

### 1.3 Run Analysis via tmux

**IMPORTANT**: Mole requires TTY. Always use tmux from Claude Code.

**CRITICAL TIMING NOTE**: Home directory scans are SLOW (5-10 minutes or longer for large directories). Inform user upfront and wait patiently.

```bash
# Create tmux session
tmux new-session -d -s mole -x 120 -y 40

# Run disk analysis (PRIMARY tool - interactive TUI)
tmux send-keys -t mole 'mo analyze' Enter

# Wait for scan - BE PATIENT!
# Home directory scanning typically takes 5-10 minutes
# Report progress to user regularly
sleep 60 && tmux capture-pane -t mole -p

# Navigate the TUI with arrow keys
tmux send-keys -t mole Down    # Move to next item
tmux send-keys -t mole Enter   # Expand/select item
tmux send-keys -t mole 'q'     # Quit when done
```

**Alternative: Cleanup preview (use AFTER mo analyze)**
```bash
# Run dry-run preview (SAFE - no deletion)
tmux send-keys -t mole 'mo clean --dry-run' Enter

# Wait for scan (report progress to user every 30 seconds)
# Be patient! Large directories take 5-10 minutes
sleep 30 && tmux capture-pane -t mole -p
```

### 1.4 Progress Reporting

Report scan progress to user regularly:

```
📊 Disk Analysis in Progress...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏱️ Elapsed: 2 minutes

Current status:
✅ Applications: 49.5 GB (complete)
✅ System Library: 10.3 GB (complete)
⏳ Home: scanning... (this may take 5-10 minutes)
⏳ App Library: pending

I'm waiting patiently for the scan to complete.
Will report again in 30 seconds...
```

### 1.5 Present Final Findings

After scan completes, present structured results:

```
📊 Disk Space Analysis (via Mole)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Free space: 27 GB

🧹 Recoverable Space (dry-run preview):

➤ User Essentials
  • User app cache:     16.67 GB
  • User app logs:      102.3 MB
  • Trash:              642.9 MB

➤ Browser Caches
  • Chrome cache:       1.90 GB
  • Safari cache:       4 KB

➤ Developer Tools
  • uv cache:           9.96 GB
  • npm cache:          (detected)
  • Docker cache:       (detected)
  • Homebrew cache:     (detected)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total recoverable: ~30 GB

⚠️ This was a dry-run preview. No files were deleted.
```

## Step 2: Deep Analysis Categories

Scan the following categories systematically. Reference `references/cleanup_targets.md` for detailed explanations.

### Category 1: System & Application Caches

**Locations to analyze:**
- `~/Library/Caches/*` - User application caches
- `/Library/Caches/*` - System-wide caches (requires sudo)
- `~/Library/Logs/*` - Application logs
- `/var/log/*` - System logs (requires sudo)

**Analysis script:**
```bash
scripts/analyze_caches.py --user-only
```

**Safety level**: 🟢 Generally safe to delete (apps regenerate caches)

**Exceptions to preserve:**
- Browser caches while browser is running
- IDE caches (may slow down next startup)
- Package manager caches (Homebrew, pip, npm)

### Category 2: Application Remnants

**Locations to analyze:**
- `~/Library/Application Support/*` - App data
- `~/Library/Preferences/*` - Preference files
- `~/Library/Containers/*` - Sandboxed app data

**Analysis approach:**
1. List installed applications in `/Applications`
2. Cross-reference with `~/Library/Application Support`
3. Identify orphaned folders (app uninstalled but data remains)

**Analysis script:**
```bash
scripts/find_app_remnants.py
```

**Safety level**: 🟡 Caution required
- ✅ Safe: Folders for clearly uninstalled apps
- ⚠️ Check first: Folders for apps you rarely use
- ❌ Keep: Active application data

### Category 3: Large Files & Duplicates

**Analysis script:**
```bash
scripts/analyze_large_files.py --threshold 100MB --path ~
```

**Find duplicates (optional, resource-intensive):**
```bash
# Use fdupes if installed
if command -v fdupes &> /dev/null; then
  fdupes -r ~/Documents ~/Downloads
fi
```

**Present findings:**
```
📦 Large Files (>100MB):
━━━━━━━━━━━━━━━━━━━━━━━━
1. movie.mp4                    4.2 GB  ~/Downloads
2. dataset.csv                  1.8 GB  ~/Documents/data
3. old_backup.zip               1.5 GB  ~/Desktop
...

🔁 Duplicate Files:
- screenshot.png (3 copies)     15 MB each
- document_v1.docx (2 copies)   8 MB each
```

**Safety level**: 🟡 User judgment required

### Category 4: Development Environment Cleanup

**Targets:**
- Docker: images, containers, volumes, build cache
- Homebrew: cache, old versions
- Node.js: `node_modules`, npm cache
- Python: pip cache, `__pycache__`, venv
- Git: `.git` folders in archived projects

**Analysis script:**
```bash
scripts/analyze_dev_env.py
```

**Example findings:**
```
🐳 Docker Resources:
- Unused images:      12 GB
- Stopped containers:  2 GB
- Build cache:         8 GB
- Orphaned volumes:    3 GB
Total potential:      25 GB

📦 Package Managers:
- Homebrew cache:      5 GB
- npm cache:           3 GB
- pip cache:           1 GB
Total potential:       9 GB

🗂️  Old Projects:
- archived-project-2022/.git  500 MB
- old-prototype/.git          300 MB
```

**Cleanup commands (require confirmation):**
```bash
# Homebrew cleanup (safe)
brew cleanup -s

# npm _npx only (safe - temporary packages)
rm -rf ~/.npm/_npx

# pip cache (use with caution)
pip cache purge
```

**Docker cleanup - SPECIAL HANDLING REQUIRED:**

⚠️ **NEVER use these commands:**
```bash
# ❌ DANGEROUS - deletes ALL volumes without confirmation
docker volume prune -f
docker system prune -a --volumes
```

✅ **Correct approach - per-volume confirmation:**
```bash
# 1. List all volumes
docker volume ls

# 2. Identify which projects each volume belongs to
docker volume inspect <volume_name>

# 3. Ask user to confirm EACH project they want to delete
# Example: "Do you want to delete all volumes for 'ragflow' project?"

# 4. Delete specific volumes only after confirmation
docker volume rm ragflow_mysql_data ragflow_redis_data
```

**Safety level**: 🟢 Homebrew/npm cleanup, 🔴 Docker volumes require per-project confirmation

### Step 2A-2C: Docker Deep Analysis

For Docker-heavy systems, follow the detailed per-object analysis and verification protocol (image/container/volume inspection, OrbStack sparse-file handling, and the database-volume red-flag rule) in `references/docker_analysis.md`. Core rule: verify every Docker object with independent cross-checks before deleting, and never use prune-family commands.

## Step 3: Integration with Mole

**Mole** (https://github.com/tw93/Mole) is a **command-line interface (CLI)** tool for comprehensive macOS cleanup. It provides interactive terminal-based analysis and cleanup for caches, logs, developer tools, and more.

**CRITICAL REQUIREMENTS:**

1. **TTY Environment**: Mole requires a TTY for interactive commands. Use `tmux` when running from Claude Code or scripts.
2. **Version Check**: Always verify Mole is up-to-date before use.
3. **Safe Help Command**: Only `mo --help` is safe. Do NOT append `--help` to other commands.

**Installation check and upgrade:**

```bash
# Check if installed and get version
which mo && mo --version

# If not installed
brew install tw93/tap/mole

# Check for updates
brew info tw93/tap/mole | head -5

# Upgrade if needed
brew upgrade tw93/tap/mole
```

**Using Mole with tmux (REQUIRED for Claude Code):**

```bash
# Create tmux session for TTY environment
tmux new-session -d -s mole -x 120 -y 40

# Run analysis (safe, read-only)
tmux send-keys -t mole 'mo analyze' Enter

# Wait for scan (be patient - can take 5-10 minutes for large directories)
sleep 60

# Capture results
tmux capture-pane -t mole -p

# Cleanup when done
tmux kill-session -t mole
```

**Available commands (from `mo --help`):**

| Command | Safety | Description |
|---------|--------|-------------|
| `mo --help` | ✅ Safe | View all commands (ONLY safe help) |
| `mo analyze` | ✅ Safe | Disk usage explorer (read-only) |
| `mo status` | ✅ Safe | System health monitor |
| `mo clean --dry-run` | ✅ Safe | Preview cleanup (no deletion) |
| `mo clean` | ⚠️ DANGEROUS | Actually deletes files |
| `mo purge` | ⚠️ DANGEROUS | Remove project artifacts |
| `mo uninstall` | ⚠️ DANGEROUS | Remove applications |

**Reference guide:**
See `references/mole_integration.md` for detailed tmux workflow and troubleshooting.

## Multi-Layer Deep Exploration with Mole

For comprehensive analysis, perform multi-layer exploration (drilling into Home, Library, .cache, .npm, Downloads, etc.) rather than only top-level scans. The full TUI navigation walkthrough, recommended exploration tree, time expectations, and a complete example session are documented in `references/mole_integration.md`.

## Anti-Patterns: What NOT to Delete

**CRITICAL**: The following items are often suggested for cleanup but should NOT be deleted in most cases. They provide significant value that outweighs the space they consume.

### Items to KEEP (Anti-Patterns)

| Item | Size | Why NOT to Delete | Real Impact of Deletion |
|------|------|-------------------|------------------------|
| **Xcode DerivedData** | 10+ GB | Build cache saves 10-30 min per full rebuild | Next build takes 10-30 minutes longer |
| **npm _cacache** | 5+ GB | Downloaded packages cached locally | `npm install` redownloads everything (30min-2hr in China) |
| **~/.cache/uv** | 10+ GB | Python package cache | Every Python project reinstalls deps from PyPI |
| **Playwright browsers** | 3-4 GB | Browser binaries for automation testing | Redownload 2GB+ each time (30min-1hr) |
| **iOS DeviceSupport** | 2-3 GB | Required for device debugging | Redownload from Apple when connecting device |
| **Docker stopped containers** | <500 MB | May restart anytime with `docker start` | Lose container state, need to recreate |
| **~/.cache/huggingface** | varies | AI model cache | Redownload large models (hours) |
| **~/.cache/modelscope** | varies | AI model cache (China) | Same as above |
| **JetBrains caches** | 1+ GB | IDE indexing and caches | IDE takes 5-10 min to re-index |

### Why This Matters

**The vanity trap**: Showing "Cleaned 50GB!" feels good but:
- User spends next 2 hours redownloading npm packages
- Next Xcode build takes 30 minutes instead of 30 seconds
- AI project fails because models need redownload

**The right mindset**: "I found 50GB of caches. Here's why most of them are actually valuable and should be kept..."

### What IS Actually Safe to Delete

| Item | Why Safe | Impact |
|------|----------|--------|
| **Trash** | User already deleted these files | None - user's decision |
| **Homebrew old versions** | Replaced by newer versions | Rare: can't rollback to old version |
| **npm _npx** | Temporary npx executions | Minor: npx re-downloads on next use |
| **Orphaned app remnants** | App already uninstalled | None - app doesn't exist |
| **Specific unused Docker volumes** | Projects confirmed abandoned | None - if truly abandoned |

## Report Format Requirements

Every cleanup report MUST follow this format with impact analysis:

```markdown
## Disk Analysis Report

### Classification Legend
| Symbol | Meaning |
|--------|---------|
| 🟢 | **Absolutely Safe** - No negative impact, truly unused |
| 🟡 | **Trade-off Required** - Useful cache, deletion has cost |
| 🔴 | **Do Not Delete** - Contains valuable data or actively used |

### Findings

| Item | Size | Classification | What It Is | Impact If Deleted |
|------|------|----------------|------------|-------------------|
| Trash | 643 MB | 🟢 | Files you deleted | None |
| npm _npx | 2.1 GB | 🟢 | Temp npx packages | Minor redownload |
| npm _cacache | 5 GB | 🟡 | Package cache | 30min-2hr redownload |
| DerivedData | 10 GB | 🟡 | Xcode build cache | 10-30min rebuild |
| Docker volumes | 11 GB | 🔴 | Project databases | **DATA LOSS** |

### Recommendation
Only items marked 🟢 are recommended for cleanup.
Items marked 🟡 require your judgment based on usage patterns.
Items marked 🔴 require explicit confirmation per-item.
```

### Docker Report: Required Object-Level Detail

Docker reports must list every individual object (each image, container, and volume), not just categories. See the object-level table templates in `references/report_templates.md`.

## High-Quality Report Template

After multi-layer exploration, present findings using the detailed fill-in-the-blank template in `references/report_templates.md`.

### Report Quality Checklist

Before presenting the report, verify:

- [ ] Every item has "Impact If Deleted" explanation
- [ ] 🟢 items are truly safe (Trash, _npx, old versions)
- [ ] 🟡 items require user decision (age info, usage patterns)
- [ ] 🔴 items explain WHY they should be kept
- [ ] Docker volumes listed by project, not blanket prune
- [ ] Network environment considered (China = slow redownload)
- [ ] No recommendations to delete useful caches just to inflate numbers
- [ ] Clear action items with exact commands

## Step 4: Present Recommendations

Format findings into actionable recommendations with risk levels:

```markdown
# macOS Cleanup Recommendations

## Summary
Total space recoverable: ~XX GB
Current usage: XX%

## Recommended Actions

### 🟢 Safe to Execute (Low Risk)
These are safe to delete and will be regenerated as needed:

1. **Empty Trash** (~12 GB)
   - Location: ~/.Trash
   - Command: `rm -rf ~/.Trash/*`

2. **Clear System Caches** (~45 GB)
   - Location: ~/Library/Caches
   - Command: `rm -rf ~/Library/Caches/*`
   - Note: Apps may be slightly slower on next launch

3. **Remove Homebrew Cache** (~5 GB)
   - Command: `brew cleanup -s`

### 🟡 Review Recommended (Medium Risk)
Review these items before deletion:

1. **Large Downloads** (~38 GB)
   - Location: ~/Downloads
   - Action: Manually review and delete unneeded files
   - Files: [list top 10 largest files]

2. **Application Remnants** (~8 GB)
   - Apps: [list detected uninstalled apps]
   - Locations: [list paths]
   - Action: Confirm apps are truly uninstalled before deleting data

### 🔴 Keep Unless Certain (High Risk)
Only delete if you know what you're doing:

1. **Docker Volumes** (~3 GB)
   - May contain important data
   - Review with: `docker volume ls`

2. **Time Machine Local Snapshots** (~XX GB)
   - Automatic backups, will be deleted when space needed
   - Command to check: `tmutil listlocalsnapshots /`
```

## Step 5: Execute with Confirmation

**CRITICAL**: Never execute deletions without explicit user confirmation.

**Interactive confirmation flow:**

```python
# Example from scripts/safe_delete.py
def confirm_delete(path: str, size: str, description: str) -> bool:
    """
    Ask user to confirm deletion.

    Args:
        path: File/directory path
        size: Human-readable size
        description: What this file/directory is

    Returns:
        True if user confirms, False otherwise
    """
    print(f"\n🗑️  Confirm Deletion")
    print(f"━━━━━━━━━━━━━━━━━━")
    print(f"Path:        {path}")
    print(f"Size:        {size}")
    print(f"Description: {description}")

    response = input("\nDelete this item? [y/N]: ").strip().lower()
    return response == 'y'
```

**For batch operations:**

```python
def batch_confirm(items: list) -> list:
    """
    Show all items, ask for batch confirmation.

    Returns list of items user approved.
    """
    print("\n📋 Items to Delete:")
    print("━━━━━━━━━━━━━━━━━━")
    for i, item in enumerate(items, 1):
        print(f"{i}. {item['path']} ({item['size']})")

    print("\nOptions:")
    print("  'all'    - Delete all items")
    print("  '1,3,5'  - Delete specific items by number")
    print("  'none'   - Cancel")

    response = input("\nYour choice: ").strip().lower()

    if response == 'none':
        return []
    elif response == 'all':
        return items
    else:
        # Parse numbers
        indices = [int(x.strip()) - 1 for x in response.split(',')]
        return [items[i] for i in indices if 0 <= i < len(items)]
```

## Step 6: Verify Results

After cleanup, verify the results and report back:

```bash
# Compare before/after
df -h /

# Calculate space recovered
# (handled by scripts/cleanup_report.py)
```

**Report format:**

```
✅ Cleanup Complete!

Before: 450 GB used (90%)
After:  385 GB used (77%)
━━━━━━━━━━━━━━━━━━━━━━━━
Recovered: 65 GB

Breakdown:
- System caches:        45 GB
- Downloads:            12 GB
- Homebrew cache:        5 GB
- Application remnants:  3 GB

⚠️ Notes:
- Some applications may take longer to launch on first run
- Deleted items cannot be recovered unless you have Time Machine backup
- Consider running this cleanup monthly

💡 Maintenance Tips:
- Set up automatic Homebrew cleanup: `brew cleanup` weekly
- Review Downloads folder monthly
- Enable "Empty Trash Automatically" in Finder preferences
```

## Bonus: Dockerfile Optimization Discoveries

When image analysis reveals oversized images, suggest multi-stage build optimization. See the before/after example and key techniques in `references/docker_analysis.md`.

## ⚠️ Safety Guidelines

### Always Preserve

Never delete these without explicit user instruction:
- `~/Documents`, `~/Desktop`, `~/Pictures` content
- Active project directories
- Database files (*.db, *.sqlite)
- Configuration files for active apps
- SSH keys, credentials, certificates
- Time Machine backups

### ⚠️ Require Sudo Confirmation

These operations require elevated privileges. Ask user to run commands manually:
- Clearing `/Library/Caches` (system-wide)
- Clearing `/var/log` (system logs)
- Clearing `/private/var/folders` (system temp)

Example prompt:
```
⚠️ This operation requires administrator privileges.

Please run this command manually:
  sudo rm -rf /Library/Caches/*

⚠️ You'll be asked for your password.
```

### 💡 Backup Recommendation

Before executing any cleanup >10GB, recommend:

```
💡 Safety Tip:
Before cleaning XX GB, consider creating a Time Machine backup.

Quick backup check:
  tmutil latestbackup

If no recent backup, run:
  tmutil startbackup
```

## Troubleshooting

### "Operation not permitted" errors

macOS may block deletion of certain system files due to SIP (System Integrity Protection).

**Solution**: Don't force it. These protections exist for security.

### App crashes after cache deletion

Rare but possible. **Solution**: Restart the app, it will regenerate necessary caches.

### Docker cleanup removes important data

**Prevention**: Always list Docker volumes before cleanup:
```bash
docker volume ls
docker volume inspect <volume_name>
```

## Resources

### scripts/

- `analyze_caches.py` - Scan and categorize cache directories
- `find_app_remnants.py` - Detect orphaned application data
- `analyze_large_files.py` - Find large files with smart filtering
- `analyze_dev_env.py` - Scan development environment resources
- `safe_delete.py` - Interactive deletion with confirmation
- `cleanup_report.py` - Generate before/after reports

### references/

- `cleanup_targets.md` - Detailed explanations of each cleanup target
- `mole_integration.md` - How to use Mole, plus the multi-layer TUI exploration walkthrough
- `docker_analysis.md` - Docker deep-analysis workflow (Step 2A-2C) and Dockerfile optimization
- `report_templates.md` - Detailed report templates (object-level Docker tables, full report layout)
- `safety_rules.md` - Comprehensive list of what to never delete

## Usage Examples

### Example 1: Quick Cache Cleanup

User request: "My Mac is running out of space, can you help?"

Workflow:
1. Run quick diagnosis
2. Identify system caches as quick win
3. Present findings: "45 GB in ~/Library/Caches"
4. Explain: "These are safe to delete, apps will regenerate them"
5. Ask confirmation
6. Provide the command for the user to run themselves: `rm -rf ~/Library/Caches/*` (per Core Principle 9, do not auto-execute)
7. After the user runs it, verify with `df -h /` and report: "Recovered 45 GB"

### Example 2: Development Environment Cleanup

User request: "I'm a developer and my disk is full"

Workflow:
1. Run `scripts/analyze_dev_env.py`
2. Present Docker + npm + Homebrew findings
3. Explain each category
4. Provide cleanup commands with explanations
5. Let user execute (don't auto-execute Docker cleanup)
6. Verify results

### Example 3: Finding Large Files

User request: "What's taking up so much space?"

Workflow:
1. Run `scripts/analyze_large_files.py --threshold 100MB`
2. Present top 20 large files with context
3. Categorize: videos, datasets, archives, disk images
4. Let user decide what to delete
5. Provide deletion commands for the user to run (or use scripts/safe_delete.py for interactive per-item confirmation)
6. Suggest archiving to external drive

## Best Practices

1. **Start Conservative**: Begin with obviously safe targets (caches, trash)
2. **Explain Everything**: Users should understand what they're deleting
3. **Show Examples**: List 3-5 example files from each category
4. **Respect User Pace**: Don't rush through confirmations
5. **Document Results**: Always show before/after space usage
6. **Educate**: Include maintenance tips in final report
7. **Integrate Tools**: Suggest Mole for users who prefer GUI

## When NOT to Use This Skill

- User wants automatic/silent cleanup (against safety-first principle)
- User needs Windows/Linux cleanup (macOS-specific skill)
- User has <10% disk usage (no cleanup needed)
- User wants to clean system files requiring SIP disable (security risk)

In these cases, explain limitations and suggest alternatives.
