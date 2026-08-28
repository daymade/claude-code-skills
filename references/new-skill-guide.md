# Adding a New Skill to Marketplace - Detailed Guide

**CRITICAL**: When adding a skill to this marketplace, you MUST update all of these files. Missing any file will result in incomplete integration.

## Files to Update

```
✅ CHANGELOG.md                        (Add version entry)
✅ README.md                          (description, install, unnumbered skill section, use case, docs link, requirements)
✅ README.zh-CN.md                    (same as above, translated) ⚠️ CRITICAL
✅ CLAUDE.md                          (stable manifest/README authority pointer only)
✅ .claude-plugin/marketplace.json    (CRITICAL: metadata + new plugin entry)
✅ <skill-directory>/                 (The canonical Skill source directory)
```

Packaging creates a disposable `<output-dir>/skill-name.skill` artifact. Keep the
source directory in Git; do not copy the package back into the source tree.

## Step-by-Step Process

### 1. Refine the Skill + PII Read-Through (mandatory gate)
```bash
SKILL_DIR="<repo-root>/<skill-directory>"
cd <repo-root>/daymade-skill/skill-creator
uv run --with PyYAML python -m scripts.security_scan "$SKILL_DIR" --verbose
```

`security_scan` (gitleaks) is a **keyword-based first pass, NOT the gate**. It cannot see real project/person nicknames, CJK names (gitleaks ignores CJK), or verbatim transcript lines — none have a secret signature. **Before publishing you MUST read the whole skill yourself** (SKILL.md + every reference + every example) and judge each concrete noun semantically: generic placeholder, or lifted from a real project/person? See [`../daymade-skill/skill-creator/references/sanitization_checklist.md`](../daymade-skill/skill-creator/references/sanitization_checklist.md). A green scan is **not** a clean bill of health. (2026-06-28: openclaw shipped review with real instance nicknames that scan/gitleaks/grep all missed — caught only by the read-through.)

### 2. Package the Skill
```bash
SKILL_DIR="<repo-root>/<skill-directory>"
cd <repo-root>/daymade-skill/skill-creator
uv run --with PyYAML python -m scripts.package_skill "$SKILL_DIR" <output-dir>
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
- Updated marketplace version from X.(Y-1).0 to X.Y.0
- Updated README.md to include skill-name in skills listing
- Updated README.zh-CN.md to include skill-name in skills listing
- Added skill-name use case section to README.md
- Added skill-name use case section to README.zh-CN.md
- Added dependencies to requirements section (if any, both EN and ZH)
```

### 4. Update README.md

**a. Update description:**
```markdown
Professional Claude Code skills marketplace featuring N production-ready skills...
```

**b. Add installation command:**
```markdown
# Brief description
claude plugin install skill-name@daymade-skills
```

**c. Add an unnumbered skill section:**
```markdown
### **skill-name** - One-line Title

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

**d. Add use case section:**
```markdown
### For [Use Case Category]
Use **skill-name** to [describe primary use case]. Combine with **other-skill** to [describe integration].
```

**e. Add documentation quick link and update requirements section (if needed).**

### 5. Check CLAUDE.md

- Keep only the stable pointer to `.claude-plugin/marketplace.json` and the two READMEs. Do not add a per-skill entry, version, count, or catalog position.

### 6. Update .claude-plugin/marketplace.json (MOST IMPORTANT)

```json
{
  "name": "skill-name",
  "description": "Clear description with trigger conditions. Use when [scenarios]",
  "source": "./skill-name",
  "strict": false,
  "version": "1.0.0",
  "category": "appropriate-category",
  "keywords": ["keyword1", "keyword2", "keyword3"]
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
- [ ] README.md has an unnumbered skill section
- [ ] README.md has use case section
- [ ] README.md has documentation link
- [ ] README.md requirements updated (if needed)
- [ ] README.zh-CN.md has an unnumbered skill section
- [ ] README.zh-CN.md has use case section
- [ ] README.zh-CN.md has documentation link
- [ ] README.zh-CN.md requirements updated (if needed)
- [ ] README.zh-CN.md installation command added
- [ ] CLAUDE.md still contains only the manifest/README authority pointer
- [ ] marketplace.json metadata.version updated
- [ ] marketplace.json metadata.description updated
- [ ] marketplace.json has new plugin entry
- [ ] marketplace.json validates (python3 -m json.tool)
- [ ] Disposable `.skill` package was generated outside the source tree
- [ ] Security scan passed

## Common Mistakes to Avoid

1. **Forgetting marketplace.json** - Without this, `claude plugin install` fails
2. **Forgetting Chinese documentation** - README.zh-CN.md must be updated in sync (6 locations)
3. **Duplicated version/count facts** - versions live in `marketplace.json`; derive counts and catalog positions from its entries instead of persisting badges or sequential numbers
4. **Numbered README skill headings** - use `### **skill-name**`; positions change whenever another Skill is added or removed
5. **Relying on JSON syntax check alone** - `python -m json.tool` only catches malformed JSON. It will NOT catch missing plugin entries, broken source+skills resolution, or orphan SKILL.md files on disk. Use `bash daymade-claude-code/marketplace-dev/scripts/check_marketplace.sh` for the full 4-check validation.
6. **Leaving orphan SKILL.md directories** - A tracked skill directory with no plugin entry in marketplace.json is invisible to `claude plugin install`. The reverse-sync check in `check_marketplace.sh` emits a WARN for each orphan. Treat every WARN as a real signal: register it or delete it.
7. **Using `git add -A` or `git add .`** - When multiple sessions/agents edit the repo in parallel, a blanket stage can piggyback another agent's unstaged changes into your commit. Always stage files by name.
   - If files change outside your edits or already contain unrelated WIP, do not infer ownership or permission from process lists or quiet mtimes. Preserve the shared checkout and move your work to an isolated branch/worktree; ask the owner before integrating overlapping bytes.
8. **Forgetting to push** - Local changes are invisible until pushed to GitHub

## Quick Reference Commands

```bash
# 1. Scan the skill itself for secrets and PII
SKILL_DIR="<repo-root>/<skill-directory>"
cd <repo-root>/daymade-skill/skill-creator
uv run --with PyYAML python -m scripts.security_scan "$SKILL_DIR" --verbose

# 2. Package the skill (auto-validates SKILL.md structure)
uv run --with PyYAML python -m scripts.package_skill "$SKILL_DIR" <output-dir>

# 3. Full marketplace validation — the single source of truth for "is this shippable?"
cd <repo-root>
bash daymade-claude-code/marketplace-dev/scripts/check_marketplace.sh .
# Runs 4 checks in sequence:
#   [1/4] JSON syntax of .claude-plugin/marketplace.json
#   [2/4] claude plugin validate .         (schema-level, skipped if CLI missing)
#   [3/4] source+skills resolution         (every plugin entry points to a real SKILL.md)
#   [4/4] reverse sync (disk → manifest)   (WARN-only: orphan SKILL.md detection)

# 3b. Verify README catalogs and the CLAUDE.md authority pointer
python3 daymade-claude-code/marketplace-dev/scripts/check_doc_skill_lists.py
# Rejects missing/ghost README entries, numbered Skill headings, copied version
# badges, and a model-loaded CLAUDE.md Skill snapshot.

# 4. Stage by name (never -A), commit, push, release
git add .claude-plugin/marketplace.json CHANGELOG.md README.md README.zh-CN.md \
        CLAUDE.md <skill-directory>/
git commit -m "Release vX.Y.0: Add skill-name"
git push
gh release create vX.Y.0 --title "Release vX.Y.0: Add skill-name" --notes "..."
```
