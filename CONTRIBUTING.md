# Contributing to Claude Code Skills Marketplace

Thank you for your interest in contributing! This is a **curated marketplace of our own skills**, not a community collection — please read "What We Don't Accept" before opening a pull request.

## What We Accept

### 🐛 Bug Reports

Always welcome:

1. Check if the issue already exists
2. Provide clear description and reproduction steps
3. Include Claude Code version and environment details
4. Add relevant error messages or screenshots

### 🔧 Bug Fixes to Existing Skills

Welcome. To submit a fix:

1. **Open an issue describing the bug first**, so we can confirm it's a real defect rather than intended behavior
2. Fork the repository and make your change on a branch
3. Test thoroughly — if the skill has evals or a registered test suite, run them
4. Submit a pull request referencing the issue

Notes:

- **Keep the fix minimal and scoped to the bug.** Drive-by refactors, reformatting, or unrelated "improvements" will be asked to be split into separate PRs.
- **Don't worry about version numbers, CHANGELOG, or README bookkeeping** — the maintainer handles those in a follow-up commit (repo rules require a `marketplace.json` version bump for every skill-file change, and contributor PRs almost never include it).

## What We Don't Accept

### 🚫 New Skills (or major new features) via PR

We do not accept new-skill submissions, even excellent ones. This marketplace is a curated collection of skills we build and maintain ourselves; merging outside skills would make us responsible for code we didn't write and can't stand behind at our quality bar.

If you've built a skill worth sharing:

- **Publish it as your own marketplace.** The format is open — anyone can add your repo with `claude plugin marketplace add <your-repo>` exactly the way this one is added. Our [marketplace-dev](https://github.com/daymade/claude-code-skills/tree/main/daymade-claude-code/marketplace-dev) skill automates the marketplace.json generation, validation, and packaging if you want it.
- **Think it belongs here specifically?** Open an issue describing what it does and why. If we're convinced, we'll **re-author it ourselves** under our conventions rather than merge your PR.

New-skill PRs are closed with this standing message:

> Thanks for taking the time to build this! This repository is a curated marketplace of our own skills — we only accept bug fixes to existing skills, not new-skill PRs. You're very welcome to publish it as your own marketplace.

## Guidelines That Apply to Bug Fixes

The standards below govern any change you make to an existing skill (they were originally written for skill authors, and a fix must not degrade them).

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

### Bundled Resources

- **scripts/**: Executable code (Python/Bash) for automation
- **references/**: Documentation loaded as needed
- **assets/**: Templates/files used in output

Keep SKILL.md lean (~100-500 lines). Move detailed content to `references/`.

## Code Quality

### Python Scripts

- Use Python 3.10+ compatible syntax
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

Before submitting a fix, verify:

- [ ] The bug reproduces on current `main` without your change, and is gone with it
- [ ] YAML frontmatter of any touched SKILL.md is still valid
- [ ] All referenced files exist
- [ ] Scripts are executable and working
- [ ] No absolute paths or user-specific information
- [ ] Tested in an actual Claude Code session
- [ ] No sensitive information (API keys, passwords, etc.)

## Review Process

Bug-fix PRs are reviewed for:

1. **Correctness**: does it fix the reported bug without regressions?
2. **Scope**: is it minimal — only the fix?
3. **Convention fit**: does it follow the existing style of that skill?
4. **Evidence**: for behavior changes, before/after output or a test.

## Questions?

- Open an issue with the `question` label
- Email: daymadev89@gmail.com
- Check [Claude Code documentation](https://docs.claude.com/en/docs/claude-code)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for helping make Claude Code skills better for everyone! 🎉
