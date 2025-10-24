# Pull Request

## Description

Brief description of what this PR does.

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] New skill
- [ ] Enhancement to existing skill
- [ ] Infrastructure/tooling improvement

## Related Issues

Fixes #(issue number)
Relates to #(issue number)

## Changes Made

Detailed list of changes:

- Change 1
- Change 2
- Change 3

## Affected Skills

Which skills are affected by this PR?

- [ ] skill-creator
- [ ] github-ops
- [ ] markdown-tools
- [ ] mermaid-tools
- [ ] statusline-generator
- [ ] teams-channel-post-writer
- [ ] repomix-unmixer
- [ ] llm-icon-finder
- [ ] Marketplace infrastructure
- [ ] Documentation only

## Testing Done

How has this been tested?

- [ ] Tested on macOS
- [ ] Tested on Linux
- [ ] Tested on Windows
- [ ] Manual testing performed
- [ ] Automated tests added/updated
- [ ] Validated with skill-creator validation script

**Test description:**

1. Test step 1
2. Test step 2
3. Test step 3

## Quality Checklist

### For New Skills

- [ ] SKILL.md has valid YAML frontmatter (name, description)
- [ ] Description includes clear activation triggers
- [ ] Uses imperative/infinitive writing style
- [ ] All referenced files exist
- [ ] Scripts are executable (chmod +x)
- [ ] No absolute paths or user-specific information
- [ ] Tested in actual Claude Code session
- [ ] Passed validation: `skill-creator/scripts/quick_validate.py`
- [ ] Successfully packages: `skill-creator/scripts/package_skill.py`

### For All PRs

- [ ] Code follows the style guidelines of this project
- [ ] Self-review of code performed
- [ ] Comments added for complex code
- [ ] Documentation updated (if applicable)
- [ ] No new warnings generated
- [ ] Changes don't break existing functionality
- [ ] Commit messages are clear and descriptive

### For Documentation Changes

- [ ] Checked for typos and grammar
- [ ] Links are working
- [ ] Code examples are tested
- [ ] Screenshots updated (if applicable)
- [ ] Chinese translation updated (if applicable)

## Screenshots (if applicable)

Add screenshots to help explain your changes.

## Additional Notes

Any additional information reviewers should know.

## Checklist for Reviewer

- [ ] Code quality is acceptable
- [ ] Tests are adequate
- [ ] Documentation is clear
- [ ] No sensitive information exposed
- [ ] Follows skill quality standards
