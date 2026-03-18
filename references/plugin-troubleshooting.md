# Plugin and Skill Troubleshooting

Systematic debugging steps for common plugin and skill installation issues.

## Understanding the Architecture First

**CRITICAL**: Claude Code's plugin system is **GitHub-based**, not local-file-based.

```
GitHub Repository (source of truth)
    ↓ (git clone / git pull)
~/.claude/plugins/marketplaces/{marketplace-name}/
    ↓ (claude plugin install)
~/.claude/plugins/cache/{marketplace-name}/{plugin}/{version}/
    ↓ (Claude Code loads)
Active skill in Claude's context
```

**Key insight**: Local file changes are NOT visible to `claude plugin install` until pushed to GitHub.

## Common Error 1: "Plugin not found in marketplace"

**Error message**:
```
Installing plugin "skill-name@marketplace-name"...
✘ Failed to install plugin: Plugin "skill-name" not found in marketplace "marketplace-name"
```

**Root causes** (in order of likelihood):

### Cause 1.1: Local changes not pushed to GitHub (MOST COMMON)

**Symptoms**:
- `git status` shows modified files or untracked directories
- marketplace.json updated locally but install fails
- All documentation updated but plugin not found

**Diagnosis**:
```bash
# Check if you have uncommitted changes
git status

# Check last commit vs remote
git log origin/main..HEAD

# Verify GitHub has latest marketplace.json
# Open: https://github.com/{owner}/{repo}/blob/main/.claude-plugin/marketplace.json
```

**Solution**:
```bash
# 1. Commit all changes
git add -A
git commit -m "Release vX.Y.Z: Add {skill-name}"

# 2. Push to GitHub
git push

# 3. Clear local marketplace cache
rm -rf ~/.claude/plugins/cache/{marketplace-name}

# 4. Update marketplace from GitHub
claude plugin marketplace update {marketplace-name}

# 5. Retry installation
claude plugin install {skill-name}@{marketplace-name}
```

**Why this happens**: You updated marketplace.json locally, but Claude CLI pulls from GitHub, not your local filesystem.

### Cause 1.2: marketplace.json configuration error

**Symptoms**:
- Git is up-to-date but install still fails
- Other plugins from same marketplace install fine

**Diagnosis**:
```bash
# 1. Check marketplace.json syntax
python3 -m json.tool .claude-plugin/marketplace.json > /dev/null

# 2. Verify plugin entry exists
cat .claude-plugin/marketplace.json | jq '.plugins[] | select(.name == "skill-name")'

# 3. Check spelling matches exactly
# Plugin name in marketplace.json MUST match install command
```

**Common mistakes**:
```json
// ❌ Wrong: name mismatch
{
  "name": "macos_cleaner",  // Underscore
  "skills": ["./macos-cleaner"]  // Dash
}

// ✅ Correct: consistent naming
{
  "name": "macos-cleaner",
  "skills": ["./macos-cleaner"]
}
```

**Solution**: Fix marketplace.json, then commit and push.

### Cause 1.3: Skill directory missing

**Symptoms**:
- marketplace.json has entry
- Git is up-to-date
- Plugin installs but skills don't load

**Diagnosis**:
```bash
# Check if skill directory exists
ls -la {skill-name}/

# Verify SKILL.md exists
ls -la {skill-name}/SKILL.md
```

**Solution**: Ensure skill directory and SKILL.md are committed to git.

## Common Error 2: Marketplace cache is stale

**Symptoms**:
- GitHub has latest changes
- Install finds plugin but gets old version
- Newly added plugins not visible

**Diagnosis**:
```bash
# Check cache timestamp
ls -la ~/.claude/plugins/cache/{marketplace-name}/

# Compare with last git push
git log -1 --format="%ai"
```

**Solution**:
```bash
# Option 1: Update marketplace cache
claude plugin marketplace update {marketplace-name}

# Option 2: Clear cache and re-fetch
rm -rf ~/.claude/plugins/cache/{marketplace-name}
claude plugin marketplace update {marketplace-name}
```

## Common Error 3: JSON syntax error

**Error message**:
```
Error parsing marketplace manifest
```

