# Quick Start Guide

Get started with Claude Code Skills Marketplace in less than 2 minutes!

## For Skill Creators

**Want to create your own skills? Start here!**

### Step 1: Install skill-creator

```bash
# Add the marketplace
claude plugin marketplace add https://github.com/daymade/claude-code-skills

# Marketplace name: daymade-skills (from marketplace.json)
# Install skill-creator
claude plugin install skill-creator@daymade-skills
```

### Step 2: Initialize Your First Skill

```bash
# Create a new skill from template
skill-creator/scripts/init_skill.py my-first-skill --path ~/my-skills
```

This generates:
```
~/my-skills/my-first-skill/
├── SKILL.md                  # Main skill file
├── scripts/                  # Executable code
│   └── example_script.py
├── references/               # Documentation
│   └── example_reference.md
└── assets/                   # Templates/resources
    └── example_asset.txt
```

### Step 3: Customize Your Skill

Edit `~/my-skills/my-first-skill/SKILL.md`:

1. **Update frontmatter** - Set name and description
2. **Write "When to Use This Skill"** - Define activation criteria
3. **Document workflows** - Explain how Claude should use your skill
4. **Add resources** - Create scripts, references, or assets as needed

### Step 4: Validate Your Skill

```bash
# Check if your skill meets quality standards
skill-creator/scripts/quick_validate.py ~/my-skills/my-first-skill
```

Fix any errors reported, then validate again.

### Step 5: Package for Distribution

```bash
# Create a distributable .zip file
skill-creator/scripts/package_skill.py ~/my-skills/my-first-skill
```

This creates `my-first-skill.zip` ready to share!

### Step 6: Test Your Skill

```bash
# Copy to Claude Code skills directory
cp -r ~/my-skills/my-first-skill ~/.claude/skills/

# Restart Claude Code
# Your skill is now active!
```

### Next Steps

- 📖 Read [skill-creator/SKILL.md](./skill-creator/SKILL.md) for comprehensive guidance
- 🔍 Study existing skills in this marketplace for examples
- 💡 Check [CONTRIBUTING.md](./CONTRIBUTING.md) to share your skill

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
# Do not use /plugin; all commands are `claude plugin ...`
# Step 2: Install skills you need
claude plugin install github-ops@daymade-skills
claude plugin install markdown-tools@daymade-skills
# ... add more as needed

# Step 3: Restart Claude Code
```

### Available Skills (Starter Set)

This table is a quick starter list. See [README.md](./README.md) for the full catalog (25 skills).

| Skill | Description | When to Use |
|-------|-------------|-------------|
| **skill-creator** ⭐ | Create your own skills | Building custom workflows |
| **github-ops** | GitHub operations | Managing PRs, issues, workflows |
| **markdown-tools** | Document conversion | Converting docs to markdown |
| **mermaid-tools** | Diagram generation | Creating PNG diagrams |
| **statusline-generator** | Statusline customization | Customizing Claude Code UI |
| **teams-channel-post-writer** | Teams communication | Writing professional posts |
| **repomix-unmixer** | Repository extraction | Extracting repomix files |
| **llm-icon-finder** | AI/LLM brand icons | Finding model logos |

### Updating Skills

```bash
# Use the same install command to update
claude plugin install skill-name@daymade-skills
```

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
A: Start with **skill-creator** if you want to create skills. Otherwise, install based on your needs (see the starter table and the full list in README).

**Q: Can I install multiple skills?**
A: Yes! Each skill is independent. Install as many or as few as you need.

**Q: How do I uninstall a skill?**
A: Remove it from `~/.claude/skills/` and restart Claude Code.

**Q: Where can I get help?**
A: Open an issue at [github.com/daymade/claude-code-skills](https://github.com/daymade/claude-code-skills/issues)

---

## What's Next?

- 📖 Read the full [README.md](./README.md) for detailed information
- 🇨🇳 中文用户查看 [README.zh-CN.md](./README.zh-CN.md)
- 💡 Review [CHANGELOG.md](./CHANGELOG.md) for recent updates
- 🤝 Contribute at [CONTRIBUTING.md](./CONTRIBUTING.md)

**Happy skill building! 🚀**
