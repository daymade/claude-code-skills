---
name: qa-expert
description: >-
  Sets up QA testing processes: test strategies, Google Testing Standards test cases, P0-P4 bug
  tracking, quality metrics, progress reports, autonomous execution via master prompts, and OWASP
  security testing, with third-party QA handoff docs. Use when establishing QA infrastructure,
  writing test cases, executing test plans, or tracking bugs. Not for auditing an already-rendered
  UI (use frontend-visual-qa).
---

# QA Expert

Set up test cases, execution tracking, bug reports and QA handoffs using AAA test structure and OWASP security categories.

## When to Use This Skill

Trigger this skill when:
- Setting up QA infrastructure for a new or existing project
- Writing standardized test cases (AAA pattern compliance)
- Executing comprehensive test plans with progress tracking
- Implementing security testing (OWASP Top 10)
- Filing bugs with proper severity classification (P0-P4)
- Generating QA reports (daily summaries, weekly progress)
- Calculating quality metrics (pass rate, coverage, gates)
- Preparing QA documentation for third-party team handoffs
- Enabling autonomous LLM-driven test execution

## Quick Start

**One-command initialization**:
```bash
uv run "<qa-expert-dir>/scripts/init_qa_project.py" "<project-name>" "<project-root>"
```

The output directory is the project root; the script appends `tests/`. Use a fresh
destination: initialization overwrites its template files. Replace example CSV
rows, write test specifications and bind the project harness before execution.
Resolve `<qa-expert-dir>` from this loaded Skill's directory, not the target project.

**For autonomous execution**: Follow [the master prompt](references/master_qa_prompt.md)
for preparation, bounded execution and interruption recovery. Initialization
creates templates; it does not run tests or install a scheduler.

## Core Capabilities

### Test Case Writing

Write standardized, reproducible test cases following AAA pattern (Arrange-Act-Assert):

1. Read template: `assets/templates/TEST-CASE-TEMPLATE.md`
2. Follow structure: Prerequisites (Arrange) → Test Steps (Act) → Expected Results (Assert)
3. Assign priority: P0 (blocker) → P4 (low)
4. Include edge cases and potential bugs

**Test case format**: TC-[CATEGORY]-[NUMBER] (e.g., TC-CLI-001, TC-WEB-042, TC-SEC-007)

**Reference**: See `references/google_testing_standards.md` for AAA guidelines and project-bound coverage and release acceptance.

For cross-platform adapters or compatibility with another runtime/implementation,
load [runtime compatibility acceptance](references/runtime-compatibility-acceptance.md)
before choosing mocks, expected results or supported-version cases.

