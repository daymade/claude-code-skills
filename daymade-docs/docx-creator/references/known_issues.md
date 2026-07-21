# Known issues

Every entry below comes out of building a real Chinese-contract pipeline on top of
`minimax-skills:minimax-docx` — most of them the hard way, one of them after shipping a broken
document. Format: **symptom → root cause → fix → how to verify the fix**.

Read this before debugging. Most of these fail *silently* — the document generates, the exit
code is 0, and the damage is only visible in Word.

Severity legend: **P0** = ships a broken document. **P1** = costs an hour. **P2** = annoyance.

---

## ISSUE-001 — The CLI cannot express a formal document (P0)

**Symptom.** You build a `--content-json` payload for a contract and there is no way to say
bold, list, table, alignment, font, border, or footer. Output is an undifferentiated wall of
default-styled paragraphs.

**Root cause.** `create --content-json` understands exactly three block types. In
`minimax-docx/scripts/dotnet/MiniMaxAIDocx.Core/Commands/CreateCommand.cs`, `AddContentFromJson`
(line 287) switches over `"heading"`, `"paragraph"`, `"pagebreak"` (lines 301, 309, 313) and
drops everything else on the floor — unknown types are not even warned about, they simply do
not append. The JSON schema is `{type, text, level?}`; there is no field in which bold, list
or table could be encoded.

**Fix.** For anything beyond flat prose, write C# against the OpenXML SDK instead of driving
the CLI. That is what `scripts/Program.cs` is. Keep using the CLI for what it is good at:
`validate` (ISSUE-003), `analyze`, `diff`.

**Verify.** Grep the switch yourself before assuming a block type is supported:
`grep -n 'case "' minimax-docx/scripts/dotnet/MiniMaxAIDocx.Core/Commands/CreateCommand.cs`.
Three cases means three block types.

---

## ISSUE-002 — `run-script` is documented but does not exist (P1)

**Symptom.** minimax-docx's SKILL.md shows the C# scaffold being executed with
`dotnet run --project minimax-docx/scripts/dotnet/MiniMaxAIDocx.Cli -- run-script task.csx`.
Running it does nothing useful — there is no such command. Falling back to `dotnet-script`
fails too because it is not installed.

**Root cause.** Documentation ahead of implementation. The CLI's command set is what exists in
`minimax-docx/scripts/dotnet/MiniMaxAIDocx.Core/Commands/`: analyze, apply-template, create,
diff, edit-content, fix-order, merge-runs, validate. No script runner among them.

**Fix.** Create your own console project — that is the supported path in practice:

```bash
dotnet new console -o _docxgen
dotnet add _docxgen package DocumentFormat.OpenXml --version 3.2.0
dotnet add _docxgen package Markdig
```

`scripts/mmdocx-gen.csproj` is exactly this, already wired up.

**Verify.** `ls minimax-docx/scripts/dotnet/MiniMaxAIDocx.Core/Commands/` — if there is no
`RunScriptCommand.cs`, the documented invocation is fiction on your installed version.

---

## ISSUE-003 — minimax-docx's CLI will not launch on a .NET 10-only machine (P1)

**Symptom.**

```
You must install or update .NET to run this application.
App: .../MiniMaxAIDocx.Cli/bin/Debug/net8.0/MiniMaxAIDocx.Cli
Framework: 'Microsoft.NETCore.App', version '8.0.0' (arm64)
The following frameworks were found:
  10.0.5 at [/usr/local/share/dotnet/shared/Microsoft.NETCore.App]
```

The project *builds* fine — this is a launch-time failure, so it looks like the build worked
and the tool is broken.

**Root cause.** Both `MiniMaxAIDocx.Cli.csproj` and `MiniMaxAIDocx.Core.csproj` set
`TargetFramework` to `net8.0`. .NET does not silently roll a framework-dependent app forward
across a **major** version; a machine with only the 10.x shared runtime refuses to host a
net8.0 app.

**Fix.** Do not install an extra runtime. Set the roll-forward policy per invocation:

```bash
DOTNET_ROLL_FORWARD=Major dotnet run --project <path-to>/MiniMaxAIDocx.Cli -- validate --input out.docx
```

**Verify.** Re-verified live while writing this skill, on a machine with only
`Microsoft.NETCore.App 10.0.5`: without the env var the launch fails with the message above;
with it, the same command prints `Validation: PASSED`.

Note: this env var is for **minimax-docx's** CLI only. `scripts/mmdocx-gen.csproj` targets the
local SDK's framework and needs no roll-forward.

---

## ISSUE-004 — Justified text stretches info blocks and signature blocks apart (P0, most expensive)

**Symptom.** In Word, a block like

```
甲方：某某公司
统一社会信用代码：...
法定代表人：...
```

