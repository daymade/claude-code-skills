# Bind the source account before reading

Apply this procedure before the first target-resource read. It selects an existing
authorized account; it does not grant new access or change the global profile.

1. Preserve a profile and identity already bound to this task, or explicitly
   selected by the user. A conflicting URL/registry entry is a mismatch to resolve,
   not permission to silently replace that selection.
2. When there is no binding, inspect the supplied URL's tenant host and the user's
   existing private account/profile registry or project source context. Match the
   full tenant host to a profile whose ownership and use for this task are known.
   Keep personal tenant names, account IDs and machine paths in that private
   registry, outside this public Skill.
3. Run `lark-cli profile list` to inspect available profile names, reported users
   and current token status. When identity needs checking, use
   `lark-cli --profile "<selected-profile>" whoami`. Apply the router's required
   no-proxy/notifier environment flags to these commands too. Do not infer a
   resource's tenant/account binding merely from the default profile, an app ID,
   a working token, a company name in the document, or a similar display name.
4. If a unique authorized binding is established, pass that `--profile` and the
   domain guide's supported `--as` on the first read and every dependent call.
   Default to the user's identity for their resource unless the task already
   explicitly selects the application identity. Do not change the global active
   profile. Preserve the supplied resource token rather than searching it again.
5. With no registry/binding and one clearly authorized account, use that explicit
   account and retain the resource's access result as the evidence. With several
   plausible accounts and no resolving evidence, ask which account owns/can read
   the resource; until resolved, inspect account metadata only. Do not probe the
   resource through every account or access another person's account by analogy.

After a denial, retain the exact resource/profile/identity and stop that route.
Load the router's current identity/permission owner to distinguish missing scope,
authentication state and resource access. A wrong organization does not establish
that a new login or scope is needed. Another existing profile may be assessed
only after the same ownership/authorization check; success on that profile does
not prove access on the denied one. Respect the domain's permission boundary and
never turn a denial into browser/raw-API retries or an automatic access request.
