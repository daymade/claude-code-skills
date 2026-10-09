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

## Routine synchronization

1. Verify the current branch has the intended upstream.
2. Check the gate in [Authorized shared-checkout delivery](#authorized-shared-checkout-delivery)
   when the task includes delivery, before treating dirty or divergent state as a stop.
3. Outside that gate, if the working tree is clean, run git pull --ff-only.
4. If local changes exist, do not auto-stash or pull; report the changed paths.
5. If histories diverged, show the graph and ask how the local commits should be
   handled. Do not choose merge/rebase/force by habit.
6. On network failure, distinguish "remote not checked" from "already current".

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
6. Retire only this task's temporary resources under the existing recovery rules
   (use git-safety-net for branch/worktree retirement). Stop when the authorized
   stage has its delivery evidence; report any remaining blocker explicitly.

Do not report the whole shared checkout as clean or synchronized based only on
the task's paths. A scoped delivery can finish while unrelated work remains.

Before final delivery, compare the original user outcome with the owned artifact and
resource set. Releasing an index, sending a coordination message or merging a stage
does not finish remaining authorized closure: execute the next necessary safe action.
For landed content, compare the exact task paths in the published commit, current HEAD,
index and actual consuming files; retire the owned temporary resources once containment
is proven. Continuous unrelated WIP does not make a verified task artifact unfinished.
Whole-repository convergence belongs to its separately authorized scope; do not expand
a task's cleanup into that work or claim the whole checkout clean from scoped evidence.

## Commit scope

- Review git diff and git diff --cached.
- Stage explicit paths, never git add . or git add -A in a shared worktree.
- Preserve pre-existing staged work that is outside the approved task.
- Verify the resulting commit and remaining working tree before reporting success.
- Follow the repository's commit-message and attribution policy; do not invent one.

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
