# Merge Verification — prove content is merged without being fooled by counts

## Why commit counts lie (the squash-merge illusion)

When a PR is **squash-merged**, main gets one new commit whose *content* equals the branch, but
whose *sha* is new — the branch's original commits are not ancestors of main. So:

```bash
git rev-list --count origin/main..stale-branch   # → 173  ("173 commits ahead!")
```

…is a lie about merge status. Those 173 commits are the branch's own history; their content is
already on main. **Never conclude "unmerged" (or "safe to keep this branch") from a count.**
The same applies to rebased branches: rebasing rewrites shas, so the pre-rebase commits look
"unmerged" while their content landed long ago.

The only trustworthy question is: **is the branch's content already contained in the base?**

## The sound content check (a trial merge, not a heuristic)

`scripts/git_verify_branch_merged.sh <branch> [base]` answers that question with Git's own merge
machinery instead of per-file guesses. It rejects the base ref itself as a deletion target, then
runs two checks in order:

1. **Ancestor** — the branch is literally in the base's history:
   ```bash
   git merge-base --is-ancestor origin/<branch> origin/main && echo "MERGED (ancestor)"
   ```

2. **Content-contained** — do a trial 3-way merge of the branch *into* the base, in memory, and
   ask whether it changes anything. If merging the branch produces the base's exact tree, the
   branch adds nothing the base lacks — which is precisely the squash/rebase case where the count
   says "ahead" but the content is already upstream:
   ```bash
   base_tree=$(git rev-parse "origin/main^{tree}")
   if merge_output=$(git merge-tree --write-tree origin/main origin/<branch> 2>&1); then
     merged_tree=$(printf '%s\n' "$merge_output" | head -1)
     [ "$merged_tree" = "$base_tree" ] && echo "MERGED (content contained)"
   fi
   ```

This is **sound**, not a heuristic, because it *is* Git's merge: a revert, an edit, or a new file
the base lacks would change the merged tree and fail the equality — so it can never be silently
mistaken for "merged." (`git merge-tree --write-tree` needs git ≥ 2.38; on older git the script
cannot prove containment and falls back to reporting NEEDS REVIEW rather than guessing.)

Everything else is **UNMERGED / NEEDS REVIEW**. To show what to review, list the branch's own
contribution (three-dot = what it changed since diverging), display-safe for Unicode/space paths:

```bash
git -c core.quotePath=false diff --no-renames --name-status origin/main...origin/<branch> --
```

