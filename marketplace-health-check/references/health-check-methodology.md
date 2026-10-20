# Health-Check Methodology

The reasoning and real failure cases behind the judgment principles in SKILL.md. Read this before acting on PII or PR/issue findings — the rules look obvious in the abstract, but each one exists because the obvious-looking move was *wrong* in a real run. (Cases are described abstractly on purpose: naming the real leaked values here would re-leak them, which is the anti-target rule below.)

## Counter-Review: agent findings are hypotheses, not conclusions

A fan-out of inspectors is fast and broad, but breadth comes with noise. Each inspector is good at *finding* things and bad at *weighing* them — it lists every theoretically-possible problem without distinguishing a hypothetical edge case from a live one. So the inspectors' output is a risk list, not a verdict. Reporting it verbatim floods the user with noise and, worse, can launder a wrong fix into an action.

Before reporting any high/critical finding, run it through these questions:

1. **Probability** — does this really happen, or is it a fictional edge case?
2. **Cost** — what does fixing vs ignoring each cost?
3. **Real scenario** — does it actually bite in this repo's real usage?
4. **Verifiable** — can a one-line command confirm or refute it right now?

Then verify the survivors with a direct command (grep the value, `sed -n` the line, `gh repo view` the state). Failure modes this catches:

- **False alarms** — a flagged "broken reference" that's actually an illustrative example; a "secret" that's a documented public placeholder; a `version` line inside a skill that *teaches about* versioning.
- **Wrong recommendations** — the more dangerous case, where an inspector correctly finds a real problem and proposes a fix that makes things worse.

### Case: the anti-target recommendation (rejected)

In the run this skill was distilled from, the security inspector correctly found real private values in shipped examples — and then recommended adding those exact values into the repo's own public `.gitleaks.toml` so future commits would be caught. That is backwards. `.gitleaks.toml` lives in the PUBLIC repo, so a list enumerating the owner's real private domains/handles is itself a published target map. Sanitize the value in place, AND put the *detection rule* in the owner's PRIVATE global guard, which already scans future diffs. Verifying that global guard's coverage (it already had the domains; it lacked the names) is what converted a plausible-but-wrong recommendation into the right action. Relayed verbatim, it would have shipped a target list.

## Anti-target: never publish the thing you're hiding

A public allowlist/denylist that names real private assets defeats itself. This applies to `.gitleaks.toml`, to "forbidden domains" comments, to any in-repo file in a public repo. In the public repo, only ever *remove* the value (replace with `example.com`, a neutral placeholder, `<user>`); never *enumerate* it. Detection rules for real private values belong in a private guard outside the repo. The same logic is why this very methodology file describes its cases abstractly.

## History: working-copy sanitization is not a history scrub

Sanitizing a file cleans the current version. But a leak that was committed earlier (pre-existing) still sits in git history — `git show <old-commit>:<file>` reveals it. The honest report says: "current version clean; the value remains in history." A history rewrite (`git filter-repo` + force-push) is a separate, high-risk decision — it rewrites every commit hash and breaks every fork's sync, and the value is likely already forked/cached anyway, so the benefit is limited. Never rewrite history unprompted; present it as an option with its full cost, and let the owner decide (in practice they usually keep history and accept the residual exposure).

## Interpret public scan evidence and isolate scanner writes

Treat `.security-scan-passed` as a local, content-bound scanner receipt. Consult [Skill Creator's packaging policy](https://github.com/daymade/claude-code-skills/blob/main/daymade-skill/skill-creator/scripts/packaging_policy.py) before interpreting its availability: the public distribution excludes it. A public clone/package with no marker is normal and reveals no scan history. A present marker does not establish semantic sanitization: real names, private assets and transcript fragments may match no secret pattern.

Run available generic secret/PII checks, then semantically read samples containing production-like examples. Record scanned paths, scanner exits and samples read. Distinguish confirmed exposure from placeholders. Keep the owner's private asset-value guard optional for this public audit; if unavailable, state that specific scope limit while completing the generic checks. Do not publish private detection values or claim those values were checked.

Before using a scanner that writes a marker, load [Skill Creator's materialization procedure](https://github.com/daymade/claude-code-skills/blob/main/daymade-skill/skill-creator/references/materialization-budget.md). Declare exact immutable input paths, the cumulative budget, reserve and owner; use prepare → run → finish. Execute the scanner from the locked creator project against the isolated skill arm, inspect the scan output, and finish after success or failure. Independently compare source content/modes before and after; never scan a shared checkout and attempt to undo the writes with Git. If the required generic scan cannot run safely, mark that dimension `not_checked` and retain what was checked.

## The broken-install-command bug class

A recurring, high-leverage doc bug in a suite-based marketplace: install instructions that name a SUITE MEMBER as if it were a standalone plugin. `claude plugin install <member>@<marketplace>` FAILS — only the suite plugin is installable; members are invoked as `<suite>:<member>`. It bites hardest on the flagship skill's front-door command (the first thing a visitor copy-pastes), so a broken one is HIGH severity, not cosmetic. The check is mechanical: for every install command, confirm the named plugin is a top-level marketplace.json entry, NOT a name that only appears inside a suite's `skills[]` array. Internal inconsistency (one section correct, another wrong) is the tell that it's an oversight, not a design choice — and a sign the fix is doc-only, not a re-architecture.

## Apply the current release and contribution owners

Read [release readiness](https://github.com/daymade/claude-code-skills/blob/main/daymade-skill/skill-creator/references/release-readiness.md) for shipped-change classification, registered plugin identity and release checks. Read [CONTRIBUTING.md](https://github.com/daymade/claude-code-skills/blob/main/CONTRIBUTING.md) for accepted contribution types and maintainer follow-up. Classify PRs under those current contracts rather than copying a universal “every file change requires its own version” rule into the audit. Keep third-party merge decisions with the human owner even when the patch looks correct.

## Promotion is declined by default

Third-party promotion — "add my external directory", "list my tool", revenue-share backlinks, a new "Community Skills" section — is declined per the repo's standing promotion-decline policy — a reference doc at the repo root, outside this skill's bundle. The repo is a personal curated marketplace, not an ecosystem directory. Decline politely with the policy's template; the contributor's own repo/marketplace already works standalone. This is the dominant pattern in the open-PR/issue queue, so triaging it correctly is what clears most of the backlog — but it's outward-facing, so surface the decline list to the owner rather than commenting on PRs/issues directly.
