# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **excalidraw-use** v1.0.0 (marketplace v3.7.0): place existing images onto an Excalidraw whiteboard — the one Excalidraw job the ecosystem does not cover. The available MCP servers and skills (including the 26-tool one) document element CRUD, alignment, export and Mermaid conversion but no `image` element type, no `dataURL` handling and no `files` map; they export diagrams rather than embed pictures. `build_scene.py` writes a grid-laid scene with content-hash dedupe, exclusion of images already on the board, and a read-back check that fails on a missing/mismatched file entry, a distorted aspect ratio, or any overlap; `--template-from` deep-copies the image-element field set out of the user's own board, because Excalidraw's published schema stops before `fileId`/`status`/`scale`/`crop`. `split_scene.py` partitions a scene for the clipboard route. `inspect_scene.py` reports element mix, payload size, key/content mismatches and occupied extent read-only. `shoot_deck.mjs` turns a Vite/React deck into per-slide PNGs with presenter chrome hidden and staged reveals expanded, and reports fragments that stayed at opacity 0 — the failure that otherwise ships plausible screenshots with content missing. Bundled references carry the paste workflow (Open and drag-and-drop **replace** the scene; only the clipboard merges) and the deck-capture pitfalls (a stale build silently removes a source feature; `innerText` reads hidden fragments as present). Scripts verified end-to-end on generated fixtures and a real 30-slide deck, with both the stale-build warning and `--strict` calibrated against known-bad and known-good input.
- **peer-message** v1.0.0 (marketplace v3.6.0): restore the previously uncommitted Claude UDS messenger from its source session and extend it into a local Claude Code ↔ Codex coordination layer. The bundled stdlib CLI discovers `claude:` and `codex:` targets across isolated standard Claude profiles, preserves the original authenticated UDS fallback, routes Codex through the first-party `codex queue --thread` command, supports explicitly counted cross-provider broadcasts, adds source/reply envelopes with explicit provenance strength, and verifies delivery from Claude transcripts or Codex queue/thread history without writing either product's SQLite stores. Claude uses a host-recognized peer wrapper; Codex provenance remains advisory text enforced by receiver-side governing instructions. The Skill-local official-feature reference owns the corrected availability and inbound-policy boundaries. The registered test suite, live Codex queue acceptance, and subsequent thread-history consumption were independently verified.

### Changed
- **skill-creator** (`daymade-skill` v1.35.2 → v1.35.3, marketplace v3.9.2): the version-bump rule now says what the gate actually enforces. It read "any change to a skill's files — even a one-line typo fix — needs a bump", which stopped being literally true when the version gate began consuming `packaging_policy.py`: a change confined to files that never ship is not a content change and needs no bump. The sentence now says *shipped* files and points at the module that defines the set rather than restating it, and names the consequence the exception exists for — retiring one local artifact would otherwise demand a release from every plugin that happened to carry one, which is exactly the 53-release bill that surfaced the gate defect.
- **transcript-fixer** v1.34.1 → v1.34.2: two roster-variant shapes can no longer become global rules, and a retired rule no longer keeps a sidecar open. (1) The people-roster loader refuses a **single surname plus an honorific** (`朱老师`, `王总`) (`老師`/`總` included) with a loud stderr warning, and `--add` / `--import` refuse the same FROM shape as an error that `--force` does not override: such a form names everyone with that surname, so one meeting's mishearing of one person's surname recorded as a variant rewrites people who were named correctly. Real case 2026-09-07: seven surname variants captured from a single meeting had been loaded as global rules for months, and a `朱老师` in an unrelated transcript was presented as that person; the rule had already been disabled as a false positive, but the roster line resurrected the question. A given name plus an honorific (`明源总`) and a bare misheard name token (`小铭`) still load. (2) The **bare-numeric refusal** written on 2026-09-05 ships with it: a variant that is only digits (`95`) is refused at roster load and by `--add` / `--import` (`--force` included), because digits match timestamps, scores and prices in every transcript (one such line once deferred 122 items in a single rerun). The three predicates — loader, `check_correction_safety`, import — are kept in sync and documented together in `dictionary_identity_and_context.md`; the native workflow gains the entity-evidence rule that parallel list slots are not identity evidence. (3) `--close-sidecars` reads the dictionary's disabled pairs: a report entry whose FROM→TO rule has since been disabled as a false positive and has no active rule left in the consulted scope (`--domain` when given, else every domain) is `disabled` — closed without a verdict and never re-asked — instead of surfacing as `undecided` for a human to answer again; a matched queue row still outranks the retirement; `entries.disabled` is added to the JSON. 11 new tests (756 collected across `scripts/tests` and `tests`); the roster fixture's example variant is renamed because the old example (`金老师`) is itself a refused shape.
- **tibo-reset-codex** v1.4.0 → v1.5.0: fold the 2026-09-04~06 live-run lessons into the announcement path, the multi-account checks and the banked semantics. (1) The Radar `type` tag is an editor label, not a machine verdict — a cross-platform reply gets tagged `reset` too (2026-09-05: Tibo replying "Wow, huge, wonder why!" to Anthropic's Claude-Max reset announcement), so the fxtwitter command now prints `replying_to`/`replying_to_status` and §1 says an off-platform reply is not an OpenAI event. (2) The B-layer account check gains its second dated hit and a reading trap: cc-switch's `is_current` is only that tool's own bookmark and goes stale after a manual `codex login` (measured: it pointed at one real account's email while `auth.json` held a different one) — the logged-in identity is always layer A's. (3) §2 states the rollout coverage boundary: snapshots cover only the currently logged-in account, so a multi-account user's other accounts are invisible to it; user-transcribed product-page statistics (per-account reset countdowns plus "N full resets") count as direct observation at the same evidence level and close the "announced ≠ landed" gap (measured: four paid accounts each showing two full resets the day after the full-banked-reset announcement), and relative countdowns must be converted to absolute times with the reading moment stated. (4) The BANKED row states the redemption semantics — landed credits do not auto-consume; the user applies them on the usage page — and maps rollout-delay compensation explicitly under failure compensation. (5) The retry rule now names every external endpoint in §1 (Radar, fxtwitter, status page), carrying the independent fresh-agent re-run's three flake evidences, after that review caught the first-copy commands failing intermittently while the rule sat scoped to the status family.
- **peer-message** v1.5.0 → v1.5.1 (marketplace v3.9.1): repair the paragraph v1.5.0 shipped broken, and bring the README's ownership clause back to what the file it points at actually covers. The §5 explanatory paragraph had the war story's two-conjunct filter spliced into the middle of another sentence, leaving three consecutive em-dashes, a dangling clause, and two references to "three items" whose antecedents read as different sets; it is now three sentences with the conjuncts stated once and each half mapped to the error it names. README.md and README.zh-CN.md described `coordination-and-learning-loop.md` as owning only "parent/worker handoff language and evidence-gated Skill improvement" — accurate at v1.2.0 and stale ever since v1.3.0 gave that file the inbound-assertion contract and v1.4.0 the denial contract, so the entry now matches the scope the file declares in its own header and that CLAUDE.md's ownership map already stated correctly. No rule, command, or contract changes.
- **peer-message** v1.4.3 → v1.5.0 (marketplace v3.9.0): close the item v1.4.0's review left open — "not yet executed end-to-end in a real multi-session ownership investigation" — with what that run produced. §4 gains the case where the premise is true but the *discriminator* under it does not discriminate. A peer classifying a shared artifact usually holds one binary marker — a record carries a trailer or not, a file is in a manifest or not, a field is empty or not — and reads absence as "anomaly", then anomaly as "from a writer I cannot enumerate". Answering only "not mine" is correct and still harmful: it confirms the one link in that chain the peer could not check for itself, and it walks away with an uncalibrated criterion. The action is not to prove authorship but to run the same marker across comparable neighbours — adjacent commits on the branch, sibling files in the directory, records from the same tool in the same window. What the rule asks for is a **count**, not a verdict: how many were read, how many are missing the marker, and a value distribution instead of present/absent when the marker turns out to be multi-valued. Whether that count means "baseline" is the asker's call, so the `Stop` is unconditional and says so — an earlier draft gated it on "the criterion is calibrated", which two independent reviewers showed was satisfiable by reading one neighbour that happened to carry the marker, releasing the gate for exactly the move the section exists to prevent. There is deliberately no sample-size threshold, because a threshold becomes a pass you issue to yourself. §5's report frame gains the item its own prose already demanded and its checklist never carried: the section says outright that writing the frame IS stating the default filter you applied, yet the three required items (targets polled, provider and whether `--limit` was hit, unverified saved-catalog rows) contain nothing that reveals it — so a narrowed investigation fills all three truthfully and reads as compliant while the exact gap the section's war story teaches is the one thing absent from the table. Four items now, the filter first, with the boundary stated (item one is the cut *you* made; items three and four are the coverage the *tool* gave you, and one fact appearing in both is not double-counting). Both examples now name their own filter — review found the pre-existing one had quietly narrowed by provider while being presented as the un-narrowed case, since `list` defaults to `--provider all` and "ask only the Claude side" is already a cut — and the narrowed example states what it gave up, because no narrowing axis is safe: `cwd`, liveness and provider each drop precisely the rows this section names as the lead. The war story's filter is now quoted as the conjunction it is ("in this repo's working directory" **and** "all live"), each half mapping to one of the two errors the section teaches; the previous text quoted half of it as "verbatim". SKILL.md carries the calibration rule inline, warns that neighbours drawn only from your own history calibrate nothing, and its frame pointer says four. Three reviewer dispatches on two axes produced eight adopted findings; the first attempt at §5 was deleted outright rather than softened after the fidelity axis showed it inverted the section's own war story. Description unchanged at 1023 of its 1024 characters.
- **peer-message** v1.4.2 → v1.4.3 (marketplace v3.8.10): put the Codex reply address back in `from`. The previous release removed it, reasoning that the field's contract is "copy this into `to`" and no Codex address satisfies it for the official Claude tools. That conflated two things: the official tools cannot reach a Codex thread, but `codex:<uuid>` is a working reply address — `codex queue --thread` documents its argument as "Session UUID or exact session name", and `resolve_codex` resolves it. Dropping it spared recipients holding only the official tools one recoverable failed attempt, which the body line already explained, and charged for it by taking a usable handle away from every recipient that has this Skill. It also left the route travelling without the thing it routes, inverting Case 23's T2: when the two spaces do not intersect, the identifier and its route travel together. `protocol-and-discovery.md` §2 had said `from` stays put; the previous release contradicted it in code without updating it. Both are corrected, and §2 now states why the identifier is good and only the official-resolvable form is missing.
- **claude-switch-models-setup** (`daymade-claude-code` v3.15.0 → v3.16.0): the skill described two incompatible answers to "where do the deployed `~/.config/claude-switch-models-setup/` links point". Setup step 2, `scripts/setup.sh` and a copied block in `troubleshooting.md` said the checkout; the architecture reference (since v3.9.0), `skill-install-audit.py`'s `DAEMON_RUNTIME_LAG` and the maintainer machine itself say the daemon's pinned plugin copy, advanced only with the pin. Running the installer on a pinned machine silently turned the links back into checkout links, which is exactly how the daemon and `csk` end up following whatever branch the checkout sits on. Step 2 now states both layouts once and points at the architecture reference and the pin procedure; `troubleshooting.md` references that step instead of carrying its own copy of the link loop; the architecture reference names the installer rule. `setup.sh` refuses to relink a machine whose existing links target a `plugins/cache` directory unless `CSMS_SETUP_RELINK_TO_CHECKOUT=1` is set, with a test for both the refusal and the override. Observed on the maintainer machine (2026-09-05/06): the links pointed at 3.6.1 and 3.11.0 version directories while `.zshrc` sourced the checkout copy directly; the launcher and the audit copy under `~/.config` now follow the pinned layout, and the machine-local wiring is recorded outside this public skill.
- **transcript-fixer** v1.33.4 → v1.34.0: the sidecar lifecycle gets a closing command and Stage 1 stops matching fragments across real words. (1) `--close-sidecars --input FILE` decides `closed | open | blocked` mechanically: every `*_changes.md`/`*_needs_review.md` entry is re-read against the ledger-masked transcript (applied / still the original / original absent from the whole file) and against the review queue for that exact file (rows are matched to occurrences by nearest line across every entry of the pair, so an applied occurrence claims its own row and a bare second occurrence stays undecided; a pending row blocks), a `*_stage1.md` newer than the file is refused (the plain Stage 1 rerun is its promotion path), a report the parser cannot read — a hand-written `_needs_review.md`, or a declared `Total changes` above the entries parsed — blocks instead of counting as empty, a newer `*_stage2.md`/`*_dryrun.md` is retained unless `--discard-unpromoted`; only `closed` removes the evidence, and `--decide-raw kept_original|skipped --by --note` records verdicts through the queue so closure leaves an audit trail rather than a silent deletion (exit 0/1/2, `--dry-run`, `--json`). Until now the contract said "preserve until every associated decision is closed" and nothing could decide it: a 51-sidecar audit of one knowledge base on 2026-09-05 found 36 files from 20 transcripts whose decisions had long closed, plus API `_stage2.md` outputs that were never promoted and never discarded. (2) A third match-time safety check in `DictionaryProcessor` (after the superset and common-word checks; the add-time and apply-time layers are unchanged): a dictionary match that is a fragment of real words is refused and counted as `Refused at word boundaries` (summary, with the first refusals listed) and `boundary_refused` (the eleventh `--json` field), neither applied nor deferred. The rule is chosen by script: an ASCII match with an ASCII letter directly beside it is inside a longer word (`Cloud` in `iCloud`; digits do not count, so `cloud3` still corrects); a CJK match is refused only when every segment of a dictionary-only jieba cut (HMM off) that overlaps it is a multi-character word and one of them crosses the match boundary (新一 in 更新|一下, 问题记 in 问题|记下来, 同龄 in 同龄人) — one single-character segment under the match (巨|神智|能, 章|伟大|概) means an unknown fragment and the match proceeds, which is what an independent fresh-context review showed the first single-sided cut got wrong. `--apply-all` switches the check off for a run; a context rule skips it but is still risk scored, so in safe mode that match is deferred rather than applied; `--apply-domain` keeps it. Replay on three real transcripts against the pre-change engine: 8 refusals, all fragments, no correction lost; five of them were `Cloud→Claude` inside `iCloud` that the old engine auto-applied as low risk, so the recommended plain Stage 1 rerun would have written `iClaude` five times. jieba was already a declared dependency (the 4+ char real-word guard). (3) `--lookup TERM`: every existing claim on a term — dictionary rules active and disabled as FROM or TO, context rules (global plus the `--domain` list), roster variants, review-queue rows — replacing a corpus probe or raw SQL for "is there already a rule for X"; a blank term is a usage error. `--close-sidecars --output` must name an existing directory (exit 2) and the JSON reports the `dir` it searched, so a typo can no longer make it decide in the transcript's own directory unannounced. (4) Docs: `_stage2.md`/`_dryrun.md` are run-scoped outputs, promoted or discarded in the session that produced them; SKILL.md step 10 and Finalization, troubleshooting §7, the native workflow's finalize step and rung 1, script_parameters and false_positive_guide carry the new contract. 44 new tests (745 collected across `scripts/tests` and `tests`).
- **transcript-fixer** v1.33.3 → v1.33.4: the last restated resolve-window value in prose (`native_ai_full_workflow.md`, audio-wiring paragraph) now says "the resolve window"; `review_queue_dashboard.md` stays the only place the value is stated. No behaviour change.
- **claude-switch-models-setup** (`daymade-claude-code` v3.14.1 → v3.15.0): an active skill name that no discovered source checkout registers no longer aborts `sync-local-skill-sources.py`. The manifest is written against the marketplace as published on `main`, but the syncer reads working trees. On 2026-09-05 a shared checkout sat on another session's feature branch, 52 commits behind `main` with uncommitted work, so it did not register two skills merged that afternoon; a manifest edit activated them anyway, and the resulting `ValueError` made the daemon exit 1 on every trigger — `~/.agents/skills` and the `enabledPlugins` mirror queued behind it stayed frozen for every skill, and `csk` printed the traceback at every launch. `select_active_skills` now partitions the requested names into resolvable sources and unresolved names; `main()` reports the unresolved ones on stderr (under `--quiet` too, naming each scanned checkout with the branch read from its `HEAD` file — no git invocation, since the daemon runs under launchd's PATH) and syncs the rest. A link the checkout registered earlier and no longer does is pruned into `.source-sync-backups/` like any stale managed link, and a skipped name is linked on the first pass after a checkout registers it, with no manual step. Manifest shape errors (missing file, duplicates, a compatibility name outside `active_skills`, an unknown `active_marketplaces` entry) still abort before any root is touched, and a misspelled or retired name repeats the warning on every pass until the manifest is corrected. Four deterministic tests cover the partition, the `HEAD` reader (branch, detached, linked worktree), the skip-and-sync pass, the self-healing second pass and the prune direction. Calibrated on the machine that failed: the failing manifest now exits 0 with the two names and the parked branch in the warning, the previous manifest produces byte-identical dry-run output, and `--quiet` still shows the warning. SKILL.md, the architecture reference and troubleshooting.md state the new contract; the daemon keeps running its pinned copy until the pin is advanced (`DAEMON_RUNTIME_LAG`).
- **transcript-fixer** v1.33.2 → v1.33.3: documentation-consistency follow-up to v1.33.2. The `ReAnchorNeeded` docstring still described the recognised hand-applied shape by its first-cut precondition ("original gone from the whole file") and named a function that no longer exists; it now states the current condition and points at `_already_applied_verdict`. The resolve window was hard-coded as `3` in the enqueue-time hint-repair comparison and as three separate function defaults — `RESOLVE_WINDOW_LINES` defines it once — and the prose restated the value in three places; `review_queue_dashboard.md`'s fail-closed paragraph now carries the only stated value while SKILL.md and `script_parameters.md` say "the resolve window". `native_ai_full_workflow.md` 9b sends a row whose context already reads corrected to `--decision accepted` instead of `--reanchor-review`. The skill-local `CHANGELOG.md` — the only per-skill changelog in the repository, last updated at #438 while 1.33.1 and 1.33.2 were recorded only in this file — is frozen with a note pointing here; nothing is backfilled.
- **transcript-fixer** v1.33.1 → v1.33.2: two exits that recorded something other than what happened. `harvest_corrections.py` aborted the whole harvest (exit 2, nothing printed) when one candidate could not be rendered as a trap bullet — a vendor's `***` redaction mask diffed against the real word yields a FROM the bullet grammar cannot carry, since `*` is the bold delimiter and `_BOLD_TRAP` rejects it on either side even inside backticks. On a real two-hour transcript that single pair hid every other candidate; the same pair now prints 45. The noise filter drops any side with no letter or digit in any script (`str.isalnum`, so fullwidth `ＡＩ`, kana and hangul still harvest — the ASCII/URO-only `_WORD_RUN` was too narrow for this filter) or containing `*`, and a bullet that still fails the parser round-trip is reported on stderr, excluded from the output and from `--write`, and no longer aborts the run (`--json` lists it under `unrenderable`). The review queue's accept path fails closed with `ReAnchorNeeded` once the anchored occurrence cannot be located; a fix applied by hand before the verdict was indistinguishable from file drift, and SKILL.md told the agent to close such rows with `kept_original` — a verdict describing a transcript that was right as spoken, contradicting `native_ai_full_workflow.md` 9b, which reserves `kept_original` for the actual human verdict. `--decision accepted` (and `overridden`, for its override text) now recognises the one shape it can tell apart: the context recorded at enqueue reappears in the ledger-masked file with the resolved text in the exact slot the original occupied, recorded neighbours intact on both sides (width tried from 8 characters down to 2; a one-sided neighbourhood needs 3). The whole file is searched rather than the ±3-line resolve window, because frontmatter growth shifts every later line; the occurrence count of the original is not a precondition, because a suggestion that contains it (阿里→阿里云) never lets it disappear — that shape used to be re-anchored onto the fixed line and replaced a second time. It fails closed, naming the reason, when the original still sits within three lines of the hint outside the suggestion (the anchored utterance or a look-alike beside it is still garbled), when the recorded neighbourhood occurs with a third form in the slot — anywhere in the file at the width that matched, or near the hint at any width down to two characters a side, overlapping occurrences all examined — or when the edit touched the slot's neighbours; `--reanchor-review` refuses a row whose context already reads corrected instead of silently re-pointing it at a surviving occurrence and editing that one under the row's id. It records the verdict without writing and logs `already in place at the anchor — recorded without writing`; every other missing-anchor shape still raises `ReAnchorNeeded`, the `asr_note` ledger mask still applies, and `reopen` reverts nothing it never wrote. The one shape it cannot see is stated where the guard is documented: an anchored utterance deleted or rewritten past both neighbours while an identical one elsewhere reads corrected is recorded as accepted with nothing written, and a garble still in the file is re-deferred by the next Stage 1 run. The runtime messages that named `kept_original`/`skipped` as the exit for a missing original, the `ReAnchorNeeded` docstring, the dashboard reference's fail-closed and sweep paragraphs, `--help`, SKILL.md item 7, the native workflow reference and `script_parameters.md` now describe the recognised shape, its limits, the `--list-review --review-file` id source, and the `skipped`-with-note exit for a row the queue can neither re-anchor nor recognise; `kept_original` asserts the transcript keeps the original form. Twenty-four deterministic tests cover both changes, including the surviving-original, containing-suggestion, long and co-edited third-form, overlapping-neighbour and past-the-window shapes, plus pinned tests for the two shapes the check cannot see; three pre-existing `test_stage1_auto_finalize` failures and three collection errors under `scripts/tests` are unchanged on the baseline and out of scope.
- **claude-switch-models-setup** (`daymade-claude-code` v3.14.0 → v3.14.1): correct the `/advisor off` bullet added in v3.14.0. It said a session already running "keeps its advisor" and grounded that on a record still naming the session model — evidence that could not separate "running sessions keep their startup configuration" from "an absent key defaults to the session model". The transcripts do separate them: the session that ran the `off` made no further advisor calls, sessions started afterwards on the same model carry no `advisorModel` on any record, and only a *different* session that was already running kept calling the advisor. The bullet now states exactly that and tells the reader to restart such windows.
- **claude-switch-models-setup** (`daymade-claude-code` v3.13.0 → v3.14.0): `troubleshooting.md` gains a section for the advisor answering on the same model as the session. That pairing is allowed and silent — `advisorModel` is its own setting that `/model` never rewrites, and the only `/advisor` warnings are for a *less* capable or unsupported advisor — so raising the main model to the advisor's tier quietly produces a same-model advisor. The section records the two dispositions as dated observations: `/advisor <model>` writes `advisorModel` into the **global** `~/.claude/settings.json` even when run inside a project (2026-08-13), and `/advisor off` removes it from the same file without touching sessions already running (2026-09-05). `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` is named as present in the binary and unexercised, not recommended.
- **read-claude-code-history** (`daymade-claude-code` v3.12.0 → v3.13.0): the two format references now say what the JSONL looks like on disk. `session_file_format.md` documents record granularity (one content block per line; every line of one assistant message shares `message.id` / `requestId` and repeats `message.usage`, so group by `message.id` before counting calls or summing tokens), the `server_tool_use` / `advisor_tool_result` block pair written by the advisor tool with the observed `content.type` variants and a fallback rule for unrecognized ones, the optional `advisorModel` / `effort` / `apiBlockIndex` record fields, and where `agent-<id>.jsonl` actually lives. `claude_session_format.md` adds the `subagents/workflows/<wf-id>/` layer (transcripts, `.meta.json`, `journal.jsonl`) that top-level `projects/*/*.jsonl` globs never reach, and marks its block-type list as non-exhaustive with a pointer to the schema file. Motivation: a line-oriented count and a `message.id`-grouped count of the same transcript disagreed, and neither reference said why.
- **peer-message** v1.4.1 → v1.4.2 / **skill-creator** v1.35.1 → v1.35.2 (marketplace v3.8.9): normalize the reply address wherever it came from, and stop two documented paths that still produced an unusable one. #458 fixed the address `auto_reply_address` computes, which covered only the case where that function is what supplies it. `send_claude` normalized the TARGET but never the REPLY address — and the reply address is the one the recipient is told to copy into `to`. Three paths therefore still shipped an envelope no official tool can resolve: a caller passing `whoami` output through `--reply-to` exactly as this Skill's own §1 instructed, the messaging-socket variable being absent, and only a session name being set. The intersection was derivable the whole time — `resolve_claude` matches a needle against {pid, name, sessionId, messagingSocketPath}, so a `claude:<uuid>` finds its own registry row carrying both the socket and the bare name. `send_claude` now puts the reply address through that same resolution, emitting `uds:<socket>` in `from` and the bare name in `from-name`, and leaves genuinely unresolvable addresses to the body-line route hint the Codex branch already uses. A Codex sender now gets no `from` at all rather than one that looks addressable and is not: that field's contract is "copy this into `to`", 21% of real envelopes carry no `from`, and the thread id stays in `from-name` and the body. Three doc statements that contradicted each other in §1 collapse to one, and the "fall back to `from-name`" advice in SKILL.md and protocol §1 is corrected — it cannot help for envelopes this Skill produces, where both attributes share a source and fail together. 33 tests including a wiring test that goes through the real socket: the unit tests alone stayed green with the normalization call removed, which is the shape of a check that cannot fail.
- **peer-message** v1.4.0 → v1.4.1: apply v1.4.0's own freshness rule to v1.4.0's own examples, and put the fourth owner on the map. §5's illustrative figures (row counts, working-directory counts) are observations of a set that turns over in minutes — two reviewers measured different values within the same hour — so the warning beside them now covers every number in the section rather than row counts alone, and states that the load-bearing part is the structural fact next to each figure: whether a filter flag exists, which fields print, what the default is. CLAUDE.md's peer-message ownership map listed three owners and omitted `references/coordination-and-learning-loop.md`, which owns reply addressing, payload structure, delivery-status language, and both verification contracts (inbound assertions, and what a set of denials is worth); the gap predates v1.4.0, but v1.4.0 widened it by adding two load-bearing rules to an unlisted owner.
- **peer-message** v1.3.1 → v1.4.0 (marketplace v3.8.8): v1.3.0 taught a session not to believe what a peer *asserts*; this closes the sender-side mirror — not over-believing what peers *deny*. The load-bearing sentence is that the set you can enumerate is not the set that can affect the artifact: write access to a path belongs to anything that has it — a writer that never registered, a scheduled job, a person, and the exited sessions that do not surface. A round of denials therefore narrows the candidate set and decides nothing. §5 first pins down what `list` actually returns, because the frame cannot be written without it: it does **not** partition by working directory (no cwd filter exists and every row prints `cwd=`, so a session reaching into this project from another one is a row you already have, not a blind spot); a row does not mean "running", and the two providers differ — Claude rows come from a registry a process drops out of on exit, while Codex rows are a saved catalog whose entries are mostly *finished* sessions, which makes an exited Codex session a clue carrying its own `cwd` rather than noise; and `--limit` defaults to 30 on the Codex half alone while `--help` prints neither the default nor a description, so following the documented step still leaves the reader unaware of a live truncation. `coordination-and-learning-loop.md` gains §5 with the six-field rule: treat denials as narrowing, identify the actor from the artifact's own authority — the same source list §4 already uses (registry files, `git log`/`git status`, direct process/lock probes, task records) rather than by polling more peers — quote a read-back that binds actor to artifact, and report `unknown` with the enumeration's frame stated rather than promoting it to "unowned". §2 gains the freshness clause its `evidence` field was missing: when the subject is mutable, one observation is not a fact, so re-observe before asserting and report "still changing" instead of a value that expired between measuring and sending; an honest timestamp on a dead fact still gets acted on. SKILL.md's trust boundary gains the inverse of its existing rule — a conclusion derived from peer replies must not enter a user-facing report as established fact, because that crossing is where an unverified inference acquires maximum authority. Distilled from a real cross-session ownership misjudgement in which every polled session truthfully denied authorship and the actual writer was never in the polled frame; §5 also names the second half of that error, where "I cannot find the owner" was converted into "the owner is a dead session, so this is disposable" — neither step holds, and an exited writer's in-flight work is exactly what someone else may be waiting on. Two rounds of independent fresh-context review shaped it: the first found that the mandatory frame-reporting instruction could not be executed because the text described `list` in ways three live runs contradicted, and the second caught this changelog entry still restating the corrected claim, an "exited sessions are unreachable" line that the Codex saved catalog falsifies, and an example row count that the section's own freshness rule would have rejected. The description is unchanged: it already sat at 1023 of its 1024 characters, so a new trigger phrase would have had to delete an existing one.
- **transcript-fixer** v1.33.0 → v1.33.1: the cold-read completion contract gains the recovery ladder's first rung — a background reviewer past its ETA gets ONE SendMessage nudge before any fresh-retry or salvage, resuming from its own transcript at zero rework cost (measured 2026-09-04: three background reviewers went silently idle; one nudge revived all three).
- **skill-creator** v1.35.0 → v1.35.1 / **peer-message** v1.3.0 → v1.3.1 (marketplace v3.8.7): sharpen Case 23 with the boundary work that keeps it from becoming a tax, then apply its own precondition back to the skill it came from. The rule is now stated as an error-interpretation rule rather than a pre-call gate — on the happy path it costs nothing, and it only engages once a not-found-shaped error actually returns; its trigger is a conjunction of three conditions all decidable from context without probing, and it is phrased as a producer-side question ("can your consumer resolve what you emit?") because the consumer-side phrasing fires everywhere. The not-found clause gains three terminal exits, none of which is trying another address, and the third verdict `unresolved` that lets an agent stop instead of searching to decide between exists and absent. T1 gains its three preconditions, of which the load-bearing one is that a handle destined for storage must not be cast: names are mutable and collidable, canonical ids are not — cast for use, store the canonical, carry both when the envelope has room. Applying that to peer-message found the reference implementation breaking it in one branch: when a session name is set, `from` is a pid-derived socket locator and `from-name` is a mutable display name, so an archived envelope carries no stable route back to the sender. The canonical session id now rides the body's first line whenever neither attribute already carries it. Two deterministic tests cover the added and the not-duplicated branch; removing the line turns one red.
- **skill-creator** v1.34.0 → v1.35.0 (marketplace v3.8.6): add Case 23 and the identifier-space check it produced. A sibling skill wrapped an official tool and a bundled script for one job, told authors to prefer the official route, and had the script write its own address space into the field the host tells recipients to copy back. The first fix was documentation — a shape table, a conversion recipe, a warning — and it shipped to a public repo before three independent audits found the premise came from 2 of 541 real samples, the conversion's fallback read the same registry as its lookup (so a miss could not be rescued), the stated acceptance evidence still passed when the lookup returned a form the official side rejects, and the reverse direction was never covered. The decisive finding is that documentation could not fix it at all: the recipient may never have loaded the skill. Case 23 records the three-tier rule that replaced it — produce the identifier in the consumer's form; when the two spaces do not intersect, make the route travel with the identifier; write conversion tables only when neither end is yours — plus the not-found taxonomy that keeps it from degenerating into never trusting a negative, and a trigger condition that keeps it from firing on single-route skills. SKILL.md's third-party-overlap bullet, the line that sets the trap by saying to prefer the official tool, now carries the pointer.
- **skill-creator** v1.33.1 → v1.34.0 (marketplace v3.8.7): discipline #6 now says what
  "differently-shaped" means. The rule already required re-running a check in a different
  shape before trusting it, and v1.33.0's own reachability check was "confirmed" by a
  second script that asked the identical predicate — both tested whether the full path
  `references/<name>` appears in SKILL.md, so both were blind to the same healthy form
  (a `### references/` section listing files by bare name) and a correct skill was
  flagged. Two agreeing numbers look exactly like corroboration. The added paragraph
  names the test: say out loud what question each side asks, and if it is the same
  sentence you have one instrument, not two. Repository CLAUDE.md gains the companion
  rule for shared checkouts — compute a version bump from `git show origin/main:<path>`,
  never from the working tree, which may already carry a parallel session's in-flight
  bump while every status-shaped signal stays green.
