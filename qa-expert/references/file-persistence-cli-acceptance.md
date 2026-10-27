# File persistence and CLI acceptance

Load for file-backed state, snapshot dependency validation, recovery, CLI arguments,
wrappers, compatibility aliases, output or read-cost changes. The QA engineer or
agent turns the affected rows below into AAA cases in the repository's existing
harness, using its real writers, readers,
executor and child-process CLI. Keep the existing tracking/reporting workflow;
this recipe requires neither CSV initialization nor a new global test program.

Freeze the original and candidate revisions, supported format/consumer contracts,
selected operation IDs and expected results. Use synthetic files in an isolated
temporary state root. Bind each fault to the actual read/write boundary; retain
the original failure and a healthy counterexample. An injected impossible state
is a robustness probe, not evidence that production reaches it.

## Persistence and CLI matrix

Select rows touched by the change. Each row supplies Arrange, Act and Assert;
derive retry/read bounds from the fixture and existing policy before execution.

| Case | Arrange and act through the actual consumer | Observable assertions and healthy controls |
|---|---|---|
| **Byte identity and Unicode** | Write compressed and plain fixtures through the supported writer. Identify whether each declared digest covers stored-file bytes or decompressed entity bytes; validate raw bytes at that layer before text decoding. For text/entity identity, hash the exact decompressed bytes. Reopen through the normal reader. Separately inject malformed UTF-8, legal U+FFFD, emoji, a UTF-8 BOM, and an escaped isolated UTF-16 surrogate in JSON sent to the plain report path. | Positive controls for both legitimate digest layers pass with their matching declared digest; substituting the other layer fails. Preserve stored-file digest validation where required, and never hash decoded/re-encoded text as a substitute. Invalid bytes fail the encoding contract; literal U+FFFD and valid emoji remain intact. Assert BOM strip/preserve/reject behavior per consumer. JSON parsing alone does not prove report safety: assert the declared reject/escape/normalization result for the isolated surrogate, without silently changing authoritative bytes or digest. |
| **Complete CLI transport** | Spawn the real CLI with stdout connected to an OS pipe. Hold and release the reader at a controlled barrier so output exceeds pipe capacity and encounters backpressure; capture raw stdout, stderr and terminal exit status. Include multibyte text near chunk boundaries and a large JSON result. | Strictly decode the complete captured bytes, parse the whole JSON and compare exact record count, final record, fields and text with the fixture. A prefix with exit 0 fails. Verify ordinary small output too. A mock writer, terminal display or redirected file alone does not exercise the pipe path. |
| **CLI arguments and early exits** | Select for argument-parser or dispatch refactors. Freeze the original CLI contract, then spawn the actual entry with missing, empty, unknown and valid arguments, plus supported special modes such as help, liveness or self-test that legitimately omit ordinary required arguments. For paths that must exit before reading stdin, hold its pipe open without input until a bounded exit deadline; supply input and close stdin as specified for healthy input-consuming paths. | Compare exit status and complete stdout/stderr with each mode's declared contract; do not impose one universal error code. Catch tracebacks replacing usage errors or valid modes becoming argument failures. Observe dispatch and independently read isolated state/journal outputs: paths required to reject or exit before application dispatch and state access dispatch no event/command and create or change no state/journal. Retain permitted effects for valid calls and special modes. Parser/helper-only mocks supplement, rather than replace, these child-process cases. |
| **Wrapper arguments and compatibility aliases** | Select when a Make target, shell wrapper or compatibility entry dispatches to a CLI. Freeze each supported entry's argument mapping and declared differences; spawn the public wrapper and retained aliases with the same supported options, including dry-run, explicit empty values and values containing spaces. Include missing/unknown arguments and supported early-exit modes from the CLI row above. Capture the final executable/argv and isolated effect journal at the downstream operation boundary while executing the real wrapper and dispatch path. | Verify that the downstream consumer receives each option and value with its declared meaning, including argument boundaries. For dry-run, require propagation to the consumer that suppresses effects, or an explicit nonzero refusal before any external operation or state mutation; accepting and silently dropping it fails even with exit 0. Independently read the effect journal to prove no mutation for dry-run/rejected calls. Compare equivalent entries' selected operation, mode, option semantics, exit status and complete output; preserve declared deprecation messages or intentional differences. A healthy non-dry-run control still performs exactly the permitted operation. Calling only the bottom-level parser or checking the wrapper's echoed command does not cover this path. |
| **Interactive wrapper terminal ownership** | Select for changes to interactive wrapper output or input. Freeze the consumer’s existing ownership regions/intervals and permitted status/failure channels before selecting assertions. Drive the real wrapper and a synthetic child through an allocated PTY; capture raw consumed output and child-received exact byte fixtures for Chinese text, bracketed paste, edits and Enter. Trigger affected health transitions, an allowed coordinated status update where supported, and an uncoordinated write. Separately inject operational and relevant persistence failures; exercise the declared output timing, exit and restoration boundaries within predeclared case bounds. | Preserve exact declared input and independently verify affected positive health/state records. For exclusive child output ownership, require zero unsolicited wrapper stdout/stderr during that interval. For declared coordinated ownership, accept only permitted output and verify the reserved region, cursor/redraw and input remain correct; reject injected uncoordinated writes. Retain genuine failure visibility through its declared channel; require post-exit/restored-terminal diagnostics only when that is the existing contract. Mocked streams, pipe-only runs or tool completion alone do not cover this PTY case. Preserve declared noninteractive stdout/stderr and successful-exit output. |
| **Dependency scope and completeness** | Read a selected sealed root whose nested dependency is missing; separately read an unsealed top-level operation. Repeat with a healthy selected root and a damaged unselected root or side branch. | Preserve the contract's distinct integrity-failure versus unfinished/unknown diagnoses. Check which dependencies were selected and actually examined. Unselected damage neither poisons the healthy selection nor causes an older/unrelated fallback; damage on a selected dependency cannot be skipped. If the contract requires validating all branches, make them selected explicitly. |
| **Delivered dependency closure** | Build or select the actual delivered/cache/frozen package. Execute its changed normal and recovery branches, including lazy imports and relevant tool variants, in an isolated consumer with source-checkout fallback disabled. Remove a required packaged helper in a separate fixture. | Healthy packaged branches complete using only declared runtime dependencies; the missing helper fails explicitly. Inspect the consumed paths/module origins so a source checkout or inherited search path cannot hide the omission. One tool/branch passing does not cover another. |
| **State changes after validation** | Validate existing test-owned state, hold a barrier before its final open/write, then separately remove it, corrupt it or remove required schema. Release through the actual final persistence API. Use path/URI-sensitive characters in supported locations. | When the operation requires existing state, final open must not create or migrate a replacement after disappearance. Preserve the original bytes or absence and return the specified structured failure. A completed precheck is not proof of a safe final open. Preserve healthy writes, supported same-operation retry and legitimate first-create/migration operations under their own contracts. |
| **Corruption, repair and retry** | Separately corrupt a completed operation's result and metadata. Invoke the existing recovery path on the same operation ID, repair only the test-owned artifact through the supported procedure, then repeat the operation. Inject a transient I/O failure at the same boundary as a separate case. | Read the diagnosis and recovered result through the public consumer. Preserve operation identity and verify no duplicate executor invocation or side effect after a terminal record exists. Deterministic hash/schema/dependency errors stay integrity errors, rather than silently retrying, falling back or starting new work. Test bounded transient-I/O retries only where policy allows them; valid stored work still succeeds. No supported repair path means report the gap, not invent a rerun. |
| **Terminal state and cleanup** | Hold asynchronous cleanup behind a test barrier after the terminal record is committed. Read that record from a separate reader before releasing cleanup. Then release it and await the public close/drain API, including a cleanup-rejection case. | The terminal result is visible and usable while cleanup is held; close/drain waits for started cleanup and reports its specified failure. Read final persisted state and resource release independently. Do not replace this observation with sleep, swallowed rejections or retry-until-green. A harness without a barrier or completion API leaves that timing claim unverified. |
| **Shared graph and cache cost** | Build distinct snapshot roots with separate metadata that share immutable leaves. Select several roots in one operation and instrument actual filesystem opens/reads, unique visited artifacts/edges and materialized output. For an operation-local cache, end the call, alter a test-owned dependency or root, and start the next call. | Compare actual opens with the fixture's unique graph and declared read bound, not loader-call counts or elapsed time alone. Reuse only verified immutable facts within the operation; still validate every root's identity, metadata and selected edges. Roots sharing leaves remain distinct in the output. The next call rechecks changed files; per-root failures and healthy results match the uncached path. |

