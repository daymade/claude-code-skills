# False Positive Prevention Guide

Dictionary-based corrections are powerful but dangerous. Adding the wrong rule silently corrupts every future transcript. The `--add` command runs safety checks automatically, but you must understand the risks.

## What is safe to add

- **ASR-specific gibberish**: "巨升智能" -> "具身智能" (no real word sounds like "巨升智能")
- **Long compound errors**: "语音是别" -> "语音识别" (4+ chars, unlikely to collide)
- **English transliteration errors**: "japanese 3 pro" -> "Gemini 3 Pro"

## What is NEVER safe to add

- **Common Chinese words**: "仿佛", "正面", "犹豫", "传说", "增加", "教育" -- these appear correctly in normal text. Replacing them corrupts transcripts from better ASR models.
- **Words <=2 characters**: Almost any 2-char Chinese string is a valid word or part of one. "线数" inside "产线数据" becomes "产线束据".
- **Both sides are real words**: "仿佛->反复", "犹豫->抑郁" -- both forms are valid Chinese. The "error" is only an error for one specific ASR model.

## Defense layers and guard state

1. **Add time** — `--add` runs `check_correction_safety()` and blocks a rule whose `from_text` is a known common word or a substring-collision source (override with `--force`); a bare number or a single surname + 老师/总 is an error in every mode, with no override, because it names timestamps or everyone with that surname.
2. **Apply time** — In default safe mode, `_assess_risk()` grades each rule and medium/high-risk candidates remain in the review report and queue. A low-risk label is a screening result, not proof that the occurrence is correct. Selected-domain trust and occurrence-specific deferral follow [Stage 1 variant matching](dictionary_identity_and_context.md#stage-1-variant-matching).
3. **Match time** — `DictionaryProcessor` refuses a match at the position itself, before risk scoring, when the corrected form is already in place (superset check), when a short rule sits inside a longer listed common word, or when the match is a fragment of real words. That last check picks its rule by script: an ASCII match with an ASCII *letter* directly before or after it is inside a longer word (`Cloud` in `iCloud`, `Joe` in `Joey`; digits do not count, so `cloud3` and `fiber5` still correct); a match containing CJK is refused only when every segment of a dictionary-only jieba cut (HMM off, nothing invented) that overlaps it is a multi-character word and at least one of them crosses a match boundary — 新一 in 更新|一下, 下电 in 楼下|电动车, 问题记 in 问题|记录, 同龄 in 同龄人. One single-character segment under the match is what an unknown fragment looks like, so 巨|神智|能, 章|伟大|概 and 叫|新|一下|单 all pass through to risk scoring. Refusals are counted as `Refused at word boundaries` (summary) and `boundary_refused` (JSON), listed in the summary, and never deferred, so a rerun no longer re-defers the same fragments. When the check is wrong: `--apply-all` disables this straddle check and bypasses risk deferral; superset and listed-common-word refusals remain; a context rule (`--add-context-rule`) skips it for one phrase but is still risk scored, so in safe mode that match is deferred to the review queue, where it is accepted like any other row. The cut itself depends on jieba's bundled dictionary (`requirements.txt` pins only a floor), so the examples here hold for the dictionary shipped with jieba 0.42.1. **Without jieba the CJK half of this straddle check does not run**. Its diagnostic is: a one-time stderr warning, a `Refused at word boundaries: CHECK OFF` line in the summary instead of a count, and `boundary_check_active: false` in the JSON. Read that flag before trusting `boundary_refused`; on its own, `0` cannot distinguish "nothing straddled" from "nothing was examined". Blind spots, both directions: a real mishearing whose neighbours complete whole words on both sides is refused; a fragment whose neighbours are single-character or out-of-vocabulary words (的是 in 看它的是什么, 书妙 in 飞书妙记) is not — safe mode still defers it as before, so "a rerun no longer re-defers the same fragments" holds only for words jieba knows. The separate entity-tail guard follows [Stage 1 variant matching](dictionary_identity_and_context.md#stage-1-variant-matching); its missing-segmentation behavior is independent of this straddle-check status.

Word-list screening cannot recognize a real word absent from `common_words.py`. When a confirmed false positive's `from_text` is a genuine common word, add it to that list rather than relying only on a per-rule disable.

## The corpus answers what the word list cannot (project-domain rules)

The word-list checks answer "is this a real word **in Chinese**". A project-domain rule needs a different question answered: "when this word appears in **this project's** transcripts, is it ever the real meaning?" That is empirical — measure it before deciding the rule's shape:

```bash
uv run scripts/fix_transcription.py --probe "候选词" --corpus /path/to/transcripts/
# or inline during the add:
uv run scripts/fix_transcription.py --add "候选词" "正确词" --domain myproject --check-corpus --corpus /path/to/transcripts/
```

Read the sampled context windows, then decide by **in-corpus real-meaning frequency**:

| In-corpus reality | Rule shape |
|---|---|
| 0 occurrences (the term never appears at all) | bare rule is zero-risk, but compounds nothing until the term actually recurs — and if you expected hits, re-check the corpus path (a probe cannot tell "absent" from "never searched") |
| Every sampled occurrence is the ASR error | bare rule is likely safe — **even if the FROM side is a "real word"** (a colleague's name ASR keeps garbling: every in-corpus occurrence of the garbled form IS them). Mind the coverage line: samples are capped, so occurrences in unsampled files were never inspected |
| Mixed (real meanings present) | anchored rule (`--add "搭配短语" "修正短语"`) or no rule — record the trap in the domain context file |
| Real usage dominates | do not add; context-file trap only |

Both directions of intuition fail without the measurement: "obviously an error form" turns out to carry real meanings all over one corpus, and "obviously a real word" turns out to be the mishearing in 100% of another corpus's occurrences. The probe makes the shape decision a 30-second lookup instead of a guess.

## When in doubt, use a context rule instead

Context rules use regex patterns that match only in specific surroundings, avoiding false positives:
```bash
# Instead of: --add "线数" "线束"
# Use a context rule in the database:
sqlite3 ~/.transcript-fixer/corrections.db "INSERT INTO context_rules (pattern, replacement, description, priority) VALUES ('(?<!产)线数(?!据)', '线束', 'ASR: 线数->线束 (not inside 产线数据)', 10);"
```

## Auditing the dictionary

Run `--audit` periodically to scan all rules for false positive risks:
```bash
uv run scripts/fix_transcription.py --audit
uv run scripts/fix_transcription.py --audit --domain manufacturing
```

## Screening 4+ character real phrases

In ordinary safe-mode risk scoring, a 4+ character FROM recognized as a valid
Chinese phrase is promoted to medium risk unless its confidence is at least
0.95 and its length is at least 5. Selected-domain trust and context-veto
precedence follow [Stage 1 variant matching](dictionary_identity_and_context.md#stage-1-variant-matching).
A real phrase can therefore still auto-apply; tokenization is not proof that
this occurrence is an ASR error.

`--audit` uses the same jieba heuristic (`is_likely_valid_phrase`) to flag
`valid_phrase` candidates whose FROM decomposes into known dictionary words.
The audit warning is advisory: it also catches legitimate garbles such as
`一视同然`→`一视同仁`. Judge whether FROM is a fluent phrase appropriate to the
occurrence; keep a valid recurring ASR rule rather than disabling it solely
because the heuristic flagged it.

**Disabling audit hits is a human decision — never automate it.** When you act on `valid_phrase` (or any audit) results, review each candidate by hand; do NOT bulk-disable everything flagged. Roughly half a batch can be context-specific GOOD rules the audit mislabels, because neither jieba nor an LLM reviewer knows the dictionary owner's context — which products/terms they say often. `GDP 5.5→GPT 5.5` reads as "GDP is a common word" to any general reviewer, yet is a correct `GPT 5.5` ASR fix for an AI-heavy user; `长城任务→长程任务` (same pronunciation) is a correct "long-horizon task" fix. Even an LLM review pass (more accurate than jieba) mislabeled ~half a batch this way in practice. So: the audit surfaces candidates, the **owner** decides, and you back up the DB (`cp corrections.db corrections.db.bak-…`) before any disable so it is reversible.

## Forcing a risky addition

If you understand the risks and still want to add a flagged rule:
```bash
uv run scripts/fix_transcription.py --add "仿佛" "反复" --domain general --force
```

## Re-adding a disabled rule

`--report-false-positive FROM TO` soft-deletes a rule (`is_active=0`) rather than removing it — the row stays so the audit trail is preserved and the exact `(from_text, domain)` can't be silently re-inserted. If you later want that `from_text` back — most often because the disable was really about a **wrong target** (the rule was disabled because it pointed at the wrong correction, and the right fix is a different target) — re-running `--add` does **not** silently resurrect it:

```bash
# Without --force: reports the disable and refuses, so a deliberate
# false-positive disable is never un-done by accident.
uv run scripts/fix_transcription.py --add "小茗" "小明" --domain demo
# -> Correction '小茗' -> '小名' exists in domain 'demo' but is DISABLED
#    ([FALSE POSITIVE reported by <user>]), added 2026-01-01 ...
#    To reactivate it with target '小明', re-run with --force.

# With --force: reactivates (is_active=1) AND updates the target,
# writing a reactivate_correction audit entry.
uv run scripts/fix_transcription.py --add "小茗" "小明" --domain demo --force
```

Reactivating restores the rule to `--apply-all` (and, per its risk grade, safe-mode) behavior, so re-verify it the same way you would a fresh `--add`.
