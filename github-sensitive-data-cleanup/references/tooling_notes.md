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
git clone --mirror --no-local /path/to/repo /tmp/repo-mirror.git
```

After a successful clone, run the bundled `rewrite_history.py` from the Skill
directory with `--repo /tmp/repo-mirror.git`.
Keep the native fresh-clone guard; do not add `--force`. The wrapper rejects
linked worktrees and ordinary/bare repositories with attached worktrees.
Save the verified publication target and remote preimage before rewriting, as
described in SKILL.md's Step 4; a local mirror's source URL is not the approved
push destination. If git-filter-repo removes the remote, restore only its saved
verified configuration and retain the old remote SHA for the explicit lease.

### "Cannot combine --force with ..."

`git-filter-repo` has strict option validation. Read the error and preserve its
safety boundary. The bundled `rewrite_history.py` does not pass `--force` and
provides no fresh-clone or shared-history bypass.

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

Use this pickaxe form for a manual "when did this string enter/leave" check.
`verify_cleanup.py` itself checks each pattern over both channels: blob
content (`git grep` across every commit's tree) and commit messages
(`git log` over all refs with a hash-annotated record format, decoded with
`errors="replace"` so legacy-encoded messages cannot crash verification).
A FAILED message check lists the offending commit hashes
(`commit_message_commits`, first 10), not just a count.

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