For payment, procurement, fulfillment or refund recovery, load
[transaction recovery acceptance](references/transaction-recovery-acceptance.md)
before selecting cases. For schema upgrades, accounting views or integration
fixtures, load [migration and fixture acceptance](references/migration-fixture-acceptance.md).
For file-backed state, snapshot dependency checks, recovery or CLI argument,
wrapper, compatibility-alias, output or read-cost changes, load
[file persistence and CLI acceptance](references/file-persistence-cli-acceptance.md).
For a persisted-state upgrade, use its
[old-writer/new-reader recipe](references/file-persistence-cli-acceptance.md#persisted-state-upgrade-and-recovery)
before choosing fresh fixtures or changing retry identity.
For bounded concurrent probes with ordered publication, use its
[blocked-first-slot case](references/file-persistence-cli-acceptance.md#bounded-concurrent-probes-and-ordered-publication).
For admission decisions, account/resource bindings, retained sessions or cached
permissions across upgrades, and recovery that can authorize an effect,
load [admission and recovery acceptance](references/admission-recovery-acceptance.md)
before choosing fault timing or side-effect assertions.
For responses, normalization or suggested edits that race with user changes,
load [asynchronous editing and conflict acceptance](references/async-edit-conflict-acceptance.md)
before selecting timing, session and related-object cases.
Bind these recipes to the application's existing contract and test harness;
retain the general AAA, tracking and reporting workflow.

### Test Execution & Tracking

**Ground Truth Principle** (critical):
- **Test case documents** (e.g., `02-CLI-TEST-CASES.md`) = **authoritative source** for test steps
- **Tracking CSV** = execution status only (do NOT trust CSV for test specifications)
- See `references/ground_truth_principle.md` for preventing doc/CSV sync issues

**Manual execution**:
1. Read test case from category document (e.g., `02-CLI-TEST-CASES.md`) ← **always start here**
2. Execute test steps exactly as documented
3. Update `TEST-EXECUTION-TRACKING.csv` **immediately** after EACH test (never batch)
4. File bug in `BUG-TRACKING-TEMPLATE.csv` if test fails

**Autonomous execution** (recommended):
1. Copy master prompt from `references/master_qa_prompt.md`
2. Paste to LLM session
3. Execute the authorized batch, track each result, file reproduced bugs and report evidence

On interruption, read back checkpoints and reconcile uncertain side effects
before choosing the first unmet test. Future execution requires an available,
authorized host runner; a prompt alone does not keep a session running.

### Bug Reporting

File bugs with proper severity classification:

**Required fields**:
- Bug ID: Sequential (BUG-001, BUG-002, ...)
- Severity: P0 (24h fix) → P4 (optional)
- Steps to Reproduce: Numbered, specific
- Environment: OS, versions, configuration

**Severity classification**:
- **P0 (Blocker)**: Security vulnerability, core functionality broken, data loss
- **P1 (Critical)**: Major feature broken with workaround
- **P2 (High)**: Minor feature issue, edge case
- **P3 (Medium)**: Cosmetic issue
- **P4 (Low)**: Documentation typo

**Reference**: Initialization creates `tests/docs/templates/BUG-TRACKING-TEMPLATE.csv`.

### Quality Metrics Calculation

Calculate metrics from the current tracking rows:

```bash
uv run "<qa-expert-dir>/scripts/calculate_metrics.py" "<project-root>/tests/docs/templates/TEST-EXECUTION-TRACKING.csv"
```

**Metrics dashboard includes**:
- Test execution progress (X/Y tests, Z% complete)
- Pass rate (passed/executed %)
- Unique linked bug IDs and test-priority breakdown
- Quality gates status (✅/❌ for each gate)

[`scripts/calculate_metrics.py`](scripts/calculate_metrics.py) owns the built-in
checks and CSV field interpretation. Record results as `✅ PASSED` or `❌ FAILED`
and completed status as `Completed`. Its P0 check only reads linked bug IDs and
`P0` in tracking notes; it does not read bug severity from the bug log. Coverage,
OWASP mitigation and release acceptance need their own project evidence.
The CLI prints failing checks but still exits 0; it is a report, not a release
gate. Follow [release acceptance](references/google_testing_standards.md#release-criteria). Calculate current
totals on demand rather than maintaining another summary table.

### Progress Reporting

Generate QA reports for stakeholders:

**Daily summary** (end-of-day):
- Tests executed, pass rate, bugs filed
- Blockers (or None)
- Tomorrow's plan

**Weekly report** (every Friday):
- Use template: `WEEKLY-PROGRESS-REPORT.md` (created by init script)
- Compare against baseline: `BASELINE-METRICS.md`
- Assess quality gates and trends

**Reference**: See `references/llm_prompts_library.md` for task-specific reporting prompts.

### Security Testing (OWASP)

Implement OWASP Top 10 security testing:

**Coverage targets**:
1. **A01: Broken Access Control** - RLS bypass, privilege escalation
2. **A02: Cryptographic Failures** - Token encryption, password hashing
3. **A03: Injection** - SQL injection, XSS, command injection
4. **A04: Insecure Design** - Rate limiting, anomaly detection
5. **A05: Security Misconfiguration** - Verbose errors, default credentials
6. **A07: Authentication Failures** - Session hijacking, CSRF
7. **Others**: Data integrity, logging, SSRF

Select security acceptance from the target project's authoritative release policy.

Each security test follows AAA pattern with specific attack vectors documented.

## Day 1 Onboarding

For new QA engineers, follow [Day 1 onboarding](references/day1_onboarding.md)
for its sequence, checkpoints and project setup examples.

## Adapting for Your Project

### Small Project (50 tests)
- Timeline: 2 weeks
- Categories: 2-3 (e.g., Frontend, Backend)
- Daily: 5-7 tests
- Reports: Daily summary only

### Medium Project (200 tests)
- Timeline: 4 weeks
- Categories: 4-5 (CLI, Web, API, DB, Security)
- Daily: 10-12 tests
- Reports: Daily + weekly

### Large Project (500+ tests)
- Timeline: 8-10 weeks
- Categories: 6-8 (multiple components)
- Daily: 10-15 tests
- Reports: Daily + weekly + bi-weekly stakeholder

## Third-Party QA Handoff
```
1. Ensure all templates populated
2. Verify BASELINE-METRICS.md complete
3. Package tests/docs/ folder
4. Include references/master_qa_prompt.md for autonomous execution
5. QA team verifies prerequisites, completes the applicable onboarding and follows the project schedule
```
