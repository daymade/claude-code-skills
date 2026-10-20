# Metadata and correction-ledger provenance

Read before editing ASR-derived metadata or writing/reversing a correction ledger.

**Correction scope includes the metadata lines, not just the body.** A filed transcript usually carries ASR-derived metadata — a `Keywords:` line, frontmatter, a title — and those lines contain the *same* recognition errors as the spoken body (e.g. a `Keywords:` line still listing `克劳锐` when every body mention was already corrected to `Claude`). Fix them with the same rules. There is no "metadata is sacred, leave it" exception: the metadata is a search/grep surface too, and a keyword left in its ASR-garbled form will silently fail every future `grep Claude` while the body looks clean. When you re-grep the final file to confirm a correction landed, include the metadata lines in that check.

**One metadata field is the exception by design: `asr_note`.** When you record a run's correction history in the transcript's frontmatter, use the key `asr_note` — Stage 1 masks its value before matching, so the verbatim old forms your ledger cites (`修正含：<old-form>→<canonical>`) never re-fire as phantom matches, and no phantom review items get enqueued from it. The field stays a full-fidelity ledger; the masking keeps line numbers exact and splices the ledger back untouched. Before this existed, one such ledger line produced 18 phantom Stage 1 matches and 9 phantom queue enqueues on every re-run — a per-file tax that recurred forever. **Two constraints, both load-bearing: the value must sit on the same line as the key (single-line flow style — a multi-line `asr_note: |` / folded value is out of the masker's reach and stays unprotected), and other frontmatter keys are processed normally — keep correction ledgers under `asr_note` and nowhere else.**

**A third rule, for any process that WRITES `asr_note` into frontmatter (not just transcript-fixer reading it back): grep for an existing `^asr_note:` key first and MERGE — never blind-append a second `asr_note:` line.** Two `asr_note:` keys is a YAML duplicate key — invalid per spec: strict parsers reject it, and permissive ones (PyYAML included) silently keep the last value and drop the earlier ledger with no error. Real case 2026-09-20: a batch closure process appended a second `asr_note:` to 8 transcripts; `sync-feishu-minutes`' audit archive-scan rejected the invalid frontmatter (exit 2, coverage unknown) and blocked a date sweep until all 8 were merged back to one single-line key. The masker above protects the tool from old forms *inside* the value; nothing protects a reader from a *duplicated key* — that check is the writer's job.

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
