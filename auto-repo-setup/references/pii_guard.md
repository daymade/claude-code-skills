# Public-distribution content review

Use the repository's existing guard as the authority. Do not install a competing
hook path or copy machine-specific deny-lists into a public skill.

## Select checks for the actual change

Use the repository's check map to select checks for the changed inputs and their
dependencies. Keep the required staged-content, introduced-history and publication
checks. Reuse successful results when the candidate content, relevant configuration
and checked inputs are unchanged; add checks for changed inputs, failures or
unresolved evidence.

Before repeating a slow publication check, read its route and cache receipts for
the exact candidate and destination base. If qualifying evidence is missing, use
the guard owner's explicit background maintenance path, then retry the normal
publication. Do not replace that recovery with repeated cold scans in the
interactive push or reuse evidence from a different scanner or policy identity.

A passing doctor or test suite verifies its stated checks. Publication recovery
requires the normal publication to pass for the intended refs and an independent
readback of the destination commit.

## Four complementary layers

### 1. Secret scanner

Run the repository's configured gitleaks/secret scanner on the actual staged diff
and, before push, the commits being published. Confirm the scanner configuration
itself is included in scope.

### 2. Path and generated-artifact scan

Reject machine-specific absolute paths, credentials files, build caches, archives,
and generated artifacts that are not part of the deliverable.

### 3. Repository-specific pattern scan

Use local/private pattern sources for organization-specific domains, identities, or
infrastructure. Do not publish the sensitive deny-list as the way to protect it.

### 4. Semantic read-through

Read the complete public artifact. For every concrete name, example, transcript
fragment, hostname, and path, ask:

> Is this a generic placeholder/public entity, or was it lifted from a real
> private project, person, conversation, or system?

Replace private material with role-based placeholders that do not encode the
original value. Scanners cannot detect private meaning that has no known pattern.

## Repository visibility matters

- Public distribution: all four layers are required.
- Private/internal repository: follow the repository's explicit retention and
  credential policy; do not impose a public-repository policy by assumption.
- Any material moving from private to public: treat the destination as public from
  the moment content is drafted.

Verify visibility from the hosting service rather than inferring it from a URL or
owner name.

## Findings

| Finding | Action |
|---|---|
| Live credential | Remove from content, revoke, rotate, assess exposure |
| Personal/private example | Replace with a role-based synthetic example |
| False positive | Fix the rule or add a narrow reviewed allowlist |
| Scanner is green | Continue to semantic review; green is not proof of privacy |

Never bypass a guard to make a commit or push succeed unless the user explicitly
authorizes that exact bypass in the current session.
