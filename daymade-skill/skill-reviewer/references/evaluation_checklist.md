# Skill Evaluation Checklist

Use this checklist as an advisory inspection aid for the intended host. For scored design review, load `references/quality_rubric.json` through the batch workflow. A checklist match is not a quality score or proof of task benefit.

## Delivery review (only when explicitly requested)

- [ ] Read the original user requirement, declared scope and source ownership; independently check the private contract against them.
- [ ] Use the [reviewer Quick Start](../SKILL.md#quick-start) with a delivery contract; inspect source ownership, registration and installed route separately.
- [ ] Treat execution/tests/discovery green with a wrong source as delivery failure.
- [ ] Record missing install or current host loading evidence as unknown; use the fresh-host checks from `skill-governance` for current availability.
- [ ] Without a contract, report quality coverage only, not completed delivery review; third-party reviews require no owned-marketplace contract.

## YAML Frontmatter

- [ ] `name` field present and valid
  - Max 64 characters
  - Lowercase letters, numbers, hyphens only
  - No reserved words (anthropic, claude)
- [ ] `description` field present and valid
  - Non-empty
  - Max 1024 characters
  - Third-person voice
  - Expresses triggering situations in the skill's language; no mandatory English phrase

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

- [ ] SKILL.md carries necessary detail; length alone is not a defect
- [ ] Detailed content in `references/`
- [ ] Large files include grep patterns
- [ ] No duplication between SKILL.md and references

## Bundled Resources

### Scripts (`scripts/`)
- [ ] Executable entry points have the declared invocation; imported helpers need no shebang
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

- [ ] No machine-specific user-home paths
- [ ] Public-release material contains no unintended private identities; public entities and necessary private-environment contracts have context
- [ ] No hardcoded secrets
- [ ] Required paths resolve in the bundle or declared host; do not test preinstalled host paths on the evaluator machine

## Workflow Pattern

- [ ] Clear sequential steps
- [ ] Copy-paste checklist provided
- [ ] Validation/verification steps included

## Error Handling

- [ ] Scripts have specific exception types
- [ ] Error messages are helpful
- [ ] Recovery paths documented
