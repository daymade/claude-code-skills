# Team Collaboration Guide

This guide explains how to share correction knowledge across teams using export/import and Git workflows.

## Table of Contents

- [Export/Import Workflow](#exportimport-workflow)
  - [Export Corrections](#export-corrections)
  - [Import from Teammate](#import-from-teammate)
  - [Team Workflow Example](#team-workflow-example)
- [Git-Based Collaboration](#git-based-collaboration)
  - [Initial Setup](#initial-setup)
  - [Team Members Clone](#team-members-clone)
  - [Ongoing Sync](#ongoing-sync)
  - [Handling Conflicts](#handling-conflicts)
- [Selective Domain Sharing](#selective-domain-sharing)
  - [Finance Team](#finance-team)
  - [AI Team](#ai-team)
  - [Individual imports specific domains](#individual-imports-specific-domains)
- [Git Branching Strategy](#git-branching-strategy)
  - [Feature Branches](#feature-branches)
  - [Domain Branches (Alternative)](#domain-branches-alternative)
- [Automated Sync (Advanced)](#automated-sync-advanced)
  - [macOS/Linux Cron](#macoslinux-cron)
  - [Windows Task Scheduler](#windows-task-scheduler)
- [Backup and Recovery](#backup-and-recovery)
  - [Backup Strategy](#backup-strategy)
  - [Recovery from Backup](#recovery-from-backup)
  - [Recovery from Git](#recovery-from-git)
- [Team Best Practices](#team-best-practices)
- [Integration with CI/CD](#integration-with-cicd)
  - [GitHub Actions Example](#github-actions-example)
- [Troubleshooting](#troubleshooting)
  - [Import Failed](#import-failed)
  - [Git Sync Failed](#git-sync-failed)
  - [Merge Conflicts Too Complex](#merge-conflicts-too-complex)
- [Security Considerations](#security-considerations)
- [Further Reading](#further-reading)

## Export/Import Workflow

### Export Corrections

Share your corrections with team members:

```bash
# Export specific domain
python scripts/fix_transcription.py --export team_corrections.json --domain embodied_ai

# Export general corrections
python scripts/fix_transcription.py --export team_corrections.json
```

**Output**: Creates a standalone JSON file with your corrections.

### Import from Teammate

Two modes: **merge** (combine) or **replace** (overwrite):

```bash
# Merge (recommended) - combines with existing corrections
python scripts/fix_transcription.py --import team_corrections.json --merge

# Replace - overwrites existing corrections (dangerous!)
python scripts/fix_transcription.py --import team_corrections.json
```

**Merge behavior**:
- Adds new corrections
- Updates existing corrections with imported values
- Preserves corrections not in import file

### Team Workflow Example

**Person A (Domain Expert)**:
```bash
# Build correction dictionary
python fix_transcription.py --add "巨升" "具身" --domain embodied_ai
python fix_transcription.py --add "奇迹创坛" "奇绩创坛" --domain embodied_ai
# ... add 50 more corrections ...

# Export for team
python fix_transcription.py --export ai_corrections.json --domain embodied_ai
# Send ai_corrections.json to team via Slack/email
```

**Person B (Team Member)**:
```bash
# Receive ai_corrections.json
# Import and merge with existing corrections
python fix_transcription.py --import ai_corrections.json --merge

# Now Person B has all 50+ corrections!
```

## Git-Based Collaboration

For teams using Git, version control the entire correction database.

### Initial Setup

**Person A (First User)**:
```bash
cd ~/.transcript-fixer
git init
git add corrections.json context_rules.json config.json
git add domains/
git commit -m "Initial correction database"

# Push to shared repo
git remote add origin git@github.com:org/transcript-corrections.git
git push -u origin main
```

### Team Members Clone

**Person B, C, D (Team Members)**:
```bash
# Clone shared corrections
git clone git@github.com:org/transcript-corrections.git ~/.transcript-fixer

# Now everyone has the same corrections!
```

### Ongoing Sync

**Daily workflow**:
```bash
# Morning: Pull team updates
cd ~/.transcript-fixer
git pull origin main

# During day: Add corrections
python fix_transcription.py --add "错误" "正确"

# Evening: Push your additions
cd ~/.transcript-fixer
git add corrections.json
git commit -m "Added 5 new embodied AI corrections"
git push origin main
```

### Handling Conflicts

When two people add different corrections to same file:

```bash
cd ~/.transcript-fixer
git pull origin main

# If conflict occurs:
# CONFLICT in corrections.json

# Option 1: Manual merge (recommended)
nano corrections.json  # Edit to combine both changes
git add corrections.json
git commit -m "Merged corrections from teammate"
git push

# Option 2: Keep yours
git checkout --ours corrections.json
git add corrections.json
git commit -m "Kept local corrections"
git push

# Option 3: Keep theirs
git checkout --theirs corrections.json
git add corrections.json
git commit -m "Used teammate's corrections"
git push
```

**Best Practice**: JSON merge conflicts are usually easy - just combine the correction entries from both versions.

## Selective Domain Sharing

Share only specific domains with different teams:

### Finance Team
```bash
# Finance team exports their domain
python fix_transcription.py --export finance_corrections.json --domain finance

# Share finance_corrections.json with finance team only
```

### AI Team
```bash
# AI team exports their domain
python fix_transcription.py --export ai_corrections.json --domain embodied_ai

# Share ai_corrections.json with AI team only
```

### Individual imports specific domains
```bash
# Alice works on both finance and AI
python fix_transcription.py --import finance_corrections.json --merge
python fix_transcription.py --import ai_corrections.json --merge
```

## Git Branching Strategy

For larger teams, use branches for different domains or workflows:

### Feature Branches
```bash
# Create branch for major dictionary additions
git checkout -b add-medical-terms
python fix_transcription.py --add "医疗术语" "正确术语" --domain medical
# ... add 100 medical corrections ...
git add domains/medical.json
git commit -m "Added 100 medical terminology corrections"
git push origin add-medical-terms

# Create PR for review
# After approval, merge to main
```

### Domain Branches (Alternative)
```bash
# Separate branches per domain
git checkout -b domain/embodied-ai
# Work on AI corrections
git push origin domain/embodied-ai

git checkout -b domain/finance
# Work on finance corrections
git push origin domain/finance
```

## Automated Sync (Advanced)

Set up automatic Git sync using cron/Task Scheduler:

### macOS/Linux Cron
```bash
# Edit crontab
crontab -e

# Add daily sync at 9 AM and 6 PM
0 9,18 * * * cd ~/.transcript-fixer && git pull origin main && git push origin main
```

### Windows Task Scheduler
```powershell
# Create scheduled task
$action = New-ScheduledTaskAction -Execute "git" -Argument "pull origin main" -WorkingDirectory "$env:USERPROFILE\.transcript-fixer"
$trigger = New-ScheduledTaskTrigger -Daily -At 9am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "SyncTranscriptCorrections"
```

## Backup and Recovery

### Backup Strategy
```bash
# Weekly backup to cloud
cd ~/.transcript-fixer
tar -czf transcript-corrections-$(date +%Y%m%d).tar.gz corrections.json context_rules.json domains/
# Upload to Dropbox/Google Drive/S3
```

### Recovery from Backup
```bash
# Extract backup
tar -xzf transcript-corrections-20250127.tar.gz -C ~/.transcript-fixer/
```

### Recovery from Git
```bash
# View history
cd ~/.transcript-fixer
git log corrections.json

# Restore from 3 commits ago
git checkout HEAD~3 corrections.json

# Or restore specific version
git checkout abc123def corrections.json
```

## Team Best Practices

1. **Pull Before Push**: Always `git pull` before starting work
2. **Commit Often**: Small, frequent commits better than large infrequent ones
3. **Descriptive Messages**: "Added 5 finance terms" better than "updates"
4. **Review Process**: Use PRs for major dictionary changes (100+ corrections)
5. **Domain Ownership**: Assign domain experts as reviewers
6. **Weekly Sync**: Schedule team sync meetings to review learned suggestions
7. **Backup Policy**: Weekly backups of entire `~/.transcript-fixer/`

## Integration with CI/CD

For enterprise teams, integrate validation into CI:

### GitHub Actions Example
```yaml
# .github/workflows/validate-corrections.yml
name: Validate Corrections

on:
  pull_request:
    paths:
      - 'corrections.json'
      - 'domains/*.json'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Validate JSON
        run: |
          python -m json.tool corrections.json > /dev/null
          for file in domains/*.json; do
            python -m json.tool "$file" > /dev/null
          done

      - name: Check for duplicates
        run: |
          python scripts/check_duplicates.py corrections.json
```

## Troubleshooting

### Import Failed
```bash
# Check JSON validity
python -m json.tool team_corrections.json

# If invalid, fix JSON syntax errors
nano team_corrections.json
```

### Git Sync Failed
```bash
# Check remote connection
git remote -v

# Re-add if needed
git remote set-url origin git@github.com:org/corrections.git

# Verify SSH keys
ssh -T git@github.com
```

### Merge Conflicts Too Complex
```bash
# Nuclear option: Keep one version
git checkout --ours corrections.json  # Keep yours
# OR
git checkout --theirs corrections.json  # Keep theirs

# Then re-import the other version
python fix_transcription.py --import other_version.json --merge
```

## Security Considerations

1. **Private Repos**: Use private Git repositories for company-specific corrections
2. **Access Control**: Limit who can push to main branch
3. **Secret Scanning**: Never commit API keys (already handled by security_scan.py)
4. **Audit Trail**: Git history provides full audit trail of who changed what
5. **Backup Encryption**: Encrypt backups if containing sensitive terminology

## Further Reading

- Git workflows: https://git-scm.com/book/en/v2/Git-Branching-Branching-Workflows
- JSON validation: https://jsonlint.com/
- Team Git practices: https://github.com/git-guides
