# Metadata and correction-ledger provenance

Read before editing ASR-derived metadata or writing/reversing a correction ledger.

**Correct ASR-derived metadata as well as the spoken body.** Titles and keywords
are search surfaces and can carry recognition errors after the body is corrected.
Include them in the final correction check; distinguish them from the audit
values below.

## Protected audit values

Correction history and pending candidates are evidence rather than another utterance.
In a complete leading YAML frontmatter block:

- `asr_note` holds correction history, including verbatim old forms. Keep its value
  on the same line as the key. Multi-line `asr_note: |` / folded values remain
  unsupported by the masker and emit a warning; do not assume they are protected.
- `asr_pending` holds pending IDs or candidate audit data. Its scalar, block
  list/scalar and flow list/map values are protected, including continuation rows.
  Do not text-correct quoted candidates as if they were spoken words.

The shared boundary is implemented by `_mask_ledger_spans` and
`project_without_ledger_values` in [dictionary_processor.py](../scripts/core/dictionary_processor.py).
Matching, scanner projections and review acceptance/reversal use this boundary;
audit values round-trip intact and newline positions remain truthful. Ordinary
titles, keywords and body text stay in correction scope. Reversal also retains
the legacy protection for standalone `asr_note:` lines outside frontmatter.

## Writing and native edits

Before writing `asr_note`, check for an existing `^asr_note:` key and merge its
history; never append a duplicate key. Duplicate-key rejection belongs to the
writer: permissive YAML readers can silently discard earlier values.

**The masker guards Stage 1's matcher — it does not guard YOUR edits.** It runs
inside the dictionary pass, so it stops the *tool* from re-firing on the old
forms your ledger cites. Nothing stops a whole-file `sed -i` or
`text.replace(old, new)` in the native pass from rewriting those same citations,
because that replacement never goes through the matcher at all. The failure is
silent and it corrupts the one artifact whose entire job is to record what you
did.

So in the native pass, **anchor every body edit**: replace at a known line
index, or include enough surrounding words that the frontmatter cannot match.
Reserve whole-file replacement for tokens you have just confirmed appear nowhere
in the frontmatter. After any reversal, re-read the ledger line itself: it should
still name the original decision *and* the overturn — `A→B（据X，后经Y推翻，终态C）`
— because "what was decided, then corrected" is the provenance; "what turned out
right" alone is not.
