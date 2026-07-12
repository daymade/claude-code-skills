# Git safety gates

## Contents

- Inspect before mutation
- Routine synchronization
- Commit scope
- Push safety
- Conflict handling
- Hook bypass
- Secret or PII history cleanup

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
2. If the working tree is clean, run git pull --ff-only.
3. If local changes exist, do not auto-stash or pull; report the changed paths.
4. If histories diverged, show the graph and ask how the local commits should be
   handled. Do not choose merge/rebase/force by habit.
5. On network failure, distinguish "remote not checked" from "already current".

git pull --ff-only only accepts a fast-forward update. Automatic stash/pop is a
separate operation and can create non-trivial conflicts.

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
