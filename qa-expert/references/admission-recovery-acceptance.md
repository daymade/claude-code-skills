# Admission and recovery acceptance

Load when a change affects admission decisions, account/resource bindings or
recovery that can authorize a native start, provider write or other effect.
The QA engineer or executing agent uses the existing harness and the authority's
actual request/result contract; this recipe grants no credential, production or
recovery permission and installs no enforcement mechanism.

Freeze the original and candidate revisions, selected operation identity,
binding fields, decisive validity checks and observable side-effect boundaries.
Use isolated synthetic state and barriers at the real validation, wait and
effect boundaries. Count attempts as well as successful writes/starts: a rejected
downstream call can expose an invalid action even when it creates no artifact.
Keep unrelated telemetry separate. Label impossible protocol faults as robustness
probes; do not report them as observed production incidents.

## Select affected cases

| Case | Arrange and act | Assert and healthy control |
|---|---|---|
| **Binding mismatch before recovery** | Capture a valid decision. Change tool, declared mode, profile and account/resource instance one field at a time, where those fields exist in the real contract. Invoke the public consumer's normal and recovery paths. | Reject a mismatch known at entry before publishing the wrong recovery request, writing to a provider or starting native work. Observe attempted effects with their target identities. Repeat with the original valid binding and verify its permitted completion/recovery. |
| **Validity changes while waiting** | Start with a valid binding, hold the existing wait/recovery boundary, then invalidate its source or change a bound field before releasing the barrier. | Recheck the same binding after the wait and before the effect under the authority's existing concurrency protection. No newly invalid effect proceeds. Preserve legitimate earlier reservations/writes and reconcile unknown results; do not demand zero total writes over an originally valid run or delete state to make that assertion pass. An unchanged valid binding still completes. |
| **Positive permission evidence** | Read the owner's actual success schema. At the consumer boundary inject missing, null, contradictory, malformed and unsupported result states, including a formerly supported state if compatibility is affected. | Only explicit proof valid under that contract permits the effect. “Not a known failure” is insufficient. Assert structured rejection/unknown and absence of the disallowed attempt; do not convert unknown into a safe retry. Include each currently supported success variant as a control. Do not copy another product's state names as the oracle. |
| **Retry and late outcome** | Hold a result, interrupt or lose its receipt, then exercise the supported reconciliation/retry path for that same operation. Separately deliver a late result after its binding changes. | Preserve operation identity and the owner's retry/idempotency semantics. A late receipt cannot authorize a different binding; an unknown outcome stays unresolved until reconciled. Verify healthy same-operation retry without duplicate effects where the contract promises that property. Do not infer universal exactly-once execution from a single run. |

Derive invalidation and effect ordering from the current implementation and
contract. A check immediately before a write is insufficient if another writer
can invalidate it in between; exercise that interval under the existing lock,
transaction or equivalent authority boundary. Report missing protection or an
unavailable barrier as a specific gap rather than asserting race safety.

## Reservations, expiry and command replay

Select this recipe for upload quotas, leases or other capacity reservations.
Bind each reservation to its operation, account/resource, original backend and
counter generation under the existing contract. Observe actual admission and
release effects using the supported backend, alongside its outage fallback.

- Reserve two legitimate slots, then release one reservation twice, including
  concurrent release calls. Only its own capacity becomes available.
- Expire the original counter, create replacement-window usage, then deliver
  the old release. The replacement usage remains intact, and releasing an
  expired missing counter creates no negative or persistent counter.
- Capture the actual admission and release commands and redeliver each with
  the same arguments. When the client can resend unacknowledged commands, each
  operation's promised effect still occurs once. Two concurrent calls with
  distinct identities remain two legitimate operations within the limit.
- At the exact reset boundary, verify admission and reported retry time against
  the backend's actual expiry. Preserve supported historical counter formats.
- Consume capacity during an outage, restore the backend, and exercise new
  admission, backend rejection and failed-upload release. Active fallback usage
  remains enforced under the declared policy. Duplicate history recorded during
  the outage still reaches its intended consumer after recovery.

Preserve supported differences between local and distributed enforcement.
Record an unresolved transport outcome separately from confirmed release.
For a regression intended to outlive an audit, keep the meaningful replay in
the repository's existing test entry, with explicit disposable endpoints and
scoped cleanup. Retire scratch payloads after their evidence has a durable owner.

## Retained sessions and cached permissions

When login restoration, permissions or upgrades are affected, the QA executor
tests fresh login and an existing signed-in session separately. Freeze the
installed artifact, account/tenant binding and authority's permission contract.
Use an owned disposable fixture to preserve or change the local cache; do not
alter a real user's role, credentials or data merely to manufacture a case.

| Case | Arrange and act | Assert and healthy control |
|---|---|---|
| **Grant after login** | Keep a signed-in session with an earlier denial cached, while the fixture authority now grants the affected permission. Exercise restoration and upgrade without logout or clearing data. | The required refresh reaches the authority and the real consuming page/action becomes usable without a stale denial. Compare with fresh login for the same identity; an API probe with a different session does not establish this path. |
| **Revoke after login** | Keep an earlier grant cached after the fixture authority revokes it. Re-enter the affected surface using the retained session. | Stale UI state cannot authorize the revoked effect. Check the consumer's denied state and actual server rejection, alongside a still-authorized account that can complete its permitted action. |
| **Identity changes in flight** | Hold an old permission response, then log out or change the account/tenant/environment before releasing it. Separately reverse two refresh responses for the same binding. | The old binding and superseded refresh cannot overwrite the current user's state or reopen access. The latest valid response still updates its own consumer. |
| **Unknown refresh result** | Return missing, null, malformed or failed permission data through the real refresh consumer. | Preserve the contract's explicit unresolved/error state; do not manufacture a grant or interpret missing evidence as a confirmed empty permission set. A valid response still recovers normally. |

Verify runtime enforcement independently of declarations: a permission annotation,
menu entry or hidden button does not prove a server interceptor ran. Use the
actual controller/security configuration with a denied fixture and an allowed
control. Keep potentially effective writes isolated; client-cache tests do not
replace server authorization tests. Record permission outcomes and binding
identifiers without saving tokens, credentials or full user payloads.

## Observe the consuming surface

Exercise each changed actual consumer and relevant tool/mode variant. Include
the lazy recovery branch in the delivered or frozen package when packaging is
affected, using [file persistence](file-persistence-cli-acceptance.md). A source import or one tool's
success cannot establish another tool's recovered native-start path.

Keep observations separate: request accepted, recovery published, permission
proved, effect attempted and operation completed. Capture correlated operation
and target identities through those boundaries. Stop when the original failure
is reproduced, the candidate rejects it at the required boundary, and the
protected healthy controls pass. Reuse unchanged successful evidence; expand
only for a new change, failure or unresolved axis. Synthetic tests do not prove
real OAuth recovery, live credentials, production adoption or historical cause.