Apply the operation-local reuse boundary to configuration snapshots when a call
must use one consistent configuration: change test-owned configuration between
internal reads, verify the declared snapshot governs that call, then verify the
next invocation sees the change. Repeat after an exceptional exit to detect a
leaked snapshot. Revalidate mutable admission state at its own effect boundary;
a configuration snapshot does not freeze permissions. Select this case only for
an affected snapshot contract, not as a global requirement to cache configuration.

## Synthesis example: stored jobs with shared snapshots

**TC-CLI-001 — Arrange:** In the existing harness, create two completed synthetic
jobs with distinct root metadata and a shared text artifact containing `status � 😀`.
Register expected IDs, digests of exact decompressed bytes under this fixture's
declared entity-digest contract, selected edges, output rows and executor counts.
Add an unselected damaged branch and a barrier for cleanup.

**Act:** Export both jobs through the real CLI into the controlled pipe; read each
job while cleanup is held, then release it and await close. In separate fixture
copies, remove a selected nested leaf, leave a top-level job unsealed, and corrupt
a stored result or metadata. Use the supported repair procedure and request the
same job again. Start a new call after changing a shared leaf.

**Assert:** Full JSON/UTF-8 and both job identities survive; the legal replacement
character and emoji are unchanged. Actual file reads show shared-leaf reuse within
the fixture bound while both roots are checked. The unselected branch has no
effect; selected damage and an unfinished root produce their distinct diagnoses.
Repair preserves the job ID without another executor action, and the next call
detects the changed leaf. Check the matrix's BOM, isolated-surrogate and transient
I/O variants separately when those contracts are affected.

Stop when the affected original defect is reproduced, the candidate passes the
same consumer-level case and healthy controls, and test-owned resources are
closed. Reuse unchanged successful evidence; expand only for a new change,
failure or unresolved axis. Synthetic disk and pipe tests establish those paths,
not live services, power-loss durability or an untested reader version.

Technical boundaries: [RFC 8259 §8](https://www.rfc-editor.org/rfc/rfc8259#section-8)
distinguishes JSON interoperability from Unicode edge cases; the
[Node.js TextDecoder options](https://nodejs.org/api/util.html#new-textdecoderencoding-options)
define fatal decoding and BOM handling, and
[Node.js process I/O](https://nodejs.org/api/process.html#a-note-on-process-io)
explains why early process exit can lose pending stdout. Apply the actual
runtime's contract when testing another implementation.
