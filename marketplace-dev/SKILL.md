---
name: marketplace-dev
description: |
  Converts any Claude Code skills repository into an official plugin marketplace.
  Analyzes existing skills, generates .claude-plugin/marketplace.json conforming to
  the Anthropic spec, validates with `claude plugin validate`, tests real installation,
  and creates a PR to the upstream repo. Encodes hard-won anti-patterns from real
  marketplace development (schema traps, version semantics, description pitfalls).
  Use when the user mentions: marketplace, plugin support, one-click install,
  marketplace.json, plugin distribution, auto-update, or wants a skills repo
  installable via `claude plugin install`. Also trigger when the user has a skills
  repo and asks about packaging, distribution, or making it installable.
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

## Maintaining an existing marketplace

When adding a new plugin to an existing marketplace.json:

1. **Bump `metadata.version`** — this is the marketplace catalog version.
   Follow semver: new plugin = minor bump, breaking change = major bump.
2. **Update `metadata.description`** — append the new skill's summary.
3. **Set new plugin `version` to `"1.0.0"`** — it's new to the marketplace.
4. **Bump existing plugin `version`** when its SKILL.md content changes.
   Claude Code uses version to detect updates — same version = skip update.
5. **Audit `metadata` for invalid fields** — `metadata.homepage` is a common
   mistake (not in spec, silently ignored). Remove if found.

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

## Pre-flight Checklist (MUST pass before proceeding to PR)

Run this checklist after every marketplace.json change. Do not skip items.

### Sync check: skills ↔ marketplace.json

```bash
# List all skill directories on disk
DISK_SKILLS=$(find skills -maxdepth 1 -mindepth 1 -type d -exec basename {} \; | sort)

# List all skills registered in marketplace.json
JSON_SKILLS=$(python3 -c "
import json
with open('.claude-plugin/marketplace.json') as f:
    data = json.load(f)
for p in data['plugins']:
    for s in p.get('skills', []):
        print(s.split('/')[-1])
" | sort)

# Compare — must match
diff <(echo "$DISK_SKILLS") <(echo "$JSON_SKILLS")
```

If diff shows output, skills are out of sync. Fix before proceeding.

### Metadata check

Verify these by reading marketplace.json:

- [ ] `metadata.version` bumped from previous version
- [ ] `metadata.description` mentions all skill categories
- [ ] No `metadata.homepage` (not in spec, silently ignored)
- [ ] No `$schema` field (rejected by validator)

### Per-plugin check

For each plugin entry:

- [ ] `description` matches SKILL.md frontmatter EXACTLY (not rewritten)
- [ ] `version` is `"1.0.0"` for new plugins, bumped for changed plugins
- [ ] `source` is `"./"` and `skills` path starts with `"./"`
- [ ] `strict` is `false` (no plugin.json in repo)
- [ ] `name` is kebab-case, unique across all entries

### Final validation

```bash
claude plugin validate .
```

Must show `✔ Validation passed` before creating PR.

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
