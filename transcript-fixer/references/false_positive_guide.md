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

## Forcing a risky addition

If you understand the risks and still want to add a flagged rule:
```bash
uv run scripts/fix_transcription.py --add "仿佛" "反复" --domain general --force
```
