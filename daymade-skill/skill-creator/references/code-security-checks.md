# Secret and Python archive-path checks

Run `security_scan.py` through [the packaging entry](publishing-and-packaging.md#step-6-security-review).
Require both Gitleaks and the bundled local Semgrep rule in default and verbose
modes. Use verbose mode only to add educational pattern checks.

## Bind the coverage

Read [the rule](../security_rules/python-archive-paths.yaml) and
[its runner](../scripts/code_scan.py) as the executable scope. Track Python `.py` regex
captures, and `path` fields read from JSON/XML parsed in the same function, into
`open`/`io.open`/`Path.open` literal write modes (`w`, `a`, `x`, `+`) and
`write_text`/`write_bytes`. Recognize
the local resolved-path `is_relative_to` rejection guard before a write, outside
exception-catching and context-manager blocks. Review other guard forms as
potential false positives rather than assuming they establish containment. Verify
that the root and guard actually implement the caller's intended boundary.

Keep cross-function/inter-file flows, other parsers, other languages, other sink
APIs, symlink races and general vulnerability detection outside this check's
claim. Review those boundaries through task-specific filesystem/CLI tests and
code review. Do not treat a green result as proof that the Skill is safe.
Use [Semgrep's taint documentation](https://docs.semgrep.dev/writing-rules/data-flow/taint-mode/overview)
for engine semantics; keep the local rule narrower than the engine's capabilities.

Scan the shared packaging superset, including optional evals, in an isolated
snapshot. Parse Python syntax without executing it and require the engine's
examined-file inventory to equal the selection. Fail on missing engines, wrong
versions, timeouts, analysis errors, incomplete JSON or inconsistent exit codes.
Disable inline suppression and external rules; turn metrics/version checks off.

Bind the packaging receipt to both source content and detector policy. Include
the code runner, rules, secret runner, packaging policy and locked dependencies
in the policy hash. Require a new combined scan for old secret-only receipts or
changed policy; never regenerate a marker by copying its fields.

## Calibrate before arming

For detector maintenance, run from a canonical source checkout's Skill Creator
directory containing `tests/`. Keep these maintainer tests outside `.skill`
packages according to the shared packaging policy. Use the combined scanner
entry above for ordinary installed-Skill packaging.

```bash
uv run --frozen python -m pytest tests/test_code_scan.py tests/test_security_scan.py tests/test_package_skill.py -q
```

For SDK dependency changes, follow
[scanner SDK maintenance](prerequisites.md#scanner-sdk-maintenance).
Keep advisory-floor checks, actual Semgrep MCP/telemetry consumer imports and
construction, healthy span roundtrips and oversized-TraceState rejection in this
calibration. Test the uv compatibility requirement at its declared boundary;
keep selected versions and runtime requirements in the project configuration.

Preserve the public pre-repair #1499 extractor under `tests/fixtures/repomix_1499.py`;
bind its immutable source and checksum in the test. Require all three original
XML/Markdown/JSON writes to be reported. Pair that with renamed/aliased calls,
resolve-only and late/missing rejection cases, safe guarded writes, constant
filenames, read-only access and real scan-to-package consumption. Keep fixture
values synthetic; do not execute the vulnerable extractor against real files.

Measure false positives on actual shipping code as well as synthetic controls.
For this marketplace, invoke the fixed owner entry from any directory:

```bash
python3 "<skill-creator-path>/scripts/creator.py" code_scan "<absolute-marketplace-root>" --marketplace
```

Select registered Skill packaging supersets and repository maintenance scripts;
reject missing or out-of-tree registered entries. Run this inventory check and
the calibration tests in CI's existing required `Secret scan` job. Keep the job
name stable for its configured branch-protection requirement.

For detector changes, compare recall on the frozen vulnerable source and false
alarms on the healthy corpus. Reproduce each false positive before refining
sources, sinks or sanitizers. Preserve missing/null/empty receipt tests and
engine failure paths; do not accept a detector because its rule count or process
exit looks correct.
