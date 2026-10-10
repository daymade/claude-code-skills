---
name: publishing-and-packaging
description: >-
  Apply destination-specific sanitization, security scan, packaging, marketplace registration/versioning and requested local-host readback. Read the applicable delivery section before distribution, registry changes or a release/availability claim.
---

# Publish only the authorized deliverable

Choose sections by the requested delivery: public sanitization before public distribution, security before packaging/distribution, packaging for an archive request, marketplace for registered publication, and Ship or Iterate for requested consumption. Complete required independent review before the release boundary even when packaging is skipped. Package-only and source-only requests retain their scope; stop at verified requested delivery or report the exact unresolved consumption boundary.

### Step 5: Sanitization Review (mandatory for any public skill)

**Before this gate, when discipline #5 is due, its independent pass must have run**, and the current change's `independent-review.md` (in your private git-tracked knowledge repo — not the wiped workspace, not any repo that is or may become public or distributed) must exist **and be committed**. It is always due for a new skill; for an existing skill use the threshold in the next paragraph. A file sitting uncommitted in a git working directory is not meaningfully different from a file that was never written; `ls`/`test -f` confirms it is on disk, not that it survives. For a **new** skill this is the first step where anything leaves your hands, so it is where that discipline is actually enforced rather than merely stated — a rule that lives 1000 lines above the point of use, with nothing checking it, loses to completion-drive every time.

**For an edit to an already-published skill, the moment it leaves your hands is the push, not this step.** This gate can be answered "internal-only, skip" in one sentence, and packaging may never run at all for a docs-only change — so anchoring the review here means a skill edit can reach a public branch having passed no independent eye. Real case (2026-07): a change to this very file shipped a discovery command that could not reach three of the roots the prose beside it claimed it covered; it was merged, and only a review commissioned *afterwards* caught it. **So for an existing skill: the independent pass and its recorded artifact are due before `git push` / opening the PR — the gates that run at push (regression audit, validation, scans) all check structure, and none of them can tell you the instructions are wrong.** This inherits discipline #5's threshold unchanged: it is due when *a rule, contract, or number changed*, not for a typo or a pure reformat. Making a spelling fix wait on a review round would teach exactly the reflex #6 warns about — "this one's small" becomes the universal exemption, and then it covers the changes that mattered too.

**Not optional for a skill going to a public repo.** Private content leaks into public skills all the time, and the leaks a scanner misses are the dangerous ones — a real name in a non-English language, a verbatim line from a real transcript, a real example dropped into an illustration. Skip only if the skill is genuinely internal-only.

