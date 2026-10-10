---
name: existing-skill-migration
description: >-
  Preserve old runtime jobs, classify every delta and verify the migration review. Read before the first existing-Skill edit; use the concurrent section when sharing a checkout and the reference check when writing pointers or rules.
---

# Preserve an existing Skill through edits

Before the first existing-Skill edit, read preservation and the migration gate. After editing, execute compare/classify/verify from that gate. Read the concurrent-session section when another writer shares the source. Read reference-and-self-application only when the edit writes a pointer or normative rule. Clear this static review, then complete the required task-result gate defined in [change verification](change-verification.md#fix-required-acceptance-before-selecting-evidence) before claiming the edit complete.

## Contents

- [Preservation and delta classification](#preservation-and-delta-classification)
- [Concurrent sessions on the same skill repo](#concurrent-sessions-on-the-same-skill-repo)
- [Existing-skill migration gate](#existing-skill-migration-gate)
- [Validation and escalation probes](#validation-and-escalation-probes)
- [Reference-and-self-application check](#reference-and-self-application-check)

## Preservation and delta classification

4. **Preserve before you compress an existing skill.** Updating an existing skill is a migration, not a blank-page rewrite. Before the first edit, capture the auditable source bundle with the audit tool's `snapshot` command, or reconstruct it from an explicit Git ref; an arbitrary copy plus a provenance label is not a baseline. Inventory runtime capabilities, trigger contexts, interfaces, references, and eval coverage. Progressive disclosure and concision authorize moving or deduplicating content; they do not authorize silently deleting behavior. After editing, run `scripts/audit_skill_regression.py` and classify every unmatched old unit. A runtime contract that survives only in `evals/`, tests, or an unlinked reference is still lost. Do not call the update complete while any candidate is unclassified or any true gap remains unfixed. The same logic governs *reversals*, not just deletions, and covers any prior commitment — not only the ones carrying a date and a name: **overturning a decision already made is a proposal, never a side effect.** Say it out loud and get it accepted. A silent rewrite is worse than a silent deletion, because it destroys the artifact and the evidence that could have caught it in one move — and it blinds every downstream reviewer (see #5).

   **Classify each intended delta before editing; “compression” is a claim of behavioral equivalence, not a synonym for “shorter.”** For every old user scenario, a fresh agent must still be able to find the trigger, decision inputs, supported action, stop/confirmation point, impact/recovery boundary, and verification path. Use these names as a separate change-type label in the plan, review, and changelog; record the label in each regression candidate's reason/semantic review while keeping the audit tool's `disposition` field to the exact Step 4 enum:

   | Change type | Definition | Required handling |
   |---|---|---|
   | **Lossless compression** | Only representation changes: relocate detail into a directly reachable bundled reference, deduplicate against a packaged canonical source, or shorten wording while preserving every runtime contract above | May be called compression; prove scenario reachability, not just string survival |
   | **Capability retirement** | A previously executable job or action is no longer available | Not compression; name the retired capability, obtain traceable user approval, and publish the boundary |
   | **Scope narrowing / boundary change** | Fewer inputs, targets, environments, or modes remain supported; an execution branch becomes analysis-only | Not compression even when safer; surface and publish the boundary/trade-off, then obtain traceable approval unless the user already requested this exact narrowing |
   | **Workflow or safety redesign** | Commands, sequence, confirmation, side effects, recovery, or success checks materially change | Not compression; surface the new contract and trade-off, obtain traceable approval unless the user already requested this exact redesign, then verify it independently of preservation |
   | **Bug fix / factual correction** | The implementation or prose is brought back to an explicit existing contract or current authority | Not compression; use the narrow authority or deterministic regression that decides it |
   | **Lossy summarization** | Exact conditions, commands, decision semantics, or execution exits disappear without a runtime-reachable equivalent | Regression, not optimization; restore it or reclassify it through an approved row above |

   Deduplication counts as lossless only when the canonical source ships with or is reliably available to the skill **and** SKILL.md tells the runtime reader when to load it. “The idea still exists in tests, a changelog, an installed sibling skill, or the author's memory” is not compression. If one patch contains several types, list them separately; never let the compression label launder a retirement or redesign.

## Concurrent sessions on the same skill repo

Preserve a current immutable baseline and avoid writes that clobber another session’s work. Apply these concurrent-session rules:

1. **Baseline from a git ref, not from the working tree**, whenever the repo is clean at task start: `git archive <HEAD-sha> <skill-dir> | tar -x -C <workspace>/skill-before` and pass `--baseline-origin git-ref:<sha>` to the audit. A tree snapshot taken minutes before someone else's commit is a baseline for a tree that no longer exists. **Extract into a fresh, non-existent directory.** Into an existing one, `tar -x` silently overwrites same-named files and leaves files the archive doesn't contain untouched — a mixed snapshot with zero signal at extract time, which `compare` later rejects as not matching the ref. Same trap, other command: `mv <dir> <existing-dir>` nests instead of replacing — and where `mv` is aliased to `mv -i`, a target-already-exists rename prints one prompt line and defaults to *not* happening, with exit 0 either way (verified by experiment).
2. **Re-read before write** when a write is rejected or any time has passed: diff what changed (`git log --oneline -3`, `git show <new-commit> --stat`), fold the other session's intent into your version — their edit usually has a reason — and only then write.
3. **Check HEAD *and which branch you are on* before committing.** `git log --oneline -1` catches a moved SHA: if it moved since your baseline, re-run the regression `compare` against the new ref before `verify` — the audit tool will reject a stale review anyway ("after skill changed"), so catching it yourself saves a round. But a sibling session can do something worse than advance HEAD: **it can switch the branch out from under you**, because a checkout is worktree-wide. Real sequence — `checkout -b feat/x`, edit for a while, and meanwhile another session ran `checkout main` + `pull`; the commit then landed on **main**, violating the repo's "never commit directly to local main" rule while the feature branch still pointed at the old base. So add `git branch --show-current` to the pre-commit check, not just the SHA. When it has already happened, `git reflog` is the authoritative reconstruction (it records each `checkout: moving from X to Y` with order), and the repair — **given a clean worktree** — is `git checkout -B <feature> <your-sha>` followed by `git branch -f main origin/main`: both are ref moves that never touch the working tree, so neither can destroy a parallel session's uncommitted work the way `reset --hard` would.
4. **Stage only your own paths** (`git add <skill-dir> <registry-file>`), never `git add .` — the sibling session's uncommitted work must not ride along. (Already the rule for packaging; doubly load-bearing under concurrency.)
5. **One version bump per session outcome**, not per editing round: consecutive same-session rounds on one skill collapse into a single bump — unless an intermediate state was already consumed (committed + pulled by the user or another session), which makes each consumed state its own version.
6. **Co-releasing another session's change in your PR is a contract, not a courtesy.** When two sessions' work lands in one release (their file riding in your commit): (a) ownership stays with the author — you stage their file, but the commit message names both changesets and who authored which; (b) read their full diff before staging — it accumulated across their rounds, not just their last message; (c) establish the 代改 (edit-on-their-behalf) fallback **explicitly before you need it**: who may edit their file, with what commit note, and the clobber rule (re-read the file state immediately before editing; never assume it is unchanged); (d) one release, not two — merge changelog entries additively (keep both authors' lines; never `--ours`/`--theirs`); (e) sanity-run their change yourself before it ships in your name — 2026-09-19: the staged co-shipped script had a release-blocking bug invisible in its author's environment (the documented invocation plus a color-forced environment broke it; caught only by running it in the staging session's own environment); (f) send the PR link back to them when it merges. **When the same file carries both sessions' uncommitted changes, never `git add` the whole file into one commit: branch from the clean ref, apply only your own sections to the clean version, and let the two PRs merge separately** (2026-09-19: a mixed working tree would have double-landed the other session's discipline #1 addition, colliding at merge; the fix was restore-from-ref plus selective re-application).

## Existing-skill migration gate

**Existing-skill migration gate — required before the first edit:**

1. Capture the complete current bundle before editing. For a non-Git or dirty
   source, use the tool so the snapshot carries a verifiable provenance manifest:

   ```bash
   cd <skill-creator-path>
   uv run --frozen python -m scripts.audit_skill_regression snapshot \
     --source <path/to/skill-folder> \
     --output <workspace>/skill-before
   ```

   For a clean Git-tracked source, materialize the directory from the chosen ref:

   ```bash
   mkdir -p <workspace>/skill-before   # tar -C requires the target to already exist
   git -C <repo-containing-the-skill> archive <ref> <skill-dir-relative-to-repo-root> \
     | tar -x -C <workspace>/skill-before
   # lands at <workspace>/skill-before/<skill-dir>/SKILL.md — one level deeper than
   # the snapshot subcommand's output, because `git archive` preserves the path
   # prefix; --before in step 3 is <workspace>/skill-before/<skill-dir>, not
   # <workspace>/skill-before itself.
   ```

   Include SKILL.md, references, scripts, assets, workflows, and existing evals—not
   just the main prompt. Never copy the already-edited tree and label it "before".
   New snapshots record their inclusion policy so later verification uses the same
   source boundary. For local runtime authorization files, required configuration
   templates, legacy records, and verified ZIP archives, follow
   [source snapshot archives](source-snapshot-archives.md). Do not remove
   included files during handoff and continue using the original tree hash.
   **Use a directory nothing has extracted into before** — reusing one that already
   has content from an earlier run lets `tar -x` silently overwrite same-named files
   while leaving stale files the new archive doesn't contain untouched, producing a
   mixed snapshot with zero signal at extract time (`compare` only catches it later,
   indirectly, as a tree-hash mismatch). See "Concurrent sessions on the same skill
   repo" above for the fuller version of this trap, including the `mv`-based variant.
2. Inventory the old skill's actor/jobs, trigger contexts, runtime contracts,
   commands/flags, failure and recovery cases, page/domain variants, bundled
   resources, and eval coverage. Add preservation cases for important old edge
   behavior before a structural rewrite.
3. After editing, generate an old-vs-new review:

   ```bash
   cd <skill-creator-path>
   uv run --frozen python -m scripts.audit_skill_regression compare \
     --before <workspace>/skill-before \
     --after <path/to/skill-folder> \
     --output <workspace>/skill-regression-review.json \
     --baseline-origin pre-edit-snapshot
   ```

   If the old directory was reconstructed from Git, replace the final flag with
   `--baseline-origin git-ref:<ref>`. The tool resolves the ref to an immutable
   commit and verifies every included file and executable bit against that tree.

   **Renaming or moving the skill directory itself** (not just editing its
   contents) changes `--after`'s path, which both baseline modes use for
   identity — `compare` rejects that by default (on the assumption `--before`/
   `--after` were mismatched by accident) with `pre-edit snapshot source
   identity does not match the edited skill`. Add `--renamed-from <old-path>`
   (the path `--source` pointed at for `snapshot`, or the skill's old path
   relative to its repo root for `git-ref:`) to declare the rename explicitly;
   the identity check then verifies that path instead of `--after`, while the
   content/tree-hash check is untouched, so an actually-mismatched pairing
   still fails. **Pass `--renamed-from` as an absolute path.** Every path this
   command takes resolves relative to the current working directory when given
   as relative — not relative to `--after`, and not relative to each other —
   and `--renamed-from` typically names a directory that no longer exists (it
   was renamed away), so there's no existence check to catch a wrong
   resolution the way there is for `--before`/`--after`; it just fails deeper,
   confusingly. This bites skill-creator's own edits in particular: `cd
   <skill-creator-path>` above is skill-creator's own repo, which is usually a
   *different* repo from the skill being audited, so a relative
   `--renamed-from` silently resolves against the wrong one.

4. Review every candidate. Use exactly one disposition and record concrete
   evidence/reason: `preserved_or_moved`, `intentional_sanitization`,
   `intentional_boundary`, `removed_by_explicit_user_request`, `not_reusable`,
   or `true_gap_fixed`. Runtime capabilities cannot use `not_reusable`; moving a
   runtime capability outside this skill requires the owning destination, current
   boundary evidence, and traceable user approval. Explicit retirement must also
   quote/trace the user's approval. Preserved/sanitized/fixed claims must point to
   a real current file and line and include a short `contains` quote that the
   verifier can locate nearby. File-level candidates use the current file
   fingerprint plus a named semantic review explaining why behavior survived—the
   fingerprint alone proves file identity, not capability preservation.

   Don't hand-edit the review JSON or rewrite the same filler script each round —
   the `classify` subcommand does the mechanical part (locates the quote's line
   in the destination file, fills evidence/semantic_review, fail-fasts on a
   missing quote or a too-short reason). You still author every disposition and
   reason; it only types them in:

   ```bash
   uv run --frozen python -m scripts.audit_skill_regression classify \
     --review <workspace>/skill-regression-review.json \
     --after <path/to/skill-folder> \
     --map <workspace>/dispositions.json \
     --reviewer "<who-reviewed>"
   ```

   where `dispositions.json` maps candidate index (or id) to
   `{"destination": "<rel-file>", "needle": "<verbatim current quote>",
   "reason": "<why this counts as preserved/sanitized/…>",
   "disposition": "preserved_or_moved"}` (disposition defaults to
   `preserved_or_moved`; file-level candidates need only destination + a 40+
   char reason — the fingerprint is computed for you). **Copy the needle out of
   the destination file (Read/grep/sed), never type it from memory** — the lookup
   is exact-match and fail-fasts on a missing quote, and the two ways a hand-typed
   needle actually fails are full-width vs half-width punctuation (`：` vs `:`) and
   memory-paraphrased near-synonym characters (`也` vs `都`) — both escape
   self-review, and both get caught only by the tool rejecting your whole map (one
   map rejected twice in a row for exactly those two reasons).

   **The needle proves a line survives, not that a concept survives.** A
   `heading` candidate's needle can match any line in the new file while the
   *section it titled* — the heading plus its body content — has been scattered
   across other sections or compressed beyond recognition. Text-level survival
   is not semantic survival. For every `heading` candidate, after the needle
   passes, additionally verify: (a) the new file still has a section covering
   the same topic (find the corresponding heading or content block by meaning,
   not by string match), and (b) the new section's body is not trivially smaller
   than the old one — count the old section's non-blank lines and compare with
   the new section's. A section whose body shrank by more than half needs a
   `semantic_review` explaining what was deliberately compressed and why the
   compression is lossless. Skipping this check is how a restructure reports
   "162/162 preserved" while a named principle the user later asks about has
   silently lost its dedicated section (real case 2026-08-30: an "Outcome-first
   gate" section was scattered into a summary table row; every needle passed;
   the user had to ask "有没有丢失东西" to surface it).
5. Verify the completed review. Hashes make the review stale after any further
   edit, so regenerate and reclassify when the candidate changes. A passing
   verification writes `.skill-regression-reviewed`, a content-bound local status
   receipt. It helps detect later edits, but it is deliberately not standalone
   packaging authority; packaging re-verifies the completed review itself:

   ```bash
   uv run --frozen python -m scripts.audit_skill_regression verify \
     --before <workspace>/skill-before \
     --after <path/to/skill-folder> \
     --review <workspace>/skill-regression-review.json
   ```

What success looks like at each gate step (real output, so silent failure is recognizable):

   ```
   $ … compare …
   Regression audit: 8 candidate(s), 371 exact preservation(s)   # exit 1 = candidates to review
   $ … classify …
   Classified 8 candidate(s).                                    # exit 1 = some still unclassified
   $ … verify …
   Skill regression review passed.
   Scope: static preservation; behavior and performance were not assessed.
   Regression attestation created: .skill-regression-reviewed    # exit 0 = static review cleared
   ```

Treat this receipt as static preservation evidence, not completion of the
[required task-result gate](change-verification.md#fix-required-acceptance-before-selecting-evidence).
The verify CLI reports `scope: static_preservation`, `behavior: not_assessed` and
`performance: not_assessed` in JSON; the default output states the same boundary.

`compare` returning 1 means review candidates exist, not that the tool failed;
2 means invocation/runtime failure. The tool proves exact movement and interface
preservation, but deliberately refuses to infer semantic equivalence from fuzzy
word overlap. A generic phrase such as “check permission denied” cannot silently
replace a precise signed-in-without-role contract. Also inspect candidates marked
`only_outside_runtime`: runtime behavior present only in evals, tests, or an
unreachable reference is absent from the normal invocation path.

## Validation and escalation probes

**Validate immediately after every SKILL.md edit — don't wait for packaging (Step 7).** The failure this catches early is real: a frontmatter description written as an unquoted YAML scalar parses fine in Claude Code's lenient parser but breaks in strict parsers (codex reported `invalid YAML: mapping values are not allowed` on a skill that had been shipping for months), and a ` #` inside an unquoted description doesn't even error — it silently truncates everything after it, so the trigger keywords vanish while every scan stays green.

```bash
cd <skill-creator-path>
uv run --frozen python -m scripts.quick_validate <path/to/skill-folder>
```

**Write the description as a YAML block scalar** (`description: >-` followed by an indented paragraph) whenever it contains `: ` or ` #` or spans multiple sentences — block scalars tolerate both characters natively — the recommended convention for every new or edited description since the incident above.

**When updating an existing skill**: Scan every existing reference and bundled
resource for corresponding updates, then pass the migration gate above. Moving a
contract requires a direct runtime pointer from SKILL.md; an eval or changelog is
not a replacement.

The next three checks are **escalation probes, not unconditional scope expansion**. If acting on one would add or materially change a capability, workflow branch, output contract, script behavior, dependency, permission, or external write, stop and reclassify to Tier 3 before changing the skill. Tier 1 and Tier 2 may inspect these questions, but they do not acquire new deliverables from them.

**Scripts check**: Before calling the edit done, ask: *what code did the source conversation (or the eval transcripts) write — that every future invocation would otherwise rewrite?* When the selected tier already authorizes that capability work, bundle it into `scripts/` (parameterized, sanitized) and change the docs to point at it. Otherwise record the signal as a Tier 3 proposal and do not bundle it as a Tier 1/2 side effect. The division of labor: **scripts carry the execution, docs carry the understanding** — a skill whose method lives only in prose re-pays the full authoring cost on every run. This check exists here, in the edit step, precisely because paths that skip the eval loop (conversation distillation, direct edits) never reach the eval-transcript version of this check in "Improving the skill".

**Component-shelf check (the same question, asked of artifact-EMBEDDED fragments)**: the Scripts check covers code the *skill* executes; artifact-generating skills (report pages, decks, documents) also accumulate fragments their *outputs* embed — an image-overlay widget, a sticky nav, a chart config, a CSS block. If successive outputs each hand-write a similar fragment, that is the same repetition signal pointing at a different shelf. Before adding a `components` subfolder or registry reference, apply the escalation rule above; Tier 1/2 surface the proposal but do not create the component capability. When Tier 3 is authorized, what turns a snippet into a shelf component is the contract around it: (a) **verbatim-embed block** — BEGIN/END markers copied whole into the artifact, zero dependencies, so single-file artifacts stay self-contained; (b) **registry entry** stating the interaction contract (triggers, key bindings, close behavior, edge cases) and provenance — which delivered artifact it came from, when the user approved it; (c) **admission gate** — only fragments the user has actually used and approved enter (the approved-corpus discipline applied to interactions; unapproved-but-pretty stays out); (d) **behavior frozen, skin adjustable** — calibrated behavior and key bindings are the contract and must not drift between runs, while colors and sizing may follow the artifact's register; (e) **write-back loop** — a fragment invented for one artifact is promoted to the shelf in the same session its approval lands. The reason this matters beyond token savings: hand-rewritten fragments *drift* — each rewrite subtly changes key bindings, close behavior, counters — and for a user who reads these artifacts daily, interaction consistency IS the product experience. In the user's founding words for the first such shelf: 交互形式要沉淀下来、可复用、有复利，代表一致的交互喜好 (2026-07). Real instance (project fingerprints removed): a report-page skill's lightbox-gallery component (image overlay: ←/→ cycles the group, ESC closes, in-place zoom, n/N counter) with its interaction-components registry reference — extracted the same session the user corrected jump-style references, and verified with an automated click-through test before shipping. See methodology Case 17.

**Pipeline check**: Consider whether this skill's output naturally feeds into another skill, and whether an existing skill should chain *into* this one. Adding or materially changing a "Next Step" handoff or pipeline contract requires Tier 3 reclassification before the edit; Tier 1/2 may surface the proposal but must not add it in passing.

## Reference-and-self-application check

**Reference-and-self-application check (the defects that survive a careful author)**: a family of failure modes that all look like finished work from the inside, and none of which is caught by re-reading harder — each needs a *mechanical* action instead. (No count is written in that opener on purpose. "Three failure modes:" is a derived number that goes stale the moment anyone appends a bullet, and counting prose is the hardest drift to catch precisely because it *does not contain the thing that changed* — renumbering greps and diffs of the list itself both sail straight past it.) They are grouped here because they share one cause: **writing an assertion and verifying it are different modes, and a single pass cannot hold both.** While you are composing, "see rule 8" *is* the claim; you are not simultaneously opening rule 8.

Unlike the three escalation probes above, this one is **not** scoped by tier — it is scoped by what you wrote. A Tier 1 fix that added no pointer and no normative rule has nothing here to do, and you do not have to judge that yourself: the corollary's script answers it in seconds by reporting `NONE prose-reference-shaped`. Wrote a pointer or a rule, at any tier? Then the bullets apply.

- **Every pointer you write, open its target and copy one line out of it — before you write the pointer.** Not "I'm confident that rule lists all three markers": paste a fragment of it — into whatever you are already producing for this step (the review note, the commit message body, your reply), somewhere a second reader could later check it against the target. A fragment you only look at is the self-assessment this sentence opens by rejecting. A wrong cross-reference is invisible on re-read, because a wrong pointer looks exactly like a right one, and the author is the one person guaranteed to "remember" what the target says. Real case: an author wrote "see Cardinal rule 3" meaning a rule about not citing stale enumerations — but the referenced document's *own* rule 3 was about sample size, and the rule actually being quoted lived in a different file; a reader following that document's established self-reference convention lands on an unrelated topic. The same editing pass also shipped a pointer whose direction was inverted ("see below" for material above) and one naming a section heading that does not exist.
- **A bare "rule N" is ambiguous the moment a file has two numbered lists.** The check is per-pointer, not per-file: before writing "rule N", run `grep -n '^N\. ' <file>` and confirm exactly one hit falls in the section you mean; if several do, name the section too. (Do **not** turn this into a file-level alarm like "does this file contain more than one list starting at 1" — on any long document that is true almost always, so it fires on healthy input and gets ignored, which discipline #6 warns is worse than no check; run it on this file and see for yourself.) In the real case a bare "rule 1" had three candidate lists and a top-down search hit the wrong one first.
- **After writing any normative rule, check it against the lines beside it — and make the check produce an artifact, not a verdict.** Read your own hunk with `git diff <base-ref> -- <file>`, using the same `<base-ref>` as the corollary below. Reading it yourself is enough here — you are not pattern-matching it, so it needs no script — but it must carry that ref: a bare `git diff` shows unstaged work only and prints nothing the moment you `git add`, which is one of the five silent-empty modes this block's own corollary was built to escape. Split the new rule into its separate clauses, and write down, per clause, the line *in that same hunk* that satisfies it. (The `scripts/reference_net.sh` in the corollary below is a different job: it lists *prose cross-references* for you to resolve. It does not hand you the hunk, and it will not tell you whether a clause of your rule is satisfied.) **A clause with no line beside it is the finding.** The tempting short version — "does my new rule pass?" — cannot fail for the person who wrote it 30 seconds ago; that is precisely what discipline #6 means by preferring a falsifiable observation to a self-assessment, so this bullet owes the same artifact it demands. Its first victim is usually the paragraph beside it. Real case: a rule was added saying "always report both the raw and the filtered count — the difference *is* the contamination", and its own worked example, in the same commit, printed only the filtered numbers. A second statement in that same diff quoted two figures without saying whether they were collected under the qualifier the neighbouring new rule had just made mandatory. The scope is small and bounded: not "re-read the document", just "does the rule I wrote 30 seconds ago pass on the lines I wrote 30 seconds ago".
- **Give every new rule one line naming who executes it and whether they actually can.** A rule the existing tooling cannot satisfy is a rule that gets skipped by people who believe they complied — the worst kind, because it produces documented false confidence. Real case: a new rule said "check both log stores"; the project's own canonical one-command triage tool hardcodes one of them, so the standard workflow returns a clean result for exactly the failure the rule existed to catch. The rule was true and inert, and did not mention the gap. **The artifact that makes this falsifiable** (without it this bullet is the one self-assessment in a block that bans them): name the tool or command that would catch a violation, then **run it once against a case you already know it should catch**. If it comes back clean on a known-bad input, you have measured that the rule is inert — write that gap into the rule itself. "Whether they actually can" answered from memory is exactly the unverified assertion discipline #6 rejects. **When no tool can decide the rule** — true for most prose and taste rules, so do not treat this as an escape hatch — the artifact is the sentence naming that: *"nothing enforces this; it holds only while someone remembers it."* That is a worse position to be in than a passing check, and saying so out loud is the point; a rule whose enforcement is silent gets assumed rather than verified. Note this bullet's own honest limit: the choice of tool and of known-bad case is still a judgment call, so it moves the unverified step rather than removing it — it is cheaper than the alternative, not free.
- **After changing a rule that uses absolute language ("always / must / never / only"), grep the whole bundle for the old form's literal — `references/`, script comments, examples — not just the file you were editing.** Absolute wording turns every surviving old prescription into a live contradiction the reader cannot resolve, and the author's edit pass only reaches the files they remembered. Real case (2026-10-10, names generalized): an "X must always go through the new gate" rule landed in a skill's SKILL.md with every SKILL.md in the repo swept, while one `references/*.md` file still prescribed the bare old command — caught only by the independent reviewer's full-bundle `git grep`, flagged MAJOR. The mechanical action costs seconds: `git grep -n "<old imperative's literal>" <base-ref> -- <skill-dir>/`, then disposition every hit — rewrite it, or name it as an explicit exception next to the new rule.
- **Corollary — your fixes are themselves a defect source, so re-check the regions you touched, after the last edit.** In a two-round review of a single change, round 1 produced eight findings; round 2 produced eight more, **seven of which were cross-reference errors introduced by round 1's fixes**. Rewriting a sentence moves the anchors around it. This is also why "it was reviewed" is not a finish line for an artifact whose readers navigate by its pointers: the review is stale the moment you act on it. The re-check is mechanical, and it is a **script**, not a command to retype: `scripts/reference_net.sh <base-ref> <file>…` (in this skill's bundle). It lists the prose cross-references among the lines you added, so you can open each target and confirm it says what you claim. Read its header before first use — it explains why it takes a base ref rather than defaulting to `HEAD`, and what it deliberately does *not* do.

**Get `<base-ref>` before you start editing, not after.** Resolve it once to a literal SHA — `BASE=$(git rev-parse HEAD)` at the moment you begin — and reuse that same value for this and for the bullet above. If you ran the existing-skill migration gate, it is the ref you already baselined against. Passing `HEAD` *later* is the trap: after you commit, `HEAD` contains your own work, the script truthfully reports `IDENTICAL`, and that is indistinguishable from having nothing to check. If you did not capture it up front, recover it (`git log`, `git reflog`, or the baseline you gave the migration gate) rather than substituting `HEAD`; the script prints a note when your base ref is also your current HEAD, but do not rely on catching it there.



**Read its verdict, not just its exit code.** The script exits 0 whenever it ran, so `$?` alone tells you nothing about what it found; the verdict line is where the answer is, and it always names one of: references found (resolve each), file identical to base, file changed but with no added lines, or added lines with nothing reference-shaped. Those are different results and the script keeps them different on purpose — the version of this check that collapsed them into one silent "nothing" is the reason it became a script. It costs seconds and does not depend on vigilance, which is what discipline #6 asks of any check worth writing. (It is a net, not a proof. Its blind spot is a pointer with no number in it — "see the section below", "as the rule above says" — so read the added lines too.)

Use [source-snapshot-archives.md](source-snapshot-archives.md) for snapshot inclusion and archive handling; use [change-verification.md](change-verification.md) to reclassify only when an actual escalation probe changes authorized scope. Review mechanics remain with [independent-review-protocol.md](independent-review-protocol.md).

For historical evidence behind these procedures, inspect [developer-casebook.md](developer-casebook.md) only when investigating that failure.

Resolve numbered standing-discipline citations using [their named owners](change-verification.md#shared-discipline-names); the owning contract supplies the conditions and stopping rule.
