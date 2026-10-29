# CLAUDE.md

## Repository Overview

This repository is a Claude Code skills marketplace.

**Essential Skill**: `skill-creator` is the most important skill in this marketplace - it's a meta-skill that enables users to create their own skills. Always recommend it first for users interested in extending Claude Code.

## Skills Architecture

### Progressive Disclosure Pattern

Skills use progressive loading:
1. **Metadata** (name + description in YAML frontmatter) - Advertised according to the host's discovery policy and catalog budget; verify the fresh host rather than assuming every description is present
2. **SKILL.md body** - Loaded when skill triggers
3. **Bundled resources** - Loaded as needed by Claude

## Development Commands

### Installation Scripts

**In Claude Code (in-app):**
```text
/plugin marketplace add daymade/claude-code-skills
```

Then:
1. Select **Browse and install plugins**
2. Select **daymade/claude-code-skills**
3. Select **daymade-skill**
4. Select **Install now**

**From your terminal (CLI):**
```bash
# Generate installation commands (macOS/Linux)
bash -o pipefail -c 'curl -fsSL https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.sh | bash'

# Generate installation commands (Windows PowerShell)
iwr -useb https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.ps1 | iex

# Manual installation
claude plugin marketplace add https://github.com/daymade/claude-code-skills
# Marketplace name: daymade-skills (from marketplace.json)
claude plugin install daymade-skill@daymade-skills
```

