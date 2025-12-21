# Contributing to Claude Code Skills Marketplace

Thank you for your interest in contributing! This marketplace aims to provide high-quality, production-ready skills for Claude Code users.

## How to Contribute

### Reporting Issues

1. Check if the issue already exists
2. Provide clear description and reproduction steps
3. Include Claude Code version and environment details
4. Add relevant error messages or screenshots

### Suggesting New Skills

1. Open an issue with the `skill-request` label
2. Describe the skill's purpose and use cases
3. Explain why it would benefit the community
4. Provide examples of when it would activate

### Submitting Skills

To submit a new skill to this marketplace:

#### 1. Skill Quality Requirements

All skills must meet these standards:

**Required Structure:**
- ✅ `SKILL.md` with valid YAML frontmatter (`name` and `description`)
- ✅ Imperative/infinitive writing style (verb-first instructions)
- ✅ Clear "When to Use This Skill" section
- ✅ Proper resource organization (`scripts/`, `references/`, `assets/`)

**Quality Standards:**
- ✅ Comprehensive documentation
- ✅ Working code examples
- ✅ Tested functionality
- ✅ No TODOs or placeholder text
- ✅ Proper cross-referencing of bundled resources

**Best Practices:**
- ✅ Progressive disclosure pattern (metadata → SKILL.md → references)
- ✅ No duplication between SKILL.md and references
- ✅ Scripts have proper shebangs and are executable
- ✅ Clear activation criteria in description

#### 2. Validation

Before submitting, validate your skill:

```bash
# Use skill-creator validation
~/.claude/plugins/marketplaces/anthropics-skills/skill-creator/scripts/quick_validate.py /path/to/your-skill

# Test in Claude Code
# 1. Copy skill to ~/.claude/skills/your-skill
# 2. Restart Claude Code
# 3. Verify skill activates correctly
```

#### 3. Submission Process

1. **Fork this repository**

2. **Add your skill:**
   ```bash
   # Create skill directory
   mkdir your-skill-name

   # Add SKILL.md and resources
   # Follow the structure of existing skills
   ```

3. **Update marketplace.json:**
   ```json
   {
     "skills": [
       // ... existing skills
       "./your-skill-name"
     ]
   }
   ```

4. **Update README.md:**
   - Add skill description to "Included Skills" section
   - Follow the existing format

5. **Test locally:**
   ```bash
   # Add your fork as marketplace
   claude plugin marketplace add https://github.com/your-username/claude-code-skills
   # Marketplace name comes from .claude-plugin/marketplace.json

   # Install and test
   claude plugin install productivity-skills@your-marketplace-name
   ```

6. **Submit Pull Request:**
   - Clear title describing the skill
   - Description explaining the skill's purpose
   - Link to any relevant documentation
   - Screenshots or examples (if applicable)

### Improving Existing Skills

To improve an existing skill:

1. Open an issue describing the improvement
2. Fork the repository
3. Make your changes
4. Test thoroughly
5. Submit a pull request referencing the issue

## Skill Authoring Guidelines

### Writing Style

Use **imperative/infinitive form** throughout:

✅ **Good:**
```markdown
Extract files from a repomix file using the bundled script.
```

❌ **Bad:**
```markdown
You should extract files from a repomix file by using the script.
```

### Documentation Structure

Follow this pattern:

```markdown
---
name: skill-name
description: Clear description with activation triggers. Activates when...
---

# Skill Name

## Overview
[1-2 sentence explanation]

## When to Use This Skill
[Bullet list of activation scenarios]

## Core Workflow
[Step-by-step instructions]

## Resources
[Reference bundled files]
```

### Bundled Resources

- **scripts/**: Executable code (Python/Bash) for automation
- **references/**: Documentation loaded as needed
- **assets/**: Templates/files used in output

Keep SKILL.md lean (~100-500 lines). Move detailed content to `references/`.

## Code Quality

### Python Scripts

- Use Python 3.6+ compatible syntax
- Include proper shebang: `#!/usr/bin/env python3`
- Add docstrings for functions
- Follow PEP 8 style guidelines
- No external dependencies (or document them clearly)

### Bash Scripts

- Include shebang: `#!/bin/bash`
- Use `set -e` for error handling
- Add comments for complex operations
- Make scripts executable: `chmod +x script.sh`

## Testing Checklist

Before submitting, verify:

- [ ] Skill has valid YAML frontmatter
- [ ] Description includes activation triggers
- [ ] All referenced files exist
- [ ] Scripts are executable and working
- [ ] No absolute paths (use relative or `~/.claude/skills/`)
- [ ] Tested in actual Claude Code session
- [ ] Documentation is clear and complete
- [ ] No sensitive information (API keys, passwords, etc.)

## Review Process

Pull requests will be reviewed for:

1. **Functionality**: Does the skill work as described?
2. **Quality**: Does it meet our quality standards?
3. **Documentation**: Is it well-documented?
4. **Originality**: Is it distinct from existing skills?
5. **Value**: Does it benefit the community?

## Questions?

- Open an issue with the `question` label
- Email: daymadev89@gmail.com
- Check [Claude Code documentation](https://docs.claude.com/en/docs/claude-code)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for helping make Claude Code skills better for everyone! 🎉
