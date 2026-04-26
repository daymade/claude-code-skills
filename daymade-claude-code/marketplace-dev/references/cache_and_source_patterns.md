# Cache and Source Patterns

This reference captures marketplace lessons from real Claude Code marketplace work:
full-repo cache pollution, suite namespace design, symlink experiments, and version
semantics.

## Contents

- [Mental Model](#mental-model) — the three-level marketplace → plugin → skill hierarchy
- [Pattern: Single-Skill Narrow Cache](#pattern-single-skill-narrow-cache) — independent install/update for one skill
- [Pattern: Suite Plugin](#pattern-suite-plugin) — shared namespace for related skills
- [Canonical Source for Suite Members](#canonical-source-for-suite-members) — avoiding duplicate skill directories
- [Anti-Patterns](#anti-patterns) — full-repo sources, symlink suites, broad text replacement
- [Verification Commands](#verification-commands) — schema, resolution, and cache footprint checks

## Mental Model

Claude Code marketplace distribution has three levels:

```text
marketplace -> plugin -> skill
```

- **Marketplace** is the catalog and install suffix: `plugin@marketplace`.
- **Plugin** is the install/update/cache boundary and slash namespace.
- **Skill** is the actual `SKILL.md` capability.

`source` defines the installed plugin root. `skills` paths are resolved relative
to that root.

## Pattern: Single-Skill Narrow Cache

Use this when a skill should install and update independently:

```json
{
  "name": "mermaid-tools",
  "source": "./daymade-docs/mermaid-tools",
  "strict": false,
  "version": "1.0.2",
  "skills": ["./"]
}
```

Expected cache:

```text
SKILL.md
references/
scripts/
```

The slash command remains `/mermaid-tools:mermaid-tools` because the plugin and
skill have the same name. This is acceptable when independence matters more than
namespace aesthetics.

## Pattern: Suite Plugin

Use this when related skills should share one namespace:

```json
{
  "name": "daymade-docs",
  "source": "./daymade-docs",
  "strict": false,
  "version": "1.0.1",
  "skills": [
    "./doc-to-markdown",
    "./mermaid-tools",
    "./pdf-creator",
    "./ppt-creator",
    "./docs-cleaner",
    "./meeting-minutes-taker"
  ]
}
```

Expected slash commands:

```text
/daymade-docs:doc-to-markdown
/daymade-docs:mermaid-tools
/daymade-docs:pdf-creator
```

Expected cache top level:

```text
doc-to-markdown/
docs-cleaner/
meeting-minutes-taker/
mermaid-tools/
pdf-creator/
ppt-creator/
```

## Canonical Source for Suite Members

If users also need single-skill installs for suite members, point the individual
plugin entries at the same canonical subdirectories:

```json
{
  "name": "pdf-creator",
  "source": "./daymade-docs/pdf-creator",
  "strict": false,
  "version": "1.3.2",
  "skills": ["./"]
}
```

Avoid keeping duplicate root-level skill directories and suite copies. Duplication
creates drift and makes version bumps ambiguous.

## Anti-Patterns

### Full repo source for a single skill

```json
{
  "name": "mermaid-tools",
  "source": "./",
  "skills": ["./mermaid-tools"]
}
```

This loads correctly but installs a full repository cache for one plugin. The cache
will contain unrelated skills and can confuse debugging.

### Symlink suite directories

Do not build suite sources from symlinks to canonical skill directories. Claude Code
preserves the symlink in the cache, and the symlink can point back to the marketplace
working copy. That cache is not self-contained or version-immutable.

### Text-wide source replacement

Do not patch `source` fields by broad text replacement. In a real failure, a patch
that intended to change only docs plugins also changed unrelated plugins like
`skill-creator` and `statusline-generator`. Use a structured JSON edit keyed by
`plugins[].name`, then run a source+skills resolution check.

## Verification Commands

Schema + resolution + reverse sync in one shot (uses the bundled script):

```bash
bash scripts/check_marketplace.sh          # validate current repo
bash scripts/check_marketplace.sh /path    # validate a target repo
```

`check_marketplace.sh` runs four checks:

1. JSON syntax of `.claude-plugin/marketplace.json`
2. `claude plugin validate .` (skipped if `claude` CLI is missing)
3. source+skills resolution (every plugin path resolves to a real `SKILL.md`)
4. Reverse sync (WARN-only when a disk `SKILL.md` is not registered)

Inspect the installed cache footprint (cannot be done by the pre-flight script
because it depends on what `claude plugin install` actually produced):

```bash
PLUGIN=<plugin-name>
MARKET=<marketplace-name>
CACHE=$(jq -r --arg id "$PLUGIN@$MARKET" \
  '.plugins[$id][0].installPath' ~/.claude/plugins/installed_plugins.json)
find "$CACHE" -maxdepth 1 -mindepth 1 -exec basename {} \; | sort
find "$CACHE" -maxdepth 1 -type l -ls
```

A symlink in the cache almost always means the plugin was built from a symlink
suite and is not self-contained. Fix by pointing `source` at a real canonical
directory.

