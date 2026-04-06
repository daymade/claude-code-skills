---
name: marketplace-dev
description: |
  Convert any Claude Code skills repository into an official plugin marketplace.
  Creates .claude-plugin/marketplace.json conforming to the Anthropic spec, validates
  it, tests installation, and creates a PR to the upstream repo.
  Use this skill when the user says: "make this a marketplace", "add plugin support",
  "convert to plugin", "one-click install", "marketplace.json", or wants their skills
  repo installable via `claude plugin install`. Also trigger when the user has a
  skills repo and mentions distribution, installation, or auto-update.
argument-hint: [repo-path]
---

# marketplace-dev

Convert a Claude Code skills repository into an official plugin marketplace so users
can install skills via `claude plugin marketplace add` and get auto-updates.

**Input**: a repo with `skills/` directories containing SKILL.md files.
**Output**: `.claude-plugin/marketplace.json` + validated + installation-tested + PR-ready.

## Phase 1: Analyze the Target Repo

### Step 1: Discover all skills

```bash
# Find every SKILL.md
find <repo-path>/skills -name "SKILL.md" -type f 2>/dev/null
```

For each skill, extract from SKILL.md frontmatter:
- `name` — the skill identifier
- `description` — the ORIGINAL text, do NOT rewrite or translate

### Step 2: Read the repo metadata

- `VERSION` file (if exists) — this becomes `metadata.version`
- `README.md` — understand the project, author info, categories
- `LICENSE` — note the license type
- Git remotes — identify upstream vs fork (`git remote -v`)

### Step 3: Determine categories

Group skills by function. Categories are freeform strings. Good patterns:
- `business-diagnostics`, `content-creation`, `thinking-tools`, `utilities`
- `developer-tools`, `productivity`, `documentation`, `security`

Ask the user to confirm categories if grouping is ambiguous.

## Phase 2: Create marketplace.json

### The official schema (memorize this)

Read `references/marketplace_schema.md` for the complete field reference.
Key rules that are NOT obvious from the docs:

1. **`$schema` field is REJECTED** by `claude plugin validate`. Do not include it.
2. **`metadata` only has 3 valid fields**: `description`, `version`, `pluginRoot`. Nothing else.
   `metadata.homepage` does NOT exist — the validator accepts it silently but it's not in the spec.
3. **`metadata.version`** is the marketplace catalog version, NOT individual plugin versions.
   It should match the repo's VERSION file (e.g., `"2.3.0"`).
4. **Plugin entry `version`** is independent. For first-time marketplace registration, use `"1.0.0"`.
5. **`strict: false`** is required when there's no `plugin.json` in the repo.
   With `strict: false`, the marketplace entry IS the entire plugin definition.
   Having BOTH `strict: false` AND a `plugin.json` with components causes a load failure.
6. **`source: "./"` with `skills: ["./skills/<name>"]`** is the pattern for skills in the same repo.
7. **Reserved marketplace names** that CANNOT be used: `claude-code-marketplace`,
   `claude-code-plugins`, `claude-plugins-official`, `anthropic-marketplace`,
   `anthropic-plugins`, `agent-skills`, `knowledge-work-plugins`, `life-sciences`.
8. **`tags` vs `keywords`**: Both are optional. In the current Claude Code source,
   `keywords` is defined but never consumed in search. `tags` only has a UI effect
   for the value `"community-managed"` (shows a label). Neither affects discovery.
   The Discover tab searches only `name` + `description` + `marketplaceName`.
   Include `keywords` for future-proofing but don't over-invest.

### Generate the marketplace.json

Use this template, filling in from the analysis:

```json
{
  "name": "<marketplace-name>",
  "owner": {
    "name": "<github-org-or-username>"
  },
  "metadata": {
    "description": "<one-line description of the marketplace>",
    "version": "<from-VERSION-file-or-1.0.0>"
  },
  "plugins": [
    {
      "name": "<skill-name>",
      "description": "<EXACT text from SKILL.md frontmatter, do NOT rewrite>",
      "source": "./",
      "strict": false,
      "version": "1.0.0",
      "category": "<category>",
      "keywords": ["<relevant>", "<keywords>"],
      "skills": ["./skills/<skill-name>"]
    }
  ]
}
```

### Naming the marketplace

The `name` field is what users type after `@` in install commands:
`claude plugin install dbs@<marketplace-name>`

Choose a name that is:
- Short and memorable
- kebab-case (lowercase, hyphens only)
- Related to the project identity, not generic

### Description rules

- **Use the ORIGINAL description from each SKILL.md frontmatter**
- Do NOT translate, embellish, or "improve" descriptions
- If the repo's audience is Chinese, keep descriptions in Chinese
- If bilingual, use the first language in the SKILL.md description field
- The `metadata.description` at marketplace level can be a new summary

## Phase 3: Validate

### Step 1: CLI validation

```bash
claude plugin validate .
```

This catches schema errors. Common failures and fixes:
- `Unrecognized key: "$schema"` → remove the `$schema` field
- `Duplicate plugin name` → ensure all names are unique
- `Path contains ".."` → use `./` relative paths only

### Step 2: Installation test

```bash
# Add as local marketplace
claude plugin marketplace add .

# Install a plugin
claude plugin install <plugin-name>@<marketplace-name>

# Verify it appears
claude plugin list | grep <plugin-name>

# Check for updates (should say "already at latest")
claude plugin update <plugin-name>@<marketplace-name>

# Clean up
claude plugin uninstall <plugin-name>@<marketplace-name>
claude plugin marketplace remove <marketplace-name>
```

### Step 3: GitHub installation test (if pushed)

```bash
# Test from GitHub (requires the branch to be pushed)
claude plugin marketplace add <github-user>/<repo>
claude plugin install <plugin-name>@<marketplace-name>

# Verify
claude plugin list | grep <plugin-name>

# Clean up
claude plugin uninstall <plugin-name>@<marketplace-name>
claude plugin marketplace remove <marketplace-name>
```

## Phase 4: Create PR

### Principles
- **Pure incremental**: do NOT modify any existing files (skills, README, etc.)
- **Squash commits**: avoid binary bloat in git history from iterative changes
- Only add: `.claude-plugin/marketplace.json`, optionally `scripts/`, optionally update README

### README update (if appropriate)
Add the marketplace install method above existing install instructions:

```markdown
## Install

![demo](demo.gif)  <!-- only if demo exists -->

**Claude Code plugin marketplace (one-click install, auto-update):**

\`\`\`bash
claude plugin marketplace add <owner>/<repo>
claude plugin install <skill>@<marketplace-name>
\`\`\`
```

### PR description template
Include:
- What was added (marketplace.json with N skills, M categories)
- Install commands users will use after merge
- Design decisions (pure incremental, original descriptions, etc.)
- Validation evidence (`claude plugin validate .` passed)
- Test plan (install commands to verify)

## Anti-Patterns (things that went wrong and how to fix them)

Read `references/anti_patterns.md` for the full list of pitfalls discovered during
real marketplace development. These are NOT theoretical — every one was encountered
and debugged in production.