- **peer-message** v1.2.1 → v1.2.2 (marketplace v3.8.5): close the one direction v1.2.1 left open. A Codex sender has no address the official Claude tools can reach — that is a fact about the two products, not a defect — so unlike the Claude case there is no intersection form to substitute into `from`. The receiving Claude session is therefore given an instruction by its own host (copy `from` into `to`) that cannot work, with nothing telling it why. Since the host parser fixes the attribute set, the envelope now carries `[reply: peer.py send codex:<id>]` on the body's first line, alongside the message-id that already rides there. Claude senders are unaffected: their `from` is directly usable by the official tools, and adding a hint would push work away from the official channel for no reason. Two deterministic tests cover both branches; removing the hint turns one red.
- **peer-message** v1.2.0 → v1.2.1 (marketplace v3.8.4): correct the reply address-space contract v1.2.0 shipped, and move the fix from prose to the envelope producer. v1.2.0 asserted that the envelope `from` is a `claude:<session-uuid>` form and that the official peer tools accept only bare names. Both are wrong. A sweep of the local transcript corpus found `from` is `uds:<socket-path>` in the overwhelming majority of real envelopes and a session-UUID in a negligible minority; the generalization was drawn from that minority. Live testing confirms the official tools accept `uds:<socket-path>` (the form the host itself emits) and bare names, and reject `claude:<uuid>`. The v1.2.0 guidance also carried three defects of its own: its fallback ("on a lookup miss, use peer.py") is a dead end because `list` and `send` read the same registry, so a miss means exit 3 rather than a second chance; its acceptance check (`reachable` is true) still passes when `list` yields `claude:<pid>` for an unnamed session, which the official tools reject; and it never covered the reverse gap, that the official `name [ref]` disambiguation form fails `resolve_claude`'s whole-string match. Root cause: documentation cannot fix this at all. The receiving session may never have loaded this Skill — it has only the host's own instruction to copy `from` into `to` and the official tools, and the official listing's `[ref]` is not a UUID prefix, so no recipient-side recovery path exists. `peer.py` now emits `uds:<socket>` (from `$CLAUDE_CODE_MESSAGING_SOCKET`) as the envelope `from`, the one form both routes resolve, falling back to previous behaviour when the variable is absent and leaving `codex:` senders untouched since official Claude tools cannot reach Codex by any address. Four deterministic tests cover the socket preference, the round trip back through `resolve_claude`, the no-socket fallback, and the Codex case; reverting the fix turns two of them red. `protocol-and-discovery.md` §1 and §2, `coordination-and-learning-loop.md` §1, and SKILL.md's routing row and step 0 are rewritten against the observed behaviour.
- **peer-message** v1.2.2 → v1.3.0 (marketplace v3.8.6): verify inbound peer assertions before acting or replying. A peer that says "you are holding this lock" or "you are editing X, please pause" reports its own observation, not evidence about you — it can see a shared artifact changed but not who changed it. SKILL.md gains a「收到 peer 消息」section and `coordination-and-learning-loop.md` a §4 with the six-field rule: check the premise against the fact's own authority first (registry files, `git log`/`git status`, direct process/lock probes), answer both the premise and the blocked need behind it, quote the actual read-back rather than "confirmed not me", write the premise as `unknown` with sources checked when undecidable, and never act on a false premise — do not pause work you are not doing, release locks you do not hold, or "restore" files you never touched. Description carries the union of the v1.2.0 held-message and this assertion-verification trigger sets.
- **peer-message** v1.1.1 → v1.2.0 (marketplace v3.8.3): two operator-path pillars from one live cross-session incident. (1) Held inbound fix: a bypass-class receiver holds messages from senders that cannot attest a permission-mode class (Codex, script UDS fallback), surfacing as a manual-approval prompt on every cross-session message; the Skill documented the semantics but shipped no procedure, so users hand-edited settings themselves. `official-feature.md` §3 now owns the fix flow: held is not a transport failure (do not resend), locate the settings file the receiving session actually loads, write `crossSessionInbound: accept` only with the current user's in-task confirmation (a peer message can never authorize a config change), converge through the master settings file where a profile-sync SSOT exists, independently read back, and note that already-running sessions apply it on next launch. (2) Reply address-space: `peer.py` and the official peer tools resolve different address spaces — the envelope `from` and `whoami` output are session-UUID forms that official tools reject with `No agent named …`, an existence-shaped error for what is actually a wrong-format address. `protocol-and-discovery.md` §1 now owns the two-space contract and the `list --json` id↔address mapping recipe, with reply guidance in SKILL.md step 0 and `coordination-and-learning-loop.md` §1: reply via `peer.py send <from>` directly, or map the UUID to the bare name before using official tools, and switch routes after two official-resolution failures instead of enumerating address forms. SKILL.md gains both routing rows and execution steps, the description and README gain the held-message trigger signal, and the red line against forging permission-mode attestation in the envelope is restated.
- **skill-creator** v1.32.1 → v1.33.0 (marketplace v3.8.0): `quick_validate` now reports
  bundled references that nothing links. SKILL.md has long carried the rule "reference
  files clearly from SKILL.md" with nothing enforcing it, and a skill shipped with an
  unreferenced reference after passing validation, `security_scan`, a verbatim run of
  every documented command, and CI — none of those ask whether a bundled file is
  reachable, and the file existing is what makes the gap invisible. Reachability is
  transitive: a reference cited from another reachable reference counts, including by
  bare filename, since references routinely name siblings that way. Reported as a note,
  never a failure — some unreferenced files are deliberate (an author-facing template is
  not runtime guidance) and a gate that fails on those gets bypassed, which turns it off
  for the skills it was built for. Calibrated against all 104 committed skills before
  arming: 6 flagged, 0 validation failures. The first version required the full
  `references/<name>` path in SKILL.md and flagged a skill that lists each file by bare
  name under a `### references/` heading with a line on what it holds — the exact form
  the guidance asks for. The initial calibration missed it because the confirming
  measurement applied the same path-only rule; two instruments sharing a blind spot
  agreeing is not calibration. Re-checked with a different rule (does the filename appear
  in SKILL.md at all), which isolated the one false positive from the six real ones.
  Nine tests cover the directly-linked, bare-name-in-SKILL.md, transitive,
  bare-name-between-references, nested-directory, non-markdown and no-references cases.