renders with enormous gaps between characters on every line **except the last one**. Body
prose looks perfect. It is the most visually damning failure a formal document can have, and
it does not reproduce in a macOS Quick Look thumbnail (see ISSUE-008).

**Root cause.** `JustificationValues.Both` stretches all lines of a paragraph *except its
final line* — that is what justification means. A markdown info block written as consecutive
lines inside one paragraph (soft breaks) or with trailing double-space (hard breaks) compiles
into **one** Word paragraph containing `<w:br/>` runs. Word therefore has N-1 "non-final"
lines, each of which is short, each of which gets blown out to the full text width.

**Fix.** Alignment must be layered, and the layer is decidable from the AST:

| Content | Alignment |
|---|---|
| H1 title | Center |
| H2+ clause heading | Left |
| Paragraph whose inlines contain a `LineBreakInline` (info block, signature block, address block) | **Left** |
| Ordinary paragraph | Justified (`Both`) |
| Table cells | Left |

In `scripts/Program.cs` the inline walker returns a `hasBreak` flag (lines 59-64) and the
block dispatcher picks `hasBreak ? Left : Both` (lines 144-147).

**Verify.** Only through the real chain — LibreOffice-rendered PDF, page PNGs, eyes on the
signature page. `references/verification_protocol.md`. A stretched info block is unmistakable
at 100 DPI.

Reproduced on demand while writing this skill: replacing the decision at
`scripts/Program.cs` line 146 with an unconditional `JustificationValues.Both` and
regenerating turns `甲方：示例科技有限公司` into `甲 方 ： 示 例 科 技 有 限 公 司` spread
edge to edge, while the **last** line of each block (住所, 联系地址) stays normal — the exact
signature of "justify stretches every line but the last". Restoring the conditional restores
the block. That one-line revert-and-render is the regression test for this issue.

---

## ISSUE-005 — Clause 3's list starts at 4 (P0)

**Symptom.** Each numbered list in the document continues the previous one instead of starting
over: clause 1 has items 1-3, clause 2's list starts at 4.

**Root cause.** All list paragraphs referenced the same numbering instance. In OpenXML a
`NumId` identifies a *counter*, not a *style* — sharing one means sharing its running count.

**Fix.** Allocate a fresh `NumId` per markdown list, and attach a level override that forces a
restart:

```csharp
new NumberingInstance(
    new AbstractNumId { Val = ordered ? 0 : 1 },
    new LevelOverride(new StartOverrideNumberingValue { Val = 1 }) { LevelIndex = 0 }
) { NumberID = numId }
```

Two abstract definitions are enough (one decimal, one bullet); every list gets its own
instance pointing at one of them. `scripts/Program.cs` lines 148-162 (allocation) and 194-196
(emission).

**Verify.** The generator prints the number of lists it created; it must equal the number of
lists in the markdown. Then confirm visually — the first item of every list reads `1.`.
Confirmed on a two-clause fixture: the generator reported 3 lists, and the second clause's
list rendered `1.` `2.` rather than continuing from 4.

---

## ISSUE-006 — Numbering part compiles wrong, or opens as a corrupt document (P1)

**Symptom.** Two distinct failures while wiring up ISSUE-005's fix:

1. `error CS0246: The type or namespace name 'Num' could not be found`
2. The .docx builds but Word reports it needs repair, or numbering silently disappears

**Root cause.**

1. Much OpenXML material calls the element `Num` (its XML name is `w:num`). In
   `DocumentFormat.OpenXml` 3.x the generated class is **`NumberingInstance`**.
2. `w:numbering` has a schema-mandated child order: **all** `AbstractNum` elements must
   precede **all** `NumberingInstance` elements. Interleaving them (natural if you append one
   pair per list in a loop) produces schema-invalid XML that some readers reject outright.

**Fix.** Append both `AbstractNum` definitions first, then loop the instances — see
`scripts/Program.cs` lines 192-196. Element-order rules for other parts are catalogued in
minimax-docx's `openxml_element_order.md` reference; consult it whenever you add a new part.

**Verify.** `DOTNET_ROLL_FORWARD=Major dotnet run --project <path-to>/MiniMaxAIDocx.Cli --
validate --input out.docx` — the XSD validator catches ordering violations that Word merely
complains about later. Expect `Validation: PASSED`.

---

## ISSUE-007 — Chinese renders in the wrong font on someone else's machine (P1)

**Symptom.** The document looks right locally and wrong on the recipient's Word — Chinese
characters fall back to a system default, so line lengths, weight and page breaks all shift.

**Root cause.** `RunFonts` has separate slots for Latin (`Ascii`, `HighAnsi`) and East Asian
(`EastAsia`) text. Setting only the Latin slots leaves CJK unspecified; the reader's Word
picks. Font *size* has the same trap: `FontSize` covers the Latin run, `FontSizeComplexScript`
covers complex-script runs, and setting only one produces mixed sizes in bilingual lines.