`--no-renames` decomposes a rename into add+delete (so a renamed-and-edited file can't hide); the
`--` guarantees a branch named like a path (e.g. `docs`) is never parsed as a pathspec.

Three-dot is correct **here** — the question is "what did this branch contribute", and hiding the
base's parallel work is the point. It is the wrong form for "what does the base lack"; see
[Pick the diff FORM](#pick-the-diff-form-from-the-question-youre-asking-two-dot-vs-three-dot).

## Per-branch verdict procedure

For each branch, the script returns one of these outcomes:

- **MERGED (ancestor)** — in the base's history. Content containment is proven; deletion still
  requires the separately authorized Mode E target, current ref equality, and preservation gate.
- **MERGED (content contained)** — a trial merge into the base changes nothing; the "commits
  ahead" count is a squash/rebase artifact. This proves content containment, not deletion authority.
- **UNMERGED / NEEDS REVIEW** — a trial merge *would* change the base, so the branch carries
  content the base does not already have (a genuinely new/edited/reverted/deleted file). Review
  the listed contribution before deleting.

## Pick the diff FORM from the question you're asking (two-dot vs three-dot)

`git diff base...ref` and `git diff base ref` answer **different questions**, and reaching for the
wrong one produces a confidently wrong "nothing is missing." Both are content-level, so the usual
"don't judge by counts" instinct does not catch the mistake.

| Question | Form | Why |
|---|---|---|
| "What did this branch *change* since it diverged?" (reviewing a PR's contribution) | **three-dot** `base...ref` | Diffs from the **merge base** to `ref` — deliberately hides everything `base` did in parallel, which is what makes a PR diff readable. |
| "What does `base` **lack** that `ref` has?" (auditing a retired/archived ref for lost work) | **two-dot** `base ref` | Compares the two trees **as they are now**. This is the loss question. |

Three-dot is wrong for the loss question because a file that existed at the merge base and was
later deleted from `base` is *not* part of "what the branch changed" — so it never appears, even
though `base` genuinely lacks it today. Real incident: auditing three archive tags with
`git diff origin/main...<tag> --diff-filter=A` reported **1** file missing from main; the same
audit with the two-dot form reported **5** (the extras included a real 107-line script). The
three-dot answer was not a rounding error — it was a different question, answered correctly.

```bash
# "What would I lose by deleting this ref?" — always two-dot:
git diff <base> <ref> --name-only --diff-filter=A     # files ONLY on <ref>
git diff <base> <ref> --stat | tail -1                # aggregate direction
```

Read the aggregate direction as triage, not verdict: **base-only lines ≫ ref-only lines** is the
fingerprint of "base evolved past this ref" (safe); it does not by itself clear the ref-only lines,
which still need the supersession ladder below. In that same audit the archive tags showed ~58,000
base-only vs ~3,700 ref-only lines — overwhelmingly superseded, yet the ~3,700 still hid the one
file worth investigating.

## Why safety-biased: a false "merged" loses work, a false "unmerged" only costs a look

The two error directions are not symmetric. A false **UNMERGED** wastes a second look; a false
**MERGED** tells you to delete a branch whose work then vanishes. So the check is deliberately
biased: it only says "safe to delete" when it can *prove* containment, and it reports everything
it cannot prove as NEEDS REVIEW. One real consequence: if a branch was squash-merged **and** the
base later edited the same lines, the trial merge no longer reproduces the base tree exactly, so
the script says NEEDS REVIEW rather than MERGED. That over-reporting is the correct trade — you
look, confirm the lines are redundant, and delete; you never lose work to a confident wrong "yes."

## The historical-merge-commit rung — proving containment when base moved past a landed change

The sound content check above answers "is the branch contained in base *right now*". That is
usually the right question — but it has one blind spot: once base has changed **the same lines
again** after a squash-merge landed the branch, a fresh trial merge of the branch into the
*current* base conflicts instead of reproducing base's tree, even though the branch's content
genuinely landed. An edit elsewhere — another file, or other lines of the same file — does not
trigger this; the trial merge still proves containment. The blind spot is routine wherever many
branches touch one shared line: a version field the next release bumps again, a changelog block
every change prepends to. The squash-merge illusion and this one look alike (a real squash-merged
branch reading as something other than cleanly MERGED) but need different fixes: the squash
illusion is fixed by checking content instead of commit count (above); this one is fixed by
checking content **at the right point in time**.

"Landed once" and "still there now" are different questions, and the trial merge against the
current base can only ever answer the second one. When it cannot prove containment, do not fall
straight to the unsound hints below (`git cherry`, a blob search) — first ask whether a *sound*
answer to the *first* question is available: does a hosting platform's record say this branch's
content was already merged, and if so, at which commit?

**The check**, implemented by `scripts/git_verify_branch_merged.sh --merge-commit <sha>` for one
branch and by `scripts/git_classify_refs.sh --base <sha> --pr-map <json>` for a whole batch:

1. Require the candidate merge commit `M` to be an ancestor of base. Refuse otherwise — an `M`
   that never reached base at all cannot be used as a "landed at" baseline; it could be from a
   line of history that was reverted, or one that never merged into this base to begin with.
2. Trial-merge the branch into `M` (not into base). If the result reproduces `M`'s own tree
   exactly, the branch's content was fully present at that historical merge — sound, for the same
   reason the base trial merge is sound: it is Git's own merge, so anything the branch still adds
   on top of `M` would change the result and fail the equality.

**The boundary, and why it must be stated in every verdict this rung produces:** this proves
containment **at that merge commit**, never that the **current** base still has it. Base may have
reverted, overwritten, or otherwise dropped the content since `M`. If the next action depends on
whether base has it *right now*, this rung is not sufficient by itself — the current-base trial
merge is still the authority for that question, and a NEEDS-REVIEW verdict from it, alongside a
LANDED-AT-MERGE verdict from this rung, is not automatically a contradiction — but it is not
automatically a loss either. Which one it is depends on the *shape* of the current-base
NEEDS-REVIEW result: a conflict is routine (base moved the same lines forward again); a clean
merge that would still change base is the actual fingerprint of lost content. See
"Landed, then lost" (below) for how to read that shape before concluding anything.

**Where `M` comes from:** this rung never queries a hosting platform itself — both scripts stay
offline. The caller supplies `M` after independently confirming, through the hosting platform's
own API/CLI, that the branch's tip equals a specific pull request's recorded head and that pull
request's state is `MERGED`; `M` is that pull request's own merge-commit SHA. Most hosting
platforms keep a merged pull request's head ref addressable long after its source branch is
deleted, which is why this rung stays usable even once the original branch is long gone — `M`
itself, once it is an ancestor of base, never becomes unreachable from local history either.
If the branch itself needs recovering — not just verifying — rather than only its merge-commit
SHA, `recovery_playbook.md`'s Ladder step 4 has the concrete `refs/pull/<N>/head` commands.

On GitHub, do that confirmation by PR number, not by branch name: `gh pr list --head <branch>` has
returned an empty result for a branch whose pull request was already `MERGED` — checked again by
number moments later, it showed `MERGED` (measured), and a branch-deletion decision built on the
empty result would have been wrong. Use `gh pr view <number> --json headRefOid,state,mergeCommit`,
or the REST equivalent `gh api repos/<owner>/<repo>/pulls/<number>`, for the check. When the PR
number itself is not yet known, REST search still beats `pr list`:
`gh api "repos/<owner>/<repo>/pulls?state=all&head=<owner>:<branch>"`.

## Landed, then lost — investigating content that provably merged but is missing from the current base

**Identify the signal first: one pair of verdicts covers both a routine case and a loss, and only
the *shape* of the current-base result tells them apart.** A branch whose merge is independently
confirmed (its tip equals the PR's recorded head, and the PR's state is `MERGED`) reports LANDED
with `--merge-commit <that PR's merge commit>` but NEEDS REVIEW against the *current* base. Read
how the current-base trial merge failed:

- **It conflicts** — base went on to change the same lines (the next version bump, a rewritten
  entry). Nothing is missing; this is the routine case the historical-merge-commit rung exists for.
- **It merges cleanly but would change base** — the branch's lines can be re-applied without
  conflict, which means base no longer has them and put nothing else in their place. Something on
  base's own history, after the merge commit, wrote the content back out. This is the fingerprint
  of a **candidate regression**, not of unmerged work.

Treating the second shape as "still unmerged" and re-landing the branch risks silently reverting
whatever base did afterward (the same double-apply hazard SKILL.md's troubleshooting section
already warns about for a mis-timed rescue); the right response is to find and understand the
regression, not to re-ship.

**Two ways to find it, in order of how targeted the loss is:**

1. **Walk base's own history for the regression, first-parent, comparing one tracked value per
   commit.** Useful whenever the lost content is (or is summarized by) an orderable or
   presence/absence field in a shared manifest — a version number, a counter, an entry that should
   only ever be added to:
   ```bash
   git log --first-parent --reverse --format='%H' <base> -- <path-to-manifest>
   ```
   Walk that commit list and, at each one, read the tracked field's value
   (`git show <commit>:<path-to-manifest>`); a commit where the value goes *down*, or a
   previously-present entry disappears, instead of holding or advancing, is the regression point —
   the commit that did the reverting, and worth reading in full (`git show <commit>`) for *why*.
2. **Diff the merge commit's own copy of the shared file against the current base, line by line:**
   ```bash
   git diff <merge-commit> <base> -- <path>
   ```
   Read the `-` lines (present at merge time, absent from base now) as candidate losses, then run
   each one through this document's existing Supersession triage ladder (rungs 1-4, above) before
   concluding anything is actually lost — a line that a *later, intentional* change legitimately
   replaced is not a regression, it is ordinary iteration, and the ladder is what tells the two
   apart.

**One boundary that keeps this from becoming a noisy repo-wide hunt:** a generic "were any
recently-added lines deleted anywhere in base's history" sweep is not useful at repository scale —
ordinary development constantly deletes lines it just added (refactors, typo fixes, superseded
drafts), so an unscoped version of this check would flag most of a healthy history. It only becomes
decidable evidence once narrowed two ways: to **one specific file** already known to be shared
across the branches/PRs in question, and **excluding commits that are themselves ordinary PR
merges** — a PR merge legitimately adding or removing lines in that file is the normal mechanism,
not a loss, and counting it as one would flag every healthy merge alongside the real regression.

**Cause and prevention, each in one line:** the common cause is a shared checkout that sat for a
long time on an already-merged branch, from which someone later builds a "restore" or "sync back"
commit out of that stale working copy — silently reintroducing the pre-merge state as new,
seemingly ordinary commits on base. The prevention is to confirm a shared checkout's *branch and
HEAD* are current (`git branch --show-current`, `git log -1`) before trusting its working copy as a
commit source, not merely that its `git status` is clean — a clean-but-stale checkout looks
identical to a current one until you check which commit it is actually sitting on.

## Manual-only investigation hints (do NOT auto-decide on these)

These help a **human** investigate a NEEDS-REVIEW branch, but must never drive an automated
"safe to delete" verdict — each has a false-positive mode that can hide real unmerged work:

- `git log origin/main --oneline --find-object="$blob" -- <path>` — did this exact blob ever
  appear at this path in the base's history? A hit *suggests* the base passed through this content.
  **Unsound for auto-decisions:** it also matches a revert (the base *used* to have it but doesn't
  now — the revert is still unmerged work), so a match does not prove "currently contained."
- `git cherry origin/main origin/<branch>` — marks each branch commit `-` (patch already upstream)
  or `+` (not). Useful for cherry-picked/rebased commits, but a squash-merge combines commits into
  one new patch-id, so cherry shows the originals as `+` even though their content is merged.
- Superset tells (base file is larger and contains the branch's distinctive symbols) — a hint the
  base evolved past the branch, to be **confirmed by eye**, not trusted blindly.
- Patch-id set comparison — for each of the branch's unique commits compute
  `git show <sha> | git patch-id --stable`, then look for that id among the base's
  (`git log --format=%H -<N> <base> | while read h; do git show "$h" | git patch-id --stable; done | sort -u`).
  Measured 2026-09-22 in scratch repos, one-commit and two-commit branches, five landing shapes:

  | landing shape | `git cherry <base> <branch>` | this comparison |
  |---|---|---|
  | one-commit squash | `-` | MATCH |
  | two-commit squash | `+ +` | both miss |
  | merge, no squash | *(empty — head is an ancestor)* | *(no unique commits to test)* |
  | cherry-pick | `-` | MATCH |
  | rebase onto base | *(empty — ancestor)* | *(no unique commits to test)* |

  **It has no discriminating power beyond `git cherry`: in all five shapes the two agree, and no shape
  was found where they disagree.** Its only real difference is granularity — a per-commit MATCH/miss
  list instead of an aggregate `+`/`-`. What matters most is the row nobody wants: **a two-commit
  squash makes both instruments miss**, because the squash emits one new patch whose id equals neither
  original. That is GitHub's default PR merge, so this is the shape you are usually asking about, and a
  miss there is *not* evidence of "not contained". Escalate instead of concluding — containment is
  established by § The historical-merge-commit rung above
  (`git_verify_branch_merged.sh --merge-commit`), which states that claim explicitly. Know its two
  preconditions before relying on it: the merge commit `M` must be obtained independently from the
  hosting API (nothing in this skill can derive it), and the rung proves containment **at `M`** — it
  does not prove the content is still in today's base if the base moved again after `M`.
  **Unsound for auto-decisions:** it sees only the window you scan, so a squash older than `-<N>`
  reads as unmerged; the window includes merge commits, whose patch-id is a *combined* diff matching
  no single parent's patch (a trivial merge produces no patch-id line at all); and "contained" says
  nothing about *which* version of the content survived.

When a hint and the trial merge disagree, trust the trial merge; it is the sound one. **What no hint
in this list can do is *establish* containment.** `git cherry` and the patch-id comparison both go
blind on a two-commit squash — the default PR merge, and exactly the shape you are usually asking
about — so a hint's "contained" is never the last word, and its "miss" is a signal to escalate rather
than a verdict. Escalate to § The historical-merge-commit rung above
(`git_verify_branch_merged.sh --merge-commit`), the one that states a containment claim — subject to
its two preconditions, spelled out there.

## Supersession triage — "is this leftover a live WIP or a superseded draft?" (Mode E's method)

Retiring old stashes/backup-branches asks a *different* question than "is this branch merged":
the leftover is often an **early draft of work that later landed in a better form**, so a trial
merge can't clear it (its old lines genuinely differ from the base's evolved lines), yet
restoring it would be a regression, not a recovery. Judge supersession by escalating evidence:

1. **`git cherry <base> <branch>`** — patch-content equivalence. Handles rebases/rewords; every
   `-` is proven-on-base. Only the `+` commits proceed to the next rungs. (For a squash-merged
   backup branch, expect all `+` — that's the squash artifact, not evidence of unmerged work;
   compare *statistics per file* next.)
2. **Same-file superset comparison** — for each file the leftover touches, extract both versions
   and compare shape and content:

   ```bash
   git cat-file -p <leftover-ref>:<path> | wc -l     # vs
   git cat-file -p <base>:<path> | wc -l
   diff <(git show <leftover-ref>:<path>) <(git show <base>:<path>) | grep '^<' | head
   ```

   The `^<` lines are what the leftover has that the base lacks. If they are only *older
   signatures* of things the base now does better (e.g. the same function without a parameter
   the base later added), the leftover is a superseded draft. Real case: a stash the author
   had labeled "unfinished development — handle later" held a 1128-line renderer; the base's
   was 1151 lines — every function present *plus* a later-added `base_url` image-rendering
   parameter. The scary label was stale; the stash was an early draft of already-landed work.
3. **Distinctive-marker probe** — grep the base for the leftover's unique additions (new function
   names, constants, error strings). All present → the work was absorbed (perhaps into a
   refactor that moved it to a different file — search repo-wide, not just the original path).
   Real case: a backup branch's hardening (a required-columns check + a `COALESCE` timestamp
   fix) had been absorbed verbatim into a new shared `_core/` module the refactor created;
   the original file was gone but every marker line lived on at the new path.

4. **Ask the base why it removed this — grep for the leftover's own name/path.** Rungs 1–3 all ask
   "is this content somewhere on the base?" and go quiet when the honest answer is *no*. But "the
   base does not have it" has two opposite causes, and only one is a loss:

   ```bash
   git grep -n "<basename-of-the-missing-file>" <base>     # who mentions it now?
   git log <base> --oneline --diff-filter=D -- <path>      # which commit removed it?
   ```

   A replacement usually **documents the supersession in prose**, and that prose is stronger
   evidence than any marker probe because it states intent rather than resemblance. Real case: a
   107-line `fix-marketplace-paths.py` existed on three archive tags and nowhere on the base — by
   rungs 1–3 a textbook "unique work, rescue it." Grepping the base for its filename surfaced its
   successor saying, in comments: *"replaces the old fix-marketplace-paths.py"*, *"made this worse,
   not better"*, and *"CAUSED the corruption by rewriting the shared file."* The script had been
   **deliberately excised because it was harmful** — the corruption it claimed to fix was its own.
   Restoring it would have reintroduced a known bug while looking like a careful rescue.

   Two removal causes, opposite verdicts:

   | The base's history says | Verdict |
   |---|---|
   | A later commit removed it, and something on the base names it as replaced / harmful / merged-in | **Superseded — do not restore.** Restoring reverts a deliberate decision. |
   | Nothing on the base mentions it; it vanished in a bulk rewrite (`filter-repo`, mass revert, history cleanup) with no successor | **Candidate loss — escalate.** Collateral damage looks identical to intentional removal in the tree; only the surrounding evidence separates them. |

   Also classify what the missing file *is* before escalating: **generated artifacts are not
   work.** Scan markers, lockfiles, and build outputs (anything carrying a timestamp + content
   hash of its own inputs) legitimately differ or vanish between refs and are regenerated on
   demand — three of the "missing" files in that same audit were `.security-scan-passed` markers,
   and their skills were all present on the base, one of them simply moved to another suite
   directory. Check for a **relocation** (`git ls-tree -r <base> --name-only | grep <basename>`)
   before concluding a path's absence means the thing is gone.

**The label on the leftover is not evidence.** Stash messages and branch names describe intent
*at creation time* ("unfinished", "backup", "wip") — they never get updated when the work later
lands through another path. Judge by content against the current base, never by how urgent the
name sounds. The same applies in reverse to *size*: a substantial-looking file the base lacks
(rung 4's 107-line script) reads as "obviously valuable" and is exactly the shape of leftover
most likely to be restored on instinct.

Same safety bias as everywhere else in this skill: prove supersession per item, or keep the item.

## Converging many branches to one main through single-writer windows

Use this READ-DO sequence when the outcome is not one deletion but a repository-wide convergence:
keep every unique behavior, preserve current WIP, and leave exactly one maintained `main`. A branch
list is a moving snapshot while other sessions are alive, so the start-of-task audit cannot double
as the deletion gate. Another active writer makes this sequence read-only: do not fetch, create
objects, update refs, export bundles, push/open PRs, or delete until the repository's existing
coordination proves quiescence and transfers exclusive writer ownership. Hold that ownership
through commit and final readback. If it is lost, stop and restart from a fresh authority snapshot.

The executing agent owns only the explicitly authorized slice of this sequence, not every object
the inventory reveals. `--verify-current` mechanically decides only whether exact ref tips stayed
unchanged; it grants no ownership. Unique-behavior and supersession judgments still require the
content evidence below and have no automatic enforcement.

**When another writer is active and exclusive ownership cannot be obtained, the "stay read-only"
rule above is about the SHARED checkout — it does not blanket-forbid every action everywhere, and
this paragraph narrows it without weakening it.** Split what "another writer is active" actually
threatens. Mutating the shared checkout's `HEAD`, index, or working tree stays fully off-limits
regardless of technique, because nothing can guarantee a concurrent `switch`/`add`/`commit` in that
same checkout does not race yours — this part of the rule is unchanged. A separate class of action
carries its own compare-and-swap guard and needs no shared-checkout ownership at all, because it
runs from your OWN independent worktree or clone and only succeeds if the state it names has not
moved since you read it:

- exporting a bundle from your own worktree (touches nothing shared);
- deleting a remote branch with an expected-tip guard —
  `git push --force-with-lease=<ref>:<expected-sha> origin --delete <branch>` — which refuses
  instead of racing when the remote tip is not the SHA you expected;
- opening a pull request from a linked worktree or your own clone (never touches the shared
  checkout's files);
- a hosted merge that names an expected-head-SHA precondition, which refuses rather than merging
  the wrong tip.

None of these authorize touching the shared checkout, and the CAS guard on each one is only as
good as how fresh the state it compares against is: re-read the current ref/tip **immediately**
before every one of these actions, not from an earlier snapshot — `--force-with-lease` protects
against a mover between your read and your push only when the SHA you pass came from your most
recent read, and an expected-head-SHA merge precondition is worthless if the "expected" value
itself is already stale.

### 1. Freeze the outcome and the first ref snapshot

Before interpreting the inventory, partition objects as follows:

- **change-authorized:** exact checkout/ref/PR targets this task may mutate;
- **inspect-only:** objects the evidence question genuinely requires reading but not changing;
- **excluded collaborator resources:** active or user-excluded worktrees/refs/PRs that this task
  may acknowledge by identity but must not inspect internally, back up, publish, merge, unlock,
  remove, or count as its own unfinished cleanup.

Generic phrases such as "take over", "continue", or "finish this" do not move an object between
sets. The user must name the additional object or otherwise make the expansion unambiguous.

Before spawning reviewers or interpreting refs, the sole writer performs one authority refresh,
including any required fetch, then freezes the exact local and remote-tracking refs and queries the
hosting service for its current branch list and PR heads. Keep the two inventories separate:
remote-tracking refs are a Git cache; the hosting API is authority for branches that exist on the
server. Record every exact tip SHA and give reviewers those immutable SHAs. If another writer is
active and ownership cannot transfer, hosting/API and existing immutable-object reads may inventory
what is already known, but the inability to refresh authority is a reported gap, not permission to
fetch concurrently.

Classify each change-authorized non-main ref by content. Use the trial-merge verdict first. For
NEEDS REVIEW refs, walk the supersession ladder above and open distinctive code/tests at authority.
`git cherry` may surface candidates, but every `+` after a squash merge is still only a hypothesis.
Merge or adapt the smallest unique behavior; never merge an old whole branch merely because it has
many `+` commits or a compelling name. Report inspect-only and excluded refs separately without
turning their existence into an action item.

### 2. Build keeper commits after exclusive ownership transfers

When another session or scheduler is actively changing files, do not switch, use the real index,
create objects with an alternate index, update refs, or publish a PR. Wait for the existing
coordination mechanism to quiesce that writer and transfer exclusive ownership. Once transferred,
build from the freshly fetched frozen base with Mode D's sole-writer alternate-index technique.
Preserve each candidate as an exact `(mode, object ID, path)` tuple from an immutable commit;
copying only blob bytes can silently strip executable (`100755`), symlink (`120000`), or gitlink
(`160000`) behavior. An owned temporary regular file may be hashed only after its intended
`100644`/`100755` mode is verified explicitly; symlinks and submodules must use the immutable-entry
route. Never hash a shared-worktree path attributed to someone else's WIP. Run the candidate's
deterministic tests and the exact hook/security gates that a normal commit would have run before
opening the PR, and retain exclusive ownership through push and final readback.

After a squash merge, do not compare commit SHAs: GitHub creates a new base-branch commit. If the
base did not otherwise move, equal tree IDs prove byte-identical landing. If it did move, compare
the owned path set or re-run the trial merge so unrelated base work does not manufacture a failure.
GitHub-side duplicate/superseded PR handling belongs to the `github-ops` skill.

**For a convergence PR specifically — one whose whole job is absorbing several old branches'
content into a single keeper commit — prefer a merge commit over a squash for landing it.** A
squash replaces every absorbed branch's own commits with one new-SHA commit, breaking ordinary
ancestry for each of them (the effect this document's opening section describes at branch scale, now
multiplied across every branch the convergence absorbed). A real merge commit keeps each absorbed
branch's original commits as ancestors of base: the hosting platform can then auto-detect and mark
each absorbed branch's own pull request (if it had one) as merged, and plain `git branch -d` — no
content check, no `-D`, no supersession ladder — succeeds for every one of them by ordinary
ancestry. The squash-vs-merge choice for the convergence PR's own content is unaffected; this is
specifically about *how the absorption itself lands*.

### 3. Preserve refs and dirty WIP through different channels

This section creates refs, objects, external backups, or hosted state. Run it only while the
exclusive writer window from Step 1 remains valid. If another writer resumes, stop before the next
mutation; the frozen evidence remains useful, but it does not authorize continuing.

Create a repository-external bundle containing only the branches/refs whose deletion is authorized,
then verify it. The bundle is the ref manifest: immediately before deletion run:

```bash
scripts/git_export_before_drop.sh \
  --branch <authorized-ref-1> --branch <authorized-ref-2> \
  --out <external-backup-dir>
scripts/git_export_before_drop.sh --verify-current <external-backup-dir>/branches.bundle
```

For an authorized linked worktree on a branch, export that branch. For an authorized detached HEAD,
create one collision-checked recovery ref pointing at the recorded HEAD, then export that ref:

```bash
git update-ref refs/recovery/<worktree-id> <recorded-head> 0000000000000000000000000000000000000000
scripts/git_export_before_drop.sh \
  --branch refs/recovery/<worktree-id> --out <external-backup-dir>
```

This pin is part of preserving the named retirement target; it does not authorize pinning other
danglers. Use `--all-refs` only for an explicitly authorized full-ref-topology operation. The
repository-wide loss audit is valid only when every worktree/ref/tag/stash/dangler it enumerates is
inside evidence scope, and the all-refs export only when every ref it captures is change-authorized.
Otherwise use the authorized checkout/ref's own status/HEAD/upstream checks plus targeted exports,
and make only a scoped-cleanup claim.

Bundles cannot preserve untracked bytes. Freeze an explicit dirty-path manifest, save tracked
changes as a binary diff, copy or tar the exact dirty/untracked paths outside the repository, then
extract to a fresh verification directory and byte-compare every declared path. Do not use stash,
a temporary clone, or a worktree as the backup mechanism.

If the new base now tracks a path that was untracked WIP at the first snapshot, it will collide
with checkout materialization. Move that exact path to the verified external backup, update the
clean base, then restore the saved bytes; it should naturally become a tracked modification. Never
drop it because "main now has a file with that name."

If another writer is active, leave the real HEAD/index/worktree, object store, refs, and hosted
branches unchanged and postpone both local convergence and PR publication. When the existing
coordination restores an exclusive window, restart at Step 1, update only paths proven clean, or
restore the complete verified WIP set after materializing the new base.

### 4. Re-freeze immediately before deletion

While retaining exclusive writer ownership, fetch again, re-query hosting branches/PRs, and
re-enumerate local refs. Compare the result with the
bundle heads. A new branch, changed tip, or late PR inside the change-authorized set is new evidence:
stop, classify its unique behavior, and rebuild the bundle. A newly discovered collaborator object
does not silently join that set; record it as inspect-only or excluded and rebuild only if the next
authorized destructive action could reach it. This is not an optional "final check"; it is the only
check that covers work created after the first audit.

Delete only refs whose current SHA still equals the verified snapshot. For remote branch deletion,
query the exact hosted ref one last time; then delete it through the normal push/API route and prune
stale local remote-tracking refs.

### 5. Prove the user-visible terminal state

If every local/hosted branch, associated PR head, and linked worktree path in the convergence set is
explicitly change-authorized, the task is complete only when all are independently true:

- the hosting service lists only the intended maintained branch;
- local `refs/heads/` contains only `main`, and `HEAD`, local `main`, and the refreshed
  `origin/main` resolve to the intended commit;
- `git worktree list --porcelain` registers only the primary worktree, and every authorized linked
  worktree path is absent;
- the index has no staged residue from the convergence;
- every pre-existing WIP path still byte-matches its frozen source/backup, even if Git now reports
  a different tracked/untracked classification;
- until separately authorized artifact retirement completes, the recovery bundle still verifies
  and lists the retired exact tips.

Tags, stashes, and dangling commits do not block a branch/worktree convergence claim unless the
Outcome contract separately names them as retirement targets; preserve or report them under their
own scope.

When collaborator resources are inspect-only or excluded, do not claim repository-wide one-main
convergence. Report **scoped completion** instead: the authorized refs/PRs are merged or retired,
the maintained main identities agree, and every excluded branch/worktree/PR is listed as untouched.
Those exclusions are not blockers and must not be deleted to make a count reach one. Counts and
checksums support these claims; they do not replace them.

### 6. Retire task-owned temporary recovery artifacts

Treat recovery-artifact retirement as a separate destructive phase after convergence, never as an
implied final line of the initial "one main" request. A verified bundle, diff, copied file, or
metadata archive is a temporary safety net only after the underlying payload is independently
accounted for; before that, it may be the sole surviving copy of the work.

Classify every exact artifact path recorded by this task before proposing cleanup:

| Payload status | Terminal action |
|---|---|
| Every ref, diff, copied byte, and metadata item is on the maintained survivor or proven intentionally superseded | Eligible for separately authorized retirement after stating that deletion removes this recovery route |
| Any content exists only in the backup | Keep it; the artifact is still the delivery copy, not temporary residue |
| Any content is unresolved, or one artifact mixes cleared and unresolved payloads | Keep the whole artifact; do not let the cleared entries authorize deletion of the unresolved ones |

Use the same evidence that cleared the source: trial-merge or the supersession ladder for refs;
blob/path comparison for committed content; byte hashes or symlink targets for copied dirty and
ignored paths; and the clone-retirement receipt for clone metadata. Re-run `git bundle verify` and
`git bundle list-heads` before retiring a bundle, then map every listed identity to its content
proof. Recoverability alone is not delivery evidence.

Obtain deletion authority for the exact files or one exact task-exclusive backup directory. Show
the paths, their classification, and the lost recovery route. Do not infer this authority from age,
inactivity, successful convergence, or authorization to delete the original refs/worktrees/clones.
Do not sweep a machine-wide backup root, delete a parent that may contain another task's material,
or create a persistent registry of recovery artifacts. If an exact directory was not freshly
created for this task or its inventory does not match this task's recorded artifacts, authorize and
retire individual paths instead.

A Trash/quarantine move keeps the artifact at a new path; verify the old path is absent and the new
path is readable, but report that recovery material remains. Claim artifact retirement only after
an explicitly authorized permanent removal. Then perform a separate filesystem readback for every
exact path, including the dangling-symlink case:

```bash
: "${ARTIFACT_PATH:?set one exact authorized artifact path}"
if [ -e "$ARTIFACT_PATH" ] || [ -L "$ARTIFACT_PATH" ]; then
  printf 'STILL_PRESENT %s\n' "$ARTIFACT_PATH" >&2
  exit 1
fi
printf 'ABSENT %s\n' "$ARTIFACT_PATH"
```

The lifecycle has two valid terminal states: a verified recovery set remains available, or every
separately authorized temporary artifact has been retired and independently proven absent. Never
report the second state when backup-only or unresolved work remains.

## Independent clone retirement — preserve refs, metadata, and borrowed objects

An independent clone is not a linked worktree. Git has no registry connecting it to the checkout
you intend to keep, so `git worktree list`, the survivor's branch inventory, and the survivor's
loss audit cannot prove that deleting it is safe. A clean `git status` covers only one layer; the
clone can still be the sole owner of a ref name, reflog-only commit, stash, ignored file, hook, or
repository-local configuration.

`git clone --shared` adds one more asymmetry: the clone starts with no objects of its own and reads
the source through `.git/objects/info/alternates`. Git's official `git-clone` documentation calls
this potentially dangerous because source-side maintenance can prune borrowed objects and corrupt
the clone; `git repack -a` is the documented way to break that dependency when the clone will be
kept. For retirement, an empty local object directory is therefore **not** evidence that the clone
contains nothing — its refs remain unique state even while their objects live elsewhere.

Use this READ-DO sequence for one explicitly authorized clone:

1. **Name the survivor, clone, and external backup directory.** The backup must be a fresh absolute
   path outside both repositories; reusing an existing directory can mix two audits while looking
   valid. Confirm the clone has a `.git` directory. A `.git` file is a linked worktree and belongs
   to the worktree-retirement procedure below.
2. **Prepare the recovery set:**

   ```bash
   scripts/git_prepare_clone_retirement.sh \
     --clone <absolute-clone> \
     --survivor <absolute-kept-checkout> \
     --out <new-external-backup-dir>
   ```

   The helper is intentionally non-destructive. It refuses tracked/untracked changes, ignored
   physical files, stashes, reflog commits with no current ref, shallow history, every clone-only
   unreachable object reported by `git fsck`, partial/promisor clones, any attached linked worktree,
   local submodule repositories, and known clone-private Git LFS/annex object stores that require
   their own audit. The promisor check happens before object traversal and the helper exports
   `GIT_NO_LAZY_FETCH=1`, so bundle creation cannot silently hydrate missing objects into the clone
   it promised not to mutate. A repository using another extension-managed object store must name
   and audit that store separately; a core Git bundle cannot prove those bytes exist elsewhere. The
   helper also refuses tracked content filters, repository-local `include.path` / `includeIf`
   config, and local `core.hooksPath` overrides rather than pretending their external processes or
   closure were archived. Every Git call disables repository `core.fsmonitor`, untracked-cache
   refresh, and optional locks. It snapshots every ref tip, every symbolic-ref target, every reflog
   OID, and the default config/hooks/info tree with file types and modes; creates `all-refs.bundle`
   without revision exclusions; runs `git bundle verify`; compares every advertised bundle head
   (including `HEAD`) with the frozen ref set; and binds both the bundle and repository-metadata
   archive to SHA-256 receipts.
   The regression suite also verifies the no-prerequisite bundle from an empty bare repository. A
   successful `READY_TO_QUARANTINE` means the recovery set is
   complete for that instant, not that deletion authority exists.

   A bundle records the OID advertised under each ref name; it does not recreate symbolic-ref
   topology. `symrefs.manifest` is therefore part of the recovery contract. After fetching the
   bundle's refs into a recovery repository, replay each `<name> <target>` line with
   `git symbolic-ref <name> <target>`, then read every target back. A bundle-only restore that turns
   `refs/remotes/origin/HEAD` or another symbolic alias into a direct ref is not complete.
3. **Obtain current-session retirement authority.** A prior cleanup request or a different clone's
   approval does not transfer. Prefer a recoverable OS Trash/quarantine move; permanent deletion
   is a distinct consequence and requires an explicit decision plus the verified bundle.
4. **Freeze the quarantine target, then run process occupancy as a separate probe.** Resolve one
   absolute, unique quarantine/OS Trash destination, prove it does not exist, and select a
   no-clobber move form now. Do not target the clone's parent unless a separate inventory proves
   that parent contains nothing else. Then finish every preliminary Git command.
   On macOS, `/usr/sbin/lsof +D <absolute-clone>` is one available probe; use the platform-native
   equivalent elsewhere. A process result gathered in parallel with another Git probe can be the
   auditor observing its own sibling process, so it cannot authorize a move. Any genuine writer or
   unknown occupant stops the retirement. This `lsof +D` occupancy probe is the third of the
   Skill's three `lsof` uses — the shared-file writer probe in `references/prevention_practices.md`
   and SKILL.md's retirement occupancy check are the others — and all three stop on any genuine
   writer or unknown occupant; change the criterion in one, change it in the others.
5. **Re-freeze, then make the quarantine move the next operation:**

   ```bash
   scripts/git_prepare_clone_retirement.sh --verify-current <external-backup-dir>
   ```

   It fails if refs, reflog identities, metadata bytes/types/modes, physical state, linked-worktree
   or submodule inventory, symbolic-ref topology, unreachable objects, promisor/extension-store
   state, bundle bytes, or source/survivor identity changed. Rebuild the recovery directory on any
   failure; do not edit the receipt. After a successful final verification, move exactly one clone
   to the already-frozen destination with the selected no-clobber form. Do not recheck the
   destination first; the move itself must refuse a race-created destination. This move must be the
   next operation: another probe would
   reopen the very race the final verification closes. No unlocked filesystem sequence can remove
   the last verify-exit-to-move interval; if a writer or automation may still start in that interval,
   stop instead of claiming safety. Treat postconditions—not `mv`'s exit code—as authority: the old
   path must be absent and the quarantine path must contain the clone's `.git` directory. Do not
   target the clone's parent unless a separate inventory proves that parent contains nothing else.
   Keep the external recovery set after the move. Retire it later only through § Retire task-owned
   temporary recovery artifacts; moving the clone does not itself clear the archive's payload.
6. **Verify the user-visible result.** The survivor's HEAD/index/worktree must be unchanged; the
   old active path is absent; the quarantine copy or permanent backup is readable; `git bundle
   verify` still succeeds; `git bundle list-heads` still lists the frozen identities; and
   `symrefs.manifest` remains available for topology replay. Report this as scoped clone retirement,
   not as proof that no other checkout exists anywhere.

If the clone must remain active instead of being retired, stop this procedure. For a shared clone,
use the official dissociation path (`git repack -a`) and verify it no longer depends on alternates;
that is a different outcome from clone retirement and should not be smuggled into cleanup.

## Worktree retirement — prove the checkout is disposable before removal

A linked worktree is both a checkout and a ref boundary. A clean branch elsewhere does not prove
the worktree itself has no uncommitted files, and a detached worktree HEAD is absent from ordinary
`--branches` checks. Retire one only after this sequence:

1. **Inventory and identify the primary checkout:** run `git worktree list --porcelain`. Keep the
   first/primary checkout; select only the exact linked path the user intends to retire. A Git
   worktree lock prevents pruning, moving, and deletion; it is not an ownership lease or deletion
   authority. If its reason says the worktree is active, or the user assigns it to another worker,
   stop before inspecting its contents and do not unlock it as a workaround.
2. **Inspect tracked and untracked state in the linked checkout itself:** run
   `git -C <worktree-path> status --porcelain=v1 --untracked-files=all`. The output must be
   empty. Do not substitute the primary checkout's status.
3. **Inventory ignored physical files separately:** run
   `git -C <worktree-path> status --porcelain=v1 --ignored --untracked-files=all` and inspect every
   `!!` path. A normal clean status ignores this layer. So does `git worktree remove` itself —
   measured: it does not stop for an ignored file or warn about it, it deletes the file along with
   the directory. Bundle/archive/format-patch cannot reach this layer either. Freeze the complete
   ignored inventory before removal: expand ignored directories to leaf entries and record every
   relative path and entry type, including items classified as disposable. Judge that inventory by
   its total entry count and total byte size, not by naming only the paths that look sensitive or
   important. Real case: a retirement pass that named 22 paths (a few credentials and plan files)
   missed that the actual `!!` set was 8092 entries and roughly 200MB, including 13 build-output
   directories that existed only in that worktree. For every regular leaf, record
   `git hash-object --no-filters -- <path>`; for every symlink, record its `readlink` output. Stop on
   an unsupported special-file type. An entry is disposable on one of two grounds only: the primary
   checkout has the same relative path with byte-identical content (the same `git hash-object`
   output), or a named tool rebuilds it from tracked inputs alone (dependency caches, bytecode,
   virtualenvs, provider plugins). "Looks like build output" is not a ground — that is what those
   13 directories looked like, and each held a per-build environment file that nothing outside the
   worktree could regenerate. Copy everything else — different content, no matching path in the
   primary checkout, or otherwise user-authored or uncertain — outside the worktree first with `cp -p`,
   preserving its relative path under the backup; hash, never read or print, a path that may hold a
   credential. Run the same hash/readlink check on each source and backup copy and require equality.
   Use `git check-ignore -v <path>` when the ignore rule itself is unclear.
4. **Record the exact identity:** copy `git -C <worktree-path> rev-parse HEAD` and
   `git -C <worktree-path> branch --show-current`. An empty branch means detached HEAD, not "no
   work". Confirm the recorded HEAD resolves as a commit; when a branch is present, require that
   branch to resolve to the same SHA. The targeted bundle in step 6 preserves this exact identity.
5. **Prove containment against a fresh base:** fetch the maintained repository, then run
   `scripts/git_verify_branch_merged.sh <recorded-head> <base>`. An
   ancestor/content-contained verdict proves the committed state is on the base; NEEDS REVIEW
   requires manual supersession triage or preserving the commit under a branch/ref.
6. **Back up before deletion:** export the worktree's named branch with `--branch`. For a detached
   HEAD, create one collision-checked `refs/recovery/<worktree-id>` ref at the recorded HEAD and
   export that ref. Verify the targeted bundle; do not pin unrelated danglers or use `--all-refs`
   unless the Outcome contract separately authorizes every captured ref. Keep any ignored-file
   copies from step 3 beside this backup—the bundle does not contain them.
7. **Obtain current-session deletion authority, then remove through Git without force:** run
   the tracked/untracked status check again. Then re-run the exact ignored-inventory command from
   step 3, expand directories the same way, and rebuild the ignored manifest. Its path set, entry
   types, regular-file hashes, and symlink targets must exactly equal the frozen step 3 manifest;
   any added or missing path, type change, content change, or link-target change aborts removal.
   Also require every preserved source and backup copy to match that manifest. Make
   `git worktree remove <absolute-worktree-path>` the next operation—no intervening command may
   reopen the race. Never use `rm -rf` or
   `git worktree remove --force` to make a dirty/uninspectable worktree disappear.
8. **Verify the postconditions independently:** re-run `git worktree list --porcelain`, prove the
   exact path no longer exists, resolve the kept local branch if one exists, and re-run the
   recorded-HEAD containment check (or locate that HEAD in the verified bundle). These observations
   distinguish "checkout removed, history preserved" from a partial cleanup. Re-hash every copied
   ignored file at its backup-relative path and compare it with the pre-removal manifest; merely
   seeing a destination file is not an integrity check.
9. **Retire its branch separately:** prefer `git branch -d <branch>`. Worktree-removal authority
   does not authorize branch deletion. If Git refuses after a
   proven squash/supersession case, require the verified backup and explicit deletion authority
   before `-D`. A worktree removal does not itself prove a remote branch may be deleted.

The recovery artifacts created in step 6 may later follow § Retire task-owned temporary recovery
artifacts. A copied ignored path that exists only in that backup keeps the artifact ineligible.

## Adversarial multi-agent verification (for a whole repo of branches)

A single reviewer scanning a dozen branches reliably misses one real gap (it happened in the
session this skill was distilled from: a solo pass mis-judged a genuine 2-line fix as "already
merged" by matching the wrong call site; a fan-out of independent agents caught it). For a
high-stakes "is *everything* merged?" verdict, fan out:

1. **Partition** the branches across N agents (e.g. large feature-adding branches, small fix
   branches, local-only-history branches, plus one agent that independently re-runs the loss
   check and re-derives the "should this old branch be merged?" verdict from content).
2. **Frame each agent adversarially**: "Default to the assumption that these branches still have
   unmerged unique content, and try to *prove* it. Judge by content (the trial-merge check above),
   never by commit count. Report per branch: MERGED / **UNMERGED / NEEDS REVIEW (with the file(s)
   the trial merge would change)**."
3. **Lock them read-only** (see rules below) so concurrent agents don't corrupt each other's tree.
   The sole writer refreshes authority first and hands them frozen SHAs; reviewers never fetch.
4. **Counter-review every finding yourself.** An agent's "UNMERGED" is a *hypothesis*: re-run the
   trial-merge / inspect the specific files before believing it (agents produce false positives
   too). An agent's "all merged" is only as good as its method — spot-check that it judged by
   content, not counts.
5. **Converge**: everything merged across all agents = strong confirmation; any single
   content-backed UNMERGED finding = a real gap to land.

This is inline orchestration (the skill spawns the agents), so `git-safety-net` must run inline —
a subagent cannot spawn subagents.

## Rules for the verification agents

Put these in every agent's prompt — they are what make parallel verification safe and correct:

- **Read-only, always.** Only `merge-base`, `merge-tree`, `diff`, `log`, `show`, `cat-file`,
  `rev-list`, `rev-parse`, `ls-tree`, `for-each-ref`, `branch -r --contains`. **Never** `fetch`,
  `checkout`, `switch`, `reset`, `rebase`, `commit`, `push`, `update-ref`, or `gc`. The sole writer
  refreshes once before fan-out and supplies immutable SHAs; a reviewer does not move even a
  remote-tracking ref.
- **Explicit frozen SHAs first.** Use the supplied immutable object IDs for conclusions. Named refs
  (`origin/main`, `origin/<branch>`) may be displayed for attribution but are not merge authority.
- **Judge by content via the trial merge, not by counts** — restate the check in the prompt.
- **Return structured per-branch verdicts with the file(s) the trial merge would change for any
  UNMERGED**, not prose.