[Run the generated commands in your terminal](README.md#generate-installation-commands) after using either helper script.

### Skill Validation and Packaging

Use [skill-creator](daymade-skill/skill-creator/SKILL.md) before creating or
changing a skill. Before selecting evidence or reporting completion, follow its
[required-acceptance owner](daymade-skill/skill-creator/references/change-verification.md#fix-required-acceptance-before-selecting-evidence).
For executable handoffs, including instruction-only cross-owner workflows, bind its
[intended-consumer boundary](daymade-skill/skill-creator/references/change-verification.md#bind-the-intended-consumer-before-verification)
and follow its [first-use route](daymade-skill/skill-creator/references/first-use-and-resume.md).
Use its selected workflow for regression review, validation, initialization, and packaging.
For capability extraction or reuse across business callers, follow its
[ownership decision](daymade-skill/skill-creator/references/authoring-and-reuse.md#the-extend-vs-create-check--runs-before-any-specialized-branch).

Operational or code-bearing Skill edits complete directly affected document alignment
before the first candidate freeze; follow skill-creator's Edit workflow.
For project instruction-entry maintenance, enter
[claude-md-progressive-disclosurer](daymade-claude-code/claude-md-progressive-disclosurer/SKILL.md).
Its verification reference owns dual-entry reconciliation and native-host readback;
keep the detailed procedure there.
For a valid check that emits warnings, follow its
[warning interpretation](daymade-skill/skill-creator/references/knowledge-skill-grounding.md#interpret-validation-warnings).
For local/remote ASR selection, speed comparison and speech-content acceptance, enter
[asr-transcribe-to-text](daymade-audio/asr-transcribe-to-text/SKILL.md) and its
[execution SOP](daymade-audio/asr-transcribe-to-text/references/execution_location_and_comparison.md).
For Scrapling browser-cache diagnosis, follow
[the troubleshooting owner](scrapling-skill/references/troubleshooting.md#2-browser-backed-fetchers-not-ready).
For competitor source-carrier/edition binding, claims, citations and existing-product learning, enter
[competitors-analysis](competitors-analysis/SKILL.md) and its
[citation readback checklist](competitors-analysis/references/analysis_checklist.md#citation-readback-and-counterevidence).
For changes since a prior analysis, load its
[Update classification](competitors-analysis/references/analysis_checklist.md#a-newly-discovered-path-is-not-necessarily-a-new-feature).
For user-selected collection destinations, load the
[collection destination route](competitors-analysis/references/collection_destination.md).
For running an original application demo, follow that Skill's
[original-app demo recipe](competitors-analysis/references/original-app-demo.md).
For file-backed persistence and CLI acceptance (including wrapper argument forwarding
and compatibility aliases), transaction recovery tests,
financial migration/fixture acceptance, admission/recovery bindings, runtime compatibility or project-bound release acceptance, enter
[qa-expert](qa-expert/SKILL.md); its test-case routes select the detailed recipes.
For required runtime capability probes, path normalization or drive-relative adapter cases,
follow its [runtime compatibility recipe](qa-expert/references/runtime-compatibility-acceptance.md)
and select the affected boundary before starting validation.

For choosing or reviewing a library, framework, storage, data format, model,
build-vs-buy or architecture — including 用哪个 / 选什么框架 / 要不要自建 / A 还是 B /
这个方案行不行 — enter [tech-selection](daymade-claude-code/tech-selection/SKILL.md).
Follow its full or lightweight route and linked execution owners.
For observability collector choices, use its [measurement and business-decision guidance](daymade-claude-code/tech-selection/SKILL.md#step-2--probe-for-evidence).
Before delegation, follow its [public orchestration route](daymade-claude-code/tech-selection/references/delegation-contract.md#agent-orchestration)
within the current user/host contract.

For research asset discovery, follow [deep-research's catalog contract](deep-research/references/research-asset-contract.md#start-before-external-retrieval);
keep discovery observations separate from final result checks.

For research-driven evolution of a specified existing Skill, start at
[skill-evolver](skill-evolver/SKILL.md) and follow its public stage routes; use
local private adapters only when available.
Before presenting an improvement diagnosis, follow its
[mechanism decision step](skill-evolver/SKILL.md#decide-every-important-mechanism).
For verification of changed state side effects, artifact reuse or prerequisite
handling, read `skill-evolver/references/behavior-replay-cases.md`.

For product-audit confidence, API consumer coverage and recommendation priority,
enter [product-analysis's synthesis method](product-analysis/references/synthesis_methodology.md).

For evidence-based improvement of an existing application, enter
[app-evolver](app-evolver/SKILL.md). For released-artifact or runtime evidence,
load its [Skill composition route](app-evolver/references/skill-composition.md);
keep specialist selection and handoff boundaries in that owner.
For domain-role extraction or scattered policy, use its
[consumer-adoption recipe](app-evolver/references/implementation-and-acceptance.md#extract-a-domain-role-through-its-consumers).
When the user corrects premises, research focus or scope, return first to its
[task binding](app-evolver/SKILL.md#1-bind-the-application-and-unfinished-result).
For next-increment selection after that reconciliation or a completed repair batch, use its
[increment-selection contract](app-evolver/references/evidence-and-fit.md#make-the-disposition-operational).
When feedback questions navigation, information hierarchy or interface coherence, use its
[structure comparison](app-evolver/references/evidence-and-fit.md#reconsider-interface-structure).
For discovery-task changes, follow its [task-pivot and return-context cases](app-evolver/references/implementation-and-acceptance.md#task-pivots-and-return-context).

For permission-sensitive fixtures, use Skill Creator's
[execution-context verification recipe](daymade-skill/skill-creator/references/stateful-script-verification.md#execution-identity-and-permission-fixtures).

For its audit, release, source-contract or materialization commands from another
working directory, use the [fixed command entry](daymade-skill/skill-creator/references/fixed-command-entry.md).

Before a command that may exceed the response budget, enter Skill Creator's
[large-output capture recipe](daymade-skill/skill-creator/references/stateful-script-verification.md#large-command-output).
For a large file or saved tool response, use its
[complete-file reading workflow](daymade-skill/skill-creator/references/stateful-script-verification.md#complete-file-reads).
For Codex Code Mode source reads or provisional loading receipts, enter its
[Code Mode receipt procedure](daymade-skill/skill-creator/references/stateful-script-verification.md#codex-code-mode-receipt).
Keep invocation, selection and incomplete-read semantics in those owners.

For plugin/Skill naming, source registration or release labels, use
[source location and activation](daymade-skill/skill-creator/references/source-location-and-activation.md)
and [delivery identity](daymade-skill/skill-creator/references/delivery-identity.md).

For a Chinese illustrated recipient guide from a manufacturer PDF, enter
[docs-router](daymade-docs/docs-router/SKILL.md) and its
[manual workflow](daymade-docs/pdf-creator/references/illustrated-manual.md).
For relative-image resource paths or Markdown → PDF rendering, read
[PDF Creator's ordinary entry](daymade-docs/pdf-creator/SKILL.md).

For Word creation, existing Word/WPS → PDF, DOCX review or version comparison, enter
[docs-router](daymade-docs/docs-router/SKILL.md) and load its selected child before acting.
DOCX delivery follows docx-creator's
[native acceptance procedure](daymade-docs/docx-creator/references/verification_protocol.md#step-3a--check-the-actual-file-in-microsoft-word-when-the-native-route-is-usable),
including refused/unavailable checks and reviewable handoff. DOCX comparison follows
[the input-identity and coverage procedure](daymade-docs/read-docx-review/references/full-comparison.md);
keep sending evidence, revision-view selection and comparison limits with that owner.

For saved HTML batches, follow [the conversion owner](daymade-docs/doc-to-markdown/references/html-conversion.md#gate-a-batch-through-the-existing-recipe)
and its actual-reader pilot before expansion. Keep conversion evidence and reader
observations separate; this file does not define another batch recipe.

For proxy-selection or disruptive VPN recovery changes, enter `tunnel-doctor` and its
proxy-conflict and network-recovery references. For unresolved tunnel packet-loss
localization, read the [capture procedure](debugging-network-issues/references/packet-capture-recipes.md#four-boundary-tunnel-captures).
For same-provider node failures with a working subscription, enter
[provider account checks](tunnel-doctor/references/provider_account_suspension.md).
For automatic WeCom integration,
enter `setup-notifications-via-wecom`; its receipt contract owns accepted/rejected/unknown
handling, while the worker owns event identity and delivery state.

For Terraform publication, linked releases, shared-route replacement, approval, first mutation,
expired plans, environment isolation or initialization-cache changes, enter
[`terraform-skill`](terraform-skill/SKILL.md).

For Deep Research or Kimi financial-research changes, enter the owning
[`deep-research`](deep-research/SKILL.md) or [`kimi-use`](kimi-use/SKILL.md) Skill.
Their linked references own the input handoff, download/export, run, source-archive, mode, and billing procedures;
the bundled CLIs own executable argument and validation behavior. Keep this file
as the route rather than a second copy of those procedures.

For customer-approved report forms, follow
[skill-creator's report-template contract](daymade-skill/skill-creator/references/authoring-and-reuse.md#show-the-result-not-just-the-work).

For Codex login, credential recovery, quota-query ownership or quota-driven continuation, enter
[local-codex authentication](daymade-codex/local-codex/SKILL.md#authentication-chatgpt-oauth).
For existing unmanaged/legacy Ghostty Codex windows around a manual account switch, enter
[ghostty-use's switch workflow](ghostty-use/SKILL.md#codex-account-switch). Minions
`native_runtime` rows instead use the owning Account Manager, not that manual route.

For rebuilding a paper form from an image, scan or screenshot as an editable
XLSX with a printable layout, enter
[excel-automation](daymade-docs/excel-automation/SKILL.md).

For growth analysis from sales or support conversations, enter
[product-growth](product-growth/SKILL.md) and follow its
[customer-conversation evidence recipe](product-growth/references/customer-conversations.md).

For HTML report creation or updates, enter
[report-with-html's Define success workflow](report-with-html/SKILL.md#workflow)
for reader/use, evidence precision, delivery location and investigation acceptance.
Its [technical comparison reading order](report-with-html/references/visualization-patterns.md)
owns concrete plans, cost boundaries and next-verification choices; do not turn a research
shortlist into purchase or deployment approval.
For filtered evidence inspection, follow its
[interactive-analysis recipe](report-with-html/references/interactive-analysis.md).
For transcript speaker-label updates, later reconciliation and consumer readback,
follow its [maintenance contract](report-with-html/references/long-lived-report-maintenance.md).

For citation previews and in-place source inspection, enter
[report-with-html's interaction owner](report-with-html/references/interaction-components.md)
and [frontend-visual-qa's source-inspection route](frontend-visual-qa/references/journey-and-page-contracts.md#cited-source-inspection).
For lightbox keyboard behavior, use the [shipped component](report-with-html/assets/components/lightbox-gallery.html);
for masked screenshots, use the [delivery gate](report-with-html/scripts/delivery_gate.py)
through the report workflow above.

For HTML report images and explanatory diagrams, enter
[report-with-html](report-with-html/SKILL.md); its
[visual evidence workflow](report-with-html/references/visual-evidence.md) owns selection,
source verification, placement and review. Keep report-specific assets with the report.

Treat [packaging_policy.py](daymade-skill/skill-creator/scripts/packaging_policy.py)
as the canonical inclusion policy for packaged content, security attestation and
source audits. Version progression and shipped-change review use their owning
gates under **Updating Existing Skills** below. Preserve the recorded policy
when verifying an existing baseline; consult
[source snapshot archives](daymade-skill/skill-creator/references/source-snapshot-archives.md)
before archiving or restoring it.

For hook creation, consolidation, Skill-entry enforcement, registration or recovery, load
[`daymade-claude-code:claude-code-hooks`](daymade-claude-code/claude-code-hooks/SKILL.md)
and follow its Build order and installer-owned recovery contract. Follow that
Skill's loop and reminder contract; keep current thresholds in the
owning implementation.
For hook model-context delivery claims or ordinary-interface notification visibility, use
[hook_pitfalls.md #66](daymade-claude-code/claude-code-hooks/references/hook_pitfalls.md);
for current-version/partial-structure SQLite upgrades, use that file's #59.
Before accepting persisted evidence that releases a hook block, read
[release-evidence failure handling](daymade-claude-code/claude-code-hooks/references/hook_pitfalls.md#68-invalid-release-evidence-can-escape-into-an-outer-fail-open-handler).

Python entry points registered as synchronous Claude Code/Codex lifecycle hooks or
background services (LaunchAgents included) must call a fixed direct interpreter
**owned by the installer that writes it**. Do not register a Python entry point through a
package manager, generic interpreter dispatcher, or `.py` shebang lookup: a
shared environment/cache lock can stall every prompt or tool boundary, and a
bare `python3` resolves under launchd's minimal PATH to the Developer Tools
stub, which is old enough to reject syntax the script was written in. The
opposite error costs the same: resolving `sys.executable` bakes in a versioned
path another product owns, so the job dies silently when that product upgrades.
Own the literal path, the way `SYSTEM_GIT` is owned. Explicit maintenance,
retrieval, validation, and test commands may still use their declared `uv`
project; the runtime boundary is the rule. The concrete prior-work wrapper and
profile-converger registration live in their respective Skills rather than
being copied here. An owning installer may support an already authorized
launcher; that does not make a package-manager dispatcher the default for
Python hooks.

For persistent Python service installation, environment reuse or startup, follow
[macos-watchdog's persistent runtime procedure](daymade-macos/macos-watchdog/SKILL.md#persistent-python-runtime).

### Rendered UI delivery acceptance

For rendered UI freshness, delayed editor/batch responses or deployment acceptance, enter
[frontend-visual-qa](frontend-visual-qa/SKILL.md).
For publication-wide clutter or AI Slop despite passing local checks, including
controls, deks and expanded summaries, use its
[publication journey calibration](frontend-visual-qa/references/publication-journey-cases.md).
For the pre-release ancillary-copy gate or density/layout comparisons, follow
[information necessity](frontend-visual-qa/references/history-derived-checklist.md#information-necessity-before-layout).
Before measuring loading speed, read its
[cache and timing comparison](frontend-visual-qa/references/browser-driving-and-observation-traps.md#separate-freshness-checks-from-performance-comparisons).
For build reuse across source refs or a target redeployed during acceptance, load its
[delivery verification procedure](frontend-visual-qa/references/delivery-verification.md).
For nested zoomable workspaces, use its
[journey and state matrix](frontend-visual-qa/references/journey-and-page-contracts.md#journey-and-state-matrix).
For repeated journey positions or measured wheel sensitivity, use its
[route contract](frontend-visual-qa/references/journey-and-page-contracts.md#route-and-addressability)
and [received-input recipe](frontend-visual-qa/references/browser-driving-and-observation-traps.md#wheel-requests-are-not-browser-received-wheel-events).
Before drawing page relationships or a click-through journey, use
[the topology/visit distinction](data-visualization-discipline/references/visual-form-selection.md#关系拓扑与有序旅程).
For live status, attention filters, retention intent or excluded-record recovery, follow its
[cross-view attention journey](frontend-visual-qa/references/journey-and-page-contracts.md#operational-attention-across-views).
For embedded-reader sizing, surrounding navigation, overlays, zoom, reading/return,
focus or filtered-selection changes, use its
[reader journey](frontend-visual-qa/references/journey-and-page-contracts.md#embedded-readers-and-semantic-zoom).
For long-document outlines, active-section cues or source sidebars, follow its
[reading-position recipe](frontend-visual-qa/references/journey-and-page-contracts.md#long-document-reading-positions).
For browser visibility, hidden-page polling (query eligibility, scheduling opportunities or product cancellation), selected read modes, request/capture timing or long JSONL input problems, load its
[browser-driving and observation traps](frontend-visual-qa/references/browser-driving-and-observation-traps.md);
keep adapter requirements and invocation examples in that reference.
For timed-out screenshots or blank hidden-window captures, follow its
[background capture diagnosis](frontend-visual-qa/references/browser-driving-and-observation-traps.md#background-screenshot-failure-does-not-establish-a-page-failure).
For changed contribution views or multi-item reads, use that same journey contract
for source-derived coverage and partial-result recovery; keep the detailed recipe
with the Skill.
Before designing or judging monitoring, availability or certificate matrices, enter
[data-visualization-discipline](data-visualization-discipline/SKILL.md).
Observation and risk semantics follow its data-validation route.
For incomplete observations, unknown counts or confirmed zero, use its
[operational-state matrix](data-visualization-discipline/references/operational-state-matrix.md).
When maintaining UI-journey or operational-state regression cases, use
[frontend-visual-qa evals](frontend-visual-qa/evals/evals.json) and
[data-visualization-discipline evals](data-visualization-discipline/evals/evals.json).

For oversized images or figure readability in a Markdown note or transcript, use
[frontend-visual-qa's actual-reader handoff](frontend-visual-qa/references/markdown-reader-handoff.md).
It owns reader-specific sizing and the representative pilot; keep display values
and verification details there.

### Visible permission and Keychain dialogs

For a visible permission or Keychain dialog, enter
[macos-permissions' observation and classification route](daymade-macos/macos-permissions/SKILL.md#observe-and-classify-the-reported-problem-first).
For an authorized desktop view, use
[capture-screen's full-screen observation route](daymade-macos/capture-screen/SKILL.md#observe-an-unidentified-dialog-or-the-full-desktop).
Keep detailed diagnosis and cancellation procedures with those Skills.

### Background protected-data access

For a background protected-data read failure, start at
[macos-permissions' reproduction step](daymade-macos/macos-permissions/SKILL.md#reproduce-the-reported-denial-first).
Before interpreting preflight logs or grant rows, read its
[correlation procedure](daymade-macos/macos-permissions/references/tcc-mechanics.md#correlate-preflight-and-grant-evidence).
For an established Full Disk Access repair, use its
[automated repair SOP](daymade-macos/macos-permissions/references/automated-full-disk-access.md).
After a permission grant or reset, follow `macos-permissions`'s
[request lifecycle](daymade-macos/macos-permissions/SKILL.md#after-a-grant-or-reset).

Treat `daymade-skill/skill-creator` as a locked uv project. Run its bundled Python tools from that directory with `uv run --frozen`; the project-local `.venv` is isolated from caller projects while uv's shared cache supplies the pinned packages. Do not reintroduce per-call `--with` overlays for dependencies already in its `pyproject.toml`.

From the repository root, enter the locked tool project once and validate the
selected skill (replace `<skill-path>` with its absolute path):

```bash
cd daymade-skill/skill-creator
uv run --frozen python -m scripts.quick_validate <skill-path> --audience public
```

### Review and evaluation input preparation

Before dispatching source evaluation cases, follow
[source-case input preparation](daymade-skill/skill-creator/references/eval_pipeline_schemas.md#source-case-input-preparation).

For Skill eval grading, aggregation or previous-iteration review, follow
[the eval schemas](daymade-skill/skill-creator/references/eval_pipeline_schemas.md)
and [the viewer workflow](daymade-skill/skill-creator/references/paired-evaluation.md#step-4-grade-aggregate-and-launch-the-viewer).
Keep assertion identity, missing-data semantics and viewer startup instructions in those owners.

When review, replay or evaluation needs input copies, follow
[the materialization SOP](daymade-skill/skill-creator/references/materialization-budget.md)
from the locked skill-creator project above. Its
[CLI](daymade-skill/skill-creator/scripts/materialize.py) owns argument parsing,
accounting, retry eligibility and cleanup behavior. For disk diagnosis, cleanup
recovery, or capacity checks before necessary backup/copy/extraction, use
[macos-cleaner](daymade-macos/macos-cleaner/SKILL.md) and its
[necessary-copy capacity preflight](daymade-macos/macos-cleaner/references/safety_rules.md#necessary-copy-capacity-preflight).
When changing measurement, run the SOP's targeted regression suite before shipping.
For uv cache diagnosis or retirement, enter
[macos-cleaner](daymade-macos/macos-cleaner/SKILL.md) and its
[uv target semantics](daymade-macos/macos-cleaner/references/cleanup_targets.md#uv-cache-retirement).
For Cargo or manual CI cleanup, read its
[artifact selection rules](daymade-macos/macos-cleaner/references/cleanup_targets.md#cargo-and-manual-ci-outputs).

### Automated Test Suites (CI)

For third-party model speed, protocol, concurrency or answer collection, enter
[llm-eval-harness](llm-eval-harness/SKILL.md). For machine results, consumed inputs,
retained answers, output-directory reuse or interrupted runs, read its
[machine-result contract](llm-eval-harness/references/machine-results.md).
For endpoint throttling or exhausted quota, follow its
[concurrency failure guidance](llm-eval-harness/SKILL.md#dimension-2--concurrency--stability).
Process exit alone does not establish the measured result.

A `tests/` directory under a Skill does **not** automatically run in CI.
[The registry](scripts/ci/test-suites.txt) owns suite admission and membership;
[the dispatcher](scripts/ci/run_registered_tests.sh) owns their execution commands.
[The workflow](.github/workflows/ci.yml) owns job environments, dependency installation,
timeouts and additional test steps. For required-check readback, bootstrap mismatches, installation stalls,
test failures and temporary-Git cleanup, follow [CI operations](references/ci-operations.md).

For CI demand, notification overload, exhausted allowance or repeated validation,
enter [github-ops' CI demand workflow](github-ops/references/ci-demand-and-notifications.md).
For self-hosted routing, resource limits or cache persistence, follow its
[runner acceptance](github-ops/references/workflow_operations.md#self-hosted-runner-capacity-and-acceptance).
Keep demand selection, validation-reuse and capacity acceptance in those owners.

For automatic observers or recovery jobs, begin with
[ordinary-entry and lifecycle acceptance](daymade-macos/macos-watchdog/SKILL.md#bind-the-ordinary-entry-before-choosing-a-mechanism),
including recovery after temporary protection. Browser-backed recurring jobs also
use that Skill's deployment acceptance for resource-budget and focus evidence.

Before selecting file-event or periodic triggers, follow
[macos-watchdog's trigger and acceptance workflow](daymade-macos/macos-watchdog/references/event-driven-observers.md).
For loaded plist scheduling and configuration, use its
[native readback](daymade-macos/macos-watchdog/references/native-job-readback.md).
For stopping or persistently disabling a job, follow its
[stop semantics](daymade-macos/macos-watchdog/SKILL.md#stop-semantics-the-deprecated-trap).
Before replacing an existing launchd job, enter its
[authorized unload and replacement procedure](daymade-macos/macos-watchdog/references/event-driven-observers.md#wait-for-an-authorized-unload-before-replacement).
Before choosing or changing any periodic observer's cadence, follow
[macos-watchdog's observation contract](daymade-macos/macos-watchdog/references/probe-cost.md).
For named macOS load/runaway alerts, follow
[macos-load-doctor's intervention and diagnosis-completion contract](daymade-macos/macos-load-doctor/SKILL.md#5-act-within-the-boundary).
For memory pressure or suspected child-process leaks, enter that Skill's
[triage](daymade-macos/macos-load-doctor/SKILL.md#triage-read-do-in-order) and
[memory evidence](daymade-macos/macos-load-doctor/SKILL.md#memory-evidence) before attributing the cause.
The observation contract above owns delayed-sampling acceptance; keep its tests
and the diagnostic stop conditions in those Skills.
For changed operating defaults or thresholds in an already-required review,
or behavior-replay dispatch and coverage claims, use
[skill-creator's independent-review protocol](daymade-skill/skill-creator/references/independent-review-protocol.md).
Keep decision criteria and verification details in those owners.

### Transcript Correction

For local audio listening, speaker decisions, word edits and recovery of saved
judgments, use [Listening Desk](daymade-audio/asr-transcribe-to-text/references/review_workbench.md).
Its saving, recovery and verification sections govern the browser and local
service; keep the operating procedure there rather than in review artifacts.

For explicit single-task speaker-inference requests, load
[scoped speaker inference](daymade-audio/transcript-fixer/references/scoped_speaker_inference.md).

Use [transcript-fixer](daymade-audio/transcript-fixer/SKILL.md) for transcript
correction. Its Native workflow owns evidence selection, selective human escalation,
and correction/finalization order;
[Native review packets](daymade-audio/transcript-fixer/references/native_review_packets.md)
owns split, batch, and resumed review instructions; first-pass and cold reviewers
use its [occurrence-specific evidence](daymade-audio/transcript-fixer/references/native_review_packets.md#occurrence-specific-evidence).
Keep CLI parameters and
validation behavior in
[native_review.py](daymade-audio/transcript-fixer/scripts/native_review.py), and
queue anchor behavior in
[review_queue.py](daymade-audio/transcript-fixer/scripts/core/review_queue.py).
For same-line repeats or a legacy row needing an explicit slot, follow
[occurrence anchoring](daymade-audio/transcript-fixer/references/review_queue_dashboard.md#same-line-occurrence-anchoring).
For company slots or a short match inside a longer name, follow
[minimum occurrence checks](daymade-audio/transcript-fixer/references/dictionary_identity_and_context.md#minimum-occurrence-checks-for-name-candidates).
For wording supported by a parallel transcript, follow
[written wording evidence](daymade-audio/transcript-fixer/references/review_queue_dashboard.md#written-evidence-for-ordinary-wording).
Use the [CLI reference](daymade-audio/transcript-fixer/references/script_parameters.md#fix_transcriptionpy)
to select the command; the argument parser owns accepted combinations.
For domain-context location, configuration-directory selection or homophone-veto
authoring, enter the [Domain Context Guide](daymade-audio/transcript-fixer/references/domain_context_guide.md).
For remaining pending rows or a received occurrence-specific human verdict on an
already reviewed file, enter [pending continuation](daymade-audio/transcript-fixer/references/pending-continuation.md)
for queue resolution and its finalization, learning and propagation owners.
For source-audio export, identity and timeline pairing, follow
[the audio setup SOP](daymade-audio/transcript-fixer/references/review_queue_dashboard.md#source-audio-and-timeline-pairing)
and its [audio helper](daymade-audio/transcript-fixer/scripts/fetch_minute_audio.py).
For batch audio checks, follow
[queue-level clip cross-check](daymade-audio/transcript-fixer/references/advanced_correction_evidence.md#batch-pending-adjudication--queue-level-clip-cross-check).
[verify_queue_audio.py](daymade-audio/transcript-fixer/scripts/verify_queue_audio.py)
owns executable anchor, duration and attachment validation; keep its CLI and
adjudication details in that SOP.
For an existing MLX file-output recognizer, use the
[audio engine CLI contract](daymade-audio/transcript-fixer/references/script_parameters.md#verify_queue_audiopy)
and resolve the runner from `asr-transcribe-to-text`; do not use progress stdout
as recognition text.
When changing these paths, update their owning instructions together; keep
review coverage, unresolved verdicts, and repository publication distinct.
For local correction tests and repository CI ownership, follow the
[testing strategy](daymade-audio/transcript-fixer/references/architecture.md#testing-strategy);
keep maintainer-only repository resources distinct from installed Skill paths.
Context-veto CLI regressions live in
[test_trap_demotion.py](daymade-audio/transcript-fixer/scripts/tests/test_trap_demotion.py).

### Feishu Recording Lookup

To find an existing Feishu recording by date, enter
[lark-cli-router's recording lookup](daymade-claude-code/lark-cli-router/SKILL.md#find-an-existing-recording-by-date).

### Feishu Document Capture

For Feishu document reads and archives, enter
[feishu-doc-scraper](feishu-doc-scraper/SKILL.md). Its
[API extraction SOP](feishu-doc-scraper/references/lark-cli-api-extraction.md)
owns resolved Wiki target dispatch and the authorized reference-traversal scope.
Its
[comments and feedback SOP](feishu-doc-scraper/references/comments-and-feedback.md)
owns discussion capture and interpretation; the bundled helper owns the CLI
interface. Before permanent filing or choosing an authorized archive destination,
follow the [destination handoff](feishu-doc-scraper/references/archive-destination-handoff.md).
For storage decisions, use its
[archive storage contract](feishu-doc-scraper/references/archive-storage-contract.md)
alongside the destination repository's storage SOP.
For local originals, Obsidian delivery or a personal source-catalog handoff, follow the Skill's
[original-media and reader SOP](feishu-doc-scraper/references/original-media-and-reader.md).

### Prior Work Retrieval Boundary

`prior-work-retrieval` creates an obligation only for an explicit prior-work,
reuse, or history request. Ordinary implementation, reports, and read-only
inspection do not arm it; PreToolUse and Stop may enforce only a requirement
already created by the current prompt. Artifact selection and runtime-read
comparison are owned by that Skill; a receipt about a locator is not proof of
the delivered artifact. For retrieval freshness, changed-source recovery and
receipt lifetime, follow the [Prior Work operating contract](daymade-claude-code/prior-work-retrieval/SKILL.md).
Requests to repeat a previously successful method enter its
[candidate verification](daymade-claude-code/prior-work-retrieval/SKILL.md#4-verify-candidates-at-authority).

For CLI/hook manifest selection or continuation in an already-running host, read
[the manifest-selection contract](daymade-claude-code/prior-work-retrieval/SKILL.md#2-validate-the-explicit-source-manifest).

### Local Conversation History Boundary

For reconciliation of an already-resumed native Goal, read
[native Goal reconciliation](daymade-claude-code/continue-codex-work/references/native-goal-reconciliation.md)
directly, binding the current host thread without external-takeover preparation;
use `continue-codex-work`'s full entry and verified history receipt for external task takeover.

For input appended after an operation's current-thread request, use [read-codex-history's bounded input cursor](daymade-claude-code/read-codex-history/SKILL.md#bounded-current-thread-direct-input-cursor). That owner defines source binding and read failures; the consuming operation owns human authorization. Keep executable commands and source details in the Skill.

For conversation-backup health checks or recent unfinished-request inventories, follow
[`local-conversation-history`](daymade-claude-code/local-conversation-history/SKILL.md).

For the latest Codex conversation about a topic across continuations, enter
[latest-topic discovery](daymade-claude-code/read-codex-history/SKILL.md#latest-topic-across-continuations).
For an unknown or cross-provider scope, start at the
[history router](daymade-claude-code/local-conversation-history/SKILL.md).

For remembered facts or a repeated search request, use that router's evidence
selection contract. The provider readers own original-record retrieval;
[`read-codex-history`](daymade-claude-code/read-codex-history/SKILL.md#original-tool-and-record-evidence)
owns complete Codex tool evidence, and
[`hybrid history recall`](daymade-claude-code/read-claude-code-history/references/hybrid_history_recall.md#query)
owns indexed role/phrase filters. Keep commands and source-attribution rules in
those owners rather than copying them here.

For suspected batch or controller termination, enter
[suspected termination evidence](daymade-claude-code/read-codex-history/SKILL.md#suspected-termination-evidence).

For original Claude tool calls/results from a known Session, including a named
Workflow subagent, use
[read-claude-code-history's narrow evidence entry](daymade-claude-code/read-claude-code-history/SKILL.md#original-tool-callresult-evidence).
Keep selectors, pairing, source scope and incomplete-output handling in that owner.

For a Claude session briefing or expansion of folded runtime Skill bodies, enter
[Exact Session evidence](daymade-claude-code/read-claude-code-history/SKILL.md#exact-session-evidence).
Large or unmeasured briefing output follows that reader's
[file-backed reading procedure](daymade-claude-code/read-claude-code-history/references/large-session-briefing.md).

For Claude history discovery without a known Session, use
[read-claude-code-history's indexed search entry](daymade-claude-code/read-claude-code-history/SKILL.md#indexed-content-search).
Keep executable examples and coverage requirements in that owner.

Codex inventory must use the index-only command in
`daymade-claude-code/read-codex-history/SKILL.md`. If its state database is
unavailable, report an unknown inventory; do not substitute a raw rollout scan.
Edit shared reader code in `daymade-claude-code/_conversation_core/`, then run
`python3 daymade-claude-code/sync_core.py sync` and `check` before shipping;
bundled `scripts/_core/` copies are generated projections.
For Claude task-ending and cwd interpretation, enter `read-claude-code-history`
and its [local runtime and cwd contract](daymade-claude-code/read-claude-code-history/references/session_file_format.md#local-runtime-and-working-directory-evidence).
Use its [session-ending workflow](daymade-claude-code/read-claude-code-history/references/workflow_examples.md#inspect-session-endings)
for candidate selection and commands; keep the detailed rules in those owners.

### Local Agent Messaging

For local transport selection or accepted/consumed delivery interpretation, enter
[peer-message](peer-message/SKILL.md). For independent sessions, enter the
[local coordination workflow](peer-message/references/local-coordination.md#原生跨会话通信)
before sending. Use its routing guidance for uncovered local targets
or coordination evidence that needs verification, never to bypass denied or Held messages.
Treat `peer-message/scripts/peer.py` as the fallback CLI executable
contract, [codex_live.py](peer-message/scripts/codex_live.py) as its Codex live adapter,
and `peer-message/SKILL.md` as the runtime router and owner of stable
runtime prerequisites plus the peer-cannot-authorize safety boundary. Independent-session
task/resource declarations and request lifecycle belong in its `references/local-coordination.md`.
Keep native-guard installation, recovery and actual-host acceptance in that workflow;
do not duplicate its parameters here. Reply lookup, transport and discovery
details belong in [the transport and receiver-evidence SOP](peer-message/references/protocol-and-discovery.md).
Enter that SOP when diagnosing delayed Codex coordination or comparing live and queued receipts.
Before asking about mutable ownership or a publication window, use the
[fresh-state preflight](peer-message/references/coordination-and-learning-loop.md#51-发现别人的在制品先核实再问等一个有界窗口).
For an inbound coordination envelope, a native reply or a receive-integrity error, follow
[receive, reply and closure](peer-message/references/local-coordination.md#收件回信和关闭).
For a known inbound `peer-message` envelope ID in Codex, use the
[original-envelope receive recipe](peer-message/references/local-coordination.md#从-codex-入站原件接收).
For oversized discovery responses or complete-title export, use its
[discovery-output contract](peer-message/references/protocol-and-discovery.md#发现输出的范围).
Current product availability, provenance, and inbound-control mechanics belong in
`peer-message/references/official-feature.md`; reply addressing, payload structure,
delivery-status language, what to do when you find another session's in-flight work on a
shared resource, and the verification contracts that decide what a peer assertion or a
peer denial is worth belong in
`peer-message/references/coordination-and-learning-loop.md`. Keep implementation, CLI help,
tests, and those owners aligned; README and changelog entries should point to
them instead of restating volatile protocol facts. The repository-wide
local-source activation contract below still applies—never hand-create Codex
Skill links.

### Ghostty Terminal Sessions

For snapshotting, restoring or reconciling Claude Code / Codex sessions in Ghostty
across reboots, enter [`ghostty-use`](ghostty-use/SKILL.md). Unmanaged/legacy manual Codex account
switches and blocked/delegated reopening enter its
[account-switch SOP](ghostty-use/references/codex-account-switch.md), including
the original-set handoff and actual-continuation acceptance. Minions `native_runtime`
rows use the owning Account Manager instead. Its bundled script owns
liveness classification and the paste-restore + auto-reconciliation loop; keep the
storage-layout facts and macOS Ghostty limits in its references rather than here.
Before a restore or retry, follow its
[current-set reconciliation](ghostty-use/references/restore_mechanics.md#reconcile-the-current-wanted-set).
For change-only automatic backups, use its
[automatic workflow](ghostty-use/references/automatic-snapshots.md).

For one-shot helper exits or attribution of an exited terminal, enter
[helper terminals and original sessions](ghostty-use/SKILL.md#one-shot-helper-terminals-and-original-sessions).

### Codex Quota and Account Checks

For selected-site Cookie copying between local profiles of the same macOS Chrome,
enter [cookie-copy](cookie-copy/SKILL.md). For its quota-query caller, follow
[Tibo's Cookie Copy handoff](tibo-reset-codex/references/browser-session-migration.md).

For a remote Codex sign-in prompt or terminal refresh rejection, start at
[Local Codex authentication recovery](daymade-codex/local-codex/references/oauth-guide.md#remote-account-switch-and-expired-login-recovery).
That owner defines project-authorization recovery, credential-store selection and usable-access verification; quota checks below remain a separate route.

For Codex reset announcements or account quota questions, enter
[tibo-reset-codex](tibo-reset-codex/SKILL.md). Follow its
[account usage SOP](tibo-reset-codex/references/account-usage.md) for authentication,
per-account verification, adjacent-reset attribution and browser restoration.
For unused quota, reset gains or avoidable waste, follow
[waste and added capacity](tibo-reset-codex/references/account-usage.md#浪费与新增容量).
Treat
[query_usage.py](tibo-reset-codex/scripts/query_usage.py) as the executable authority
for query parameters, supported response fields and exit behavior;
[reset_attribution.py](tibo-reset-codex/scripts/reset_attribution.py) owns mechanical
claim/evidence attribution and `claim_gate`. For local
snapshot reconstruction, [scan_rollouts.py](tibo-reset-codex/scripts/scan_rollouts.py)
owns candidate output. An unfulfilled
reset promise, missing execution signals or deadline-bound quota work enters the Skill's
[monitoring and stop contract](tibo-reset-codex/SKILL.md#监测轮从信息到可行动信号) and
[output contract](tibo-reset-codex/SKILL.md#输出合同先给结论再交代边界).
For a missed reset notification, enter its
[notification-chain diagnosis](tibo-reset-codex/SKILL.md#已有监测与通知链诊断).
Before interpreting tracker timestamps, Yes/No labels or mixed X reply results,
follow [signal readings](tibo-reset-codex/references/signal-readings.md).
For recurring community queries, follow
[community increments](tibo-reset-codex/references/forecast-feedback.md#社区增量读取);
when preparing the next monitor invocation, follow
[handoff carry-forward](tibo-reset-codex/references/forecast-feedback.md#交接结转).
[Next-reset forecast](tibo-reset-codex/references/next-reset-forecast.md) owns
date judgments; [forecast feedback](tibo-reset-codex/references/forecast-feedback.md)
owns recording, review and withdrawal, with
[forecast_log.py](tibo-reset-codex/scripts/forecast_log.py) as the executable
authority for CLI and local journal layout. Keep detailed commands and changing
account or forecast state out of this file.

### WeCom Send Boundary

WeCom sender skills must read an explicit target class. `self` may send to the
user's own delivery channel without authorization; `others` requires the exact
label and message at a human confirmation gate. Unknown target identity fails
fast. Automatic self delivery also requires the config-bound sender path and
digest; a matching basename is not identity. A pending item is not a delivery
receipt, and an automatic outbox path gets one non-retrying HTTP attempt.

### Testing Skills Locally

For affected executable entries before release and after source synchronization,
follow [source location and activation](daymade-skill/skill-creator/references/source-location-and-activation.md).

For installed-Skill and fresh-host acceptance, test the canonical source route. Use the current
`claude-switch-models-setup` local-source workflow for this maintainer machine,
and use `daymade-skill:skill-governance` to verify source, installed state,
discovery policy, and the fresh model-visible catalog. Do not blindly remove and
re-add a marketplace: removing it uninstalls plugins installed from that
marketplace. Do not `cp -r` a second Skill tree into a user Skill directory; that
copy immediately creates an independent drift owner.

For maintainer source-backed activation, source-watcher deployment, or authorized plugin-to-personal
Skill conversion, follow
[Local Source Sync Architecture](daymade-claude-code/claude-switch-models-setup/references/local-source-sync-architecture.md).
Do not hand-create user Skill links. Intentional same-name source variants follow
that owner's [explicit source preferences](daymade-claude-code/claude-switch-models-setup/references/local-source-sync-architecture.md#explicit-source-preferences).
For Skill authoring in an approved independent Fleet clone, follow the
[leased-authoring owner procedure](daymade-claude-code/claude-switch-models-setup/references/local-source-sync-architecture.md#leased-fleet-authoring-clones).

When delivery includes local availability, finish the source owner's dry-run/apply
and the [newly registered Skill gate](daymade-skill/skill-governance/references/skill-surface-governance.md#14-verify-a-newly-registered-skill).
Take expected identities from the requested change, not from links or a whitelist
that may already omit the new Skill. Keep installation/catalog evidence separate
from actual task results. A daemon using a pinned plugin copy also needs the
[pin-update workflow](daymade-claude-code/claude-switch-models-setup/references/troubleshooting.md#advance-the-pin).
Do not treat a merged source change as proof that this runtime advanced.
For a named-target availability verdict, use the
[target-verdict procedure](daymade-skill/skill-governance/references/skill-surface-governance.md#named-target-verdict).
Keep its invocation and result contract in that owner.
For recorder deployment, follow that workflow's ordinary-copy migration and
link readback; retaining a LaunchAgent wrapper does not update its files.

The syncer's managed marketplace identities, conventional checkout candidates,
and generated watch paths are owned by `sync-local-skill-sources.py`; derive them
from its constants/functions and `--print-watch-paths` output instead of copying
their current members or counts into instructions or references.

For context-window setting changes, keep the executable configuration and the
[context request probe](daymade-claude-code/claude-switch-models-setup/references/context-window-config.md)
aligned. That reference owns the request fields and probe commands.

In Claude Code, use `/plugin ...` slash commands. In your terminal, use `claude plugin ...`.

### Source Location Guard for Skill Creation and Edits

Load [skill-creator](daymade-skill/skill-creator/SKILL.md) and follow its canonical
source preflight before the first write. Its shared source-contract checker owns
repository identity, marketplace registration and project-local placement; use
[skill-governance](daymade-skill/skill-governance/SKILL.md) for installation and
fresh-host readback. Keep source, installed entry and private review archive distinct.
A registered marketplace source does not prove the installed copy or current host advanced;
follow the consumed-file checks in that governance reference before claiming activation.

After committing, run `scripts/ci/validate_changed_skills.sh origin/main`; it checks
the committed diff. A repository-level plugin validation does not replace per-Skill
validation.

### Repository Environment Repair

For repository startup failures or dependency/environment repairs, enter
[auto-repo-setup](auto-repo-setup/SKILL.md) and select its Environment repair workflow.
Keep runtime identification, update steps and consumer verification in that owner.

### Git Operations

For document-ingestion reviews and authorized small maintainer repairs, enter
[github-review-pr](github-review-pr/SKILL.md) and its
[small-repair workflow](github-review-pr/references/remediation_and_landing.md#expose-an-authorized-small-repair).
Before selecting an environment for an authorized repair, follow its
[carrier and source-owner selection](github-review-pr/SKILL.md#2-fetch-the-exact-objects-without-touching-the-users-worktree).
For cross-runtime staged-content validation or isolated task-copy setup, enter
[auto-repo-setup's Git safety reference](auto-repo-setup/references/git_safety.md).
Before choosing a task checkout's storage location, follow its
[isolated checkout preparation](auto-repo-setup/references/git_safety.md#isolated-checkout-preparation).

For already-authorized delivery in a shared checkout, enter
[auto-repo-setup's scoped delivery route](auto-repo-setup/references/git_safety.md#authorized-shared-checkout-delivery).
It owns the authorization/tool gate, bounded coordination, partial-result recovery and final closure;
keep ordinary sync, publication and recovery boundaries with their existing owners.

For inbound coordination during delivery or closeout, use
[peer-message's receiving route](peer-message/SKILL.md#收到消息先分流).
Keep the receiving and user-delivery procedure with that owner rather than duplicating it here.

Stage only explicit owned file paths; never `git add -A` / `git add .`.
Inspect the staged file list, including deletions,
in a separate call before committing; investigate any entry outside the intended
scope through `git-safety-net`. For branch publication and PR creation, follow
[the publication recipe](github-ops/references/pr_operations.md#basic-pr-creation)
before the first push. Keep its policy preflight, pinned source and remote readback
in that owner rather than maintaining another push example here.

For recovery or repository convergence under concurrent work, enter
[git-safety-net](git-safety-net/SKILL.md).
For local snapshot failures involving an index lock or commit-hook refusal, use its
[snapshot recovery procedure](git-safety-net/references/recovery_playbook.md#blocked-local-snapshots).
For Tibo's application retry and acceptance, follow
[the forecast journal owner](tibo-reset-codex/references/forecast-feedback.md#快照诊断与显式恢复).
For inherited upload restrictions, source paths hidden by ignore rules, or selected/delegated
classification batches, read its
[convergence authority and source-inventory procedure](git-safety-net/references/merge_verification.md#1-freeze-the-outcome-and-the-first-ref-snapshot).

For GitHub-hosted state — PRs, issues, Actions, repository or organization settings, permissions,
and API/UI mutations — enter [github-ops](github-ops/SKILL.md).
For reauthentication during an authorized operation, use its
[named-write authentication procedure](github-ops/SKILL.md#8-authenticate-only-for-the-named-write).
For upstream contributions and desktop E2E acceptance, enter
[github-contributor](github-contributor/SKILL.md) and its
[quality/E2E workflow](github-contributor/references/phase3_quality_gates_and_e2e.md).
For an explicitly requested independent evaluation of your own contribution,
follow the contributor entry's route to [github-review-pr](github-review-pr/SKILL.md).
For behavioral changes and review-led repairs, the review Skill's
[impact procedure](github-review-pr/references/behavioral-impact-review.md) owns
consumer tracing, preservation evidence and finding closure.
Before expensive checks on a concurrently edited base, follow GitHub Operations'
[publication coordination](github-ops/references/pr_operations.md#coordinate-publication-before-expensive-checks).
Before diagnosing conflicts or differing local and hosted merge results, use its
[fresh-base verification](github-ops/references/pr_operations.md#fresh-base-verification).
When the same verified objects still yield different local and hosted results, use
[the merge-semantics diagnostic](github-review-pr/SKILL.md#when-local-and-hosted-merge-results-disagree).
Before a merge or selecting `--auto`, enter its
[merge preflight](github-ops/references/pr_operations.md#merging-prs).
For hosted-state writes through `gh`, follow its
[identity, host and target binding](github-ops/SKILL.md#2-bind-identity-host-and-target)
before using an operation recipe. For historical account or connector attribution,
use the [identity-source contract](tibo-reset-codex/references/account-usage.md#区分身份来源与观察时刻).

**Closing a PR unmerged (declined, or superseded by another PR) → delete its head
branch in the same action.** `gh pr merge --delete-branch` only covers merged PRs.
Use `github-ops`'s [exact-tip branch retirement workflow](github-ops/references/pr_operations.md#converging-parallel-prs-and-retiring-remote-branches).
Apply that same owning workflow after merge-adjacent cleanup failures or a strict
up-to-date refusal; it owns exact-tip preservation, independent absence readback
and history-policy recovery.
For sensitive publication residuals, first enter `github-sensitive-data-cleanup`'s
[surface selection](github-sensitive-data-cleanup/SKILL.md#step-05-bind-each-exposed-surface);
approved PR body revision removal follows `github-ops`'s
[edit-history cleanup](github-ops/references/pr_operations.md#pr-body-edit-history-cleanup).
Keep detailed procedures and completion limits in those owners.

### Local `main` Is a Read-Only Mirror

Squash-merged PRs rewrite commits under new SHAs, so every direct commit to
local `main` guarantees divergence the moment its PR merges. These rules keep
`main` clean:

Before pushing shipped Skill changes, follow
[skill release readiness](daymade-skill/skill-creator/references/release-readiness.md).
The existing pre-push entry checks committed current-review evidence for the exact head.

`.githooks/pre-commit` and `.githooks/pre-push` dispatch to
`scripts/git-mainline-guard.mjs`, which rejects direct local-main work and stale
marketplace manifests or reused plugin versions against current main. The
dispatchers preserve the shared PII guard when it is installed. Activate this
repository **from the canonical primary main checkout** with
`git config core.hooksPath "$(pwd -P)/.githooks"`. The absolute path matters:
`core.hooksPath` is shared by linked worktrees, so a relative path would let a
stale feature worktree select its own stale dispatcher. CI and the GitHub main
ruleset independently enforce version progression on PRs; private review
evidence is checked locally by pre-push, as defined in the linked release SOP.

Push through the remote name so the repository guard can refresh current main.
For per-invocation HTTPS transport without changing shared remote configuration,
follow [the named-remote transport SOP](references/git-publication-transport.md).

1. **Never commit directly to local `main`.** All work starts on a feature
   branch (`git checkout -b <topic>`), ships via PR, and lands by squash merge.
2. **After every merge, read the current branch before updating the checkout.**
   If already on `main`, pull with `--ff-only` without another checkout. If the
   shared checkout is on another session's branch, coordinate before moving it.
   A failed pull is not proof of local-main commits: inspect its error and compare
   the local and remote refs to distinguish divergence, changed files, and a
   failed remote read. Do not merge or force-push `main` to bypass a refusal.
3. **If switching your own feature checkout to `main` is refused** ("local
   changes would be overwritten"): this is not
   automatically the divergence case above. Check whether local `main` is
   merely **stale** (nobody committed to it, it just never got its ref
   updated after a previous merge) before assuming divergence — `git diff
   HEAD origin/main -- <the-file>` from your feature branch; empty output
   means your branch's committed content already matches `origin/main`
   exactly, and the checkout conflict is purely local `main`'s ref being
   behind. Fix without touching the working tree or any other session's
   uncommitted changes: `git fetch origin main:main` (updates the ref
   directly, no checkout needed), then retry `git checkout main`. Only fall
   through to the divergence procedure below if the diff is non-empty.

4. **Treat `pull --ff-only` as a whole transaction, not a per-file one.** It
   refuses when *any* file it would update carries local modifications — and
   that file may belong to another session and be untouched by your branch.
   One peer's uncommitted file therefore blocks the update of every other file
   in the same pull, which is how a shared checkout stays behind `origin/main`
   while every signal you checked still looks fine. Before assuming
   divergence, list what the pull would touch and check each path:
   `git diff --name-only main origin/main`, then
   `git status --porcelain=v1 -- <that-path>`. When the blocking file is not
   yours and is still being written, leave it alone and report the baseline
   SHA, who was asked, and that the ff is still outstanding — do not stash,
   `checkout --`, or `restore` it.

For an already-authorized task with declared scoped tools, use the scoped delivery
route above before treating another writer's unrelated changes as a reason to
leave the task waiting. This does not permit overwriting that writer's files or
claiming the whole checkout is current.

For divergent local `main` or branch/worktree retirement, follow
[git-safety-net](git-safety-net/SKILL.md) and its
[content-containment proof](git-safety-net/references/merge_verification.md).
Before selecting recovery material for a named branch or worktree, apply
[Preservation before retirement](git-safety-net/references/merge_verification.md#preservation-before-retirement).
For a linked checkout, follow the owning
[worktree-retirement procedure](git-safety-net/references/merge_verification.md#worktree-retirement--prove-the-checkout-is-disposable-before-removal).
When current content differs from an older published review, use that reference's
[historical publication example](git-safety-net/references/merge_verification.md#worked-example--old-review-content-landed-through-another-ref)
before deciding supersession; historical equality alone does not establish current intent.
Resolving conflicts toward upstream can erase the very delta being checked;
an empty result after that resolution does not prove it shipped.

## Skill Writing Requirements

### Writing Style

Use **imperative/infinitive form** (verb-first instructions) throughout all skill content:
- ✅ "Extract files from a repomix file using the bundled script"
- ❌ "You should extract files from a repomix file"

### YAML Frontmatter Requirements

Every SKILL.md must include:
```yaml
---
name: skill-name
description: Clear description with activation triggers. This skill should be used when...
---
```

### Privacy and Path Guidelines (Enforced by Pre-commit Hook)

Skills for public distribution must NOT contain:
- Absolute paths to user directories (`/home/username/`, `/Users/username/`)
- Personal usernames, company names, product names
- Phone numbers, personal email addresses
- OneDrive paths or environment-specific absolute paths
- Use relative paths within skill bundle or standard placeholders (`<workspace>/`, `<user_id>`)

**Defense layers:**
1. **CLAUDE.md rules** (this section) — Claude avoids generating sensitive content
2. **Global PII Guard pre-commit hook** (`~/scripts/git-pii-guard/pre-commit`) — blocks staged PII/secrets and generated/local artifact paths
3. **Global PII Guard pre-push hook** (`~/scripts/git-pii-guard/pre-push`) — scans commits about to be pushed, catching bad local history before it hits GitHub
4. **gitleaks** (`.gitleaks.toml`) — deep scan with custom rules for this repo
5. **AI semantic read-through** — pattern-based scans only match patterns someone listed, and are blind to private content with **no keyword** — a real name in another language (gitleaks doesn't cover CJK), a verbatim line from a real transcript, a real example dropped into an illustration. Before publishing, **read the whole skill yourself and judge each concrete name/example/snippet semantically** ("generic placeholder / public entity, or lifted from a real project / person / transcript?"). A green scan is **not** a clean bill of health; "grep found nothing" only means your word list didn't fire. Method: [`daymade-skill/skill-creator/references/sanitization_checklist.md`](./daymade-skill/skill-creator/references/sanitization_checklist.md).

Most repositories enable PII Guard via `~/scripts/git-pii-guard/manage.sh enable <repo-path>`. This repository instead points `core.hooksPath` at the canonical primary checkout's absolute `.githooks` directory: its versioned dispatchers run the repository mainline guard and then delegate to the same shared PII guard when installed.
For repo-specific additions:
- `.pii-patterns` — extra content regexes
- `.pii-path-patterns` — extra forbidden path regexes
- `.pii-allowpaths` — explicit path allowlist exceptions
- `.pre-commit-config.yaml` — optional repo-local runner that wires `pre-commit` framework to the same path/content rules for contributors who prefer managed hooks
If it fires, fix the issue — do NOT use `--no-verify` to bypass.

### Content Organization

- Size SKILL.md by information density, not a line-count target
- Move detailed documentation to `references/` files
- Avoid duplication between SKILL.md and references
- Keep `tunnel-doctor` environment-neutral: it may teach discovery and presence checks, but exact private node labels, billing identities, endpoints, credentials, and current chain state remain in the owning private configuration/Skill and must not be copied into this public repository.
- Kimi desktop input and tunnel diagnostics follow the current host-specific procedures in `kimi-use/references/driving-kimi-app.md` and `tunnel-doctor/SKILL.md`; a proxy bypass recommendation requires compared path evidence.
- Scripts must be executable with proper shebangs
- All bundled resources must be referenced in SKILL.md

## Marketplace Configuration

The marketplace is configured in `.claude-plugin/marketplace.json`:
- Contains plugin entries: single-skill plugins point `source` directly at the skill directory (no `skills` field); any plugin entry with a non-empty `skills` array is a suite and uses those relative paths for multi-skill routing
- **All suite plugins are suite-only.** Derive the current suite set from non-empty `plugins[].skills`; do not maintain another name list here. Users install the suite and invoke members as `<suite>:<skill>`. When adding a member, update only the suite entry's `skills` array — do NOT create a parallel standalone plugin entry.

### Versioning Architecture

1. **Marketplace Version** (`.claude-plugin/marketplace.json` → `metadata.version`)
   - Tracks the marketplace catalog as a whole
   - Bump when: Adding/removing skills, adding/removing suite plugins, major marketplace restructuring
   - Semantic versioning: MAJOR.MINOR.PATCH

2. **Plugin release identity** (`.claude-plugin/marketplace.json` → `plugins[].version`)
   - The registered plugin owns the release version. Suite members share their suite's
     version; a standalone Skill uses its own plugin entry.
   - Follow [skill-creator's versioning contract](daymade-skill/skill-creator/SKILL.md)
     for change classification and release identity.

### ⚠️ Updating Existing Skills (MANDATORY)

Use [skill-creator](daymade-skill/skill-creator/SKILL.md) to classify the change and
[packaging_policy.py](daymade-skill/skill-creator/scripts/packaging_policy.py) to
decide which changed files ship. Do not infer a separate member version from its directory.

For pre-commit release progression, use the existing
[version checker](scripts/ci/check_version_progression.py) through the
[mainline guard](scripts/git-mainline-guard.mjs). That checker owns registered-plugin
mapping and version-increment eligibility; package exclusion alone is not a version
exemption. Select shipped-change review eligibility through
[release readiness](daymade-skill/skill-creator/references/release-readiness.md).

**Read the baseline version from an immutable ref, never from the working tree.**
A shared checkout's `marketplace.json` may already carry another session's staged
or saved version bump; that working copy cannot establish the baseline.

For a stale marketplace guard, a foreign plugin's apparent version regression,
or a release candidate missing current main, follow
[integration before review binding](daymade-skill/skill-creator/references/release-readiness.md#integrate-current-main-before-binding-review).

## Available Skills

Current plugin names, versions, sources, and suite membership are defined only
in `.claude-plugin/marketplace.json`. Use README.md / README.zh-CN.md for the
human-readable capability guide; do not maintain another numbered Skill snapshot
in this model-loaded file.

## YouTube Downloader SOP (Internal)

See [youtube-downloader/references/internal-sop.md](./youtube-downloader/references/internal-sop.md) for yt-dlp troubleshooting steps (PO tokens, proxy, cookies, etc.).

## Python Development

All Python scripts in this repository:
- Use Python 3.10+ syntax
- Include shebang: `#!/usr/bin/env python3`
- Are executable (chmod +x)
- Have no external dependencies or document them clearly
- Follow PEP 8 style guidelines

## Quality Standards

For public first-use instructions, follow [QUICKSTART.md](QUICKSTART.md) or
[QUICKSTART.zh-CN.md](QUICKSTART.zh-CN.md). For reporter environment fields, use
the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) rather than copying
a Skill list or assuming the reporter's host.

For a blocked packaging attempt, follow the
[packaging recovery procedure](daymade-skill/skill-creator/references/publishing-and-packaging.md#step-7-packaging-a-skill).

For changes to scripts, importable API contracts, configuration, or operating procedures, use
[docs-cleaner](daymade-docs/docs-cleaner/SKILL.md) for scoped documentation delivery:
resolve implementation intent and authorization before updating the owning SOP,
and validate the delivered command examples. Keep detailed governance in that Skill.
For outbound link-check diagnostics, follow its
[reader-host interpretation](daymade-docs/docs-cleaner/SKILL.md#updating-references-to-a-file-you-moved-or-deleted).
After moving a procedure or renaming an anchor, use its
[delivery-entry replay](daymade-docs/docs-cleaner/references/delivery-entry-replay.md)
against the consuming instruction-file entry.
When a changed workflow affects stable rules or entry routes, update this file's
rules and indices; retain implementation values and detailed procedures in their SSOT.

Before submitting or modifying skills:
- Valid YAML frontmatter with required fields
- Description includes clear activation triggers
- All referenced files exist
- Scripts are executable and tested
- No absolute paths or user-specific information
- Comprehensive documentation
- No TODOs or placeholders

## Adding a New Skill to Marketplace

Follow [Adding a New Skill to Marketplace](references/new-skill-guide.md) for
registration, README updates, documentation alignment, validation, and publication.
Apply **Quality Standards** above to this file's affected stable rules and routes.
Use the existing suite identity when adding a member; do not introduce a parallel
standalone plugin.
The local-availability gate under **Testing Skills Locally** applies when local
use is part of the requested delivery.

## Chinese User Support

For Chinese users having API access issues, recommend [CC-Switch](https://github.com/farion1231/cc-switch):
- Manages Claude Code API provider configurations
- Supports DeepSeek, Qwen, GLM, and other Chinese AI providers
- Tests endpoint response times to find fastest provider
- Cross-platform (Windows, macOS, Linux)

See README.md section "🇨🇳 中文用户指南" for details.

## Handling Third-Party Marketplace Promotion Requests

Decline all third-party marketplace promotion requests. For policy, response template, and precedents, see [references/promotion-policy.md](./references/promotion-policy.md).

## External Contributor PRs (Curation Policy)

**Policy SSOT: [CONTRIBUTING.md](./CONTRIBUTING.md)** — this is a curated marketplace of our own skills; bug fixes are welcome, new-skill PRs are not accepted.

Agent rules when an external PR appears:

- **Never merge external PRs unilaterally.** Every external-PR merge decision goes to the user first, no matter how small or obviously-correct the fix looks.
- **Bug-fix PRs** (after the user approves): land the repo bookkeeping as a maintainer follow-up — version bump in `marketplace.json`, CHANGELOG entry, README sync where applicable. Contributor PRs usually lack these.
- **New-skill PRs**: close with the standing message in CONTRIBUTING.md.

## Best Practices Reference

Always consult Anthropic's skill authoring best practices before creating or updating skills:
https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices.md

An application's project-level health-check Skill owns its concrete audit facets; keep project
hostnames, variable lists and rollout commands with that owner.

## Plugin and Skill Architecture

For full architecture documentation (core concepts, installation flow, data flow, common misconceptions, best practices), see [references/plugin-architecture.md](./references/plugin-architecture.md).

## Plugin and Skill Troubleshooting

For systematic debugging steps (common errors, debugging process, pitfalls, real-world examples), see [references/plugin-troubleshooting.md](./references/plugin-troubleshooting.md).

For maintainer source/install/catalog drift, use **Testing Skills Locally** above.
Identify the failing layer before updating a marketplace or reinstalling a plugin.

## Cloudflare mail operations

For Pages custom-hostname failures or signed delegation moves, enter [Cloudflare Troubleshooting](cloudflare-troubleshooting/SKILL.md) and its [custom-domain procedure](cloudflare-troubleshooting/references/pages-custom-domain.md). For a failure confined to one recently moved hostname, [Tunnel Doctor](tunnel-doctor/SKILL.md) selects its local-path comparison; keep mutation authority and recovery with the selected owner.

For domain forwarding diagnosis, use [Email Routing](cloudflare-troubleshooting/references/email-routing.md) through the owning Cloudflare Skill. Keep its endpoint sequence and delivery evidence contract in that reference.
