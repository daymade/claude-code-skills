# Verification protocol

**A .docx that generates without error is not a verified .docx.** Layout failures such as
stretched info blocks, incorrect list numbers, missing table rules and font fallback require
inspection of rendered pages. A successful process or extracted text cannot establish that
layout is correct; macOS Quick Look is not the target Word engine.

This protocol covers DOCX and existing-Word → PDF delivery. Apply the gate for the actual
deliverable: Word application checks matter when delivering DOCX; a PDF-only handoff needs
final-PDF inspection in the intended reader, not a claim that the disposable DOCX is Word-ready.

## Existing Word → PDF: delivery gate

- Pin the source file/hash, selected content and revision view. Preserve the original and
  compare the selected accepted text, tables and image references before/after formatting.
  Compare code whitespace exactly; any permitted ordinal-separator normalization is narrow
  and explicit. Text equality proves content preservation, not readable layout.
- Check role relationships: body first line; list marker, text and wrapped continuation;
  code panel edge and internal padding. Inspect typed and automatic numbering separately,
  including two-digit labels and disabled numbering (ISSUE-015/016).
- Render after the last edit and inspect **every page at a readable scale**. Small contact
  sheets help navigation but do not clear indentation, punctuation, captions or table rules.
  Inspect code glyphs, full images, heading/page-break relationships, notes and table cells.
  If a fix causes reflow, inspect all changed pages and boundaries. Unchanged page-image hashes
  may reuse a recorded prior inspection; rerendering is not itself a new inspection.
- Reopen the final delivered path independently, check page count, bookmarks, attachments
  and selected content, then inspect it in the intended PDF reader. A temporary preview or
  old open tab is not the delivered file. Scope any unavailable consumer check explicitly.
- Failures return to the generator and repeat the affected checks. Do not stop after each
  patch to ask the user to find the next defect. Stop when the agreed deliverable passes
  content, layout and consumer checks; present one final artifact for user acceptance.

Use synthetic bad/good fixtures for recurring failures. Cover a long list item, a two-digit
ordinal, a code panel, literal URL punctuation and an inline image under exact line spacing.
A delivery file is not a user-approved golden template merely because it was sent.

The remaining steps describe the DOCX-specific chain.

---

## Step 0 — Prerequisites (check the binaries, not the installers)

```bash
dotnet --list-sdks                                      # inventory installed SDKs
ls -l /Applications/LibreOffice.app/Contents/MacOS/soffice   # the file must exist
which pdftoppm                                          # brew install poppler
ls -d "/Applications/Microsoft Word.app" 2>/dev/null   # installation only; assess readiness in Step 3a
```

Read `TargetFramework` in [`mmdocx-gen.csproj`](../scripts/mmdocx-gen.csproj) and confirm
the selected installed SDK supports it. An SDK being present does not establish that the
project can build; a missing compatible SDK remains an unmet prerequisite.

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

### Before replacing a generated DOCX

The executing agent preserves signed documents, templates and returned drafts at their
original paths; generate a derived file at a new output path. Replace an existing generated
deliverable only within the authorized regeneration scope. Pin its exact path/hash and the
source/build that should produce the replacement. A lock check does not establish this
identity or prove that an old generated file is the intended current output.

A sibling `~$<name>.docx` is a signal to investigate, not proof of a current holder, their
identity or release. Whether or not a lock is present, inspect the existing app/document
route and, when available, query the exact target path for local open-file holders:

```bash
target="/absolute/path/your-doc.docx"
lsof -- "$target"
```

Inspect stdout, stderr and exit status. Reported process/PID/user rows identify observed
local handles, not which recipient saved the document. A missing tool, permission refusal,
warning, path error or unobservable app state leaves holder status unknown; retain the
original and continue at a new output path. A clean no-match query only means no local
holder was observed through that probe. Absence of a lock is not overwrite clearance.

If a holder is observed, wait for it to save and close the document, then repeat the same
path query and check the app/document state to verify release. Do not kill the process,
quit without saving, or delete the lock to force release. An unexplained remaining lock or
unknown release keeps replacement pending; absence of a lock cannot override an observed
holder. A no-lock/no-observed-holder case may continue after the independent identity checks.

After regeneration, verify the final file's hash against the new build output and its
source identity, then reopen the final delivered path for the required content/layout
checks. An old open window or a prior PDF at that path does not prove the new output was
loaded. ISSUE-011 records the stale-open-copy failure.

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

## Step 3a — Check the actual file in Microsoft Word when the native route is usable

**LibreOffice passing Steps 3-5 is not the same claim as "Word will render this correctly."**
ISSUE-012 is a real, reproduced case: a file that renders perfectly in the LibreOffice PDF —
clean info blocks, correct list numbers, intact table borders, everything Step 5 checks for —
opened in actual Word with "兼容性模式" in the title bar and phantom bullet markers scattered
across paragraphs that were never given any numbering. LibreOffice has no equivalent
Compatibility Mode fallback, so it is structurally incapable of surfacing this class of defect
no matter how carefully you read its rendered pages. This is the exact shape of ISSUE-008
(qlmanage hides what LibreOffice shows) recurring one layer up (LibreOffice hides what Word
does).

Distinguish installation from a usable native route. The executing agent checks the existing
project renderer or authorized app route: can it invoke Word for this exact file, is that
operation permitted, and can it observe the resulting document/pages or native export?
An app directory, successful event delivery or process exit alone proves none of these.

