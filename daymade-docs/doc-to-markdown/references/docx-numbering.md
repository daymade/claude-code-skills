# DOCX generated numbering

Use this procedure for Word questionnaires, numbered instructions and list-heavy
documents. Word stores generated labels in `numbering.xml`, outside paragraph
text runs. Missing labels in an extraction do not prove that the source has none.

## Convert without changing the original

Run `scripts/convert.py` normally. Its Pandoc path uses
`scripts/docx_numbering.py` to add a missing `ilvl` only where the level is
unambiguous: a sole abstract level defaults to zero; an override uses its enclosing
level index. It changes only `word/numbering.xml` in a disposable DOCX and preserves
the other ZIP members' payloads and XML prefixes. Multiple implicit abstract levels
are ambiguous and fail explicitly. This repair does not apply to legacy `.doc`,
the experimental `--docx-deep` path or a different converter's output.

## Check the original independently

```bash
python3 scripts/validate_output.py source.docx converted.md --json
```

Require `source_numbered_item_count` to equal the expected generated decimal item
count and `numbering_equal: true` when that count is positive. A count of zero is
not evidence for a source known to show numbered questions in Word.

The checker reads the original OOXML paragraph/style properties, numbering
instances, starts, overrides and restarts independently of Pandoc. It compares
decimal ordinals, list depth and paragraph binding with the Markdown AST. Plain
unnumbered paragraphs and literal text labels are not counted as generated labels.
The existing text/numeric comparison still uses Pandoc and remains a separate
diagnostic; it cannot replace the OOXML check.

Lost labels, changed starts or hierarchy produce a failed result. Unsupported
formats such as Roman numerals or linked numbering styles fail as unavailable
comparisons; inspect those in Word and the actual output reader. This check does
not certify list glyph styling, compound prefix rendering, numbering inside images
or fields, all document structure, or reader access. Bullet labels are outside the
decimal check. When original display and extracted numbering disagree, inspect the
original in Word before asserting what the source contains.

Run the synthetic bidirectional controls from the source checkout with
`python3 -m unittest discover -s tests -v`. They include the omitted-level failure,
unchanged-source/other-part checks, good and missing labels, nesting, restarts,
overrides, inherited styles, plain text and explicit unsupported cases. Customer
files are not fixtures.

Restart and override semantics follow Microsoft's [LevelRestart](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.levelrestart)
and [StartOverrideNumberingValue](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.startoverridenumberingvalue)
definitions; the implicit-level compatibility repair is verified behavior, not a
claim that every incomplete numbering definition is valid OOXML.
