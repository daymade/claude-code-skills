# Mole Integration Guide

How to integrate [Mole](https://github.com/tw93/Mole) with the macOS Cleaner skill.

## About Mole

**Mole** is a visual macOS disk cleanup tool with a native macOS interface. It provides:

- Visual disk usage analysis
- One-click cleanup for common targets
- Safe deletion with preview
- Native macOS design

**Repository**: https://github.com/tw93/Mole

## When to Recommend Mole

Suggest Mole to users in these scenarios:

### 1. User Prefers Visual Interface

```
User: "I prefer clicking buttons rather than running commands"
```

**Response**:
```
I recommend using Mole alongside these scripts:

1. Use the analysis scripts to understand what's using space
2. Install Mole for visual cleanup: https://github.com/tw93/Mole
3. Use Mole's GUI to execute cleanup with visual confirmation

Would you like me to guide you through the analysis first?
```

### 2. Complex Cleanup Needs

```
User: "I have lots of cache files and don't want to run commands for each"
```

**Response**:
```
Mole can help with batch cleanup. It provides visual categories:

- System caches
- Application caches
- Log files
- Trash

Install Mole and you can review and clean multiple categories at once.
```

### 3. Ongoing Maintenance

```
User: "I want to clean my Mac regularly"
```

**Response**:
```
For regular maintenance, I recommend:

1. Keep Mole installed for weekly quick cleanups
2. Use our analysis scripts monthly for deep analysis
3. Use safe_delete.py for specific files/folders

This hybrid approach gives you both convenience and precision.
```

## Installation

### Check if Mole is Installed

```bash
if [ -d "/Applications/Mole.app" ]; then
  echo "✅ Mole is installed"
  open -a Mole
else
  echo "💡 Mole is not installed"
  echo "   Install from: https://github.com/tw93/Mole"
fi
```

### Installation Methods

**Method 1: Download from GitHub Releases**

```bash
# Guide user to:
# 1. Visit https://github.com/tw93/Mole/releases
# 2. Download latest .dmg file
# 3. Open .dmg and drag Mole.app to /Applications
```

**Method 2: Build from Source** (if user is developer)

```bash
git clone https://github.com/tw93/Mole.git
cd Mole
# Follow build instructions in README
```

## Workflow Integration

### Hybrid Workflow: Scripts + Mole

**Best practice**: Use both tools for their strengths.

#### Step 1: Analysis with Scripts

Run comprehensive analysis:

```bash
# System analysis
python3 scripts/analyze_caches.py
python3 scripts/analyze_large_files.py --threshold 100
python3 scripts/find_app_remnants.py

# Developer analysis (if applicable)
python3 scripts/analyze_dev_env.py
```

This gives detailed reports with safety categorization.

#### Step 2: Review Findings

Present findings to user in readable format (see SKILL.md Step 4).

#### Step 3: Execute Cleanup

For different types of cleanup:

**Option A: Use Mole** (for batch operations)
- System caches: Use Mole's "System" category
- Application caches: Use Mole's "Applications" category
- Trash: Use Mole's "Trash" feature

**Option B: Use Scripts** (for precision)
- Large files: Use `safe_delete.py` with specific paths
- Application remnants: Use `safe_delete.py` with confirmed orphans
- Dev environment: Run cleanup commands directly

**Option C: Manual** (for sensitive items)
- Guide user to review in Finder
- User deletes manually

### Example Integrated Session

```markdown
🔍 Analysis Results

I've analyzed your Mac and found:
- System caches: 45 GB (safe to clean)
- Large files: 38 GB (need review)
- App remnants: 8 GB (medium confidence)
- Docker: 25 GB (requires caution)

Recommended cleanup approach:

1. **Use Mole for safe batch cleanup** (45 GB)
   - Open Mole
   - Select "System Caches"
   - Click "Clean"
   - This will clear ~/Library/Caches safely

2. **Use scripts for large file review** (38 GB)
   - I found 20 large files >100MB
   - Let me show you the list
   - We'll use safe_delete.py to delete selected files

3. **Manual review for app remnants** (8 GB)
   - 5 folders for possibly uninstalled apps
   - Please verify these apps are truly gone:
     - Adobe Creative Cloud (3 GB)
     - Old Xcode version (2 GB)
     - ...

4. **Manual Docker cleanup** (25 GB)
   - Requires technical review
   - I'll guide you through checking volumes

Shall we proceed with step 1 using Mole?
```

## Mole Feature Mapping

Map Mole's features to our script capabilities:

| Mole Feature | Script Equivalent | Use Case |
|--------------|-------------------|----------|
| System Caches | `analyze_caches.py --user-only` | Quick cache cleanup |
| Application Caches | `analyze_caches.py` | Per-app cache analysis |
| Large Files | `analyze_large_files.py` | Find space hogs |
| Trash | N/A (Finder) | Empty trash |
| Duplicate Files | Manual `fdupes` | Find duplicates |

**Mole's advantages**:
- Visual representation
- One-click cleanup
- Native macOS integration

**Scripts' advantages**:
- Developer-specific tools (Docker, npm, pip)
- Application remnant detection
- Detailed categorization and safety notes
- Batch operations with confirmation

## Coordinated Cleanup Strategy

### For Non-Technical Users

1. **Install Mole** - Primary cleanup tool
2. **Keep scripts** - For occasional deep analysis
3. **Workflow**:
   - Monthly: Run `analyze_caches.py` to see what's using space
   - Use Mole to execute cleanup
   - Special cases: Use scripts

### For Technical Users / Developers

1. **Keep both** - Mole for quick cleanup, scripts for precision
2. **Workflow**:
   - Weekly: Mole for routine cache cleanup
   - Monthly: Full script analysis for deep cleaning
   - As needed: Script-based cleanup for dev environment

### For Power Users

1. **Scripts only** - Full control and automation
2. **Workflow**:
   - Schedule analysis scripts with cron/launchd
   - Review reports
   - Execute cleanup with `safe_delete.py` or direct commands

## Limitations & Complementary Use

### What Mole Does Well

✅ Visual disk usage analysis
✅ Safe cache cleanup
✅ User-friendly interface
✅ Quick routine maintenance

### What Mole Doesn't Do (Use Scripts For)

❌ Docker cleanup
❌ Homebrew cache (command-line only)
❌ npm/pip cache
❌ Application remnant detection with confidence levels
❌ Large .git directory detection
❌ Development environment analysis

### Recommended Approach

**Use Mole for**: 80% of routine cleanup needs
**Use Scripts for**: 20% of specialized/technical cleanup needs

## Troubleshooting

### Mole Not Opening

```bash
# Check if Mole is installed
ls -l /Applications/Mole.app

# Try opening from command line (see error messages)
open -a Mole

# If not installed
echo "Download from: https://github.com/tw93/Mole/releases"
```

### Mole Shows Different Numbers than Scripts

**Explanation**:
- Mole uses different calculation methods
- Scripts use `du` command (more accurate for directory sizes)
- Both are valid, differences typically <5%

**Not a problem**: Use Mole's numbers for decisions

### Mole Can't Delete Some Caches

**Reason**: Permission issues (some caches are protected)

**Solution**:
1. Use scripts with sudo for system caches
2. Or manually delete in Finder with authentication

## Summary

**Best Practice**: Use both tools

- **Mole**: Visual cleanup, routine maintenance, user-friendly
- **Scripts**: Deep analysis, developer tools, precise control

**Workflow**:
1. Analyze with scripts (comprehensive report)
2. Execute with Mole (safe and visual) OR scripts (precise and technical)
3. Maintain with Mole (weekly/monthly routine)

This combination provides the best user experience for macOS cleanup.