- **Ready:** when the native route is callable, authorized and observable, perform this check.
  Do not choose the unavailable exit merely because LibreOffice has already rendered cleanly.
  Open the actual file (or use the project's verified native route):

  ```bash
  open -a "Microsoft Word" your-doc.docx
  ```

  Inspect the title bar first: a suffix other than "— 已保存到…" / "— saved" is a red flag;
  "兼容性模式" specifically requires the ISSUE-012 compatibility-settings check. Then inspect
  every page for Step 5's failures. Unexpected Compatibility Mode, unrequested markers
  or visible damage returns to Step 6;
  a fallback PDF does not excuse a real text, structure or layout defect.
- **Not yet known:** make one bounded readiness pass over existing, already-authorized native
  routes. Read the observed failure before another attempt; retry only after a relevant state
  change. Keep an unobservable result pending. Installation alone does not require an Office
  installation, activation, login or network-repair project as part of document delivery.
- **Explicit host/permission refusal:** stop that native operation. Do not switch automation
  tools, credentials or machines to bypass the refusal. Record the refused operation and leave
  native acceptance incomplete.
- **Unavailable:** if Word is absent, or existing authorized routes are demonstrably unusable
  after that bounded pass, stop native attempts. Record the concrete missing prerequisite or
  failure and the action needed to resume; do not claim native verification passed.

When native acceptance remains incomplete, continue independent content/structure checks and
repair real defects. If an allowed renderer is available, deliver the generated, reviewable
DOCX together with a PDF rendered after the final edit and inspected on every page (Steps 4–5).
Name the actual PDF engine/version and label **Word-native acceptance pending**, with its cause.
If no allowed renderer can produce that PDF, state the missing PDF/layout acceptance instead
of inventing evidence. Respect any explicit project requirement for a particular renderer.

This is a review handoff, not proof that a signing-ready clean document is complete. Keep any
other content/approval/annotation-removal requirements pending too. Resume at this native
check when access becomes usable; do not repeat already valid independent checks. The agent
records these observations; no automatic readiness or prose classifier enforces this branch.

---

## Step 4 — Rasterize every page

```bash
pdftoppm -png -r 100 /tmp/docxcheck/your-doc.pdf /tmp/docxcheck/page
ls /tmp/docxcheck/page-*.png
```

100 DPI is enough to see character-spacing damage and fine table rules while keeping images
small enough to read quickly. Raise to 150 if a table's borders are ambiguous.

---

## Step 5 — Read every page image and check the failure modes

`Read` each `page-NN.png`. Not the first page. Not a sample. Every page — pagination bugs and
signature-block damage live at the end, which is exactly where sampling stops looking.

| # | Check | Failing looks like | Cause |
|---|---|---|---|
| 1 | **Info blocks are not stretched** — 甲方/乙方 blocks, addresses, signature blocks | Huge, uneven gaps between characters on every line but the last of the block | ISSUE-004 |
| 2 | **Independent generated lists restart; intentional existing continuations remain** | An independent clause's list continues a previous counter, or an intended continuation restarts | ISSUE-005/016 |
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
| Wrong text, wrong clause order, wrong wording | The authoritative source: Markdown for new generation, a derived Word revision for an existing manuscript |
| New Markdown-generated DOCX: alignment, numbering, typography or missing structural feature | `scripts/Program.cs`; read the matching minimax-docx sample before adding structure |
| Existing Word-derived DOCX/PDF: alignment, numbering, typography or missing structural feature | The project's derived-copy Word formatter/selection script; preserve the authoritative Word structure, and read the relevant minimax-docx sample if extending its support |

Never patch a rendering bug by contorting the markdown — the next document will hit it again.
Revalidate changed structure and rerender after a layout fix. Reuse unchanged checks; inspect
all pages affected by reflow (changing spacing moves page breaks, which is check 5).

---

## Forbidden substitutions

| Substitution | Why it is not verification |
|---|---|
| `qlmanage -t` thumbnail | Different rendering engine; showed a clean page for a document Word laid out visibly broken. This is the mistake that created this document (ISSUE-008). |
| **LibreOffice PDF alone, with a usable authorized Word route skipped** | Different rendering engine, one level up from the qlmanage mistake — LibreOffice has no Compatibility Mode fallback and cannot surface it, so a clean LibreOffice render is not evidence Word will render the same file correctly (ISSUE-012). |
| Exit code 0 | Says the writer did not crash. Every failure mode here is silent. |
| `minimax-docx validate` reporting `PASSED` alone | Does not check `rPr`/`pPr`/`tblPr` child-element order or `tblGrid` presence — a file with real ECMA-376 violations still passes it (ISSUE-013). |
| `python-docx` / text extraction round-trip | Confirms the characters are present. The characters were never the problem — their layout was. |
| Reading the generated XML | Confirms your intent was encoded. Does not confirm Word's interpretation of it. |
| Verifying page 1 only | Signature blocks and pagination failures are at the end. |
| "It renders fine in the markdown preview" | The markdown is the input, not the artifact. |

---

## Minimum evidence to claim "verified"

State the evidence below. Use an unqualified "Word verified" only after native acceptance passes;
an unavailable-route review handoff must state which checks passed and which remain pending:

1. `Validation: PASSED` from the XSD validator, **and**, if available, 0 errors from
   `OpenXmlValidator` (ISSUE-013 — the first alone is not sufficient).
2. PDF produced at a named path after the last edit; name the actual renderer and version.
3. Page count, and confirmation that **every** page image was read.
4. The checks in Step 5, each explicitly passed — naming the info block and the list you
   looked at, not "looks good".
5. Step 3a native result: when the route is usable, title bar has no "兼容性模式" suffix and
   no page has unrequested markers. Otherwise record **Word-native acceptance pending**, its
   observed cause and resume condition; describe the completed PDF/structure checks by scope,
   not as unqualified "Word verified" or "signing-ready clean copy".