- **tibo-reset-codex** (v1.3.1 → v1.4.0): fix a multi-account exclusion check that was
  structurally incapable of failing, and stop reading "clean +7d" as proof of a reset.
  §2 told the agent to exclude multi-account interleaving by counting `account_id`s in
  `~/.codex/auth.json` and entries in `~/.cc-switch/cc-switch.db` — but auth.json stores
  only the currently logged-in account and cc-switch never sees a manual `codex login`,
  so both probes answer a historical question with current state and always return "one
  account". On a machine demonstrably rotating two Pro accounts, both reported single-
  account and the whole attribution came out inverted. Replaced with a three-layer check
  that can actually fail: (A) `auth.json` `last_refresh` aligned against the zero-out
  interval plus the decoded `id_token` identity, (B) the cc-switch `providers` table
  (not `profiles`, which was empty on the observed machine) with per-entry `id_token`
  decoding, (C) an anchor back-jump scan derived from rollout alone — the only layer
  still lit when the user switches accounts by hand. Reordered the concurrent-session
  dedup rule to run *after* the back-jump scan: the records it discards are where the
  decisive evidence lives (`used_percent` rising, which quota can never do). The two-
  shape anchor taxonomy becomes three shapes, with "clean +7d" explicitly demoted from
  "button reset" to "reset **or** account switch, indistinguishable on this axis alone"
  — reading it the old way turned 8 deduplicated account rotations into "8 silent
  resets" on the observed machine. Adds trap 4: `sessions/<Y>/<M>/<D>/` directory dates do not bound
  timestamps, because a session running past midnight keeps writing next-day timestamps
  into the previous day's directory — scanning N date directories silently under-samples
  and drops exactly the long-session interleaving that multi-account rotation produces
  (same one-minute window: 9 rows across 7 directories vs 67 across 9). The bundled
  rebuild script now decouples directory scan from the time window, reports the back-jump
  count, and labels each zero-out with its pre-drop usage peak. Back-jump detection was
  calibrated both ways on real rollout data: it catches the `used 0%→82%` account switch
  and returns 0 on a known single-anchor-chain period, with a 5-minute threshold added to
  suppress the false hits produced by the documented second-level `resets_at` drift. All
  four documented commands were extracted verbatim from SKILL.md and executed.
  An independent fresh-context review of §2's executability then found nine issues, all
  fixed and re-verified: the rebuild script crashed with an unguarded `rows[0]` on an
  empty `~/.codex` (a state §2 elsewhere treats as meaningful) and now exits with an
  explanation; the back-jump `used%` comparison read the *first* row of the previous
  anchor run instead of the strictly adjacent snapshot, which printed one real transition
  as `0%→0%` when it was `100%→0%` — the "quota never un-spends" invariant only holds
  between adjacent rows, so the loop now compares adjacent rows; the three-layer gate
  claimed three clean layers proved a single account, when all three are positive-only
  detectors that can be simultaneously silent during exactly the rotation the section
  calls its most expensive error, so it now concludes "no positive evidence" and routes
  to the one question that can settle it; the A layer was labelled decisive though
  `last_refresh` is indistinguishable from a token renewal on the observed data
  (`iat` equal, `exp` exactly +3600s) and covers at most one of ten zero-out intervals;
  the B-layer rule counted an API-key provider row (`auth_mode=None`, `email=None`) as a
  second account and now filters to `auth_mode='chatgpt'`; the prose pointed at
  anchor-keyed dedup as the place the decisive record is discarded, which is structurally
  impossible since dedup merges same-anchor rows, and now points at the back-jump output
  where the record actually appears; the C-layer middle band had no rule; run order was
  unstated although the A layer needs an interval only the script produces; and the
  "widest adjacent gap 1h56m" figure was stale (measured 9.65h, with 39 gaps over the
  600-second `clean` tolerance).
- **claude-switch-models-setup** (`daymade-claude-code` v3.7.14 → v3.7.15): close the
  enabledPlugins write-back hole that erased installed skills. `claude plugin
  install/enable` writes the new key into the ACTIVE profile's settings.json only; the
  next `claude-plugins-sync.py` pass then mirrored the default profile's map wholesale,
  wiping the key from every profile — the mechanical root cause of recurring "my skills
  disappeared" losses. The sync now adopts profile-only enabledPlugins keys back into
  the default settings.json before mirroring: consistent values only; cross-profile
  conflicts are kept per-profile behind a standing warning instead of being silently
  overwritten, and a corrupted profile settings file now skips its own mirror instead of
  crashing the whole pass. Adds `skill-install-audit.py`, a read-only reconciliation
  across the local marketplace registries, installed_plugins.json, enabledPlugins, the
  codex-active-skills.json manifest, and the real `~/.agents/skills` links (sections:
  ENABLED / INSTALLED_DISABLED / INSTALLED_NO_KEY / REGISTERED_NOT_INSTALLED /
  ORPHAN_INSTALLED / PROFILE_ONLY_RISK / MANUAL_LINK_RISK / CODEX_UNLISTED_ENABLED).
  Deterministic fixture suite registered as `scripts/claude-plugins-sync.test.py`
  (27 checks, tmp-dir isolated via CLAUDE_BASE_DIR / CLAUDE_PROFILES_DIR).
- **git-safety-net** v1.16.0 → v1.16.1: closes a discrimination gap in the
  eval suite's first negative case. `evals.json` eval 9 asserted that ordinary
  edit-and-commit work draws no forensic sweep, but it did so by enumerating
  three commands — so an agent that reached for `git log -g`, which inspects
  the same reflog, would have passed a check written to catch exactly that
  over-triggering. The assertion now names the category (any command searching
  for lost or unreferenced work) and keeps the three commands as anchoring
  examples, which is what a grader with no knowledge of this Skill can still
  match against.

  Found by the second independent reviewer and deliberately reported outside
  its own scope: it was judging assertion *judgeability*, and noted this as a
  weakness of a different kind rather than folding it into its findings. Kept
  as a separate change so the axis boundary stays visible.
- **git-safety-net** v1.15.2 → v1.16.0: adds the Skill's first behavioural eval
  suite and trims one paragraph of Mode D.

  `evals/evals.json` holds ten scenarios. Eight are failure shapes measured
  first-hand rather than imagined: an empty `git branch --contains` for work that
  did land (a squash merge rewrote the SHA); a sibling session's commit adopted
  onto your branch, invisible to `git status` and to every per-commit check; a
  `git rebase --onto <base> <foreign-sha>` that silently discards the commits
  before the foreign one and exits 0; `merge-base --is-ancestor` answering 1 for
  squash-merged work and 128 for a SHA it does not have; an `ls-remote > file`
  emptiness probe that reports "gone" for any failure written to stderr; an
  autostash that a conflicted rebase leaves outside `git stash list`; a shared
  index carrying another session's staged files; and a `git worktree remove` that
  refuses over untracked files, where forcing past it destroys content the object
  store holds no copy of while the branch's commits would have survived anyway. The remaining two are negative: an
  ordinary edit-and-commit in a clean solo repo, and a week-old stash in a
  fully-pushed one, must not draw an audit, a rescue ref, or an alarm — the
  Skill's own boundary is forensics, not routine work, and a check that fires on
  healthy input trains its reader to bypass it. Assertions are written against
  intent rather than a named script, so an agent reaching the same outcome by
  another sanctioned route passes; each is a statement a grader holding only the
  session transcript can mark true or false.

  Separately, the Mode D paragraph on the base-SHA verify line moves its measured
  detail — the `HEAD..HEAD` degeneration, the contrasting `fatal: Invalid
  revision range` at exit 128, and the full rationale for recording the base at
  branch creation — into `prevention_practices.md`, newly routed by two
  `§`-pointers. The directional fact the guard exists for, that the empty case is
  the silent one, stays inline: a reader who cannot see why the guard matters
  deletes it as noise.
- **daymade-audio** v1.32.5 → v1.33.0 (`asr-transcribe-to-text`): replaces the stale “Minute URL always ends the job” rule with explicit outcomes. Upload-only still stops at the URL; a request that names upload but no downstream result lands at resumable `outcome_pending` instead of forcing a guess; transcript-only waits for a readable Feishu transcript; project delivery hands preprocessing into `meeting-ingest` and cannot finish until routing, full correction, project indexes, verified Git handoff, and the pushed delivery receipt are complete. A later downstream request preserves the same `minute_token`/URL and resumes instead of re-uploading.
- **git-safety-net** v1.15.1 → v1.15.2: give the references section-level
  routing. Measured before the change: of 39 reference sections, only 11 had any
  inbound pointer naming them — `recovery_playbook.md` had exactly one, so its
  recovery ladder, the rung an agent actually needs when work has gone missing, was
  reachable only by opening a 223-line file and scanning. SKILL.md now cites the
  specific `§ <section>` at each decision point: Mode A routes by symptom to the
  ladder rung that handles it, Mode B names the at-risk definition and the pinning
  rationale, Mode C distributes the six merge-verification topics to the sentences
  that raise them, and every Mode D bullet carries the `§` name of its full
  treatment. 37 citations; all resolve, checked with a negative control. One
  measured gap remains by design: `merge_verification.md` was already the
  best-routed file and needed the least.
  The change is routing, not rules. The regression audit flagged 18 units whose
  wording moved; each was classified `preserved_or_moved` against a needle taken
  from the changed file, and the 31 load-bearing phrases across the nine reworded
  paragraphs were verified still present by literal match with a negative control.
  One illustrative example ("an orphan from a rebase") that the rewrite had dropped
  was restored rather than argued away. No command, condition, verdict, or stop
  point changed, and the 63-test suite still passes.
- **git-safety-net** v1.15.0 → v1.15.1: put mechanical judges under the three
  scripts that had none — and they were the load-bearing three.
  `git_verify_branch_merged.sh` is what the Skill's own rules call the only check
  that was right every time, what Mode E rung 1 accepts as deletion-grade evidence,
  and what Mode C routes "is everything merged?" to; it is referenced six times and
  had zero tests. `git_loss_audit.sh` (the Mode B evidence path, required before any
  rebase or branch-delete) and `git_preserve_danglers.sh` (the only script here that
  writes refs) were likewise untested, while the three scripts that did have tests
  were the lower-stakes ones. 27 tests close that inversion. No runtime behaviour
  changes: not one line of any script was edited.
  Every expectation was calibrated by running the script against the fixture first,
  which is how two wrong assumptions were caught before they became tests — deleting
  a branch does not create a dangling commit (the reflog keeps it reachable until
  expired, so a naive fixture would have asserted against an empty run and passed for
  the wrong reason), and a branch whose content is a textual subset of the base's is
  still correctly reported UNMERGED, because containment is decided by a three-way
  merge rather than by line presence.
  The suite was then mutation-calibrated rather than trusted for being green: breaking
  the containment check turns six tests red, restoring the `set -e` abort that the
  script's own comments record as a past regression turns the conflict test red,
  inverting the local-vs-remote ref precedence turns three red, widening the audit's
  exit 1 to cover a routine stash turns the two alarm-fatigue tests red, and making
  the pinning script delete a ref or use the wrong namespace turns the
  non-destructive-invariant test red. One mutation was NOT caught — removing the `--`
  pathspec guard leaves every test green, because the script resolves to a fully
  qualified ref before the diff — so that test was renamed to what it actually proves
  and the gap is stated in its docstring instead of being implied away.
  The content-containment expectations are skipped below git 2.38, where
  `merge-tree --write-tree` does not exist and the script deliberately degrades to a
  conservative verdict; failing a healthy older runner would teach people to bypass
  the suite.
- **git-safety-net** v1.14.0 → v1.15.0: add the inverse of the shared-checkout
  failure the previous release covered. v1.14.0 handles *your uncommitted work*
  being stranded on *another session's* branch; this adds *their commit* landing
  in *your branch's history*, where it ships inside your PR. Every check the skill
  already prescribes reports green on it, because the foreign work left both the
  working tree and the index the moment it was committed; only the branch's
  cumulative range against its recorded base reveals it, so that read-only
  comparison becomes a pre-push/pre-PR step, with the accidental tell named — a
  validator or CI job reporting a wider blast radius than you worked on. Repair
  is routed through the contracts this Skill already carries rather than restated
  inline: finding a foreign commit is itself evidence another writer was in the
  checkout, so the standing quiesce/ownership rules apply before anything else,
  and the sequence that follows is the existing one — Mode B evidence path,
  `backup/pre-rewrite` at your own tip per "Snapshot before any history rewrite",
  a separate rescue ref for their commit, then the rebase, with either ref retired
  only under Mode C/E deletion-grade evidence. The base SHA is recorded at branch
  creation because recovering it later reads a cached remote ref whose refresh is
  a gated fetch. Three measured instrument corrections ship with it: `--contains`
  reports zero refs for a commit whose work already merged under a
  squash-rewritten SHA; hash-equality comparison of whole files against the
  integration branch reports differences as soon as the branch moves on; and
  `merge-base --is-ancestor` answers only where the merge preserved the commit, so
  under squash merges its exit 1 means "not this object", not "not landed" — the
  probe that survives either strategy is a content grep carrying a known-absent
  control line; `--is-ancestor` also has a third exit code, 128, for a SHA this
  repository does not have — a different answer from 1. The prescribed rebase is
  `--onto "<foreign-sha>^"`, never `--onto "$base"`: the latter replays
  `<foreign-sha>..<branch>` and so discards the author's *own* earlier commits when
  the foreign one is not first after the base, silently and with exit 0 (measured
  on an `A(yours) → F(foreign) → C(yours)` branch: `A` vanished). Because a rebase
  exit code cannot report that, re-running the detection is now a required step,
  and the already-pushed case routes to the existing force-push contract instead of
  inventing one. Troubleshooting also gains the lost-receipt entry (a moved remote
  ref is not proof *your* write landed when concurrent sessions are merging) and a
  probe-shape entry: `git ls-remote > f; [ -s f ]` is wrong in **both** directions
  depending on one redirection detail — bare `> f` leaves 0 bytes because Git
  writes the failure to stderr, so a live branch reads as "already gone", while
  `2>&1` writes 155 bytes and a deleted branch reads as "still there";
  `--exit-code` separates matched (0), no match (2), and probe failure (128). The
  `rebase.autoStash` hazard is documented from measurement: on a conflicted rebase
  a sibling session's uncommitted work leaves the working tree while
  `git stash list` shows nothing, because an autostash is not a stash entry.
  Every probe that ships carries the guard that stops it failing green: an
  unresolvable base turns `"$base"..HEAD` into `HEAD..HEAD` and prints nothing at
  exit 0, indistinguishable from "clean", so the base is verified first; Git cannot
  attribute commits in a shared checkout (both sessions write the same author), so
  "which are mine" is a recorded fact and a stop condition, not a query; the
  content grep needs its diff `+` stripped and its path checked, since a renamed
  file and an unstripped needle both return 0 with the control line passing;
  `--contains` stops reporting zero the moment the rescue ref exists, so the
  reading must exclude it; `ls-remote` takes a fully-qualified `refs/heads/<branch>`
  because a bare name also matches a same-named tag; and `cat-file -e` returns 128
  for a mistyped branch and a symlinked path as well as a missing file.
  Every exit code, both failure directions, and each of the three wrong
  instruments were measured, not recalled.
- **tibo-reset-codex** v1.2.2 → v1.3.1: add the missing local-account
  forensics leg and close the announcement path's structural blind spot,
  both exposed by the 2026-09-01 live run. The skill previously could only
  point the user at the product usage page or `/status`; it now reads the
  `rate_limits` snapshots in `~/.codex/sessions/**/rollout-*.jsonl`, which
  are the same evidence tier but scriptable, historical, and precise enough
  to bound a reset to a minutes-wide interval. Three traps that return
  plausible wrong answers without erroring are documented with the filters
  that defeat them: `primary` does not always denote the weekly window,
  `limit_id` includes a permanently-zero decoy bucket that manufactures
  dozens of phantom resets, and `resets_at` drifts by seconds on every
  snapshot so it cannot be used as a reset predicate. Window-anchor shape
  now distinguishes a button-press reset (clean +7d) from a quota
  reconfiguration (anchor moved into the past), and concurrent sessions are
  noted as emitting the same reset twice. On the announcement side, Radar
  indexes only @thsottiaux and therefore cannot see @ChatGPT or
  status.openai.com — half the predictive signal, since resets fire on
  outage compensation as well as milestones — so the outage line and
  codexrunway.com join the channel list. Both new scripts were executed
  verbatim as a reader would paste them; that is how the status-page command
  was found to need built-in retries rather than a bare call.
