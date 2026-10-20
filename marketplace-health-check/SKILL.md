---
name: marketplace-health-check
description: >-
  Runs an evidence-based health audit of this skills marketplace repo — code safety,
  docs/SSOT, security/PII, PR/issue triage, manifest integrity — via a parallel workflow, then
  verifies findings by priority. Use for 全面体检 / 检查仓库状态 / 审计一下仓库, a pre-release sweep, or "is this
  repo OK" even without saying "workflow". Not for building marketplace.json (use marketplace-dev)
  or cache drift (use skill-governance).
---

# Marketplace Health Check

Run a comprehensive, evidence-based health check of this Claude Code skills marketplace repo using a parallel fan-out Dynamic Workflow. Use independent inspectors to cover these dimensions in parallel:

1. **Code & script safety** — dangerous deletes, NO-FALLBACK secret leaks, hardcoded real paths, bare `except`, injection, missing shebangs
2. **Documentation / SSOT consistency** — authoritative documentation checks, release-policy consistency, broken references, derived-value drift
3. **Security / PII** — keyword-free leaks gitleaks can't catch (real names, private domains), generic secret scans, case-file audits
4. **Open-PR triage** — classify every PR (worth-merging / needs-changes / decline-as-promotion)
5. **Open-issue triage** — real bugs vs skill-requests vs promotion, plus the broken-install-command bug class
6. **Marketplace-manifest integrity** — `check_marketplace.sh` + `check_doc_skill_lists.py`, orphans, suite registration

Then YOU verify the serious findings and report by priority. Use the bundled script (`scripts/repo-health-check.workflow.js`) for orchestration; this file is how to run and interpret it.

## Why a workflow — and why it MUST run inline

The dimensions are independent, so fanning them out across parallel agents is far faster than one agent sweeping serially, and each inspector stays focused on one concern with its own structured output.

Use the script's explicit maximum task budget and its runtime refusal before fan-out. Review usage cost before adding an inspector or changing that budget; do not derive the limit from the current dimension list.

**This skill must run inline (no `context: fork`).** It orchestrates parallel agents through the Workflow tool, and a forked subagent cannot spawn subagents or launch a workflow — running it forked would silently break the fan-out. The Workflow tool also requires explicit user opt-in; a user asking to "run the health check" IS that opt-in, so proceed.

## How to run

### Step 1 — Scout the current scale and share the result with all inspectors

The workflow script takes an `args` object so all agents share one accurate snapshot instead of each re-discovering it. Gather:

Resolve this Skill's installed/source directory to `<health-skill-dir>`, confirm the selected repository root, and run:

```bash
python3 "<health-skill-dir>/scripts/scout_repository.py" --repo "<owner/name>" --root "<repo-root>"
```

Read the helper's JSON and exit status; its `--help` owns the output/exit contract. It parses manifest metadata as JSON and follows the [github-ops GraphQL pagination recipe](https://github.com/daymade/claude-code-skills/blob/main/github-ops/references/api_reference.md#query-multiple-prs-with-pagination) for PRs and issues, reconciling unique items with server totals. Preserve the complete output outside the source tree so inspectors can read it; include its exact path and a concise scope summary in `scale`. Pass the helper's absolute path there too when inspectors cannot resolve the installed bundle. A failed inventory retains partial items as `not_checked`; never report those items as ALL or a failed request as zero. A later inspector may complete that exact missing inventory with the same helper and use the newly validated result.

Confirm `identity.isPrivate: false` before applying public-publication PII judgments. If visibility is unavailable, keep that judgment unknown; if the target is private, apply its actual privacy boundary. Do not change accounts, permissions or global settings to make a scout appear ready.

### Step 2 — Launch the workflow

