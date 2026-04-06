# Anti-Patterns: Marketplace Development Pitfalls

Every item below was encountered during real marketplace development.
Not theoretical — each cost debugging time.

## Schema Errors

### Adding `$schema` field
- **Symptom**: `claude plugin validate` fails with `Unrecognized key: "$schema"`
- **Fix**: Do not include `$schema`. Unlike many JSON schemas, Claude Code rejects it.
- **Why it's tempting**: Other marketplace examples (like daymade/claude-code-skills) include it,
  and it works for JSON Schema-aware editors. But the validator is strict.

### Using `metadata.homepage`
- **Symptom**: Silently ignored — no error, no effect.
- **Fix**: `metadata` only supports `description`, `version`, `pluginRoot`. Put `homepage`
  on individual plugin entries if needed.
- **Why it's tricky**: `homepage` IS valid on plugin entries (from plugin.json schema),
  so it looks correct but is wrong at the metadata level.

### Conflicting `strict: false` with `plugin.json`
- **Symptom**: Plugin fails to load with "conflicting manifests" error.
- **Fix**: Choose one authority. `strict: false` means marketplace.json is the SOLE
  definition. Remove plugin.json or set `strict: true` and let plugin.json define components.

## Version Confusion

### Using marketplace version as plugin version
- **Symptom**: All plugins show the same version (e.g., "2.3.0") even though each was
  introduced at different times.
- **Fix**: `metadata.version` = marketplace catalog version (matches repo VERSION file).
  Each plugin entry `version` is independent. First time in marketplace = `"1.0.0"`.

### Not bumping version after changes
- **Symptom**: Users don't receive updates after you push changes.
- **Fix**: Claude Code uses version to detect updates. Same version = skip.
  Bump the plugin `version` in marketplace.json when you change skill content.

## Description Errors

### Rewriting or translating SKILL.md descriptions
- **Symptom**: Descriptions don't match the actual skill behavior. English descriptions
  for a Chinese-audience repo feel foreign.
- **Fix**: Copy the EXACT `description` field from each SKILL.md frontmatter.
  The author wrote it for their audience — preserve it.

### Inventing features in descriptions
- **Symptom**: Description promises "8,000+ consultations" or "auto-backup and rollback"
  when the SKILL.md doesn't mention these specifics.
- **Fix**: Only state what the SKILL.md frontmatter says. If you want to add context,
  use the marketplace-level `metadata.description`, not individual plugin descriptions.

## Installation Testing

### Not testing after GitHub push
- **Symptom**: Local validation passes, but `claude plugin marketplace add <user>/<repo>`
  fails because it clones the default branch which doesn't have the marketplace.json.
- **Fix**: Push marketplace.json to the repo's default branch before testing GitHub install.
  Feature branches only work if the user specifies the ref.

### Forgetting to clean up test installations
- **Symptom**: Next test run finds stale marketplace/plugins and produces confusing results.
- **Fix**: Always uninstall plugins and remove marketplace after testing:
  ```bash
  claude plugin uninstall <plugin>@<marketplace> 2>/dev/null
  claude plugin marketplace remove <marketplace> 2>/dev/null
  ```

## PR Best Practices

### Modifying existing files unnecessarily
- **Symptom**: PR diff includes unrelated changes (empty lines in .gitignore, whitespace
  changes in README), making it harder to review and merge.
- **Fix**: Only add new files. If modifying README, be surgical — only add the install section.
  Verify with `git diff upstream/main` that no unrelated files are touched.

### Not squashing commits
- **Symptom**: Git history has 15+ commits with iterative demo.gif changes, bloating the
  repo by megabytes. Users cloning the marketplace download all this history.
- **Fix**: Squash all commits into one before creating the PR:
  ```bash
  git reset --soft upstream/main
  git commit -m "feat: add Claude Code plugin marketplace"
  ```

## Discovery Misconceptions

### Over-investing in keywords/tags
- **Symptom**: Spending time crafting perfect keyword lists.
- **Reality**: In the current Claude Code source (verified by reading DiscoverPlugins.tsx),
  the Discover tab searches ONLY `name` + `description` + `marketplaceName`.
  `keywords` is defined in the schema but never consumed. `tags` only affects UI
  for the specific value `"community-managed"`. Include keywords for future-proofing
  but don't obsess over them.

### Using `tags` for search optimization
- **Symptom**: Adding `tags: ["business", "diagnosis"]` expecting search improvements.
- **Reality**: Only `tags: ["community-managed"]` has any effect (shows a UI label).
  The official Anthropic marketplace (123 plugins) uses tags on only 3 plugins,
  all with the value `["community-managed"]`.
