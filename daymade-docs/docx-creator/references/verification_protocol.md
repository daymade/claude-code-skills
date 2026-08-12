# Verification protocol

**A .docx that generates without error is not a verified .docx.** Every failure mode that
matters in a formal Chinese document — stretched info blocks, restarted-or-not list numbers,
missing table rules, font fallback — is invisible in the exit code, invisible in the extracted
text, and invisible in a macOS Quick Look thumbnail. The only thing that surfaces them is a
Word-grade rendering, looked at.

This protocol is mandatory before delivering any .docx produced with this skill.

---

## Step 0 — Prerequisites (check the binaries, not the installers)

```bash
dotnet --version                                        # any SDK; see scripts/README.md
ls -l /Applications/LibreOffice.app/Contents/MacOS/soffice   # the file must exist
which pdftoppm                                          # brew install poppler
ls -d "/Applications/Microsoft Word.app" 2>/dev/null && echo "Word available — Step 3a required"
```

`ls` on the soffice binary is the real installation check. `brew install --cask libreoffice`
can exit 0 having installed nothing (ISSUE-009), so a `$?`-based check is worthless here.

If `soffice` is not on PATH, use the full binary path in every command below, or:

```bash
export PATH="/Applications/LibreOffice.app/Contents/MacOS:$PATH"
```

---

## Step 1 — Generate

```bash
dotnet run --project _docxgen -- your-doc.md your-doc.docx
```

Read the summary line it prints. The list count must match the number of separate lists in
your markdown — a mismatch means lists merged, which is ISSUE-005 about to happen.

**Before overwriting an already-delivered file**, check for Word's owner lock (ISSUE-011):

```bash
ls -a $(dirname your-doc.docx) | grep '^~\$' || echo "no lock, safe to overwrite"
```

---

## Step 2 — Structural validation (XSD)

Use the engine skill's validator. It catches schema violations — most usefully wrong element
order inside the numbering and styles parts (ISSUE-006) — that Word would report much later as
"the file needs repair".

```bash
DOTNET_ROLL_FORWARD=Major dotnet run \
  --project ~/.claude/plugins/marketplaces/minimax-skills/skills/minimax-docx/scripts/dotnet/MiniMaxAIDocx.Cli \
  -- validate --input your-doc.docx
```

Expected output: `Validation: PASSED`.

The `DOTNET_ROLL_FORWARD=Major` prefix is required — that CLI targets net8.0 and will not
launch on a machine whose only shared runtime is 10.x (ISSUE-003). Its absence produces a
launch error, not a validation failure; do not misread it as "the document is invalid".

**This `PASSED` is weaker evidence than it looks (ISSUE-013).** minimax-docx's validator does
not check ECMA-376 child-element ordering inside `w:rPr`/`w:pPr`/`w:tblPr` — a file with real
ordering violations there and a missing required `w:tblGrid` still reports `PASSED`. If you
have the OpenXML SDK available (this generator already depends on it), run the stricter check
too:

```csharp
using var doc = WordprocessingDocument.Open(path, false);
var errors = new OpenXmlValidator(DocumentFormat.OpenXml.FileFormatVersions.Office2013).Validate(doc).ToList();
Console.WriteLine(errors.Count);   // must be 0
```

Passing either or both steps means the XML is well-formed and schema-legal. It says
**nothing** about layout, and — see Step 3a — **nothing** about whether real Word will even
render the file using its own properties instead of a Compatibility Mode fallback. Continue.

---

## Step 3 — Render with a Word-grade engine

```bash
rm -rf /tmp/docxcheck && mkdir -p /tmp/docxcheck
soffice --headless -env:UserInstallation=file:///tmp/lo-docxcheck \
        --convert-to pdf --outdir /tmp/docxcheck your-doc.docx
ls -l /tmp/docxcheck/your-doc.pdf
```

- LibreOffice is used because its layout engine reproduces Word's justification, numbering and
  font behaviour closely enough to expose the bugs. Quick Look does not (ISSUE-008).
- The private `-env:UserInstallation` profile avoids lock contention with a running GUI
  instance or a concurrent conversion (ISSUE-010).
- `rm -rf` the output directory first. Otherwise a failed conversion leaves last run's PDF in
  place and you verify a stale document.
- The final `ls` is not decoration — a missing PDF here is a hard stop, not a warning.

---

## Step 3a — Open in real Microsoft Word, not just LibreOffice (mandatory if Word is available)

**LibreOffice passing Steps 3-5 is not the same claim as "Word will render this correctly."**
ISSUE-012 is a real, reproduced case: a file that renders perfectly in the LibreOffice PDF —
clean info blocks, correct list numbers, intact table borders, everything Step 5 checks for —
opened in actual Word with "兼容性模式" in the title bar and phantom bullet markers scattered
across paragraphs that were never given any numbering. LibreOffice has no equivalent
Compatibility Mode fallback, so it is structurally incapable of surfacing this class of defect
no matter how carefully you read its rendered pages. This is the exact shape of ISSUE-008
(qlmanage hides what LibreOffice shows) recurring one layer up (LibreOffice hides what Word
does).

