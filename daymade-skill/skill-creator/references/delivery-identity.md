---
name: delivery-identity
description: >-
  Generate verified Skill names, repository links and plugin versions for a
  creation/update delivery, then compare the actual final reply with its checked
  candidate. Read before reporting a Skill release or installation outcome, including later confirmations.
---

# Report the delivered Skill's verified identity

Use the formal `name` from the requested Skill's source. Keep an internal shorthand
in quoted discussion when useful; do not substitute it for the delivery subject.
The executing agent runs the bundled `delivery_identity` CLI. A host adapter may
call the same stdlib functions without starting uv at a lifecycle boundary.

## Generate from the existing source owner

Finish the normal source, registration, review and release checks first. Resolve
the intended source ref and commit any source changes before generating identity.
`generate` reuses `source_contract` and reads the Skill name, exact registration
and version from immutable Git HEAD. It does not infer ownership from a directory
name, prove installation, or establish that a current host loaded the Skill.

```bash
python3 "<skill-creator-path>/scripts/creator.py" delivery_identity generate \
  "<absolute-source-skill>" --repo "<absolute-source-repo>" \
  --output "<private-workspace>/identity.json"
```

Expect one JSON identity file and one generated Markdown delivery row. A suite
member retains its own formal Skill name while the version is labeled with the
suite plugin's name. No separate member version is invented. Missing/empty
metadata, unsupported repository origins and inconsistent source links exit 2.
The current generator supports GitHub HTTPS and SSH origins.

Combine the generated identity objects into one JSON list for the explicit set
of Skills this task is delivering. Copy the generated rows into the reply and
add the change/result explanation. Healthy single-Skill prose may retain its
wording if it contains the formal name, matching source link and registered
version; label a suite version with `suite <plugin-name> v<version>`. For multiple
Skills, retain the generated rows so names, owners and versions cannot cross.
Quoted old shorthand and explanatory Chinese text remain allowed.

A single-Skill plugin may retain a namespace different from the Skill's formal
name. Resolve that mapping from the exact registered source; report the formal
Skill name and label the version with its owning plugin name. Do not rename either
identity to make them equal.

## Check the final candidate and the actual output

Apply this preparation to the first delivery and each later user-facing release
or installation confirmation in the same task. Reuse the verified identity JSON
when its source facts remain applicable, but prepare each complete new reply.
A successful earlier check does not protect later unprepared chat. Never reuse
an old installation observation as proof of current runtime state.


```bash
python3 "<skill-creator-path>/scripts/creator.py" delivery_identity prepare \
  --session-id "<current-session-id>" \
  --identities "<private-workspace>/identities.json" \
  --candidate "<private-workspace>/final-candidate.txt" \
  --output "<private-workspace>/delivery-receipt.json"

python3 "<skill-creator-path>/scripts/creator.py" delivery_identity check \
  --session-id "<current-session-id>" \
  --receipt "<private-workspace>/delivery-receipt.json" \
  --actual "<private-workspace>/host-final-message.txt"
```

Expect `prepared` with a nonzero examined count before sending. The checking
caller supplies the host's actual final assistant text, not a second read of the
candidate file. A valid result has `status: valid`, the same examined count and
raw `actual_sha256`. New receipts use schema 2 with the explicit comparison
policy `crlf-terminal-lf-v1`: compare after converting CRLF to LF and removing at
most one terminal LF from each side. Preserve leading indentation, Markdown
trailing spaces, internal blank lines and any additional trailing blank line.
Return both candidate and actual comparison hashes separately from raw hashes;
this distinguishes transport line endings from changed body content. Schema-1
receipts retain exact comparison and are not silently upgraded. Schema-2 receipts
require this updated checker; an older checker returns unknown instead of
interpreting them as exact receipts. Missing schema-2 policy or comparison
evidence remains unknown; re-prepare a new receipt rather
than editing an already consumed lifecycle state. A body mismatch exits 2 as `invalid`, absent/malformed evidence as
`unknown`. Re-prepare after any candidate change. Keep receipts and real replay
text private, outside the distributed Skill package.

At an armed lifecycle boundary, the host owns task/session binding, extraction
of the actual final message and receipt consumption. Ordinary chat does not
implicitly arm this check. A Codex Stop continuation gate runs after generation;
it can detect and request a bounded correction after an erroneous reply has
already appeared. It is not a display-time filter. Report an unavailable adapter
or capped correction as unverified, never as a passed identity check.

The parser checks the task's declared identity set and bounded explicit delivery
subject clauses. It is not a classifier for every possible alias or prose claim.
An exact candidate match proves text identity, not that extra factual claims are
true; retain the normal release, installation and business-result evidence.
