# Git safety gates

## Inspect before mutation

Before pull, commit, merge, rebase, push, or history rewrite, record:

~~~bash
git status --short --branch
git remote -v
git log --oneline --decorate -5
~~~

Use the hosting service as the authority for visibility and permissions. A remote
URL, directory name, or previous report does not prove those properties.

## Isolated checkout preparation

Choose the storage lifetime before creating a clone or linked worktree. For work
that must survive a pause, restart or later session, place the checkout and its
continuation evidence under a persistent task directory in the user's workspace,
outside system temporary roots and automatic cleanup targets. Resolve the actual
parent path; a name such as `worktree` does not establish persistence. Do not use
`/tmp`, `/private/tmp`, `TMPDIR` or a default `mktemp -d` destination as the only
copy of source edits, review evidence or recovery instructions needed to resume.
Keep such evidence until publication and the task's authorized retirement checks
finish. Use system temporary storage only for bounded scratch work whose loss is
acceptable and whose inputs and required evidence are retained elsewhere. If a
previous task directory is missing, recover from verified commits or retained
copies and report any unavailable uncommitted work or evidence as unknown.

Before the first mutation in a task copy, bind its origin and immutable starting
commit to the authorized repository. Read that repository's setup and hook owners;
an independent clone can have different local configuration even with identical
tracked files. Keep unrelated working-tree and index content outside the task.

- For Git LFS or custom storage, use the repository's declared setup and transfer
  adapter. A generic batch request failing does not establish that a referenced
  object is absent. If binary bytes are required, verify them through that owner.
  For a text-only task whose changed paths contain no binary changes, standard
  skip-smudge may retain pointers only when the applicable check accepts that
  representation; disclose that it did not inspect the underlying media.
- For security baselines, verify the guard's actual repository-identity lookup.
  A temporary directory name may select a different baseline. Use the guard
  owner's supported binding to the same repository's already-approved findings;
  do not introduce unrelated allowlists, suppress new findings, or bypass hooks.
- Read a failure's actual output before attributing it to the candidate. Separate
  missing environment setup, inherited findings and newly introduced defects.
  Existing full-tree security work remains separate from an added narrow check;
  preserve its result and any genuine blocker.

Finish preparation once the named task can use its normal guarded workflow.
Do not turn it into a whole-machine setup, new security policy or repeated
installation at every commit.

## Routine synchronization

1. Determine whether the ongoing task and project instructions already authorize
   synchronization. Treat a status question during that maintenance as a progress
   request, not as revocation or completion of the authorized sync. For an explicit
   read-only audit or when sync authority is absent, inspect and report only.
2. Verify that the current branch is the target branch with the intended upstream,
   check working-tree cleanliness, then fetch and compare the local and freshly
   fetched remote histories. Treat a behind count as a discovery, not a completed
   sync.
