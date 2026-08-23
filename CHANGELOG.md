# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **github-sensitive-data-cleanup** (v1.1.0): commit-message channel for rewrite and verify, closing the Lesson 7 blind spot — `rewrite_history.py --message-replacements <file>` runs `git filter-repo --replace-message` in the same pass, and `verify_cleanup.py` fails on message-only leaks (#326). Follow-up independent-review fixes (#328): GBK/legacy-encoded commit messages crashed verification with an uncaught `UnicodeDecodeError`; SKILL.md rewrite command blocks (Step 4 and the script-reference section) omitted `--yes`, so a verbatim doc run exited before creating the backup; `git bundle verify` ran without `-C <repo>` and its `RuntimeError` escaped the `except`, crashing invocations from non-git working directories; and a FAILED message check now lists `commit_message_commits` hashes (first 10) instead of only a count. A docs-round review then found the same decode-crash class still open in the blob channel (`git grep`), so every subprocess decode in all four scripts is now hardened with `errors="replace"` — verified against a GBK-encoded source file containing a leak, which both channels now report instead of crashing (boundary: a UTF-8 pattern still cannot match GBK-encoded CJK bytes; that is Layer 4 semantic-review territory). `references/incident-lessons.md` gains Lesson 9 (tooling must be more robust than the repos it cleans). Review dossier archived in the author's private knowledge repo.
- **claude-code-hooks** (`daymade-claude-code` v1.49.0): turns rule 7's hookless-loop lesson into an executable **Loop Contract**. Any Stop-hook remediation or agent-driven review/wait/retry loop must predeclare an immutable lineage+failure-axis key, fire condition T, remediation R, decreasing variant V, cycle budget, and distinct success/capped exits before cycle 1. Repair commits stay inside the original lineage; independent review defaults to one initial pass plus one narrowly scoped re-review, and only a user-authorized new task can open another budget. Unrelated findings cannot reset it, while a remaining same-axis BLOCKER/MAJOR leaves the artifact visibly unshipped. Pattern E carries every contract field; Stop ceilings emit an explicit capped status, and pitfall #36 preserves the measured hookless-loop incident. Verification: one bounded with-skill replay, fresh-context review, existing-skill regression audit, quick validation, and reference-net checks.
- **claude-code-hooks** (`daymade-claude-code` v1.48.0): rule 7 gains a new closing case — **a loop can converge and still not have been worth running, and this shows up with no hook in the picture at all**. Everything rule 7 proves is that V *exists* for a hook-enforced loop; the same T → R → recheck shape recurs when an agent self-applies a prose discipline ("a substantive edit needs a fresh independent reviewer" — the exact rule the rule's own counter-example is built from) with no shell mechanism enforcing it, only the agent's own judgment deciding when to stop. Real incident: verifying one small correction in a low-stakes, single-reader document, an agent ran three full independent-review rounds instead of one — round 1 found unrelated real errors plus this one, round 2 (dispatched specifically to re-check round 1's fixes) found the correction was still slightly wrong, round 3 found nothing. Round 3 genuinely proves convergence in rule 7's sense, but "it terminates" and "it was worth running" are different questions, and a termination proof only answers the first. The fix sits beside V, not instead of it: before paying for the next iteration, name what breaks if you stop here, and only proceed if that outweighs the round's cost — none of mechanisms 0–4 ask this, because they all assume every triggered iteration is worth its cost, an assumption that breaks once R is "spawn an agent" rather than "re-run a script." Purely additive (0 regression candidates, 821 exact preservations).
- **local-conversation-history** & **claude-code-history-files-finder** (`daymade-claude-code` v1.47.0): new third native conversation source — **Kimi CLI** (kimi-code, `~/.kimi-code`, override `$KIMI_HOME`) — alongside Claude Code and Codex, for projects developed across more than one agent CLI. The shared `_conversation_core` gains `kimi.py`, bundled into all four conversation skills by `sync_core.py` as usual. The lister gains `--source kimi` / `--kimi-home`; the finder gains `--kimi` / `--kimi-home` (opt-in, same standing as `--codex`), aggregating matches at session level across a session's main and subagent wires with agent-prefixed match fields (`main:message`, `agent-0:tool_input`). Kimi timestamps come from internal fields only — state.json `createdAt`/`updatedAt`, wire `time`, or metadata `created_at` (epoch ms) — never file mtime. Titles prefer state.json, falling back to the first real user prompt in the main wire with the injected `<git-context>` wrapper stripped; weak auto-titles like "hi" lose to that prompt. Static boilerplate (config/profile system prompts, tool snapshots, usage/token metrics) is deliberately not indexed, so a keyword shared by every session's system prompt cannot manufacture a match. Format verified against Kimi CLI 0.38.0 (wire `protocol_version` 1.5) on a real 26-session store (26/26 inventoried with correct titles/projects; project-scoped keyword search validated in both directions); Kimi CLI's own `kimi export [sessionId]` only exports single sessions as ZIP and has no cross-session inventory or search, which is why the raw store is parsed directly. Ships with 17 new unit tests (8 lister + 9 finder) over isolated fixtures; both pre-existing suites (12 + 83) stay green. Regression audits: lister 10 candidates / 246 exact preservations, finder 7 / 675 — all candidates are one-directional expansions (old clause preserved verbatim inside the widened sentence), reviewed and verified.

### Changed
- **kimi-use** (v1.0.0): new skill — drive the Kimi desktop app (Kimi.app) through computer-use as a zero-credential data-source gateway to its logged-in plugin ecosystem (天眼查 / 同花顺 iFinD / 财新数据 / 标普全球市场财智 / 恒生聚源 / SEC / IMF / 世界银行 / 学术与法律数据库 …). Distilled from two real driving sessions (Claude Code computer-use MCP, 2026-08-18; Codex computer plugin, 2026-06-29 + 2026-07-02): both harness flows step by step, the machine-wide exclusive auth lock (no release interface — check `list_granted_applications`), Chat-vs-Work mode safety with a "did it actually call the plugin" checkpoint, extraction paths — plus the verification discipline those sessions paid for: installed ≠ callable (Wind plugin), screen transcription silently corrupts CJK proper nouns (6/20 shareholder names wrong while every number was exact), "all N records" is truncation (20 shown, 50 real), Kimi itself can be factually wrong (IPO clawback 50% vs official 20%), and query-prompt patterns that force source-labeled honest answers. Three fresh-context independent reviews folded in (fidelity 17 findings / executability 13 / fix-verification 3).

### Changed
- **skill-creator** (`daymade-skill` v1.27.4): two `classify` key-resolution hardening fixes from the independent review of v1.27.3, each reproduced before fixing and pinned by a test. (1) All-digit unique id prefixes (`"1234"` for id `1234abcd…`) fell through to "matches no candidate index or id" — misleading, since hex-truncated candidate ids are all-digit in their first four characters ~15% of the time; a failed index parse (overflow/negative) now falls through to prefix matching for any ≥4-char key. (2) Negative index keys (`"-1"`) were silently accepted as Python indices and resolved to the *last* candidate; they now fail loudly. Two new tests pin both behaviors; full suite 45 green.
- **skill-creator** (`daymade-skill` v1.27.3): fix three regression-audit defects that cascaded against a skill whose directory is its repo root, found while auditing exactly such a skill (trip-scout) and each verified red-on-revert. (1) `git-ref` baselines were unusable for repo-root skills: `_git_tree_hash` built the match prefix as `"./"` for `skill_rel == Path(".")`, which never matches `git ls-tree` output (`SKILL.md`, not `./SKILL.md`), so the check always failed with "Git baseline does not contain ./SKILL.md"; the repo root now uses an empty prefix. (2) `verify` was a dead end whenever a snapshot's source path differed from `--after` (e.g. a baseline materialized via `git archive` into a stand-in directory): the mismatch hint told you to pass `--renamed-from`, but that flag was registered only on `compare` — and even though `compare` dutifully recorded it in the review's provenance, `verify_review` recomputed identity without reading it back. `verify` now reuses the `renamed_from` recorded in the review; the hint says to re-run `compare`. (3) `classify` rejected unique id prefixes (the 16-hex candidate ids are painful to transcribe); map keys now resolve as exact id → numeric index → unique ≥4-char prefix, with an ambiguous prefix failing loudly instead of silently picking wrong. Four new tests pin all three (repo-root git-ref compare passes; verify honors recorded renamed_from; unique prefix classifies; ambiguous prefix raises), each confirmed red against the pre-fix code; the full suite is 43 green, and the fixed tool re-ran the original failing audit (repo-root skill + git-ref baseline) end-to-end.
- **transcript-fixer** (`daymade-audio` v1.27.1): two Native correction checklist clarifications from a same-session real usage gap — a user's dictated request, pasted inline via slash command with no pre-existing file and no `--domain`, exposed two undocumented judgment calls. (1) Checklist item 1 now says what to do when the input has no file yet (write it to a scratch location first — `--input` and the queue anchors both need a path) and when no domain is given (omitting `--domain` already searches every domain by its own CLI default; resolve specific candidates via a single cross-domain lookup — native_ai_full_workflow.md step 4 rung 1 — rather than blocking on domain choice). (2) The fast-tier bullet's "skip the needs-checking ceremony" is reframed around the text's *durability*, not its tier: a one-off inline dictation with no file anyone will reopen states its uncertain items in the reply instead of calling `--enqueue-review`. Verified rather than assumed: the `--domain`-omitted default-to-all-domains behavior was confirmed by actually running Stage 1 bare; a fresh-context subagent replay on a synthetic no-file/no-domain/unresolvable-entity scenario caught one real wording collision — the new domain-choice sentence said to use "the entity ladder's cross-domain search" right after the same page says fast tier skips "the cross-domain name ladder" — fixed to name only the one rung, not the whole ladder. Review dossier: `next/_meta/skill-reviews/transcript-fixer/independent-review-20260821-inline-dictation-domainless.md` (private repo).
- **skill-creator** (`daymade-skill` v1.27.2): align every security layer with the shared packaging policy. Scans stage the complete package superset (including optional `evals/`) while excluding non-shipping `.enrich/`, `tests/`, and `dist/` artifacts, so retained conversation-mining evidence cannot block a release and packaged content cannot escape attestation. Gitleaks and verbose pattern findings use skill-root-relative source paths; contradictory or incomplete reports fail closed regardless of exit code; the internal marker writer accepts only a clean result bound to the exact staged bytes; and marker validation requires exactly one structurally valid content-hash line. Regex checks cover every shipping UTF-8 text file while skipping binary content; packaging revalidates the marker against an isolated snapshot and zips that snapshot, never the later live tree. Custom output inside the skill is accepted only under the excluded `dist/` root, preventing a prior package from recursively shipping in the next one. Regression tests pin report/exit contradictions, ambiguous markers, both mutation windows, staging boundaries, path reporting, hidden/extensionless/HTML coverage, binary skip, output placement, and package contents; the full skill-creator suite passes.
- **skill-creator** (`daymade-skill` v1.27.1): fix conversation-mining redaction on Windows user paths. The literal `C:\\Users\\...` placeholder was passed through `re.Match.expand()`, where `\\U` was parsed as an invalid replacement escape and aborted any mining run whose source contained a Windows path. The placeholder now escapes its separators for replacement parsing, with a regression test that reproduces the prior crash and verifies the redacted output and counter.
- **skill-creator** (`daymade-skill` v1.27.0): stop treating a long preceding conversation or the verb "optimize" as permission to mine history, classify an existing-skill edit as Tier 3, or start a multi-agent evaluation. Risk tier and evaluation spend are now separate decisions: deterministic checks come first; ordinary existing-skill behavior changes use at most one or two with-skill replays; paired baselines, mining/research fan-out, graders, benchmarks, and viewers require explicit user authorization or a decision-bearing evidence plan followed by opt-in, and that evidence request does not change the risk tier. Conversation mining now requires explicit prior-history source intent and selects the minimum mining pass instead of launching every role plus a writer by default. A/B arms and large-corpus shards may share an axis when isolation requires it, but must declare total units and capped concurrency; only extra roles/reviewers require distinct axes. The same boundary is synchronized into the repository operating guide and English/Chinese marketplace docs.
- **transcript-fixer** (`daymade-audio` v1.27.0): hardens the full Native-first correction loop around four production contracts. (1) Context trap scan executes canonical `误识 → 正确` and legacy `误识 ≈ 正确` mappings, treats a quoted/backticked FROM phrase such as `CC 思维链` as one exact literal regardless of the bare-word length cap, and removes single-line `asr_note` values from its scan projection without matcher-visible filler; title, keywords and body remain in scope. (2) Speaker-timestamp attribution is immutable across dictionary, context-rule, synchronous API and asynchronous API paths. Explicit/generic labels (including terminal colons), CJK person-name signals, and labels from the configured roster/manifest are protected; repetition and Title Case are not guessed into identities, so timestamp-ended prose remains editable. Damaged/moved markers fail closed, and internal markers are revealed before reports, history or learning. In a five-transcript corpus with its configured roster, 1,920 attribution lines were protected and one timestamp-ended metadata sentence remained editable. (3) API correction preserves exact inter-chunk separators and single-line `asr_note` ledgers, rejects blank, non-text, explicitly truncated or otherwise incomplete responses, retains failed chunks, and exposes degraded counts in history and JSON; the enhanced wrapper exits nonzero for degraded output instead of appending a green success. Confidence plus primary/fallback model provenance is recorded per edit and carried unchanged into persisted-history learning; every emitted mutation remains auditable, while non-replayable, formatting-only and punctuation-only changes cannot become dictionary rules. Learning and auto-approval flags now gate behavior, old databases migrate before review queries, schema/learning errors propagate, and automated learning cannot overwrite a concurrent human rule. Deep health checks validate every runtime-required column rather than accepting table names plus a few audit fields. RapidFuzz replaces the repetitive-token `SequenceMatcher` path: the old implementation took 6.9 seconds at 10,000 characters and exceeded 10 seconds at 50,000, while the bounded opcode path retains exact audit records without quadratic behavior. Configured file/text/concurrency limits now execute, strict environment booleans fail fast, and unpunctuated runs are split before the API. (4) Stage 1 auto-finalize removes only reproducible intermediates and retains `*_changes.md` / `*_needs_review.md` until every represented decision is closed; both its promotion path and ordinary Stage 1 return the same complete ten-field JSON state, explicitly end-to-end incomplete until Native AI or the agent-less API route runs. The Python 3.10 floor is real across entrypoint metadata and concurrency: one timer covers semaphore acquisition plus the caller body without swallowing external cancellation. The runtime SKILL is now a compact decision layer over directly linked one-level references; stale re-anchor/API/dictionary/review pointers and non-executable examples were repaired, and the public end-to-end walkthrough is fully synthetic rather than derived from a real transcript. Paired evaluation passes all three scenarios on the new version versus two on the immutable old version; only trap scan is discriminating, while caller/re-anchor scenarios are preservation checks. Full suites pass on Python 3.10 and 3.14 (`569 passed, 3 subtests` each); the skill-regression audit classifies and verifies all 771 candidates.
- **kimi-use** (v1.2.0): four Work+K3 capability probes closed three pending verdicts and retired a section whose premise was false the day it was written. **Wind** ❓→✅ callable (self-reported chain `wind-allskill` → `wind-mcp-skill` CLI → agent-gw); **Gildata** ❓→✅ callable, and it *has* broker-research retrieval (`gildata_financial_research_report`); **iFinD** ⚠️→⚠️ callable but *confirmed* to have no research-report interface, now with hard evidence (all 9 APIs listed verbatim). The old "known gap: broker research" section is replaced by **"two channels, neither complete"** — same window, same caliber: Gildata 17 hits, a free public JSON API 10, **intersection 7, union 20**, and it was the channel *declaring* it does not guarantee exhaustiveness that found more. Two new verification rules: an interface's own `hits`/"N total" is only what **that interface indexed**, so coverage tasks must union two channels; and **two channels agreeing only proves they agree on one caliber** (both plugins said 1688.38亿 for the same year's revenue while two independent brokers each said 1720.54亿 — same growth rate, 32.16亿 apart = a statement-line-level difference, not an error), so financial values must be recorded with their account level and parent account name. Two new traps: **a missing carrier is not a missing capability** (no MCP tools exposed / a 503 gateway error both still meant callable), and **creating a new task silently resets mode *and* model**, so the pre-send check must cover the model selector, not just the input box. Also drops five derived counts that were already drifting, one of them referenced cross-file by a count that no amount of grepping-by-number would have found.
- **kimi-use** (v1.1.0): same-day user calibration reversed two load-bearing rules. (1) **Mode rule reversed — never Chat**: Kimi's Chat mode can answer without calling any plugin (it fell back to reciting a company profile with a wrong figure while ignoring a named plugin), so data queries now require Work/Agent mode plus a mounted-directory check, and generated files must be collected out of the mount afterward. (2) **New model rule — K3 极致思考 only**: the K2.6 fast model's "plugin not callable" testimony is unreliable — its self-enumerated data-source list is incomplete, and two of three plugins it denied worked under K3 with full interface detail. Capability table re-scoped so every row carries its mode×model provenance: Wind "installed but not callable" and iFinD "no broker research reports" are marked **void pending Work+K3 re-probe** (both came from Chat-mode testimony); S&P Global (sp_data) verified callable under K3 — company info/financials/estimates/shareholders/executives/key-events/transactions (`sp_get_transactions_advisors` with round & deal-size fields) — with US-listed coverage (a private company exact-query returns `EMPTY_DATA`; fuzzy-name queries return a same-named listed company's real records — a false-positive trap); 投资银行私募股权 is callable but is a routing layer over the same S&P channel, not a data source. Claude Code driving gains the provider rule: computer-use availability follows the active provider — it is explicitly removed in Kimi(k3) provider segments (transcript `removedNames` deltas verified) and all 57 real calls ran on the Anthropic model, so an empty ToolSearch means check your provider first.
- **transcript-fixer** (`daymade-audio` v1.26.0): four hardenings from a 2026-08-17 session self-review of a 3043-line production fix run, each verified end-to-end. (1) **Stage 1 no longer taxes correction ledgers**: a frontmatter `asr_note` value is masked before matching (sentinel-anchored, line-number-exact) and spliced back after, so its verbatim old-form citations (`修正含：丹娜→Dyna`) no longer re-fire as phantom matches and phantom review-queue enqueues on every re-run — one such line had produced 18 phantom matches + 9 phantom enqueues per run. Multi-line/block values skip with a warning (any `|`/`>`-led value; the convention is single-line), a UTF-8 BOM no longer silently defeats the mask, and a dictionary/context rule colliding with the mask filler degrades to an unprotected run with a warning instead of crashing. (2) **The 32k second-pass ceiling is treated as a length problem, not only a prompt-shape problem**: >~1000 lines is split territory (one reviewer per segment via Read offset/limit, ~50-line overlap, file-absolute line numbers, main-session dedupe), and the completion bar is segment-scoped. (3) **The background-agent delivery protocol is welded into the second-pass prompt shape** (SendMessage the table back + start ack) — the rule existed in agent-usage docs but the prompt didn't carry it (five blocked polls ≈ 25 min). (4) **Legitimized salvage path**: a reviewer that dies after its transcript provably holds a complete candidate list (candidates reach the file's tail) may be mined instead of re-spawned — every candidate still passes step-4 triage, and the salvage is recorded in the run's ledger; where a dead agent's transcript lives (spawn `output_file` / the main session's sidechain jsonl) is now written down. 19 new tests pin the masking incl. adversarial shapes (body-□, BOM, 11 block-indicator variants, short ledgers, □-rule degradation); full suite 393 passed with the 3 failures byte-identical to the pre-change baseline (pre-existing env issue); a real 3043-line ledgered transcript now dry-runs 0 phantom. Two adversarial multi-axis review rounds plus one finding-verification round (13 + 3 findings, all applied, zero rejected as false) — dossier archived in the author's private knowledge repo (`next/_meta/skill-reviews/transcript-fixer/independent-review-20260818-selfreview-fixes.md`).
- **skill-creator** (`daymade-skill` v1.26.3): documentation sync for 1.26.2. The "scripts/ directory includes deterministic gates used by this workflow" list named only `audit_skill_regression.py`, while Step 4 (Edit the Skill) of the same document now mandates a second gate — `reference_net.sh` — that the list never mentioned. Added as a pointer, not a second copy of its contract, which stays in the script header. No behavior change.
- **skill-creator** (`daymade-skill` v1.26.2): the Reference-and-self-application check stops being a prose command and becomes a **tested script**, `scripts/reference_net.sh`. The one-liner it replaces had taken five rounds of patches — anchor the diff to the right base, see staged edits, survive committing, skip the diff's own `+++` header, drop a misleading `-n` — and **four of those five added one more way for it to print nothing and exit 0**, which is indistinguishable from "I checked and it was clean". The fifth was the same disease wearing the opposite face: the `-n` it dropped had been printing real hits numbered off the piped stream, authoritative-looking and pointing nowhere — worse than silence. Either way the check kept shipping the defect it was written to catch. Prose cannot validate its own inputs, cannot say which of its outcomes occurred, and cannot be tested. The script's contract is that **every outcome is named out loud and bad input fails loudly** — four distinguishable verdicts (references found / identical to base / changed but no added lines / added lines with nothing reference-shaped) and exit 2, never a quiet 0, for an unresolvable base ref, an untracked path, an argument matching several paths, a git failure or a parse failure. Its scope is deliberately **half** of what the one-liner attempted: prose pointers only. Machine-resolvable markdown links are delegated to `lychee`, this repo's house standard — a hand-rolled link scanner was tried here before and deleted after it misreported 16 of 17 valid links, and the script's header says so, so it is not rebuilt inside this one. Beyond the five prose-era defects, an adversarial audit surfaced **ten** candidate findings; its own refuters killed two before they reached the author, one of the remaining eight duplicated another, and one — that `grep` would silently suppress binary-looking input — **was not acted on, but for a narrower reason than first written**. `grep` really does suppress: on NUL-bearing input `/usr/bin/grep` prints `Binary file (standard input) matches` at exit 0 and the matching line never appears. It is unreachable here, because `git diff` classifies such a file as binary before any added line exists and command substitution strips NULs regardless. The first refutation claimed "a clean exit-1, no suppression" — that measurement was taken on the *awk-truncated* stream, where the matching line had already been deleted, so grep had nothing to match and the exit-1 meant something other than what it was read to mean. Right conclusion, wrong instrument. Running the reproduction is nonetheless what exposed a worse bug the audit had only framed abstractly (item 4). Six distinct defects were acted on, each reproduced before it was fixed and each now pinned by a test verified to go **red** when its fix is reverted: (1) `git ls-files` **C-quotes any filename git considers unusual** and returns an escaped *string* — `"\346\226\207..."` for `文档.md`, and for a plain-ASCII `foo"bar.md` too, since quotes/backslashes/control bytes are escaped regardless of `core.quotepath` — which then matches nothing as a diff pathspec, so a file with real unresolved pointers reported IDENTICAL, under a mangled name; now resolved via `-z`. (2) `--no-ext-diff` does **not** neutralize a `.gitattributes` **textconv** driver, so a committed diff filter could hide an added pointer; `--no-textconv` added, alongside the already-guarded `color.diff=always` and `diff.external`. (3) The hunk parser never reset between file blocks, so a **typechange** (regular file → symlink) emits two blocks and the second's own `+++ b/<path>` header was reported as a prose reference **no human ever wrote**, with an instruction to go verify it. (4) In a UTF-8 locale a single invalid byte anywhere in the added lines makes `/usr/bin/awk` abort mid-stream (`towc: multibyte conversion failure`, exit 2); the script then printed "contributed no ADDED lines" at exit 0 — **naming a wrong cause** — while a real `see rule 8` sat unresolved. Fixed with `LC_ALL=C` on both awk and grep, plus an exit-status check on the parse step as a backstop. (5) The `:(top)` pathspec anchor, whose entire purpose is preventing "wrong file examined, clean verdict", had **zero live coverage** — dropping it left all 27 tests green. (6) Two regex quantifier boundaries (`[0-9]`→`[1-9]`, so `see rule 0` stops matching; ` *`→` `, so the ordinary typography `§4` stops matching) and the new parse-failure guard were likewise unpinned. The suite goes from 27 to **42 tests**, and the mutation matrix that calibrated them is the point: **twelve** reverts, eleven of which reddened exactly the one test claiming to cover them, and the filename-quoting revert exactly its two. An independent fidelity reviewer rebuilt that matrix from scratch, without having read the claim, and arrived at the same counts for the ten that existed then. A fresh-context reviewer then read the block and the script against a reader spec alone and returned **nine** further findings, all applied: three were the same silent-clean class in the parts that are still prose (bullet 3 said "a plain `git diff`", whose literal reading goes empty the moment you `git add`; `<base-ref>` was never operationalized, so the reader's fallback is the one value the script rules out; and `IDENTICAL` printed the same line whether nothing changed or the base already contained the reader's own commit — the script now says so). The rest were scoping, message clarity, a destination for "paste a fragment", and the removal of a hardcoded derived count that sat inside the paragraph warning against hardcoded derived counts. That the remaining silent-clean risks were all in prose, and none in the script, is the clearest evidence available that the conversion was the right move. A third reviewer, asked only what could go wrong for a stranger who installs this, then found the one silent-clean vector **the suite structurally could not see**: every test helper unsets `GIT_DIR`, so nothing exercised the case where it is left set — and there git silently targets a different repository, letting a clean verdict describe a file the caller never edited. The script now names the repository it actually examined whenever `GIT_DIR`/`GIT_WORK_TREE` is set, and a test that deliberately does *not* unset them pins it. The same pass measured the match pattern firing on five of six lines of ordinary technical prose — `whisper9`, `paper2` and `upper3` all matched through the "per" inside them — which by this repo's own standard (a check that misfires on healthy input is worse than no check) was the likelier way for this tool to die than any false negative. A portable leading word boundary — `(^|[^[:alnum:]])`, since `\b` and `\<` differ across BSD and GNU — takes that to two of six, and the header now states plainly that the remainder is expected. That reviewer also verified by checksum, across success and failure paths, that the script mutates nothing: no writes, no network, no execution of file content. Behavior was re-measured on a second toolchain before shipping, because every defect above was found on macOS/BSD: the suite is green on Debian bookworm with **dash** as `/bin/sh`, **mawk** rather than BSD awk, **GNU grep 3.8** and git 2.39.5, and the `LC_ALL=C` + `-Ei` + literal-UTF-8-`§` combination was probed directly there (`§4`, `see rule 0` and `SEE RULE 3` all match). **Honest limits**: these tests are not registered in `scripts/ci/test-suites.txt` — the repository has an audited decision keeping skill-creator's suites out of the shared registry, so CI never runs them and their green is local-only; and one boundary is documented rather than fixed — a submodule bump *is* reported and correctly classified non-prose (measured; an earlier draft of this entry claimed it was invisible, which was reasoned rather than measured and was wrong), but the content behind the new commit is never traversed, so a pointer added inside a submodule needs the script run in that submodule. Regression audit: 0 candidates / 2887 exact preservations.
- **claude-switch-models-setup** (`daymade-claude-code` v1.46.0): the profile converger gains a **second layer — per-profile `.claude.json` behavior keys** — after a live incident proved the first layer blind to it. `workflowSizeGuideline: small` was set on the main profile while 10/11 third-party profiles carried no copy of the key at all: it lives in the per-profile state file (`~/.claude.json` for main, `<profile>/.claude.json` for third-party — asymmetric paths, verified on disk), which neither the symlink layout nor the settings.json sync covers. A Kimi session then fanned one Dynamic Workflow out to 30+ agents with no size guidance in its system prompt, while hooks and every other settings.json key were fully converged. `sync-profile-settings.py` now also converges an allowlist of confirmed behavior keys (`BEHAVIOR_KEYS`, each entry carrying its reason), keeps state/cache/counter/migration/credential keys out via a pattern classifier (`is_state_key()` — syncing `projects` or `oauthAccount` across profiles would corrupt state or account identity), and **reports any unclassified drifted key once per profile** — the tripwire that surfaces the next behavior key the day it appears, not after the next incident. Write safety was measured before shipping: a marker key written into an ACTIVE profile's `.claude.json` survived 30+ minutes of the running harness rewriting the file (merged writes, not full-file clobbers); backup + atomic replace + post-write validation apply, the main profile's file is never written, and a missing profile file is skipped, never created. `--all` now also skips dot-prefixed archive directories (`.archived-profiles` was being synced). Ships with a 47-assertion fixture suite (`scripts/sync-profile-settings.test.py`): behavior-overwrite / state-untouched / gray-report-not-write / backup / idempotency / missing-file / settings-layer regression, plus a real-environment `--check --all` + `--all` + re-check green run.
- **skill-creator** (`daymade-skill` v1.26.1): fix two defects a post-merge review found *inside* the Reference-and-self-application check shipped in 1.26.0 — both of exactly the kind that block exists to catch. (1) **The prescribed `git diff -U0 -- <file>` has its own silent-empty failure**: it shows *unstaged* changes only, so the moment you `git add` — ordinary hygiene — it prints nothing and exits 0, indistinguishable from a clean pass, over an edit it never read; a mistyped or wrong-relative path does the same. Measured on one file with one staged change: 0 bytes without `HEAD`, 120 bytes with it. Now `git ls-files --error-unmatch <file> && git diff -U0 HEAD -- <file> | …`, with each of the three flags' reason stated (`HEAD` sees staged edits; `--error-unmatch` turns a wrong path from silent-0 into `pathspec … did not match any file(s) known to git`; still no `-n`, which after the first filter numbers the piped stream rather than the file), plus an instruction to read empty output as a question — "nothing changed" and "changed but nothing looked like a pointer" are not the same result. (2) **The "name who executes each rule" bullet was the block's only pure self-assessment**, in a block that cites discipline #6's ban on self-assessment three times and whose own opener promises every item "needs a *mechanical* action" — it was also, measurably, the one bullet the block's own reference-net regex did not match. It now owes the artifact it demands: name the tool that would catch a violation and run it once against a known-bad input; if it comes back clean, you have *measured* that the rule is inert. What let both through in 1.26.0 is worth naming — CI, the regression audit, an independent review and the author's own dogfooding all asked "does the command run?" (it does; exit 0) and none asked "do its outputs mean what the prose says they mean?" **A command's exit status is not its semantics.** Fixing this also fixed a third, self-caught: a "see the bullet above" pointer with an unrelated bullet in between.
- **skill-creator** (`daymade-skill` v1.26.0): Step 4 gains a **Reference-and-self-application check** — the defect class that survives a careful author, because writing an assertion and verifying it are different modes and one pass cannot hold both: while you compose "see rule 8", that sentence *is* the claim; you are not simultaneously opening rule 8. Four mechanical actions plus a corollary, each with a real case. (1) **Open every pointer's target and copy a line out of it before writing the pointer** — a wrong cross-reference is invisible on re-read because it looks exactly like a right one, and the author is the one person guaranteed to "remember" what the target says; the source incident shipped a pointer to the wrong document's rule 3, one with its direction inverted, and one naming a heading that does not exist. (2) **A bare "rule N" is ambiguous once a file has two numbered lists** — checked per-pointer (`grep -n '^N\. '`, confirm one hit in the section you mean), explicitly *not* as a file-level alarm, because on any long document that fires on healthy input and gets trained away (this file returns 19). (3) **After writing a normative rule, check it against the lines beside it and emit an artifact, not a verdict** — split the rule into clauses and name, per clause, the line in the same hunk that satisfies it; "does my rule pass?" cannot fail for whoever wrote it 30 seconds ago. (4) **State who executes each new rule and whether they can** — a rule the existing tooling cannot satisfy is skipped by people who believe they complied, which is documented false confidence. (5) **Corollary: your fixes are themselves a defect source** — in the two-round review of the originating change, round 1 found eight issues and round 2 found eight more, *seven of them cross-reference errors introduced by round 1's fixes*; a `git diff -U0` + reference-net grep re-check after the last edit is given. The block was then held to its own rules and failed twice before shipping — its opener said "three failure modes" over five bullets (counting prose is the hardest drift to catch because it does not contain the number that changed), and the self-application bullet was itself a self-assessment while citing discipline #6's ban on exactly that. Both were caught by an independent fresh-context review, not by the author. Regression audit: 0 candidates / 2887 exact preservations.
- **daymade-audio** v1.24.3: transcript-fixer fixes `--domain all` silently matching zero rules and exiting 0 as if the transcript were clean — `normalize_domains` now folds `all` (any case, alone or inside a comma-separated list) to the no-filter whole-library form the tool's own hint already documented, ending the 0-rule no-op for configs that declare `domain: all`; and the write/attribution paths now treat the alias consistently — write commands (`--add`/`--report-false-positive`) fail loud instead of silently redirecting to `general`, `--approve`/`--import`/learning/queue/history no longer mint or stamp a phantom literal `all` domain (whose rules fire on every unfiltered run but no filter can select), `--list -d all` renders the whole-library layout, and `--domain all --apply-domain` prints a hint instead of silently staying in safe mode. Seven new tests pin the alias and the write-side guards; existing multi-domain/add-guard tests pass unchanged.
- **transcript-fixer** (`daymade-audio` v1.24.2): two adjudication rules for the upstream-diff review, from a 2026-08-17 production incident where a native pass reverted a *correct* dictionary-rule application (an address-form rule curated in the transcript's own domain) because a same-sounding name existed in another project's directory. (1) **Provenance before phonetics**: a rule-backed swap is a prior settled decision, not an AI guess — the sound-distance test only ranks AI guesses, and reverting a rule requires affirmative, conversation-internal evidence (the alternative referent must be present/addressed/referenced in *this* conversation; name evidence must be searched under the canonical full name from the rule row's `to_text`, not just surface address forms — a zero-hit narrow grep is an instrument report, not absence). A raw-verified in-document self-proof against the rule also clears the bar, and then the rule itself must be retired or scoped; genuine ambiguity goes to the review queue with the rule-backed form left in place, never a revert. (2) **Self-proof outranks phonetic minimality** when auditing an already-applied fix — with the two qualifiers that keep the proof real: the proof occurrences must verify against the raw text (same-pass occurrences are circular), and both-candidates-present makes the proof non-discriminating. The pre-existing "Accept — near-homophone + in-document self-proof" bullet gets the same two qualifiers so the strongest self-proof statement no longer licenses the circular one. Verified by a Tier 2 fixture replay of the incident (rule-backed swap kept, AI rewrite reverted) plus two fresh-context independent review rounds whose findings (provenance method, priority conflict, circular-proof hole, value-list slips) are all applied; review dossier archived in the author's private knowledge repo (`next/_meta/skill-reviews/transcript-fixer/independent-review-20260817-upstream-revert-bar.md`).
- **feishu-doc-scraper** v1.3.3: version-bump catch-up for the acceptance-gate fix shipped in #302 — the gate now extracts and checks residual Feishu embed tags (whiteboard/cite-mention-doc/sheet) on the raw `source.html` instead of the pandoc-stripped `source.md` (pandoc silently drops those tags, so a document that lost three whiteboards was reported clean), widens the gate from hub-collections-only to every document, and switches to per-document filenames so a hub's recursive fetches no longer overwrite each other.
- **daymade-skill** v1.25.1: version-bump catch-up for the `audit_skill_regression compare --renamed-from <old-path>` fix — a legitimate skill rename/move no longer hard-fails the source-identity check when explicitly declared (identity check only; content/tree-hash verification unchanged, so a wrong declaration still fails), with the git-ref baseline mode locating the skill under its old path in the historical ref, plus the independent-review follow-ups (resolved-path hint in errors, distinct failures for `--after` outside a worktree vs `renamed-from` outside the repo, and a fourth test).
- **transcript-fixer** (`daymade-audio` v1.24.1): swap one residual fixture token (`1v1沟通` → `1页纸汇报`) in the numeric-consistency scanner and its test. The token sat inside fully fictional bookstore context (星辰社/北岸分馆) and was never a leak on main, but it was homologous to the real project fingerprint sanitized everywhere else — a reader with insider knowledge could recognize the shared source. The digit-carrying shape the test exercises is preserved; 22/22 tests pass.
- **docx-creator** (`daymade-docs` v1.8.0): three shipped-scheme corrections to the markdown-to-docx generator. (1) Body size moves from 24 half-points (12pt) to **21 (10.5pt)**, the common Chinese manuscript size, with body paragraphs gaining a 2-character first-line indent (`420` twips — a named constant beside the size constant so they change in lockstep); headings, list items, table cells, and soft-break info blocks correctly stay un-indented (the indent only belongs on flowing body text — ISSUE-004's multi-line blocks would warp under it). (2) **Chinese bold switches family to 黑体** — 宋体 has no true bold weight, so renderer-synthesized bold smeared multi-stroke characters into blobs in both LibreOffice and Word; Latin bold stays Times New Roman Bold, which has a real face. Registered as **ISSUE-014**. (3) Docs re-synced at all three sites that quote the old scheme (SKILL.md font section, known_issues shipped-scheme line, scripts/README.md lookup table).
- **transcript-fixer** (`daymade-audio` v1.24.0): four instruction hardenings around entity adjudication and the second-pass review, all from 2026-08 production runs. (1) Canonical-first is tightened: only a user-confirmed or human-annotated diarization label may settle a canonical spelling — an auto-assigned or unknown-provenance label stays a *candidate* and must climb the verification ladder. (2) Asking the user for a canonical person name must preserve an escape hatch outside the shortlist (`Other / none of these` accepting free text) — a single local occurrence justifies a list entry, not list exhaustiveness; the real canonical may be an English name while every candidate is a Chinese transliteration. (3) The second-pass subagent's completion criterion changes from "the process ran" to "a usable result arrived": the reviewer must cover the whole file and return either the residual table or an explicit `no new residuals`; an empty, malformed, or truncated response is a failed pass and must be retried with a fresh reviewer, and a retryable failure (e.g. an HTTP timeout carrying `retry_after`) must wait at least that long before retrying. A targeted grep/trap-scan of known patterns is explicitly *not* an independent re-read — in one production run, substituting it for a timed-out cold review reported clean, and the retried review surfaced 26 additional candidates. (4) When Task is genuinely unavailable (the instructions are already executing inside a subagent), the fallback is a line-by-line re-read from the corrected artifact — never a known-pattern grep wearing a re-read's name.
- **docs-cleaner** (`daymade-docs` v1.7.0): grows a second mode and a decision framework, turning a doc-merging tool into a documentation-governance one. **Mode 1 — post-change governance** is new: when code, config, ports, paths, deployment, auth, tests or a documented procedure change, it scopes from the change (not the repo), identifies which file *defines* each affected fact versus merely mentioning it, treats the implementation as evidence and the doc as the claim (explicitly **not** as license to edit code — if the implementation is what's wrong, report and stop), decides each doc's disposition (update vs archive) *before* editing, and finds every copy of a changed fact before changing one of them. **Mode 2 — consolidation** is the original workflow, preserved whole. Both share a new **Drift Test**: ask in order whether a value is computable from what's already recorded (→ a derived value; don't write it at all — the prose analogue of "generate your API docs, don't hand-copy them"), authoritatively defined elsewhere (→ link, don't restate), or a record of what was true at a moment (→ only now may you write it). Linking solves only the second case; pointing a link at a derived value manufactures scaffolding that goes stale *and* a false sense of alignment. Position gives no exemption — frontmatter, index description columns, checkbox state and table cells are all body text. Two self-certifying checks inherited from the old version were replaced with falsifiable ones: the tick-box "Value Preservation Checklist" became per-disposition evidence (a **Condense** section can't be verified by a verbatim search — it was *supposed* to be rewritten — so it needs its load-bearing claims enumerated instead), and the plan's "Value preserved: 100%" became a count-with-a-list filled in after execution, since at plan time it was the deleting party grading its own deletion. Verified by seven fresh-context independent review rounds — two on orthogonal axes (actionability, fidelity-to-the-old-version) and five auditing the previous rounds' own fixes, which is where most of what follows came from. Findings per round: 22 / 13 / 13 / 15 / 11 / 14 / 22. That count never converged, but the *kind* of defect did: rounds 1–2 found missing content, rounds 3–4 found the newly-written commands were wrong, and rounds 5–7 found that each rule written to fix the previous round could be complied with by an agent that was getting it wrong. The repeated correct answer was to remove something rather than repair it. The sharpest instance is worth stating because it generalizes: a check that had been producing false deletion reports for correctly-merged sections was given a softer alternative path — and the path turned out to be selectable, at check time, by the agent whose search had just missed. An exception that opens only when the gate has just caught something is not an exception; the fix binds the choice to a record made before the rewrite. One deliberate reversal of the old version is worth naming: its worked example told the reader to delete a dated test run as a "one-time record", which the new rules classify as an audit trail that may never be deleted quietly — the example now uses duplicated content instead, the only Delete you can justify by pointing at something. Two of them are the reason to read this entry — a `rg` command written without a path argument searches *stdin* in an agent's non-interactive shell and returns exit 1 with no output, byte-identical to the "clean pass" signature the file itself documented; and a hand-rolled broken-link pipeline mis-reported 16 of 17 valid links as broken the moment it was given more than one file, because `rg` prefixes `filename:` at 2+ paths — it had only ever been tested on one. The link pipeline is gone (delegated to `lychee`). So is the mechanical count-word sweep meant to catch renumbering damage: run repo-wide it emitted 652 MB on a real docs repo (17.7 MB scoped to one project directory) — a check nobody runs is a check that guarantees its own bypass — and the bounded alternative, searching only files that mention the subject, was measured **wrong in the direction that matters**: prose that bakes a count into a sentence refers to the subject by alias, translation or bare link, never by title, so the filter is anti-correlated with the target. It is now an honest three-step instruction that ends by stating what it did *not* cover, rather than a green check that quietly meant one of those two failures. Every shell command was re-measured on real repositories, multi-file inputs, empty inputs, and outside a git repo. Review dossier in the author's private knowledge repo.
- **daymade-skill** v1.25.0: make skill-creator verification risk-scaled instead of treating the full paired eval pipeline as the default for every edit. Tier 1 uses authoritative facts plus targeted deterministic checks for bounded fixes; Tier 2 adds one or two representative with-skill replays for narrow behavior uncertainty; Tier 3 retains the complete with-skill/baseline fan-out, grading, benchmark, analyst pass, and viewer for new, broad, high-risk, trigger-optimization, multi-class comparison, or explicitly benchmarked work. Subjective judgment alone no longer escalates a narrow change. The router selects the lowest tier that can falsify the changed behavior, prevents available subagents from becoming an escalation trigger, and requires already-launched paired eval, grader, aggregation, and viewer work to stop when the user says the benchmark is not worth it. Existing-skill migration, one required fresh-context review, public sanitization, and domain safety gates remain independent.

### Added
- **claude-code-hooks** (`daymade-claude-code` v1.45.0): new pitfall **#34 — a `PostToolUse`-only registration never fires on the Bash command's own failure**. Claude Code routes a Bash tool call's outcome to one of two separate hook events based on the command's own exit code, not to `PostToolUse` unconditionally with a status field: exit 0 routes to `PostToolUse`; any nonzero exit routes instead to a distinct `PostToolUseFailure` event, and `PostToolUse` never fires for that same invocation. A hook registered `PostToolUse`-only is structurally blind to every failing command — usually exactly the case worth reacting to. Discovered live (2026-08-16) building a hook meant to fire on `git`'s "fatal: not a git repository": manually running the triggering command produced zero hook output, and the two natural first guesses ("didn't hot-reload", "matcher is wrong") were both wrong — every *other* Bash call in the same session was triggering the hook fine, and the same command text fed to the script by hand produced the expected output. Confirmed by comparing a debug trace log across exit-0 and exit-128 commands in the same session window. Fix: register the identical hook command under both events (matcher `Bash`), echo `hook_event_name` back verbatim in `hookSpecificOutput.hookEventName` rather than hardcoding it, and write end-to-end test fixtures for both event shapes. Verified by an independent 3-axis Workflow review (reader-spec executability, public-safety scan, and — for a companion fix in the same session — 27-case adversarial verification of an unrelated timestamp-parsing bug); no blocking findings.
- **devils-advocate** (`daymade-financial` v1.1.0): new skill — structured devil's-advocate pressure-testing of an investment thesis against user-supplied evidence materials. A local reimplementation of LinqAlpha's hedge-fund "Devil's Advocate" agent, built from the production prompt template and JSON schema the vendor published on the AWS ML blog (2026-02), and extended with three layers that implementation lacks: a Mauboussin base-rate outside view (materials-bounded — no invented statistics, no side retrieval), a RAND Assumption-Based-Planning signpost list that turns the one-shot critique into a monitoring routine, and an explicit materials-bias/coverage declaration. Flow: decompose the thesis into explicit assertions and implicit assumptions (A1/A2 ids; fact/forecast/mechanism typing; load-bearing test; opposite-conclusion sub-claims must split), retrieve per-assumption counter-evidence under a source-credibility ladder with verbatim citations plus ACH's absent-evidence question, emit an auditable JSON object (`run_metadata`/`findings`/`deferred_assumptions`, `citations` array, `rebuttal` field, risk-flag rubric with an anti-inflation guard) and render a theme-grouped analyst narrative with references and a survived-assumptions list. Evidence-anchoring is load-bearing by design: role-played dissent underperforms authentic dissent (Nemeth 2001/2018), so free-form contrarianism is banned and every counterpoint must cite. Shipped after one fresh-context independent review (P0×1/P1×5/P2×14 — the P0 was a step-renumbering with four dangling cross-references; all fixed and re-verified), plus a full production test by a context-free agent on a real optical-module thesis with 5 research reports: 8 assumptions, 38 mechanically verified verbatim citations, schema-conformant output, and two counterarguments the authoring session's own parallel analysis had missed; the nine ambiguities that test surfaced (risk-flag inflation 6/8 High without a rubric, bare-array output with nowhere to put the coverage declaration, single-citation slot breaking multi-fact counterarguments, and six more) were folded back into the skill in the same session.
- **frontend-visual-qa** (v1.12.0): new reference **`reference-parity-decomposition.md`** — the reference-parity profile was the only profile in the skill with no method file attached, and a real engagement proved the cost: a login-page rebuild against a public product's sign-in screen, with this skill loaded, took five user-caught correction rounds because every round fixed exactly the one delta the user's side-by-side screenshot pointed out and then declared parity. The new file makes the measured structural inventory of the reference the first deliverable (anchoring pinned-vs-centered, container vs full-bleed, aspect-ratio ownership, scale ladder, material chrome, column ratios, intra-region alignment, spacing rhythm — each with an operational diagnostic), defines match criteria (categorical relationships match exactly; scalars match at the project's token granularity), and encodes four traps that outlive the inventory: a user-caught delta falsifies the inventory rather than just the pixel; self-authored geometry assertions are Level D *for the parity claim* (a 22-assertion suite stayed green through three consecutive structural misreads — claim-type scoping stated against the host's evidence table, which keeps project E2E at Level B for geometry/regression claims); a vetoed effect ("never crop the image") indicts the structural premise that forces the effect, not the parameter that picks its flavor (`cover`→`contain` swaps cropping for letterboxing inside the same wrong fixed-size container); and user-supplied assets render faithfully by default — a silently chosen crop focal point is editing the user's material. SKILL.md wires the file into the audit-contract step with the lifecycle boundary stated (decomposition is the first act of the audit, applied to the reference, which always already exists; greenfield visual direction still routes to design skills), adds a conditional reference-parity inventory block to the report schema, and states the division of labor with `data_viz_tier_and_token_audit.md` for data-page tier parity. Marketplace description gains the "compare a rendered artifact with a visual reference" clause SKILL.md already carried. Verified by historical-task replay (each of the five failure rounds now has a specific sentence that names it before it happens) plus two fresh-context independent review rounds: round one returned 10 findings (4 substantive — no measurement method/artifact home for static-screenshot decomposition, no matched-verdict tolerance, an inaccurate host evidence-table citation, and a load-window conflict with the skill's after-implementation scope), all 10 fixed; round two verified the fixes.
- **claude-code-hooks** (`daymade-claude-code` v1.43.0): new pitfalls **#30** and **#31**, both incidental discoveries from live work on a private hooks repo this session (not synthesized on request). **#30 — `UserPromptSubmit` fires on a task-notification's own arrival, not just on a human keystroke, and the stdin JSON has no field that says which**: a keyword-scanning hook fired the moment a background subagent's completion report landed, because the report's own text happened to match the trigger regex — no human had typed anything nearby. The transcript JSONL distinguishes the two internally (`origin.kind: "human"` vs `"task-notification"`), but that metadata never reaches the hook; the official stdin schema (verified against the live docs, not memory) is exactly `session_id`/`transcript_path`/`cwd`/`permission_mode`/`hook_event_name`/`prompt_id`/`prompt` — nothing marks provenance. SKILL.md's pre-existing "`UserPromptSubmit` only ever sees user input" claim gets a precise footnote rather than a rewrite: the core argument (it can't see the model's own current-turn output) still holds, it just isn't proof `.prompt` always originated from a keystroke. **#31 — a compounding-artifact staleness tracker keyed on file *kind* re-flags files nobody touched, and a written justification can't clear it, because nothing reads prose**: the tracker's `kinds` array accumulates across a whole session-scoped "turn," so re-editing *any* file of an already-flagged kind re-triggers the whole group regardless of a per-file justification already written and committed — the escape hatch its own message describes is real for a human reader, but the mechanism doesn't parse markdown to check whether it was used correctly. An independent fresh-context review — dispatched to *re-derive*, not just read and trust, the three evidentiary claims (the docs schema via its own WebFetch, the transcript shape via its own direct JSONL parse, the tracker's ledger via its own file read) — found every specific factual claim accurate, but caught two real bugs in #30's *prescribed* Fix before merge: the gate condition `origin.kind == "human" and promptSource == "typed"` silently rejects genuine human input arriving mid-turn (`promptSource: "queued"` — confirmed against a real several-sentence human message in this session's own transcript, independently re-verified before applying the fix), corrected to gate on `origin.kind` alone; and the fix told readers to look up `prompt_id` in the transcript JSONL, a string that occurs there 0 times across 1745 records — the field is `promptId`, camelCase, while the hook's own stdin JSON carries snake_case `prompt_id`, the same twin-blind-spot shape pitfall #20 already warns about on a different field pair.
- **macos-watchdog** (v1.0.0): new skill — design, deploy, and discipline macOS launchd watchdogs (LaunchAgents/LaunchDaemons that detect a recurring problem and auto-remediate). Distilled from 15 production watchdogs running on the author's machine and their incident history — the recurring failure mode was never "how to install a plist" but the watchdog itself becoming the disturbance. Ships the **quiet-watchdog contract** (four clauses, each from a real incident): premise-state self-check (a monitor's lifecycle binds to its premise — a recovery watcher kept notifying "still broken" for 2h after the system healed); patient mode (defer disruption, not detection — one measured chain self-recovered in ≤3 min, so force-reconnect on blips was net-harmful); escalating auto-cooldown (a failed repair ladder on an unfixable network re-ran every 5 min forever — ThrottleInterval can't fix this, it throttles process respawn only and has no backoff); and never-resurrect-what-the-user-quit (`open <url-scheme>` launches apps, `open` without `-g` steals foreground — the watchdog read as "I quit it and it came back"). Also covers deploy mechanics that bite (gui vs system domain, StandardOut/ErrorPath, TCC/FDA on the actual interpreter), stop semantics (`unload` is deprecated and gets resurrected by `RunAtLoad` — bootout/bootstrap/disable only), batch-loop throttling by default (an unthrottled replay forked 1,041 procs/sec and pushed the die to 83 °C), and SRE alert layering (page vs ticket, fatigue numbers). Bundles two reusable scripts (`watchdog-cooldown.sh` — source-able escalating cooldown + manual pause state machine; `new-launchagent.sh` — idempotent installer with validation) and an annotated plist template. Eval'd against baseline on three realistic prompts (new-install / noisy-watchdog triage / config audit): with-skill 17/17 assertions vs baseline 16/17 (baseline's one miss: prescribed the deprecated `unload`). The eval harness itself caught a real bug in the cooldown library — the exhausted-round counter went stale during cool-down waits longer than the stale window, pinning backoff at tier 1 forever; fixed in the library and in the production watchdog it was distilled from.

- **slides-creator** (v2.0.0): **DEPRECATED — skill retired to a stub, no longer maintained.** Same consolidation as ppt-creator (daymade-docs v1.6.0, same release): the PPT toolchain merge of 2026-08-07 folded its methodology — First Law (user's voice is primary), the ABCDEFG narrative-discussion framework, the baoyu-slide-deck delegation protocol, and the four-layer directory governance — into deck-creator's Route A · narrative in the author's private marketplace. For external users: this is the final version, kept for install compatibility, receiving no further updates; physical removal in a future major release. references/ and scripts/ removed here (git history preserves them); SKILL.md is now a deprecation notice.

- **ppt-creator** (`daymade-docs` v1.6.0): **DEPRECATED — skill retired to a stub, no longer maintained.** The PPT toolchain was merged on 2026-08-07: ppt-creator / slides-creator / html-to-ppt / a project-embedded pptx_builder were consolidated into a single entry point (deck-creator, in the author's private marketplace; its Route B absorbed this skill's methodology — INTAKE questionnaire, Pyramid-Principle workflow, assertion-evidence templates, VIS-GUIDE chart selection, STYLE-GUIDE, RUBRIC scoring). Motivation: toolchain fragmentation (5 PPT tools) produced a real routing failure — an agent aware of only 2 candidates recommended an approach a client had previously rejected. For external users: this is the final version, kept for install compatibility; it receives no further updates and will be physically removed in daymade-docs v2.0.0. The scripts/ and references/ content was removed in this release (git history preserves it); SKILL.md is now a deprecation notice.

- **transcript-fixer** (`daymade-audio` v1.23.1): **「Stage 1 alone is not the job」契约强化**,针对 2026-08-07 真实失效——meeting-ingest 经 `transcript_fixer.script_path` 配置集成（全程 0 次 Skill 加载）只跑 Stage 1 词典、报「逐字稿干净」,73min 腾讯逐字稿 54 处误识漏网,用户批评「你为什么每次都只跑 stage 1」。根因不是缺规则(SKILL.md 早写着 Native AI 是默认主路径、L121 契约节甚至预言过「run Stage 1, apply almost nothing, and report success」),而是规则不在调用方的上下文里。三处收紧:①frontmatter description 插入「Stage 1 alone is not the job.」;②Quick Start bash 块尾部新增「⚠️ STOP」注释块(扫读找命令的集成方不会错过)+「After Stage 1」段强化(豁免条款:仅人类用户当场限定 scope 或有 native pass 已跑证据有效,「the pipeline ran the script」/「稿子短」/「词典已修 N 处」均不算豁免);③cross-skill invocation contract 节引言扩为两种失败并列 +「TWO MUSTs」路标(防读者在 `--apply-domain` 处带合规自信收工),新增「Stage 1 is the whole script call — it must not be the whole job」段(caller 必须接 skill 而非仅 script path;纯 CI 走 Stage 3 API;script-path-only 集成是本文件无解的诚实边界)。两轮 fresh-context 独立审阅全采纳(第一轮 5 条:契约引言未为新 MUST 让位/豁免无有效性标准/漏 Stage 3 路径/零命中校准偏窄;第二轮 4 条:豁免字面覆盖 caller 常驻接线/相对指针落错位/「dictionary never touched」字面不准/「hand to an agent」误读另派),档案 `~/scripts/skill-reviews/transcript-fixer/independent-review-2026-08-07-stage1-not-the-job.md`。回归审计以 git ref 1809c27 为 baseline 通过(2 candidates 均 intentional_boundary + 用户原话「能不能把那个 transcript-fixer 全跑完呢」作 user_approval)。已知残留:meeting-ingest Step 3.5 措辞仍是「Stage 1 dictionary」(失效的直接位置,另一仓,待配套改写)。
- **claude-md-progressive-disclosurer** (`daymade-claude-code` v1.42.0): fold a real 168KB-global-CLAUDE.md optimization session back into the methodology — the failure modes were caught live, each by the user or an independent audit, and none was encoded in the skill yet. (1) New **Step 2.0 hotspot profiling**: measure before proposing — whole-context share (via `/context`), a per-section byte table whose descending order IS the work order, line-length distribution (lines >1KB are the "rule + war story fused into one bullet" signature: 4.4% of lines carried 35.6% of bytes), and consumer truncation caps. Added after the session's executor proposed a ~3% extensions cleanup while the 70k-token hotspot file sat waiting for a go — user's words: "你没有先去管热点，而是先找了一堆很小很小的东西". Encodes the two instrument pitfalls hit the same day: fence-unaware heading regexes fabricate phantom sections (a fake 45.9KB section distorted the first ranking), and chars/4 underestimates CJK-dense files by >2x (measured ~0.42 tokens/byte). (2) **Consumer-cap check + sentinel**: the same file read through an `~/.codex/AGENTS.md` symlink had outgrown its configured 96KiB `project_doc_max_bytes` — 41% of the body silently invisible to Codex for weeks, zero errors anywhere; the fix is raise-cap + shrink-file, plus a SessionStart size-vs-cap sentinel so the next overrun reports itself. (3) Step 3 gains the **scripted whole-section sink procedure** with two bundled stdlib-only scripts (`scripts/profile_claude_md.py`, `scripts/sink_sections.py`): fence-aware extraction → verbatim append under dated provenance headers → bottom-up splice → whole-string substring verification (grep ORs per line and passes lossy moves) → automatic rollback; refuses symlinked targets, which would silently edit another repo (prior art searched and cited in-script: mdsplit splits whole files, has no transactional sink contract). Verified live: 10 sections / 119KB sunk, 10/10 whole-string checks, zero information loss confirmed by independent audit. (4) Step 5b gains the **compressed-restatement fidelity audit**: qualifier-level word diff — the audit caught "public + 0 stars/forks" compressed to "0 stars", six characters that halved a push gate's condition — plus expected-hunks-only diffing (every non-equal hunk must map to a declared change). Carrier table updated with the official `~/.claude/rules/` + `paths:` frontmatter mechanism (boundary stated: triggers on file reads, not Bash moments), the official <200-line target, `/doctor`'s trim check (v2.1.206+), and zero-cost HTML-comment maintainer notes. Full war story: references Case 19.
- **claude-code-history-files-finder** (`daymade-claude-code` v1.40.0): new **Core Operation 6 — Triage Session Endings** (`analyze_sessions.py triage`), for "which sessions did a reboot/crash cut off" and "which older sessions are still waiting on a reply, not actually done" — a capability two real tasks in one conversation needed and the existing `list`/`search`/`stats` didn't support, so both were done by hand-rolled one-off scripts first. Classifies each in-scope session into one of five structural `kind`s (`interrupted_explicit`, `net_error`, `done`, `empty`, `stuck_no_result`) and always prints the full session ID plus the complete last-assistant text, not a truncated title — the two axes ("what kind of record ends it" vs "does it still need a reply") are independent, and only reading the full text answers the second one. An independent review then found and this session fixed two blocker-severity bugs before ship: (1) the whole-file tool_use/tool_result pending tracker was a single-pass discard-then-add, which is **not** actually order-independent — `discard()` on an id not yet seen is a silent no-op, so a `tool_result` written before its `tool_use` (a real race on fast round-trips, per `references/session_file_format.md`'s "Tool Use / Tool Result Ordering") left the id wrongly "pending"; measured on a 500-file real sample, 14 hit the ordering and 11 (79%) had their classification flip. Fixed by accumulating two never-mutated sets and diffing them once at the end. (2) a turn with text *and* a tool_use block took its kind from the text alone regardless of block position, so a narrate-then-call-tool turn ending mid-tool-call (a real, non-exotic shape: 16 occurrences in a 401-file/36,829-record sample) reported `done` with the tool call invisible — the reference doc's own "trailing tool_use block" wording implied position-awareness the code didn't have. Fixed by deriving the kind from the raw content of the last assistant record only, and folding "tool call resolved but no further reply" and "thinking-only final turn" into the same `stuck_no_result` bucket as "still-pending tool call" — all three mean the same thing for triage purposes: the final turn produced no textual reply. Also fixed: an empty-result exit code/message that differed depending on whether `--kind` or the scope itself zeroed the result (now one check, one message, exit 1 either way); an unguarded `--all-projects` with no date bound could dump tens of thousands of lines with no warning (`--limit` default changed from unlimited to 200, with `--limit 0` as the explicit opt-in); and the `excluded ... automated` counter conflating two different exclusion mechanisms (generic smoke-test regex vs. the new `--exclude-title-prefix`) is now two counters.
- **claude-code-history-files-finder** (`daymade-claude-code` v1.39.0): new **Core Operation 5 — Extract Verbatim User Messages** (`scripts/extract_user_messages.py` + 10 unit tests), producing a reading page (HTML + Markdown) of what the user actually typed across every home and archive. The extractor operationalizes v1.38.0's contamination taxonomy: command envelopes (XML wrapper and bare `/cmd`, args preserved) and hook/loop-injected boilerplate route to appendices — the boilerplate detector is generic (identical long text at >= `--min-dup` occurrences, no hardcoded patterns) and covers both the standalone and the tail-appended shapes; `[Image #N]` placeholders strip; whole-document pastes split off by the >=2000-chars-AND->=60%-ASCII rule; agent-voiced re-injection subtracts only against assistant texts *earlier* than the record (a later agent echo never eats the user's original). Mid-work input is recovered from `attachment.queued_command` (string and list payload variants) with a 120 s de-dupe window against delivered user records. A real-corpus run over a heavy multi-profile history reproduced the hand-built reference extraction from the incident session, with every remaining delta accounted for (sliding 7-day window between runs; the single user-confirmed agent-voiced entry a generic tool cannot know about).
- **claude-code-history-files-finder** (`daymade-claude-code` v1.38.0): `session_file_format.md` gains two sections, both grounded in a real extraction incident where a "what the user actually said" archive shipped contaminated output through three rounds of user correction. (1) **`attachment` records: queued mid-work user input** — text typed while the assistant is still working never lands as a `type == "user"` record; it lives in `attachment.queued_command.prompt` (a string, with an observed list-of-blocks variant), and `attachment.origin.kind` separates `human` (the user) from `peer` (another agent/session) from absent (harness notifications). An extractor reading only user records dropped 153 messages over a 7-day window — exactly the interruption corrections. (2) **A user-role record is not necessarily user-authored text** — `promptSource: "typed"` / `origin.kind: "human"` prove only that text entered through the input box, not who wrote it. Five contamination classes with the splitters that worked: command envelopes (XML wrapper and bare `/cmd` — keep args, they carry real words); hook/loop-injected boilerplate (standalone records AND appended to the tail of the user's own sentence — a prefix-only filter misses the second shape); `[Image #N]` placeholders inside `text` blocks; whole-document pastes (normalized length ≥ 2000 chars AND ≥ 60% ASCII held up without misfiring on long Chinese voice dictations); and agent-voiced re-injection — undetectable from record fields, catchable only by content matching against assistant texts *earlier* than the record, and only in verbatim form (a partial rewrite with a verbatim title defeats exact-match and prefix matching alike). Also records the structurally-safe drop list: `system`/`sdk` promptSource, `isMeta`, `tool_result`, interrupt markers, compact-summary continuations.
- **macos-cleaner** v1.2.1 → v1.3.0: new **Step 2D — Root-Cause Fix**, for when a Docker resource type keeps refilling across sessions instead of being a one-time backlog (usually a CI/CD or dev-loop script tagging a new image every build and never cleaning up the old ones). Covers diagnosing the source (group images by repository — a single repo with hundreds of tags and one active container is the tell), confirming the repository is only consumed locally before automating anything (a registry-backed multi-host pipeline needs registry-side retention instead), and a reproducible-builds caveat (Bazel/Nix/some BuildKit configs can pin `.Created` to a fixed value, so sort-by-creation-time alone can misidentify a fresh image as the oldest). Explicitly requires the user's sign-off *before* writing automated deletion logic into their build pipeline — Core Principles 1 and 9 are about unattended deletion, not which Docker subcommand runs, so avoiding `prune` alone doesn't satisfy them. Also adds: an OrbStack VM disk-usage verification method (`docker run -v /var/lib/docker:/x:ro alpine sh -c "df -h /x; du -d 1 -h /x"`, plus the BusyBox `du -d N` vs GNU `--max-depth=N` gotcha) — an earlier draft of this recommended `nsenter --privileged --pid=host` instead, on the mistaken belief that a plain read-only bind mount couldn't reach the real VM filesystem; a same-session independent review caught it, and a direct A/B test on a live OrbStack install showed both approaches report byte-identical numbers, so the unprivileged form is what shipped; a reminder that the Docker object list is live data on an actively-building machine and must be re-pulled immediately before executing a deletion plan, not reused from an earlier dry-run; and a rule that the database-volume content-inspection requirement also applies to anonymous volumes with no name to pattern-match — a real sample of 10 anonymous volumes found 5 held live, intact PostgreSQL data despite being unreferenced by any current container.
- **claude-code-hooks** (`daymade-claude-code` v1.37.0): new **rule 9 — fixtures cannot tell you the false-positive rate; replay a real command corpus before you register**, plus a matching build-order step placed *before* symlink/registration (so the replay driver isn't self-blocked). Rule 1 ranks which error is worse and rule 2 makes you test at all; neither measures how large the false-block surface is, and the test table structurally cannot — its inputs come from the same mental model that produced the detector. Measured 2026-08-06: a PreToolUse/Bash guard passed a 26-case table with 5 mutations and was registered; replayed against 11,903 deduplicated real commands from 60 recent transcripts it blocked 46, of which **10 were wrong — 21.7% of everything it blocked**, and it had blocked 3 real sessions within 39 minutes before being removed. The rule ships the four-step method with the concrete anchors an agent actually needs (where transcripts live, the exact command-extraction path — `.message.content[]` `tool_use`/`Bash` → `.input.command`, *not* the hook event's `.tool_input.command`; why the pre-filter must be the shipped detector sliced out verbatim; scratch `TMPDIR` so rule 7 receipts don't write into real sessions or silence the guard mid-measurement; Pattern B's forced-decline path for human-gated hooks), a decision rule for the resulting number, and a cross-reference to pitfall #11, which prescribes the same instrument in the under-firing direction. **rule 6 gains a qualifier from the same incident**: a checkable fact can still be the wrong fact — `test -f SKILL.md` is true in a downloads folder, and an unanchored ancestor walk looking for exactly that swallowed a whole home directory and told a real session to load a skill that cannot exist. Known gap, stated rather than hidden: no `scripts/replay_corpus.sh` ships yet, so this is currently the only rule in the file that mandates a procedure without a bundled artifact.
- **transcript-fixer** (`daymade-audio` v1.23.0): promote reviewer reasoning instead of leaving it inert in `decision_note`. The workflow now inspects the complete queue as JSON across every status—including reopened items back in `pending`—then routes each non-empty note to the correct durable surface: domain context, false-positive retirement, domain dictionary, or people roster. It also states the queue's actual execution boundary: recording a note never applies it, and verdict-specific action packs do not cover every decision.

### Fixed
- **Marketplace skill inventories**: `kimi-use` was already present in the canonical marketplace manifest but absent from the numbered lists in `CLAUDE.md`, `README.md`, and `README.zh-CN.md`. All three lists now include it; the manifest-to-doc drift guard and marketplace validator both pass.
- **claude-switch-models-setup** (`daymade-claude-code` v1.36.0): an independent review of the v1.35.0 install step found six real defects, three of which made the instructions actively harmful. (1) **`scripts/setup.sh` was still a `cp` installer** — the very thing step 2 had just been rewritten to argue against — and it deployed only 4 of the 5 scripts, omitting `sync-profile-settings.py`, which step 6 depends on; a machine set up by the one-click path had no settings converger at all. It now symlinks all five, and step 2 points at it instead of leaving readers to find the contradiction themselves. (2) **The manual form silently produced a broken install from a relative `REPO`**: every command still exited 0 while creating five dangling links, so `csk` and the LaunchAgent failed later with nothing to trace it to. The placeholder now says absolute, and says what happens if it is not. (3) **`chmod +x "$REPO"/scripts/*` dirtied the checkout** — four of the six scripts were committed 100644, so following the step produced four permanent mode changes in a repo whose own rules forbid `git add -A` precisely because parallel agents sweep up stray edits. All six are now committed executable and the `chmod` line is gone. (4) The step promised `hook-health-check.sh` as a safety net, but that script lives in a private repo and ships with nothing — the promise was unverifiable for every reader. Replaced with a four-line check anyone can run, and an explicit statement that none is bundled. (5) "A symlink makes both impossible" contradicted the sentence two lines below it that recommended re-checking; an atomic-save editor or a stray `cp` turns a link back into a real file silently, so the claim now holds only *while it stays a link*. (6) The repair for a link that has become a real file now moves it aside first — re-linking on top of it destroys contents that, by the step's own argument, may exist nowhere else.
- **claude-switch-models-setup** (`daymade-claude-code` v1.35.0): install by **symlink instead of `cp`**, which removes the drift v1.34.0 had to repair by hand. `~/.config/claude-switch-models-setup/` is what actually runs — the LaunchAgent and `claude-profile` invoke scripts by that path — while this repo holds their source, and copying created two files that nothing distinguishes: a deployed copy and its source look identical, so "am I editing the SSOT?" is not a judgement anyone reliably makes. Measured on one machine before the switch, drift had happened in **both** directions and neither was noticed: `claude-plugins-sync.py`'s lock-placement fix sat in the repo for **26 days** while the deployed copy kept running the bug it fixed (a lock inside `<base>/plugins` gets symlinked into every profile and goes dangling on release), and two cleanup routines written straight into the deployed `sync-local-skill-sources.py` never reached version control at all. A symlink makes both impossible — there is one file. It also lets `sync-local-skill-sources.py` find its own source repo by resolving its own path rather than falling back to guessing (verified: it now names both repos directly). Machines without the repo still copy, with the trade-off stated. `hook-health-check.sh` gains a SessionStart check that flags any of these becoming a real file again or going dangling, calibrated three ways: silent when all are links, red-and-named for a real file (with the re-link command), red for a dangling link.
- **claude-switch-models-setup** (`daymade-claude-code` v1.34.0): `sync-local-skill-sources.py` had diverged from its own deployed copy in **both** directions, and each side was missing something real. The deployed copy at `~/.config/claude-switch-models-setup/` carried two cleanup routines that were never folded back into the source; the source carried the sync-lock placement fix from PR #128 (the lock must live *outside* `<claude_dir>/plugins`, which `claude-plugins-sync.py` scans-and-symlinks into every profile while the lock is held) that the deployed copy had never received. Merged in the direction the skill's own install step defines — source is authoritative, `~/.config/` is the deployment target — so neither side lost work, then redeployed. The two routines now shipping from source: **version-alias symlinks** are pruned (each cache link is named after the marketplace's current version, so every bump left the previous link behind pointing at the same source directory — one plugin had six version directories, four of them aliases for one source; real directories are never touched, since a live session may still hold one through `.in_use`), and **`installed_plugins.json` backups** are capped by a `KEEP_JSON_BACKUPS` constant (every run that changed the JSON wrote one and nothing removed them — a month of runs left 453 files behind). Both are calibrated in both directions against isolated fixtures: they delete what they must, and leave real directories, differently-targeted symlinks, broken links, and under-quota sets untouched. SKILL.md's two behaviour descriptions were written before either routine existed and are now accurate.
- **transcript-fixer** (`daymade-audio` v1.22.0): the trap-scan coverage warning shipped in #256 was reviewed, found **not yet usable**, and rolled back in a working tree that never got pushed — so the defect stayed on `main` while the rollback existed only locally. Repaired in place instead, against the review's own gate: **zero false positives on real context files**. It measured 7; this now measures **5 on 6 real files, all true positives**, down from 9 before the repair. What changed: (1) rejecting prose is `_BAD_VARIANT`'s documented job, so a bullet that still yields a scannable variant no longer reports its rejected siblings — flagging each one turned every line of commentary into a "not scanned" warning; (2) whitespace only makes a term inexpressible when the term genuinely contains it — a Latin+CJK compound (`PEST 框架`, `人均 GDP`) — while Han characters split by a space are prose punctuation (`单母题固定成本 800`, the review's named false positive, 11 chars and thus *under* the length cap that was supposed to catch it); (3) the two-trap probe reads only the segment `_parse_to_side` keeps and matches only 「→」, the arrow `_BOLD_TRAP` itself requires, so an annotation citing another rule no longer appears as both a warning and a hit — and an annotation that *exemplifies* the same rule in a longer word (`**码 → 嘛（页码→页嘛）**`) is recognised as an example, not a second trap; (4) three producers could fire on one bullet, so a file with 3 unscanned bullets announced "5 traps NOT scanned" and sent the reader to fix one line twice — now one line per bullet. Two silent-loss paths the review had deferred are also closed: a bullet written with an ASCII `->` was invisible to the parser entirely (no entry, no hit, no warning — it renders fine, so nobody notices) and is now named; and keep-word synonyms (`不要改`) outside the whitelist made confirmed-correct records vanish. **Tests**: `finding 11` recorded that all 19 existing tests called `extract_trap_entries` with one argument, leaving every new branch dead code; `TestDroppedCoverage` adds 14 cases passing `dropped` explicitly, and is calibrated in both directions — against the pre-repair version exactly the false-positive cases fail, against the current one all 33 pass.
- **transcript-fixer** (`daymade-audio` v1.22.0): `--report-false-positive` told the user to edit a **cross-project person-name SSOT** on an unverified assumption, and had no answer at all for the case it was built for. Reviewed against a real environment (database dump hashed before and after — zero writes). (1) It asserted "still being re-supplied by the people roster" whenever the roster contained the pair, but a run using that domain suppresses the roster copy too — so the claim was false for exactly the domain just asked about, and acting on it deletes a correction from every other domain and project. It now states the scope instead of the mechanism, and names the domains where the pair is genuinely still active. (2) A **roster-only** pair — supplied by the roster, never in the database — got `❌ No active rule` and exit 1, word for word the failure this command exists to prevent: it fires on every run, the user runs this to stop it, and is told it does not exist. It now explains that disabling works by retiring a database row and there is none, then gives both ways forward. (3) Exit codes became a contract, because automation could not tell "I just disabled it" from "it was already off" — both returned 0: now `3` already-disabled, `4` roster-only, `2` malformed `--domain` (previously a bare traceback with empty stdout and exit 1, indistinguishable from a real not-found). (4) Every non-success path used to leak a service-layer `No active rule` warning to stderr that contradicted the stdout message beside it; all outcomes are now resolved before the service call. The internal term "veto" is gone from user-facing output, replaced by a check the reader can actually run.
- **claude-md-progressive-disclosurer** (`daymade-claude-code` v1.29.2): an adversarial reviewer executing every shipped command block on BSD and GNU found a **check that certifies itself green while the rule it encodes is being violated** — the exact failure this skill's own discipline warns about. Appendix C tested `if find … -exec grep -qF {} +`; when `find` matches **zero** candidate files, `-exec` never runs and `find` exits 0, so the `if` is true — meaning **one directory that exists but holds no `.md` makes every heading report "✓ found", including genuinely missing ones** (identical on BSD and GNU; realistic trigger is `mkdir docs/references` before writing into it). Proven by direct A/B: old code reports `✓` for a heading present only in the baseline, fixed code reports `✗ NOT FOUND`. The loop now tests `grep -lF` output for non-emptiness and never consumes `find`'s exit status. Four more from the same pass: the multi-line substring probe called bare `python`, which does not exist on stock macOS 12.3+ or on slim Linux images (now `python3`, matching the file's two other call sites); a regex-metacharacter example was written with markdown escaping, so an agent reading raw bytes would copy `\|\|` — which errors on BSD and matches *every line* on GNU, the inverse of what the row claimed (example removed); Appendix C's header note asserted the old glob form did not follow symlinks, which is false (glob names the symlink, grep follows explicit arguments) — corrected to its two real defects; 案例 14 still prescribed the `grep` verbatim-check that 反模式 6 had just been corrected to forbid. Also: 5a skipped every `docs/references/…` pointer as "relative to unknown root" — **the exact layout this skill's own Step 3 prescribes** — so it checked nothing on a typical project-level file; relative paths whose first segment exists in cwd are now judged. Re-verified on real corpus: 0 false positives, planted break still caught, bash and zsh byte-identical.
- **claude-md-progressive-disclosurer** (`daymade-claude-code` v1.29.1): the 5a reference-existence check shipped in 1.29.0 was verified only against synthetic fixtures. Run against **real corpus** — a 120KB global CLAUDE.md — 10 of its 32 findings were false `MISSING` reports: bare filenames mentioned in prose, glob patterns (`*/memory/*.md`), templates with placeholders, and a pair of paths joined by an arrow inside one backtick span. A **31% false-positive rate on healthy input** trains the reader to ignore the check, which by this skill's own rule is worse than having no check. The loop now separates *judgeable* pointers (absolute / `~` / explicit-relative) from *unjudgeable* ones (globs, placeholders, rootless filenames), reporting the latter separately for manual confirmation. Re-verified on the same real corpus: 21 judgeable all correct, 0 false positives, and a planted broken pointer is still caught — in bash and zsh, byte-identical output. That real-corpus run also surfaced **one genuine broken pointer** the synthetic fixtures could never have produced (target had been moved into a `.memory-archive-*` dot directory, with a case change in the path).
- **claude-md-progressive-disclosurer** (`daymade-claude-code` v1.29.0): adds a carrier-allocation model (which rules belong in a blocking hook, a context-injecting hook, a skill, a reference, or resident prose — keyed on "can the model know it needs this rule *before* it violates it?"), a five-row 判据陷阱 table for validators that fail silently, and two new cases. The 判据 section also **fixes a defect it was itself demonstrating**: it prescribed `grep -R` as the cure for "recursive search skips symlinks", but `-R` follows symlinks only on GNU grep — on macOS's own `/usr/bin/grep` it matches nothing (needs `-RS`), and `-RS` in turn *errors out* on GNU. There is no portable flag combination, so every recursive-grep prescription in the skill is replaced with an implementation-independent form (`readlink -f`, or `find -L … -exec grep -lF {} +`, both verified against BSD grep 2.6.0 and GNU grep 3.11 with positive and negative controls). A wrong prescription is worse than none: it does nothing, silently, in the very section warning that validators fail silently.
- **skill-creator** (`daymade-skill` v1.21.0): the Description Optimization loop's existing "sanity-check the harness" advice only fired *after* `best_description` came back — a full 5-iteration run (each iteration a complete eval batch, dozens of `claude -p` subprocess calls) could burn its entire budget against a completely dead probe before anyone looked at the numbers. `run_loop.py` now self-aborts after iteration 1 if literally zero triggers fired across every should-trigger query, skipping `improve_description` and returning `exit_reason: "degenerate_harness: ..."` or `"infra_error: ..."` (execution failures vs a genuinely dead probe) instead of continuing to iterate against nothing. Scoped strictly to zero-at-iteration-1 so a weak-but-nonzero, still-improvable description is never auto-killed. Two rounds of independent review (fresh agent each round) found and fixed a polarity-inverted counter-example (positive triggers 0 but negatives firing heavily was misdiagnosed as a dead probe), an infra-vs-description attribution ambiguity, a negative-side-errors gap in round 1's own fix, and a pre-existing `--holdout 0` report-generation crash surfaced along the way; `generate_report.py` now renders a banner when either exit reason fires, and `tests/test_run_loop_degenerate_guard.py` (10 tests, mock-only, no real `claude -p` calls) is the resulting regression suite — see methodology Case 20 for the full story of what each review round caught.
- **skill-creator** (`daymade-skill` v1.20.0): discipline #6's instrument rule gains its shipping counterpart — **calibrate against the *standard* implementation, not the one on your machine.** The existing rule keeps the author's own conclusions honest; this keeps the *reader's* commands working, because a tool-behavior claim written into a skill executes on binaries the author has never seen. Names both mechanisms that make this invisible from inside a session — the same command name resolving to a different program (shell alias/function shadowing; note `\tool` escapes an *alias* only, so `command tool` is the sole deterministic form) and the same program behaving differently across BSD/GNU implementations — and requires re-running any tool-behavior assertion against `/usr/bin/<tool>` before it enters a shipped artifact, preferring the implementation-independent formulation when it does not survive.
- **skill-creator** (`daymade-skill` v1.18.0): close four execution gaps an independent review found in the project-level-overlap guidance added in 1.17.0 — it gave a direction but no mechanism. "Retire the project-local skill" now says how (grep the project for references first, leave a `superseded by` stub), what to do when the owner is unreachable (harvest only, do not retire) or declines (that is the Coexistence & Precedence case, not a failure), and marks "reconcile toward it" as a **rebuttable presumption** with two standard exits (the project skill may be stale or project-specific; re-verify harvested rules). The ownership test gains a fallback for when both probes are silent (ask, don't guess), a fork caveat (your remote, someone else's content), and a note that a project's `git remote` answers ownership even without a `marketplace.json`. Also fixes a **directional contradiction**: Prior Art Research says merge *into* the existing skill, while the project-level case requires harvesting *from* it — the two now cross-reference instead of giving opposite instructions.
- **skill-creator** (`daymade-skill` v1.17.0): the prior-art sweep command shipped in 1.16.0 could not reach three of the roots the surrounding prose claimed it covered. It searched for *directories named* `skills`, but source repos, marketplace clones and plugin caches name their skill directories after the skill — so those roots were silently skipped while the sweep appeared to work, reproducing the exact accident the section was added to prevent. Now searches for `SKILL.md` (layout-agnostic), adds a **coverage self-check** so "it reached that root" is verified rather than inherited from prose, and filters by capability vocabulary in every language the target skill might use. All three steps were run on a real machine and confirmed to surface the skill the original war story missed. Also adds an ownership test (marketplace `owner` / `git remote`) for routing overlaps, and the disposition branch the war story lacked: what to do when the overlap is a project-level skill in an unrelated project.
- **repomix-safe-mixer** v1.0.2 (community PR #164, @thejesh23): dotenv files are now actually scanned — `Path('.env').suffix == ''` meant extension matching silently skipped the most common secret locations; scanning now matches `.env` / `.env.*` by exact filename.
- **macos-cleaner** v1.2.1 (community PR #163, @thejesh23): large-file categorizer no longer matches `log` as a substring of any filename — `catalog.pdf`, `dialog.wav`, `Prologue.mp4` were being misclassified as safe-to-delete logs; matching is now extension-based.
- **install.sh** (community PR #165, @thejesh23): stop advertising plugin names that don't exist in the marketplace (`skill-creator`, `markdown-tools`); the installer now only offers plugins that actually install (`daymade-skill` suite, `github-ops`, `teams-channel-post-writer`, `repomix-unmixer`, `llm-icon-finder`).

### Added
- **claude-switch-models-setup** (`daymade-claude-code` v1.41.0): add region-specific MiniMax-M3 and MiniMax-M2.7 profile templates with the current global and China compatible endpoints, verified context-window settings, and explicit thinking-mode behavior.
- **skill-creator** (`daymade-skill` v1.23.0): Step 8 asks you to bump the version, then stops — so the changelog entry, which is the part that makes a fix *findable* rather than merely *installable*, depended on remembering a convention that lives nowhere in the procedure. Real case that prompted this: two consecutive releases of one skill shipped with correct bumps, green gates and merged PRs, and **no changelog entries at all**; both were caught only by a later audit, and in a file that documents every other skill's versions the gaps read as "nothing changed there". Step 8 now requires the entry in the **same commit** as the bump, and points at matching the file's existing entry shape rather than inventing one. This is discipline #6 applied to this file itself — a rule carried by convention instead of by a step loses to completion-drive every time.
- **asr-transcribe-to-text** (`daymade-audio` v1.21.0): the client-side splitter had two silent failures, and the reference that documents it never said when *not* to use it. `overlap_merge_transcribe.py` hardcoded `chunk_NN.mp3` with `-acodec copy`, so any non-MP3 input made every ffmpeg call fail — and nothing checked the exit status. Measured both ways on one WAV: the old version printed normal progress, returned 4 chunk paths, raised nothing, and produced **4 files of 0 bytes**; the failure only surfaced downstream as a JSON parse error on an empty response. The container now follows the input's extension (so `copy` stays valid), and both the exit status and the resulting file size are checked; `get_duration` likewise no longer lets a failed ffprobe reach `float('')`, which had been reporting "could not convert string to float" for a file that simply could not be opened. Chunk-boundary arithmetic is byte-identical (same 4 boundaries before and after). `references/overlap_merge_strategy.md` gains the missing precondition: vLLM's endpoint already splits at the quietest point in a ~100 ms window with 1 s overlap, which *avoids* the truncation this document repairs — against such an endpoint client-side splitting makes the output worse, so the technique applies only where the server cannot take the whole file and cannot be reconfigured.
- **asr-transcribe-to-text** (`daymade-audio` v1.20.0): make the remote path self-contained. Knowledge needed to keep a self-hosted endpoint running had been filed in a private machine note — filed there because that is where it was hit, which is the wrong axis; the right one is whether it holds for anyone. Path B's diagnosis gains three steps: `ss` alone lies about what is listening (it shows only your own user's processes, so a server running as another user or **inside a container** is invisible while serving traffic — ask `docker ps` too); check whether the GPU is actually held before starting another server (an empty compute-apps list means nothing is using it, whatever an older note claims); and `pkill -f 'vllm serve'` kills the command that issued it, because `-f` matches the whole command line and yours contains that string — the old process dies, the new one never starts, nothing reports an error, so use `[v]llm serve`. The mode table also gains the judgement that actually decides local vs remote: not speed, but **where the audio already is** — a remote GPU may be ~4x faster, yet transcript text is ~10,000x smaller than its audio, so moving files to reach it routinely costs more wall-clock than the transcription (measured once at 63 KB/s, over two hours for 500 MB, to save minutes of compute).
- **asr-transcribe-to-text** (`daymade-audio` v1.19.0): document what a self-hosted vLLM endpoint actually rejects — four failures whose message points away from the cause. MP3 is refused on 0.15.x **as HTTP 200 with an error body** (a status-code-only check reports success), and the reflex fix of converting to WAV then walks into the 25 MB request cap since 16 kHz mono PCM is ~32 KB/s; OGG is accepted and ~8x smaller (measured 245 KB vs 1,920 KB per 60 s). `v0.26.0` added `VLLM_MAX_AUDIO_DECODE_DURATION_S` (600 s) on the line right after the size cap — a **separate** gate that raising the size cap does not lift, so a lecture-length file that works on an older server is refused by a freshly installed one. An offline host fails to load an already-cached model until `HF_HUB_OFFLINE=1` (a containerized server's separate `HF_HOME` is a different cause with the same symptom). And vLLM already chunks long audio at low-energy points, so Step 5's client-side splitter is scoped to endpoints that reject long audio outright. Two independent fresh-context review rounds against a pre-work git ref: the first caught that "re-checked against v0.26.0, unchanged" was literally true yet wrong — the verified line had not changed, while the second gate added directly below it was missed, which would have had every file over 10 minutes rejected on current vLLM; the second verified every vLLM claim against PyPI and the v0.15.1/v0.26.0 sources and caught a FLAC measurement that compared 24-bit against 16-bit WAV.
- **claude-code-hooks** (`daymade-claude-code` v1.30.0): adds a **Maintenance — where new content goes** section, codifying the growth outlet already in practice — incident backports route by kind (pitfall/anatomy → `hook_pitfalls.md`, skeleton/pattern → `hook_patterns.md`, worked harness script → `scripts/`), and the main file only takes contract-level rules every blocking hook consumes. This settles a four-frame design review (cost / SSOT / architecture / evidence, cross-examined) on whether to split the 50k-char SKILL.md: the split was rejected — the 25k-token premise measured 2× off (~12.6k actual), zero observed pain in git history, rules 1–8 are an interlocking numbered system, and compressed one-liners are proven error-breeders (pitfalls #22/#26 were both fixed by independent review after publication). Restart-the-split criteria are written into the file: a measurement showing size degrades compliance, or 30 consecutive days of churn settling.
- **skill-creator** (`daymade-skill` v1.19.0): four gaps closed, each from a failure that happened *while following the existing guidance*. **Retirement now starts with `find` for the skill's bodies, not `grep` for its references** — a skill routinely has copies in both `.claude/skills/` and `.agents/skills/`, and grep answers "who mentions it" rather than "how many of it are there" (with the `--exclude-dir` trap that hides same-named directories, a reachability check before deleting, and a defined stub shape). **The trigger for sanitizing is the destination's `isPrivate`, not how much the task feels like publishing** — a private→private migration into a marketplace skill reads as "publishing" and fires the reflex even with the private banner on screen. **Discipline #6 gains its counterpart: the checks you *run* to verify your own work are instruments too** — calibrate on a known answer first (`find` without `-L` and `--exclude-dir`'s basename matching both fail silently). **For an edit to an already-published skill the review gate anchors at the push**, not at Sanitization Review, which a docs-only change may never reach — with a back-reference at the push step itself, because a rule living far from its point of use is the failure mode that section already names.
- **skill-creator** (`daymade-skill` v1.16.0): make the prior-art sweep discover skill roots with a `find` instead of recalling a list, and name the root a from-memory list reliably drops — **every project's own `.claude/skills/`**. Per-project skills are structurally invisible: they appear in no marketplace, no global skill list and no source-repo listing, so a mature domain skill can already exist there while the sweep reports "no prior art" with full confidence (real 2026-07 case included). Also adds "search by capability vocabulary, not by skill name" — the missed skill would not have matched a name search.
- **openclaw-model-switch** v1.1.0: broaden from "switch model id" to switch-or-repair model configuration, distilled from a real production incident. Adds a field-tested trap catalog (`references/troubleshooting-model-config.md`): env `KIMI_API_KEY` hijacking the provider's wire key over `provider.apiKey` (with a local echo-server wire-capture recipe), provider plugins hardcoding thinking levels and the custom-provider bypass, `params.canonicalModelId` unlocking extended thinking levels (xhigh/adaptive/max), relay `/v1/models` listings being non-authoritative, group/network-dependent model availability, and multi-config/mirror discovery. The switch script now discovers candidate config paths instead of assuming one, syncs mirror files, supports `--provider`, and knows the k3 model definition. SKILL.md is restructured into a diagnose-first workflow (find real config → probe endpoint+model before editing → switch → mandatory agent-turn E2E verification).
- **windows-remote-desktop-connection-doctor** v1.1.0: extend the AVD/WVD/W365 transport-quality skill to cover direct PC connections and stuck "Configuring remote PC..." dialogs. Add an independent RDP protocol probe (`scripts/probe_rdp_server.py`) to falsify server-side failures without credentials; a new identity-poisoning category for expired Microsoft work/school accounts that block even direct PC connections, with OneAuth/MSAL log signatures and the fix; a Windows-side reboot-correlation path (`LastBootUpTime` + Event ID 1074 via WSL/SSH); per-session GUID log analysis; UTC timestamp alignment; and stuck-dialog vs. live-session-on-another-display discrimination.
- **local-conversation-history** (`daymade-claude-code` v1.11.0): list recent local Claude Code and Codex conversations for the current workspace with one read-only, standard-library command. The skill selects the newest compatible Codex thread database through schema introspection, visibly recovers through raw rollout JSONL when needed, reads only bounded Claude session prefixes, emits presentation-ready Markdown or JSON with timezone-qualified timestamps and exact session IDs, normalizes Windows paths, honors profile-specific homes, and excludes sub-agents plus obvious smoke/test prompts by default. Added isolated SQLite/JSONL/Windows regression fixtures and three behavior evals.
- **photo-to-scanned-pdf** (daymade-docs v1.3.0): convert phone photos of paper documents into scanner-quality A4 PDFs with perspective correction, noteshrink enhancement, colored-paper handling, explicit content-based page ordering, and mandatory whole-document contact-sheet verification.
- **github-review-pr** v1.2.0: review or re-review one contributor PR—including an explicitly named closed PR under reconsideration—or sweep every open PR newest-to-oldest against the live base. It separates PR-recorded-base/current-base/head snapshots, detects history discontinuity, isolates the verified contribution onto current main as a non-landable synthetic projection, reviews actual three-way results, requires target evidence for findings, separates severity from confidence, assigns PR/BASE/SHARED ownership, and remains read-only by default. Its explicit personal-maintainer context learns only maintainer-authored precedent, enforces curation before contributor metrics, treats Claude for Open Source eligibility only as a post-merit priority, preserves worthy original contributor PRs through authorized non-force repair plus squash landing, distinguishes `DECLINE` from supersession, and requires a fresh per-PR merge confirmation after every repair/re-review. A short affirmative reply now confirms the one immediately surfaced PR without requiring a magic phrase, while never carrying authority to another PR; sequential landings invalidate every later current-base review; history-repaired squash landings use reviewed commit metadata and verify the landed tree, mapped contributor author, and branch state.
- **design-style-picker** v1.0.0: batch-generate and compare multiple visual design directions so a user picks the style they actually want, instead of guessing one final design. Targets users who cannot describe an abstract visual style in words; ships a selection playbook and reusable prompt patterns, and evolves an existing UI/design system without discarding current assets.
- **claude-migrate-memory-to-doc** (`daymade-claude-code` v1.19.0): migrate Claude Code personal memory (per-project `memory/`) into tool-agnostic reference docs so other AI CLIs auto-loading `AGENTS.md` (Codex primarily; transfers to Cursor) read the same user profile and collaboration preferences. Two-layer `references/` + CLAUDE.md-inline + AGENTS.md-symlink architecture designed around what each tool actually auto-loads; runs inline with multi-agent review and empirical `codex` verification. Also newly registers `claude-migrate-memory-to-doc` in the suite's `skills` array (it had shipped on disk unlisted).

### Changed
- **skill-creator** (`daymade-skill` v1.22.0): six corrections distilled from using the skill to ship consecutive updates to an existing skill, each one a place where the workflow let a predictable mistake through. (1) **Description budget** — the 1024-character ceiling was never stated, so an update that added trigger phrases for newly-covered scope blew past it and took two rounds of compression to land; the guidance now names the limit, notes that it is in direct tension with the "pushy" advice, and makes explicit that near the ceiling **adding a trigger is zero-sum** (you are deleting an existing one to pay for it) — a trade that must be made consciously and recorded, since a silently-dropped trigger phrase narrows when the skill fires and nobody notices until it stops firing for someone. It also ranks what to cut: prose qualifiers are re-derivable from the body, distinct trigger phrases are not. (2) **Registry minimal-diff** — the marketplace manifest is the single file every skill shares and therefore the likeliest concurrent-edit collision; scripted bumps silently normalize trailing newline / indent / key order, so the step now requires a round-trip check that `git diff` shows only the intended fields (a scripted bump once added a trailing newline to a manifest that never had one). (3) **Activation check** — "sync the installed copy" is often not work at all: a symlinked skills dir or a `source: directory` marketplace reads the working tree, so edits are already live, while only cached/copied installs need the official update. Verify by grepping the resolved runtime file for a phrase unique to the new content, never by trusting a recorded version string — one session read a plugin record naming a cache directory with the new version in its path and nearly reported the update as live; that directory had never existed. (4) **Production-as-eval** gains a second signal source: when a skill's output is something that keeps running (guard, monitor, scheduled job, hook), its own telemetry is eval data, and the **first false alarm** is the highest-signal record in it — a user correction needs a user to notice and bother, while a deployed mechanism reports on itself unprompted, and a false positive proves a rule is wrong in a way re-reading never would. (5) **Concurrency now covers branch switching, not just a moved HEAD** — a checkout is worktree-wide, so a sibling session running `checkout main` mid-edit lands your next commit on **main**, violating the repo's never-commit-to-main rule while your feature branch still points at the old base; the pre-commit check gains `git branch --show-current`, with `git reflog` as the authoritative reconstruction and a ref-only repair (`checkout -B` + `branch -f`) that, unlike `reset --hard`, cannot destroy a parallel session's uncommitted work. (6) **PR staleness** — the same property that makes the manifest a collision hotspot makes an open PR go stale, so `CONFLICTING` is the expected state rather than a surprise (this PR itself sat through 69 commits of main). Conflicts there are additive (two authors appended to the same section), so keep both sides, never `--ours`/`--theirs`; and the skipped step that catches a bad resolution is proving afterwards that the **only** difference from the base is your own entry, with a copy-paste check for it. Push with `--force-with-lease`, whose whole value is failing exactly when someone else pushed to your branch.
- **frontend-visual-qa** v1.11.0: make the user-supplied target canonical and separate current-render truth from delivery freshness. Web navigation preserves the exact URL while persisted evidence redacts paths, query values, fragments, navigation errors, and target values reflected into rendered labels; reports store label hashes plus a target-string fingerprint. Single-file evidence adds a byte hash, multi-resource files use a resource/dependency manifest, and native apps use an installed-artifact fingerprint. Source, interaction/data, and target-lifecycle authority are independent. The skill now traces source → build → runtime → target → inspected pixels only for freshness/deployment claims, reports “source fixed; verification target stale” without blocking read-only inspection, and requires same-target identity/visual recheck only for fix closure. Every probe header value uses environment indirection, and raw screenshot/report directories are temporary local sensitive evidence.
- **git-safety-net** v1.7.0: close the gap between "judge by content, not counts" and *which* content check to trust, plus a shared-worktree hazard. Distilled from a real audit in which three successive content-level instruments each returned a wrong answer before the trial merge settled it: `git cherry` (squash rewrites patch-ids → false UNMERGED), a **three-dot** `diff base...ref` used to ask "what does base lack" (wrong question — under-reported missing files 1 vs 5), and a file-level existence check (a file present on base can still be missing the ref's lines). Adds a diff-form section (two-dot vs three-dot, chosen by the question) and a **fourth supersession rung**: grep the base for the missing file's own name, because a replacement usually documents the removal in prose — a 107-line script absent from the base looked like textbook unique work until its successor's comments read "replaces the old …", "made this worse, not better", "CAUSED the corruption", i.e. deliberately excised harmful code whose "rescue" would have reintroduced a known bug. Also separates generated artifacts (scan markers, lockfiles) and relocated paths from real loss. New Mode D rule: in a shared tree, never aim `reset --hard`/`merge`/`rebase` at "the current branch" — a branch check goes stale the instant it returns, so a parallel session's `switch` redirects your destructive command onto **their** branch; use checkout-independent forms (`git branch -f`, `git fetch origin <branch>:<branch>`) that name their target.
- **claude-code-hooks** (`daymade-claude-code` v1.23.0): add a fifth pattern — Stop hook, the only hook type that can react to Claude's own generated text (`UserPromptSubmit` only ever sees the user's input, a category mistake that caused a real same-day incident: a hook meant to catch Claude inventing an unverified shorthand name never once fired, while repeatedly false-blocking the user's own unrelated typing). Covers the full contract (`last_assistant_message` vs `transcript_path` fallback, the `stop_hook_active` anti-loop check and its JSON-string-vs-Python-truthiness trap), with a runnable, tested skeleton that uses a quoted heredoc instead of `python3 -c "…"` to structurally avoid a newly-cataloged pitfall (#9, 8→9 total): a literal quote or backtick inside a Python *comment* can silently corrupt an embedded multi-line block without `bash -n` catching it — confirmed by extracting and executing the shipped skeleton against 5 real JSON payloads, not just reading it. Also fixes CLAUDE.md / README.md / README.zh-CN.md skill lists, which were missing `docx-creator` and `claude-code-hooks` (both already registered in `marketplace.json`, never synced to the human-facing lists).
- **debugging-network-issues** v1.5.0: extend the cognitive-trap catalog into the LAN layer with three traps distilled from a real home-network incident whose first-day conclusions were overturned on re-investigation: fingerprint ≠ identity (a port-5000 `AirTunes` responder with no `_raop` broadcast "looked like" a DIY shairport box but was a macOS AirPlay Receiver — check SSH host keys against `known_hosts`, mDNS, and AirPlay `/info` before concluding what a device is), unreachable on one segment ≠ dead (the old router was ARP-silent on Ethernet yet still serving DHCP on Wi-Fi, silently capturing devices), and topology changes orphan manual-IP devices (including macOS "Manually Using DHCP Router Configuration" half-manual configs). Description now also triggers on LAN mysteries: unknown devices, subnet-change fallout, hosts "dead" on one segment but alive on another.
- **git-safety-net** v1.3.0: make repository convergence and worktree retirement first-class. The loss audit now inspects every linked checkout for tracked/untracked changes and includes detached worktree HEADs in the off-remote commit set; the backup exporter adds a verified `--all-refs` bundle covering worktree/stash/hidden refs; and the merge verifier no longer exits silently when a real branch conflict makes `git merge-tree` return 1. Add an explicit clean-status → exact-HEAD → containment → bundle → non-forced-removal workflow, UI metadata, and synchronized marketplace/README descriptions.
- **daymade-claude-code** v1.15.0: `local-conversation-history` and
  `claude-code-history-files-finder` now treat Claude history as one explicit
  source set: auto-discovered active homes plus every long-term archive in
  `~/.claude/history-sources.json`. Required archives fail closed instead of
  allowing a false whole-history absence claim; duplicate session IDs retain
  provenance, union their internal ranges, and use the newest copy only for
  representative title/path selection (active wins an exact tie). Claude
  inventory and date filtering now stream all JSONL records to compute true
  internal minimum/maximum ranges and never use file mtime. Codex raw-rollout
  fallback now follows the same internal-time rule, and state-database ties use
  the numeric generation instead of database mtime. Deep search unions
  distinct records across every physical copy, applies date windows to matching
  records, and covers
  message text, thinking, tool inputs/results, queue operations, attachments,
  last prompts, system/summary content, and custom titles while excluding
  structural IDs/signatures. The finder also sweeps every project in one pass
  with `--all-projects`, optionally covers Codex rollout history with `--codex`
  (mirror records counted once, project filtering by rollout cwd), and skips
  self-matches with `--exclude-session`; zero-match output suggests the
  widening not yet applied. Added isolated archive/mtime/event-field regression
  fixtures and behavior evals; simple cross-provider listing remains routed to
  `local-conversation-history`, while keyword/recovery forensics remains routed
  to the finder.
- **meeting-minutes-taker** (`daymade-audio` v1.9.1): documentation-governance sync for Step 3.5 — completeness_review_checklist.md now carries a scope note declaring itself a same-context self-review whose shared-blind-spot gap is covered by Step 3.5 (run both); meeting_minutes_template.md Action Items table gains a "Notes (conditions/expiry)" column so conditional commitments keep their expiry condition in the retrievable layer.
- **meeting-minutes-taker** (`daymade-audio` v1.9.0): add Step 3.5 Retrieval Self-Test — a consumption-side verification gate between merge and delivery. A fresh-context subagent that never sees the draft reverse-extracts a "future-query claims list" from the transcript alone (who + instruction/promise/decision/veto + scope + timestamp, chunked for long transcripts), then each claim is hit-tested against the retrievable layer (Key Decisions / Action Items / Parking Lot / Open Questions) with component-level judging and lexical anchors. Misses that survive a mandatory revocation scan are promoted with a `[self-test promoted]` tag plus a greppable verbatim quote; uncertain items route to Open Questions, never inflating the decision table; output is always "enumerated N / hits M / promoted K / uncertain" (never a binary pass) and the gate fails open with a visible NOT-RUN note. Rationale: the three same-prompt generation passes are correlated classifiers — UNION merge protects against content loss but not shared blind spots (a narrative-voiced directive missed by all three passes surfaced only when the user later queried the decision table). Validated empirically on two real transcripts before shipping: the extractor caught the original missed directive with zero hints, plus one new real miss on the already-fixed minutes and three on an older meeting's minutes. Also adds an element-based (not phrasing-based) decision-recognition rule to the generation prompts with a precision guardrail.
- **meeting-minutes-taker** (`daymade-audio` v1.8.0): make source-side speaker labeling the first action for anonymous speaker labels. When a transcript arrives with generic "Speaker N" labels from a platform that supports manual labeling (Feishu Minutes, Tencent Meeting), the skill now stops and asks the user to label speakers on the platform page and re-export, instead of inferring identities from text. The former feature-analysis workflow (Phase A–C) is demoted to an explicit fallback — used only when the user declines or the source cannot be labeled — that requires per-speaker evidence and confidence, keeps unresolved labels as-is, and corrects the minutes after the user later labels the source. Rationale: platform labeling is voice ground truth; text inference only resolves name-called speakers and cannot recover diarization-merged segments.
- Marketplace version: 1.83.0→1.84.0; `daymade-claude-code` suite: 1.10.0→1.11.0; README.md / README.zh-CN.md / CLAUDE.md synced for `local-conversation-history`.
- **auto-repo-setup** v2.0.0: replace role-based "non-technical user" assumptions and the Python/video-specific audit with an outcome router and stack-aware read-only inventory; make natural-language/project instructions the default for routine startup sync, with no automatic stash/merge/rebase/force; add a hook-diagnosis workflow that distinguishes duplicate registration from multi-agent firing; and narrow SessionStart automation to an explicit pre-prompt exception. The Claude initializer now preserves unrelated settings, uses matcher "startup", validates paths, writes atomically, supports dry-run/removal, migrates only its own legacy entry, and never mirrors itself into Codex. Add 13 script tests, four behavior evals, and a lifecycle decision reference grounded in current Anthropic/OpenAI/Git documentation.
- **frontend-visual-qa** v1.3.0: replace the accumulated all-in-one checklist with an audit-only-by-default contract, scoped audit profiles, explicit A–D evidence levels, verified/partial/blocked completion states, and conditional references for core layout, journeys/page contracts, and data visualization. Restore and strengthen the contracts that a first compression pass had dropped: intended projection/deck canvas, computed typography evidence, authenticated-but-role-less fail-closed state, chart units/source/time/freshness and non-happy states, dense timeline collisions, selected provider/model/runtime truth, real file-dialog boundaries, and a tired-user adversarial rewalk. Harden the bundled Playwright sweep against HTTP error-page false passes, ineffective mobile viewports, clipped text, non-focusable custom controls, stale output directories, duplicate section screenshots, and ambiguous CLI failures; add behavior/trigger evals with public self-contained fixtures.
- **daymade-skill** v1.11.0: make every existing-skill edit a migration with an authoritative old-bundle baseline and explicit disposition audit. Add `audit_skill_regression.py` to create provenance-bearing pre-edit snapshots or verify a reconstructed Git tree against an immutable commit, then surface removed Markdown clauses and bullets, trigger clauses, files and executable modes, command lines, environment variables, flags, code symbols, behavior evals, and trigger evals without using fuzzy similarity as proof. Exact text moved only into evals/tests or an unreachable reference no longer counts as runtime preservation; same-path script/asset changes also require review. Preserved/sanitized/fixed classifications require current evidence, and file-level claims additionally require a named semantic review because a fingerprint cannot prove behavior. Runtime capabilities cannot be dismissed as `not_reusable`, and boundary/removal dispositions require traceable user approval. Successful verification writes a schema-versioned `.skill-regression-reviewed` status receipt, while `package_skill.py` re-verifies the completed review on every existing-skill package attempt, so a clean commit or hand-written marker cannot bypass the gate. Add behavior evals, known-bad validator self-tests, and focused regression/package tests.
- Marketplace version: 1.82.0→1.83.0; README.md / README.zh-CN.md / CLAUDE.md synced for `github-review-pr` without adding a derived skill-count badge.
- **daymade-claude-code** v1.9.0: `read-claude-web-conversation` now exports the full active conversation path with real tool-use/tool-result blocks, inventories and downloads user uploads, generated images, and sandbox deliverables through the correct endpoint family, reconstructs sandbox-created files from tool history, and renders faithful Markdown locally. Add a macOS AppleScript injection channel for account-mismatch cases where the Chrome extension cannot pair. File downloads preserve duplicate names with deterministic suffixes, ignore abandoned conversation branches, and require size/magic-byte verification.
- **daymade-skill** v1.10.0: skill-creator now resolves coexistence with the official `skill-creator@claude-plugins-official` plugin — their skill descriptions are near-identical, so Claude otherwise picks between them at random (verified in a live coexistence session). On trigger, skill-creator runs a one-grep coexistence check; when the official plugin is present it offers (with user consent) `scripts/setup_supersede_hook.sh install`, which registers a self-checking `SessionStart` routing hook in `settings.json` (backed up, idempotent, reversible via `uninstall`) so the daymade edition wins deterministically in every future session. The hook is never registered statically with the suite: on machines without the official plugin the installer refuses to install anything, and the hook itself goes silent and safe if either plugin later disappears. Non-destructive throughout — the official plugin stays usable when asked for by name. The skill-creator description also gained an explicit supersedes clause as a first-trigger tiebreaker. The machinery is also generalized into a skill-creator capability: `scripts/generate_supersede_kit.py` stamps a parameterized supersede kit (conditional installer + self-checking routing hook, templates under `assets/supersede-kit/`) into any user skill that deliberately overlaps an installed plugin, guided by the new `references/skill-precedence-and-coexistence.md` (measured loading/selection-layer mechanics plus the escalation menu: rename → description tiebreaker → conditional hook → disable → user-level shadow) and a "Coexistence & Precedence" step in the creation flow; skill-creator's own scripts are regenerated from the same templates, so the dogfooded instance and the generator share a single source.
- **daymade-skill** v1.10.0 also adds a manifest-driven conversation-mining workflow and knowledge-skill grounding guide. Mining now applies `since`/`until` at message level, redacts before persistence, replaces local paths with opaque source IDs, rejects unsafe allowlist wildcards, keeps run manifests and `.enrich/` artifacts out of Git and distribution packages, and requires explicit manual promotion. Validator self-tests now cover hidden-parent paths and JSONL hash integrity; packaging always excludes root `tests/` and `.enrich/`; the supersede installer fails closed on invalid settings and removes only its own hook entry.
- **daymade-skill** v1.9.0: make `skill-reviewer` delegate YAML, frontmatter schema, and internal-path checks to the canonical `skill-creator` validator; replace substring-based bare-`except` detection with Python AST analysis; exempt explicit credential/path placeholders without suppressing real-looking findings; and reserve exit code 3 for invocation/runtime failures with structured JSON errors. Add focused regression coverage, correct the suite-local validator/security-scan commands, repair the reviewer documentation links, and replace stale standalone `skill-creator` install instructions with the suite install.
- **daymade-audio** v1.4.1, **daymade-claude-code** v1.8.6, **daymade-skill** v1.8.2, **feishu-doc-scraper** v1.3.1, **product-analysis** v1.0.2, **notify-wecom** v1.0.1, and **gemini-history-analyzer** v1.0.1: quote bracketed `argument-hint` values so strict YAML loaders parse them as strings; preserve the current URL-capable ASR hint while resolving PR #121 against latest main, and remove `notify-wecom`'s misleading bare cross-skill sender path so validation resolves only files in its own bundle.
- **llm-wiki-setup** v1.1.0: resolve wikilinks against root-level Markdown pages, trigger vault lint when those targets are deleted or renamed, and add a backup-preserving tooling refresh path for existing vaults.
- **daymade-audio** v1.4.0: `asr-transcribe-to-text` documents batch transcription of many short files — music-only/BGM-only clips can trigger a repetition-loop hallucination that stalls a whole batch, so drive batches one-file-per-process with a per-file timeout, retry stuck files with `--max-tokens 3000`, and classify no-speech clips by unique-word ratio; Step 3 now cross-references the hazard.
- **feishu-doc-scraper** v1.3.0: documents sheet cell-attachment extraction — recover fileTokens via the raw v2 values API (`+cells-get` flattens attachments to filenames), download through `medias/batch_get_tmp_download_url` with `file_tokens` as a JSON array (`drive +download` 403s on media resources), plus date-cell Excel-style serial numbers.
- **daymade-claude-code** v1.8.4: `claude-switch-models-setup` fixes — the `css` shell alias in `claude-profiles-help` points back at the shipped `stepfun` profile (a rename had left it targeting a nonexistent `css` profile); the cross-process sync lock moved out of `~/.claude/plugins/` so `shared_item_names()` can no longer symlink it into every profile as flickering dangling debris, with a scan guard against legacy lock residue.
- **daymade-claude-code** v1.8.5: `claude-switch-models-setup` references realigned with the code — the architecture doc now states the sync lock lives outside the plugins directory (it said "under the Claude plugins directory", stale after the v1.8.4 move), and the concurrent-launch verification examples loop over the shipped profile names (kimi/glm/deepseek/stepfun/anthropic) instead of a machine-specific list.

### Fixed
- **cloudflare-troubleshooting** v1.0.2 ([#89](https://github.com/daymade/claude-code-skills/issues/89)): `scripts/fix_ssl_mode.py` now runs in dry-run mode by default, prints the current SSL mode and target mode before writing, and requires `--apply` before changing live Cloudflare SSL settings or purging cache. Updated troubleshooting references so mutating examples include the explicit apply flag.
- **daymade-claude-code** v1.8.7: `claude-skills-troubleshooting` now determines marketplace-cache freshness only from the timezone-qualified `known_marketplaces.json` `lastUpdated` value, rejects missing, malformed, future, or structurally invalid metadata instead of falling back to unreliable directory mtimes, and returns a nonzero status for stale or invalid caches. Added regression coverage for timestamp parsing, threshold boundaries, malformed data, and diagnostic exit semantics.

## [1.82.0] - 2026-07-07

### Changed
- **daymade-claude-code** v1.8.1: hardened `claude-switch-models-setup` under real multi-profile tmux launch tests. The profile helper now creates the modern `.claude.json` state file, keeps zsh-sourced helper output clean, and the local-source/plugin sync scripts share a cross-process lock so simultaneous Kimi/GLM/DeepSeek/Step launches cannot race on cache symlink creation or `known_marketplaces.json` replacement.
- Documented the launch-path verification protocol and the boundary between successful skill/plugin loading and provider-side network/TLS failures.
- Ignored Claude Code `.in_use/` runtime marker directories, which can appear in source repos when plugin cache entries are symlinked back to local source.
- **daymade-claude-code** v1.8.2: `claude-profiles-init` now prunes stale profile symlinks whose targets under `~/.claude` disappeared, so optional runtime directories such as `image-cache/` do not leave every profile in a broken-link doctor state.
- **daymade-claude-code** v1.8.3: local source sync now prunes stale Codex/agents skill symlinks that point into the managed daymade source repos after a skill is removed or renamed in the marketplace manifest. Real skill directories are still never deleted.
- **competitors-analysis** v1.2.0: restructured SKILL.md around an Entry Router / Discovery Workflow / Durable Source Layout / Report Structure with explicit Evidence Rules and an Output Quality Bar; `update-competitors.sh` rewritten with `discover` / `clone-url` / `clone` / `pull` / `status` subcommands plus SSH-URL derivation helpers.
- **daymade-skill** v1.8.1: skill-creator methodology added benchmark-vs-grep, baseline-reveals-fact-errors, and counter-review sections (§5.3–5.6, §6.5, Case 8); skill-governance added Workflow E to audit and prune loose user-installed skills.
- **frontend-visual-qa** v1.2.0: added Map / GIS Workbench checks and a new data-viz tier & design-system token audit reference for reporting-grade data pages (dashboards, KPI boards) where chart tier and categorical colorblind-safety matter.
- **daymade-audio** v1.3.3: `asr-transcribe-to-text` gained a media-input resolver and a restructured Step 1–6 workflow; `transcript-fixer` added stage1 auto-finalize, learned-review, dictionary import/export, and a sqlite connection-pool fix.
- **tunnel-doctor** v1.7.0: TUN DIRECT split-brain diagnosis, plus a TUN measurement-contamination guide (raw probes lie under a global proxy).
- **debugging-network-issues** v1.4.0: certificate-verification triage (UNKNOWN_CERTIFICATE_VERIFICATION_ERROR, wrong-site certificate).
- Marketplace version: 1.81.0→1.82.0.

## [1.81.0] - 2026-07-07

### Changed
- **daymade-claude-code** v1.8.0: statusline-generator learned zero-fork git-branch rendering — the minimal layout now shows `[branch]` by reading `.git/HEAD` as a plain file (worktree/submodule `gitdir:` indirection and detached-HEAD short-sha included) instead of spawning `git`, so it works even without a git binary.
- statusline-generator SKILL.md: new authoring Rule 3 ("the statusline is a hot path") — budget subprocesses per refresh, never resolve packages (`bunx`/`npx` `@latest`) at refresh time, don't spawn `git` for the branch, treat dirty-state `git status` as a full-layout-only luxury. Distilled from a real battery-drain investigation where a package-runner statusline cost ~0.4s CPU per refresh vs ~0.01s for this script.
- statusline-generator: back-ported the cross-shell-safe `$HOME` → `~` shortening fix (case statement instead of `${var/#pattern/~}`, whose replacement-string `~` bash expands) that had drifted between the installed copy and the skill source.
- statusline-generator health_check.sh: new mock test verifies `[branch]` renders from a synthetic `.git/HEAD` with no git binary required.
- Marketplace version: 1.80.0→1.81.0.

## [1.80.0] - 2026-07-05

### Changed
- **competitors-analysis** v1.1.0: expands from single-repository code profiling into a durable competitor intelligence workflow covering discovery, clone/ingest, update, source-cited profiles, and landscape synthesis.
- Updated the competitor workspace convention to `$HOME/workspace/competitors/{product}/` with `COMPETITORS_BASE` override support.
- `competitors-analysis/scripts/update-competitors.sh` now supports `discover`, `clone-url`, `clone`, `pull`, and `status`, and can update an existing product competitor directory without requiring a prefilled repository map.
- README.md / README.zh-CN.md / CLAUDE.md: synced the competitors-analysis entry to the new discover/ingest/profile/landscape workflow.
- Marketplace version: 1.79.0→1.80.0.

## [1.79.0] - 2026-07-03

### Changed
- **daymade-claude-code** v1.7.0: multi-provider profile sync now mirrors enabled plugins from the default Claude profile, shares installed plugin state across profiles, and automatically keeps local skill source repos linked into Claude Code and Codex installs. Maintainer machines can install a macOS LaunchAgent to watch marketplace manifest changes.
- **daymade-skill** v1.8.0: adds `skill-governance` as a suite member for marketplace/cache drift checks, source-backed sync through official plugin commands, old cache cleanup, and local-source switching.
- **frontend-visual-qa** v1.1.0: browser-integrated output QA now treats export/download/share/print/PDF flows as first-class GUI journeys, requiring real Chrome/Computer Use evidence for downloads, share URLs, clipboard/new-tab behavior, and nonblank print/PDF previews.
- README.md / README.zh-CN.md / CLAUDE.md: synced the `skill-governance` listing to the marketplace manifest, updated version badges to 1.79.0, and removed the README skill-count badge derived value.
- Marketplace version: 1.78.0→1.79.0.

## [1.78.0] - 2026-06-29

### Added
- **gemini-history-analyzer** v1.0.0: Analyze Google Takeout exports of Gemini conversation history — extract and categorize transcripts and attachments, context-verified domain keyword search (finance/legal/etc.), meeting-transcript vs prompt-response detection, Chinese/Unicode filename handling via `unar` (the macOS `unzip` corrupts them), PII flagging, and optional distillation into project memory or a personal knowledge base. Top-level plugin: `gemini-history-analyzer@daymade-skills`.

### Changed
- Marketplace version: 1.77.0→1.78.0; plugin entries 54→55.

## [1.77.0] - 2026-06-29

### Added
- Four new skills landed: **claude-migrate-memory-to-doc** (migrate `.claude` memory into versioned, tool-agnostic docs), **design-style-picker** (batch-generate and compare visual design directions before committing), **local-codex** (delegate coding tasks to the local OpenAI Codex CLI via ChatGPT Pro OAuth), and **openclaw-model-switch** (switch an OpenClaw instance's default model with backup and validation).

### Security
- Removed hardcoded personal identifiers from the repo PII deny-list (`.gitleaks.toml`, `.githooks/pre-commit`) and ran a PII history-cleanup pass on the repository.

### Changed
- Marketplace version: 1.76.0→1.77.0.

## [1.76.0] - 2026-06-28

### Added
- **daymade-financial** suite v1.0.0: Financial data and investment-research suite bundling 5 skills under a shared namespace — `bigdata-skill` (Bigdata.com/RavenPack SDK + REST), `financial-data-collector` (US equity fundamentals via yfinance), `gangtise-copilot` (Gangtise OpenAPI suite installer), `ashare-news-fetcher` (A-share news/policy aggregation), and `pharma-daily-report` (A-share pharma sector daily report). Install once via `daymade-financial@daymade-skills` and invoke as `daymade-financial:<skill>`.

### Changed
- **Suite-only migration**: the 5 financial skills are now suite-only. Removed 5 standalone plugin entries from `marketplace.json`; they are now reachable only via the `daymade-financial` suite.
- Plugin entries: 56→52 (5 standalone removed, 1 suite added).
- Marketplace version: 1.75.0→1.76.0.
- README.md / README.zh-CN.md / CLAUDE.md: added suite install block, added suite-only markers to the 5 skill sections, removed standalone install commands, added Financial Data use case, updated documentation links.

### Migration
- Existing users of any of the 5 affected standalone plugins (`bigdata-skill@daymade-skills`, `financial-data-collector@daymade-skills`, `gangtise-copilot@daymade-skills`, `ashare-news-fetcher@daymade-skills`, `pharma-daily-report@daymade-skills`) should install the suite: `claude plugin install daymade-financial@daymade-skills`. Personal data and credentials are unaffected.

## [1.75.0] - 2026-06-28

### Added
- **pharma-daily-report** v1.0.0: A-share pharmaceutical sector daily report — Sina Finance real-time quotes, 7 sub-sector ranking, gainers/losers, fund-flow estimate, optional Feishu rich-text push; default 20-stock watchlist, customizable.

### Changed
- skills 76→77, plugin entries 55→56, marketplace 1.74.0→1.75.0.

## [1.74.0] - 2026-06-28

### Added
- **ashare-news-fetcher** v1.0.0: aggregate A-share news, policy, and sentiment from public Chinese sources (财联社/华尔街见闻/金十/新浪 7x24/东财快讯/regulators/东财股吧) into structured JSON or Markdown; per-stock or market-wide, no login.

### Changed
- skills 75→76, plugin entries 54→55, marketplace 1.73.0→1.74.0.

## [1.73.0] - 2026-06-28

### Added
- **wps-doc-scraper** v1.0.0: faithfully archive public WPS/KDocs/金山文档 links (incl. embedded ProcessOn mind maps) as raw source, SVG/PNG, and Markdown without login; data-API-first with browser-DOM fallback.

### Changed
- skills 74→75, plugin entries 53→54, marketplace 1.72.0→1.73.0.

## [1.72.0] - 2026-06-28

### Added
- **download-gemini-images** v1.0.0: download images from a Google Gemini conversation page via logged-in Chrome (lightbox-first, pageAssets fallback), rename in order, package into a verified ZIP.

### Changed
- skills 73→74, plugin entries 52→53, marketplace 1.71.0→1.72.0.

## [1.71.0] - 2026-06-28

### Added
- **openclaw** v1.0.0: manage OpenClaw (龙虾/lobster) instance configs — audit/diff/copy/add-model/list/switch, DeepSeek patches, config validation. Real private instance nicknames were sanitized to placeholders (甲虾/乙虾) before publishing.

### Changed
- skills 72→73, plugin entries 51→52, marketplace 1.70.0→1.71.0.

## [1.70.0] - 2026-06-28

### Added
- **frontend-visual-qa** v1.0.0: review rendered frontends/dashboards/HTML slides for visual defects lint/build miss (awkward line breaks, wrapped controls, overflow, double scrollbars, AI slop, Chrome DevTools viewport mistakes); history-derived checklist + Chrome-first pass + Playwright-core audit.

### Changed
- skills 71→72, plugin entries 50→51, marketplace 1.69.0→1.70.0.
- **transcript-fixer** → daymade-audio 1.3.0: uncertain extraction, tech presets, common-words safety table + tests.
- **feishu-doc-scraper** → 1.2.1: correct lark-cli 1.0.55 `cells-get` CSV behavior (returns JSON cell grid, not CSV) + pagination note.
- **skill-creator** (`package_skill`) → daymade-skill 1.3.0: exclude `.pytest_cache`/`.venv`/`.security-scan-passed`/`dist`, default artifact output to `<skill>/dist/`, +16 tests.
- **skill-creator** (PII SOP) → daymade-skill 1.4.0: `security_scan` "passed" now warns it is keyword-based only; `sanitization_checklist` adds the CJK project-nickname blind spot + an openclaw war-story; `new-skill-guide` makes the manual逐字 PII read-through a mandatory Step-1 gate and adds multi-agent concurrent-session diagnosis.

## [1.69.0] - 2026-06-27

### Added
- **codex-image-gallery** v1.0.0: new self-contained skill for browsing Codex-generated images in a local web gallery. Bundles `scripts/server.mjs` and `assets/index.html`; scans `~/.codex/generated_images` by default; supports `GALLERY_ROOT`, `PORT`, and `HOST`; serves a dynamic `/api/images` index and protected `/images/<relative-path>` image routes.

### Changed
- Updated marketplace skills count from 70 to 71.
- Updated marketplace plugin entry count from 49 to 50.
- Updated marketplace version from 1.68.0 to 1.69.0.
- Updated README.md / README.zh-CN.md badges and skill lists to include `codex-image-gallery`.
- Backfilled existing doc-list drift for `read-claude-web-conversation`, `setup-notifications-via-wecom`, `notify-wecom`, and `github-sensitive-data-cleanup` so the human-facing lists match `marketplace.json`.
- Updated CLAUDE.md repository overview count, marketplace plugin count, and Available Skills list.

## [1.67.0] - 2026-06-24

### Added
- **llm-eval-harness** v1.0.0: new skill — evaluate any LLM behind an OpenAI- or Anthropic-compatible endpoint across four dimensions instead of trusting a vendor's headline numbers:
  - **Speed** (`scripts/speed_probe.py`): TTFT + sustained decode tok/s, **thinking-aware** — captures `reasoning_content` separately so reasoning tokens don't inflate throughput (the trap that once read a ~750 tok/s model as 4700 tok/s).
  - **Concurrency / stability** (`scripts/concurrency_probe.py`): success rate, p50/p90 latency, and the level where it breaks; isolates from ambient proxy (`trust_env=False`) and disables keep-alive (`force_close`) so you measure the model, not the proxy.
  - **Anthropic protocol compliance** (`scripts/protocol_probe.py`): does `thinking: {type: enabled}` actually fire `thinking_delta` / `signature_delta` (N≥10)? Verdict is three-state (`fully-implemented` / `intermittent (k/N)` / `not-implemented`), never concluded from a single sample; forces `Connection: close` so a load balancer can't pin all samples to one replica.
  - **Quality / use-case regression** (`scripts/usecase_runner.py` + independent blind judges): collect then judge in isolation (3 judges/case, majority-pass, per-category precision) so the model never grades itself.
  - Keys are passed by **env-var name only** (`--key-env MY_KEY`) — never on the command line, never in a saved report. The use-case library lives **outside** the bundle (`~/.llm-eval/`) so it survives skill updates and never lands in a public repo. Bundles `assets/example_usecases.json`, two references (`evaluation_disciplines.md`, `quality_blind_judge.md`), and a recorded security scan.

### Changed
- Updated marketplace skills count from 65 to 66.
- Updated marketplace version from 1.66.0 to 1.67.0.
- Updated marketplace plugin entry count from 45 to 46 (single-skill plugin, `source` → `./llm-eval-harness`, no `skills` field).
- Updated README.md badges (skills count, version) and description; added llm-eval-harness install command, skill section #68, the "For LLM Evaluation & Model Comparison" use case (composes with promptfoo-evaluation), a documentation quick link, and a requirements entry.
- Updated README.zh-CN.md to match (same 7 locations, translated).
- Updated CLAUDE.md repository overview skill count (64 → 66, reconciled to the authoritative manifest), marketplace-config plugin count (45 → 46), and Available Skills list (added #66 llm-eval-harness).

## [Unreleased]

### Added
- **marketplace-health-check** v1.0.0: new skill — the 6-dimension repo health-check workflow distilled from a real audit session, fixed as a reusable skill. A parallel fan-out Dynamic Workflow runs six inspectors (code/script safety, documentation/SSOT consistency, security/PII, open-PR triage, open-issue triage, marketplace-manifest integrity); the skill then Counter-Reviews every high/critical finding (agent findings are hypotheses, verified before reporting) and reports by priority. Bundles the proven workflow script + a methodology reference (anti-target PII rule, working-copy-vs-history distinction, scan-marker necessary-not-sufficient, the broken-install-command bug class, promotion-decline default). Inline orchestrator — uses the Workflow tool, so it must not run forked.

### Changed
- **local-codex** extracted from `~/.kimi_openclaw/workspace/local-codex.skill` and promoted to a standalone top-level skill. Delegates coding tasks to the local OpenAI Codex CLI via ChatGPT Pro OAuth flat-rate subscription; example paths updated from `~/.agents/skills/local-codex/...` to repo-relative `scripts/codex_wrapper.py`.
- **openclaw-model-switch** extracted from `~/.agents/skills/openclaw-model-switch.skill` and promoted to a standalone top-level skill. Switches the default OpenClaw model by safely editing `openclaw.json` with backup, model validation, and optional gateway restart; example paths updated from `~/.agents/skills/openclaw-model-switch/...` to repo-relative `scripts/switch-model.py`.
- README.md, README.zh-CN.md, CLAUDE.md: added sections for `local-codex` (#78) and `openclaw-model-switch` (#79), renumbered subsequent skill sections, updated skill counts and descriptions.
- Plugin entries: 52→54 (2 new standalone skills added).
- Marketplace version: 1.76.0→1.77.0.

### Changed
- **debugging-network-issues** v1.3.0: Add client-side proxy / VPN / TUN misrouting coverage. New reference `references/case-proxy-tun-cname-override.md` documents a CNAME-based rule override that caused `ERR_CONNECTION_CLOSED` even though explicit PROXY rules were at the top of the config, plus the decisive experiments (hostname-vs-IP through the proxy, TUN-vs-physical-interface reachability) and the fix pattern (`[Host]` mapping + `use-local-host-item-for-proxy`). Adds cognitive Trap 11 "Assuming a top-of-list proxy rule beats CNAME matching" and Trap 12 "Proxy-node DNS = client DNS"; adds a triage entry and a client-side proxy/TUN checklist to SKILL.md. Marketplace description and keywords synced; README / README.zh-CN skill sections and documentation pointers updated.
- **Doc-governance hardening** (post-v1.65.0 health-check): `check_doc_skill_lists.py` now also asserts the README version badge equals `marketplace.json` metadata.version — that badge silently drifted twice (1.63→1.64, 1.64→1.65) when a metadata bump forgot it, so the drift guard enforces it instead of relying on manual discipline (`daymade-claude-code` suite v1.2.1). Slimmed `marketplace.json` metadata.description from a per-skill enumeration (which had silently fallen ~11 skills behind) to a category-level summary that points to the README for the authoritative breakdown. Removed a duplicate `## [1.56.0]` CHANGELOG header.

### Fixed
- **claude-code-history-files-finder** (`daymade-claude-code` suite v1.3.0 → v1.4.0): `analyze_sessions.py` only matched a project when given its exact absolute path — a `~` path, a relative path, or a bare project name silently returned "No sessions found", because the lookup did `project_path.replace("/", "-")` with no `expanduser`/`resolve` and no fallback. This is the trap that makes a real local history look like it was "written somewhere else" (e.g. assumed to be Claude Desktop): the encoded directory name is the *absolute* working-directory path (`/Users/<name>/Desktop/app` → `-Users-<name>-Desktop-app`), not the basename. Now expands `~`, resolves to an absolute path, then reverse-looks-up by basename (listing candidates instead of guessing when ambiguous). SKILL.md gains an explicit "reverse-look-up before concluding "no history"" gate and a note that Claude Desktop cowork sessions also land in `~/.claude/projects/`; `references/session_file_format.md` is corrected to the real 2.x line schema (top-level `type` + nested `message.role`, plus non-message event lines like `queue-operation` / `last-prompt`).
- **repomix-safe-mixer** v1.0.1: the "before" examples in SKILL.md + `references/common_secrets.md` used a real-looking Supabase project ref + JWT, flagged CRITICAL by the bundled scanner — which had never run on this skill (it shipped with no `.security-scan-passed` marker). Replaced with neutral placeholders. Also backfilled `.security-scan-passed` markers for 20 skills that shipped without a recorded scan (one of which, repomix-safe-mixer, is exactly why — it had a real leak no one had scanned for).
- **Sensitive-info sanitization** (full health-check findings): removed the owner's real private domains from shipped examples — `tunnel-doctor` v1.6.1 (`quick_diagnose.py` default `--host` + SKILL.md example) and `terraform-skill` v1.0.1 (Caddyfile / compose / SQL examples) — and a real personal handle used as a speaker-name example in `transcript-fixer` (`daymade-audio` suite v1.2.1); all replaced with `example.com` / neutral placeholders. These were pre-existing leaks predating the global PII-guard domain rules (which already cover them for future diffs). The repo-local `.gitleaks.toml` is deliberately NOT given the real private values — a public allowlist enumerating real assets would itself be a leak (anti-target principle).
- **Broken flagship install commands** ([#67](https://github.com/daymade/claude-code-skills/issues/67)): `claude plugin install skill-creator@daymade-skills` (plus `skill-reviewer` / `skills-search` / `doc-to-markdown`) failed because those are suite members, not standalone plugins. Corrected every occurrence across README.md, README.zh-CN.md, QUICKSTART.md, QUICKSTART.zh-CN.md to the suite name (`daymade-skill@daymade-skills` / `daymade-docs@daymade-skills`), invoked as `daymade-skill:skill-creator` etc.

## [1.64.0] - 2026-06-13

### Added
- **claude-usage-analyst** (`daymade-claude-code` v1.2.0): new skill — turns local `ccusage` data into an evidence-based, human-readable explanation of Claude Code / Claude Desktop token usage, cost, quota burn, model mix, and cache read/write pressure. Bundled `analyze_claude_usage.py` summarizes any date window/timezone; model-comparison mode weighs token volume against estimated cost (a model can be cheap per token but expensive overall); a 5-hour-block table addresses quota-exhaustion questions. Evidence discipline: numbers are grounded in `ccusage` output and scope is stated explicitly (local Claude Code logs, not a full Claude.ai chat bill). Registered into the `daymade-claude-code` suite (skills[] + suite 1.1.0 → 1.2.0); marketplace catalog 1.63.0 → 1.64.0.
- **skill-creator** (`daymade-skill` v1.2.0): five incident-distilled authoring rules, each placed at the workflow step where it fires:
  - *Step 4*: validate immediately after every SKILL.md edit (strict-YAML `quick_validate`, not packaging-time) + block-scalar `>-` convention for descriptions containing `: ` / ` #` — lenient/strict parser divergence and silent ` #` description truncation both shipped undetected before this.
  - *Step 5*: sanitization is scoped **by destination** — only the publicly-shipping skill bundle gets redacted; private-repo companion docs (incident reports, runbooks) keep audit-grade real values. Placeholders must not encode the real value they hide; bulk replaces need an explicit file whitelist scoped to the skill directory.
  - *Bundled Resources*: user-mutable data (correction dictionaries, learned preferences) lives under `~/.<skill-name>/` outside the bundle — installs are wiped on every update/suite-migration, a home-relative store survives untouched.
  - *Capture Intent*: mining past-session transcripts must be delegated to subagents with line-by-line truncated extraction — a full-context attempt died 17 tokens over the window limit and killed the session.
  - *Privacy & Paths*: cross-skill references — bare relative paths always mean "own bundle" (validators treat them so); name the owner skill in prose and invoke by namespaced `/suite:skill`. Marketplace-entry rename/relocation/removal flagged as a breaking change (dangling installs; mechanics live in marketplace-dev).
  - New "Phase 9 实战案例库" in `references/skill-development-methodology.md` preserving the four incident case files behind these rules; `references/schemas.md` gains a table of contents (8 schemas, >100 lines).
- **bilibili-source** v1.0.0: new skill — login-free fetch of comprehensive Bilibili (B站) video data in one `view/detail` call (title, UP follower count, tags, partition, per-part cids, live stats, and full danmaku text), accepting BVID / `av` number / `b23.tv` short link / full URL with the BVID-regex, multi-part-cid, and short-link edge cases all handled. Login-gated subtitles via `yt-dlp` (asks before reading browser cookies — no anonymous path exists, verified). Bundles a `bili-selftest.sh` health-check that detects API drift against a stable fixture, an API reference including the WBI request-signing algorithm, and 4 evals. All examples use synthetic/neutral data; metrics always carry a `fetched_at` timestamp (NO-FABRICATION discipline).
- **pdf-creator** (`daymade-docs` v1.1.0): new `warm-terra-menu` theme — a warm-terra variant hardened for 2-column long-text module menus (full-column wrap removes first-column overflow; a Menlo `unicode-range` keeps CJK inline-code from rendering blank in Preview/Adobe Reader).
- **tunnel-doctor** v1.6.0: Add "TUN Measurement Contamination" diagnostic section — while a proxy runs in TUN/global mode, common probes lie: `nc -z` shows a fabricated `0.00s` handshake (TUN completes it locally), `ping`/`remote_ip` are spoofed, and a foreign IP-geo lookup reports the proxy exit instead of the real home IP. Documents what to trust instead (`time_appconnect`/`time_starttransfer`, an in-region IP-geo source, config-decode + GUI cross-check) and adds matching trigger phrases.
- **debugging-network-issues** v1.2.0: New **Step 0.6 "upload-timeout vs processing-timeout"** recipe for large `POST` bodies behind a CDN — compare `bytes_read` to `Content-Length` in the edge/reverse-proxy log; a `status=0` / "client abort" is often the CDN edge timing out first, not a backend stall. Adds a second case study `references/case-cloudflare-524-upload.md` (a ~6 MB request body uploaded slower than Cloudflare's ~120 s origin read timeout → 524 while every backend was healthy) and cognitive Trap 10 "edge timeouts masquerading as upstream client aborts". Also adds cognitive Trap 12 "Reverse-path / directional asymmetry" — A→B healthy does not imply B→A healthy; an external probe to a node only proves that node's return direction, systematically missing the user's failing outbound direction (and the congested direction is often one an external probe structurally cannot reach). Sibling to Trap 5 (probe self-verification); synced into the SKILL.md trap list; fixed a stale "All nine traps" count in the summary.

### Fixed
- **skill-creator** (`daymade-skill` v1.2.0): `quick_validate` was failing on skill-creator itself — the marketplace-dev cross-reference was written as a bare `references/cache_and_source_patterns.md` path, which the validator (correctly, per the new cross-skill reference rule) treated as a missing local file; rewritten as a prose owner reference. Also fixed "has wrote" → "has written".
- **SKILL.md frontmatter strict-YAML validity (codex compatibility).** `description:` values are unquoted YAML plain scalars, so a `: ` or ` #` inside them breaks strict parsers — Claude Code's lenient frontmatter parser accepted them, codex did not.
  - **tunnel-doctor** v1.5.2: `: ` inside literal ssh output (`"debug2: resolving"`, `"debug1: connect"`) raised a `ScannerError`; wrapped the description in single quotes so the ssh strings stay verbatim.
  - **benchmark-due-diligence** v1.0.1: ` #` in `Product Hunt #1` silently truncated the parsed description; reordered to `#1 on Product Hunt` (no keyword loss).
  - **pdf-creator** (`daymade-docs` v1.1.0): `**Scope: markdown → PDF only.**` → `**Scope — markdown → PDF only.**`.

### Changed
- `daymade-skill` suite: 1.1.0 → 1.2.0 (skill-creator authoring rules above; also covers the previously-unversioned "Plugin boundaries are not this skill's domain" SSOT pointer added to skill-creator in the marketplace-dev consolidation).
- **macos-cleaner** v1.1.1 → v1.2.0 ([#84](https://github.com/daymade/claude-code-skills/pull/84), thanks @geniusart): progressive-disclosure refactor — moved Docker deep-analysis (Step 2A-2C), Mole multi-layer TUI exploration, and the object-level/report templates out of SKILL.md into `references/docker_analysis.md`, `references/mole_integration.md`, and `references/report_templates.md` (SKILL.md trimmed ~440 lines, zero content loss). Aligned the Example workflows with Core Principle 9 (provide commands for the user to run + `df -h` verification, never auto-execute `rm -rf`; point to `safe_delete.py` for interactive confirmation) and hardened `cleanup_report.py` exception handling (bare `except:` → specific exception types).

## [1.62.0] - 2026-06-07

### Added
- **terminal-screenshot** v1.0.0 (`daymade-claude-code` suite): render a terminal CLI's colored output to a PNG so Claude can *see* the real visual result (color contrast, alignment, background blocks) instead of raw ANSI codes — for verifying delta/bat/starship/lazygit color config. Capture-then-render discipline (never `freeze --execute` complex CLIs, which degrade in a child pty and drop background blocks); freeze-first renderer with a bundled stdlib ANSI→HTML + headless-Chrome fallback; per-CLI capture recipes. Bundled `render_ansi.sh`, `ansi2html.py`.
- **check_doc_skill_lists.py** (`marketplace-dev`): drift guard comparing the skill lists in CLAUDE.md / README.md / README.zh-CN.md against the authoritative marketplace.json (expanded), reporting MISSING and GHOST entries per doc and exiting non-zero on drift.

### Changed
- Marketplace version: 1.60.1 → 1.62.0; `daymade-claude-code` suite: 1.0.0 → 1.1.0 (adds terminal-screenshot).
- Synced documentation skill counts to the authoritative 61: README.md / README.zh-CN.md badges + descriptions, CLAUDE.md overview (54 → 61) and plugin-entry count (39 → 43).
- Backfilled the CLAUDE.md Available Skills list to 61 (added marketplace-dev, asr-transcribe-to-text, bigdata-skill, gangtise-copilot, llm-wiki-setup, benchmark-due-diligence, pdf-to-html, terminal-screenshot) and removed the ghost `wechat-article-scraper` entry (skill no longer on disk).
- Backfilled all missing README.md / README.zh-CN.md skill sections (asr-transcribe-to-text, marketplace-dev, skill-creator, feishu-doc-scraper, bigdata-skill, gangtise-copilot, llm-wiki-setup, benchmark-due-diligence, plus auto-repo-setup in zh-CN); all three doc lists (CLAUDE.md / README.md / README.zh-CN.md) now pass `check_doc_skill_lists.py`.

## [1.60.1] - 2026-06-05

### Fixed
- **macos-cleaner** v1.1.0 → v1.1.1: Hardened `safe_delete.py` with forced high-risk path blocking before confirmation and inside `delete_path()`, and updated `find_app_remnants.py` to match installed apps by Bundle Identifier as well as display name. Fixes [#70](https://github.com/daymade/claude-code-skills/issues/70).
- Marketplace version: 1.60.0 → 1.60.1

## [1.60.0] - 2026-05-31

### Added
- **auto-repo-setup** v1.0.0: Automated repository environment configuration, fault diagnosis, and repair for non-technical users. Reads ONBOARDING.md, audits environment gaps, installs missing dependencies, validates with smoke tests, and safely handles git operations with PII Guard and Push Safety. Includes SessionStart hook initialization, counter-review workflows, and git history sanitization.

## [1.56.0] - 2026-05-24

### Changed
- **All 4 suites are now suite-only.** Removed 17 standalone plugin entries from `marketplace.json` so suite member skills are reachable **only** via their suite. This unifies `daymade-audio`, `daymade-claude-code`, and `daymade-docs` with `daymade-skill` (which has been suite-only since inception). Each skill keeps its own SKILL.md, version, and bundled scripts unchanged on disk under `<suite>/<skill>/`.
  - `daymade-audio` (5 removed): `asr-transcribe-to-text`, `stepfun-asr`, `stepfun-tts`, `transcript-fixer`, `meeting-minutes-taker`
  - `daymade-claude-code` (7 removed): `claude-code-history-files-finder`, `continue-claude-work`, `claude-skills-troubleshooting`, `claude-md-progressive-disclosurer`, `statusline-generator`, `claude-export-txt-better`, `marketplace-dev`
  - `daymade-docs` (5 removed): `doc-to-markdown`, `mermaid-tools`, `pdf-creator`, `ppt-creator`, `docs-cleaner`
- Marketplace plugin entry count: 56 → 39 (17 standalone entries dropped; all 4 suite entries preserved).
- README.md / README.zh-CN.md: removed standalone `claude plugin install <skill>@daymade-skills` commands for the 17 affected skills (suite install commands at the top of "Quick Start" remain authoritative); rewrote three "Single-skill plugins remain available" / "instead of the repeating `<skill>:<skill>` form" sentences that became false after the unification; repaired broken doc links `./transcript-fixer/references/…` and `./daymade-docs/meeting-minutes-taker/SKILL.md` (leftovers from the 1.54.0 suite migration) to `./daymade-audio/…`; removed stale `/daymade-docs:meeting-minutes-taker` listing (meeting-minutes-taker moved to `daymade-audio` in 1.54.0 but the docs suite namespace listing was not updated).
- CLAUDE.md: plugin entry count 56 → 39; replaced "Suite-only members" partial list with an all-suite policy statement plus guidance to NOT create parallel standalone entries when adding new suite member skills.

### Migration
- **Existing users** of any of the 17 affected standalone plugins (`transcript-fixer@daymade-skills`, `statusline-generator@daymade-skills`, `pdf-creator@daymade-skills`, `ppt-creator@daymade-skills`, `doc-to-markdown@daymade-skills`, `mermaid-tools@daymade-skills`, `docs-cleaner@daymade-skills`, `claude-code-history-files-finder@daymade-skills`, `continue-claude-work@daymade-skills`, `claude-skills-troubleshooting@daymade-skills`, `claude-md-progressive-disclosurer@daymade-skills`, `claude-export-txt-better@daymade-skills`, `marketplace-dev@daymade-skills`, `asr-transcribe-to-text@daymade-skills`, `stepfun-asr@daymade-skills`, `stepfun-tts@daymade-skills`, `meeting-minutes-taker@daymade-skills`) should:
  1. Run `claude plugin marketplace update daymade-skills`
  2. Install the corresponding suite: `claude plugin install daymade-audio@daymade-skills`, `claude plugin install daymade-claude-code@daymade-skills`, or `claude plugin install daymade-docs@daymade-skills`
  3. Update any scripts / docs that invoke skills by namespace: `<skill>:<skill>` → `<suite>:<skill>` (e.g., `transcript-fixer:transcript-fixer` → `daymade-audio:transcript-fixer`)
- **Personal data is safe.** Skills that persist user data write to `$HOME` (e.g., `transcript-fixer` dictionary lives at `~/.transcript-fixer/corrections.db`); reinstalling or switching plugin namespaces does not touch user state.
- **`skill-creator` and other single-skill plugins are unaffected.** Only the 17 listed skills (members of the 3 newly-unified suites) need the migration.

## [1.54.0] - 2026-05-10

### Added
- **daymade-audio** suite v1.0.0: Audio processing suite covering the full speech pipeline — ASR transcription (Qwen3, StepFun), transcript error correction, structured meeting minutes generation, and TTS voice synthesis. Bundles 5 skills: `asr-transcribe-to-text`, `stepfun-asr`, `transcript-fixer`, `meeting-minutes-taker`, `stepfun-tts`.

### Changed
- Move `meeting-minutes-taker` from `daymade-docs` to `daymade-audio` — its core capability is semantic analysis of meeting transcripts, not document format processing.
- Move `asr-transcribe-to-text`, `stepfun-asr`, `stepfun-tts`, `transcript-fixer` from repo root into `daymade-audio/` suite directory.
- Marketplace plugin count: 55 → 56 (4 suites now: `daymade-audio`, `daymade-claude-code`, `daymade-docs`, `daymade-skill`).

## [1.53.2] - 2026-05-10

### Fixed
- Remove `skills: ["./"]` from 13 suite member plugin entries that triggered Claude Code 2.1.x path-escape validator error (`skills path "./" escapes plugin root`). Fixes [#64](https://github.com/daymade/claude-code-skills/issues/64).

### Changed
- Align all 52 single-skill plugins with official Anthropic marketplace pattern: `source` points directly to the skill directory (e.g., `"./tunnel-doctor"`), `skills` field omitted (auto-discovery). Previously used `source: "./"` with `skills: ["./skill-name"]`. The 3 suite plugins (`daymade-claude-code`, `daymade-docs`, `daymade-skill`) retain explicit `skills` arrays for multi-skill routing. Matches the pattern used by 167 of 168 plugins in `anthropics/claude-plugins-official`.

## [1.52.0] - 2026-04-30

### Added
- **stepfun-asr** v1.0.0: Transcribe audio with StepFun's `stepaudio-2.5-asr` — an SSE endpoint (NOT `/v1/audio/transcriptions`) with 32K context, ~85-101× RTF on long audio, and a single-call ceiling around 30 minutes (no client-side chunking). Split out from `stepfun-tts` so the ASR-specific traps (wrong-endpoint misleading error, Plan vs Normal key silent failure, SSE `error` event handling, repetition-hallucination edge case) live next to the `asr_transcribe.py` script that handles them. Bundled `scripts/asr_transcribe.py` (pure-stdlib CLI: env → `${CLAUDE_PLUGIN_DATA}/config.json` key resolution, base64 + nested JSON body, SSE parsing, censorship + transport error distinction). References cover the full SSE event contract, the legacy-vs-2.5 endpoint comparison table, and the "Plan key cannot call audio" gotcha. Suggests `transcript-fixer` / `meeting-minutes-taker` as natural downstream skills.

### Changed
- **stepfun-tts** v1.0.0 → v2.0.0 (BREAKING): ASR functionality removed and split into the new `stepfun-asr` skill. The remaining skill focuses purely on Contextual TTS (`stepaudio-2.5-tts`) — `instruction` natural-language tone + inline `()` parentheses + the `voice_label` migration story from `step-tts-2`. SKILL.md, `references/api_reference.md`, and `references/known_issues.md` all stripped of ASR sections; description and keywords updated to TTS-only. `scripts/asr_transcribe.py` removed from this skill (now lives in `stepfun-asr`).
- Marketplace skill count: 51 → 52 (effective listed count; suite member skills not double-counted)
- Marketplace plugin entry count: 55 → 56
- Marketplace version: 1.51.0 → 1.52.0
- README.md, README.zh-CN.md: badges, descriptions, skill section #50 (stepfun-tts retitled "TTS only" + description rewritten), new skill section #52 (stepfun-asr), Use Cases entries (split into two), Documentation Quick Links, Requirements (StepFun key applies to both)
- CLAUDE.md: overview count, marketplace plugin count, Available Skills list (entry #50 description rewritten + new entry #52)

### Note
This release also reconciles a versioning drift: commits `b2003d6` (statusline-generator → v1.1.0) and `ec7c313` (pdf-creator → v1.4.0) bumped their respective `plugins[].version` fields without bumping `metadata.version` and without adding CHANGELOG entries — a violation of the "any commit modifying a skill must bump that skill's version AND the marketplace metadata version" rule from `CLAUDE.md`. Those commits remain in history; v1.52.0 picks up the marketplace catalog version where it should have been after both, then adds the stepfun split on top. CHANGELOG entries for those individual skill bumps will not be retroactively backfilled — the version numbers in `marketplace.json` are authoritative and discoverable via `git log -- <skill-path>`.

## [1.51.0] - 2026-04-26

### Added
- **debugging-network-issues** v1.0.0: Evidence-driven, falsification-first methodology for network, streaming, and protocol-layer bugs where the obvious cause is probably wrong. Built from a real 5-hour production case (SSE RST_STREAM at exactly 130s, traced to a CGNAT idle timeout). Provides layered-isolation experiments (run the same logical request through 3+ paths differing by one hop), env-gated runtime instrumentation patterns, and a counter-review four-question filter to challenge single-cause assumptions before shipping a fix. Bundles probe scripts (`layered-isolation-probe.sh`, `mock-idle-upstream.py`) and reference docs covering counter-review, packet-capture recipes, instrumentation patterns, and cognitive traps. Triggers on `ECONNRESET`, HTTP/2 `RST_STREAM`, `INTERNAL_ERROR`, fixed-time SSE drops, CDN/proxy/CGNAT idle timeouts, and "works sometimes / fails after N seconds" patterns.
- **stepfun-tts** v1.0.0: Generate Chinese/Japanese speech with `stepaudio-2.5-tts` and transcribe long audio with `stepaudio-2.5-asr` (SSE endpoint, 32K context, ~100x RTF, up to 30-minute single call). Encapsulates the three non-obvious StepAudio 2.5 pitfalls that cost hours: `voice_label` removal (replaced by `instruction` + inline `()` prosody), `/v1/audio/asr/sse` endpoint mismatch (returns misleading `model not supported` error otherwise), and stricter censorship rules. Bundled scripts: `tts_generate.py` (with `--batch <jsonl>`), `asr_transcribe.py`, `ab_compare.sh`. API key resolution: `$STEPFUN_API_KEY` → `${CLAUDE_PLUGIN_DATA}/config.json` fallback. Reference docs cover migration from `step-tts-2`, the censorship rewrite list, and the verified-on-2026-04-23 known-issues registry.

### Changed
- Marketplace skill count: 49 → 51
- Marketplace plugin entry count: 53 → 55
- Marketplace version: 1.50.0 → 1.51.0
- README.md, README.zh-CN.md: badges, descriptions, skill sections (#49 + #50), Use Cases entries, Documentation Quick Links, Requirements
- CLAUDE.md: overview count, marketplace plugin count, Available Skills list

### Note
Plugin entries for these two skills were inadvertently committed in v1.50.0's path-rewrite operation (the entries existed as uncommitted draft modifications in `marketplace.json` and were carried along when that file was rewritten). v1.51.0 completes the registration that v1.50.0 left half-done by landing the skill directories themselves and synchronizing all documentation surfaces.

## [1.50.0] - 2026-04-26

### Changed
- **Suite directory flattening**: Moved both suite directories from `suites/<suite-name>/` to the repo root: `suites/daymade-docs/` → `daymade-docs/` and `suites/daymade-claude-code/` → `daymade-claude-code/`. The `suites/` intermediate directory has been removed. Plugin names, install commands, and skill invocations are unchanged for end users — only the on-disk layout and the `source` paths in `marketplace.json` (and doc links) were affected. `claude plugin update` will re-fetch from the new paths automatically.
- Updated all 15 `source` entries in `.claude-plugin/marketplace.json` from `./suites/<suite>/...` to `./<suite>/...`.
- Updated documentation references in `CLAUDE.md`, `README.md`, `README.zh-CN.md`, `references/new-skill-guide.md`, `daymade-claude-code/marketplace-dev/SKILL.md`, and `daymade-claude-code/marketplace-dev/references/cache_and_source_patterns.md`.
- Fixed pre-existing double-prefix typo (`suites/daymade-claude-code/suites/daymade-claude-code/...`) in two README locations during the path rewrite.

## [1.49.0] - 2026-04-19

### Added
- **slides-creator** v1.0.0: Narrative-first slide deck creation. Guides users through structured narrative design (ABCDEFG model), then delegates visual generation to baoyu-slide-deck. Focuses on what machines can't do — narrative co-design with humans. Six-phase workflow: source collection → narrative discussion → content structuring → prompt generation → image generation → post-processing with directory reorganization and speaker notes extraction. Triggers on "create slides", "make a presentation", "generate deck", "slide deck", "PPT", or when user needs to turn content into visual slides.

### Changed
- Updated marketplace skills count from 48 to 49
- Updated marketplace plugin entries from 52 to 53
- Updated marketplace version from 1.48.0 to 1.49.0
- Updated README.md badges, skill listings, use cases, and documentation quick links
- Updated README.zh-CN.md badges, skill listings, use cases, and documentation quick links
- Updated CLAUDE.md skill count (48 → 49), plugin entry count (52 → 53), and Available Skills list

## [1.48.0] - 2026-04-19

### Added
- **daymade-claude-code** suite v1.0.0: Claude Code operations suite bundling 7 power-user skills (`claude-code-history-files-finder`, `continue-claude-work`, `claude-skills-troubleshooting`, `claude-md-progressive-disclosurer`, `statusline-generator`, `claude-export-txt-better`, `marketplace-dev`) under one shared namespace. One command gets the full Claude Code toolkit and invocations render as `daymade-claude-code:<skill>` instead of the redundant `<skill>:<skill>` form.

### Changed
- **Canonical source migration**: The 7 Claude Code-related skills were physically moved from the repo root into `suites/daymade-claude-code/<skill>/`, mirroring the `daymade-docs` suite pattern. Both the suite and the 7 individual single-skill plugins now install from the same canonical location, keeping plugin caches narrow (only the suite's own files, not the whole repo). Transparent to existing users: plugin names and invocation remain identical; `claude plugin update` fetches from the new path automatically.
- Patch bumps for the 7 migrated skills to reflect the manifest/source change:
  - `claude-code-history-files-finder` 1.0.2 → 1.0.3
  - `continue-claude-work` 1.1.1 → 1.1.2
  - `claude-skills-troubleshooting` 1.0.0 → 1.0.1
  - `claude-md-progressive-disclosurer` 1.2.0 → 1.2.1
  - `statusline-generator` 1.0.0 → 1.0.1
  - `claude-export-txt-better` 1.0.0 → 1.0.1
  - `marketplace-dev` 1.2.0 → 1.2.1 (also simplified hook paths from `${CLAUDE_PLUGIN_ROOT}/marketplace-dev/hooks/...` to `${CLAUDE_PLUGIN_ROOT}/hooks/...` now that the cache root is the skill dir itself)
- Updated marketplace version from 1.47.0 to 1.48.0
- Updated marketplace plugin entries from 51 to 52
- README / README.zh-CN / CLAUDE.md / references/new-skill-guide.md: all doc links to these 7 skills now point to `suites/daymade-claude-code/<skill>/`

## [1.47.0] - 2026-04-12

### Added
- **wechat-article-scraper** v2.9.0: World-class WeChat article extraction with 6-level strategy routing (fast→adaptive→stable→reliable→zero_dep→jina_ai), OG metadata fallback, image-paragraph association, lazy loading handling, local image download, and Sogou search discovery. Supports Markdown/JSON/HTML/PDF export. Includes 15 unique/leading features surpassing all competitors.

### Changed
- Updated marketplace skills count from 47 to 48
- Updated marketplace version from 1.46.0 to 1.47.0

### Added
- **gangtise-copilot** v1.0.0: One-stop installer and companion for the full Gangtise (岗底斯投研) OpenAPI skill suite — 19 official skills covering data retrieval (OHLC 行情, 财务, 估值, 研报, 首席观点, 会议纪要, 调研纪要), research workflows (个股研究 L1-L4, 观点 PK 对抗性分析, 主题研究, 事件复盘, 公告摘要), and utility (股票池管理, 公开网页搜索). Distilled from a 5-round discovery session that reverse-engineered the complete Gangtise skill catalog — the Gangtise OBS bucket has LIST permission disabled, so the full 19-skill inventory is not discoverable from any public manifest. Ships with 4 preset install modes (full / workshop / minimal / custom), zero-config multi-agent distribution to Claude Code / OpenClaw / Codex via symlink from a single canonical install location, shared XDG credential file at `~/.config/gangtise/authorization.json` that rotates all 19 skills in one edit, and a read-only diagnostic script with scoped liveness checks (`auth` scope + `rag` scope). Ships: `scripts/install_gangtise.sh` (408 lines), `scripts/configure_auth.sh` (310 lines), `scripts/diagnose.sh` (320 lines), and 5 reference docs covering installation flow, credentials setup, the complete 19-skill registry with per-script capability matrix, known ecosystem traps (parallel product lines, bundle-only hidden skills, double-Bearer token bug, admin endpoint 1009 errors), and workshop best practices. Target use case: the 2026 Q2 investor Workshop series where students need to install a large skill suite quickly without reverse-engineering the catalog themselves.

### Changed
- **Renamed**: `markdown-tools` → `doc-to-markdown` — clearer name for DOCX/PDF/PPTX → Markdown conversion
- **doc-to-markdown**: Added 8 DOCX post-processing fixes (grid tables, simple tables, CJK bold spacing, JSON pretty-print, image path flattening, pandoc attribute cleanup, code block detection, bracket fixes)
- **doc-to-markdown**: Added 31 unit tests (`test_convert.py`)
- **doc-to-markdown**: Added 5-tool benchmark report (`references/benchmark-2026-03-22.md`)
- **marketplace-dev** v1.0.0 → v1.1.0: Added evidence intake from Claude Code history, plugin boundary decision guidance, source/cache patterns for single-skill and suite plugins, source+skills resolution validation, and cache footprint testing based on real marketplace debugging sessions.
- **marketplace-dev** v1.1.0 → v1.2.0: Refined against Anthropic's official skill-authoring best practices. Extracted the inline Node.js resolution check and diff pipeline into `scripts/check_marketplace.sh` — a one-shot validator that runs JSON syntax → `claude plugin validate` → source+skills resolution → reverse sync (disk SKILL.md → manifest) in a single command. Moved the two PostToolUse hook scripts from `scripts/` to `hooks/` for semantic clarity (scripts execute during skill workflow, hooks guard the editor) and updated the plugin manifest's hook paths accordingly. Added tables of contents to `anti_patterns.md` and `cache_and_source_patterns.md` (both >100 lines, per best practices). Corrected Phase 0 subagent history-mining paths to `<session-id>/subagents/agent-*.jsonl`. Documented the auto-activated hook behaviour in a new "Bundled hooks" section.

## [1.46.0] - 2026-04-11

### Added
- **claude-export-txt-better** v1.0.0: Fixes broken line wrapping in Claude Code exported `.txt` conversation files. Reconstructs tables, paragraphs, paths, and tool calls that were hard-wrapped at fixed column widths. Ships with an automated validation suite of 53 generic, file-agnostic checks. Triggers on export files with broken formatting or when the user mentions "fix export" / "fix conversation" / references a `YYYY-MM-DD-HHMMSS-*.txt` file. Bundled: `scripts/fix-claude-export.py`, `scripts/validate-claude-export-fix.py`, `evals/`.
- **douban-skill** v1.0.0: Exports and syncs Douban (豆瓣) book / movie / music / game collections to local CSV files via the reverse-engineered Frodo API. Supports full export and RSS incremental sync. No login, no cookies, no browser. Pre-flight user-ID validation and CSV output with UTF-8 BOM (Excel-compatible). Ships with a complete troubleshooting log of 7 tested scraping approaches and why each failed. Bundled: `scripts/douban-frodo-export.py`, `scripts/douban-rss-sync.py`, `references/troubleshooting.md`, `.gitleaks.toml` (allowlisting the public APK credentials).
- **terraform-skill** v1.0.0: Operational traps for Terraform provisioners, multi-environment isolation, and zero-to-deployment reliability. Every failure pattern documented caused a real incident. Covers provisioner timing races, SSH connection conflicts, DNS record duplication, volume permissions, database bootstrap gaps, snapshot cross-contamination, Cloudflare credential format errors, hardcoded domains in Caddyfiles/compose, and init-data-only-on-first-boot pitfalls. Organised as *exact error → root cause → copy-paste fix*. Bundled: `references/` with detailed remediation patterns.

### Changed
- Updated marketplace skills count from 44 to 47
- Updated marketplace version from 1.45.1 to 1.46.0
- Updated marketplace plugin entries from 47 to 50
- Updated README.md badges and skill listings (English and Chinese)
- Updated CLAUDE.md skill count (44 → 47) and plugin entry count (47 → 50)

## [1.45.1] - 2026-04-11

### Fixed
- **daymade-docs** v1.0.0 → v1.0.1: Narrowed the suite plugin source to `suites/daymade-docs/` so the installed cache contains only the documentation skills in the suite instead of a full repository snapshot.
- Moved the daymade-docs member skills under `suites/daymade-docs/` as their canonical source and repointed the corresponding single-skill plugin entries to those same directories.
- **doc-to-markdown** v2.1.0 → v2.1.1, **mermaid-tools** v1.0.1 → v1.0.2, **ppt-creator** v1.0.0 → v1.0.1, **pdf-creator** v1.3.1 → v1.3.2, **docs-cleaner** v1.0.0 → v1.0.1, and **meeting-minutes-taker** v1.1.0 → v1.1.1 now install from their suite canonical source paths.

### Changed
- Updated marketplace version from 1.45.0 to 1.45.1

## [1.45.0] - 2026-04-11

### Added
- **daymade-docs** v1.0.0: Documentation suite plugin that exposes `doc-to-markdown`, `mermaid-tools`, `pdf-creator`, `ppt-creator`, `docs-cleaner`, and `meeting-minutes-taker` under one namespace. This keeps the existing single-skill plugins available while providing `/daymade-docs:<skill-name>` slash commands for users who want a combined documentation workflow install.

### Changed
- Updated marketplace version from 1.44.0 to 1.45.0
- Updated README.md, README.zh-CN.md, and CLAUDE.md to document suite plugin architecture while preserving the existing single-skill plugin model.

## [1.44.0] - 2026-04-11

### Added
- **skill-creator** v1.7.1 → v1.7.2: Completeness pass for the `workflows/wrapper-skill/` methodology within its scope (zip-archive skill packages distributed via `npx skills add`). A fifth adversarial agent review audited the wrapper-skill workflow docs against the canonical `ima-copilot` implementation and surfaced 13 on-scope lessons that were implicit in the reference code but not elevated to named patterns in the workflow. This release lands all 13.
  - `patterns.md` install template: replaced the `<download and extract>` placeholder with a concrete defensive block covering `curl --fail` with HTTP-code branching, `wc -c` download-size sanity check rejecting suspiciously small archives before extraction, Node.js ≥18 numeric check (separate from `command -v node`), and a documented zero-agents-detected fallback policy (abort vs silent-skip vs default-to-claude-code, with the session's chosen answer named). Every defensive pattern has an accompanying "Lessons baked into this template" bullet explaining *why* it's there.
  - `patterns.md` known_issues template: added `**Why upstream probably hasn't fixed it**` as a required field (the field that keeps repair blocks load-bearing across upstream upgrades), added `Strategy skip` as a first-class documented third option (users on tolerant platforms may legitimately not want the repair and naming the skip path explicit prevents the "did I forget?" failure mode), and added detailed notes on the `[ -f ... ] && \` guard rationale, `sed -i.bak ... && command rm -f *.bak` BSD/GNU portability dance, and backup directory naming convention.
  - `patterns.md` diagnose template: added a new "Detection function return-code contract" subsection spelling out the required return codes for every post-repair state (untouched-good, untouched-broken, not-present, each Strategy-applied state, and the dual-state conflicted code). The dual-state code is the single hardest lesson from the ima-copilot session — a detection function that doesn't recognize it silently passes conflicted installs as healthy.
  - `patterns.md` diagnose template: added variadic `find_install` rationale explaining that agents whose home-directory layout has not stabilized (like OpenClaw) should be probed against an ordered list of candidate paths, and that designing the helper as variadic from day one avoids a painful refactor when a second candidate path becomes necessary.
  - `patterns.md` SKILL.md template: added explicit checklist for the description field (literal error strings from the session, tool name in every language the session used, self-disambiguation clause naming the upstream package to prevent wrapper-vs-upstream trigger fighting, symptoms that triggered the original session), plus a reference to the enforced 1024-character cap in `quick_validate.py:184`. Added "when in doubt → diagnose" as a recommended routing table default since diagnose is the only read-only entry point.
  - `patterns.md` credentials section: added explicit guidance that liveness checks must match on **response-body shape**, not just HTTP status. Many APIs return 200 OK with an error JSON body, and a naive `curl --fail` check will pass a credential that fails the first real operation.
  - `workflow.md` Step 5: expanded the install-script bullet list with prerequisite-check discipline (curl/unzip/npx loop plus separate Node.js ≥18 parse), download integrity defense in depth (HTTP code branching + size sanity), and the zero-agents fallback policy.
  - `workflow.md` Step 6: expanded the known_issues schema to include the `Why upstream probably hasn't fixed it` field and the `Strategy skip` branch, and documented the `sed -i.bak` cross-BSD/GNU portability rule alongside the existing `command cp/mv` guidance.
  - `workflow.md` Step 7: replaced the "returns OK / TRIGGERED / N/A / post-fix-state" shorthand with an explicit enumeration of the return-code contract, and added the variadic `find_install` guidance for agents with unstabilized layouts.

### Changed
- Updated marketplace version from 1.43.0 to 1.44.0

## [1.43.0] - 2026-04-11

### Fixed
- **ima-copilot** v1.0.0 → v1.0.1: Contract compliance and dogfood-driven fixes
  - `SKILL.md`, `references/known_issues.md`, `references/installation_flow.md`: removed hardcoded references to upstream version `1.1.2`. Install script keeps the version as an overridable default which is explicitly allowed by the architecture contract. Fixes a principle 6 (independent evolution) violation that would have forced a skill version bump on every upstream release.
  - `references/known_issues.md`: added `command` prefix to the `sed -i.bak` and `rm -f` commands in Strategy A repair block and to the `rm -f` command in Strategy A rollback, matching the contract's alias-safe requirement. Previously, a user shell with `alias rm='rm -i'` or `alias sed='sed -i'` would hang the repair on an interactive prompt.
  - `scripts/install_ima_skill.sh`: added a Node.js ≥18 preflight check. The `npx skills add` distribution path needs a modern Node runtime and the failure message on old Node is opaque.
  - `scripts/diagnose.sh`: `check_submodule` now recognizes and explicitly warns on the dual-state where both `SKILL.md` and `MODULE.md` exist simultaneously (can happen when a user switched repair strategies mid-session or restored a partial backup). Previously this reported clean while the install was in a conflicted state.
  - `scripts/search_fanout.py`: `rank_groups` now sorts tied hit counts by KB name for deterministic byte-identical output. Previously the tie-break depended on `concurrent.futures.ThreadPoolExecutor.map` completion order, which varied with network timing.
- **skill-creator** v1.7.0 → v1.7.1: Wrapper-skill workflow hardening from counter-review findings
  - `workflows/wrapper-skill/workflow.md` Step 2: added a "How to access the conversation" subsection with concrete guidance for three cases (same session / follow-up session / neither available) and an explicit "do not fabricate content" rule for the last case. Fresh agents were previously left to guess.
  - `workflows/wrapper-skill/workflow.md` Step 1: added an "AskUserQuestion fallback" subsection explaining that the consent requirement is the explicit user choice, not the specific tool name, and showing a plain-text fallback pattern for harnesses without `AskUserQuestion`.
  - `workflows/wrapper-skill/patterns.md`: added a new "Runtime-logic patterns shared across wrappers" section with three generalizable insights distilled from ima-copilot's `search_fanout.py` — **capability partitioning** (enumerate vs operate permission asymmetry with four-way result bucketing), **undocumented limit detection** (silent truncation heuristics for APIs that cap results without emitting pagination tokens), and **scoped liveness checks** (probe the lowest-privilege operation the skill actually performs, not the easiest API call). Each pattern includes example code, real-world examples across multiple APIs (GitHub, Slack, Notion, Google Drive), and a cross-reference to the ima-copilot implementation.
  - `workflows/wrapper-skill/verification_protocol.md`: restructured into Track 1 (session cross-reference for literal transcriptions) and Track 2 (smoke test / unit test for runtime logic). The previous "verification is not dogfood" dogma was too strict — it correctly applied to Track 1 files but wrongly exempted Track 2 runtime code from end-to-end testing. Track 2 files like `search_fanout.py` now have an explicit mandatory-smoke-test rule.

### Changed
- Updated marketplace version from 1.42.0 to 1.43.0

## [1.42.0] - 2026-04-11

### Added
- **skill-creator** v1.6.0 → v1.7.0: New `workflows/wrapper-skill/` specialized workflow for retrospectively distilling an install-and-debug session into a reusable companion skill for a third-party CLI tool
  - `workflows/wrapper-skill/workflow.md` — the retrospective distillation workflow with Step 2 conversation mining at its core (install flow, credential setup, bugs encountered and resolved, design decisions made, noise to discard)
  - `workflows/wrapper-skill/architecture_contract.md` — seven non-negotiable principles that every generated wrapper skill must follow (never vendor upstream, runtime repair over ship-time patches, explicit user consent for any upstream file modification, idempotent/reversible/alias-safe repair commands, teaching agents over humans, independent evolution from upstream, private preferences stay private)
  - `workflows/wrapper-skill/patterns.md` — copy-pasteable templates for SKILL.md, install script, diagnose script, known_issues registry, and credential setup, each annotated with the lessons baked in and cross-referenced to the canonical ima-copilot implementation
  - `workflows/wrapper-skill/verification_protocol.md` — post-generation verification focused on cross-referencing generated artifacts against the source conversation rather than re-running the full install (the install already ran in the source session)
  - `workflows/wrapper-skill/scripts/init_wrapper_skill.py` — bootstrap scaffold that creates the wrapper skill directory layout with placeholder markers pointing back at specific steps in the workflow
  - `SKILL.md` root entry now includes a "Specialized Workflow: Wrapper Skills for Third-Party CLI Tools" routing section between Capture Intent and Prior Art Research that redirects agents to the wrapper workflow when the signals apply
  - Canonical reference implementation: [`ima-copilot`](./ima-copilot) — the Tencent IMA wrapper that was the first product of this methodology, distilled during a real session whose lessons (shell alias bypass, root SKILL.md detection, realpath-based symlink dedup, idempotent reversible repairs) were captured in the patterns and propagated into this workflow

### Changed
- Updated marketplace version from 1.41.0 to 1.42.0

## [1.41.0] - 2026-04-11

### Added
- **New Skill**: ima-copilot v1.0.0 — One-stop companion and installer for the official Tencent IMA skill (ima.qq.com), with wrapper-layer architecture that never vendors upstream files
  - Zero-config installation to Claude Code, Codex, and OpenClaw via `npx skills add` ([vercel-labs/skills](https://github.com/vercel-labs/skills)) with auto-detection of installed agents and default symlink mode, so that a repair or upgrade applied once propagates automatically to every agent that shares the canonical install
  - XDG-style credential management at `~/.config/ima/{client_id, api_key}` with env-var fallback (`IMA_OPENAPI_CLIENTID` / `IMA_OPENAPI_APIKEY`)
  - Bundled `scripts/diagnose.sh` for read-only health check covering install presence, credential liveness, and known upstream issues with structured `✅/⚠️/❌` report
  - Bundled `scripts/install_ima_skill.sh` with version override via `--version` flag or `IMA_VERSION` env var
  - Bundled `scripts/search_fanout.py` for client-side cross-knowledge-base search with priority-based KB boosting, skip-list filtering, 100-result silent-truncation detection, and permission-denied KB partitioning (typical for subscribed KBs)
  - Detects and repairs ISSUE-001 (submodule SKILL.md files missing YAML frontmatter in upstream v1.1.2) with two user-selectable strategies: Strategy A (rename to `MODULE.md` and patch root references — respects upstream design intent) or Strategy B (prepend minimal frontmatter — smallest diff)
  - All repair commands are idempotent, reversible (with automatic timestamped backups to `/tmp/ima-copilot-backups/`), and use `command cp`/`command mv` to bypass interactive shell aliases
  - Personalization via `~/.config/ima/copilot.json` with `priority_kbs` and `skip_kbs` lists — template at `config-template/copilot.json.example` uses illustrative-only values so the skill ships with zero real KB names
  - Comprehensive reference documentation in `references/` covering installation flow, API key setup, known issues (source of truth for repairs), and search best practices
  - Never vendors, forks, or mirrors upstream files — every repair is a runtime instruction executed with explicit user consent

### Changed
- Updated marketplace skills/plugins count from 43 to 44
- Updated marketplace version from 1.40.1 to 1.41.0

## [1.39.0] - 2026-03-18

### Added
- **New Skill**: scrapling-skill v1.0.0 - Reliable Scrapling CLI installation, troubleshooting, and extraction workflows for HTML, Markdown, and text output
  - Bundled `diagnose_scrapling.py` script to verify CLI health, detect missing extras, inspect Playwright browser runtime, and run real smoke tests
  - Static-first workflow for choosing between `extract get`, `extract fetch`, and `stealthy-fetch`
  - Verified WeChat public article extraction pattern using `#js_content`
  - Verified recovery path for local TLS trust-store failures via `--no-verify`
  - Bundled troubleshooting reference covering extras, browser runtime, and output validation

### Changed
- **skill-creator** v1.5.0 → v1.5.1: Fixed `scripts/package_skill.py` so it works when invoked directly from the repository root instead of only via `python -m`
- **continue-claude-work** v1.1.0 → v1.1.1: Replaced newer Python-only type syntax in `extract_resume_context.py` so the script runs under the local `python3` environment
- Updated marketplace skills/plugins count from 42 to 43
- Updated marketplace version from 1.38.0 to 1.39.0
- Updated marketplace metadata description to include Scrapling CLI extraction workflows
- Updated README.md and README.zh-CN.md badges, installation commands, skill listings, use cases, quick links, and requirements
- Updated CLAUDE.md counts, version reference, and Available Skills list (added #43)

## [1.38.0] - 2026-03-07

### Added
- **New Skill**: continue-claude-work v1.1.0 - Recover local `.claude` session context and continue interrupted work without `claude --resume`
  - Bundled Python script (`extract_resume_context.py`) for one-call context extraction
  - Compact-boundary-aware extraction using `isCompactSummary` flag (highest-signal context from session compaction summaries)
  - Subagent workflow recovery — parses `subagents/` directory to report completed vs interrupted agents with last outputs
  - Session end reason detection — classifies clean exit, interrupted (ctrl-c), error cascade, or abandoned
  - Size-adaptive reading strategy based on file size and compaction count
  - Noise filtering — skips progress/queue-operation/api_error (37-53% of session lines)
  - Self-session exclusion, stale index fallback, ghost session warnings
  - MEMORY.md and session-memory integration, git workspace state fusion

### Changed
- **skill-creator** v1.4.1 → v1.5.0: SKILL.md rewrite, added eval benchmarking system (run_eval, run_loop, aggregate_benchmark), agents (analyzer, comparator, grader), eval-viewer, and improve_description script
- **transcript-fixer** v1.1.0 → v1.2.0: `--domain` defaults to all domains, added `get_domain_stats()`, cross-domain listing, and zero-match hints
- **tunnel-doctor** v1.3.0 → v1.4.0: Added Step 2C-1 for local vanity domain proxy interception, bundled `quick_diagnose.py` automated diagnostic script
- **pdf-creator** v1.0.0 → v1.1.0: Replaced Python `markdown` library with pandoc for MD→HTML conversion, removed `_ensure_list_spacing` workaround
- **github-contributor** v1.0.2 → v1.0.3: Fixed gh CLI field name (`stargazersCount` → `stargazerCount`), added Prerequisites section
- Updated marketplace skills/plugins count from 41 to 42
- Updated marketplace version from 1.37.0 to 1.38.0
- Updated README.md and README.zh-CN.md badges, installation commands, skill listings, use cases, quick links, and requirements
- Updated CLAUDE.md counts, version reference, and Available Skills list (added #42)

## [1.37.0] - 2026-03-02

### Added
- **New Skill**: excel-automation - Create formatted Excel files, parse complex xlsm models, and control Excel on macOS
  - Bundled scripts for workbook generation and complex XML/ZIP parsing
  - Bundled reference: formatting-reference.md for styles, number formats, and layout patterns
  - AppleScript control patterns with timeout-safe execution guidance
- **New Skill**: capture-screen - Programmatic macOS screenshot capture workflows
  - Bundled Swift script for CGWindowID discovery
  - AppleScript + screencapture multi-shot workflow patterns
  - Clear anti-pattern guidance for unreliable window ID methods
- Added missing `promptfoo-evaluation/scripts/metrics.py` referenced by skill examples

### Changed
- Updated marketplace skills/plugins count from 39 to 41
- Updated marketplace version from 1.36.0 to 1.37.0
- Bumped `promptfoo-evaluation` plugin version from 1.0.0 to 1.1.0 (skill content update + missing script fix)
- Updated README.md and README.zh-CN.md badges, installation commands, skill listings, use cases, quick links, and requirements
- Updated CLAUDE.md counts, version reference, and Available Skills list (added #40 and #41)

## [1.36.0] - 2026-03-02

### Added
- **New Skill**: financial-data-collector - Collect real financial data for US public companies via yfinance
  - Structured JSON output with market data, income statement, cash flow, balance sheet, WACC inputs, analyst estimates
  - Validation script with 9 checks (field completeness, cross-field consistency, sign conventions, NaN detection)
  - Reference docs: output-schema.md, yfinance-pitfalls.md (NaN years, field aliases, FCF definition mismatch)
  - NO FALLBACK principle: null for missing data, never default values

### Changed
- Updated marketplace skills count from 38 to 39
- Updated marketplace version from 1.35.0 to 1.36.0
- Updated README.md and README.zh-CN.md badges (skills count, version)
- Updated CLAUDE.md skills count and list

## [1.34.1] - 2026-02-23

### Changed
- Bumped marketplace metadata version from 1.34.0 to 1.34.1 in `.claude-plugin/marketplace.json`
- Added product-analysis entries to `README.md` and `README.zh-CN.md` and aligned skills count / version badges to 38 / 1.34.1
- Added product-analysis quick links in both READMEs and added use-case section in both READMEs
- Added **product-analysis** to `CLAUDE.md` and updated CLAUDE skill counts / version references to 38 and v1.34.1
- Bumped `skills-search` plugin version in `marketplace.json` from 1.0.0 to 1.1.0
- Bumped updated skill versions in `marketplace.json` after documentation updates:
  - `skill-creator`: 1.4.0 -> 1.4.1
  - `iOS-APP-developer`: 1.1.0 -> 1.1.1
  - `macos-cleaner`: 1.1.0 -> 1.1.1
  - `competitors-analysis`: 1.0.0 -> 1.0.1
  - `tunnel-doctor`: 1.2.0 -> 1.2.1
  - `product-analysis`: 1.0.0 -> 1.0.1

## [1.33.1] - 2026-02-17

### Changed
- **tunnel-doctor** v1.1.0 → v1.2.0: Add Layer 4 SSH ProxyCommand double tunnel diagnostics
  - New conflict layer: SSH ProxyCommand double tunneling causing intermittent git push/pull failures
  - New diagnostic step 2F: detect and fix redundant HTTP CONNECT tunnel when Shadowrocket TUN is active
  - Structural improvements per skill best practices:
    - Eliminate content duplication between SKILL.md and reference (73 → 27 lines)
    - Rename `proxy_fixes.md` → `proxy_conflict_reference.md` for clarity
    - Trim SKILL.md to 487 lines (under 500 limit)
    - Fix "apply all four" listing 5 items (separate anti-pattern warning)
    - Clarify Layer 4's relationship to Tailscale theme

## [1.33.0] - 2026-02-16

### Changed
- **tunnel-doctor** v1.0.0 → v1.1.0: Added remote development SOP with SSH tunnel and Makefile patterns
  - New SOP section: proxy-safe Makefile pattern (`--noproxy localhost` for all health checks)
  - New SOP section: SSH tunnel Makefile targets (`tunnel`/`tunnel-bg` with autossh)
  - New SOP section: multi-port tunnel configuration
  - New SOP section: SSH non-login shell setup (deduped, references proxy_fixes.md)
  - New SOP section: end-to-end workflow (first-time setup + daily workflow)
  - New SOP section: pre-flight checklist (10 verification items)
  - New diagnostic step 2D: auth redirect fix via SSH local port forwarding
  - New diagnostic step 2E: localhost proxy interception in Makefiles/scripts
  - Fixed step ordering: 2A→2B→2C→2D→2E (was 2A→2C→2D→2E→2B)
  - Fixed description to third-person voice per skill best practices
  - Replaced hardcoded IP with `<tailscale-ip>` placeholder (5 occurrences)
  - Added SSH non-login shell pitfall to references/proxy_fixes.md
  - Added localhost proxy interception section to references/proxy_fixes.md
  - Strengthened `--data-binary` vs `-d` warning in references/proxy_fixes.md
  - New keywords: ssh-tunnel, autossh, makefile, remote-development
- Updated marketplace version from 1.32.1 to 1.33.0

## [1.32.0] - 2026-02-09

### Added
- **New Skill**: windows-remote-desktop-connection-doctor - Diagnose AVD/W365 connection quality issues
  - 5-step diagnostic workflow for transport protocol analysis
  - UDP Shortpath vs WebSocket detection and root cause identification
  - VPN/proxy interference detection (ShadowRocket, Clash, Tailscale)
  - Windows App log parsing for STUN/TURN/ICE negotiation failures
  - ISP UDP restriction testing and Chinese ISP-specific guidance
  - Bundled references: windows_app_log_analysis.md, avd_transport_protocols.md

### Changed
- Updated marketplace skills count from 36 to 37
- Updated marketplace version from 1.31.0 to 1.32.0
- Updated README.md badges (skills count, version)
- Updated README.md to include windows-remote-desktop-connection-doctor in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include windows-remote-desktop-connection-doctor in skills listing
- Updated CLAUDE.md skills count from 36 to 37

## [1.31.0] - 2026-02-07

### Added
- **New Skill**: tunnel-doctor - Diagnose and fix Tailscale + proxy/VPN route conflicts
  - 6-step diagnostic workflow for route conflict detection and resolution
  - Shadowrocket, Clash, Surge proxy tool fix guides
  - Tailscale SSH ACL configuration (check vs accept)
  - WSL snap vs apt Tailscale installation guidance
  - Bundled references: proxy_fixes.md with per-tool instructions
  - Shadowrocket config API documentation

### Changed
- Updated marketplace skills count from 35 to 36
- Updated marketplace version from 1.30.0 to 1.31.0
- Updated README.md badges (skills count, version)
- Updated README.md to include tunnel-doctor in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include tunnel-doctor in skills listing
- Updated CLAUDE.md skills count from 35 to 36

## [1.30.0] - 2026-01-29

### Added
- **New Skill**: competitors-analysis - Evidence-based competitor tracking and analysis
  - Pre-analysis checklist to ensure repositories are cloned locally
  - Forbidden patterns to prevent assumptions and speculation
  - Required patterns for source citation (file:line_number)
  - Tech stack analysis guides for Node.js, Python, Rust projects
  - Directory structure conventions for competitor tracking
  - Bundled references: profile_template.md, analysis_checklist.md
  - Management script: update-competitors.sh (clone/pull/status)

### Changed
- Updated marketplace skills count from 34 to 35
- Updated marketplace version from 1.29.0 to 1.30.0
- Updated README.md badges (skills count, version)
- Updated README.md to include competitors-analysis in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include competitors-analysis in skills listing
- Updated CLAUDE.md skills count from 34 to 35
- Added competitors-analysis use case section to README.md
- Added competitors-analysis use case section to README.zh-CN.md

## [1.29.0] - 2026-01-29

### Added
- **Enhanced Skill**: skill-creator v1.4.0 - Comprehensive YAML frontmatter documentation
  - Complete YAML frontmatter reference table with all available fields
  - `context: fork` documentation - critical for subagent-accessible skills
  - Invocation control comparison table showing behavior differences
  - `$ARGUMENTS` placeholder explanation with usage examples
  - `allowed-tools` wildcard syntax examples (`Bash(git *)`, `Bash(npm *)`, `Bash(docker compose *)`)
  - `hooks` field inline example for pre-invoke configuration
  - Updated init_skill.py template with commented optional fields

### Changed
- Updated marketplace version from 1.28.0 to 1.29.0
- Updated skill-creator plugin version from 1.3.0 to 1.4.0

### Contributors
- [@costa-marcello](https://github.com/costa-marcello) - PR #6: Initial frontmatter documentation

## [1.28.0] - 2026-01-25

### Added
- **Enhanced Skill**: meeting-minutes-taker v1.1.0 - Speaker identification and pre-processing pipeline
  - Speaker identification via feature analysis (word count, segment count, filler ratio, speaking style)
  - Context file template (`references/context_file_template.md`) for team directory mapping
  - Intelligent file naming pattern: `YYYY-MM-DD-<topic>-<type>.md`
  - Pre-processing pipeline integration with markdown-tools and transcript-fixer
  - Transcript quality assessment workflow

### Changed
- Updated marketplace version from 1.27.0 to 1.28.0
- Updated meeting-minutes-taker plugin version from 1.0.0 to 1.1.0

## [1.27.0] - 2026-01-25

### Added
- **Enhanced Skill**: markdown-tools v1.2.0 - Multi-tool orchestration with Heavy Mode
  - Dual mode architecture: Quick Mode (fast) and Heavy Mode (best quality)
  - New `convert.py` - Main orchestrator with tool selection matrix
  - New `merge_outputs.py` - Segment-level multi-tool output merger
  - New `validate_output.py` - Quality validation with HTML reports
  - Enhanced `extract_pdf_images.py` - Image extraction with metadata (page, position, dimensions)
  - PyMuPDF4LLM integration for LLM-optimized PDF conversion
  - pandoc integration for DOCX/PPTX structure preservation
  - Quality metrics: text retention, table retention, image retention
  - New references: heavy-mode-guide.md, tool-comparison.md

### Changed
- Updated marketplace version from 1.26.0 to 1.27.0
- Updated markdown-tools plugin version from 1.1.0 to 1.2.0

## [1.26.0] - 2026-01-25

### Added
- **New Skill**: deep-research - Format-controlled research reports with evidence mapping
  - Report spec and format contract workflow
  - Multi-pass parallel drafting with UNION merge
  - Evidence table with source quality rubric
  - Citation verification and conflict handling
  - Bundled references: report template, formatting rules, research plan checklist, source quality rubric, completeness checklist

### Changed
- Updated marketplace skills count from 33 to 34
- Updated marketplace version from 1.25.0 to 1.26.0
- Updated README.md badges (skills count, version)
- Updated README.md to include deep-research in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include deep-research in skills listing
- Updated CLAUDE.md skills count from 33 to 34
- Added deep-research use case section to README.md
- Added deep-research use case section to README.zh-CN.md
- Added deep-research documentation quick link to README.md
- Added deep-research documentation quick link to README.zh-CN.md

## [1.25.0] - 2026-01-24

### Added
- **New Skill**: meeting-minutes-taker - Transform meeting transcripts into structured minutes
  - Multi-pass parallel generation with UNION merge strategy
  - Evidence-based recording with speaker quotes
  - Mermaid diagrams for architecture discussions
  - Iterative human-in-the-loop refinement workflow
  - Bundled references: template and completeness checklist

### Changed
- Updated marketplace skills count from 32 to 33
- Updated marketplace version from 1.24.0 to 1.25.0
- Updated skill-creator to v1.3.0:
  - Added Step 5: Sanitization Review (Optional)
  - New references/sanitization_checklist.md with 8 categories of content to sanitize
  - Automated grep scan commands for detecting sensitive content
  - 3-phase sanitization process and completion checklist

## [1.24.0] - 2026-01-22

### Added
- **New Skill**: claude-skills-troubleshooting - Diagnose and resolve Claude Code plugin and skill configuration issues
  - Plugin installation and enablement debugging
  - installed_plugins.json vs settings.json enabledPlugins diagnosis
  - Marketplace cache freshness detection
  - Plugin state architecture documentation
  - Bundled diagnostic script (diagnose_plugins.py)
  - Batch enable script for missing plugins (enable_all_plugins.py)
  - Known GitHub issues tracking (#17832, #19696, #17089, #13543, #16260)
  - Skills vs Commands architecture explanation

### Changed
- Updated marketplace skills count from 31 to 32
- Updated marketplace version from 1.23.0 to 1.24.0
- Updated README.md badges (skills count, version)
- Updated README.md to include claude-skills-troubleshooting in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include claude-skills-troubleshooting in skills listing
- Updated CLAUDE.md skills count from 31 to 32
- Added claude-skills-troubleshooting use case section to README.md
- Added claude-skills-troubleshooting use case section to README.zh-CN.md

## [1.23.0] - 2026-01-22

### Added
- **New Skill**: i18n-expert - Complete internationalization/localization setup and auditing for UI codebases
  - Library selection and setup (react-i18next, next-intl, vue-i18n)
  - Key architecture and locale file organization (JSON, YAML, PO, XLIFF)
  - Translation generation strategy (AI, professional, manual)
  - Routing and language detection/switching
  - SEO and metadata localization
  - RTL support for applicable locales
  - Key parity validation between en-US and zh-CN
  - Pluralization and formatting validation
  - Error code mapping to localized messages
  - Bundled i18n_audit.py script for key usage extraction
  - Scope inputs: framework, existing i18n state, target locales, translation quality needs

### Changed
- Updated marketplace skills count from 30 to 31
- Updated marketplace version from 1.22.0 to 1.23.0
- Updated README.md badges (skills count, version)
- Updated README.md to include i18n-expert in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include i18n-expert in skills listing
- Updated CLAUDE.md skills count from 30 to 31
- Added i18n-expert use case section to README.md
- Added i18n-expert use case section to README.zh-CN.md

### Changed
- None

### Deprecated
- None

### Removed
- None

### Fixed
- None

### Security
- None

## [1.22.0] - 2026-01-15

### Added
- **New Skill**: skill-reviewer - Reviews and improves Claude Code skills against official best practices
  - Self-review mode: Validate your own skills before publishing
  - External review mode: Evaluate others' skill repositories
  - Auto-PR mode: Fork, improve, and submit PRs to external repos
  - Automated validation via bundled skill-creator scripts
  - Evaluation checklist covering frontmatter, instructions, and resources
  - Additive-only contribution principle (never delete files)
  - PR guidelines with tone recommendations and templates
  - Self-review checklist for respect verification
  - References: evaluation_checklist.md, pr_template.md, marketplace_template.json
  - Auto-install dependencies: automatically installs skill-creator if missing

- **New Skill**: github-contributor - Strategic guide for becoming an effective GitHub contributor
  - Four contribution types: Documentation, Code Quality, Bug Fixes, Features
  - Project selection criteria with red flags
  - PR excellence workflow with templates
  - Reputation building ladder (Documentation → Bug Fixes → Features → Maintainer)
  - GitHub CLI command reference
  - Conventional commit message format
  - Common mistakes and best practices
  - References: pr_checklist.md, project_evaluation.md, communication_templates.md

### Changed
- Updated marketplace skills count from 28 to 30
- Updated marketplace version from 1.21.1 to 1.22.0
- Updated README.md badges (skills count: 30, version: 1.22.0)
- Updated README.md to include skill-reviewer in skills listing
- Updated README.md to include github-contributor in skills listing
- Updated README.zh-CN.md badges (skills count: 30, version: 1.22.0)
- Updated README.zh-CN.md to include skill-reviewer in skills listing
- Updated README.zh-CN.md to include github-contributor in skills listing
- Updated CLAUDE.md skills count from 28 to 30
- Added skill-reviewer use case section to README.md
- Added github-contributor use case section to README.md
- Added skill-reviewer use case section to README.zh-CN.md
- Added github-contributor use case section to README.zh-CN.md

## [1.21.1] - 2026-01-11

### Changed
- **Updated Skill**: macos-cleaner v1.0.0 → v1.1.0 - Major improvements based on real-world usage
  - Added "Value Over Vanity" principle: Goal is identifying truly useless items, not maximizing cleanup numbers
  - Added "Network Environment Awareness": Consider slow internet (especially in China) when recommending cache deletion
  - Added "Impact Analysis Required": Every cleanup recommendation must explain consequences
  - Added comprehensive "Anti-Patterns" section: What NOT to delete (Xcode DerivedData, npm _cacache, uv cache, Playwright, iOS DeviceSupport, etc.)
  - Added "Multi-Layer Deep Exploration" guide: Complete tmux + Mole TUI navigation workflow
  - Added "High-Quality Report Template": Proven 3-tier classification report format (🟢/🟡/🔴)
  - Added "Report Quality Checklist": 8-point verification before presenting findings
  - Added explicit prohibition of `docker volume prune -f` - must confirm per-project
  - Updated safety principles to emphasize cache value over cleanup metrics

## [1.21.0] - 2026-01-11

### Added
- **New Skill**: macos-cleaner - Intelligent macOS disk space analysis and cleanup with safety-first philosophy
  - Smart analysis of system caches, application caches, logs, and temporary files
  - Application remnant detection (orphaned data from uninstalled apps)
  - Large file discovery with automatic categorization (videos, archives, databases, disk images)
  - Development environment cleanup (Docker, Homebrew, npm, pip, Git repositories)
  - Interactive safe deletion with user confirmation at every step
  - Risk-level categorization (🟢 Safe / 🟡 Caution / 🔴 Keep)
  - Integration guide for Mole visual cleanup tool
  - Before/after cleanup reports with space recovery metrics
  - Bundled scripts: `analyze_caches.py`, `analyze_dev_env.py`, `analyze_large_files.py`, `find_app_remnants.py`, `safe_delete.py`, `cleanup_report.py`
  - Comprehensive safety rules and cleanup target documentation
  - Time Machine backup recommendations for large deletions
  - Professional user experience: analyze first, explain thoroughly, execute with confirmation

### Changed
- Updated marketplace skills count from 27 to 28
- Updated marketplace version from 1.20.0 to 1.21.0
- Updated README.md badges (skills count: 28, version: 1.21.0)
- Updated README.md to include macos-cleaner in skills listing
- Updated README.zh-CN.md badges (skills count: 28, version: 1.21.0)
- Updated README.zh-CN.md to include macos-cleaner in skills listing
- Updated CLAUDE.md skills count from 27 to 28
- Added macos-cleaner use case section to README.md
- Added macos-cleaner use case section to README.zh-CN.md

## [1.20.0] - 2026-01-11

### Added
- **New Skill**: twitter-reader - Fetch Twitter/X post content using Jina.ai API
  - Bypass JavaScript restrictions without authentication
  - Retrieve tweet content including author, timestamp, post text, images, and thread replies
  - Support for individual posts or batch fetching from x.com or twitter.com URLs
  - Bundled scripts: `fetch_tweet.py` (Python) and `fetch_tweets.sh` (Bash)
  - Environment variable configuration for secure API key management
  - Supports both x.com and twitter.com URL formats

### Changed
- Updated marketplace skills count from 26 to 27
- Updated marketplace version from 1.19.0 to 1.20.0
- Updated README.md badges (skills count: 27, version: 1.20.0)
- Updated README.md to include twitter-reader in skills listing
- Updated README.zh-CN.md badges (skills count: 27, version: 1.20.0)
- Updated README.zh-CN.md to include twitter-reader in skills listing
- Updated CLAUDE.md skills count from 26 to 27
- Added twitter-reader use case section to README.md
- Added twitter-reader use case section to README.zh-CN.md

### Security
- **twitter-reader**: Implemented secure API key management using environment variables
  - Removed hardcoded API keys from all scripts and documentation
  - Added validation for JINA_API_KEY environment variable
  - Enforced HTTPS-only URLs in Python script

## [1.18.2] - 2026-01-05

### Changed
- **claude-md-progressive-disclosurer**: Enhanced workflow with safety and verification features
  - Added mandatory backup step (Step 0) before any modifications
  - Added pre-execution verification checklist (Step 3.5) to prevent information loss
  - Added post-optimization testing (Step 5) for discoverability validation
  - Added exception criteria for size guidelines (safety-critical, high-frequency, security-sensitive)
  - Added project-level vs user-level CLAUDE.md guidance
  - Updated references/progressive_disclosure_principles.md with verification methods
- Updated claude-md-progressive-disclosurer plugin version from 1.0.0 to 1.0.1

## [1.18.1] - 2025-12-28

### Changed
- **markdown-tools**: Enhanced with PDF image extraction capability
  - Added `extract_pdf_images.py` script using PyMuPDF
  - Refactored SKILL.md for clearer workflow documentation
  - Updated installation instructions to use `markitdown[pdf]` extra
- Updated marketplace version from 1.18.0 to 1.18.1

## [1.18.0] - 2025-12-20

### Added
- **New Skill**: pdf-creator - Convert markdown to PDF with Chinese font support (WeasyPrint)
- **New Skill**: claude-md-progressive-disclosurer - Optimize CLAUDE.md with progressive disclosure
- **New Skill**: promptfoo-evaluation - Promptfoo-based LLM evaluation workflows
- **New Skill**: iOS-APP-developer - iOS app development with XcodeGen, SwiftUI, and SPM

### Changed
- Updated marketplace skills count from 23 to 25
- Updated marketplace version from 1.16.0 to 1.18.0
- Updated README/README.zh-CN badges, skill lists, use cases, quick links, and requirements
- Updated QUICKSTART docs to clarify marketplace install syntax and remove obsolete links
- Updated CLAUDE.md skill counts and added the new skills to the list

## [1.16.0] - 2025-12-11

### Added
- **New Skill**: skills-search - CCPM registry search and management
  - Search for Claude Code skills in the CCPM registry
  - Install skills by name with `ccpm install <skill-name>`
  - List installed skills with `ccpm list`
  - Get detailed skill information with `ccpm info <skill-name>`
  - Uninstall skills with `ccpm uninstall <skill-name>`
  - Install skill bundles (web-dev, content-creation, developer-tools)
  - Supports multiple installation formats (registry, GitHub owner/repo, full URLs)
  - Troubleshooting guidance for common issues

### Changed
- Updated marketplace skills count from 22 to 23
- Updated marketplace version from 1.15.0 to 1.16.0
- Updated README.md badges (skills count: 23, version: 1.16.0)
- Updated README.md to include skills-search in skills listing (skill #20)
- Updated README.zh-CN.md badges (skills count: 23, version: 1.16.0)
- Updated README.zh-CN.md to include skills-search with Chinese translation
- Updated CLAUDE.md skills count from 22 to 23
- Added skills-search use case section to README.md
- Added skills-search use case section to README.zh-CN.md
- Added installation command for skills-search
- Enhanced marketplace metadata description to include CCPM skill management

## [1.13.0] - 2025-12-09

### Added
- **New Skill**: claude-code-history-files-finder - Session history recovery for Claude Code
  - Search sessions by keywords with frequency ranking
  - Recover deleted files from Write tool calls with automatic deduplication
  - Analyze session statistics (message counts, tool usage, file operations)
  - Batch operations for processing multiple sessions
  - Streaming processing for large session files (>100MB)
  - Bundled scripts: analyze_sessions.py, recover_content.py
  - Bundled references: session_file_format.md, workflow_examples.md
  - Follows Anthropic skill authoring best practices (third-person description, imperative style, progressive disclosure)

- **New Skill**: docs-cleaner - Documentation consolidation
  - Consolidate redundant documentation while preserving valuable content
  - Redundancy detection for overlapping documents
  - Smart merging with structure preservation
  - Validation for consolidated documents

### Changed
- Updated marketplace skills count from 18 to 20
- Updated marketplace version from 1.11.0 to 1.13.0
- Updated README.md badges (skills count: 20, version: 1.13.0)
- Updated README.md to include claude-code-history-files-finder in skills listing (skill 18)
- Updated README.md to include docs-cleaner in skills listing (skill 19)
- Updated README.zh-CN.md badges (skills count: 20, version: 1.13.0)
- Updated README.zh-CN.md to include both new skills with Chinese translations
- Updated CLAUDE.md skills count from 18 to 20
- Added session history recovery use case section to README.md
- Added documentation maintenance use case section to README.md
- Added corresponding use case sections to README.zh-CN.md
- Added installation commands for both new skills
- Added quick links for documentation references
- **skill-creator** v1.2.0 → v1.2.1: Added cache directory warning
  - Added critical warning about not editing skills in `~/.claude/plugins/cache/`
  - Explains that cache is read-only and changes are lost on refresh
  - Provides correct vs wrong path examples
- **transcript-fixer** v1.0.0 → v1.1.0: Enhanced with Chinese domain support and AI fallback
  - Added Chinese/Japanese/Korean character support for domain names (e.g., `火星加速器`, `具身智能`)
  - Added `[CLAUDE_FALLBACK]` signal when GLM API is unavailable for Claude Code to take over
  - Added Prerequisites section requiring `uv` for Python execution
  - Added Critical Workflow section for dictionary iteration best practices
  - Added AI Fallback Strategy section with manual correction guidance
  - Added Database Operations section with schema reference requirement
  - Added Stages table for quick reference (Dictionary → AI → Full pipeline)
  - Added new bundled script: `ensure_deps.py` for shared virtual environment
  - Added new bundled references: `database_schema.md`, `iteration_workflow.md`
  - Updated domain validation from whitelist to pattern matching
  - Updated tests for Chinese domain names and security bypass attempts

## [youtube-downloader-1.1.0] - 2025-11-19

### Changed
- **youtube-downloader** v1.0.0 → v1.1.0: Enhanced with HLS streaming support
  - Added comprehensive HLS stream download support (m3u8 format)
  - Added support for platforms like Mux, Vimeo, and other HLS-based services
  - Added ffmpeg-based download workflow with authentication headers
  - Added Referer header configuration for protected streams
  - Added protocol whitelisting guidance
  - Added separate audio/video stream handling and merging workflow
  - Added troubleshooting for 403 Forbidden errors
  - Added troubleshooting for yt-dlp stuck on cookie extraction
  - Added troubleshooting for expired signatures
  - Added performance tips (10-15x realtime speed)
  - Updated skill description to include HLS streams and authentication
  - Updated "When to Use" triggers to include m3u8/HLS downloads
  - Updated Overview to mention multiple streaming platforms

## [1.11.0] - 2025-11-16

### Added
- **New Skill**: prompt-optimizer - Transform vague prompts into precise EARS specifications
  - EARS (Easy Approach to Requirements Syntax) transformation methodology
  - 6-step optimization workflow: analyze, transform, identify theories, extract examples, enhance, present
  - 5 EARS sentence patterns (ubiquitous, event-driven, state-driven, conditional, unwanted behavior)
  - Domain theory grounding with 10+ categories (productivity, UX, gamification, learning, e-commerce, security)
  - 40+ industry frameworks mapped to use cases (GTD, BJ Fogg, Gestalt, AIDA, Zero Trust, etc.)
  - Role/Skills/Workflows/Examples/Formats prompt enhancement framework
  - Advanced optimization techniques (multi-stakeholder, non-functional requirements, complex logic)
  - Bundled references: ears_syntax.md, domain_theories.md, examples.md
  - Complete transformation examples (procrastination app, e-commerce, learning platform, password reset)
  - Progressive disclosure pattern (metadata → SKILL.md → bundled resources)

### Changed
- Updated marketplace skills count from 17 to 18
- Updated marketplace version from 1.10.0 to 1.11.0
- Updated README.md badges (skills count, version)
- Updated README.md to include prompt-optimizer in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include prompt-optimizer in skills listing
- Updated CLAUDE.md skills count from 17 to 18
- Added prompt-optimizer use case section to README.md
- Added prompt-optimizer use case section to README.zh-CN.md
- Enhanced marketplace metadata description to include prompt optimization capability
- **prompt-optimizer v1.1.0**: Improved skill following Anthropic best practices
  - Reduced SKILL.md from 369 to 195 lines (47% reduction) using progressive disclosure
  - Added new reference: advanced_techniques.md (325 lines) for multi-stakeholder, non-functional, and complex logic patterns
  - Added 4th complete example (password reset security) to examples.md
  - Added attribution to 阿星AI工作室 (A-Xing AI Studio) for EARS methodology inspiration
  - Enhanced reference loading guidance with specific triggers for each file
  - Improved conciseness and clarity following skill authoring best practices

## [1.10.0] - 2025-11-10

### Added
- **New Skill**: qa-expert - Comprehensive QA testing infrastructure with autonomous LLM execution
  - One-command QA project initialization with complete templates and tracking CSVs
  - Google Testing Standards implementation (AAA pattern, 90% coverage targets)
  - Autonomous LLM-driven test execution via master prompts (100x speed improvement)
  - OWASP Top 10 security testing framework (90% coverage target)
  - Bug tracking with P0-P4 severity classification
  - Quality gates enforcement (100% execution, ≥80% pass rate, 0 P0 bugs, ≥80% code coverage)
  - Ground Truth Principle for preventing doc/CSV sync issues
  - Day 1 onboarding guide for new QA engineers (5-hour timeline)
  - Bundled scripts: `init_qa_project.py`, `calculate_metrics.py`
  - Bundled references: master_qa_prompt.md, google_testing_standards.md, day1_onboarding.md, ground_truth_principle.md, llm_prompts_library.md
  - Complete test case and bug tracking templates
  - 30+ ready-to-use LLM prompts for QA tasks
  - Progressive disclosure pattern (metadata → SKILL.md → bundled resources)

### Changed
- Updated marketplace skills count from 16 to 17
- Updated marketplace version from 1.9.0 to 1.10.0
- Updated README.md badges (skills count, version)
- Updated README.md to include qa-expert in skills listing
- Updated CLAUDE.md skills count from 16 to 17
- Added qa-expert use case section to README.md
- Enhanced marketplace metadata description to include QA testing capability

## [1.9.0] - 2025-10-29

### Added
- **New Skill**: video-comparer - Video comparison and quality analysis tool
  - Compare original and compressed videos with interactive HTML reports
  - Calculate quality metrics (PSNR, SSIM) for compression analysis
  - Generate frame-by-frame visual comparisons with three viewing modes (slider, side-by-side, grid)
  - Extract video metadata (codec, resolution, bitrate, duration, file size)
  - Multi-platform FFmpeg installation instructions (macOS, Linux, Windows)
  - Bundled Python script: `compare.py` with security features (path validation, resource limits)
  - Comprehensive reference documentation (video metrics interpretation, FFmpeg commands, configuration)
  - Self-contained HTML output with embedded frames (no server required)

### Changed
- Updated marketplace skills count from 15 to 16
- Updated marketplace version from 1.8.0 to 1.9.0
- Updated README.md badges (skills count, version)
- Updated README.md to include video-comparer in skills listing
- Updated CLAUDE.md skills count from 15 to 16
- Added video-comparer use case section to README.md
- Added FFmpeg to requirements section

## [1.6.0] - 2025-10-26

### Added
- **New Skill**: youtube-downloader - YouTube video and audio downloading with yt-dlp
  - Download YouTube videos and playlists with robust error handling
  - Audio-only download with MP3 conversion
  - Android client workaround for nsig extraction issues (automatic)
  - Format listing and custom format selection
  - Network error handling for proxy/restricted environments
  - Bundled Python script: `download_video.py` with yt-dlp availability check
  - Comprehensive troubleshooting documentation for common yt-dlp issues
  - Demo tape file and GIF showing download workflow

### Changed
- Updated marketplace.json from 12 to 13 skills
- Updated marketplace version from 1.5.0 to 1.6.0
- Enhanced marketplace metadata description to include YouTube downloading capability
- Updated CLAUDE.md with complete 13-skill listing
- Updated CLAUDE.md marketplace version to v1.6.0
- Updated README.md to reflect 13 available skills
- Updated README.md badges (skills count, version)
- Added youtube-downloader to manual installation instructions
- Added youtube-downloader use case section in README
- Added youtube-downloader to documentation quick links
- Added yt-dlp to requirements section

## [1.5.0] - 2025-10-26

### Added
- **New Skill**: ppt-creator - Professional presentation creation with dual-path PPTX generation
  - Pyramid Principle structure (conclusion → reasons → evidence)
  - Assertion-evidence slide framework
  - Automatic data synthesis and chart generation (matplotlib)
  - Dual-path PPTX creation (Marp CLI + document-skills:pptx)
  - Complete orchestration: content → data → charts → PPTX with charts
  - 45-60 second speaker notes per slide
  - Quality scoring with auto-refinement (target: 75/100)

### Changed
- Updated marketplace.json from 11 to 12 skills
- Updated marketplace version from 1.4.0 to 1.5.0

## [1.4.0] - 2025-10-25

### Added
- **New Skill**: cloudflare-troubleshooting - API-driven Cloudflare diagnostics and troubleshooting
  - Systematic investigation of SSL errors, DNS issues, and redirect loops
  - Direct Cloudflare API integration for evidence-based troubleshooting
  - Bundled Python scripts: `check_cloudflare_config.py` and `fix_ssl_mode.py`
  - Comprehensive reference documentation (SSL modes, API overview, common issues)
- **New Skill**: ui-designer - Design system extraction from UI mockups and screenshots
  - Automated design system extraction (colors, typography, spacing)
  - Design system documentation generation
  - PRD and implementation prompt creation
  - Bundled templates: design-system.md, vibe-design-template.md, app-overview-generator.md
- Enhanced `.gitignore` patterns for archives, build artifacts, and documentation files

### Changed
- Updated marketplace.json from 9 to 11 skills
- Updated marketplace version from 1.3.0 to 1.4.0
- Enhanced marketplace metadata description to include new capabilities
- Updated CLAUDE.md with complete 11-skill listing
- Updated README.md to reflect 11 available skills
- Updated README.zh-CN.md to reflect 11 available skills

## [1.3.0] - 2025-10-23

### Added
- **New Skill**: cli-demo-generator - Professional CLI demo generation with VHS automation
  - Automated demo generation from command lists
  - Batch processing with YAML/JSON configs
  - Interactive recording with asciinema
  - Smart timing and multiple output formats
- Comprehensive improvement plan with 5 implementation phases
- Automated installation scripts for macOS/Linux (`install.sh`) and Windows (`install.ps1`)
- Complete Chinese translation (README.zh-CN.md)
- Quick start guides in English and Chinese (QUICKSTART.md, QUICKSTART.zh-CN.md)
- VHS demo infrastructure for all skills
- Demo tape files for skill-creator, github-ops, and markdown-tools
- Automated demo generation script (`demos/generate_all_demos.sh`)
- GitHub issue templates (bug report, feature request)
- GitHub pull request template
- FAQ section in README
- Table of Contents in README
- Enhanced badges (Claude Code version, PRs welcome, maintenance status)
- Chinese user guide with CC-Switch recommendation
- Language switcher badges (English/简体中文)

### Changed
- **BREAKING**: Restructured README.md to highlight skill-creator as essential meta-skill
- Moved skill-creator from position #7 to featured "Essential Skill" section
- Updated CLAUDE.md with new priorities and installation commands
- Enhanced documentation navigation and discoverability
- Improved README structure with better organization

### Removed
- skill-creator from "Other Available Skills" numbered list (now featured separately)

## [1.2.0] - 2025-10-22

### Added
- llm-icon-finder skill for AI/LLM brand icons
- Comprehensive marketplace structure with 8 skills
- Professional documentation for all skills
- CONTRIBUTING.md with quality standards
- INSTALLATION.md with detailed setup instructions

### Changed
- Updated marketplace.json to v1.2.0
- Enhanced skill descriptions and metadata

## [1.1.0] - 2025-10-15

### Added
- skill-creator skill with initialization, validation, and packaging scripts
- repomix-unmixer skill for extracting repomix packages
- teams-channel-post-writer skill for Teams communication
- Enhanced documentation structure

### Changed
- Improved skill quality standards
- Updated all skill SKILL.md files with consistent formatting

## [1.0.0] - 2025-10-08

### Added
- Initial release of Claude Code Skills Marketplace
- github-ops skill for GitHub operations
- markdown-tools skill for document conversion
- mermaid-tools skill for diagram generation
- statusline-generator skill for Claude Code customization
- MIT License
- README.md with comprehensive documentation
- Individual skill documentation (SKILL.md files)

---

## Version Numbering

We use [Semantic Versioning](https://semver.org/):

- **MAJOR** version when you make incompatible API changes
- **MINOR** version when you add functionality in a backward compatible manner
- **PATCH** version when you make backward compatible bug fixes

## Release Process

1. Update version in `.claude-plugin/marketplace.json`
2. Update CHANGELOG.md with changes
3. Update README.md version badge
4. Create git tag: `git tag -a v1.x.x -m "Release v1.x.x"`
5. Push tag: `git push origin v1.x.x`

[Unreleased]: https://github.com/daymade/claude-code-skills/compare/v1.10.0...HEAD
[1.10.0]: https://github.com/daymade/claude-code-skills/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/daymade/claude-code-skills/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/daymade/claude-code-skills/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/daymade/claude-code-skills/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/daymade/claude-code-skills/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/daymade/claude-code-skills/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/daymade/claude-code-skills/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/daymade/claude-code-skills/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/daymade/claude-code-skills/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/daymade/claude-code-skills/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/daymade/claude-code-skills/releases/tag/v1.0.0
