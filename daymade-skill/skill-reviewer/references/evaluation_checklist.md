# Skill Evaluation Checklist

Complete checklist for evaluating Claude Code skills against best practices.

## YAML Frontmatter

- [ ] `name` field present and valid
  - Max 64 characters
  - Lowercase letters, numbers, hyphens only
  - No reserved words (anthropic, claude)
- [ ] `description` field present and valid
  - Non-empty
  - Max 1024 characters
  - Third-person voice
  - Includes trigger conditions ("Use when...")

## Description Quality

### Third-Person Voice Check

```
❌ "Browse YouTube videos..."
❌ "You can use this to..."
❌ "I can help you..."
✅ "Browses YouTube videos..."
✅ "This skill processes..."
```

### Trigger Conditions Check

Description should include:
- What the skill does
- When to use it
- Specific triggers (file types, keywords, scenarios)

```
❌ "Processes PDFs"
✅ "Extracts text and tables from PDF files. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction."
```

## Instruction Quality

- [ ] Imperative/infinitive form used (verb-first)
- [ ] Concise (avoid obvious explanations)
- [ ] Clear workflow steps
- [ ] Checklist pattern for complex tasks

### Imperative Form Check

```
❌ "You should run the script..."
❌ "The user can configure..."
✅ "Run the script..."
✅ "Configure by editing..."
```

## Progressive Disclosure

- [ ] SKILL.md body under 500 lines
- [ ] Detailed content in `references/`
- [ ] Large files include grep patterns
- [ ] No duplication between SKILL.md and references

## Bundled Resources

### Scripts (`scripts/`)
- [ ] Executable with proper shebang
- [ ] Explicit error handling (no bare except)
- [ ] Clear documentation
- [ ] No hardcoded secrets

### References (`references/`)
- [ ] Self-explanatory filenames
- [ ] Loaded as needed, not always
- [ ] No duplication with SKILL.md

### Assets (`assets/`)
- [ ] Used in output, not loaded into context
- [ ] Templates, images, boilerplate

## Privacy and Paths

- [ ] No absolute user paths (`/Users/username/`)
- [ ] No personal/company names
- [ ] No hardcoded secrets
- [ ] Relative paths only

## Workflow Pattern

- [ ] Clear sequential steps
- [ ] Copy-paste checklist provided
- [ ] Validation/verification steps included

## Error Handling

- [ ] Scripts have specific exception types
- [ ] Error messages are helpful
- [ ] Recovery paths documented

## Summary Table

| Category | Status | Notes |
|----------|--------|-------|
| Frontmatter | | |
| Description | | |
| Instructions | | |
| Progressive Disclosure | | |
| Resources | | |
| Privacy | | |
| Workflow | | |
| Error Handling | | |
