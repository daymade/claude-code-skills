# Local release readiness

Use this when preparing a candidate for independent review and Git publication.

## Select the publication contract before attesting

Verify the destination's current visibility and read its repository-owned review
and push contract before choosing an archive location or checker. Unknown
visibility remains unresolved; do not assume either public isolation or a private
same-repository allowance.

- **Public distribution:** keep private review evidence in an externally committed
  private archive and use the helper procedure below. Never ship the archive with
  the public Skill.
- **Private repository with a same-repository archive contract:** keep the review
  in its permitted location and follow that repository's own candidate binding,
  archive-commit and publication gate. Keep the archive out of the distributed
  package. Do not require the public helper to attest this layout.
- **Private repository using an external archive:** the helper below can bind that
  external evidence when it matches the repository's publication contract.

The executor selects and reads back the applicable gate. `release_readiness.py`
supports external archives only: both attest and verify reject an archive sharing
the published repository's Git common directory, regardless of visibility.
Choosing a private repository's own gate does not relax or bypass that helper.
Report which gate actually passed; a same-repository release is not a successful
helper attestation. If no applicable gate is defined, resolve the publication
contract before pushing rather than inventing a readiness claim.

## Integrate current main before binding review

Fetch the named remote's main branch and resolve its full commit. Integrate that
tree in the owned feature worktree before freezing the candidate; preserve parallel
work. A candidate missing current main is integration drift, not a request to
review main's unrelated Skills. Keep the final-tree comparison and version checks.

If a stale marketplace guard blocks the change, integrate main first. Rebuild any
remaining manifest conflict from that immutable base plus only the owned changes;
assert the base values and preserve the trailing newline. On a contended shared
checkout where `git merge` (ort) refuses staged files, merge in a temporary
worktree, copy the merged file back so staged content equals the merge
result byte-for-byte, then `git merge --ff-only <merge-sha>` — a
fast-forward accepts staged content that equals the target; ort never does.
Preserve other writers' changes throughout this recovery. Stage and commit as
separate commands under the repository's commit contract.

Resolve the integrated candidate with `git rev-parse HEAD`, then run the version
check before binding review evidence:

```bash
python3 <marketplace-path>/scripts/ci/check_version_progression.py \
  --repo <source-worktree> --base <fetched-main-full-sha> \
  --candidate <integrated-candidate-full-sha>
```

Read the merged CHANGELOG and confirm its entries remain under the intended
heading; a union merge preserves lines, not their placement. Review this candidate,
commit its permitted archive and attest only after the checks pass. If main moves
again, integrate it and bind the resulting exact commit anew. Reuse earlier
behavior evidence only for content proved unchanged; review the changed delta.
For an unchanged complete distribution, use the opt-in rebind procedure below
instead of editing the original independent review.

## GitHub says dirty; git says clean

`mergeable_state: dirty` is an asynchronous cache, not a verdict. After the base
moves under parallel mergers it can stick, and close/reopen does not reliably
recompute it. The local oracle is `git merge-tree --write-tree <branch>
origin/main` (exit 0 = clean); when git says clean and GitHub says dirty, pushing
a branch that contains current main (a real integration merge) is the reliable
refresher — the head changes, so rebind evidence to the new head.

A strict up-to-date ruleset plus a fleet merging every few minutes is a
livelock: each integration changes the head, CI reruns (~20 min class), and
another peer lands in between. The only lever is merge latency — merge the
instant checks go green (a background poller on the check-runs API, not a
long-lived `--watch`), and keep the content diff byte-identical across every
base move so the existing review stays valid: the review covers the content,
not the parent commit.

## External-archive helper and dispatcher

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
  --repo <source-worktree> --base <fetched-main-full-sha> --candidate <reviewed-full-sha>