- **peer-message** v1.0.1 → v1.1.0: add an operational coordination and learning contract distilled from post-release Claude/Codex use. A read-only `whoami` command gives parent tasks an exact reply address before delegation; worker reports correlate the incoming task through `in_reply_to`; multiline or data-rich reports use the CLI's UTF-8 message-file entry; and bounded verification stops at transport, receiver queue/history, explicit reply, or independently verified task completion instead of collapsing them into “delivered.” The evidence-gated improvement loop admits layer-bounded sender errors as well as receiver records, task outcomes, deterministic tests, and user corrections, routes each failure to its owner, requires executable When/Do/Evidence/Missing/Do-not-infer/Stop rules, and separates bounded Skill evolution from unsupported autonomous RSI. Existing transports, receipts, exit codes, and authorization boundaries are unchanged.
- **terraform-skill** v1.0.1 → v1.1.0: replace deploy-and-pray advice with a release-safety contract grounded in current Terraform, Docker Compose, Caddy, and Cloudflare behavior. Staging and production now share one required-key schema; every runtime writer must validate the exact candidate bytes, full Compose-rendered environment, and immutable image before live mutation. Saved plans are bound to source/artifact provenance, staging receipts follow live verification, and production authorization remains a distinct last-reversible-point decision. Correct the prior claims that Compose ignores shell overrides, `terraform validate` proves environment/runtime behavior, token shape proves Cloudflare capability, and disabling `set -e` is the right way to preserve failure diagnostics.
- **macos-cleaner** (daymade-macos v1.0.0 → v1.1.0): add a targeted Chromium code-sign-clone branch and current-user-scoped analyzer that separates active, inactive, and unknown children, binds approved batches to a candidate SHA, preserves explicit exclusions across activity races, and supports a final read-only recheck while the exact-path deletion prompt waits. Rank nominal APFS path accounting separately from expected physical release, require df readback for actual reclaimed space, and stop the legacy deletion helper from silently shrinking a changed batch, labeling measured totals as physically “freed,” or continuing after the first failure.
- **tibo-reset-codex** v1.2.1 → v1.2.2: fold in the 2026-08-31 live run.
  The Radar timeline command now prints each event's `url` inline, removing
  the second lookup before reading the original post; the
  celebration-as-reset rule gains its full next-day fulfillment chain
  (8-29 "moved to tomorrow" → 8-30 12:24 PT "will land at 6pm PST" →
  19:34 PT "hit 25M active users…we have now reset usage for all paid
  subscriptions"), and 25M joins the milestone list; landed-confirmation
  evidence now lists both observed phrasings ("has landed" and "we have
  now reset usage…"). Independent review caught two first-draft defects —
  an invented "<24h" duration contradicting the measured 29h10m span, and
  an order-inverted stitched quote — both fixed and re-verified pre-ship.

### Fixed
- **daymade-audio** v1.34.1 (asr-transcribe-to-text): `align_speakers.py` no longer cuts a turn inside a Latin word. Char times inside a word are interpolated between whisper anchors and diarization edges do not fall on word boundaries, so a pause or speaker change measured mid-word is boundary jitter; it is now deferred to the next word boundary and the word stays with the turn it started in. A 49-minute English talk went from 53 words cut in half (`honor t` / `o introduce`, `Y` / `eah`) to 0; four regression tests added. Docs: `--no-diarization` drops every timestamp (now stated where the flag is introduced), unattended batches run one file per invocation because a deterministic failure exits the whole multi-input run, and `HF_HUB_OFFLINE=1` keeps the whisper timing leg off the network when the proxy tunnel flaps.
- **deep-research** v2.4.0 → v2.4.1, **cli-demo-generator** v1.0.0 → v1.0.1,
  **youtube-downloader** v1.1.0 → v1.1.1, **skill-creator** v1.33.0 → v1.33.1,
  **claude-switch-models-setup** and **read-claude-code-history** (both
  `daymade-claude-code` v3.7.15 → v3.7.16, marketplace v3.8.1): resolve every bundled
  reference the new reachability check surfaced. Five were live knowledge nobody could
  route to and are now linked with a line on when to read them — the VHS tape-file
  syntax, the yt-dlp failures that look like something else, the reference-authoring
  template, the student-facing setup walkthrough, and the `~/.claude/` layout plus
  `compact_boundary` markers (distinct from the message-schema reference beside it,
  which was already linked; both were updated the same day and only one got wired up).
  One was deleted: `deep-research/references/V6_1_improvements.md` was a version-history
  file whose load-bearing rule — circular verification versus exclusive information
  advantage — already lives in SKILL.md's own accessibility table and in
  `references/source_accessibility_policy.md`, leaving a changelog of the kind that
  belongs in this file rather than in a skill. Repository now reports 0 unreachable
  references across all 104 committed skills. Also refreshes **excalidraw-use**
  v1.0.1 → v1.0.2 (marketplace v3.8.2): its security-scan marker's content hash went
  stale when SKILL.md changed in the previous release and the re-scan was not staged,
  which would have blocked the next packaging run.
- **excalidraw-use** v1.0.0 → v1.0.1 (marketplace v3.7.1): link
  `references/scene_file_format.md` from SKILL.md. It shipped unreferenced, so the
  executing agent had no route to it — an unlinked reference is unreachable at runtime
  no matter how good its content is, and this one carries the field-by-field scene
  breakdown behind `--template-from`. Caught by checking that every file under
  `references/` appears in a SKILL.md link, which is worth running before any skill
  ships. Regression audit against the merge commit confirms the three untouched
  references and four scripts are byte-identical; only SKILL.md changed.
- **git-safety-net** v1.13.0 → v1.14.0: replace the over-broad “one worktree per
  concurrent session” prescription with an authority-first, single-writer shared-checkout
  contract. Mode D now treats worktrees as explicitly authorized named exceptions, preserves
  narrow higher-authority stash contracts instead of declaring a universal ban, stops every
  repository mutation while another writer is active, freezes handoffs and merges by exact
  local/remote SHA, makes completion an AND gate over session-owned bytes,
  remote containment, and attributed residuals, and keeps cleanup in separately authorized
  Mode E. The prevention reference now counts any scheduled job that can write the checkout as a
  writer even when paths are disjoint: an idle process snapshot is not a lock, so existing
  coordination must quiesce it and transfer exclusive ownership before Git mutation; stopping,
  leasing, or rescheduling automation remains a separate design decision. The reachable Mode E
  convergence workflow now applies the same gate to alternate-index commits, ref/bundle writes,
  push/PR, and fetch; parallel verification agents receive frozen SHAs and never move
  remote-tracking refs. Bundle-relative helpers are no longer presented as commands assumed to
  exist on `PATH`.
- **peer-message** v1.1.0 → v1.1.1: stop Claude receiver-evidence verification from collapsing unreadable transcripts or malformed matching JSONL into ordinary `unverified`. The verifier now keeps scanning other candidates and later lines for valid enqueue evidence, but fails loudly if no valid match exists and any evidence read/parse error occurred; a clean, fully readable miss remains `unverified`. Four deterministic regression cases cover read failure, malformed matching JSON, later valid evidence, and the healthy-miss control.
- **peer-message** v1.0.0 → v1.0.1: make documentation ownership executable instead of duplicative. `SKILL.md` keeps only routing, stable prerequisites, safety, and owner pointers; `peer.py --help` owns CLI syntax; the protocol reference owns addressing, envelopes, receipt, exit, transport, and verification semantics; the official-feature reference owns volatile product interfaces and inbound mechanics. README/README.zh-CN and `CLAUDE.md` point to those owners, while the changelog and private review stop persisting derived test, session, reachability, and file totals.
- **prior-work-retrieval / claude-switch-models-setup** (daymade-claude-code v3.7.9 → v3.7.13): remove `uv run` from the synchronous Claude/Codex prior-work hook entrypoint and require the profile-convergence SessionStart hook to use an absolute direct-Python command. The prior-work wrapper now also fails closed when that runtime is missing or a relative override is supplied, rather than falling back to PATH `python3`. Repository and Skill contracts distinguish package-manager-free hook launch from explicit `uv` retrieval, validation, and test lifecycles. Shared UV cache cleanup or lock contention can no longer stall every PreToolUse decision or prevent profile repair.
- **read-claude-code-history** (daymade-claude-code v3.7.13 → v3.7.14): make an exact `--session` read search every discovered project across active Claude homes and registered archives when `--project` is omitted, while preserving an explicit project as a strict lookup boundary and binding workspace readback to the selected session's recorded cwd.
- **tunnel-doctor** v1.11.0 → v1.11.1: correct the Windows/v2rayN chain-repair note that assumed every manual exit was a residential VLESS profile and treated a fixed exit-IP range as the authority. The generic workflow now reads the exact protocol from the owning client, keeps credentials out of output and Git, discovers the live SQLite schema, independently reads back type/presence/pointers/active front, and treats IP/ASN as observation rather than proof of billing class.
- **twitter-reader** v1.1.1 → v1.2.0: fix the single-source-of-failure on
  Jina exposed by live tests. Single-post text now routes through the
  fxtwitter mirror API first (login-free, key-free, direct connection,
  full note_tweet body in `tweet.text` — 2,324-char long-form verified);
  X Articles with images keep `fetch_article.py`. The Jina path is
  demoted to fallback with its real reliability profile recorded: the
  anonymous `r.jina.ai` lane gets 403-globally-banned for hours when
  *third-party* users abuse x.com, then recovers (verified live — ban
  expired and anonymous fetch returned post text), so it is intermittent,
  never load-bearing; and `fetch_tweets.sh` hard-requires `JINA_API_KEY`,
  which is currently 402 out of balance and blocks the batch script
  until recharged. README facet updated to match.
- **tibo-reset-codex** v1.2.0 → v1.2.1: precision pass on the Jina
  verdict after re-test — the ban is *intermittent* (expired after hours;
  anonymous fetch then returned the post body), not "dead". Jina is
  usable-but-unreliable backup; fxtwitter stays primary.
- **tibo-reset-codex** v1.1.0 → v1.2.0: replace the dead Jina fallback for
  reading Tibo's X posts with the fxtwitter mirror API — login-free, works
  direct, and returns the full note_tweet body in `tweet.text` (**not**
  `full_text`; the first draft shipped the wrong field name and failed the
  reviewer's verbatim re-run). syndication/oembed demoted to metadata-grade
  fallbacks (both truncate at the 276-char display limit; oembed needs `-L`
  to follow the 301 to publish.x.com). Record the Jina kill mechanism:
  anonymous x.com access through r.jina.ai gets 403-globally-banned for
  hours over *third-party* abuse, and the repo's Jina key is out of
  balance. Correct the LunarWerx positioning — its verification leg is
  independent (it checks against OpenAI's status page) but its data inputs
  are still public reset records including Tibo signals, so it cross-checks
  third-party *readings* of Tibo posts, never serves as an
  independently-observed second source; §4's chain now carries that
  qualifier. Codify the milestone-celebration reading rule: Tibo binds
  resets to user milestones (7M/8M/20M all delivered; 500k explicitly
  excluded after re-verification showed it was a bug-compensation payout,
  not a milestone), so "celebration moved to tomorrow" reads as a reset
  announcement — the misreading that started this update. Two-round
  independent fresh-context review: round 1 = 1 blocker (wrong field name)
  + 4 should + 2 note, all fixed; round 2 = all seven confirmed fixed, plus
  4 wording residues (500k milestone misread, unqualified "independent
  second source" in §4, oembed 312→273 chars, "9M 时"→"逼近 9M 时") also
  fixed. quick_validate + regression audit green.
- **claude-code-hooks** (`daymade-claude-code` v3.7.9): refresh the tracked
  security-scan attestation against the v3.7.8 content so a fresh checkout can
  package the reviewed Skill without first regenerating derived evidence.
- **claude-code-hooks** (`daymade-claude-code` v3.7.8): distinguish recurring
  advisory cadence from blocking remediation budgets. Advisory injectors remain
  available throughout long sessions and prove long-horizon liveness;
  per-session ceilings are reserved for blocking loops whose capped exit
  explicitly leaves work blocked, unshipped, or pending.
- **git-safety-net** (`git-safety-net` v1.13.0): Mode D now names the shared-index drift trap
  that index-bypassing commits leave behind, and the prevention reference's commit-scope hygiene
  check is upgraded to match. A bare `git commit` snapshots the *whole* index, not just what you
  staged — but the skill never said so, and nothing warned that `commit-tree` + `update-ref` (or
  a temporary `GIT_INDEX_FILE` commit) advances HEAD while the shared index stays on its old
  baseline, so the commit's own files show as staged deletions (`D ` + `??` in `git status`) that
  anyone's next bare commit turns real. Verified mechanically on throwaway repos: the drift
  produces exactly those status pairs; a bare commit deletes the delivered files from HEAD while
  the working tree looks untouched; `git restore --staged -- <paths>` re-syncs; and
  `git commit -- <path>` neither creates nor repairs the drift. The new Mode D bullet assigns
  the two obligations — whoever advanced the branch past the index re-syncs immediately, and
  whoever commits bare on a shared tree reads `git diff --cached --name-status` as the blast
  radius and stops on any entry they don't recognize. The hygiene section's pre-commit check
  moves from `--name-only` to `--name-status`, because the status letter is what exposes a
  phantom `D` for a file you never deleted. Real incident: a 24-file delivered directory sat in
  the drift window with `D ` lines as the only sign; one bare commit by a parallel session would
  have deleted it from the branch tip.
- **claude-code-hooks** (`daymade-claude-code` v3.7.7): the skill asserted that a non-git
  heredoc whose body carries trigger-looking data leaves a fail-closed guard with "no cheap
  middle ground" — only declare-it-fail-open or a real shell grammar. That is now shown to be
  wrong, with the middle ground and its contract: **strip heredoc bodies by sink**. A body
  feeding a data consumer (`git commit -F -`, `python3 - <<'PY'`) is data and comes out; a body
  feeding a shell (`cat > x.sh <<'EOS'`, `bash <<'EOS'`, `ssh host <<'EOS'`) *is* command text
  and stays in. The `keep` branch is the half a first cut omits, and omitting it is not
  cosmetic: on an 852-command replay the wholesale-strip version passed its fixtures and then
  missed that shape's only true positive in the corpus, which lived inside a `cat > … <<'EOS'`
  that was executed two lines later. The published contract states the failure direction (an
  unnamed sink means the body is stripped — a miss, never a false block, per rule 1), that it
  does not raise pitfall #11's grammar ceiling, and that the sink list is the only side safe to
  extend. The same walker section carried the overturned claim a second time — its
  false-block-direction list headed with "non-git heredoc bodies (declared, not patched)" and a
  blanket "each block-side entry is declared because fixing it takes real shell grammar." Both
  were corrected in place; leaving them would have had the file assert "only a grammar fixes
  this" and "a heuristic fixes most of this" about one category within twenty lines.
  Recipe smoke-run verbatim (11 shapes, including the three the prose names as genuine misses).

  Two new pitfalls, both measured while writing a guard under this skill's own rules:
  **#42** — a hook that locates a sibling file with `dirname "${BASH_SOURCE[0]}"` looks in the
  wrong directory, because rule 3 requires `~/.claude/hooks/<name>.sh` to be a symlink and
  `BASH_SOURCE` is the *invocation* path. The sibling lookup exits 127, and the SessionStart
  health check renders that as `selftest failed` for a completely healthy guard — a permanent
  false alarm, the direction that trains operators to ignore the whole line. Same root as #41
  (unresolved symlink), different victim (locates from the link vs stats the link); the two now
  cross-reference. Fix is the portable link-walk loop, plus the calibration that catches it:
  exercise the selftest through the *registered* path, not only the SSOT path.
  **#43** — `settings.json` hook paths come in three spellings (measured in one active profile:
  45 `~/…`, 8 absolute, 5 `$HOME/…`; all three fire). A consumer that expands only `~` leaves
  `$HOME` literal, the path fails `[ -r ]`, and the tool files live guards under "can't check
  this one" — four registered PreToolUse guards had never actually been audited. One-way
  silent, and toward false *unknown*, which reads as noise. Fix expands both; the calibration
  is asserting targets-found equals entries-registered.

  Rule 9 (corpus replay) gains the false-positive family that is structural rather than
  incidental: for a guard whose detector is a text pattern, **documenting the anti-pattern
  reproduces its own trigger**. Of the 4 corpus commands matching that guard's headline shape,
  3 were healthy — a commit message about the guard, a doc write embedding the pattern, and the
  calibration command that runs the bad form beside the good one. A naive detector would have
  been 75% wrong on its own signature shape, blocking its author mid-sentence. Retired by the
  sink-discriminating stripper plus a "correct form present in the same command" exemption,
  the same shape as a `pipefail` escape hatch.
- **daymade-audio / asr-transcribe-to-text** (`daymade-audio` v1.32.4): prevent single-character or degenerate aligned turns from emitting `start == end` and `duration == 0`. The Qwen aligner and Whisper.cpp late-fusion producer now share one half-up integer-millisecond contract for direct and interpolated lattice points, turn fields, TXT, CSV, and alignment JSON; degenerate turns receive only the smallest 1 ms interval and never borrow a later timestamp across a speaker change or long silence. Both speaker-bundle producers record their reviewed edge-inheritance tolerance in the final receipt (Qwen 1 s; overlap-only fusion 0 s), and the shared time-contract module is covered by each pipeline hash. This keeps identically named artifacts semantically consistent without weakening downstream positive-duration or diarization-support checks; the receipt-less legacy cascade remains outside the strict bundle contract.
- **pdf-creator** (`daymade-docs` v1.13.0): the table-border check could clear the defect it
  exists to catch, and separately failed most healthy documents. Both were found by calibrating
  it against real material rather than fixtures.

  *False pass.* The check compares raster ink against the rules the object layer promises, but
  Chrome DROPS geometry lying entirely outside its page clip, and a rule that was never written
  is never looked for — measured, a table with vertical rules and no cell fills printed
  `5/5 promised rules painted — PASS` with its right border genuinely absent. New `--reference`
  mode compares the subject's distinct-rule count against the same document rendered by the other
  backend; the verdict is symmetric, so a swapped pair fails rather than silently clearing the
  damaged file. Counts rather than positions, and document-wide rather than per page, because the
  backends break one 60-row table into 5 pages vs 3 (`default`) and 3 vs 15 (`warm-terra-menu`)
  with identical rule counts throughout. A reference-free pass now states what it did not check,
  and `NOTHING CHECKED` exits 3 rather than sharing 0 with a real pass.

  *False failures.* Against 46 delivered PDFs the ink check failed 34. It read every vertical
  edge as a promised rule, and an `<hr>` is a rect 0.7pt tall whose ends are vertical edges — so
  it hunted for a full-height rule at the page margin of documents with no table at all. Scoping
  to the table bbox left 10, on inline `<code>` backgrounds inside cells. The promised set now
  comes from each table's detected cell grid, and degenerate detections (one row, or one column)
  are declined rather than accused. A coverage threshold was tried and rejected: at a clipped
  edge a single header-row fill is often the only geometry left (29.63pt of a 90pt table), so
  "must span the table" silently switched the primary detection off.

  *Also rejected*: requiring the rules to bracket the table's text. On healthy `warm-terra-menu`
  output the text runs 65.50pt past the rightmost rule — a larger asymmetry than the 37.60pt of
  the real defect. And `MAX_STROKE_PT`, added in the previous change to exclude fill edges, is
  removed: it never excluded anything (pdfplumber reports `width=0` on a `rect_edge`), and had it
  worked it would have blinded the check at the clipped edge.

  The mandatory visual self-check now names the border check as its second step. It previously
  listed the clip among the failures it exists to catch, then prescribed only "read the PNGs" —
  the procedure the same document calls unreliable for this defect.

  The reference file is ink-checked too, so argument order cannot decide whether the damaged
  file is examined — for a border Chrome *clipped* rather than *dropped* both renders promise the
  same rule count, so the count comparison sees nothing and only the ink check finds it. Measured:
  before this, passing the clipped file as `--reference` produced an unqualified PASS.

  Calibration: 5 themes × single- and multi-page × both argument orders = 20 runs — the 12 pairs
  with no clipped file pass in both orders, the 8 that have one are caught in both; 14 real
  markdown documents × 2 themes = 28 single-file runs, zero false positives.
- **read-claude-code-history** (`daymade-claude-code` v3.7.6):
  make bounded keyword search usable as an observability path instead of parsing every
  session twice before it can report one match. Search now de-duplicates aliased physical
  project directories, builds a bounded internal-sessionId index, runs a native file-level
  candidate pass, and fully parses only exact candidate paths while retaining renamed
  active/archive copies of the same session. This keeps source provenance, date-window
  untimed-record counts, and record unions exact. The shared file prefilter used by both
  `read-claude-code-history` and `read-codex-history` now safely handles uncased Unicode such
  as CJK with an exact matcher for every raw UTF-8 / JSON-escaped mixture; unsafe folds still
  fall back to full parsing.
  On a real 8,500+ physical-file / 5,200+ session / 260+ project inventory, a
  representative one-day CJK search completed in about 11s and fewer than 1% of
  sessions required full-session parsing. Deterministic regressions prove 1/41 full metadata parses,
  byte-identical output with `--no-prefilter`, archived-copy untimed-count fidelity,
  escaped-CJK recall, and honest zero-candidate reporting.
- **read-claude-code-history / read-codex-history** (`daymade-claude-code` v3.7.5):
  stop scanning the same multi-gigabyte Claude history tree once per profile label.
  Multi-model profiles commonly expose distinct config homes whose `projects/` paths are
  symlinks to one physical tree; the inventory previously parsed that tree again for every
  alias and only de-duplicated sessions after paying the full I/O cost. It now groups sources
  by the resolved physical `projects/` path, scans each tree once, and attaches every nominal
  active/archive label to the resulting conversations before the existing cross-tree merge;
  the original-word exporter now applies the same grouping to each of its two logical passes.
  A deterministic main + aliased-profile + distinct-archive regression proves two physical
  parses instead of three, full provenance retention, and non-inflated subagent exclusion
  counts, while a second regression proves two exporter reads instead of four; both complete
  reader suites remain green.
- **prior-work-retrieval** (`daymade-claude-code` v3.7.4): the Search routing table was
  provider-blind in one row and short one row. "Meaning remembered, wording changed" carried no
  platform qualifier while its adapter is a Claude-only index, and no row covered prior
  conversation evidence whose platform is unknown, plural, or simply not Claude — so a
  cross-provider retrieval could satisfy the table, search Claude alone, and write "no prior work
  found" into a receipt. The recall row now states its Claude scope and a new row routes
  unscoped/non-Claude conversation evidence to `local-conversation-history`. The description was
  audited for a trigger collision with that router and does not have one: it is limited to reuse
  before substantial new production, which the router never claims.
- **daymade-claude-code / prior-work-retrieval** (v3.7.3): stop arming the retrieval gate on
  questions about the *current* session. `什么来着` sits in the strong-signal tier, so it armed
  with no distal-referent requirement — and the gate's own `audit` command shows it firing twice
  on prompts whose referent is the conversation already in front of the executor
  (「我们这个对话最开始是想要干什么来着」,「我们的主线任务是什么来着」). Those have no carrier
  to search, no candidate to verify, and produce no artifact, so the gate could only add
  friction, and a gate that misfires on healthy input is how an operator learns to bypass it
  reflexively.

  Fixed by excising the proximal construct before signal matching, alongside the existing
  negation and stale-age excisions. Demoting `什么来着` to the weak tier was the wrong fix:
  「上次做的方案叫什么来着？」 is a genuine recall and carries no distal determiner, so it would
  have stopped arming. The excised span must include the recall idiom itself — removing only
  `这个对话` leaves `什么来着` behind and the strong tier still matches it. Calibrated in both
  directions (4 proximal prompts no longer arm; 6 genuine-recall prompts still do) with
  regression tests for each half; suite 66/66.

- **read-claude-code-history** (`daymade-claude-code` v3.7.2): the Skill claimed Kimi
  CLI was reachable "only through that reference until a dedicated Kimi reader is
  justified," while its own bundled scripts ship a live `search --kimi`
  (`search_kimi_wires`) and `list_local_history.py --source kimi`. With the
  cross-provider router now sending every Kimi request here, that stale sentence was
  the last hop of a chain that answers a Kimi question from Claude data and reports a
  false "never happened". Kimi is now a task-table row and a stated live surface, the
  legacy section documents the router, and the two frozen PR #357 snapshots carry a
  banner saying they describe retired contracts — one of them shares its `name:` with
  a skill that has since been rebuilt around a different contract. The router drops
  its duplicate copy of the Kimi home-resolution order, which belongs to the executor
  that owns the surface, and widens its own "no executor flags here" rule to admit the
  three flags that name provider scope, which it was already using.
- **read-codex-history** (`daymade-claude-code` v3.7.1): define “one chronological
  evidence briefing” as one immutable local artifact rather than one oversized model
  payload. Large briefings are materialized once, hash- and line-count-bound, then read
  through bounded non-overlapping ranges; unread ranges remain explicit gaps instead of
  being hidden by rerunning and fusing differently truncated outputs. The compatibility
  section now distinguishes the restored cross-provider router from its historical
  combined-command reference while keeping Codex evidence ownership here.
- **tunnel-doctor** (v1.11.0): correct a false negative in Step 2K that sent the reader to the
  wrong side of the fork. The step inferred "zero `sshd` journal entries → the packets never
  arrived → suspect your tunnel," but a host-local packet filter produces exactly that reading
  while the packets are in fact arriving. Verified against a live case: `tcpdump` on the
  destination showed the client's SYNs landing on the NIC and being retransmitted, while
  `ss` showed only `LISTEN` and no `SYN-RECV` — a default `-P INPUT DROP` with explicit accepts
  for 80/443 was dropping them before the socket layer. Step 2K now requires `tcpdump` + `ss`
  to separate "never arrived" from "arrived and dropped locally" before anyone blames a tunnel.

  Two related corrections in the same step. A cloud host enforces an inbound port **twice** —
  provider security group *and* host firewall (`ufw`/`firewalld`/`nftables`) — so the step now
  checks both and states that satisfying one leaves the other blocking with no signal. And the
  old bullet "it is in the allowlist and packets still never arrive → the blocker is local" is
  replaced, because that is precisely the case where the blocker is the host firewall. Also adds
  the cheapest control for "is it me or is it them": run the same probe from another host that
  shares your egress but not your network stack — the one instrument a TUN cannot corrupt,
  since it never traverses it. If that host succeeds, `ssh -J` through it is a working path
  that keeps your key on your own machine.

  Context for the correction: the earlier text let a blocked host be certified "completely
  healthy" — `sshd` active and listening, config valid, no `fail2ban`, empty `hosts.deny`,
  disk and memory fine — with the packet filter never inspected.

### Added
- **local-conversation-history** (`daymade-claude-code` v3.7.0; marketplace v3.5.0): restore the
  cross-provider entry point above the four provider-and-action-specific history skills. PR #357
  converged local history into `read-claude-code-history`, `read-codex-history`,
  `continue-claude-code-work` and `continue-codex-work`, and moved the old entry point's SKILL.md
  into `read-codex-history` as a legacy reference; the router that was meant to sit above them was
  specified the same day and never written — no branch, no commit, no PR. This adds it.

  It routes by platform (Claude Code / Codex / Kimi CLI) x action (read evidence vs continue
  interrupted work), and owns the one job none of the four own alone: a single inventory across all
  three providers. Both readers already ship `list_local_history.py` and its `--source` defaults to
  `all`, but each reader's task table pins it to that reader's own provider, so a cross-provider
  listing never happened unless someone asked for it by name. Kimi CLI, which has no dedicated skill,
  had no entry anywhere.

  Deliberately thin: no parsing, no provider-specific flags beyond `--source`, and no copy of an
  executor's commands, so it cannot drift into teaching a stale invocation. It does carry forward
  three invariants the retired skill had established — the Claude source set is indivisible (active
  homes plus every archive in `~/.claude/history-sources.json`), the current session self-matches and
  must be excluded before a hit counts as historical evidence, and zero results are not absence.
- **github-ops** (v1.2.0): replace command-success GitHub automation with a verified-state
  operating contract. Every mutation now binds the account, host, fully qualified target,
  authorized consequence, recovery path, supported input schema, and an independent readback;
  non-idempotent writes are read before retry and bulk targets are frozen before processing. Add
  organization access and settings workflows for direct/team/base permission diagnosis,
  collaborator invitations and revocation, repository-creation policy, UI-only member
  privileges, and 2FA impact preflight. Add a complete repository route for safe clone, explicit-
  visibility creation, settings, rename/archive, transfer, deletion, and hosted readback. The API
  guide now distinguishes GET response fields from writable PATCH inputs and fixes request-method,
  draft-PR, Actions filtering, GraphQL pagination, rate-limit, webhook, secret, artifact/log, and
  high-level pagination examples; Actions bulk control now freezes separate cancel, rerun, and
  artifact populations. Remove the organization-specific JIRA bypass convention and the generic
  public-repository default while preserving the accepted parallel/superseded PR convergence
  workflow and closing its exact-tip deletion race with an expected-SHA lease.
- **transcript-fixer** (`daymade-audio` v1.32.1): pin the space-bearing person-name shapes that any future whitespace- or script-based prose heuristic would silently kill (`Ada Lovelace 老师`, `山田 花子`, alongside the already-covered `Alice Maria Chen` and `Joe 老师`). A residual gap is named rather than patched: prose written into the ASR-variant field survives when a Latin word splits it into CJK runs of eight characters or fewer, and the surviving atom then enters the correction dictionary at confidence 1.0 and actively rewrites those characters. Every discriminator measured against that gap kills a healthy shape — two-or-more inner spaces kills the Latin three-part and Latin-plus-honorific forms, two-or-more CJK tokens kills the space-separated CJK form, and adding a CJK-run length floor stops catching the target — which is the expensive direction for a fail-closed check and would reverse the module's stated syntax-only rule. Realistic prose is already caught: four of five hand-written wrong-field lines trip the existing length limit and the stderr warning names the whole line. Tripwire verified by injecting the naive rule into a scratch copy and confirming the pinned names die; synthetic names only.
- **transcript-fixer** (`daymade-audio` v1.32.0): add a bounded clip-level second-recognizer rung for load-bearing tokens that exhaust local evidence. It calibrates transcript/media clocks, preserves distinct tight/medium clips, verifies neighbouring words, caps re-cuts, requires current authorization and known recognizer-family provenance, treats agreement as evidence about sound rather than spelling, and queues unresolved cases instead of guessing. The existing migration repair moves into the CI registry with its deterministic boundary suite; sanitized synthetic people-roster regressions join it, rejecting structurally malformed entries visibly while retaining quoted, multilingual, and multiword names without language-specific denylist guesses. An optional local gate checks the configured real roster without publishing names or paths, and manual promotion now verifies that the replaced form is absent instead of merely finding a corrected term that may already have existed.
- **claude-switch-models-setup** (`daymade-claude-code` v3.6.0; marketplace v3.4.0): make `cmks-skills` a first-class managed local source marketplace. Discovery now accepts the Cemakanshan marketplace identity, checks the conventional `cemakanshan-skills` checkout beside the two Daymade sources, and includes its manifest in the LaunchAgent watch set. The existing explicit `codex-active-skills.json` policy remains authoritative, so adding the source does not bulk-activate its catalog; only selected names become `~/.agents/skills` links.
- **transcript-fixer** (`daymade-audio` v1.31.1): make person-name correction explicitly consult two independent authorities—the configured global people roster and the owning project's identity roster—without exposing private repository paths in the public trigger description; project rosters remain manual inputs, and text frequency is never identity evidence. Repair the SQLite migration runner so standard builds no longer reject `UPDATE ... ORDER BY ... LIMIT`, same-run dependencies advance correctly, and same-second current-version rows resolve by insertion order. Legacy `schema.sql` databases now replace only the exact untouched lone `0.0` sentinel with a known, singular `system_config.schema_version` whose required tables are present; incomplete/unknown/edited state remains `0.0` instead of skipping work. Only a simple `ADD COLUMN` whose PRAGMA shape and exact table declaration both match is treated as already applied, so extra collation/table constraints and incompatible objects fail closed. Failed forward runs persist after schema rollback; a failed backward run preserves the still-applied current version and records the failed attempt in its audit details. Focused deterministic migration regressions cover each repaired boundary.
- **bilibili-source** (v1.2.0): document the favorites (收藏夹) enumeration endpoints — `x/v3/fav/folder/created/list-all` + `x/v3/fav/resource/list`, verified logged-in 2026-08-29 with plain params (no WBI signing; 26 consecutive pages without rate-limiting), including per-item field semantics and the `attr != 0` dead-video marker (one observed folder had lost 35 of 79 entries — the argument for archiving favorites early). Upgrade the SESSDATA subtitle path from "documented, verify on first use" to verified: the full chain (view → player/wbi/v2 with cookies → protocol-relative track JSON on aisubtitle.hdslb.com) exercised across a ~400-video batch, multi-part included, with cookie-jar extraction guidance and the "empty list while logged in = genuinely no track" rule. Two new hard-won corrections: Python urllib falls back to the macOS *system* proxy when proxy env vars are stripped (intermittent 503s in batches; fix is an explicit `ProxyHandler({})` opener), and subtitle text is not in the watch page's DOM (only track metadata is embedded), so DOM-capture tools structurally cannot save a transcript — API path only. Live selftest 9/9 after the edit; regression audit fully classified (9 candidates: 7 preserved, 2 factual upgrades).
- **claude-code-ping-start-5h-quota** (`daymade-claude-code` v3.5.0): new skill — one-shot local timer that pings Claude right after subscription quota reset (`caffeinate -is` + `sleep` + minimal `claude -p` via a detached background task), so a fresh 5-hour usage window starts counting while the user sleeps instead of when they wake up. Dual redundancy by design: the detached ping survives session/terminal close, and the background-task exit re-wakes a live session to read back the `ok` receipt. Command anatomy table explains why each component exists (idle-sleep guard, `cd "$HOME"` to avoid project CLAUDE.md/hook token burn, +5-minute buffer against reset-time estimation error) so future edits don't silently drop a load-bearing piece. Bounded to one-shot timers: periodic keep-alive → /loop or cron, Codex/ChatGPT reset-time queries → tibo-reset-codex, quota burn analysis → claude-usage-analyst. Distilled from a real 2026-08-29 run: 85-minute timer fired on schedule, `claude -p` returned `ok` exit 0, and the wake-up confirmation path was observed end-to-end. Two-round independent fresh-context review: round 1 found 6 findings (2 blocking: cross-midnight absolute-time ambiguity; output-path unrecoverable when the wake notification is lost), all fixed; round 2 confirmed all 6 resolved and caught 2 fix-introduced issues, both fixed. The cancel command was live-verified, including a real mis-kill of an unrelated heartbeat sleep that turned the "never pkill by seconds" rule from speculation into tested fact; quick_validate and security scan clean.
- **read-docx-review** (`daymade-docs` v1.10.0): new skill — extract comments and tracked changes from a reviewed docx (Word/WPS) into a per-item adjudication table (markdown or JSON). Revision-aware engine on the OpenXML SDK (dotnet-script csx + stdlib-only Python client), so content inserted via track changes (w:ins) and paragraph-level deletions (w:del) that python-docx silently misses are captured; WPS comment-reference-only anchors get a fallback so every comment stays locatable; zero-comment files emit an explicit "no review traces" warning instead of a silent empty table. Read-only — never mutates the reviewer's file. Verified against a real 96-comment WPS-exported review file plus constructed fixtures (resolved-root-with-unresolved-reply, reference-only anchors, tracked-change paragraphs); first-round independent review produced 8 findings (1 high: unresolved replies under resolved roots silently dropped), all fixed and re-verified 7/7.

### Breaking
- **prior-work-retrieval** (`daymade-claude-code` v3.0.0; marketplace v3.0.0): make explicit prior-work/reuse/history intent the only authority that creates a retrieval obligation. Ordinary implementation, reports, read-only status checks, write-shaped tools, unknown executors, and generic production language no longer arm the gate by themselves. UserPromptSubmit filters non-user envelopes, incapable executors, opt-outs, negated reuse, stale-age language, and ambiguous hedge recall; PreToolUse and Stop only enforce an already-existing prompt-scoped requirement. A new audit command reports trigger mix, empty gates, stranded receipts, non-user arms, and still-arming terms from recorded state. The existing retrieval, coverage, freshness, and source-verification contracts remain; 61 focused tests and a fully classified existing-Skill regression audit pass.
- **Local history skills** (`daymade-claude-code` v2.0.0; marketplace v2.0.0): replace three overlapping/ambiguous entry points with four provider-and-action-specific Skills: `claude-code-history-files-finder` → `read-claude-code-history`, `local-conversation-history` → `read-codex-history`, `continue-claude-work` → `continue-claude-code-work`, while `continue-codex-work` keeps its name. The two readers now own all parsing and remain evidence-only; the two continuation Skills consume verified read receipts, rebuild the original business outcome / unfulfilled requests / user corrections / proven prior assets, and only then execute a next action that directly reduces the outstanding result. `read-codex-history` keeps prompt ledger, state DB and rollout JSONL as separate evidence surfaces, adds exact raw-input tables, Codex-only search, verified selected identity and exact fork/compaction lineage, and rejects fused rollouts containing multiple `session_meta` IDs. `read-claude-code-history` adds recent inventory, chronological Session evidence with queued human prompts in place, original-word export grouped by Session, full-event search, hybrid recall, triage and deleted-file recovery. Exact readers now parse every physical record rather than a resume-oriented tail, retain every selected human and assistant text turn so a middle successful asset cannot disappear, cover registered Claude archives, require one matching record-level identity instead of trusting a filename, reject fused identities and divergent physical copies, choose a strict append-only live/archive superset without traversal-order last-wins, skip healthy blank separators, and fail visibly on malformed JSONL. The parser implementation and format references moved from the continuation bundles into their owning read bundles; all old runtime instructions remain directly reachable in migration references, including the legacy Kimi branch, rather than being silently deleted. Existing users should run `claude plugin marketplace update daymade-skills`, update/reinstall `daymade-claude-code@daymade-skills`, and replace old slash invocations with the mapping above. Verification: strict validation for all four Skills; Claude-reader and Codex-reader regression counts are recorded by the current test run; a real Claude active/archive replay retains the pre-compaction chronology, one real Codex continuation replay recovers the corrected second-attachment referent, and a separate misbound Session replay fails explicitly as a fused two-identity rollout instead of attributing another Session's events to it.

### Fixed
- **read-claude-code-history** (`daymade-claude-code` v3.6.2): stop describing a retired local POC index as though it still exists. The hybrid-recall reference keeps the reason it was never a baseline—missing provenance plus schema drift—but records the durable retirement fact only: a source-presence audit proved the index fully derivable and without unique conversation content.
- **Repository mainline guard:** make the local enforcement path real instead of documentary. The versioned pre-commit/pre-push dispatchers now invoke the mainline/version guard, replay the exact pre-push update set to the existing shared PII guard, and retain a local pre-commit PII fallback for contributors without the maintainer setup. Deterministic fixtures prove direct commits and pushes to `main` are blocked and that the shared pre-push scanner receives byte-identical input. The shared worktree config must point at the canonical primary checkout's **absolute** `.githooks` path; a relative path would let each stale worktree select its own stale dispatcher.
- **claude-switch-models-setup** (`daymade-claude-code` v3.6.1; marketplace v3.4.1): finish the documentation side of the managed-source expansion. `CLAUDE.md` now names the implementation and `--print-watch-paths` as the authority instead of inviting another copied inventory; the architecture reference removes hand-maintained marketplace, checkout, and watcher-manifest lists; and the Skill, troubleshooting guide, and both READMEs stop persisting script/alias counts that are already derivable from their explicit lists. No runtime behavior changes.
- **pdf-creator** (`daymade-docs` v1.11.0): stop routing every CJK document to Chrome, which silently amputates the right border of wide tables. Backend auto-detection was keyed on "does the text contain CJK", justified by weasyprint subsetting PingFang SC as CID Type 0C OpenType — but that is a property of the **theme's font stack**, not of the content, and the two Songti/Heiti themes (`default`, `cjk-auto`) never use PingFang as their primary face. They paid Chrome's cost for nothing, and that cost is a clip, not an overflow: Chrome wraps each page in a `re W* n` clip path at the `@page` content box, so anything past it is present in the object layer and never painted. Measured on A4 with `margin: 2.5cm 2cm 2cm 2cm` — clip path ends at 538.90pt, the table's right border sits at 545.18pt. Tables reach past the box *by design*, since the CJK typography layer sets `overflow-wrap: normal` specifically to overflow rather than break mid-token, which is safe only under a non-clipping renderer. What let the failure survive repeated delivery is not that the preview lies — rasterisers do honour the clip, and the skill's own `pdftoppm` preview shows the gap (measured: zero ink across the 25 pixel columns straddling the border at 400dpi). It is that the surviving symptom looks deliberate: the last column's text is complete and correctly spaced, only a hairline border is gone, while the mandatory checklist primed the reader to look for "text cut off" — the one thing that does not happen. The checklist gains an item that names the real symptom, and a new `scripts/check_table_borders.py` decides it mechanically: it counts the vertical rules the object layer promises against the ones that have ink in a `pdftoppm` raster and exits non-zero naming any rule present in the PDF but absent on paper. Object-layer inspection alone stays blind, since `pdfplumber` correctly reports a rect at 545.18pt. Ink is judged **relative to the local background**, not against a fixed grey cutoff: the bundled themes draw borders at `#e2d6c8` (luminance ~216), so an absolute "darker than 200" test called every warm-terra / mobile / warm-terra-menu border missing — including a table's far-left border, which a right-edge clip cannot reach — on precisely the three themes that still route to Chrome. Promised rules are also restricted to stroke-width geometry, so a shaded header's fill edge is no longer counted as a border the table never drew. Calibrated across all five themes on both backends: zero false positives on tables that are not clipped, and the clip still caught at 8/9. Scope correction from the same pass: this is not a wide-table problem — `default` and `cjk-auto` set `table { width: 100% }`, so a two-column table lands its right border at the same 545.18pt as a six-column one and clips identically. `_detect_backend` now takes the theme and routes CID-TrueType themes to weasyprint while PingFang themes (`warm-terra`, `mobile`, `warm-terra-menu`, and any unlisted/user-added theme) keep Chrome, where the Type 0C problem is real; an explicit `--backend` still wins, and a safe theme without weasyprint installed falls back to Chrome with a stderr warning naming the clipping risk. Membership is an explicit list rather than a stylesheet scan, because `cjk-auto.css` and `default.css` both mention "PingFang" in a comment and a fallback chain — grepping the CSS mis-routes exactly the themes the list protects. Verified by CoreGraphics rendering with vertical-rule counting on a real CJK fee table: before, the object layer promised 9 rules and Quartz painted 8; after, 9 promised and 9 painted. Theme membership is resolved through the filesystem rather than matched as a raw string, because `_load_theme` resolves `themes/{name}.css` case-insensitively on macOS and Windows: `--theme Default` loads the Songti/Heiti CSS, so a string-keyed table would have routed it to Chrome and silently restored the clip under a name the fix claims to protect — comparison is by `os.path.samefile`, since which spellings a filesystem folds together is its business and differs per platform. Thirteen regressions added (16 → 29 passing, baseline byte-identical), each confirmed to discriminate by mutation: dropping `cjk-auto`, adding `warm-terra`, reverting the canonical-name resolution, and giving a protected theme a PingFang body face each fail exactly the tests that should. Three independent fresh-context reviewers ran against the change; the two that completed found a blocking case-sensitivity hole, a blocking factual error about renderer behaviour, an unrunnable verification instruction, and two doc inconsistencies — all fixed here.
- **git-safety-net** (v1.12.0): make independent-clone retirement preserve more than a clean working tree. Checkout discovery now exposes `objects/info/alternates` borrowing instead of presenting a `git clone --shared` checkout as ordinary owned storage. A new non-destructive `git_prepare_clone_retirement.sh` refuses tracked/untracked/ignored bytes, stashes, shallow history, reflog-only commits, every clone-only unreachable Git object, partial/promisor clones, attached linked worktrees, local submodule repositories, known clone-private Git LFS/annex object stores, tracked content filters, unresolved repository-local config includes/custom hook paths, and mismatched survivor identity before creating a backup. It disables lazy fetch, repository fsmonitor, optional index refresh, and untracked-cache writes; freezes every ref tip plus symbolic-ref topology (including stale remote-tracking refs and `HEAD`); builds a no-prerequisite all-refs bundle; preserves reflog identities plus config/hooks/info bytes/types/modes; and binds bundle and metadata archives to SHA-256 receipts. `--verify-current` rechecks refs/symrefs, reflog, metadata, physical state, linked-worktree/submodule/promisor/extension-store inventory, unreachable objects, and artifact digests. The retirement contract defaults to an explicitly authorized recoverable quarantine/OS Trash move, keeps permanent deletion separate, and freezes the absent destination plus process occupancy before the final verification so the no-clobber quarantine can be the next operation instead of leaving an avoidable post-verification probe. Thirty-six deterministic regressions cover shared-object discovery, empty-repository restore plus symbolic-ref replay, dirty/ignored/stash gates, shallow and unreachable history/object types, promisor non-mutation, extension-store/filter refusal, fsmonitor non-execution, linked-worktree/submodule refusal, config/hook indirection, hook-mode/ref/metadata races, and archive tampering.
- **skill-creator** (`daymade-skill` v1.32.0): replace the high-frequency `uv run --with` overlays used by bundled tooling with one locked, project-local uv environment. `pyproject.toml` and `uv.lock` pin PyYAML, tiktoken, and pytest; all normal tool invocations now use `uv run --frozen`, so caller projects remain isolated while package data still comes from uv's shared global cache. The runtime contract explicitly rejects a cross-project `UV_PROJECT_ENVIRONMENT`, project-specific cache roots, and cache cleanup as part of ordinary Skill execution. The full local suite passes (`181 passed, 7 subtests`) and the validator self-test passes 27/27.
- **README skill catalogs** (marketplace v3.3.0): add the `read-docx-review` entries missed by its release commit — the English README had the suite list line but no detail section, the Chinese README had neither; caught by `check_doc_skill_lists.py` (DRIFT 100/101) during the claude-code-ping-start-5h-quota release and repaired from read-docx-review's own SKILL.md description. Both catalogs now match the manifest at 101/101.
- **skill-creator** (`daymade-skill` v1.31.2): remove the copied shipping-exclusion list from `SKILL.md` and the copied runtime-state examples from `CLAUDE.md`. Both now point to `scripts/packaging_policy.py` as the only current authority and prohibit consumer-specific filters; the changelog retains the v1.31.1 directory names only as historical evidence of what that release fixed.
- **skill-creator** (`daymade-skill` v1.31.1): exclude runtime `.in_use/` lock files and `.ruff_cache/` tool output in the shared shipping policy. Source-linked Skills can accumulate this state while active or tested; it previously entered generated `.skill` archives and the corresponding security/regression hashes. Packaging, security staging, content attestation, and regression audit now ignore the same runtime/development directories while retaining ordinary Skill files and the existing opt-in `evals/` behavior.
- **prior-work-retrieval** (`daymade-claude-code` v3.4.1; marketplace v3.2.1): stop treating bare `现有` / `已有` / `既有` as historical-reuse authority. A real medium bug-fix replay containing “现有测试或 README 如果冲突才同步” armed an empty receipt gate, loaded two governance Skills, then routed into gstack investigation before reading the three task files. The classifier now requires `已有` / `既有` to name a reusable asset such as code, script, SOP, plan, or workflow; references to current tests, README, files, implementation, behavior, and validation stay ordinary task context. The model-visible description and both user-facing docs state the same boundary, while explicit existing-asset and reuse phrases remain positive controls.
- **git-safety-net** (v1.11.0): keep authorization object-specific during concurrent repository convergence. Generic “take over / continue / finish cleanup” language no longer absorbs collaborator-owned worktrees, branches, or PRs into the mutation set; discovered objects are partitioned into change-authorized, inspect-only, and explicitly excluded sets before action. A user-excluded active worktree is not inspected internally, backed up, merged, unlocked, removed, or counted as unfinished work. Exhaustive `git_loss_audit.sh`, whole-set dangling preservation, and `--all-refs` now require every surface they enumerate to be explicitly in evidence/action scope; ordinary branch/worktree convergence uses checkout/ref-scoped checks plus targeted branch or collision-checked recovery-ref bundles. The one-main terminal gate remains available for a fully authorized branch/PR/worktree set and now also proves that only the primary worktree remains; otherwise the Skill reports scoped completion and lists collaborator resources as untouched exclusions. Git worktree locks are described by their real boundary—prevent prune/move/delete, not grant ownership or deletion authority. Existing-Skill regression review, bounded fresh-context A/B/C replays, focused tests, validation, reference checks, package validation, and security scan cover the change.
- **claude-switch-models-setup** (`daymade-claude-code` v3.0.1; marketplace v3.0.1): classify keys containing `declin` as per-machine state so prompt-decline counters such as `feedbackDraftsTurnOffPromptDeclines` are not copied from the default Claude profile into every provider profile. The real key shape is covered by the existing isolated profile-sync fixture.
- **transcript-fixer** (`daymade-audio` v1.31.0; marketplace v2.2.2): make domain-context vetoes executable at Stage 1 and give context rules a managed, domain-scoped home. A trap annotated `禁裸词`/`禁入词典` or a confirmed-correct （勿修） record in `~/.transcript-fixer/contexts/<domain>.md` now demotes any dictionary rule with the same FROM to safe-mode deferral — beating `--apply-domain` trust-flattening, so a real-word rule that is right in some contexts and wrong in others (the 绿点→绿电 class) can stay in the dictionary without firing blindly, instead of forcing an all-or-nothing `--report-false-positive`; `--apply-all` remains the explicit override, demotions print on stderr, and `--add` warns at write time when the new rule is veto-marked. Context rules gain a `domain` column (schema v2.4, NULL = global; additive migration whose backward path drops the index before the column) and their first management CLI, `--add-context-rule` / `--list-context-rules` (duplicate patterns, invalid regex, list-form write domains, and un-migrated databases all fail loud with the real direction), with Stage 1 loading global rules plus the active domain's. Context rules are exempt from trap demotion — the pattern is its own context, so a lookahead whose match text equals a demoted FROM no longer inherits the deferral. Docs scope the veto honestly (only when the domain is named; by FROM across a multi-domain union) and spell out the two marker authoring constraints (single-line, never discuss the marker word on a trap line). An independent fresh-context review surfaced 9 findings (2 major), all fixed or documented; 631 tests pass including 25 new ones, and a real replay of the motivating 84-minute transcript now defers 绿点 while still applying every correct trusted rule. Packaging cleanup also replaces scanner-confusing public path/remote examples and percent-encodes the inline SVG namespace without changing its decoded value.
- **marketplace documentation SSOT** (`daymade-claude-code` v2.1.1; marketplace v2.2.1): stop persisting catalog positions, marketplace-version badges, and a complete Skill snapshot in `CLAUDE.md`. The manifest remains the only authority for names, versions, sources, and suite membership; the READMEs keep unnumbered human-facing capability sections, and `CLAUDE.md` keeps only the stable authority pointer. The detailed new-Skill SOP now says the same thing and removes stale `.zip`, relative-path, and quiet-mtime takeover instructions. The drift checker rejects numbered capability headings, copied version badges, and model-loaded snapshots; focused positive and negative controls prove both its healthy and failure branches against the real repository.
- **prior-work-retrieval** (`daymade-claude-code` v2.1.0): stops retrieval from replacing a read-only maintenance outcome with its own receipt workflow. The catalog description now front-loads the read-only exclusion so it survives Codex's shortened Skill-description budget; negated phrases such as “不要修改文件” cannot be misread as a positive production verb; `Stop` validates only an already-existing requirement and never creates one from final-answer length. Required-source fingerprints keep receipts valid across unrelated optional-carrier edits, while required carrier changes still invalidate them. Filesystem content search no longer unconditionally enumerates every path; path scans require an explicit filename/path/date term. Forty focused regressions pass. A fresh read-only Huawei repo task then completed with one direct inspection and a seven-line business answer—no Prior Work, Goal, agent, meeting sync, or write.
- **claude-md-progressive-disclosurer** (`daymade-claude-code` v2.1.0): profiles the complete model-visible startup surface with `codex debug prompt-input` instead of assuming one historical `project_doc_max_bytes` behavior. It distinguishes the global user-instruction path from the cumulative project-doc budget, audits truncated Skill catalog descriptions and hook self-trigger loops, and adds current Claude `/memory`, `InstructionsLoaded`, `claudeMdExcludes`, and path-rule carriers. The zero-loss reviewer gate is bounded to one fresh-context reviewer by default; reviewer count and recursive re-review are no longer accepted as quality proxies.
- **continue-codex-work** (`daymade-claude-code` v2.0.3): stop routing Codex's own native resume of the same conversation through cross-session history recovery. If the host-restored turns or compaction state are already present in the current context, the Agent now continues directly and verifies current workspace/external state; a new or different Agent context taking over another rollout still requires the exact `read-codex-history` identity and lineage receipt. The Skill entry gate, metadata description, English/Chinese operator docs, and repository inventory now state the same boundary.
- **prior-work-retrieval** (`daymade-claude-code` v2.0.2): stop the prior-work gate from blocking its own receipt-completion command when a `--reuse` or `--reject` reason contains write-like prose such as `cp→symlink`. The exemption is now anchored to the parsed command entry instead of a route name found anywhere in the segment: quoted route names cannot launder arbitrary Python writes, unknown executors before a later retrieval command stay gated, and prefixed, chained, backgrounded, process-substituted, or direct tool writes remain fail-closed. The focused suite now includes the two independently reproduced `<(` / `=(` escape shapes; all 35 tests and the hook self-test pass.
- **skill-governance** (`daymade-skill` v1.30.1): close the remaining project dual-root audit false-clean and false-positive paths found by independent counterexamples. Declared-but-empty roots now fail instead of returning clean; a shared `SKILL.md` cannot hide extra divergent bundle material or be a router with no canonical source; router paths are parsed from one backtick-quoted project-relative target without assuming the directory matches the frontmatter name or uses ASCII; and quoting the router marker in ordinary full-Skill prose no longer misclassifies the bundle because the marker must be the first nonblank body line. Positive controls keep both directory-level and file-level symlink sharing valid. Twenty-one standard-library regressions pass on macOS and Linux, and the real project that motivated the fix now resolves every overlapping Skill to one shared canonical target with zero drift or identical-copy debt.
- **transcript-fixer** (`daymade-audio` v1.30.0): make the human audio-review gate executable at the exact canonical-file boundary. `--list-review --review-file FILE` now scopes the visible items to one resolved transcript path while its completion count always covers the whole file; domain/source filters can no longer hide remaining decisions. Wrong, missing, or unmatched file paths fail closed instead of returning a false `pending_total: 0`. The dashboard accepts `--file` / `--item` deep links, displays a visible file-scope banner, and keeps unrelated global queue rows out of the review count. When the human finishes marking, the operator reads the same path back and requires `stats.pending_total == 0` instead of rerunning ASR or asking the same questions again. Runtime references consistently separate “fix this occurrence” from “promote a reusable rule”: one-off wording stays file-local, identity forks remain human decisions, and stale instructions to save every correction or target high dictionary coverage are regression-blocked. Focused queue/API/CLI/docs tests and a real file-scoped HTTP/CLI journey pass.
- **setup-notifications-via-wecom + notify-wecom** (v1.1.0): bind every webhook to an explicit `self` or `others` target plus a human-readable label and the canonical sender path/digest. Self delivery needs no authorization; other, unknown, or masquerading sender paths remain behind a human confirmation gate. Missing identity fails fast. Manual sends keep bounded retry, while guard-owned outbox delivery accepts only the approved payload digest and makes one non-retrying HTTP attempt. The atomic recipient command updates metadata without printing or replacing the webhook value. Focused config/outbox tests and both Skill validators pass.
- **transcript-fixer + asr-transcribe-to-text** (`daymade-audio` v1.29.0): closes the gap between a few correct spot checks and a genuinely reviewed high-stakes transcript. Multi-recording correction now treats whole-source coverage as a separate completion claim: an independent ASR must cover the complete clearest/canonical recording, additional tracks must be compared across their complete overlap, and sampled clips remain item-level evidence only. Plausible proper-name forks with no local authority are collected for one human decision instead of guessed or majority-voted; confirmed identity aliases remain the words actually spoken. Detection and queueing no longer count as correction: any review row still pending for the canonical file blocks a high-quality/final claim, and an unavailable human leaves an explicitly incomplete draft. Human confirmation settles an occurrence without automatically promoting a rare sentence-local error into the dictionary. The local Qwen worker also recovers from valid containers its pinned MLX decoder cannot open (including Ogg/Opus) by using a temporary ffmpeg-normalized PCM WAV while keeping checkpoints and provenance bound to the original source bytes; only recognized decoder/container failures trigger this path, while GPU, memory, and programming failures propagate unchanged. Finalization now freezes each leg's source and producer identity before execution, binds each completed checkpoint to its exact chunk index, invalidates legacy post-run sidecars, and rejects a conflicting second speaker rename before it can desynchronize TXT/CSV from alignment metadata. Thirty-four long-audio regressions and eleven transcript-contract checks pass, plus a real Ogg/Opus decoder probe through the temporary PCM path.
- **asr-transcribe-to-text** (`daymade-audio` v1.28.0): fixes the long-audio resource, quality, provenance, and orphan-process contracts instead of extending the old timeout. The pinned Qwen3-ASR implementation applies `max_tokens` to each low-energy ~20-minute chunk, so the former 200,000-token default allowed one bad chunk to grow a 33.4 GB physical footprint (44.0 GB peak) and run for more than nine hours without a final file. Local MLX now defaults to 8,192 tokens per chunk, requires an explicit override above 16,384, atomically checkpoints each chunk, and binds resume identity to source bytes, resolved immutable model revision (or local model content), producer, splitter, sample rate, dependencies, parameters, and quality policy. A real-corpus-calibrated repetition gate rejects bounded garbage below the token ceiling. Qwen/Whisper/diarization outer caches require source+producer+parameter+artifact provenance; each run writes into a unique staging directory, alignment rechecks the complete producer-and-parameter contract before consumption, and an atomic final receipt binds the four delivery artifacts plus producer/model/parameter contract. Receipt-backed voiceprint relabeling updates the complete bundle transactionally and restores the anonymous-speaker version on failure. Checkpoint and quality failures propagate machine-readable exit classes instead of human-message parsing. Managed workers bind to their owner PID, run in process groups, emit heartbeats, and reap descendants even when the group leader exits first. Twenty-one deterministic tests pass on macOS and Linux. A 30-minute accepted production recording reran in 68.2 seconds at 4.36 GB peak RSS with zero swap and produced a byte-identical 9,005-character transcript.
- **skill-creator** (`daymade-skill` v1.29.1): update its pipeline example and wrapper-workflow follow-up pointer to the renamed `read-claude-code-history` / `continue-claude-code-work` entry points so future Skill work does not route into removed slash names.
- **continue-codex-work** (`daymade-claude-code` v1.58.1): make Codex compaction support explicit and preserve every retained character. The extractor already read `compacted.message` / `replacement_history` alongside raw pre-compaction rollout records, but each surviving compacted item was silently cut to 800 characters before rendering, so `--full` could not honor its untruncated-retained-text contract. Parsing now keeps full non-noise `input_text` / `output_text`; default rendering applies the existing visible section limit and `--full` removes it. All compacted records are ingested, while the briefing renders the latest continuation state per selected session or ancestor. Briefings and docs call this `Compacted Context` rather than implying one synthetic summary, and define the honest boundary as content absent from both raw rollout records and retained compaction state. Long-text and two-compaction regressions prove default clipping/full recovery and the ingest-vs-render boundary; all 40 extractor tests pass, and a real 26.1 MB session with two compactions replays successfully in both modes.

### Added
- **claude-switch-models-setup** (`daymade-claude-code` v3.4.0; marketplace v3.2.0): separate local marketplace inventory from Codex activation policy. Maintainer machines now require an explicit `codex-active-skills.json`, activate only those source-backed names under the official `~/.agents/skills` root, and keep `~/.codex/skills` only for the declared compatibility subset. Registered sources carry repo containment and load-time inode evidence into freeze; the apply path freezes selected source and user-root identities before mutation, rejects changed topology, and cross-checks active/legacy links plus a post-snapshot source identity against one source. Only wrong managed-source symlinks move to recoverable backups; platform-exclusive rename restores a third-party race winner to its original name without overwriting a newer winner. Real objects, third-party links, and malformed foreign links otherwise remain untouched. Manifest setup and its manual SOP share an atomic no-overwrite seeder, dry-run is zero-write, and no-follow/no-overwrite publication closes root and same-name races. The deterministic suite is registered in Linux CI and covers the resulting collision, traversal, and concurrency paths.
- **lark-cli-router** (`daymade-claude-code` v3.4.0; marketplace v3.2.0): add one model-visible Feishu/Lark/Doubao entry that selects and reads the version-matched guide embedded in `lark-cli` while keeping detailed domain bundles as cold disk resources. It preserves domain-specific identity, confirmation, success, and verification contracts; unembedded resources require an embedded-vs-disk guide hash match. Tencent IMA remains an explicit exclusion. Two fresh-context review rounds closed the Creative Design resource, Calendar verification, and `cliHelp` recipe gaps, with no remaining Blocker/Major.
- **skill-governance** (`daymade-skill` v1.31.0; marketplace v3.1.0): replace cache-count governance with a five-layer contract for canonical source, installed inventory, discovery policy, the fresh model-visible catalog, and router-resolved runtime resources. The new read-only `audit_codex_skill_surface.py` compares `codex debug prompt-input` with complete metadata from Codex's own app-server `skills/list`, then detects description truncation/mismatch, enabled-but-omitted entries, identity/source collisions, exact disabled-path drift, stale policy, scan errors, missing direct activation entries, absent required routers, and optional user-defined catalog ceilings. Cold third-party bundles remain on disk behind exact-path discovery policy and must pass both fresh-prompt and representative resource probes. Lossless retirement checks every implicated user root plus `.skill-lock.json`, plugin metadata, and activation ownership before moving anything. Routine “one cache version” deletion and blind marketplace remove/add are retired in favor of Claude's orphan lifecycle and scope-preserving repair. Nineteen new standard-library regressions join the existing dual-root suite (40 total); existing-Skill regression classification, a two-pass fresh-context review, real-host replay, validator, marketplace validation, and security scan pass.
- **interaction-design-board** (`daymade-codex` v1.2.0; marketplace v2.2.0): add a test-time-scaling workflow for interaction decisions that static mockup skills cannot resolve. It freezes one business/task contract, generates isolated self-contained HTML candidates with distinct interaction hypotheses, builds a keyboard-accessible Focus/Compare Design Board, captures task-based selection or remix feedback, and requires confirmed `approved.json` behavior before production implementation. The standard-library builder rejects byte-identical candidates, path traversal, missing declared states, and external runtime assets; feedback works through gstack's current relative multi-Board daemon route, its legacy injected server URL, or direct-file JSON download. Prototype content identity stays separate from the daemon's runtime Board ID, and reload is explicit so repeated `serve` calls cannot silently display stale bytes. Ten deterministic regressions pass on macOS and Linux; an independent 16-case CSS parser matrix and a three-candidate browser replay cover state changes, Arrow-key tabs, note persistence, comparison mode, feedback writeback, identity separation, and same-URL reload.
- **git-safety-net** (v1.10.0): make repository-wide branch convergence safe while refs and dirty WIP are still moving. Mode E now treats `git cherry` as a squash-unsafe hint, builds keeper commits from owned immutable bytes, separates Git-object bundles from working-tree backups, re-enumerates local/hosted refs immediately before deletion, and verifies the user-visible one-main/WIP outcome. `git_export_before_drop.sh --verify-current BUNDLE` binds cleanup authority to the exact bundled ref tips and fails when any ref moved or disappeared; four new regressions join the checkout-discovery suite (12 total).
- **github-ops** (v1.1.0): add an outcome-first workflow for parallel and superseded PRs, squash/rebase landing verification, remote branch retirement, and REST fallback when gh's GraphQL path fails. It compares immutable behavior and acceptance tests before resolving conflicts, closes an equivalent PR instead of merging it for identity's sake, transplants only genuinely unique deltas onto a fresh base, and separates hosted branch authority from local remote-tracking caches.
- **skill-governance** (`daymade-skill` v1.30.0): add a read-only project dual-root audit for `.claude/skills` and `.agents/skills`. It pairs direct child bundles by frontmatter `name`, hashes complete bundle content plus executable bits, reports identical copies without pretending they cannot drift later, and fails on divergent full copies. A thin compatibility router passes only with an explicit marker, exactly one paired canonical `SKILL.md` target, a complete-read instruction, fail-visible behavior, and no second business-rules file; symlinked shared targets pass separately. Invalid identity/router state exits 2, real drift exits 1, and an empty wrong project cannot silently return green. Sixteen standard-library regressions run in the shared CI registry and on Linux; a real project replay distinguished canonical router, identical copy, drift, symlink-hidden drift, and single-root states.
- **codex-1m-context-window-setup** (`daymade-codex` v1.1.0; marketplace v2.1.0): add a model-aware `doctor` / transactional `apply` / drift-detecting `verify` workflow for Codex CLI and Desktop's shared base config. It resolves the selected model and live `debug models` contract instead of guessing, requests up to 1,000,000 raw tokens while respecting the declared maximum, reports the effective usable window, and sets automatic compaction to 60% of the attainable raw window. The conservative TOML editor changes only `model_context_window` and `model_auto_compact_token_limit`, preserves comments and unrelated tables, creates content-addressed backups only for changed bytes, uses atomic same-directory replacement with a concurrency check, and restores the exact prior file when strict-config validation fails. Sixteen standard-library regressions cover model caps (including models whose default already equals their maximum), the 1M/600K policy, human-readable diagnostics, idempotency, permissions, preservation, unsupported syntax, missing model contracts, and rollback for existing or newly created configs; the same suite passes on macOS and Linux.
- **local-conversation-history** (`daymade-claude-code` v1.58.0): add a first-class, read-only Codex verbatim-input path for the job the title-only inventory could not perform. `list_codex_user_inputs.py --recent N` takes the newest global prompt-ledger window and groups it by Session; repeated `--session-id` plus `--per-session N` expands an already selected set without reordering it. Both Markdown and JSON preserve exact wording, duplicate inputs, input chronology, and Session boundaries; Markdown headings contain only Session IDs and counts, never inferred topic labels. The Skill router now lets the requested output outrank background topic clues, so “show my recent original inputs for me to inspect” no longer gets misrouted to full-content keyword search. The prompt ledger is parsed strictly and any malformed or unsupported row aborts before output instead of yielding a complete-looking partial table. Six isolated regressions cover global-window grouping, explicit Session order, exact JSON text, duplicates, missing IDs, malformed ledgers, and incompatible flags; all 31 lister tests pass. Two live-store replays independently matched every selected text and order against the prompt ledger: 100 recent rows across 12 Sessions, and 280 rows across 13 explicitly expanded Sessions.
- **continue-codex-work** (`daymade-claude-code` v1.58.0): apply the record-ordinal handoff to the selected session itself, not only inherited ancestors. The former selected-session 6-user/4-assistant slices silently hid an early objective and remained capped under `--full`; selected briefings now retain every user turn and the first/latest assistant state before the next turn, exactly like the inherited timeline. A non-fork seven-user regression proves the earliest objective appears in both default and `--full` output; all 38 tests pass. The motivating fork replay still preserves the structural-safety objective, two-file state, missing-file gap, next step and final unanswered request in order while excluding the parent's post-fork bytes.
- **local-conversation-history** (`daymade-claude-code` v1.58.0): add a first-class, read-only Codex verbatim-input path for the job the title-only inventory could not perform. `list_codex_user_inputs.py --recent N` takes the newest global prompt-ledger window and groups it by Session; repeated `--session-id` plus `--per-session N` expands an already selected set without reordering it. The default Markdown stays a compact human-reading table: it preserves wording, duplicates, chronology, and Session boundaries, HTML-escapes literal markup/table delimiters, and never invents topic labels; `--format json` preserves the exact string value for machine or forensic use. The Skill router now lets the requested output outrank background topic clues, so “show my recent original inputs for me to inspect” no longer gets misrouted to full-content keyword search. The prompt ledger is parsed strictly and any malformed row or Session ID with surrounding whitespace aborts before output; a blank CLI Session ID fails even beside valid IDs instead of disappearing silently. Nine isolated regressions cover global-window grouping, explicit Session order, exact JSON text, duplicates, readable Markdown structure, invalid ledger/CLI IDs, missing IDs, malformed ledgers, and incompatible flags; all 34 lister tests pass. Two live-store replays independently matched every selected text and order against the prompt ledger: 100 recent rows across 12 Sessions, and 280 rows across 13 explicitly expanded Sessions.
- **continue-codex-work** (`daymade-claude-code` v1.57.0): make inherited context usable as a handoff, not merely present in the briefing. The parser now retains physical record ordinals for the richer user and assistant streams and renders a chronological continuation timeline containing every retained user turn plus the first/latest assistant state before the next turn; this keeps corrections attached to the state they corrected without replaying every tool-progress message. `task_complete.last_agent_message` is now a true fallback at its original ordinal—an early completed answer is no longer duplicated at the end merely because later commentary exists. Default output never drops a retained user turn because the actual objective can occur anywhere; it clips each message instead. `--full` removes character clipping and restores every state in assistant-only histories. Five new regressions cover mixed-stream ordering, non-relocation of an early task tail, an un-compacted parent whose objective falls outside the former role caps, long user timelines, and assistant-only full expansion. All 37 tests pass.
- **prior-work-retrieval** (`daymade-claude-code` v1.56.0): add an executable retrieve-before-produce harness over an explicit source manifest spanning current code, project SSOTs, Skills/SOPs, meeting transcripts, archived WeChat, and prior conversations. Each prompt-scoped run records per-carrier coverage, source authority and freshness metadata, immutable candidate IDs, and verified `reuse` / `adapt` / `reject` decisions; zero ranked hits never become an absence claim. Filesystem terms are combined into one `rg` pass per source and automatic adapters run with an explicit four-worker ceiling: on the real 15-source manifest this reduced a serial run that exceeded 90 seconds to 14.17 seconds while returning the existing recall hook, formal hybrid history index, global retrieval rule, and hook-health dependency. Companion Claude/Codex hooks gate only substantial production, preserve read-only repair paths and prompt-scoped user opt-out, additively install beside unrelated hooks, and retire the narrower unversioned `recall-first-evidence` registration. Twenty-four standard-library regressions cover source gaps, receipt invalidation, authority re-read, current-prompt scoping, both host tool shapes, legacy trigger families, installer idempotence, and Stop anti-loop behavior.
- **continue-codex-work** (`daymade-claude-code` v1.56.0): recover exact inherited fork lineage instead of treating a tiny child rollout whose only local prompt is `继续` as the task. The extractor follows every declared `history_base` edge root-first, reads each ancestor only through its recorded half-open byte snapshot, excludes parent events written after the fork, separates inherited actionable context from child-local turns, auto-expands every ancestor's retained summary when the child contains only a continuation cue, and prints progress before parsing each potentially large inherited prefix. Missing parents, cycles, mismatched IDs, out-of-range offsets, offsets through a JSONL record, and a selected rollout whose `session_meta.id` differs from the requested session now fail visibly; a parent ID without a byte boundary is reported rather than guessed from the current full parent. Seven new regressions cover single- and multi-level lineage, post-fork growth exclusion, continuation-only summary expansion, split offsets, conflicting parent IDs, selected-rollout identity, cycles, and missing byte boundaries; all 33 tests pass. A real two-ancestor replay recovered the previously hidden system-level objective in default mode while excluding a post-fork parent tail. Skill Creator's immutable-baseline audit classified 8 changed candidates with 239 exact preservations and passed; public quick validation and the security scan are green.
- **claude-code-history-files-finder** (`daymade-claude-code` v1.55.0): add an exact Codex session-ID metadata path and a bounded broad-scan contract. `analyze_sessions.py locate-codex <uuid>` now globs only filenames carrying that UUID, requires and validates authoritative `session_meta.id`, and reports active/archive copies without parsing unrelated rollout bodies; a sole UUID passed to `search ... --codex` auto-routes before any Claude or Codex corpus scan. One shared stop-loss clock now covers rollout discovery, the native `rg`/`grep` pre-filter, and structured parsing; each phase emits progress while active, defaults to 300 seconds, and exits non-zero on timeout or unreadable/malformed input instead of presenting partial matches as complete. `--codex-max-scan-seconds 0` is the explicit unbounded opt-in. The first fresh-context review rejected the frozen candidate and produced executable counterexamples: missing metadata was accepted through a filename fallback, the normal pre-filter could outrun both timeout and heartbeat, and tolerant JSONL I/O could become a complete-looking zero result. All three are now closed in the shared conversation core and finder. Eleven new finder regressions pass, alongside local-history and continue-codex-work suites; the shared-core drift check is green. On the motivating real store, exact lookup completed in 0.27 seconds instead of entering a multi-gigabyte full-history scan.
- **claude-code-history-files-finder** (`daymade-claude-code` v1.54.0): migrates the previously standalone Claude-history BM25/vector proof of concept into the maintained skill as a versioned, rebuildable recall index. The new `history_index.py` keeps exact forensic search authoritative while adding Chinese-aware BM25 and optional Qwen3/MLX vector recall for wording drift; unions active and registered archive copies by session identity, preserves source labels and internal timestamps, reports index freshness and incomplete vectors, and never turns zero ranked hits into an absence claim. Fresh builds now include the `chunks.usable` field the old POC query required but its schema omitted; failed rebuilds cannot replace the active database; failed incremental updates roll back as one transaction; and each database is bound to its full source/project scope so a later diagnostic subset cannot prune unrelated history. Chunk and vector completeness are separate gates, and model-revision mismatches fail instead of mixing embeddings. Ranked recall indexes only user/assistant prose after a real all-event smoke produced a 1.3 GB WAL; thinking, tools, attachments, queues, and file-history remain with exact search. Exact search also stops treating Claude's user-side `isSidechain` agent prompts as human messages by default while retaining assistant-side agent output and sidechain `tool_result` evidence. Verified by 110 isolated regressions plus real full-history lexical indexing and BM25 recall; the mutable index lives outside the skill bundle and the legacy POC database remains untouched during migration.
- **claude-code-hooks** (`daymade-claude-code` v1.53.1): new pitfall **#37** — a keyword-whitelist review-loop guard, once built, still needs calibrating against the phrasing its own author actually types. `review-loop-budget-guard.sh` (the mechanization pitfall #36 names as the fix for its own nothing-mechanically-enforces-this gap) never fired in a live session where the same artifact received three independent-review Agent dispatches back to back — exactly the pattern it exists to catch. Root cause: the guard's marker check was a fixed three-phrase list (`"independent review"`, `"independent reviewer"`, `"independent acceptance"`), but real dispatch prompts written per this skill's own discipline 5 phrasing ("an independent, fresh-context adversarial pass") insert methodology adjectives between "independent" and the terminal noun, so the literal substring check never fires. Replaying the incident session's own transcript (grep-extracted `tool_input.prompt` values, not reconstructed from memory) showed 4 of 5 real independent-review dispatches that session were invisible to the guard, including the exact 3rd dispatch on one lineage that should have crossed `BUDGET=2`. Fixed in the private hook script (not shipped from this repo) with a regex requiring `independent` + 0–3 words from a closed review-methodology adjective set + a terminal noun (`review|reviewer|acceptance|pass`); an open "any word(s) between independent and review" version was tried first and false-positived on 4 of 6 adversarial negative probes ("independent contractor review") before the closed set replaced it. The independent review this diff itself received (see below) then found the fix's own first-shipped adjective set was under-calibrated in the same way — it executed the shipped regex directly and found "second"/"skeptical"/"outside" all false-negative — so those three words were added too, with two more `--selftest` cases (four total) exercising them through the real call path. Verified three ways in ascending strength: hand-built positive/negative phrase probes; four `--selftest` regression cases in the guard; and — strongest — literal replay of the three real failing prompts extracted from the incident's own session JSONL, independently re-derived by the reviewer from the raw transcript, confirming silent/silent/correctly-triggered behavior with the right key. Cross-references rule 9 as this pitfall's false-negative mirror (rule 9's own worked example is the false-positive direction; its four-step replay method is direction-agnostic) and generalizes the lesson to every keyword/phrase-based hook in this skill, including to its own fix: a marker list is a claim about agent phrasing that goes stale the moment its own teaching material's recommended wording moves, and a first calibration pass is still a guess until an adversarial party probes it.
- **daymade-macos** v1.0.0: new suite-only Apple-platform namespace containing `capture-screen`, `developing-ios-apps` (canonical directory renamed from `iOS-APP-developer` to match its existing frontmatter name), `macos-cleaner`, and `macos-watchdog`.
- **daymade-codex** v1.0.0: new suite-only namespace containing `codex-image-gallery`, `local-codex`, and `design-style-picker` for Codex-assisted coding, generated-image review, and visual-style exploration.
- **local-conversation-history** (`daymade-claude-code` v1.51.0): add positive-only Codex advisory lock-state evidence to the existing one-command inventory. Every in-scope Codex row is probed, and a positive hit outside the recent-row limit is appended instead of silently missed. `writer-lock file held` proves only that some process held the exact canonical per-thread advisory lock during the snapshot; it does not identify the process or prove an open UI, a running agent, or progress, while an absent marker is never inverted into “stopped.” The probe coordinates through `.coordination.lock`, never creates/removes lock files, and returns visible `busy` / `partial` / `unavailable` boundaries; even injected per-thread unlock failures preserve the complete history result as `partial`. Codex JSON gains structured provider-level observation metadata, a `recent_rows` count, and per-row lock evidence while Claude/Kimi payload shapes remain unchanged. POSIX uses Python's standard-library advisory locks; Windows history listing remains intact while lock observation reports `unavailable` until an interoperable standard-library probe is verified. Five isolated lock regressions cover held-vs-stale, beyond-limit retention, coordination contention, malformed IDs, and unlock failure; all 25 lister tests pass on macOS and Linux, and a real multi-session store marks three main-thread lock files as held while leaving older rows unclassified.
- **github-sensitive-data-cleanup** (v1.1.0): commit-message channel for rewrite and verify, closing the Lesson 7 blind spot — `rewrite_history.py --message-replacements <file>` runs `git filter-repo --replace-message` in the same pass, and `verify_cleanup.py` fails on message-only leaks (#326). Follow-up independent-review fixes (#328): GBK/legacy-encoded commit messages crashed verification with an uncaught `UnicodeDecodeError`; SKILL.md rewrite command blocks (Step 4 and the script-reference section) omitted `--yes`, so a verbatim doc run exited before creating the backup; `git bundle verify` ran without `-C <repo>` and its `RuntimeError` escaped the `except`, crashing invocations from non-git working directories; and a FAILED message check now lists `commit_message_commits` hashes (first 10) instead of only a count. A docs-round review then found the same decode-crash class still open in the blob channel (`git grep`), so every subprocess decode in all four scripts is now hardened with `errors="replace"` — verified against a GBK-encoded source file containing a leak, which both channels now report instead of crashing (boundary: a UTF-8 pattern still cannot match GBK-encoded CJK bytes; that is Layer 4 semantic-review territory). `references/incident-lessons.md` gains Lesson 9 (tooling must be more robust than the repos it cleans). Review dossier archived in the author's private knowledge repo.
- **claude-code-hooks** (`daymade-claude-code` v1.49.0): turns rule 7's hookless-loop lesson into an executable **Loop Contract**. Any Stop-hook remediation or agent-driven review/wait/retry loop must predeclare an immutable lineage+failure-axis key, fire condition T, remediation R, decreasing variant V, cycle budget, and distinct success/capped exits before cycle 1. Repair commits stay inside the original lineage; independent review defaults to one initial pass plus one narrowly scoped re-review, and only a user-authorized new task can open another budget. Unrelated findings cannot reset it, while a remaining same-axis BLOCKER/MAJOR leaves the artifact visibly unshipped. Pattern E carries every contract field; Stop ceilings emit an explicit capped status, and pitfall #36 preserves the measured hookless-loop incident. Verification: one bounded with-skill replay, fresh-context review, existing-skill regression audit, quick validation, and reference-net checks.
- **claude-code-hooks** (`daymade-claude-code` v1.48.0): rule 7 gains a new closing case — **a loop can converge and still not have been worth running, and this shows up with no hook in the picture at all**. Everything rule 7 proves is that V *exists* for a hook-enforced loop; the same T → R → recheck shape recurs when an agent self-applies a prose discipline ("a substantive edit needs a fresh independent reviewer" — the exact rule the rule's own counter-example is built from) with no shell mechanism enforcing it, only the agent's own judgment deciding when to stop. Real incident: verifying one small correction in a low-stakes, single-reader document, an agent ran three full independent-review rounds instead of one — round 1 found unrelated real errors plus this one, round 2 (dispatched specifically to re-check round 1's fixes) found the correction was still slightly wrong, round 3 found nothing. Round 3 genuinely proves convergence in rule 7's sense, but "it terminates" and "it was worth running" are different questions, and a termination proof only answers the first. The fix sits beside V, not instead of it: before paying for the next iteration, name what breaks if you stop here, and only proceed if that outweighs the round's cost — none of mechanisms 0–4 ask this, because they all assume every triggered iteration is worth its cost, an assumption that breaks once R is "spawn an agent" rather than "re-run a script." Purely additive (0 regression candidates, 821 exact preservations).
- **local-conversation-history** & **claude-code-history-files-finder** (`daymade-claude-code` v1.47.0): new third native conversation source — **Kimi CLI** (kimi-code, `~/.kimi-code`, override `$KIMI_HOME`) — alongside Claude Code and Codex, for projects developed across more than one agent CLI. The shared `_conversation_core` gains `kimi.py`, bundled into all four conversation skills by `sync_core.py` as usual. The lister gains `--source kimi` / `--kimi-home`; the finder gains `--kimi` / `--kimi-home` (opt-in, same standing as `--codex`), aggregating matches at session level across a session's main and subagent wires with agent-prefixed match fields (`main:message`, `agent-0:tool_input`). Kimi timestamps come from internal fields only — state.json `createdAt`/`updatedAt`, wire `time`, or metadata `created_at` (epoch ms) — never file mtime. Titles prefer state.json, falling back to the first real user prompt in the main wire with the injected `<git-context>` wrapper stripped; weak auto-titles like "hi" lose to that prompt. Static boilerplate (config/profile system prompts, tool snapshots, usage/token metrics) is deliberately not indexed, so a keyword shared by every session's system prompt cannot manufacture a match. Format verified against Kimi CLI 0.38.0 (wire `protocol_version` 1.5) on a real 26-session store (26/26 inventoried with correct titles/projects; project-scoped keyword search validated in both directions); Kimi CLI's own `kimi export [sessionId]` only exports single sessions as ZIP and has no cross-session inventory or search, which is why the raw store is parsed directly. Ships with 17 new unit tests (8 lister + 9 finder) over isolated fixtures; both pre-existing suites (12 + 83) stay green. Regression audits: lister 10 candidates / 246 exact preservations, finder 7 / 675 — all candidates are one-directional expansions (old clause preserved verbatim inside the widened sentence), reviewed and verified.

### Changed
- **prior-work-retrieval / continue-codex-work** (`daymade-claude-code` v1.56.0 hotfix): close all six independently reproduced post-merge acceptance findings without adding new scope. Bash and Codex exec write paths now enter the receipt gate; an exact manifest repair remains possible while configuration is broken; installer ownership uses the exact supplied wrapper identity instead of substring deletion; malformed command-adapter rows are failed coverage; candidate Git HEAD drift invalidates reuse; and the selected Codex rollout identity is checked before lineage traversal.
- **claude-code-history-files-finder** (`daymade-claude-code` v1.56.0): bound real MLX embedding memory after the former batch-64 loop was user-observed beyond 70 GiB and was killed with exit 137. Embedding now defaults to batch 16 with an 8 GiB total MLX limit and 0.5 GiB cache limit, streams missing rows instead of `fetchall()`, releases arrays and clears the Metal cache after every batch, reports the configured limits and observed MLX peak, and fails at the configured boundary instead of relying on system OOM. A 90-second real-index canary embedded 1,872 chunks with observed process RSS near 1.5 GiB and a 2.13 GB MLX active-memory peak; 17 isolated history-index regressions remain green.
- **git-safety-net** v1.9.0: add an outcome contract ahead of audit and preservation so Git safety work cannot silently replace the user's job. The skill now freezes the user-visible outcome, current authorized phase, named targets, and stop condition; separates read-only evidence scope from action scope; limits machine-wide discovery to exhaustive or unknown-target audits; preserves only what the next authorized destructive action threatens; and classifies temporary bundles, diffs, snapshots, and transport chunks as repository-external recovery material rather than Git/LFS content. Unexpected bundle size or a stalled upload is now a re-plan signal, not a prompt to invent another transport. High-stakes adversarial verification defaults to one independent pass, with fan-out requiring distinct evidence axes and user authority.
- **git-safety-net** v1.8.0: close two linked-worktree retirement gaps observed in a real no-loss cleanup. Checkout discovery now derives repository freshness from the newest `FETCH_HEAD` receipt across the common Git directory and every linked-worktree admin directory, so a fetch run from either primary or linked checkout refreshes the verdict for their shared remote refs without contaminating independent clones. Isolated, environment-hermetic regressions pin both fetch directions and clone isolation. The retirement gate now separates Git-clean state from ignored physical files, requires uncertain ignored content to be copied because bundles cannot reach it, freezes the complete ignored path/type/hash-or-link-target manifest, repeats that inventory as the last pre-remove gate, and rechecks surviving copies after removal. It also verifies path removal, worktree deregistration, and recorded-HEAD recoverability after non-forced removal. Branch deletion remains a separate authorization.
- **tibo-reset-codex** v1.0.0 → v1.1.0: fix the announcement-only blind spot exposed by the unannounced 2026-08-25 quota restoration. The skill now treats product usage changes as account-level direct evidence, recognizes a time-clustered multi-account silent platform reset only after ordinary per-account schedules are ruled out, separates source families so two Tibo mirrors no longer masquerade as independent confirmation, reads known X URLs through Jina when direct X fails, and forbids turning an empty tracker result into “no reset.” A verdict-first output contract now requires the agent to state the strongest supported conclusion before evidence boundaries instead of making the user choose among candidate explanations. Verified against the observed silent-reset case and the negative single-account weekly-reset case.
- **continue-codex-work** (`daymade-claude-code` v1.53.0): a `task_complete` rollout event carrying an `error` (e.g. `usage_limit_exceeded`, `context_window_exceeded`, `unauthorized`, `cyber_policy`) with no closing message was classified as "Clean exit" — the parser never read the `error` field (#338). Grounded in a bounded scan of the local `~/.codex/sessions` corpus (6,650 rollouts, ~33GB): 468 real error-carrying `task_complete` records, 6 distinct `codex_error_info` values, a stable 2-key shape. `task_error` is now captured on every `task_complete` (last-wins, mirroring the existing `task_tail` handling), so a later clean turn correctly clears a stale earlier error. 464/468 corpus cases had no closing message → new end-reason `"errored"`, inlining the exact error; 4/468 had a real closing message anyway → stays `"completed"`, with a visible caveat rather than hiding the error. `usage_limit_exceeded`/`internal_server_error` additionally surface a hint that the original process may resume on its own — motivated directly by the session that exposed this bug, where the underlying Codex process did resume and finish independently of an in-progress manual continuation once its quota reset (that session's own real error tail, re-checked against its original un-grown bytes, was a clean `errored` case with zero open calls). A follow-up commit closes a second interaction found by independent review, not observed in that motivating session itself: `_detect_end_reason` checks `open_calls` before the new error logic, so a dangling tool call plus a `task_complete` error classified as "interrupted" with the error detail invisible everywhere — not rare in general, since those exact error codes are the ones likely to strand a call mid-flight. Separately, Codex's own `update_plan` tool call had no dedicated handling — it competed with thousands of other tool calls for the generic "Recent Tool Calls" list's last-20 window and 120-char preview, so in a long session (6,540 tool calls in the motivating session) the most recent plan state was reliably evicted or truncated; it now renders in its own `## Latest Plan State` section (schema stability confirmed on a ~4,000-call sample, 0 parse failures), exempt from both limits. `scripts/_core/` untouched. 10 new fixture tests built from the real corpus shapes; all 16 pre-existing tests pass unchanged (26/26 total). Existing-skill regression audit passed both rounds; two rounds of independent fresh-context review (correctness + scope fidelity, then a targeted recheck of the follow-up fix). Post-merge, a session self-review caught two evidentiary errors in #338's shipped text: the corpus split was mis-summed as 466/2 (correct: 464/4, re-summed from the raw scan output), and the open_calls interaction was described as "confirmed on the real motivating session" when it was never observed there — both corrected in this release across the code comments, tests, and SKILL.md; PR #338's description was fixed on GitHub with a correction comment.
- **marketplace-dev** (`daymade-claude-code` v1.52.0): add a dedicated standalone-to-suite consolidation route for creating or extending suite plugins, moving/renaming canonical skill directories without changing bundle behavior, removing superseded standalone registrations, closing repository-wide install/path drift, publishing an installed-user migration, validating through an isolated real install/cache footprint, and freezing the result for independent review before PR merge. The detailed workflow lives in a directly linked bundled reference; the main SKILL remains the router.
- **skill-governance** (`daymade-skill` v1.29.0): add post-merge suite-migration reconciliation that installs and verifies replacement suites before retiring old standalone identities at their original scopes. Remove hand-maintained suite-name inventories from the skill and repository instructions, and derive suites from non-empty `plugins[].skills` arrays in the current manifest, eliminating the drift that omitted `daymade-codex` and `daymade-macos` immediately after their introduction.
- **feishu-doc-scraper** v1.4.0: separates faithful extraction from durable storage so a successful download can no longer be treated as permission to put MP4/XLSX/DOCX/PDF/image bytes into Git or Git LFS. The new source-first artifact contract keeps searchable Markdown/CSV/JSON/HTML plus provenance in Git, treats Feishu originals as the default raw-binary source of record, reserves OSS for an explicitly chosen independent replica, and marks local downloads as optional caches. A bundled fail-closed validator rejects raw binaries declared as Git storage, external artifacts without stable locators, and cache paths masquerading as authoritative paths; whiteboard and sheet-attachment workflows now apply the same boundary.
- **Suite-only distribution migration**: move `capture-screen`, `developing-ios-apps`, `macos-cleaner`, and `macos-watchdog` under `daymade-macos`; move `codex-image-gallery`, `local-codex`, and `design-style-picker` under `daymade-codex`; move `benchmark-due-diligence` under `daymade-financial`; and move `excel-automation` under `daymade-docs`. Their standalone marketplace entries are removed; skill bundles and runtime behavior remain unchanged.
- **daymade-docs** v1.8.0 → v1.9.0: add `excel-automation` as a suite member.
- **daymade-financial** v1.1.0 → v1.2.0: add `benchmark-due-diligence` as a suite member.
- **marketplace-health-check** v1.0.0 → v1.0.1: update safety-audit sample paths for the nested `daymade-macos/macos-cleaner` and `daymade-financial/financial-data-collector` canonical sources.
- **Migration for existing installs**: run `claude plugin marketplace update daymade-skills`, install `daymade-macos@daymade-skills`, `daymade-codex@daymade-skills`, `daymade-docs@daymade-skills`, and/or `daymade-financial@daymade-skills` as needed, verify the new `<suite>:<skill>` invocation, then uninstall the superseded standalone plugin record. Update scripted invocations to the suite namespace; `iOS-APP-developer:developing-ios-apps` becomes `daymade-macos:developing-ios-apps`.
- **tunnel-doctor** v1.9.0 and **debugging-network-issues** v1.7.0: reduce the active network entry points from three to two. `tunnel-doctor` now owns concrete local path operations—Tailscale, TUN, DNS/routes, WSL/Docker propagation, and single-hop or chained proxy node/exit capacity—while `debugging-network-issues` remains the generic falsification/layer-isolation fallback for unknown or application/protocol failures. The new proxy-capacity reference requires serial same-load node comparison, real-client verification, and replay of the original complete workload before changing application semantics: a recovered representative rate plus `ls-remote` or a partial clone is not proof that full clone semantics must change. Grounded in one explicitly approved, redacted Codex session and RFC 6349's separation of sustained TCP throughput from RTT/liveness.
- **local-conversation-history** (`daymade-claude-code` v1.51.1): make the inventory-vs-content-search decision explicit before any tool call. Requests such as “I remember we did X,” “find that old conversation,” or “did we discuss Y?” now route directly to `claude-code-history-files-finder` even when phrased as “historical conversation records”; unknown provider scope must cover Claude, Codex, and Kimi CLI, unknown project scope must cover all projects, and the current session must be excluded before a fresh self-match is accepted as historical evidence. Recent title/time/session-ID inventory remains a single bundled-command path, and the inventory script itself is unchanged. A real DINO-history prompt is retained as development coverage for this distinction.
- **skill-creator** (`daymade-skill` v1.28.0): defines compression as a behavior-equivalence claim instead of a synonym for “shorter.” Existing-skill edits must classify each delta before writing: lossless relocation/deduplication, capability retirement, scope narrowing, workflow/safety redesign, bug fix, or lossy summarization. Scenario reachability now carries the proof burden—trigger, decision inputs, exact action, confirmation/stop, recovery, and verification must remain executable; grep/string survival alone cannot certify preservation. Independent review also gains a frozen boundary (immutable artifact, reader spec, blast radius, failure axes, terminal condition): current-change regressions and newly elevated legacy defects block release, while untouched historical defects become explicit backlog hypotheses rather than silently expanding the task. Grounded in the `macos-cleaner` v1.4.0 compression audit, where both failure directions occurred in one task. Verification: existing-skill audit found 0 unmatched candidates across 2,974 exact preservations; the local suite passed 179 tests plus 7 subtests.
- **macos-cleaner** v1.3.0 → v1.4.0: adds a targeted Apple Content Caching / `AssetCacheManagerUtil` workflow grounded in a real macOS 26.5.2 repair and Apple's supported command-line controls. It distinguishes logical `CacheUsed` from physical `ActualCacheUsed`, verifies peers without touching them, protects co-resident services, separates read-only diagnosis → plan/confirmation → supported mutation → APFS/service verification, and fail-fasts on partial deactivation or purge. The main SKILL.md is now a compact route-and-safety layer instead of a duplicated manual; the Mole, cleanup-target, report, and safety references follow the same phase contract instead of retaining broad immediate-cleanup instructions. The unknown-source route restores an ordered short-circuit sequence, establishes an explicit success target, names every fixed scanner scope, and stops only on candidates with defensible physical-release plans; optional duplicate detection is read-only and path-scoped, with per-file Finder-Trash handling after explicit keep/remove decisions. The original Xcode/npm/uv/Playwright/iOS/model/JetBrains cache trade-offs and narrow npm `_npx` route remain reachable from named-cache requests, now with targeted path authority, allocated-size measurement, in-use checks, exact actions, and postconditions. Docker metadata remains read-only, while temporary-container volume inspection has a separate no-pull/no-network/read-only authorization gate and object-size reports permit honest unknown/upper-bound host release estimates. `cleanup_report.py` is wired back into local before/after verification, defaults to `/System/Volumes/Data`, records and prints the measured volume and offset-aware timestamp, returns nonzero on baseline failure, and refuses legacy, stale-order, or cross-volume comparisons; nine deterministic tests cover that contract. The contradictory `docker builder prune` exception is intentionally retired under the prune prohibition: build cache remains measurable, but deletion is explicitly outside the skill's execution scope.
- **continue-codex-work** (`daymade-claude-code` v1.50.0): close three silent briefing gaps against current Codex rollouts and give every truncation an exit, with version claims now measured on ~2,600 real rollouts (0.142.2–0.149.0) instead of a handful of samples. (1) **Turn stream drift**: the `event_msg/user_message` / `agent_message` mirror stream — the parser's only turn source — is the norm through 0.146.x and in the 0.147/0.148 alphas, but stable 0.147.0 drops it for most sessions, so `Last User Requests` silently vanished; the parser now also reads `response_item/message` (assistant `output_text` decoded locally — the shared `extract_text` is deliberately untouched) and lets the **richer stream win per role** (ties go to the event stream), because the streams measurably diverge in both directions and per role (0.142.3/0.143.0/0.144.0 keep per-step commentary only in the event stream, while mid-turn queued user inputs appear only in message records — whole-stream selection was measured to lose the final user request on real dual-stream files). Inter-agent `response_item/agent_message` traffic is never parsed as main-thread text, and `task_complete.last_agent_message` remains a tail safeguard. (2) **Files Edited vanished on 0.147+** the same way: `patch_apply_end` is gone (0 vs 1086 `item_completed`/`FileChange` items in one measured session), so file edits and failed-patch errors are now read from the `FileChange` envelope; both sources union into one set. (3) **Truncation had no exit**: long sections ended in a silent "..." and the Limitations section said "read the rollout line directly" without saying how — which cost a real resume session two wrong schema guesses; truncated sections now print a `rerun with --full` hint at the cut point and `--full` prints complete text. Also: skill-invocation bundles delivered as user messages (measured 2.7–148 KB) collapse to a one-line marker instead of evicting a real request; image-only user messages render as `[image-only user message]` instead of vanishing; `turn_aborted` classifies as interrupted and a commentary-phase tail as in progress rather than completed. 16 synthetic-fixture tests pin the per-role stream selection in both directions, inter-agent exclusion, the `task_complete` safeguard, FileChange success/failure, both markers, the truncation contract, and the end-reason shapes — registered in `scripts/ci/test-suites.txt` so CI actually runs them. Real-corpus verified on a 187 MB / 22-compaction 0.147.0 rollout (Files Edited restored: 44 files) and dual-stream July rollouts.
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
