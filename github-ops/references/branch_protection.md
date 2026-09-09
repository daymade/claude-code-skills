# Contributor Access and Default-Branch Protection

Use this workflow when an authorized contributor must be able to push topic branches while
changes to the default branch require PR review. It applies only to the named repositories;
it does not change organization-wide base permissions or future repositories by inference.

## Inspect before changing rules

1. Resolve the active GitHub account, repository owner, effective administrative permission,
   visibility, `archived`, and `default_branch`. An archived repository is a lifecycle state,
   not a collaborator-role error; do not unarchive it without that separate authorization.
2. Read both classic branch protection and rulesets, including inherited rules. Preserve any
   existing required checks, reviews, deployment rules and deliberate bypasses unless the
   user explicitly changes them. Do not replace a stronger rule with the example below.
3. Read the repository owner's current plan if the API reports an entitlement restriction.
   Personal Pro does not establish an organization's entitlement. Check the current official
   feature contract; neither a generic 403 nor a 404 alone proves a plan limitation.

```bash
gh api "repos/OWNER/REPO" \
  --jq '{full_name,visibility,archived,default_branch,permissions}'
gh api "repos/OWNER/REPO/branches/BRANCH/protection"
gh api -X GET 'repos/OWNER/REPO/rulesets?includes_parents=true&per_page=100' --paginate
gh api "repos/OWNER/REPO/rules/branches/BRANCH"
```

Interpret failures in context: a verified repository's explicit `Branch not protected` response
identifies absent classic protection, not absent rulesets. An explicit upgrade response must
be resolved at billing; changing API families, making the repository public or reporting an
unenforced rule as protection is not a substitute. Prepare the actual seat count, billing
cadence and total before asking for new spend. After the owner upgrades, re-read the entitlement
and complete the already-authorized protection work without asking again.

## Define the review policy

Confirm any unresolved product choice, then freeze the concrete policy: branch targets, review
count, stale-approval handling, required checks, force-push/deletion behavior, and bypass actors.
An explicitly authorized policy does not need a second confirmation. Explain which operations
each bypass permits; `always` is broader than `pull_request`. Never add the contributor to a
bypass list merely to let them submit a branch.

The following is a policy example, not a universal default. It requires one approving review,
dismisses approvals after reviewable changes, resolves review threads, and prevents deletion
and force pushes. With no bypass actors it also applies to administrators; the PR author cannot
approve their own PR. If the owner needs to merge their own reviewed work, resolve that choice
and add only the explicitly approved actor in `pull_request` mode. Resolve the actor ID from
GitHub; never reuse the example author's or another environment's ID.

```json
{
  "name": "default-branch-pr-review",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}
  },
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true
      }
    }
  ]
}
```

Save the approved payload to a file. Add a rule only if no existing rule already implements
the policy; otherwise update that exact rule, preserving unrelated settings. Record the old
JSON and rule ID for recovery. A new rule can be removed or disabled by an administrator;
an update can be reversed by restoring its recorded previous policy.

```bash
gh api -X POST "repos/OWNER/REPO/rulesets" --input approved-ruleset.json
# For an existing rule, use its verified ID:
gh api -X PUT "repos/OWNER/REPO/rulesets/RULESET_ID" --input approved-ruleset.json
```

These are alternative actions, not two sequential steps. Create once. If the response is
lost, query the current rule list before retrying; names alone are not immutable identities.

## Read back both contribution and integration

Run fresh reads after the change:

```bash
gh api "repos/OWNER/REPO/collaborators/USER/permission" --jq '{permission,role_name}'
gh api "repos/OWNER/REPO/rulesets/RULESET_ID"
gh api "repos/OWNER/REPO/rules/branches/BRANCH"
```

Verify effective contributor Write access, `enforcement=active`, exact include/exclude targets,
the approved review parameters, and the complete bypass list. The branch's effective-rules
endpoint must return the new rules; listing a saved rule is insufficient. Inherited rules may
add constraints, so do not claim every future topic-branch push or merge is guaranteed merely
because the repository role is Write.

Do not create fake commits or attempt a destructive push just to test protection. Check the
configuration against the approved contract and use an existing legitimate PR when execution
evidence is needed. Report configuration enforcement separately from unperformed user actions.
Stop when the selected repositories are verified, or report the precise remaining entitlement,
identity or policy gap. Permission repair does not authorize merging a contributor's pending PR.

## Contract sources

- [GitHub collaborator permissions](https://docs.github.com/en/rest/collaborators/collaborators)
- [Ruleset API inputs and effective branch rules](https://docs.github.com/en/rest/repos/rules)
- [Protected-branch availability and review behavior](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

Recheck the current request schema and plan availability before changing hosted rules. The
permission/ruleset reads, create operation, explicit entitlement failure, post-upgrade create,
and effective-branch readback in this workflow were exercised on real repositories in September
2026; the sample's actor-free policy is illustrative rather than an executed policy for a user.