If Microsoft Word.app is installed on the machine — check with `ls -d "/Applications/Microsoft
Word.app"` — this step is not optional, it is Step 3a, between rendering and rasterizing:

```bash
open -a "Microsoft Word" your-doc.docx
```

Then look at two things, in this order:

1. **The title bar.** Any suffix after the filename other than "— 已保存到…" / "— saved" is a
   red flag; "兼容性模式" specifically means ISSUE-012 (missing `DocumentSettingsPart`
   compatibility declaration) — go fix that before doing anything else.
2. **Every page, same five checks as Step 5**, but now the ground truth is what a real
   recipient's Word will show, not what LibreOffice approximated.

If Word is not installed on this machine (common on Linux CI, some Mac minis), say so
explicitly in your verification report rather than silently skipping the step — "Word was not
available to verify this on" is honest; a verification report that omits Step 3a without
comment reads as if it passed.

---

## Step 4 — Rasterize every page

```bash
pdftoppm -png -r 100 /tmp/docxcheck/your-doc.pdf /tmp/docxcheck/page
ls /tmp/docxcheck/page-*.png
```

100 DPI is enough to see character-spacing damage and fine table rules while keeping images
small enough to read quickly. Raise to 150 if a table's borders are ambiguous.

---

## Step 5 — Read every page image and check five things

`Read` each `page-NN.png`. Not the first page. Not a sample. Every page — pagination bugs and
signature-block damage live at the end, which is exactly where sampling stops looking.

| # | Check | Failing looks like | Cause |
|---|---|---|---|
| 1 | **Info blocks are not stretched** — 甲方/乙方 blocks, addresses, signature blocks | Huge, uneven gaps between characters on every line but the last of the block | ISSUE-004 |
| 2 | **Every list starts at 1** | Second clause's list starts at 4 | ISSUE-005 |
| 3 | **Table borders complete** | Some cells unruled, or only outer border drawn | Missing `insideH` / `insideV` |
| 4 | **Signature block intact** | Party rows split across a page break; name and seal line separated; column drift | Layout / pagination |
| 5 | **Pagination sane** | Orphaned heading at page bottom, single-line last page, clause split from its number | Spacing / keep-with-next |

Also confirm at a glance: Chinese renders in the intended 宋体/黑体 rather than a fallback
(ISSUE-007), headings are centered or left per the layer rule, and the page-number footer
appears.

---

## Step 6 — Fix at the right layer, then rerun from Step 1

| Symptom | Fix in |
|---|---|
| Wrong text, wrong clause order, wrong wording | the markdown |
| Info block stretched, list restarting wrong, font/size/spacing/borders wrong | `scripts/Program.cs` |
| Structural feature missing entirely (image, TOC, header, track change) | `scripts/Program.cs`, after reading the matching `Samples/*.cs` in minimax-docx |

Never patch a rendering bug by contorting the markdown — the next document will hit it again.
Rerun the whole chain after any fix; a fix in one layer routinely breaks another (changing
paragraph spacing moves page breaks, which is check 5).

---

## Forbidden substitutions

| Substitution | Why it is not verification |
|---|---|
| `qlmanage -t` thumbnail | Different rendering engine; showed a clean page for a document Word laid out visibly broken. This is the mistake that created this document (ISSUE-008). |
| **LibreOffice PDF alone, with Word installed and skipped** | Different rendering engine, one level up from the qlmanage mistake — LibreOffice has no Compatibility Mode fallback and cannot surface it, so a clean LibreOffice render is not evidence Word will render the same file correctly (ISSUE-012). |
| Exit code 0 | Says the writer did not crash. Every failure mode here is silent. |
| `minimax-docx validate` reporting `PASSED` alone | Does not check `rPr`/`pPr`/`tblPr` child-element order or `tblGrid` presence — a file with real ECMA-376 violations still passes it (ISSUE-013). |
| `python-docx` / text extraction round-trip | Confirms the characters are present. The characters were never the problem — their layout was. |
| Reading the generated XML | Confirms your intent was encoded. Does not confirm Word's interpretation of it. |
| Verifying page 1 only | Signature blocks and pagination failures are at the end. |
| "It renders fine in the markdown preview" | The markdown is the input, not the artifact. |

---

## Minimum evidence to claim "verified"

State all five, or do not use the word:

1. `Validation: PASSED` from the XSD validator, **and**, if available, 0 errors from
   `OpenXmlValidator` (ISSUE-013 — the first alone is not sufficient).
2. PDF produced by LibreOffice at a named path, generated after the last edit.
3. Page count, and confirmation that **every** page image was read.
4. The five checks in Step 5, each explicitly passed — naming the info block and the list you
   looked at, not "looks good".
5. **If Microsoft Word.app is installed**, Step 3a done: title bar has no "兼容性模式" suffix,
   and no unrequested markers on any page. If Word is not installed, say so explicitly instead
   of omitting this point silently.