**Diagnosis**:
```bash
# Validate JSON syntax
python3 -m json.tool .claude-plugin/marketplace.json

# Check for common issues:
# - Missing commas
# - Trailing commas (in arrays/objects)
# - Unescaped quotes in strings
# - Missing closing braces
```

**Solution**: Fix JSON syntax, validate, commit, push.

## Systematic Debugging Process

When facing ANY plugin/skill issue, follow this checklist:

### Step 1: Verify marketplace registration

```bash
# List registered marketplaces
claude plugin marketplace list

# Expected output should include your marketplace
```

If missing, register:
```bash
claude plugin marketplace add https://github.com/{owner}/{repo}
```

### Step 2: Check Git status

```bash
# Are there uncommitted changes?
git status

# Is local ahead of remote?
git log origin/main..HEAD

# Push if needed
git push
```

### Step 3: Verify GitHub has latest

```bash
# Open in browser or use gh CLI
gh browse .claude-plugin/marketplace.json

# Or check with curl
curl https://raw.githubusercontent.com/{owner}/{repo}/main/.claude-plugin/marketplace.json | jq '.plugins[] | .name'
```

### Step 4: Clear and update cache

```bash
# Remove stale cache
rm -rf ~/.claude/plugins/cache/{marketplace-name}

# Re-fetch from GitHub
claude plugin marketplace update {marketplace-name}
```

### Step 5: Validate configuration

```bash
# Check marketplace.json is valid JSON
python3 -m json.tool .claude-plugin/marketplace.json > /dev/null && echo "✅ Valid JSON"

# Check plugin entry exists
cat .claude-plugin/marketplace.json | jq '.plugins[] | select(.name == "skill-name")' || echo "❌ Plugin not found"
```

### Step 6: Inspect installation state

```bash
# Check if plugin is installed
cat ~/.claude/plugins/installed_plugins.json | jq -r '.plugins | keys[]' | grep "skill-name"

# If installed, check details
cat ~/.claude/plugins/installed_plugins.json | jq '.plugins["skill-name@marketplace-name"]'

# Verify files exist
ls ~/.claude/plugins/cache/{marketplace-name}/{skill-name}/{version}/
```

## Debugging Commands Reference

| Purpose | Command |
|---------|---------|
| List marketplaces | `claude plugin marketplace list` |
| Update marketplace | `claude plugin marketplace update {name}` |
| Install plugin | `claude plugin install {plugin}@{marketplace}` |
| Uninstall plugin | `claude plugin uninstall {plugin}@{marketplace}` |
| Update plugin | `claude plugin update {plugin}@{marketplace}` |
| Validate manifest | `claude plugin validate {path}` |
| Check installed plugins | `cat ~/.claude/plugins/installed_plugins.json \| jq '.plugins \| keys'` |
| Inspect plugin details | `cat ~/.claude/plugins/installed_plugins.json \| jq '.plugins["{plugin}@{marketplace}"]'` |
| Clear marketplace cache | `rm -rf ~/.claude/plugins/cache/{marketplace-name}` |
| Verify JSON syntax | `python3 -m json.tool {file.json}` |

## File Locations

```bash
# Marketplace clones (git repositories)
~/.claude/plugins/marketplaces/{marketplace-name}/

# Installed plugin cache
~/.claude/plugins/cache/{marketplace-name}/{plugin-name}/{version}/

# Installation registry
~/.claude/plugins/installed_plugins.json

# Personal skills (not from marketplace)
~/.claude/skills/

# Project-scoped skills (shared with team)
.claude/skills/
```

## Common Pitfalls

### Pitfall 1: Confusing local skills with plugin skills

```bash
# ❌ Wrong: Copying skill to personal directory doesn't make it installable
cp -r my-skill ~/.claude/skills/my-skill  # Works, but not managed by plugin system

# ✅ Correct: Install via marketplace for version management
claude plugin install my-skill@my-marketplace
```

### Pitfall 2: Forgetting to push after updating marketplace.json

```bash
# ❌ Wrong workflow
vim .claude-plugin/marketplace.json  # Add new plugin
git add .claude-plugin/marketplace.json
git commit -m "Add plugin"
# FORGOT TO PUSH!
claude plugin install new-plugin@my-marketplace  # ❌ Fails: not found

# ✅ Correct workflow
vim .claude-plugin/marketplace.json
git add -A
git commit -m "Add new plugin"
git push  # ← CRITICAL STEP
claude plugin marketplace update my-marketplace
claude plugin install new-plugin@my-marketplace  # ✅ Works
```

