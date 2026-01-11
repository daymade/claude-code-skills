---
name: macos-cleaner
description: Analyze and reclaim macOS disk space through intelligent cleanup recommendations. This skill should be used when users report disk space issues, need to clean up their Mac, or want to understand what's consuming storage. Focus on safe, interactive analysis with user confirmation before any deletions.
---

# macOS Cleaner

## Overview

Intelligently analyze macOS disk usage and provide actionable cleanup recommendations to reclaim storage space. This skill follows a **safety-first philosophy**: analyze thoroughly, present clear findings, and require explicit user confirmation before executing any deletions.

**Target users**: Users with basic technical knowledge who understand file systems but need guidance on what's safe to delete on macOS.

## Core Principles

1. **Analyze First, Act Second**: Never delete files without explicit user confirmation
2. **Transparency**: Explain what each file/directory is and why it's safe (or unsafe) to delete
3. **Interactive Decision Making**: Present findings in human-readable format, let users decide
4. **Conservative Defaults**: When in doubt, don't delete
5. **Backup Suggestions**: Recommend Time Machine backup before major cleanups

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

## Step 1: Quick Diagnosis

Start with a rapid assessment to understand the scope:

```bash
# Check available disk space
df -h /

# Find top 10 largest directories in home folder
du -h -d 1 ~ | sort -hr | head -n 10

# Quick check for common space hogs
du -sh ~/Library/Caches ~/Library/Logs ~/Downloads ~/.Trash 2>/dev/null
```

**Present findings in this format:**

```
📊 Disk Space Analysis
━━━━━━━━━━━━━━━━━━━━━━━━
Total:     500 GB
Used:      450 GB (90%)
Available:  50 GB (10%)

🔍 Top Space Consumers:
1. ~/Library/Caches          45 GB
2. ~/Downloads                38 GB
3. ~/Library/Application Support  25 GB
4. ~/.Trash                   12 GB
5. ~/Library/Logs              8 GB

⚡ Quick Win Opportunities:
- Empty Trash: ~12 GB
- Clear Downloads: ~38 GB (requires user review)
- System Caches: ~45 GB (mostly safe to clear)
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
# Docker cleanup
docker system prune -a --volumes

# Homebrew cleanup
brew cleanup -s

# npm cache
npm cache clean --force

# pip cache
pip cache purge
```

**Safety level**: 🟢 Safe for development caches, 🟡 Caution for Docker volumes

## Step 3: Integration with Mole

**Mole** (https://github.com/tw93/Mole) is a visual macOS cleaner. Recommend it as a complementary tool for users who want GUI-based cleanup.

**When to suggest Mole:**
- User prefers visual interface over command-line
- User wants one-click cleaning for common targets
- Script analysis reveals complex cleanup needs

**How to integrate:**

1. **Check if Mole is installed:**
   ```bash
   if [ -d "/Applications/Mole.app" ]; then
     echo "✅ Mole is installed"
   else
     echo "💡 Consider installing Mole for visual cleanup: https://github.com/tw93/Mole"
   fi
   ```

2. **Coordinate workflow:**
   - Use scripts for detailed analysis and reports
   - Suggest Mole for executing approved cleanups
   - Use scripts for developer-specific cleanup (Docker, npm, etc.)

3. **Reference guide:**
   See `references/mole_integration.md` for detailed usage.

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

## Safety Guidelines

### Always Preserve

Never delete these without explicit user instruction:
- `~/Documents`, `~/Desktop`, `~/Pictures` content
- Active project directories
- Database files (*.db, *.sqlite)
- Configuration files for active apps
- SSH keys, credentials, certificates
- Time Machine backups

### Require Sudo Confirmation

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

### Backup Recommendation

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
- `mole_integration.md` - How to use Mole alongside this skill
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
6. Execute: `rm -rf ~/Library/Caches/*`
7. Report: "Recovered 45 GB"

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
5. Execute confirmed deletions
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
