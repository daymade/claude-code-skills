# Release Safety and Environment Parity

Use this reference when Terraform or a recovery tool can change a running service, especially a shared
gateway. The invariant is simple: no candidate reaches a live path until the exact bytes, environment,
and runtime have been validated together.

## Freeze the real outcome and mutation surface

Write down:

- User-visible outcome and the real path that proves it
- Exact environment and service
- Every writer that can change that runtime, including broad deploy modules and break-glass recovery
- Last reversible point
- Authorized action and non-goals
- Recovery path if the mutation fails after it starts

A focused resource name does not imply a focused blast radius. Inspect provisioner bodies and dependency
edges: a "service deploy" resource may also extract a gateway directory, replace the runtime env, and
recreate a shared front door.

## Use one required-key contract

Keep required keys in one manifest or derive them from one canonical schema. Run the same validator for
every environment and every writer.

| Allowed difference | Forbidden difference |
|---|---|
| Domain, credential value, capacity, feature value | Required in staging but optional/defaulted in production |
| Environment-specific resource identity | Empty accepted by one writer but rejected by another |
| Explicit optional feature disabled in an environment | A hand-picked env list that omits a newly used key |

Treat unset and explicit-empty separately in fixtures, but reject both for required keys. Caddy replaces
`{$VAR}` before parsing and can expand it to an empty token. Compose `${VAR:?message}` rejects unset and
empty, while `${VAR?message}` rejects only unset. Pick the form from the schema, not by habit.

Do not "fix" a duplicated tracked secret by replacing it with a marker until the complete injection chain
is proven: one named secret SSOT, CI/Make export, renderer replacement, non-empty candidate readback, and a
negative test for missing input. Removing the only usable value is an outage, not secret management.

## Validate the exact bundle

Build a candidate directory away from live paths. It must contain the exact reviewed source archive,
selected environment artifact, Compose file, gateway files, generated files owned by adjacent modules,
and immutable image digest.

Then:

1. Render Compose's canonical JSON from explicit candidate paths and a controlled interpolation environment.
2. Extract the gateway service's full environment map and exact image from that rendered model.
3. Reject any missing/empty required key, any unresolved `${IDENTIFIER}` token, and any image mismatch.
4. Run the exact image with the complete environment and candidate config using the runtime's strongest
   non-starting validation mode.
5. Promote only the candidate bytes that passed, under the same deployment lock.
6. Use exact sync semantics for managed directories so a deleted config cannot survive as stale live input.

Do not validate with a host-installed binary, a different image tag, a manually reconstructed env subset,
or the current live config. Those validate a different system.

## Bind staging, source provenance, and production authorization

- Let staging test a clean local candidate before it is merged.
- Record a staging receipt only after apply and every required live verifier passes. A recorder callable
  by itself must rerun or cryptographically consume that evidence; it cannot mint a receipt from plan text.
- Before production, freshly fetch/read the authoritative remote branch and prove the candidate commit is
  in its history. Reject fetch failure; never fall back to a cached remote-tracking ref.
- Ask for production authorization at the last reversible point, using a channel the applying process
  cannot forge. Plan digests and blast-radius acknowledgements prove review, not permission.
- Keep the invalid-config recovery path separate and narrow: exact target, approved known-good bytes,
  prevalidation, compare-and-swap live identity, recovery ledger, and public readback.

## Keep pre- and post-mutation checks distinct

Pre-mutation validation prevents a known bad candidate from touching live state. Post-deploy acceptance
detects runtime, dependency, routing, and user-journey failures that static validation cannot know. Run
both; never describe a post-deploy failure as evidence that the pre-deploy gate worked.

## Exercise the actual release entry

The release author must test the repository's real orchestration recipe, not only its controller
functions. In an isolated fixture, execute the canonical entry with boundary executors replaced by
recording stubs; retain its actual ordering and file handling. Cover saved-plan filename registration,
plan creation, private evidence production, summary/digest binding, proof consumption and live verification.
Do not mock away the Make recipe that wires these steps together. A missing producer must fail before
mutation; a healthy recipe must reach its consumer. Keep a real staging run as the runtime acceptance.

For a shared runtime, the release author also enumerates parallel plan guards and post-write consumers
before changing the transition. Replay their joint canonical path with the same authenticated baseline.
A missing Terraform `before` is not proof that no live configuration exists: accept recovery only from
the explicitly authorized provenance-bound evidence, then preserve the complete protected inventory.
If a consumer already supports an authenticated runtime binding for permitted image replacement, validate
that binding before applying a legacy original-image equality; a binding-shaped JSON object alone cannot
authorize arbitrary drift.
Test both the intended transition and missing, empty, forged or unrelated route/image/runtime changes.

Retain real subprocess and filesystem boundaries for the changed transport, even when cloud operations
are stubbed. Use a complete production-sized synthetic witness, the runner's restrictive umask and real
import/file handling. Check successful completion, bounded failure, temporary-file cleanup and unchanged
tracked/untracked checkout state. Large private evidence belongs in a validated private file or descriptor,
not an unbounded environment/argument string. Exercise the actual pipe/file consumer: an input writer
finishing does not prove the reader observed EOF. Do not assume an isolated interpreter inherits ambient
flags that suppress bytecode or other cache writes. These are focused regression cases, not permission
to widen live deployment or repeat unchanged runtime tests.

For a narrow runtime update, capture the exact target identity and protected state before and after,
including when the plan has no changes. Derive preservation flags from those comparisons. Bind production
promotion to the authenticated staging producer, source, environment and attempt; a local JSON object
with the expected shape does not establish provenance. Test absent, empty, fabricated and stale evidence.

Compare runtime state by meaning. Canonicalize only fields known to be unordered, such as a container's
mount inventory; preserve every entry and field. A permutation should pass, while a changed mount source,
destination, type or access mode should fail. Do not sort order-sensitive arrays or omit protected fields
to silence a false alarm. Use captured healthy output and synthetic changed values for calibration.

If a release exits nonzero, establish whether mutation occurred before replaying it. Independently read
the target identity, effective configuration and affected user path; distinguish a write failure from a
post-write verifier failure. Preserve both facts in the result: what is live and which acceptance remains
unmet. Reconcile through the canonical narrow release entry rather than blindly replaying a saved plan.

## Minimum fixtures

Healthy fixtures:

- Staging and production both provide the same required key set with different valid values.
- Exact image accepts the rendered candidate.
- Saved plan, source/artifact provenance, live verifiers, and plan-bound production authorization/audit
  all match; the apply runner remains non-interactive and headless-compatible.

Dangerous fixtures:

- Required key absent.
- Required key present but empty.
- Required key remains an unresolved self- or foreign-key placeholder.
- Ambient shell variable overrides the candidate env file.
- Config uses a module absent from the exact production image.
- A broad deploy writer bypasses the focused gateway validator.
- Live directory retains a config deleted from the candidate.
- A standalone recorder tries to issue a staging receipt after a failed verifier.
- Candidate commit exists only locally or fetch of authoritative main fails.
- Production orchestration cannot prove that its recorded authorization/audit is bound to the exact
  plan digest, environment, and source/artifact identities.

For every pre-mutation failure, assert the live manifest/env and restart count are unchanged. Calibrate the
gate on known-good inputs before enabling it fail-closed; a false positive trains operators to bypass it.
