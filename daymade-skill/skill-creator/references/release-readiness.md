# Local release readiness

Use this after the required independent review and before a Git publication step.
This marketplace's existing pre-push dispatcher checks changed shipped Skill roots
against the exact pushed commit. Both branch and tag pushes are checked; annotated
tags bind to their target commit. Tags pointing to a commit already reachable from
current main introduce no new Skill content and need no new receipt. Root documentation and excluded test/eval-only
changes do not need a release receipt. Branch pushes retain the version guard;
the shared PII guard still receives the original update set. CI does not have
access to the private archive and does not run this
local evidence check.

Before attesting a public release, check that the private review records the
[public-distribution axes](independent-review-protocol.md#public-distribution-axes)
against this exact candidate and the public files declared for that pass. Use the
shared `scripts/packaging_policy.py` for the distributed dependency set. Source dispositions and
dependency observations belong in the review; a `passed` metadata field alone
does not establish them.

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
exit status before any dependent action. If committing and landing are combined,
classify the result using that tool's exit-code contract: a nonzero result can
report completed landing with a concurrent-state notice. Independently verify
the exact archive path is committed at current HEAD, unchanged on disk, and bound
to the reviewed candidate before proceeding. A failed or unverified commit stops
publication; do not recreate a commit merely because landing reported a notice.
Resolve the archive's full commit only after that readback. Never send private archive content
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
blocks push. A new candidate commit needs a new review binding. A nonzero or
ambiguous result pauses dependent mutations until its documented meaning and
the required readback establish readiness; do not batch unchecked mutations.

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
