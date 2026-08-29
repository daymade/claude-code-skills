# Repository Operations

Use this reference to inspect, clone, create, edit, rename, archive, transfer, change visibility,
or delete a repository. All hosted writes follow the authorization, impact-preview, recovery, and
independent-readback contract in [`../SKILL.md`](../SKILL.md).

## Contents

- Inspect a repository
- Clone into a safe local destination
- Create with explicit owner and visibility
- Edit, rename, archive, and change visibility
- Transfer ownership
- Delete and recover
- Terminal evidence

## Inspect a repository

Resolve the exact hosted target and the active account before deciding whether a write is needed:

```bash
gh auth status --hostname github.com
gh api user --jq '.login'
gh repo view OWNER/REPO \
  --json nameWithOwner,visibility,isPrivate,isArchived,defaultBranchRef,viewerPermission,url
```

Use `HOST/OWNER/REPO` and `--hostname HOST` for another GitHub host. A local remote name or current
directory is not sufficient authority for a consequential hosted change.

## Clone into a safe local destination

Cloning is read-only on GitHub but writes locally. Resolve a destination that does not already
exist; do not let a clone overlay another checkout or untracked work.

```bash
destination='./repo-copy'
test ! -e "$destination" || {
  printf 'Destination already exists: %s\n' "$destination" >&2
  exit 1
}

gh repo clone OWNER/REPO "$destination"
git -C "$destination" remote get-url origin
git -C "$destination" status --short --branch
```

If the request involves replacing, retiring, or consolidating an existing clone, stop and use
`git-safety-net`; a successful new clone does not prove the old checkout is safe to remove.

## Create with explicit owner and visibility

Repository creation requires an exact `OWNER/REPO` and an explicit visibility decision. Do not
infer `public` from an example or infer the owner from the active account.

```bash
# Set only from the authorized decision: private, internal, or public.
visibility='private'
case "$visibility" in
  private|internal|public) ;;
  *) printf 'Invalid visibility: %s\n' "$visibility" >&2; exit 1 ;;
esac

gh repo create OWNER/REPO "--$visibility"
gh repo view OWNER/REPO --json nameWithOwner,visibility,isPrivate,url
```

`internal` is available only where the owning organization/enterprise supports it. If the new
repository will receive an existing local repository, create the remote without pushing, verify
the live visibility, and only then publish the intended branch:

```bash
visibility='private'
branch='main'
gh repo create OWNER/REPO "--$visibility" --source=. --remote=origin
gh repo view OWNER/REPO --json nameWithOwner,visibility,isPrivate,url
git push -u origin "$branch"
```

If creation times out or returns a 5xx, query `OWNER/REPO` before retrying. A blind retry can target
an already-created repository with different follow-up behavior.

## Edit, rename, archive, and change visibility

Use a fully qualified repository and read back the exact fields changed:

```bash
gh repo edit OWNER/REPO --description 'Repository description'
gh repo view OWNER/REPO --json nameWithOwner,description,url

gh repo rename NEW_NAME --repo OWNER/REPO
gh repo view OWNER/NEW_NAME --json nameWithOwner,url

gh repo archive OWNER/REPO
gh repo view OWNER/REPO --json nameWithOwner,isArchived,url
```

Changing visibility can expose or detach code, forks, Actions logs, artifacts, Pages, rulesets,
stars, and watchers. Record the current visibility and affected surfaces before the write. Use the
required consequence acknowledgement only after the user authorized that exact transition:

```bash
gh repo edit OWNER/REPO \
  --visibility public \
  --accept-visibility-change-consequences
gh repo view OWNER/REPO --json nameWithOwner,visibility,isPrivate,url
```

Replace `public` only with the explicitly requested visibility. Reverting visibility does not
necessarily reconstruct fork networks, rulesets, or other effects of the first transition.

## Transfer ownership

A transfer changes who administers repository content, issues, PRs, releases, projects, settings,
and policy. Before sending it, verify:

- the target owner and optional new name;
- permission to create the repository at the target;
- no conflicting repository or fork at the target;
- plan-dependent features, Pages/DNS, Actions, packages, collaborators, teams, and secrets that
  can change or require reconfiguration; and
- whether the old owner/name combination can be reused.

The REST transfer is asynchronous:

```bash
gh api -X POST repos/OWNER/REPO/transfer \
  -f new_owner=NEW_OWNER \
  -f new_name=NEW_NAME

gh api repos/NEW_OWNER/NEW_NAME \
  --jq '{full_name,visibility,archived,default_branch,html_url}'
```

A `202 Accepted` is pending, not complete. Poll the new fully qualified name with a bounded deadline,
then re-audit collaborators, team access, branch protection/rulesets, Actions, Pages, packages, and
secrets required by the workload. Recovery is another transfer and can be blocked by name, policy,
plan, or fork-network state; do not describe it as a guaranteed inverse.

## Delete and recover

Deletion is destructive. Verify the exact repository, visibility, forks, and active integrations;
record what must survive outside GitHub. If independent content recovery is required, complete and
verify that backup before deletion. Local Git preservation belongs to `git-safety-net`; issues,
projects, packages, release assets, Actions artifacts, Pages/DNS, team permissions, and other hosted
surfaces require their own export or migration decision.

```bash
gh repo view OWNER/REPO \
  --json nameWithOwner,visibility,isPrivate,isArchived,defaultBranchRef,forkCount,url

# Keep the interactive exact-name confirmation. Do not add --yes by default.
gh repo delete OWNER/REPO

gh repo list OWNER --limit 1000 --json nameWithOwner \
  --jq '.[] | select(.nameWithOwner == "OWNER/REPO")'
```

The final query must return no matching repository under an account whose identity and access were
already verified. A standalone `404` is ambiguous. GitHub can restore some deleted repositories
within its documented window, but fork-network constraints apply and restored repositories do not
automatically recover team permissions. Treat the **Deleted repositories** settings page as a
possible recovery path, not the only backup or a guarantee.

## Terminal evidence

A repository operation is complete only when:

- account, host, and fully qualified repository were verified;
- owner, visibility, public/destructive consequence, and recovery were explicit;
- clone/create/edit/rename/archive/transfer/delete used the intended object exactly once;
- the new hosted path and requested fields were independently read back;
- local push/clone state was verified separately from hosted state; and
- pending transfer, invitation, policy, fork, Pages, Actions, secret, or recovery obligations remain
  visible rather than being collapsed into “done.”
