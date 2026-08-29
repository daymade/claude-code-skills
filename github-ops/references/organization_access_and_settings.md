# Organization Access and Settings

Use this reference for organization membership, outside collaborators, direct or team
repository access, base permissions, member privileges, repository creation policy, and
organization-wide 2FA requirements.

## Contents

- Access model and least-privilege decision
- Read-only access audit
- Granting and revoking repository access
- Changing base permissions and repository-creation policy
- UI-only member privileges and silent API no-ops
- Requiring organization 2FA
- Verification and recovery

All writes follow the authorization, impact-preview, and independent-readback contract in
[`../SKILL.md`](../SKILL.md).

## Access model

Effective repository permission is the highest grant from repository, team,
organization base permission, organization ownership, or enterprise policy. GitHub's
effective-permission response does not identify which source supplied that highest role.
Diagnose access by combining the effective role with direct-collaborator, team, membership,
base-permission, and enterprise-policy evidence.

Choose the narrowest grant that meets the actual job:

- One repository, no organization-wide role: outside collaborator or explicit repository
  collaborator, subject to organization policy.
- A stable group that needs the same repositories: organization membership plus team access.
- Every organization repository: only use a non-`none` base permission when broad default
  access is the intended policy. Base permission changes affect existing and future members.
- Automation or publishing: prefer a GitHub App or narrowly scoped automation credential over
  a shared human account. Never copy another environment's credential as a fallback.

`none` base permission prevents ordinary members from receiving private-repository access only
because they joined the organization. It does not remove explicit repository/team grants,
owner access, enterprise grants, or the minimum read visibility of internal repositories.

## Read-only access audit

Bind `ORG`, `REPO`, and `USER` to exact slugs before running the queries.

```bash
gh auth status
gh api user --jq '.login'

gh api "orgs/ORG" --jq '{
  login,
  default_repository_permission,
  members_can_create_repositories,
  members_can_create_public_repositories,
  members_can_create_private_repositories,
  members_can_create_internal_repositories,
  members_can_delete_repositories,
  members_can_change_repo_visibility,
  two_factor_requirement_enabled
}'

gh api -X GET "orgs/ORG/members/USER"
gh api "repos/ORG/REPO/collaborators/USER/permission" \
  --jq '{permission,role_name,user:.user.login}'

gh api -X GET 'repos/ORG/REPO/collaborators?affiliation=direct&per_page=100' \
  --paginate --jq '.[] | {login,role_name}'

gh api -X GET 'repos/ORG/REPO/teams?per_page=100' --paginate \
  --jq '.[] | {slug,permission}'
```

Interpret absence carefully:

- `GET /orgs/ORG/members/USER` returning `204` proves organization membership; `404` does
  not distinguish every possible access path.
- `collaborators/USER/permission` is effective access, not grant provenance.
- `affiliation=direct` surfaces explicit repository collaborators; it does not replace the
  effective-permission query.
- A direct collaborator removal can leave access intact through base permission, team,
  ownership, or enterprise policy.

## Grant repository access

Before adding someone, record the current membership, direct access, effective role, and
whether an invitation is already pending. Then grant the minimum role required:

```bash
gh api -X PUT "repos/ORG/REPO/collaborators/USER" -f permission=pull
```

GitHub may return `201` for a new invitation or `204` when an existing collaborator/member is
granted direct access. A `201` does not prove access is active. Read the repository invitations,
then verify effective permission after acceptance:

```bash
gh api -X GET 'repos/ORG/REPO/invitations?per_page=100' --paginate \
  --jq '.[] | {id,invitee:.invitee.login,permissions,html_url}'
gh api "repos/ORG/REPO/collaborators/USER/permission" \
  --jq '{permission,role_name,user:.user.login}'
```

Do not accept the invitation on another person's behalf unless the current task explicitly
authorizes acting as that account.

For team-based access, first verify the user belongs to the intended team and the team is the
correct policy unit. Use GitHub's current team-repository endpoint or the organization UI, then
read back both team repository access and the user's effective permission.

## Revoke repository access

Record the direct role before removal so it can be restored. Deleting a direct collaborator is
not a complete revocation when another grant remains:

```bash
gh api -X DELETE "repos/ORG/REPO/collaborators/USER"

gh api -X GET 'repos/ORG/REPO/collaborators?affiliation=direct&per_page=100' \
  --paginate --jq '.[].login'
gh api "repos/ORG/REPO/collaborators/USER/permission" \
  --jq '{permission,role_name,user:.user.login}'
```

The effective-permission query may return `404` when no access remains. If it still returns a
role, inspect base permission, teams, ownership, and enterprise policy before claiming access was
revoked. Removing a collaborator can also affect invitations, assignments, packages, projects,
and private forks; preview these consequences and preserve the prior role for recovery.

## Base permissions and repository creation

The documented `PATCH /orgs/{org}` input contract supports base permission and repository-
creation controls. Re-read the current official input schema before each automation because
GitHub versions its REST API.

Example bounded change:

```bash
gh api -X PATCH "orgs/ORG" \
  -f default_repository_permission=none \
  -F members_can_create_repositories=false \
  -F members_can_create_public_repositories=false \
  -F members_can_create_private_repositories=false

gh api "orgs/ORG" --jq '{
  default_repository_permission,
  members_can_create_repositories,
  members_can_create_public_repositories,
  members_can_create_private_repositories
}'
```

Do not combine unrelated organization settings in one PATCH. A smaller request makes a silent
no-op attributable and recovery exact. Before changing base permission, enumerate current members
and explain that the change applies to existing and future members; internal repositories retain
their platform-defined minimum read visibility.

## UI-only member privileges and silent API no-ops

Some organization attributes appear in `GET /orgs/{org}` but are not accepted body parameters
for `PATCH /orgs/{org}`. Under the current documented contract, examples include repository
visibility-change permission, repository deletion/transfer permission, and the organization 2FA
requirement.

Do not send these response-only names in a PATCH and interpret `200 OK` as success. Use the
documented settings page:

- Organization **Settings → Member privileges** for repository visibility changes and repository
  deletion/transfer policy.
- Organization **Settings → Authentication security** for the organization 2FA requirement.

After the UI save, read the setting back in the UI and, when GitHub exposes the corresponding
organization attribute, through a fresh API GET. If the UI and API disagree, report the mismatch
instead of claiming completion. Enterprise policy may make an organization control read-only.

## Require organization 2FA

This is an organization-wide access change, not a checkbox-only task. The operating account must
already have 2FA enabled. Before enforcement, audit members, outside collaborators, billing or
shared accounts, and automation identities that could lose access.

Organization owners can query accounts without 2FA:

```bash
gh api -X GET 'orgs/ORG/members?filter=2fa_disabled&per_page=100' \
  --paginate --jq '.[].login'
gh api -X GET 'orgs/ORG/outside_collaborators?filter=2fa_disabled&per_page=100' \
  --paginate --jq '.[].login'
```

Notify or remediate affected identities before enabling the requirement. Under GitHub's current
documented behavior, non-compliant organization members retain membership but cannot access
organization resources until they enable 2FA; non-compliant outside collaborators are removed
and can lose repository and private-fork access. Shared, bot, or service accounts used as outside
collaborators need an explicit compliant authentication plan.

Enable the requirement in **Organization Settings → Authentication security**, review GitHub's
impact confirmation, and then verify:

```bash
gh api "orgs/ORG" --jq '{login,two_factor_requirement_enabled}'
gh api -X GET 'orgs/ORG/members?filter=2fa_disabled&per_page=100' \
  --paginate --jq '.[].login'
gh api -X GET 'orgs/ORG/outside_collaborators?filter=2fa_disabled&per_page=100' \
  --paginate --jq '.[].login'
```

Also inspect the organization audit log for removals and verify any critical automation account
can still perform its required read or write operation. Recovery may require disabling the policy
or reinviting a former outside collaborator after that account enables 2FA; record removed access
before enforcement so it can be reinstated accurately.

## Terminal evidence

An organization-access task is complete only when:

- the exact account and organization were verified;
- current and requested grants/settings were compared;
- affected identities and repositories were enumerated at the required scope;
- the supported API or documented UI path was used;
- every requested field was independently read back;
- effective repository permission, not only direct membership, matches the intended result; and
- any pending invitation, asynchronous policy effect, removal, or recovery obligation is reported.
