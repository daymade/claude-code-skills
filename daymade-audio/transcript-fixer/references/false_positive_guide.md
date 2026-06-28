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

## Two layers of defense (and why the word list is the weak point)

The guard fires at two points, and both read `utils/common_words.py`:

1. **Add time** — `--add` runs `check_correction_safety()` and blocks a rule whose `from_text` is a known common word or a substring-collision source (override with `--force`).
2. **Apply time** — Stage 1 defaults to **safe mode**: `_assess_risk()` grades every rule and only low-risk (non-word, high-confidence) ones auto-apply. Common-word / ≤2-char / real-word-fragment rules are written to `*_needs_review.md` instead. So even a bad rule already sitting in the database won't silently corrupt a transcript unless you pass `--apply-all`.

The catch: both layers are only as good as the word list. **A real word missing from `common_words.py` is invisible to *both* checks** — that is exactly how `多深`, `小龙虾`, and `早生` slipped in and then got applied (fixed 2026-06; they are in the list now). So when you find a false positive whose `from_text` is a genuine word, add it to `common_words.py` — not just to the per-rule disable list. That fixes the whole class, not the one instance.

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

## The 4+ char real-word blind spot (important)

The risk classifier and the common-word list only catch short / listed words. A rule whose `from_text` is a **4+ character string that is itself valid Chinese** (`济南大学`→`暨南大学`, `关税证明`→`完税证明`, `老公说的`→`老郭说的`) is classified `low` and **auto-applies even in safe mode** — silently corrupting clean transcripts that legitimately contain that phrase. The common-word list cannot scale to this: Chinese has hundreds of thousands of valid multi-char phrases.

`--audit` flags these with a `valid_phrase` warning, using a jieba heuristic (`is_likely_valid_phrase`): it reports rules whose `from_text` decomposes entirely into known dictionary words. **This is advisory and deliberately low-precision** — it also flags many legitimate ASR-garble rules (e.g. `一视同然`→`一视同仁`, where `from_text` happens to split into known tokens). When reviewing `valid_phrase` hits, the question to ask is *"is `from_text` itself a fluent, real phrase someone would actually say?"* — if yes, it's a dangerous rule (disable it); if it's garble that merely tokenizes cleanly, keep it. This is why the heuristic never gates auto-application: a false flag there would silently cut recall. Genuinely closing this class needs language-model-grade judgment.

**Disabling audit hits is a human decision — never automate it.** When you act on `valid_phrase` (or any audit) results, review each candidate by hand; do NOT bulk-disable everything flagged. Roughly half a batch can be context-specific GOOD rules the audit mislabels, because neither jieba nor an LLM reviewer knows the dictionary owner's context — which products/terms they say often. `GDP 5.5→GPT 5.5` reads as "GDP is a common word" to any general reviewer, yet is a correct `GPT 5.5` ASR fix for an AI-heavy user; `长城任务→长程任务` (same pronunciation) is a correct "long-horizon task" fix. Even an LLM review pass (more accurate than jieba) mislabeled ~half a batch this way in practice. So: the audit surfaces candidates, the **owner** decides, and you back up the DB (`cp corrections.db corrections.db.bak-…`) before any disable so it is reversible.

## Forcing a risky addition

If you understand the risks and still want to add a flagged rule:
```bash
uv run scripts/fix_transcription.py --add "仿佛" "反复" --domain general --force
```