3. Check the gate in [Authorized shared-checkout delivery](#authorized-shared-checkout-delivery)
   when the task includes delivery, before treating dirty or divergent state as a stop.
4. Outside that gate, use repository-declared safe sync tools when applicable;
   otherwise, on the target branch with a clean working tree and behind-only
   histories, run git pull --ff-only.
5. Before reporting synchronized, independently verify the target branch, clean
   status, and local/remote commit equality.
6. Outside that gate, do not pull on a non-target branch or with real WIP; report
   the changed paths. Leave ahead-only or divergent local commits in place. For
   divergence, show the graph and ask how the local commits should be handled.
   Pause for locks or active-writer conflicts. Do not auto-stash, discard, rebase,
   create a non-fast-forward merge, force, or absorb others' commits.
7. On network failure, report the remote state as unknown rather than already
   current. Continue locally only when the user's task can safely proceed on the
   local version.

git pull --ff-only only accepts a fast-forward update. Automatic stash/pop is a
separate operation and can create non-trivial conflicts.

## Authorized shared-checkout delivery

Enter only when current user or project instructions already authorize the named
delivery stage, including any commit or push, and the repository declares usable
scoped tools that preserve unrelated shared HEAD, index, and WIP. Read their actual
contracts before use. This Skill supplies no such tools or additional permission;
missing authority or a usable scoped route leaves the conservative routine in effect.
The existing visibility, protection, conflict, and public-push gates still apply.

1. Bind the task's exact paths and a full immutable base commit. Use an isolated
   task checkout or the declared scoped tools; never absorb unrelated local commits.
2. Verify whether affected paths have an active writer, then coordinate once with
   a bounded deadline. On expiry, reassess the actual overlap or blocker; a new ETA
   alone does not restart the wait. Continue independently when the declared route
   preserves the other writer's work. Explicit objections to touching the affected
   target, overlapping edits, locks, or an unavailable safe route pause that part.
3. Commit only the owned task changes through the declared workflow. If a tool
   returns a notice or nonzero result, read its documented stage contract and
   independently inspect whether it created the commit or completed landing before
   retrying. Reuse an unchanged candidate; a concurrent-state notice alone is not
   a reason to rebuild it.
4. On remote-ref drift, refresh the immutable remote base and integrate only this
   task's isolated change through the authorized repository workflow, preserving
   both sides. Unresolved semantic conflicts or product choices remain blockers;
   do not force a ref, bypass a lock, or merge unrelated shared local history.
5. Publish the exact candidate through the normal repository workflow, then verify
   the hosted commit independently. Synchronize only known landed content through
   the declared safe route, preserving unrelated staged and unstaged work.
   Compare the task's exact paths in the published commit, current HEAD, index and
   actual consuming files; a successful write receipt alone does not prove delivery.
6. Retire only this task's temporary resources under the existing recovery rules
   (use git-safety-net for branch/worktree retirement) once containment is proven.
   Before final delivery, compare the original authorized outcome with the artifact
   and resource set. If necessary safe work remains, execute it; only a genuine
   dependency justifies returning an incomplete result and recovery condition.

Do not report the whole shared checkout as clean or synchronized based only on
the task's paths. A scoped delivery can finish while unrelated work remains.
If the original authorized outcome includes whole-repository convergence, verify
that result too. Otherwise do not expand scoped cleanup into unrelated work.

## Commit scope

- Review git diff and git diff --cached.
- Stage explicit paths, never git add . or git add -A in a shared worktree.
- Preserve pre-existing staged work that is outside the approved task.
- Verify the resulting commit and remaining working tree before reporting success.
- Follow the repository's commit-message and attribution policy; do not invent one.

## Commit-time checks

Use a Git pre-commit hook when the authorized outcome is automatic validation
of what any person or Agent is about to commit. Use an Agent lifecycle hook for
that runtime's tool/session behavior. Cheap deterministic checks with no hosted
environment requirement can run locally; retain CI or later checks where the
repository's integration, release or trust contract requires them.

1. Inspect the repository's existing check command, configured hooks path and
   effective pre-commit dispatcher. Reuse its installation and chaining protocol;
   preserve existing hooks and their failure propagation.
2. Make the check consume the index that Git will commit, including an explicit
   `GIT_INDEX_FILE` when the repository's workflow uses one. Working-tree files
   can differ from the staged content. Scope the added check to its relevant
   changed inputs; a narrow rule passing does not certify the whole artifact.
3. Connect installation through the existing repository setup or onboarding.
   Tracked hook files alone do not establish that a fresh clone runs them.
   Verify executable/runtime prerequisites and the actual consuming hook entry.
4. In an isolated fixture, stage a known-bad input and leave a corrected version
   unstaged: commit must still fail. Stage a known-good input and leave a bad
   version unstaged: the content check must accept the staged input, with the
   remaining hook chain still running. Preserve shared index and WIP.
5. Read the real hook's result and failure message. A new finding must identify
   the file and actionable correction; an unavailable check remains incomplete.

For different task types, keep the common hook entry and call their existing
checks rather than building a universal semantic checker. Stop once the required
automatic check is installed and the two staged-input controls work. Do not add
a dedicated hosted workflow, model call or broad audit without a demonstrated
requirement and authorization.

## Push safety

Before any push, query the hosting service for the repository's real visibility,
ownership, default branch, and protection state. For GitHub:

~~~bash
gh repo view <owner>/<repository> \
  --json visibility,isPrivate,stargazerCount,forkCount,defaultBranchRef
~~~

Then:

- public repository with downstream users: prefer a feature branch and PR;
- private/internal repository: push still needs the authority implied by the task;
- protected or external-owned branch: follow its contribution workflow;
- force push: require explicit approval for the exact ref and explain the impact.

Do not describe a repository as private/public until the API output confirms it.

## Conflict handling

1. Read git status and every conflict marker.
2. Explain what each side represents in project terms.
3. Resolve from current requirements and source-of-truth files.
4. Never select "ours" or "theirs" for all files as a generic fix.
5. Run the relevant tests and inspect the final diff before commit.

If the intended resolution depends on a business choice the repository cannot
answer, ask the user. Syntax conflicts that have one verified project-consistent
resolution do not need to be outsourced.

## Hook bypass

Never add --no-verify, --no-gpg-sign, or equivalent bypasses on your own.

- A hook failure is evidence to diagnose.
- Past authorization does not authorize a new bypass.
- Only an explicit user instruction for the current operation authorizes it.
- Fix a false positive in the rule or allowlist; do not make bypass the workflow.

## Secret or PII history cleanup

Treat this as an incident, not a routine setup option.

1. Revoke and rotate any exposed credential first.
2. Verify whether the material exists only locally or has reached remote refs,
   releases, caches, forks, or collaborators.
3. Create a recoverable backup and record the exact refs before rewriting.
4. Choose a maintained history-rewrite tool from current authoritative guidance.
5. Preview the rewrite in an isolated clone and verify the target content is gone
   while intended history remains.
6. Obtain explicit approval before replacing remote history.
7. Verify the remote and communicate the re-clone/rebase requirement to affected
   collaborators.

Do not include a ready-to-run force-push recipe in an ordinary setup flow. The
specific rewrite depends on exposure scope, collaboration state, and repository
policy.

For GitHub-focused cleanup, prefer a dedicated current workflow rather than
extending this general setup skill ad hoc.
