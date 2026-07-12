# Public-distribution content review

Use the repository's existing guard as the authority. Do not install a competing
hook path or copy machine-specific deny-lists into a public skill.

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
