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