Read the bundled script and launch it **inline via the `script` parameter** (pass its contents, so there's no dependency on where the skill is installed):

```
Workflow({
  script: <full contents of scripts/repo-health-check.workflow.js>,
  args: { repo: "<owner/name>", scale: "<one-line summary from Step 1>" }
})
```

Tell the user this launches parallel model work and consumes the current plan's usage; do not quote a fixed time/token estimate as a guarantee. Keep the host's actual permission gate. Before editing the saved script, load Claude Code's `/workflow-authoring` bundled Skill when available; consult the [official Workflow contract](https://code.claude.com/docs/en/workflows) for host prerequisites and script limits.

Distinguish launch from completion: an initial `error` means the run did not produce an audit; `async_launched` only confirms startup. Wait for that run's final completion event and inspect its returned report. On failure, cancellation or unavailable Workflow tooling, report the audit as unfinished with the missing prerequisite; do not turn a launch receipt or scout into a completed audit.

The final payload is `{ complete, checks: [...] }`. Preserve one row per expected dimension with `dimension`, `status` (`checked` / `not_checked`), the existing `health`, `summary`, `findings[]` and `stats` fields. `complete` means all dimension reports completed, including reports of critical defects; it does not mean the repository is healthy. A missing, failed or invalid inspector becomes an empty `not_checked` placeholder with `health: needs-attention`. For a schema-valid partial report, retain its findings and statistics with the same conservative health value; explain that overall repository health remains undetermined. Incomplete coverage does not retract observed findings: counter-review and report them by severity as usual.

While it runs you can do other useful prep, but don't start editing files the inspectors are reading.

### Step 3 — Counter-Review the serious findings BEFORE reporting

**Agent findings are HYPOTHESES, not conclusions. Never relay them verbatim.** For every `high`/`critical` finding, verify it yourself with a quick command — grep the leaked value, `sed -n` the broken line, `gh repo view` the claimed state — confirming it's (a) real, (b) located where the agent says, and (c) not over-reach. This catches false alarms AND, just as important, agent *recommendations* that are actively wrong. (In the session this skill was distilled from, a security inspector recommended adding the real private domains into the public `.gitleaks.toml` — an anti-target move that had to be rejected; see the methodology reference.)

Filter every finding through these questions: **probability** (does it really happen?), **cost** (fix vs ignore), **real scenario** (does it bite in practice?), **verifiable** (can a 1-line command confirm or refute it?).

## Report format

Lead with the table, then layer by priority. Classify — don't dump:

- **One-line verdict + a dimension table** with status, health and scope; keep every expected row. For `not_checked`, lead with “not checked”, name the missing evidence and recovery action, and avoid an overall healthy verdict
- **🔴 Must-fix** — each VERIFIED high/critical, with exact location + a concrete fix
- **🟠 Backlog** — PR/issue triage outcomes and incomplete checks (decisions, often outward-facing — flag that they affect external contributors)
- **🟢 Optional** — low/info nits, one line each
- **💡 Key insights** — the meta-findings worth surfacing (a structural blind spot in tooling, a recurring bug class)

Tag each surfaced item ✅ real / ⚠️ partly / ❌ false-alarm. Most raw agent output is noise; your job is to surface the real risks the owner didn't already know, not to forward raw findings for them to sift.

## Judgment principles

Apply these when interpreting findings and proposing fixes. Full reasoning + the real failure cases behind each are in [references/health-check-methodology.md](references/health-check-methodology.md) — read it before acting on PII or PR/issue findings.

- **Anti-target**: never "fix" a PII leak by listing the real value in a public allowlist (e.g. the repo's own `.gitleaks.toml`) — a public list enumerating real assets is itself a leak. Sanitize the value in place; detection rules for real private values belong in the owner's private global guard, not in this public repo.
- **History note**: sanitizing the working copy cleans the *current* version, but a pre-existing leak still sits in git history. Flag the history exposure honestly; a history rewrite (force-push) is a separate high-risk decision that affects every fork — never do it unprompted.
- **Public scan evidence**: follow the methodology reference for marker interpretation and isolated scans. Run generic checks plus semantic sample reads; missing local receipts or optional private asset rules do not establish an unscanned/unsafe public package.
- **Release and contribution decisions**: read the current [release owner](https://github.com/daymade/claude-code-skills/blob/main/daymade-skill/skill-creator/references/release-readiness.md) and [CONTRIBUTING.md](https://github.com/daymade/claude-code-skills/blob/main/CONTRIBUTING.md). Use their change classification, registered plugin identity and maintainer follow-up rules; do not invent a member version or require every contributor to do maintainer bookkeeping. External PR merges require the human owner's decision.
- **Promotion is declined by default**: third-party directory / tool / marketplace promotion PRs and issues are declined — the repo is a personal curated marketplace, not an ecosystem directory. The decline-policy template is a reference doc at the repo root (outside this skill's bundle).

## Bundled resources

- `scripts/repo-health-check.workflow.js` — the parallel inspection Dynamic Workflow. Run it via the Workflow tool's `script` param (Step 2). Edit it when you add/retire an inspector dimension.
- `scripts/scout_repository.py` — the read-only JSON scout; use its `--help` for arguments and exit semantics.
- `references/health-check-methodology.md` — Counter-Review, privacy, isolated scan handling, and contribution-policy interpretation.
- `tests/test_health_check.py` — deterministic scout and Workflow-body contract tests; run with `python3 -m unittest discover -s "<health-skill-dir>/tests" -v`. These do not replace native Workflow execution or model judgment.

## Next step

Deliver the read-only report, including unresolved coverage. Continue fixes only within the user's existing authorization; obtain any missing authorization for repository writes, external comments, third-party merges or history rewrites. An audit request alone does not authorize those actions.
