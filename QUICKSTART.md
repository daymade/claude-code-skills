# Quick Start Guide

Install Skills or create a Skill in an existing source repository.

## For Skill Creators

**Want to create your own skills? Start here!**

### Step 1: Install skill-creator

**In Claude Code (in-app):**
```text
/plugin marketplace add daymade/claude-code-skills
```

Then:
1. Select **Browse and install plugins**
2. Select **daymade/claude-code-skills**
3. Select **daymade-skill**
4. Select **Install now**

**From your terminal (CLI):**
```bash
# Add the marketplace
claude plugin marketplace add https://github.com/daymade/claude-code-skills

# Marketplace name: daymade-skills (from marketplace.json)
# Install the daymade-skill suite (bundles skill-creator)
claude plugin install daymade-skill@daymade-skills
```

### Step 2: Select the source and initialize

Load [skill-creator](./daymade-skill/skill-creator/SKILL.md#critical-edit-skills-at-source-location) and complete its source preflight first. This example creates a project Skill in an existing Git project. For a reusable global Skill, select your own marketplace source repository and follow the creator workflow.

Replace these variables with the absolute paths of the loaded skill-creator directory and an existing Git project:

```bash
TASK_CREATOR=/absolute/path/to/loaded/skill-creator
TASK_PROJECT=/absolute/path/to/existing/git-project
uv run --project "$TASK_CREATOR" --frozen python "$TASK_CREATOR/scripts/init_skill.py" my-first-skill \
  --path "$TASK_PROJECT/.claude/skills" --repo "$TASK_PROJECT" --scope project
```

### Step 3: Edit and validate

Edit `$TASK_PROJECT/.claude/skills/my-first-skill/SKILL.md` to define triggers, actions and failure criteria. Add needed resources and remove unused template examples.

```bash
uv run --project "$TASK_CREATOR" --frozen python "$TASK_CREATOR/scripts/quick_validate.py" \
  "$TASK_PROJECT/.claude/skills/my-first-skill"
```

Continue through [skill-creator's delivery workflow](./daymade-skill/skill-creator/SKILL.md#skill-creation-process-step-by-step) for the required security, regression and packaging checks. Structural validation alone does not establish delivery.

### Step 4: Verify host consumption

Follow the installation lifecycle and fresh-host checks in [skill-governance](./daymade-skill/skill-governance/references/skill-surface-governance.md). Read the actual consumed file and verify task behavior. Avoid creating another maintained copy with `cp -r`; restarting or seeing a directory does not prove loading.

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the contribution policy.

---

## For Skill Users

**Just want to use existing skills? Here's how!**

### Option 1: Automated Installation (Fastest)

**macOS/Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.sh | bash
```

**Windows (PowerShell):**
```powershell
iwr -useb https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.ps1 | iex
```

Follow the interactive prompts to select skills.

### Option 2: Manual Installation

```bash
# Step 1: Add the marketplace
claude plugin marketplace add https://github.com/daymade/claude-code-skills

# Marketplace name: daymade-skills (from marketplace.json)
# Use @daymade-skills in install commands (e.g., skill-name@daymade-skills)
# In Claude Code use `/plugin ...`; in your terminal use `claude plugin ...`
# Step 2: Install skills you need
claude plugin install github-ops@daymade-skills
claude plugin install daymade-docs@daymade-skills
# ... add more as needed

# Step 3: Restart Claude Code
```

### Discovery, updates and removal

See [README.md](./README.md) for the catalog. Follow [skill-governance](./daymade-skill/skill-governance/references/skill-surface-governance.md) for installation source, suite boundaries, updates and removal.

---

## 🇨🇳 For Chinese Users

### Recommended: Use CC-Switch

If you're in China, install [CC-Switch](https://github.com/farion1231/cc-switch) first to manage API providers:

1. Download from [Releases](https://github.com/farion1231/cc-switch/releases)
2. Install and configure your preferred provider (DeepSeek, Qwen, GLM)
3. Test response times to find the fastest endpoint
4. Then install Claude Code skills normally

**Why CC-Switch?**
- ✅ Supports Chinese AI providers
- ✅ Automatic fastest endpoint selection
- ✅ Easy configuration switching
- ✅ Works on Windows, macOS, Linux

---

## Common Questions

**Q: Which skills should I install first?**
A: Start with **skill-creator** if you want to create skills. Otherwise, install based on your needs (see the catalog in README).

**Q: Can I install multiple skills?**
A: Follow the plugin boundaries in the [marketplace manifest](./.claude-plugin/marketplace.json).

**Q: How do I uninstall a skill?**
A: Follow the removal workflow in [skill-governance](./daymade-skill/skill-governance/references/skill-surface-governance.md).

**Q: Where can I get help?**
A: Open an issue at [github.com/daymade/claude-code-skills](https://github.com/daymade/claude-code-skills/issues)

---

## What's Next?

- 📖 Read the full [README.md](./README.md) for detailed information
- 🇨🇳 中文用户查看 [README.zh-CN.md](./README.zh-CN.md)
- 💡 Review [CHANGELOG.md](./CHANGELOG.md) for recent updates
- 🤝 Contribute at [CONTRIBUTING.md](./CONTRIBUTING.md)

**Happy skill building! 🚀**
