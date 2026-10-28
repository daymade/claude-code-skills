---
name: docx-creator
disable-model-invocation: true
description: >-
  Produces Word (.docx) and exports existing Word/WPS manuscripts to PDF, preserving revisions,
  tables and images, especially Chinese formal documents via a verified OpenXML generator with
  mandatory visual verification. Use for 生成 Word 文档 / 写合同 docx / 把 markdown 转成 Word / 中文排版. Not for
  Markdown → PDF (use daymade-docs:pdf-creator).
---

# DOCX Creator

Thin incremental layer over **`minimax-skills:minimax-docx`**. Not a document engine.

> **Read this first.** The OpenXML SDK capability lives in `minimax-docx`. This skill contains
> zero engine code. What it contains is the part that took a full debugging session to learn:
> where that engine's CLI stops being usable, how to drive its SDK correctly for Chinese formal
> documents, and how to verify the output so you don't ship a file that looks fine to you and
> broken in Word.

## Division of labor

| Layer | Owner | What lives there |
|---|---|---|
| OpenXML SDK (`DocumentFormat.OpenXml`), `WordprocessingDocument` API, XSD validator, style templates, OpenXML encyclopedia | **`minimax-skills:minimax-docx`** | Engine + reference docs. Never duplicated here. |
| Where the CLI's expressiveness ceiling is, and when to abandon it for C# | **this skill** | ISSUE-001, ISSUE-002 |
| A verified markdown-to-docx generator for Chinese formal documents | **this skill** | `scripts/Program.cs` |
| Chinese formal-document typography rules that OpenXML lets you get wrong | **this skill** | Hard rules below + ISSUE-004…007 |
| Real end-to-end visual verification chain | **this skill** | `references/verification_protocol.md` |

Locate the engine at the marketplace install path, typically
`~/.claude/plugins/marketplaces/minimax-skills/skills/minimax-docx/`.

**Go read minimax-docx directly** for anything structural this skill does not cover — images,
track changes, comments, TOC, multi-section layouts, template application. Its
`minimax-docx/references/` folder (`cjk_typography.md`, `openxml_element_order.md`,
`openxml_units.md`, `troubleshooting.md`) and its `Samples/*.cs` are the authority for SDK
patterns. Do not reinvent them here.

## Routing: which path for this document?

| Situation | Path |
|---|---|
| Chinese contract / agreement / 公文 / any doc with 甲乙方 info blocks, numbered clauses, signature block, tables | **C# OpenXML via `scripts/Program.cs`** (this skill) |
| Plain prose, headings and paragraphs only, no bold / lists / tables | minimax-docx CLI `create --content-json` is enough |
| Fill or edit an **existing** .docx | minimax-docx pipeline B (`edit-content`), plus this skill's layout and verification guidance |
| Match an existing .docx's formatting | minimax-docx pipeline C (`apply-template`) |
| Existing Word/WPS → repaired layout / selected excerpt → PDF | Keep the Word source; follow `references/word-to-pdf.md` and `references/verification_protocol.md` |
| Markdown → PDF | `daymade-docs:pdf-creator` |

Rule of thumb: the CLI's `--content-json` understands these block types:
(`heading`, `paragraph`, `pagebreak`). Bold, lists, tables, borders, footers, fonts,
alignment — none of it is expressible. A Chinese contract needs all of them. See ISSUE-001.

## Quick start

The generator reads markdown and writes a formatted .docx. Copy it next to your document so
build artifacts stay out of the skill directory:

```bash
# 1. Stage the generator beside your markdown
mkdir -p _docxgen && cp <skill-dir>/scripts/Program.cs <skill-dir>/scripts/mmdocx-gen.csproj \
   <skill-dir>/scripts/.gitignore _docxgen/

# 2. Generate (first run restores the project dependencies)
dotnet run --project _docxgen -- your-doc.md your-doc.docx

# 3. Structural validation via the engine's XSD validator (note the roll-forward env — ISSUE-003)
DOTNET_ROLL_FORWARD=Major dotnet run \
  --project ~/.claude/plugins/marketplaces/minimax-skills/skills/minimax-docx/scripts/dotnet/MiniMaxAIDocx.Cli \
  -- validate --input your-doc.docx

# 4. MANDATORY visual verification — never skip, never substitute qlmanage
soffice --headless --convert-to pdf --outdir /tmp/docxcheck your-doc.docx
pdftoppm -png -r 100 /tmp/docxcheck/your-doc.pdf /tmp/docxcheck/page
# then Read every /tmp/docxcheck/page-NN.png

# 5. Follow verification_protocol.md Step 3a before invoking the native Word route.
# Perform its native checks when usable; otherwise retain the named acceptance gap.
```

Full command details and troubleshooting: `scripts/README.md`.
Full verification steps and pass/fail criteria: `references/verification_protocol.md`.

## Hard rules (violating these means rework)

### 1. Alignment is layered — this is the expensive one

Never justify the whole document. Apply alignment by content role:

| Content | Alignment | Why |
|---|---|---|
| Document title (H1) | Center | Convention |
| Clause headings (H2+) | Left | Convention |
| **Info blocks and signature blocks** — 甲方/乙方/统一社会信用代码/法定代表人/日期, i.e. any paragraph whose lines are joined by markdown soft or hard line breaks | **Left** | Justification stretches **every line except the paragraph's last**. A multi-line info block is *one* paragraph, so all but its final line get blown out into huge inter-character gaps. |
| Ordinary body prose | Justified (`Both`) | Clean right edge |