**Fix.** Always set all three font slots and both size properties:

```csharp
rp.Append(new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "宋体" });
rp.Append(new FontSize { Val = "24" });               // half-points → 12pt
rp.Append(new FontSizeComplexScript { Val = "24" });
```

Shipped scheme: 宋体 body / 黑体 headings; 24 half-points body, 36 H1, 28 clause heading.
`scripts/Program.cs` lines 23-32.

**Verify.** Convert to PDF and inspect embedded fonts (`pdffonts out.pdf`), or read the page
PNGs — a fallback font is visible as a weight and width change against the surrounding text.

---

## ISSUE-008 — `qlmanage` thumbnails are a fake verification (P0 — this one shipped a broken document)

**Symptom.** `qlmanage -t -s 2000 -o /tmp/preview out.docx` produces a clean-looking page.
The document is declared verified. The recipient opens it in Word and the layout is visibly
broken — specifically the ISSUE-004 stretched info blocks, which the thumbnail did not show.

**Root cause.** macOS Quick Look renders .docx with its own lightweight engine, not Word's.
It approximates the layout: it does not reproduce Word's justification stretching, its
numbering-instance behaviour, or its font substitution. It answers "does this file parse",
which was never the question. The question is "does Word lay this out correctly".

**Fix.** Use a renderer with Word-grade layout fidelity. LibreOffice headless is the practical
one:

```bash
soffice --headless --convert-to pdf --outdir /tmp/docxcheck out.docx
pdftoppm -png -r 100 /tmp/docxcheck/out.pdf /tmp/docxcheck/page
# Read every page-NN.png
```

**Verify.** The regression test for this rule is ISSUE-004 itself: a document whose
soft-break info block is set to `Both` must look *visibly broken* in the LibreOffice PNG —
confirmed reproducible, see that issue's Verify section. If your verification method shows
that document as fine, your verification method is the qlmanage mistake wearing a different
hat.

Related bans, same reasoning: "exit code 0" is not verification; `python-docx` reading the
text back is not verification (the text was never the problem); "it looks right in the
markdown" is not verification.

---

## ISSUE-009 — LibreOffice install reports success without installing (P1)

**Symptom.** `brew install --cask libreoffice` prints an error like
`App source ... is not there`, purges what it staged, and **still exits 0**. A script that
checks `$?` concludes LibreOffice is installed. The next `soffice` call fails with
command-not-found, and you go looking for a PATH problem that does not exist.

**Root cause.** Cask post-install failure paths that do not propagate a non-zero status.
"Exit code 0" describes the installer's opinion, not the filesystem.

**Fix.** Verify the binary, never the exit code:

```bash
brew reinstall --cask libreoffice
ls -l /Applications/LibreOffice.app/Contents/MacOS/soffice   # this is the real check
```

Add `/Applications/LibreOffice.app/Contents/MacOS` to PATH, or call the binary by full path.

**Verify.** `ls` on the binary path prints a file. Anything else means not installed,
regardless of what the installer said.

---

## ISSUE-010 — First headless LibreOffice run hangs or dies on a profile lock (P2)

**Symptom.** `soffice --headless --convert-to pdf` hangs, or exits complaining the user
profile is in use — typically when the GUI app is open, or when two conversions run
concurrently.

**Root cause.** LibreOffice takes an exclusive lock on its user profile directory. Headless
and GUI instances contend for the same default profile.

**Fix.** Give each headless run a private throwaway profile:

```bash
soffice --headless -env:UserInstallation=file:///tmp/lo-docxcheck \
        --convert-to pdf --outdir /tmp/docxcheck out.docx
```

**Verify.** The PDF appears in the output directory. If it does not, that is a hard failure —
do not proceed to the visual step with a stale PDF from a previous run. Delete the output
directory before each conversion so a missing PDF cannot masquerade as a fresh one.

---

## ISSUE-011 — `~$name.docx` beside the target means the recipient has it open (P2)

**Symptom.** You regenerate and overwrite a delivered .docx. The recipient insists nothing
changed.

**Root cause.** A sibling file named `~$<same-name>.docx` is Word's owner lock, written while
a document is open. Its presence means someone has the **old** version open right now.
Overwriting the file on disk does not touch their in-memory copy, and Word may write theirs
back over yours when they save.

**Fix.** Before overwriting, `ls` the target directory for `~$` files. If one exists, tell the
recipient to close the document first, and to reopen it after you deliver.

**Verify.** `ls -a <dir> | grep '^~\$'` returns nothing before you overwrite, and the
recipient confirms a reopen after delivery.
