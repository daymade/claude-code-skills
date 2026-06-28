# Tooling Notes for GitHub Sensitive Data Cleanup

## git-filter-repo vs BFG Repo-Cleaner

### git-filter-repo (recommended default)

- **Pros:** Modern, actively maintained, Python-based, flexible
  `--replace-text`, readable docs, safer defaults than
  `git-filter-branch`.
- **Cons:** Requires a "fresh enough" clone (no multiple remotes, no stale
  refs). Slower than BFG on very large repositories.
- **Install:** `brew install git-filter-repo`

### BFG Repo-Cleaner

- **Pros:** Very fast on large repos. Good for removing large files or
  converting files to `git-lfs`.
- **Cons:** Requires Java. Less flexible than git-filter-repo for arbitrary
  string replacement. Slightly more complex for private-domain replacement.
- **Install:** Download the JAR from the official repo.

**Rule of thumb:** Use `git-filter-repo` for private-domain / secret-string
replacement. Use BFG if the repo is huge and you are mainly removing large
files.

## Common git-filter-repo Errors

### "Need a fresh clone"

```text
Error: Need a fresh clone to operate on.  Please clone with `git clone --mirror ...`
```

**Cause:** The repo has multiple remotes, stale refs, or was not cloned
normally.

**Fix:**

```bash
git clone --mirror /path/to/repo /tmp/repo-mirror.git
cd /tmp/repo-mirror.git
# run rewrite_history.py here
```

### "Cannot combine --force with ..."

`git-filter-repo` has strict option validation. Read the error and adjust the
command. The bundled `rewrite_history.py` uses the minimal safe set of flags.

## gitleaks Allowlist Patterns

If gitleaks flags test fixtures or documentation examples, add an allowlist
rather than bypassing the hook.

Example `.gitleaks.toml`:

```toml
title = "Repo allowlist"

[allowlist]
paths = [
  '''tests/fixtures/secrets.json''',
  '''docs/examples.md''',
]
regexes = [
  '''sk-kimi-REDACTED''',
]
```

Never use `--no-verify` to suppress a real finding.

## Replacement File Syntax

`git-filter-repo --replace-text` accepts a file with one replacement per line:

```text
literal:old-string==>new-string
regex:old-pattern==>new-string
```

Use `literal:` for exact strings. Use `regex:` only when necessary and test
thoroughly, because a bad regex can corrupt many commits.

## Checking Whether a String Is in History

```bash
git log --all --pickaxe-regex -S 'your-pattern' --pretty=format:'%H %s'
```

This is what `verify_cleanup.py` does for each pattern.

## Git Bundle Backups

A bundle is a file that contains a complete copy of the repository refs. It
can be cloned or fetched from later:

```bash
# Create
git bundle create backup.bundle --all

# Verify
git bundle verify backup.bundle

# Restore
git clone backup.bundle restored-repo
```

## GitHub Support

For severe leaks (live production secrets, PII), contact GitHub Support after
rotating credentials. They can remove cached views of sensitive data and
assist with repository-level cleanup.