The rule is machine-checkable, so do not eyeball it: if the markdown paragraph's inline tree
contains a `LineBreakInline`, left-align that paragraph; otherwise justify it. Implemented in
the `case ParagraphBlock p:` arm of `Main`'s block-dispatch switch, with the break detection in
`InlineRuns`. Use `scripts/README.md`'s function-name lookup table. Full write-up: ISSUE-004.

### 2. Independent lists restart; continuations retain numbering

Each independent markdown list must get its **own** `NumId` plus a `LevelOverride` carrying
`StartOverrideNumberingValue = 1`. Reuse one `NumId` across clauses and clause 3's list
silently continues from 4. Implemented across the `case ListBlock lb:` arm and the
`NumberingDefinitionsPart` setup — see `scripts/README.md`'s lookup table for both.
SDK traps include the wrong class name and wrong element order — ISSUE-005, ISSUE-006.
For existing Word lists, preserve intentional continuations. Resolve `numId` and its level
before changing geometry; `numId=0` disables numbering. Typed ordinals are text, not an
automatic list. See ISSUE-016.

### 3. CJK fonts need both slots

A run must set `RunFonts { Ascii, HighAnsi, EastAsia }`. Setting only the Latin slots leaves
Chinese characters to Word's fallback, and the document renders in whatever the reader's
machine picks. Read the current fonts, half-point sizes and body indent in
[`scripts/Program.cs`](scripts/Program.cs), at its constants and `RunProps`/`Para` callers.
Keep body size and its character-based first-line indent in sync. Chinese bold-family
handling is defined in `RunProps`; the rendering failure and verification are in ISSUE-014.

### 4. Page and table basics

Use [`scripts/Program.cs`](scripts/Program.cs) for the current page, margin and footer
profile. Tables need complete borders and a `tblGrid`: missing borders leave cells unruled
in print; a missing grid fails strict validation even when LibreOffice hides it.
Preserve the schema order documented at `BuildTable`; ISSUE-013 explains the failure.
Find the page/footer setup at `SectionProperties`/`FooterPart` in `Main`.

## Verification is not optional

**Banned: `qlmanage` thumbnails as visual proof.** macOS Quick Look renders with a different
engine than Word and will happily show a clean-looking page for a document whose info blocks
are stretched apart. A document was declared "verified perfect" on qlmanage evidence and
opened broken in Word — that is the origin of this rule. ISSUE-008.

**Required chain:** generate → XSD validate → `soffice --headless --convert-to pdf` →
`pdftoppm -png` → `Read` every page image → check the failure modes in the verification
protocol → **assess and use the existing authorized, observable
Word route; check the actual file/title bar and every page when usable**. Installation alone
is not readiness. If refused or unavailable after bounded checks, preserve native acceptance
pending and hand off the reviewable DOCX plus an allowed-engine PDF inspected on every page;
name the renderer and the missing native check. Follow Step 3a rather than expanding the task
into Office setup or bypassing a refusal. Details, prerequisites
and the "what counts as failure" list: `references/verification_protocol.md`.

**LibreOffice rendering clean is not the same claim as "Word renders this correctly."**
ISSUE-012 is a real, reproduced case where a file passed every LibreOffice-based check in this
chain — clean info blocks, correct numbering, intact tables — and still opened in real Word
with "兼容性模式" in the title bar and phantom bullet markers on paragraphs that were never
given any numbering. LibreOffice has no equivalent fallback path and is structurally unable to
surface that class of defect. This is ISSUE-008's own lesson (a lenient renderer hides what
Word does) recurring one layer up; treat LibreOffice-only verification as incomplete whenever
Word is available to check against directly.

**Before replacing a generated .docx**, follow
[the holder and output-identity check](references/verification_protocol.md#before-replacing-a-generated-docx).
Preserve signed/template/returned originals. A lock is a signal, not proof of a live holder
or safe release; keep unknown holder/release states pending and verify the new output
independently of the lock. ISSUE-011 records the stale-open-copy failure.

## Customizing

Edit `scripts/Program.cs` directly for fonts,
sizes, spacing, borders, or new block types — that is the intended workflow. Before adding a
structural feature (images, TOC, headers, track changes), read the corresponding
`Samples/*.cs` in minimax-docx first; those patterns are SDK-version-verified and will save
you a compile-error loop.

**If you append a new property to `RunProperties`, `ParagraphProperties`, `TableProperties`,
`TableCellProperties`, or `TableBorders`: it must go in ECMA-376's child-element order for
that parent, not wherever `.Append()` reads naturally in the C#.** This is not a style
preference — get it wrong and you reproduce ISSUE-012/ISSUE-013: `minimax-docx validate` still
reports `PASSED`, LibreOffice still renders the file cleanly, and real Word still opens it in
Compatibility Mode with unrequested formatting scattered across the document. The current code
already carries a schema-order comment at each construction site (`RunProps`, `Para`,
`BuildTable`) — extend the existing property list in place rather than appending after it, and
if you add a genuinely new element, look up its position in `openxml_element_order.md`
(minimax-docx) before deciding where the `.Append()` call goes. Re-run Step 3a of the
verification protocol after any such change. Real Word is the only check in this chain that
would have caught this class of bug; if its route is refused or unusable, preserve that native
check as pending under Step 3a rather than declaring the DOCX Word-ready.

## References

- `references/word-to-pdf.md` — existing Word source, excerpt selection, accepted revisions,
  layout repair and PDF delivery; no Markdown round-trip.
- `references/known_issues.md` — symptom / root cause / fix / verification for
  every trap hit while building this pipeline. Read before debugging anything.
- `references/verification_protocol.md` — the full end-to-end verification chain, its
  prerequisites, its pass criteria, and the substitutions that are forbidden.
- `scripts/README.md` — how to run the generator, what markdown it supports, environment
  requirements.