```

Repeat `--skill-path` for multiple roots. The receipt is local under Git's common
metadata directory, shared by linked worktrees. Verification requires the archive
blob to remain committed at its current HEAD and unchanged on disk; unrelated
archive commits are allowed. A missing, dirty, replaced, stale or non-passed review
blocks push. A new candidate commit needs a new review binding. A nonzero or
ambiguous result pauses dependent mutations until its documented meaning and
the required readback establish readiness; do not batch unchecked mutations.

## Rebind an unchanged distribution after main integration

The release executor may use `rebind` only when the original committed review
declares its complete additional repository dependency scope. Add a nonempty
`rebind_dependencies` list to that review's JSON block **before its original
attestation**, and have the independent reviewer check its completeness. Name
whole cross-plugin dependency roots, not only the one helper called in a sample.
For a package with no additional repository dependency, list the packaging-policy
owner itself: `"rebind_dependencies":["daymade-skill/skill-creator/scripts/packaging_policy.py"]`.
Missing, empty, null, duplicate or malformed declarations cannot enable reuse.
Legacy reviews without this declaration retain normal `attest`/`verify`; obtain
a normal reviewed binding before using rebind rather than retrofitting an old
review with an unreviewed dependency claim.

The helper automatically binds every shipped file of each **whole registered
plugin**, including sibling Skills and plugin-level helpers; the exact selected
plugin catalog objects; shared repository files; the packaging-policy source;
and every declared dependency's complete tracked tree. Skill files use the
shared packaging policy. Shared/dependency files are compared without exclusions.
Only `CHANGELOG.md` and unrelated catalog entries are outside the shared-file
comparison. File modes and Git blob identities must match. Internal symlinks bind
their complete tracked targets; escaping, dangling or cyclic links and submodules
block reuse. Missing roots, changed policy/dependencies/plugin metadata and changed source
identity block reuse. This route requires local marketplace sources and the
packaging-policy owner at the path shown above.

Dependency discovery and review quality remain human/agent review judgments:
the helper cannot infer complete dynamic dependencies or verify an external
service. An incomplete or unknown dependency closure requires normal review.
The machine check prevents a later caller from narrowing or expanding the
original exact Skill/dependency scope; it does not certify the original
declaration's semantic completeness.

After fetching and integrating `origin/main`, run:

```bash
python3 <skill-creator-path>/scripts/release_readiness.py rebind \
  --repo <source-worktree> --candidate <new-full-sha> \
  --from-candidate <original-reviewed-full-sha> \
  --base <fetched-main-full-sha> --skill-path <same-skill-root>
python3 <skill-creator-path>/scripts/release_readiness.py verify \
  --repo <source-worktree> --candidate <new-full-sha> \
  --skill-path <same-skill-root>
```

Repeat every original `--skill-path`; changed or omitted scope fails. The original
candidate must remain an ancestor and the new candidate must include current
fetched main. Rebased or rewritten ancestry needs a normal reviewed binding.
Rebind writes a schema-2 local receipt and leaves both the original receipt and
committed review untouched. The verifier reopens the original archive, checks its
current committed clean path, original receipt digest, source identity, complete
distribution equality and current fetched-main integration. A changed original
receipt or stale candidate blocks verification. Repeated identical rebind is
idempotent; existing different evidence is never overwritten.

The exact-head publication checker consumes the new receipt. Version progression,
privacy/security and repository publication checks still run through their
existing owners. A rebind is evidence reuse, not a new independent review or a
claim that changed content passed. Normal schema-1 writer/reader behavior remains
supported. Old readers reject schema 2; update the release-checking consumer
before relying on rebind. The helper does not fetch, commit an archive, push or
merge on the operator's behalf. Stop after the actual publication gate passes;
run a normal review when equivalence is rejected.

## Other attestation routes

For a spelling-only or pure formatting change, the existing review exemption can
be declared with `--review-not-required typo-only` or `format-only` and a nonblank
`--reason`, instead of the three archive arguments. This is an attributable author
classification, not a semantic validator. The gate cannot establish review quality,
reviewer independence, private visibility or whether the exemption is truthful;
those remain the review and operator contracts. Do not use an exemption to bypass
a substantive change or move the private artifact into a distributed repository.

For another repository using this external-archive helper, its push dispatcher
must call the matching verifier for its exact candidate and affected Skill roots.
Merely installing this Skill does not install a global hook. Until that integration
exists, invoke its compatible checker explicitly and inspect the result before
push. A repository-owned same-repository archive gate remains under that
repository's contract; this helper does not implement it.