**Scope the pass by destination, not by topic.** Only the artifact that ships publicly — the skill bundle itself — gets sanitized. Companion documents that stay in a private repo (the incident report the skill was distilled from, internal runbooks, the project's CLAUDE.md) keep their real hostnames, paths, and timestamps: redacting those destroys their audit value, and you will end up reverting it. One distillation session went through three rounds of rework precisely because the redaction pass was applied to everything the source material touched instead of just the public skill.

**Check the destination first, and let it pre-fill the recommendation.** Run
`gh repo view --json isPrivate` on the repo the skill will live in (or read the note
`quick_validate` already printed). A private destination makes option C the default
recommendation rather than an afterthought — "assume public unless told otherwise" is
what turns a private skill's working paths into placeholders nobody asked for.

**The trigger for sanitizing is the destination's `isPrivate`, not how much the task
feels like publishing.** These come apart, and when they do the feeling wins unless you
name it. Moving content *into a marketplace skill* feels like publishing — marketplaces
are where things get distributed — so the sanitizing reflex fires even when both the
source and the destination are private repos and nothing is going anywhere. Real case
(2026-07): a migration from a project-level skill into a private marketplace skill
generalized a real config path, a real hex value and a real named example into
placeholders. `quick_validate` had printed `🔒 audience: private` on **every** run;
the author read it every time and sanitized anyway, because the *activity* read as
publication. The cost is not cosmetic — a real path is what lets the next reader go
check the value; "the project's own token file" cannot be opened.

So make it a lookup, not a judgment: **read `isPrivate` for the destination, and if it
is `true`, sanitizing requires the owner to ask for it.** A private→private move is a
move, not a release. **When neither probe answers** (no remote yet, `quick_validate` not
run), you have no lookup — fall back to treating it as public *and say so*, because the
asymmetry runs that way: an unnecessary question costs a sentence, an unnecessary leak
does not come back. And `isPrivate` reports the destination's state **today** — a skill
sitting in a private repo on its way to release gets its sanitization pass on the push
that publishes it, not on this one. If you find yourself reasoning about whether something "should"
be generalized in a private destination, that reasoning is the tell.

Resolve a missing sanitization-scope decision through
[Resolve the task before acting](../SKILL.md#resolve-the-task-before-acting).

**Sanitization process — the read-through is the method, the scan is a helper:**

1. **Read the entire skill yourself and judge semantically** (this is the real check): SKILL.md + every reference + every example. For each concrete noun / example / snippet ask "generic-placeholder-or-public-entity, or lifted-from-a-real-project/person/transcript?" Replace the latter — even if no scanner flagged it. This is the only thing that catches no-keyword leaks. Full guidance + the semantic question in [references/sanitization_checklist.md](sanitization_checklist.md).
2. **Run scanners as a cheap first pass**: the checklist's grep patterns + `security_scan.py` (Step 6). They catch obvious secrets / paths / known names fast — but "no matches" is not a pass.
3. **Replace** each finding with a generic equivalent that keeps the teaching point (real name → public figure or `<placeholder>`, real snippet → `<placeholder>`). Two rules learned the hard way: the placeholder itself must not encode the real value — `<acme-corp-domain>` leaks exactly the name it was supposed to hide; name the *role* instead (`<api-domain>`, `<upstream-provider>`). And when you script a bulk replace, give it an explicit file whitelist scoped to the skill directory — an unscoped find-and-replace will happily rewrite the project's own CLAUDE.md and force a git restore.
4. **Verify by re-reading, not by re-grepping**: re-read the changed sections and confirm no broken references.

### Step 6: Security Review

Before packaging or distributing a skill, run the security scanner to detect hardcoded secrets and personal information:

```bash
# Required before packaging
uv run --frozen python -m scripts.security_scan <path/to/skill-folder>

# Verbose mode includes additional checks for paths, emails, and code patterns
uv run --frozen python -m scripts.security_scan <path/to/skill-folder> --verbose
```

**Detection coverage:**
- Hardcoded secrets (API keys, passwords, tokens) via gitleaks
- Personal information (usernames, emails, company names) in verbose mode
- Unsafe code patterns (command injection risks) in verbose mode
- The complete shipping set is defined only by [scripts/packaging_policy.py](../scripts/packaging_policy.py). Packaging, security attestation, content hashing, and regression auditing must consume that shared policy; do not maintain a second exclusion list in prose or in a consumer-specific filter.

**What it does NOT cover** — why Step 5's read-through is still required: gitleaks and the regex rules only match *known secret formats and patterns you listed*. They are structurally blind to private content with no keyword — a real person/project name in a non-English language, a verbatim line from a real transcript, a real example lifted from your own work. A green `security_scan` means "no known-format secret was found", **not** "the skill is sanitized". Never treat it as the latter.

**First-time setup:** Install gitleaks if not present:

```bash
# macOS
brew install gitleaks

# Linux/Windows - see script output for installation instructions
```

Read the [security scanner](../scripts/security_scan.py) for executable exit
semantics; resolve findings and scan/runtime failures before distribution.

**In a private skill, a finding is information, not a work order.** The scanner cannot
tell a leaked credential from a credential that is *supposed* to be there — a template whose
whole value is that it comes pre-filled, a script pointing at the one machine it runs on.
Never auto-fix in a private repo: report what was found and let the owner choose. Option A
below ("fix automatically") is for skills headed somewhere public.

**If issues are found**, present them via **AskUserQuestion**:

```
Security scan found [N] issues in "[skill-name]":
- [SEVERITY] [file]: [description]
- ...

RECOMMENDATION: Fix automatically — these look like [accidental leaks / false positives].

Options:
A) Fix all issues automatically (Recommended)
B) Review each finding — let me decide per-item (some may be intentional)
C) Override and proceed — I accept the risk for internal distribution
```

### Step 7: Packaging a Skill

Once the skill is ready, package it into a distributable file:

```bash
cd <skill-creator-path>
uv run --frozen python -m scripts.package_skill <path/to/skill-folder>
```

For every existing Git-tracked skill, packaging is blocked until the completed
review is supplied and re-verified. A current marker is only a local status receipt,
so committing first or hand-writing a marker cannot bypass the review. The review
becomes stale on the next edit:

```bash
uv run --frozen python -m scripts.package_skill \
  <path/to/skill-folder> \
  --regression-review <workspace>/skill-regression-review.json
```

Optional output directory, and `--include-evals` to ship the root `evals/` directory (excluded by default as a development asset):

```bash
cd <skill-creator-path>
uv run --frozen python -m scripts.package_skill <path/to/skill-folder> ./dist --include-evals
```

Treat the [packager](../scripts/package_skill.py) as the executable owner of its
validation, regression-review and security prerequisites and archive creation.

### Step 8: Update Marketplace

For authorized marketplace publication, update `.claude-plugin/marketplace.json`
using the hosting repository's registration and release guide. Resolve the owning
plugin from its exact source directory before editing:

- **New member of an existing suite:** append the member's path relative to the
  suite's `source` to that plugin's nonempty `skills` array and bump the owning
  suite version. Do not add a parallel standalone plugin entry.
- **New standalone plugin:** add an entry pointing directly at the Skill source
  directory, using the shape below.

Advance `metadata.version` for catalog additions, removals or restructuring under
the hosting repository's policy. Verify exact-source registration through
[the source owner](source-location-and-activation.md), not a name grep.

Use this example only for a new standalone plugin:

```json
{
  "name": "skill-name",
  "description": "Copy from SKILL.md frontmatter description",
  "source": "./skill-name",
  "strict": false,
  "version": "1.0.0",
  "category": "developer-tools",
  "keywords": ["relevant", "keywords"]
}
```

**For updated skills**, bump only the owning registered plugin's `version`
following semver; suite members share the suite release identity and have no
separate member bump. Any change to a skill's **shipped** files — even a one-line typo fix — needs a bump: without it, `marketplace update` sees no new version, so **already-installed copies never refresh** and users keep running the old skill while your fix sits unshipped. Files that never ship are the one exception, and it is not a judgement call: `scripts/packaging_policy.py` defines that set and the repository's version gate consumes the same module, so a change confined to those paths is not a content change and needs no bump. Without that exception, retiring one local artifact would demand a release from every plugin that happened to carry one.

**Then record it in the changelog — this is the step that gets skipped.** The bump makes the
update *installable*; the entry is what makes it *findable* six months later, when someone
hits the same problem and greps for it. And a changelog that documents every other skill's
versions while silently dropping yours is worse than none at all: the gaps read as "nothing
changed there".

Match the existing entries' shape instead of inventing one — in a Keep-a-Changelog file that
is usually `- **skill-name** (\`suite\` vX.Y.Z): what broke, why, and what proves it fixed`.
Write it in the **same commit** as the bump; a changelog updated "later" is one that never
gets updated.



**Keep the registry diff minimal — it is the single file every skill shares.** A marketplace manifest is the one place where every concurrent editor collides, so an unrelated formatting change there is far more expensive than the same change anywhere else: it turns a clean three-line bump into a conflict for whoever else is mid-edit. When you script the update (parsing to JSON, mutating, writing back), the rewrite silently normalizes things the file may not have used — trailing newline, indent width, key order, unicode escaping. Round-trip discipline: re-read the file afterwards and run `git diff --stat` on it; **the only lines that may appear are the fields you meant to change.** If extra lines show up, restore the file's original convention rather than shipping the normalization (a scripted bump once added a trailing newline to a manifest that had never had one — one wasted diff line, in the file most likely to be edited by someone else at the same moment). The same instinct applies to any shared registry a skill touches: lockfiles, catalogs, index documents.

**Refresh a PR when actual conflicts, changed validation inputs or repository requirements demand it.**
An unrelated base advance alone does not require a new head or repeated checks.
For an already-pushed branch, preserve its published history by default: add commits
or merge the current base under the repository's established workflow. Rebase or
amend a pushed history only after explicit authorization for the exact ref,
consequences and recovery path. A squash-merge policy does not supply that authority.
For owned, unpushed work, use the authorized local integration workflow. Resolve
additive registry/changelog conflicts by retaining both authors' intended changes;
never discard the other contribution with `--ours` or `--theirs`.

The step people skip is the one that catches a bad resolution — **after resolving, prove the only difference from the base is yours:**

```bash
# Every version the base has vs. what your branch has; the diff must contain
# ONLY the entry you bumped. Anything else means the resolution ate someone's work.
uv run --project <skill-creator-path> --frozen python -c "
import json,subprocess
mine=json.load(open('<manifest>'))
base=json.loads(subprocess.run(['git','show','origin/main:<manifest>'],capture_output=True,text=True).stdout)
b={p['name']:p['version'] for p in base['plugins']}; m={p['name']:p['version'] for p in mine['plugins']}
print({k:(b.get(k),m.get(k)) for k in set(b)|set(m) if b.get(k)!=m.get(k)})"
```

Push normally after history-preserving integration. Only for the exact authorized
history rewrite, use the authorized lease against the independently verified remote
tip. `--force-with-lease` protects against remote drift; it does not grant permission
to rewrite already-published history. Stop when the remote tip differs or the
specific authorization/recovery path is missing.

**Plugin boundaries are not this skill's domain.** Whether to split skills into
separate plugins, how to lay out `source`/`skills`, and whether users can toggle
skills individually all belong to the packaging/distribution domain — the SSOT is
the `marketplace-dev` skill, not here. When a task actually needs those decisions:
ensure `marketplace-dev` is available (auto-install it if missing — the same way
`skill-reviewer` pulls in `skill-creator` when it needs its scripts), then read
marketplace-dev's cache-and-source-patterns reference and follow it. Don't restate
its rules here; a copy would drift.

**Renaming, relocating, or removing a marketplace entry is a breaking change** for
every user who already installed it — Claude Code does not clean up installed copies
when an entry disappears, leaving dangling installs that error on every `marketplace
update`. Treat such changes like an API deprecation: ship a migration note in the
changelog, and follow marketplace-dev's guidance for the mechanics.

For repositories with the local release gate installed, use
[release readiness](release-readiness.md) to bind committed review evidence
to the exact head before push. The gate checks persistence and coverage; it does not
replace the independent pass or determine whether a typo exemption is truthful.

**If you commit/push the skill repo yourself:** for an existing skill whose current change crosses discipline #5's rule/contract/number threshold, confirm the review artifact records this change and is committed (check its exact path with `git status` and `git log -1 -- <artifact>`, not merely whether some historical `independent-review.md` exists). A typo or pure reformat does not require that artifact; an older review never satisfies a current substantive change. Step 5's note explains why push, not packaging, is the real enforcement point for an already-published skill. Then stage only the skill's explicit paths (`git add <skill-dir> .claude-plugin/marketplace.json`) — never `git add .`; the working tree is usually full of unrelated churn that will otherwise ride into the commit (one commit swept in a pile of unrelated transcript files and had to be `git reset` and re-staged). Before pushing, confirm the repo's real visibility with `gh repo view --json visibility,isPrivate` instead of assuming from the path — a public skill repo deserves a PR + review, not a direct push to main.

### Step 9: Ship or Iterate

**When local availability is part of the requested delivery**, finish installation
and verify the target host before calling the Skill ready. Invoke `skill-governance`
and use its newly registered Skill checks. Supply the new Skill's identity from
this task, independently of the current activation whitelist; an omitted name
must not disappear from the expected set. For owned marketplaces approved for
automatic activation, use `claude-switch-models-setup` to sync the declared hosts.
Preserve explicit host-specific disables and existing router-only contracts.
Do not infer Claude availability from a Codex link, or installation from a
marketplace entry. A failed or unavailable host probe leaves local delivery
incomplete. Package-only and source-only requests retain their narrower scope.

After the requested delivery, follow [Show the result, not just the work](../SKILL.md#show-the-result-not-just-the-work)
for completion and any later refinement.

---

### Package and Present (only if `present_files` tool is available)

Check whether you have access to the `present_files` tool. If you don't, skip this step. If you do, package the skill and present the .skill file to the user:

```bash
uv run --frozen python -m scripts.package_skill <path/to/skill-folder>
```

After packaging, direct the user to the resulting `.skill` file path so they can install it.

Use [delivery-identity.md](delivery-identity.md) for formal Skill names/source links and suite-owned versions; it does not prove installation or the business result. Use [release-readiness.md](release-readiness.md) before Git publication when the repository release gate applies. These checks do not authorize a new release target or expand the user’s requested scope.

For historical evidence behind these procedures, inspect [developer-casebook.md](developer-casebook.md) only when investigating that failure.

Resolve numbered standing-discipline citations using [their named owners](change-verification.md#shared-discipline-names); the owning contract supplies the conditions and stopping rule.
