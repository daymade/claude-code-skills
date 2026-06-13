---
name: marketplace-health-check
description: >-
  Run a full 6-dimension health check of this Claude Code skills marketplace repo — code/script
  safety, documentation/SSOT consistency, security/PII leaks, open-PR triage, open-issue triage,
  and marketplace-manifest integrity — via a parallel fan-out Dynamic Workflow, then verify the
  serious findings and report them by priority. Use this whenever the user asks to check the repo,
  run a health check, do a full sweep/audit before a release, 全面体检, 检查仓库状态, 看看仓库健康吗,
  审计一下仓库, or asks whether the PRs / issues / docs / versions / PII are in good shape across the
  board — even if they never say the word "workflow". Reach for it for any broad "is this whole repo
  OK" request, not just one-file checks.
---

# Marketplace Health Check

Run a comprehensive, evidence-based health check of this Claude Code skills marketplace repo using a parallel fan-out Dynamic Workflow. Six independent inspectors cover, in parallel:

1. **Code & script safety** — dangerous deletes, NO-FALLBACK secret leaks, hardcoded real paths, bare `except`, injection, missing shebangs
2. **Documentation / SSOT consistency** — version coherence across marketplace.json / README×2 / CHANGELOG / git release, skill & plugin counts, broken references, derived-value drift
3. **Security / PII** — keyword-free leaks gitleaks can't catch (real names, private domains), the `.security-scan-passed` marker gap, case-file audits
4. **Open-PR triage** — classify every PR (worth-merging / needs-changes / decline-as-promotion)
5. **Open-issue triage** — real bugs vs skill-requests vs promotion, plus the broken-install-command bug class
6. **Marketplace-manifest integrity** — `check_marketplace.sh` + `check_doc_skill_lists.py`, orphans, suite registration

Then YOU verify the serious findings and report by priority. The bundled script (`scripts/repo-health-check.workflow.js`) is the proven, ready-to-run workflow; this file is how to run and interpret it.

## Why a workflow — and why it MUST run inline

The six dimensions are independent, so fanning them out across six parallel agents is far faster than one agent sweeping serially, and each inspector stays focused on one concern with its own structured output.

**This skill must run inline (no `context: fork`).** It orchestrates parallel agents through the Workflow tool, and a forked subagent cannot spawn subagents or launch a workflow — running it forked would silently break the fan-out. The Workflow tool also requires explicit user opt-in; a user asking to "run the health check" IS that opt-in, so proceed.

## How to run

### Step 1 — Scout the current scale (one quick pass, shared by all six agents)

The workflow script takes an `args` object so all agents share one accurate snapshot instead of each re-discovering it. Gather:

```bash
gh repo view --json nameWithOwner,stargazerCount,isPrivate | jq -c .
echo "skills: $(find . -name SKILL.md -not -path '*-workspace/*' | wc -l | tr -d ' ')"
echo "open PRs: $(gh pr list --state open --json number | jq length)"
echo "open issues: $(gh issue list --state open --json number | jq length)"
grep -A1 '"metadata"' .claude-plugin/marketplace.json | grep -oE '"version": "[^"]*"' | head -1
git rev-parse --short HEAD; gh release view --json tagName -q .tagName 2>/dev/null
```

Confirm `isPrivate: false` before treating PII as a publishing risk — the whole point is that this is a PUBLIC repo.

### Step 2 — Launch the workflow

Read the bundled script and launch it **inline via the `script` parameter** (pass its contents, so there's no dependency on where the skill is installed):

```
Workflow({
  script: <full contents of scripts/repo-health-check.workflow.js>,
  args: { repo: "<owner/name>", scale: "<one-line summary from Step 1>" }
})
```

It runs the six inspectors in parallel (~15-20 min, ~400-500k output tokens — tell the user the cost up front) and returns `{ checks: [...] }`, one structured result per dimension: `health` + `summary` + `findings[]` (each with severity / title / detail / location / recommendation) + `stats`.

While it runs you can do other useful prep, but don't start editing files the inspectors are reading.

### Step 3 — Counter-Review the serious findings BEFORE reporting

**Agent findings are HYPOTHESES, not conclusions. Never relay them verbatim.** For every `high`/`critical` finding, verify it yourself with a quick command — grep the leaked value, `sed -n` the broken line, `gh repo view` the claimed state — confirming it's (a) real, (b) located where the agent says, and (c) not over-reach. This catches false alarms AND, just as important, agent *recommendations* that are actively wrong. (In the session this skill was distilled from, a security inspector recommended adding the real private domains into the public `.gitleaks.toml` — an anti-target move that had to be rejected; see the methodology reference.)

Filter every finding through four questions: **probability** (does it really happen?), **cost** (fix vs ignore), **real scenario** (does it bite in practice?), **verifiable** (can a 1-line command confirm or refute it?).

## Report format

Lead with the table, then layer by priority. Classify — don't dump:

- **One-line verdict + a 6-dimension health table** (good / minor-issues / needs-attention / critical per dimension)
- **🔴 Must-fix** — each VERIFIED high/critical, with exact location + a concrete fix
- **🟠 Backlog** — PR/issue triage outcomes, scan-marker gaps (decisions, often outward-facing — flag that they affect external contributors)
- **🟢 Optional** — low/info nits, one line each
- **💡 Key insights** — the meta-findings worth surfacing (a structural blind spot in tooling, a recurring bug class)

Tag each surfaced item ✅ real / ⚠️ partly / ❌ false-alarm. Most raw agent output is noise; your job is to surface the real risks the owner didn't already know, not to forward 25 findings for them to sift.

## Judgment principles

Apply these when interpreting findings and proposing fixes. Full reasoning + the real failure cases behind each are in [references/health-check-methodology.md](references/health-check-methodology.md) — read it before acting on PII or PR/issue findings.

- **Anti-target**: never "fix" a PII leak by listing the real value in a public allowlist (e.g. the repo's own `.gitleaks.toml`) — a public list enumerating real assets is itself a leak. Sanitize the value in place; detection rules for real private values belong in the owner's private global guard, not in this public repo.
- **History note**: sanitizing the working copy cleans the *current* version, but a pre-existing leak still sits in git history. Flag the history exposure honestly; a history rewrite (force-push) is a separate high-risk decision that affects every fork — never do it unprompted.
- **Scan marker = necessary-not-sufficient**: a `.security-scan-passed` marker means "no known-format secret was found", NOT "sanitized". It is blind to keyword-free leaks, so pair it with a human/semantic read of any skill shipping real-data examples.
- **Mandatory version bump**: any change to a skill's files requires bumping that skill's `version` in marketplace.json (and a CHANGELOG entry). External-contributor PRs almost always miss this — flag it, don't merge without it.
- **Promotion is declined by default**: third-party directory / tool / marketplace promotion PRs and issues are declined — the repo is a personal curated marketplace, not an ecosystem directory. The decline-policy template is a reference doc at the repo root (outside this skill's bundle).

## Bundled resources

- `scripts/repo-health-check.workflow.js` — the six-inspector Dynamic Workflow. Run it via the Workflow tool's `script` param (Step 2). Edit it when you add/retire an inspector dimension.
- `references/health-check-methodology.md` — the Counter-Review filter, reporting discipline, and the anti-target / history / scan-marker / decline rules, each with the real failure case that motivated it.

## Next step

After delivering the report, the typical follow-ups are owner decisions, not automated actions — fixing the verified HIGHs (sanitize PII, correct broken commands), or triaging the PR/issue backlog. Surface them as options; don't auto-fix or auto-comment on PRs/issues without the user's go-ahead, since those are outward-facing and affect external contributors.
