# Runtime compatibility acceptance

Load before designing tests for an adapter that promises another platform,
runtime or implementation's behavior. Use the application's existing harness;
keep ordinary platform-independent tests on their current fast path.

## Bind the behavior and its oracle

The QA engineer or executing agent must freeze the supported versions, input,
expected consumer-visible output and compatibility authority before inspecting
the candidate's output. Use the target's approved contract and its actual
implementation/API as the oracle; do not generate expected values with the
adapter under test. Resolve a conflict between the promised contract and an
upstream implementation explicitly rather than silently choosing either result.

Record which dimensions are real and which are replaced: platform selection,
path parser, filesystem, process environment, current directory and runtime
version. Changing `sys.platform` does not change the host's `os.path` module or
filesystem. Use `ntpath` or `posixpath` for the selected Python path syntax and
`path.win32` or `path.posix` for the selected Node.js syntax; do not assume the
different runtimes classify every input identically.

## Exercise the changed boundary

Select relevant rows; do not require every platform or a new device matrix for
unaffected logic. Bind missing and empty values separately when the contract
distinguishes them.

| Boundary | Arrange and act | Observable assertions and control |
|---|---|---|
| Platform-specific selection | Populate only a different platform's cache or configuration; leave the selected platform's location empty. Repeat with the selected location populated. | The other platform cannot satisfy the selected platform's requirement. The selected location still succeeds. Assert the selected path as well as the status. |
| Path classification and resolution | Compare rooted-without-drive, drive-absolute and relative inputs with the promised implementation under fixed base/current directories. Use its actual path API and the candidate's real path parser. | Compare exact paths/classifications at the same API boundary. Preserve literal input where the contract does; resolve only the inputs the target resolves. Healthy absolute and relative cases remain correct. |
| Version or implementation difference | Run the discriminating input through the supported runtime versions or standard implementations; record their identities and outputs. | A host-specific substitute cannot stand in for an untested supported implementation. If it is unavailable, retain that gap while testing available paths. |
| Required runtime capability | Before long validation, run a small operation through the actual selected interpreter in the affected job's platform and execution context; record its version/build and the required API. | A supported version string or a present symbol alone cannot establish readiness. A missing API or rejected operation leaves that job explicitly `not_ready`; a healthy control must complete the operation and release its resources. Keep unrelated jobs on their existing path. |

For a Linux job requiring `os.pidfd_open`, two interpreter builds in the supported
Python 3.12 series can differ in API availability. Probe the selected interpreter
with `fd = os.pidfd_open(os.getpid(), 0); os.close(fd)` before the long run.
Distinguish a missing symbol from a call rejected by the host; neither establishes
readiness. Calibrate both failure cases with synthetic controls and verify actual
self-open and close on the healthy Linux runtime. Select this case only for jobs
that require that API; do not impose pidfd on other platforms or unrelated Python jobs.

For a synthetic example, consider a Python adapter promising Node.js Windows
path behavior. Python 3.13 changed `ntpath.isabs()` for a single leading slash
or backslash; Node's `path.win32.isAbsolute()` accepts that rooted form. A test
that equates the two classifiers can pass on an older Python and fail after a
runtime upgrade. Compare the promised operation, not only the helper predicate:
preserve a rooted path if the target keeps it, rather than resolving it against
an unrelated base drive. Include drive-absolute and ordinary relative paths as
controls. Keep this example separate from a claim about native Windows I/O.

### Select optional path-operation cases

Select these synthetic cases when normalization or drive-relative resolution is
part of the adapter's promised operation; retain the existing fast path otherwise.

| Operation | Discriminating input and independent oracle | Healthy controls |
|---|---|---|
| Normalize Windows syntax | Compare `C:\pkg\`, `pkg\` and `\\server\share\folder\` with the supported Node.js `path.win32.normalize()`. Assert the exact trailing separator: substituting Python `ntpath.normpath()` can remove it. | Include an empty string, a drive root and paths without trailing separators. |
| Resolve a drive-relative path | Compare base `D:\base` plus `C:pkg` with the supported Node.js `path.win32.resolve(base, input)`. Freeze the oracle's current directory and per-drive environment; do not derive its result with the adapter's join/absolute-path helper. | Include the same-drive base `C:\base`, a drive-absolute input and an ordinary relative input. |

Capture the oracle's output for the selected runtime and environment before
evaluating the candidate. Do not hard-code a maintainer's current directory or
generalize modeled path-module results to native Windows drive state.

## Calibrate and report

Run the original faulty behavior or a test-owned mutation through the same
assertions and confirm rejection; then run the repaired candidate and healthy
controls. For the selection row, a cross-platform union must fail. For the path
row, unconditionally resolving a rooted input against the supplied base must
fail when that differs from the promised output. A mutation that only changes
an unrelated helper does not calibrate the asserted behavior.

Report the exact compared outputs, examined cases and runtime versions. Label
real path-module execution with modeled filesystem inputs as such: it does not
prove native filesystem, permissions, per-drive current-directory state or
application launch. Use a native consumer check only when that affected claim
requires it. Finish when the affected failures and healthy controls have result
evidence; retain unavailable required observations and reuse unchanged checks.
These checks support compatibility claims, not adoption or retention claims.

## Sources

- [Python path modules and version-specific `isabs`](https://docs.python.org/3.13/library/os.path.html#os.path.isabs)
- [Python 3.12 `os.pidfd_open` and Linux availability](https://docs.python.org/3.12/library/os.html#os.pidfd_open)
- [Node.js platform-specific path APIs](https://nodejs.org/api/path.html#pathwin32)
- [Node.js v24.14.0 normalization and resolution](https://nodejs.org/download/release/v24.14.0/docs/api/path.html#pathnormalizepath)
