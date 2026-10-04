---
name: multi-account-repository-sync
description: >-
  Copy a repository accessible to a secondary GitHub account into the usual
  account's private repository and synchronize upstream without switching the
  default login. Read for multi-account SSH, private copies and upstream sync.
---

# Multi-account repository copy and upstream sync

Resolve whether the requested result is a local clone or a separately hosted
private copy. Keep advice read-only; execute setup when authorized. Reuse the
user's stated owner and visibility instead of asking again. Use an independent
private repository when the destination account lacks upstream access; do not
assume that account can create or access a private fork.

## Bind each account to its own interface

Probe the default CLI account, existing SSH config and destination paths. Use the
main Skill's checked invocation for hosted writes; verify Git authentication
separately. Keep the usual `gh` account active.

Reuse an already logged-in browser for the upstream account when available.
Enter the host's browser Skill and use a task-owned tab. Verify the exact login
and access to every named source before adding a key. If the observed login
differs from the user's spelling, report it and proceed only when the user has
identified that logged-in account as the target. Do not export browser cookies
into CLI credentials or switch the default account merely to clone.

Reuse an account-specific SSH key. If none exists and credential setup is
authorized, generate a new key at an unused path and add only its public key to
the verified upstream account. Preserve existing keys and their protection.
Hand off only an essential login, MFA or trusted credential prompt; re-probe
the same account afterward and continue from the first unmet prerequisite.

Configure an SSH alias such as `github-upstream`. Inspect the ordinary host's
resolved hostname, port and proxy settings, and reuse the working transport.
The following example assumes GitHub's normal SSH endpoint:

```sshconfig
Host github-upstream
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_upstream
    IdentitiesOnly yes
```

Inspect matching `Host`, `Match` and `Include` entries first. `IdentityFile`
directives accumulate; `IdentitiesOnly yes` still permits all configured keys.
Exclude this alias from any generic identity stanza, for example
`Host * !github-upstream`, while preserving other shared defaults. Back up the
config and compare before/after resolution with the same `ssh -F CONFIG -G HOST`
loading mode; `-F` changes whether system configuration is read.

```bash
ssh -G github-upstream
ssh -T git@github-upstream
ssh -T git@github.com
```

Require the intended login in each greeting. GitHub's successful `ssh -T` test
exits 1 because it provides no shell; the greeting decides authentication.
Then read every source with `git ls-remote`: a valid account greeting alone does
not establish repository permission. Stop before writes on an unknown or wrong actor.

## Create and import the private copy

Use existing Git and `gh`; the command templates below use a POSIX shell.
Resolve `COPY_LOGIN`, `COPY_OWNER`, `SOURCE_OWNER`, `REPO`, `DEFAULT_BRANCH`,
`<github-ops-dir>` and `<destination>` from the task. Discover the default branch
from the source rather than assuming `main`. Quote substituted shell arguments.

For a local-only request, clone through the upstream alias and stop after a
successful fetch/readback; do not create a hosted copy. For a hosted copy,
create an **empty, private** destination with the explicit owner. On an existing
local or remote path, inspect and resume only a verified same-task setup;
do not overwrite, recreate or absorb unrelated contents.

```bash
uv run python <github-ops-dir>/scripts/checked_gh.py --expected-login COPY_LOGIN --host github.com -- repo create COPY_OWNER/REPO --private
gh repo view COPY_OWNER/REPO --json nameWithOwner,isPrivate,visibility,stargazerCount,forkCount,url
git clone --origin upstream git@github-upstream:SOURCE_OWNER/REPO.git <destination>
git -C <destination> remote add origin git@github.com:COPY_OWNER/REPO.git
git -C <destination> ls-remote origin
git -C <destination> ls-remote --heads --tags upstream
```

Require positive private-visibility readback. Require a successful, empty
`ls-remote origin` before an initial import; an error is unknown, not empty.
The `origin` example assumes ordinary GitHub SSH authenticates as `COPY_LOGIN`.
Preserve HTTPS when it is the working destination transport; bind its account
instead of introducing an unverified SSH path.

Inspect source workflows before the first push. When the new copy is requested
only for code/history, state the reversible default of disabling Actions before
importing deployment workflows. Keep workflow files unchanged. Preserve requested
CI behavior and existing repositories' policy. For that identified new copy:

```bash
uv run python <github-ops-dir>/scripts/checked_gh.py --expected-login COPY_LOGIN --host github.com -- api --method PUT repos/COPY_OWNER/REPO/actions/permissions -F enabled=false
gh api -X GET repos/COPY_OWNER/REPO/actions/permissions --jq '.enabled'
```

