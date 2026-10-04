# Local release readiness

Use this after the required independent review and before a Git publication step.
This marketplace's existing pre-push dispatcher checks changed shipped Skill roots
against the exact pushed commit. Root documentation and excluded test/eval-only
changes do not need a release receipt. The normal version and shared PII guards
still run. CI does not have access to the private archive and does not run this
local evidence check.

## Commit the current review first

Keep the review in the private knowledge repository's permitted directory. Preserve
the reviewer prompt verbatim, findings/dispositions and limits required by
[independent review](independent-review-protocol.md). Add one JSON comment block:

```text
<!-- skill-release-review
{"schema":1,"candidate":"<full 40-hex reviewed commit>","skill_paths":["<repository-relative Skill root>"],"result":"passed"}
-->
```

List every changed shipped Skill root. Include the exact commit under review;
resolve it with `git rev-parse HEAD`. Commit the archive and inspect that command's
exit status before any dependent action. A failed commit stops publication. Resolve
the archive's full commit only after success. Never send private archive content
into the public Skill repository.

```bash
python3 <skill-creator-path>/scripts/release_readiness.py attest \
  --repo <source-worktree> --candidate <reviewed-full-sha> \
  --skill-path <skill-root> \
  --review-repo <private-knowledge-worktree> \
  --review-commit <archive-full-sha> --review-path <review-relative-path>
python3 <marketplace-path>/scripts/ci/check_skill_release.py \
  --repo <source-worktree> --base <current-main> --candidate <reviewed-full-sha>
```

Repeat `--skill-path` for multiple roots. The receipt is local under Git's common
metadata directory, shared by linked worktrees. Verification requires the archive
blob to remain committed at its current HEAD and unchanged on disk; unrelated
archive commits are allowed. A missing, dirty, replaced, stale or non-passed review
blocks push. A new candidate commit needs a new review binding. Stop on nonzero
status; do not batch dependent mutations without checking each result.

For a spelling-only or pure formatting change, the existing review exemption can
be declared with `--review-not-required typo-only` or `format-only` and a nonblank
`--reason`, instead of the three archive arguments. This is an attributable author
classification, not a semantic validator. The gate cannot establish review quality,
reviewer independence, private visibility or whether the exemption is truthful;
those remain the review and operator contracts. Do not use an exemption to bypass
a substantive change or move the private artifact into a distributed repository.

For another repository, its existing push dispatcher must call the verifier for
its exact candidate and affected Skill roots. Merely installing this Skill does
not install a global hook. Until that integration exists, invoke the checker
explicitly and inspect its result before push.
