# Adding a New Skill to Marketplace - Detailed Guide

**CRITICAL**: When adding a skill to this marketplace, you MUST update all of these files. Missing any file will result in incomplete integration.

## Files to Update

```
✅ CHANGELOG.md                        (Add version entry)
✅ README.md                          (7 locations: badges, description, install, skill section, use case, docs link, requirements)
✅ README.zh-CN.md                    (7 locations: same as above, translated) ⚠️ CRITICAL
✅ CLAUDE.md                          (3 locations: overview, marketplace config, available skills)
✅ .claude-plugin/marketplace.json    (CRITICAL: metadata + new plugin entry)
✅ skill-name/                        (The actual skill directory)
✅ skill-name/skill-name.zip          (Packaged skill)
```

## Step-by-Step Process

### 1. Refine the Skill (if needed)
```bash
cd skill-creator
python3 scripts/security_scan.py ../skill-name --verbose
```

### 2. Package the Skill
```bash
cd skill-creator
python3 scripts/package_skill.py ../skill-name
```

### 3. Update CHANGELOG.md

Add new version entry at the top (after [Unreleased]):

```markdown
## [X.Y.0] - YYYY-MM-DD

### Added
- **New Skill**: skill-name - Brief description
  - Feature 1
  - Feature 2
  - Bundled scripts/references/assets

### Changed
- Updated marketplace skills count from N to N+1
- Updated marketplace version from X.(Y-1).0 to X.Y.0
- Updated README.md badges (skills count, version)
- Updated README.md to include skill-name in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include skill-name in skills listing
- Updated CLAUDE.md skills count from N to N+1
- Added skill-name use case section to README.md
- Added skill-name use case section to README.zh-CN.md
- Added dependencies to requirements section (if any, both EN and ZH)
```

### 4. Update README.md

**a. Update badges (top of file):**
```markdown
[![Skills](https://img.shields.io/badge/skills-N-blue.svg)]
[![Version](https://img.shields.io/badge/version-X.Y.0-green.svg)]
```

**b. Update description:**
```markdown
Professional Claude Code skills marketplace featuring N production-ready skills...
```

**c. Add installation command:**
```markdown
# Brief description
claude plugin install skill-name@daymade-skills
```

**d. Add skill section (### N. **skill-name**):**
```markdown
### N. **skill-name** - One-line Title

Brief description paragraph.

**When to use:**
- Use case 1
- Use case 2

**Key features:**
- Feature 1
- Feature 2

**Example usage:**
\`\`\`bash
# Example commands
\`\`\`

**🎬 Live Demo**

*Coming soon* (or add demo GIF)

📚 **Documentation**: See [skill-name/references/](./skill-name/references/)...

**Requirements**: Dependencies (e.g., Python 3.8+, FFmpeg, etc.)
```

**e. Add use case section:**
```markdown
### For [Use Case Category]
Use **skill-name** to [describe primary use case]. Combine with **other-skill** to [describe integration].
```

**f. Add documentation quick link and update requirements section (if needed).**

### 5. Update CLAUDE.md

- Update repository overview skill count
- Update marketplace configuration plugin count
- Add skill to Available Skills list

### 6. Update .claude-plugin/marketplace.json (MOST IMPORTANT)

```json
{
  "name": "skill-name",
  "description": "Clear description with trigger conditions. Use when [scenarios]",
  "source": "./",
  "strict": false,
  "version": "1.0.0",
  "category": "appropriate-category",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "skills": ["./skill-name"]
}
```

**Categories:** `developer-tools`, `document-conversion`, `documentation`, `customization`, `communication`, `utilities`, `assets`, `design`, `productivity`, `security`, `media`

Validate: `python3 -m json.tool .claude-plugin/marketplace.json > /dev/null`

### 7. Update README.zh-CN.md

**CRITICAL**: Chinese documentation must be kept in sync with English version.

Same 7 locations as README.md, translated to professional technical Chinese. Keep code examples in English.

### 8. Commit and Release

```bash
# Commit marketplace update
git add .claude-plugin/marketplace.json skill-name/
git commit -m "Release vX.Y.0: Add skill-name

- Add skill-name vX.Y.Z
- Update marketplace to vX.Y.0"

# Commit documentation
git add README.md README.zh-CN.md CLAUDE.md CHANGELOG.md demos/
git commit -m "docs: Update README for vX.Y.0 with skill-name"

# Push
git push

# Create GitHub release
gh release create vX.Y.0 \
  --title "Release vX.Y.0: Add skill-name - Description" \
  --notes "$(cat <<'EOF'
## New Skill: skill-name

Features:
- Feature 1
- Feature 2

Installation:
```bash
claude plugin install skill-name@daymade-skills
```

Changelog: ...
EOF
)"
```

### 9. Generate Demo (Optional but Recommended)

```bash
./cli-demo-generator/scripts/auto_generate_demo.py \
  -c "command1" \
  -c "command2" \
  -o demos/skill-name/demo-name.gif \
  --title "Skill Demo" \
  --theme "Dracula"
```

## Verification Checklist

Before committing, verify:

- [ ] CHANGELOG.md has new version entry
- [ ] README.md badges updated (skills count + version)
- [ ] README.md has skill section with number
- [ ] README.md has use case section
- [ ] README.md has documentation link
- [ ] README.md requirements updated (if needed)
- [ ] README.zh-CN.md badges updated (skills count + version)
- [ ] README.zh-CN.md has skill section with number
- [ ] README.zh-CN.md has use case section
- [ ] README.zh-CN.md has documentation link
- [ ] README.zh-CN.md requirements updated (if needed)
- [ ] README.zh-CN.md installation command added
- [ ] CLAUDE.md skill count updated in 3 places
- [ ] CLAUDE.md has skill in Available Skills list
- [ ] marketplace.json metadata.version updated
- [ ] marketplace.json metadata.description updated
- [ ] marketplace.json has new plugin entry
- [ ] marketplace.json validates (python3 -m json.tool)
- [ ] skill-name.zip package exists
- [ ] Security scan passed

## Common Mistakes to Avoid

1. **Forgetting marketplace.json** - Without this, `claude plugin install` fails
2. **Forgetting Chinese documentation** - README.zh-CN.md must be updated in sync (6 locations)
3. **Inconsistent version numbers** - CHANGELOG, README badges (both EN and ZH), CLAUDE.md, and marketplace.json must all match
4. **Inconsistent skill counts** - README description (both EN and ZH), badges, CLAUDE.md must all have same count
5. **Missing skill number in README** - Skills must be numbered sequentially in both EN and ZH versions
6. **Invalid JSON syntax** - Always validate marketplace.json after editing
7. **Forgetting to push** - Local changes are invisible until pushed to GitHub

## Quick Reference Commands

```bash
# 1. Refine and validate skill
cd skill-creator && python3 scripts/security_scan.py ../skill-name --verbose

# 2. Package skill
python3 scripts/package_skill.py ../skill-name

# 3. Validate marketplace.json
cd .. && python3 -m json.tool .claude-plugin/marketplace.json > /dev/null && echo "✅ Valid"

# 4. Verify Chinese documentation is in sync
grep "skills-[0-9]*" README.md README.zh-CN.md
grep "version-[0-9.]*" README.md README.zh-CN.md
```
