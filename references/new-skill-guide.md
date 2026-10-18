# Adding a New Skill to Marketplace - Detailed Guide

Packaging creates a disposable `<output-dir>/skill-name.skill` artifact. Keep the
source directory in Git; do not copy the package back into the source tree.

## Step-by-Step Process

### 1. Refine the Skill + PII Read-Through (mandatory gate)
```bash
SKILL_DIR="<repo-root>/<skill-directory>"
cd <repo-root>/daymade-skill/skill-creator
uv run --frozen python -m scripts.security_scan "$SKILL_DIR" --verbose
```

`security_scan` (gitleaks) is a **keyword-based first pass, NOT the gate**. It cannot see real project/person nicknames, CJK names (gitleaks ignores CJK), or verbatim transcript lines — none have a secret signature. **Before publishing you MUST read the whole skill yourself** (SKILL.md + every reference + every example) and judge each concrete noun semantically: generic placeholder, or lifted from a real project/person? See [`../daymade-skill/skill-creator/references/sanitization_checklist.md`](../daymade-skill/skill-creator/references/sanitization_checklist.md). A green scan is **not** a clean bill of health. (2026-06-28: openclaw shipped review with real instance nicknames that scan/gitleaks/grep all missed — caught only by the read-through.)

### 2. Update .claude-plugin/marketplace.json (MOST IMPORTANT)

For a member of an existing suite, append its relative path to that plugin's
`skills` array and bump the suite version. Do not create a second standalone
entry. For a new standalone plugin, use this shape:

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

### 3. Align operating documentation

Before freezing the candidate, follow the repository's
[documentation contract](../CLAUDE.md#quality-standards) for the affected operating
procedures and instruction entries, and its
[catalog authority](../CLAUDE.md#available-skills) for marketplace navigation.

### 4. Update CHANGELOG.md

Add new version entry at the top (after [Unreleased]):

```markdown
## [X.Y.0] - YYYY-MM-DD

### Added
- **New Skill**: skill-name - Brief description
  - Feature 1
  - Feature 2
  - Bundled scripts/references/assets
```

### 5. Update README.md

**a. Update description:**
```markdown
Professional Claude Code skills marketplace for [the supported workflows]...
```

**b. Add the owning plugin's installation command:**

For a suite member, use the existing suite name instead of the member Skill name.
The example below applies to a standalone plugin.
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

📚 **Documentation**: See [skill-name](./skill-name/SKILL.md).

**Requirements**: Dependencies and supported runtime versions declared by the Skill.
```

**d. Add use case section:**
```markdown
### For [Use Case Category]
Use **skill-name** to [describe primary use case]. Combine with **other-skill** to [describe integration].
```

**e. Add documentation quick link and update requirements section (if needed).**

### 6. Update README.zh-CN.md

**CRITICAL**: Chinese documentation must be kept in sync with English version.

Review the same user-facing changes as README.md, translated to professional technical Chinese. Keep code examples in English.

### 7. Package an archive deliverable

Run this step when a `.skill` archive is part of the requested delivery:

```bash
SKILL_DIR="<repo-root>/<skill-directory>"
cd <repo-root>/daymade-skill/skill-creator
uv run --frozen python -m scripts.package_skill "$SKILL_DIR" <output-dir>
```

### 8. Validate, merge, and release

Run the repository checks before committing:

```bash
cd <repo-root>
bash daymade-claude-code/marketplace-dev/scripts/check_marketplace.sh .
python3 daymade-claude-code/marketplace-dev/scripts/check_doc_skill_lists.py
```

Stage the explicit source, manifest, changelog, and affected documentation paths
together. Read `git diff --cached --stat` in a separate call before committing.
Follow [the repository PR workflow](../CLAUDE.md#local-main-is-a-read-only-mirror);
do not commit to local `main`. Complete the authorized deliverable through
[publication and packaging](../daymade-skill/skill-creator/references/publishing-and-packaging.md).

### Local availability when requested

For delivery that includes use on the maintainer machine, follow
[Verify a newly registered Skill](../daymade-skill/skill-governance/references/skill-surface-governance.md#14-verify-a-newly-registered-skill)
after publication. That gate owns source-sync, installed-route readback, fresh-host
checks, and the distinction between catalog discovery and successful task execution.
Source-only or package-only delivery does not require changing local activation.

### 9. Generate Demo (Optional but Recommended)

```bash
./cli-demo-generator/scripts/auto_generate_demo.py \
  -c "command1" \
  -c "command2" \
  -o demos/skill-name/demo-name.gif \
  --title "Skill Demo" \
  --theme "Dracula"
```

## Common Mistakes to Avoid

1. **Forgetting marketplace.json** - Without this, `claude plugin install` fails
2. **Forgetting Chinese documentation** - README.zh-CN.md must describe the same capability and installation route as README.md
3. **Duplicated version/count facts** - versions live in `marketplace.json`; derive counts and catalog positions from its entries instead of persisting badges or sequential numbers
4. **Numbered README skill headings** - use `### **skill-name**`; positions change whenever another Skill is added or removed
5. **Relying on JSON syntax check alone** - `python -m json.tool` only catches malformed JSON. It will NOT catch missing plugin entries, broken source+skills resolution, or orphan SKILL.md files on disk. Use `bash daymade-claude-code/marketplace-dev/scripts/check_marketplace.sh` for manifest, source resolution, and reverse-registration validation.
6. **Leaving orphan SKILL.md directories** - A tracked skill directory with neither a standalone plugin entry nor suite membership in marketplace.json is invisible to `claude plugin install`. The reverse-sync check in `check_marketplace.sh` emits a WARN for each orphan. Treat every WARN as a real signal: register it or delete it.
7. **Using `git add -A` or `git add .`** - When multiple sessions/agents edit the repo in parallel, a blanket stage can piggyback another agent's unstaged changes into your commit. Always stage files by name.
   - If files change outside your edits or already contain unrelated WIP, do not infer ownership or permission from process lists or quiet mtimes. Preserve the shared checkout and move your work to an isolated branch/worktree; ask the owner before integrating overlapping bytes.
8. **Forgetting to push** - Local changes are invisible until pushed to GitHub
