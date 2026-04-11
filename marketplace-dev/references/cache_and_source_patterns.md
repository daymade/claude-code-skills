# Cache and Source Patterns

This reference captures marketplace lessons from real Claude Code marketplace work:
full-repo cache pollution, suite namespace design, symlink experiments, and version
semantics.

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
  "source": "./suites/daymade-docs/mermaid-tools",
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
  "source": "./suites/daymade-docs",
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
  "source": "./suites/daymade-docs/pdf-creator",
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

Validate schema:

```bash
claude plugin validate .claude-plugin/marketplace.json
```

Validate source+skills resolution:

```bash
node - <<'NODE'
const fs = require('fs');
const path = require('path');
const data = JSON.parse(fs.readFileSync('.claude-plugin/marketplace.json', 'utf8'));
let ok = true;
for (const p of data.plugins || []) {
  if (typeof p.source !== 'string' || !p.source.startsWith('./')) continue;
  const root = p.source.replace(/^\.\//, '').replace(/\/$/, '') || '.';
  for (const s of p.skills || []) {
    const rel = s.replace(/^\.\//, '').replace(/\/$/, '') || '.';
    const skillPath = path.join(root, rel, 'SKILL.md');
    if (!fs.existsSync(skillPath)) {
      ok = false;
      console.log(`MISSING ${p.name}: ${skillPath}`);
    }
  }
}
if (!ok) process.exit(1);
console.log('All marketplace skill paths exist');
NODE
```

Validate installed cache:

```bash
PLUGIN=<plugin-name>
MARKET=<marketplace-name>
CACHE=$(jq -r --arg id "$PLUGIN@$MARKET" '.plugins[$id][0].installPath' ~/.claude/plugins/installed_plugins.json)
find "$CACHE" -maxdepth 1 -mindepth 1 -exec basename {} \; | sort
find "$CACHE" -maxdepth 1 -type l -ls
```

