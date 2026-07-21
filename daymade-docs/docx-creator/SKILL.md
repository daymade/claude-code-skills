---
name: docx-creator
description: >-
  Produce production-grade Word (.docx) documents — especially Chinese ones — by driving the
  minimax-skills:minimax-docx OpenXML engine correctly. Use whenever the deliverable is a .docx
  file: 生成 Word 文档 / 做一份 docx / 写合同 docx / 起草协议 / 正式文书 / 公文 / offer / 劳动合同 /
  把 markdown 转成 Word / Word 排版 / 中文排版 / 签字栏 / 盖章版 / 甲方乙方, or any plain
  "give me a Word file" request. This skill adds the layer minimax-docx does not ship: a verified
  markdown-to-docx OpenXML generator, the alignment-layering rule that stops justified text from
  stretching 甲方/乙方 info blocks and signature blocks into garbage, per-list numbering restart,
  CJK font dual-slot setup, and a mandatory LibreOffice-to-PDF-to-PNG visual verification chain
  (qlmanage thumbnails are banned — they hide exactly the bugs that matter). Engine belongs to
  minimax-docx; correct usage and the field-tested workarounds belong here. For PDF output use
  daymade-docs:pdf-creator instead — the two pipelines are intentionally orthogonal.
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
| Fill or edit an **existing** .docx | minimax-docx pipeline B (`edit-content`) — this skill has nothing to add |
| Match an existing .docx's formatting | minimax-docx pipeline C (`apply-template`) |
| Output should be a **PDF**, not Word | `daymade-docs:pdf-creator` — wrong skill, stop here |

Rule of thumb: the CLI's `--content-json` understands exactly three block types
(`heading`, `paragraph`, `pagebreak`). Bold, lists, tables, borders, footers, fonts,
alignment — none of it is expressible. A Chinese contract needs all of them. See ISSUE-001.

## Quick start

The generator reads markdown and writes a formatted .docx. Copy it next to your document so
build artifacts stay out of the skill directory:

```bash
# 1. Stage the generator beside your markdown
mkdir -p _docxgen && cp <skill-dir>/scripts/Program.cs <skill-dir>/scripts/mmdocx-gen.csproj \
   <skill-dir>/scripts/.gitignore _docxgen/

# 2. Generate (first run restores DocumentFormat.OpenXml + Markdig, ~20s)
dotnet run --project _docxgen -- your-doc.md your-doc.docx

# 3. Structural validation via the engine's XSD validator (note the roll-forward env — ISSUE-003)
DOTNET_ROLL_FORWARD=Major dotnet run \
  --project ~/.claude/plugins/marketplaces/minimax-skills/skills/minimax-docx/scripts/dotnet/MiniMaxAIDocx.Cli \
  -- validate --input your-doc.docx

# 4. MANDATORY visual verification — never skip, never substitute qlmanage
soffice --headless --convert-to pdf --outdir /tmp/docxcheck your-doc.docx
pdftoppm -png -r 100 /tmp/docxcheck/your-doc.pdf /tmp/docxcheck/page
# then Read every /tmp/docxcheck/page-NN.png
```

Full command details and troubleshooting: `scripts/README.md`.
Full verification steps and pass/fail criteria: `references/verification_protocol.md`.

## Hard rules (violating these means rework)

### 1. Alignment is layered — this is the expensive one

Never justify the whole document. Three layers, three alignments:

| Content | Alignment | Why |
|---|---|---|
| Document title (H1) | Center | Convention |
| Clause headings (H2+) | Left | Convention |
| **Info blocks and signature blocks** — 甲方/乙方/统一社会信用代码/法定代表人/日期, i.e. any paragraph whose lines are joined by markdown soft or hard line breaks | **Left** | Justification stretches **every line except the paragraph's last**. A multi-line info block is *one* paragraph, so all but its final line get blown out into huge inter-character gaps. |
| Ordinary body prose | Justified (`Both`) | Clean right edge |

The rule is machine-checkable, so do not eyeball it: if the markdown paragraph's inline tree
contains a `LineBreakInline`, left-align that paragraph; otherwise justify it. Implemented at
`scripts/Program.cs` lines 144-147, with the break detection at lines 59-64.
Full write-up: ISSUE-004.

### 2. Every list restarts at 1

Each markdown list must get its **own** `NumId` plus a `LevelOverride` carrying
`StartOverrideNumberingValue = 1`. Reuse one `NumId` across clauses and clause 3's list
silently continues from 4. Implemented at `scripts/Program.cs` lines 148-162 and 183-197.
Two SDK traps come with it (wrong class name, wrong element order) — ISSUE-005, ISSUE-006.

### 3. CJK fonts need both slots

A run must set `RunFonts { Ascii, HighAnsi, EastAsia }`. Setting only the Latin slots leaves
Chinese characters to Word's fallback, and the document renders in whatever the reader's
machine picks. Shipped defaults: Latin `Times New Roman`; East Asian 宋体 for body, 黑体 for
headings. Sizes are OpenXML half-points — body 24 (12pt), H1 36 (18pt), clause heading 28
(14pt). ISSUE-007.

### 4. Page and table basics

A4 is 11906 × 16838 twips with 1440 twip margins; page number goes in a centered footer
`PAGE` field. Tables need all six borders (`top`/`bottom`/`left`/`right`/`insideH`/`insideV`)
— set fewer and cells look unruled in print. Implemented at `scripts/Program.cs`
lines 93-125 and 175-177.

## Verification is not optional

**Banned: `qlmanage` thumbnails as visual proof.** macOS Quick Look renders with a different
engine than Word and will happily show a clean-looking page for a document whose info blocks
are stretched apart. A document was declared "verified perfect" on qlmanage evidence and
opened broken in Word — that is the origin of this rule. ISSUE-008.

**Required chain:** generate → XSD validate → `soffice --headless --convert-to pdf` →
`pdftoppm -png` → `Read` every page image → check the five failure modes
(info blocks not stretched / each list restarting at 1 / table borders present / signature
block intact / no orphaned pagination). Details, prerequisites and the "what counts as
failure" list: `references/verification_protocol.md`.

**Before overwriting a delivered .docx**, check for a sibling `~$<name>.docx` — that is Word's
owner lock, meaning the recipient has the old version open. Overwriting works, but they will
keep seeing the stale document until they close and reopen it. Tell them. ISSUE-011.

## Customizing

`scripts/Program.cs` is ~215 lines of straightforward OpenXML. Edit it directly for fonts,
sizes, spacing, borders, or new block types — that is the intended workflow. Before adding a
structural feature (images, TOC, headers, track changes), read the corresponding
`Samples/*.cs` in minimax-docx first; those patterns are SDK-version-verified and will save
you a compile-error loop.

## References

- `references/known_issues.md` — ISSUE-001…011: symptom / root cause / fix / verification for
  every trap hit while building this pipeline. Read before debugging anything.
- `references/verification_protocol.md` — the full end-to-end verification chain, its
  prerequisites, its pass criteria, and the substitutions that are forbidden.
- `scripts/README.md` — how to run the generator, what markdown it supports, environment
  requirements.
