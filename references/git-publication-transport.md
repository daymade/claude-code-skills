# Named-remote publication transport

Use this when the repository's normal transport is unavailable and an authorized
push needs HTTPS without changing shared remote configuration. Load
[the verified publication recipe](../github-ops/references/pr_operations.md#basic-pr-creation)
and complete its preflight before applying the transport options below.

The [repository mainline guard](../scripts/git-mainline-guard.mjs) resolves the
remote name and refreshes that remote's main ref. Keep the remote operand
`origin`; passing a bare URL as that operand cannot supply the expected ref namespace.

Bind the HTTPS URL to the preflight's authorized repository and follow
[the operating identity and credential contract](../github-ops/SKILL.md#2-bind-identity-host-and-target).
Set `publish_sha` through the publication recipe's `rev-parse` step.

Apply the following per-invocation options to the recipe's native push:

```bash
git -C "<worktree>" \
  -c remote.origin.url="<https-url>" -c remote.origin.pushurl="<https-url>" \
  push origin "${publish_sha}:refs/heads/feature/new-feature" || exit 1
```

Replace the worktree, URL and branch with the preflight's bound values. These
options select transport for that command and preserve the named-remote hook
contract. Use the same options for the recipe's independent `ls-remote` readback,
then perform its exact SHA/ref comparison. A transport success receipt is not
the publication result.
