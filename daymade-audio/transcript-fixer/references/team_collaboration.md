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
uv run scripts/fix_transcription.py --export team_corrections.json --domain embodied_ai

# Export general corrections
uv run scripts/fix_transcription.py --export team_corrections.json
```

**Output**: Creates a standalone JSON file with your corrections.

### Import from Teammate

Two modes: **merge** (combine) or **replace** (overwrite):

```bash
# Merge (recommended) - combines with existing corrections
uv run scripts/fix_transcription.py --import team_corrections.json --merge

# Replace - overwrites existing corrections (dangerous!)
uv run scripts/fix_transcription.py --import team_corrections.json
```

**Merge behavior**:
- Adds new corrections
- Updates existing corrections with imported values
- Preserves corrections not in import file

### Team Workflow Example

**Person A (Domain Expert)**:
```bash
# Build correction dictionary
uv run scripts/fix_transcription.py --add "巨升" "具身" --domain embodied_ai
uv run scripts/fix_transcription.py --add "奇迹创坛" "奇绩创坛" --domain embodied_ai
# ... add 50 more corrections ...

# Export for team
uv run scripts/fix_transcription.py --export ai_corrections.json --domain embodied_ai
# Send ai_corrections.json to team via Slack/email
```

**Person B (Team Member)**:
```bash
# Receive ai_corrections.json
# Import and merge with existing corrections
uv run scripts/fix_transcription.py --import ai_corrections.json --merge

# Now Person B has all 50+ corrections!
```

## Git-Based Collaboration

The local store is a SQLite database (`~/.transcript-fixer/corrections.db`) — **never commit the `.db`** (it is gitignored for a reason; see `best_practices.md` / `file_formats.md`). To version-control corrections in git, commit the **JSON exports**, not the database.

### Initial Setup

**Person A (first user)** — export the dictionary and commit the JSON to a shared repo (a normal repo, **not** `~/.transcript-fixer`):
```bash
uv run scripts/fix_transcription.py --export team_corrections.json

mkdir ~/transcript-corrections && cd ~/transcript-corrections
mv ~/path/to/team_corrections.json .
git init && git add team_corrections.json
git commit -m "Initial correction export"
git remote add origin git@github.com:org/transcript-corrections.git
git push -u origin main
```

### Team Members Clone + Import

```bash
git clone git@github.com:org/transcript-corrections.git ~/transcript-corrections
uv run scripts/fix_transcription.py --import ~/transcript-corrections/team_corrections.json --merge
# --merge combines with each person's existing local corrections;
# --import without --merge overwrites (dangerous).
```

### Ongoing Sync

```bash
# Morning: pull the shared export, import into your local DB
cd ~/transcript-corrections && git pull origin main
uv run scripts/fix_transcription.py --import team_corrections.json --merge

# During the day: add corrections to your local DB
uv run scripts/fix_transcription.py --add "错误" "正确" --domain <domain>

# Evening: re-export and push the updated JSON
uv run scripts/fix_transcription.py --export ~/transcript-corrections/team_corrections.json
cd ~/transcript-corrections && git add team_corrections.json
git commit -m "Add embodied-AI corrections" && git push origin main
```

### Handling Conflicts

Conflicts live in the **exported JSON**, never in a database. The export is a flat list of correction entries, so a merge conflict just means combining both sides' entries — resolve by hand (`git checkout --ours/--theirs team_corrections.json`, then re-add), or simpler: take either version, then have each person re-run `--import … --merge` so both sets of local additions re-converge into the shared export on the next push.

## Selective Domain Sharing

Share only specific domains with different teams:

### Finance Team
```bash
# Finance team exports their domain
uv run scripts/fix_transcription.py --export finance_corrections.json --domain finance

# Share finance_corrections.json with finance team only
```

### AI Team
```bash
# AI team exports their domain
uv run scripts/fix_transcription.py --export ai_corrections.json --domain embodied_ai

# Share ai_corrections.json with AI team only
```

### Individual imports specific domains
```bash
# Alice works on both finance and AI
uv run scripts/fix_transcription.py --import finance_corrections.json --merge
uv run scripts/fix_transcription.py --import ai_corrections.json --merge
```

## Git Branching Strategy

For larger teams, use branches for different domains or workflows:

### Feature Branches
```bash
# In the exports repo, branch for a big batch:
cd ~/transcript-corrections && git checkout -b add-medical-terms
# Add the corrections to your local DB:
uv run scripts/fix_transcription.py --add "医疗术语" "正确术语" --domain medical
# ... add 100 medical corrections ...
# Re-export and commit the updated JSON:
uv run scripts/fix_transcription.py --export team_corrections.json
git add team_corrections.json
git commit -m "Add 100 medical terminology corrections"
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

Automate the pull cycle on the **exports repo** (never `~/.transcript-fixer`). A `git pull` alone does not touch the local DB — you still `--import` the pulled JSON afterward.

### macOS/Linux Cron
```bash
crontab -e
# Pull the shared export twice daily (then import on your own cadence)
0 9,18 * * * cd ~/transcript-corrections && git pull -q origin main
```

### Windows Task Scheduler
```powershell
$action = New-ScheduledTaskAction -Execute "git" -Argument "pull origin main" -WorkingDirectory "$env:USERPROFILE\transcript-corrections"
$trigger = New-ScheduledTaskTrigger -Daily -At 9am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "SyncTranscriptCorrections"
```

## Backup and Recovery

The whole store is one SQLite file (`corrections.db`) plus your JSON exports.

### Backup Strategy
```bash
# Weekly backup of the local store + any exports
tar -czf transcript-corrections-$(date +%Y%m%d).tar.gz \
  ~/.transcript-fixer/corrections.db ~/transcript-corrections/*.json
# Upload to Dropbox/Google Drive/S3
```

### Recovery from Backup
```bash
# Restore corrections.db back to ~/.transcript-fixer/
tar -xzf transcript-corrections-20250127.tar.gz
cp .transcript-fixer/corrections.db ~/.transcript-fixer/corrections.db
```

### Recovery from Git (the exports)
```bash
cd ~/transcript-corrections
git log team_corrections.json                 # view history
git checkout HEAD~3 team_corrections.json      # restore an older export
uv run scripts/fix_transcription.py --import team_corrections.json   # no --merge = replace local with this export
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

For enterprise teams, validate the **exported JSON** in the shared-exports repo on every PR:

### GitHub Actions Example
```yaml
# .github/workflows/validate-corrections.yml
name: Validate Corrections
on:
  pull_request:
    paths: ['*.json']

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate JSON is well-formed
        run: |
          for f in *.json; do python -m json.tool "$f" > /dev/null; done
```

Duplicate detection is handled by the tool itself: `--import … --merge` de-duplicates against existing corrections, so there is no separate `check_duplicates.py`.

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
git checkout --ours team_corrections.json  # Keep yours
# OR
git checkout --theirs team_corrections.json  # Keep theirs

# Then re-import the other version
uv run scripts/fix_transcription.py --import other_version.json --merge
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