### Pitfall 3: Expecting instant propagation

```bash
# ❌ Wrong expectation
git push  # Push changes
claude plugin install new-plugin@my-marketplace  # ❌ Fails: cache is stale

# ✅ Correct: Update cache first
git push
claude plugin marketplace update my-marketplace  # Fetch latest from GitHub
claude plugin install new-plugin@my-marketplace  # ✅ Works
```

### Pitfall 4: Inconsistent naming

```json
// marketplace.json
{
  "name": "my_plugin",  // Underscore
  "skills": ["./my-plugin"]  // Dash - will cause confusion
}
```

```bash
# User tries to install
claude plugin install my-plugin@marketplace  # ❌ Not found (name has underscore)
claude plugin install my_plugin@marketplace  # ✅ Works, but confusing
```

**Best practice**: Use consistent kebab-case for both plugin name and skill directory.

## Real-World Example: macos-cleaner Installation Issue

**Scenario**: After creating macos-cleaner skill and updating all documentation, `claude plugin install macos-cleaner@daymade-skills` failed with "Plugin not found".

**Investigation**:
```bash
# 1. Check git status
git status
# Output: 16 modified/untracked files

# 2. Check marketplace cache
ls -la ~/.claude/plugins/cache/daymade-skills/
# Output: Last modified Dec 20 (weeks old!)

# 3. Check GitHub
# marketplace.json on GitHub: version 1.20.0 (old)
# Local marketplace.json: version 1.21.0 (new)
```

**Root cause**: Local changes weren't pushed to GitHub. CLI was pulling from GitHub, not local files.

**Solution**:
```bash
# 1. Commit and push
git add -A
git commit -m "Release v1.21.0: Add macos-cleaner"
git push

# 2. Update marketplace
claude plugin marketplace update daymade-skills

# 3. Install
claude plugin install macos-cleaner@daymade-skills
# ✔ Successfully installed plugin: macos-cleaner@daymade-skills
```

**Verification**:
```bash
cat ~/.claude/plugins/installed_plugins.json | jq '.plugins["macos-cleaner@daymade-skills"]'
# Output: Installation details with correct version

ls ~/.claude/plugins/cache/daymade-skills/macos-cleaner/1.0.0/
# Output: All skill files present
```

**Lesson**: Always remember the GitHub-based architecture. Local changes are invisible until pushed.

## Advanced: Manual Cache Inspection

If automated commands don't reveal the issue, manually inspect:

```bash
# 1. Check marketplace clone
cat ~/.claude/plugins/marketplaces/{marketplace-name}/.claude-plugin/marketplace.json | jq '.metadata.version'

# 2. Check what's in cache
ls -R ~/.claude/plugins/cache/{marketplace-name}/

# 3. Compare with GitHub
curl -s https://raw.githubusercontent.com/{owner}/{repo}/main/.claude-plugin/marketplace.json | jq '.metadata.version'

# 4. Check installation record
cat ~/.claude/plugins/installed_plugins.json | jq '.plugins' | grep -i "{skill-name}"
```

## When All Else Fails

1. **Complete cache reset**:
   ```bash
   rm -rf ~/.claude/plugins/cache/*
   claude plugin marketplace update {marketplace-name}
   ```

2. **Re-register marketplace**:
   ```bash
   # Remove marketplace
   # (No direct command, manual edit ~/.claude/plugins/known_marketplaces.json)

   # Re-add
   claude plugin marketplace add https://github.com/{owner}/{repo}
   ```

3. **Check Claude Code version**:
   ```bash
   claude --version
   # Plugins require Claude Code v2.0.12+
   ```

4. **Enable verbose logging** (if available):
   ```bash
   CLAUDE_DEBUG=1 claude plugin install {plugin}@{marketplace}
   ```

## Getting Help

If you're still stuck:

1. **Check GitHub issues**: https://github.com/anthropics/claude-code/issues
2. **Verify marketplace.json**: Run `claude plugin validate .claude-plugin/marketplace.json`
3. **Compare with working marketplace**: Study anthropic's official marketplace structure
4. **Document your debugging**: Include output from all diagnostic commands above