Require `false` before import. Restore with `enabled=true` through the same
endpoint when requested; retain other policy fields when changing existing policy.

Enumerate source branches and tags. A normal clone stores extra branches under
`refs/remotes/upstream/`; `git push --all` copies only local branches. Build explicit
non-forcing refspecs for the requested branches, excluding symbolic `upstream/HEAD`.
For a source with the selected branch and an observed additional `develop`:

```bash
git -C <destination> push --atomic origin refs/remotes/upstream/DEFAULT_BRANCH:refs/heads/DEFAULT_BRANCH refs/remotes/upstream/develop:refs/heads/develop
git -C <destination> push origin --tags
git -C <destination> fetch origin
git -C <destination> branch --set-upstream-to=origin/DEFAULT_BRANCH DEFAULT_BRANCH
git -C <destination> config --local remote.pushDefault origin
```

Omit `develop` unless present; include every branch in the requested copy scope.
Check LFS and submodules when present: refs do not transport their external objects.
Git copies preserve history, not issues, release assets, secrets or repository settings.
Avoid `push --mirror` for routine sync; it can overwrite or delete destination refs.

For pull-only upstream use, optionally set its local `pushurl` to
`disabled://upstream-read-only` and disclose the safeguard. It blocks local
`git push upstream`, not the account's GitHub permissions. Remove the override
when an authorized upstream contribution requires that push path.

## Install and run a convenient sync command

Keep the local branch tracking `origin` and default pushes targeting `origin`.
Use Git's repository-local alias rather than another account-switching tool or
periodic service. Set the discovered branch as data, not interpolated shell code:

```bash
git -C <destination> config --local githubSync.branch DEFAULT_BRANCH
git -C <destination> config --local alias.sync-upstream '!f() {
  expected=$(git config --get githubSync.branch) || return 1
  [ -n "$expected" ] || { echo "Missing sync branch" >&2; return 1; }
  actual=$(git symbolic-ref --quiet --short HEAD) || return 1
  [ "$actual" = "$expected" ] || { echo "Switch to $expected first" >&2; return 1; }
  state=$(git status --porcelain=v1 --untracked-files=all) || return 1
  [ -z "$state" ] || { echo "Commit or preserve local work first" >&2; return 1; }
  git fetch upstream --prune --tags &&
  git merge --ff-only "refs/remotes/upstream/$expected" &&
  git push origin "refs/heads/$expected:refs/heads/$expected" &&
  git push origin --tags
}; f'
git -C <destination> sync-upstream
```

Run the command in each actual destination. Verify the dirty-worktree stop with
a task-owned untracked file, then remove only that probe and confirm a clean tree.
Missing configuration, detached/wrong branch or failed status must stop before
network writes. Chain dependent operations so a failed fetch, merge or push stops
the sequence. On divergent local commits, preserve work and report the integration
decision; do not reset, force-push or rebase to manufacture a successful sync.
Use `git-safety-net` when existing work needs preservation or recovery.

Name the scope: this command updates the selected branch and tags, and fetches
other upstream branches locally. It does not mirror all destination branches.
An all-branch sync needs a ref-by-ref plan preserving destination-only work.
Stop on conflicting tags rather than forcing replacement. Continued upstream
access still depends on the upstream account's permission.

## Resume and accept the result

After interruption, inspect the existing key/alias, live private destination,
hosted refs, local remotes, branch tracking and worktree state. Reuse completed
steps. After an ambiguous create or key-add receipt, read the exact repository
or key fingerprint before retrying. Re-probe identities after a manual handoff.

Complete only when the default account remains active, each source is readable
through its selected account, every requested branch/tag matches fresh hosted
destination refs, and the real sync command succeeds. For an unchanged copy,
confirm local HEAD equals the selected upstream and destination tips and the
checkout is clean and tracks `origin`. For destination-only commits, verify
upstream containment instead of demanding SHA equality. Report uncopied LFS or
submodule objects and metadata outside the Git-copy scope.

## Authority

- [GitHub multi-account authentication](https://docs.github.com/en/account-and-profile/how-tos/account-management/managing-multiple-accounts)
- [OpenSSH config loading and IdentityFile](https://man.openbsd.org/ssh_config)
- [GitHub SSH connection test](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection)
- [GitHub repository duplication](https://docs.github.com/en/repositories/creating-and-managing-repositories/duplicating-a-repository)
- [Git push refspecs and mirror behavior](https://git-scm.com/docs/git-push)
- [GitHub Actions permission endpoint](https://docs.github.com/en/rest/actions/permissions#set-github-actions-permissions-for-a-repository)
