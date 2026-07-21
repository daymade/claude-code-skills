# `mmdocx-gen` — markdown to Chinese formal .docx

A ~215-line C# console app built on the OpenXML SDK that `minimax-skills:minimax-docx`
provides. It exists because that skill's CLI can only emit headings, paragraphs and page
breaks, which is not enough for a contract (see `references/known_issues.md`, ISSUE-001).

This is verified code — it produced production Chinese agreements that passed XSD validation
and page-by-page visual review. Prefer editing it over rewriting it.

## Requirements

| Requirement | Check | Notes |
|---|---|---|
| .NET SDK | `dotnet --version` | The shipped `mmdocx-gen.csproj` targets `net10.0`. On an older SDK, change `TargetFramework` to your SDK's major version — the code uses no version-specific APIs. |
| NuGet reachable | first `dotnet run` restores | Pulls `DocumentFormat.OpenXml` 3.2.0 and `Markdig` 1.3.2 |
| LibreOffice | `ls /Applications/LibreOffice.app/Contents/MacOS/soffice` | Needed for verification, not generation. Install check is itself a trap — ISSUE-009. |
| poppler | `which pdftoppm` | `brew install poppler` |

## Run

Stage the three files next to your markdown so `bin/`, `obj/` and the NuGet restore stay out
of the skill directory:

```bash
mkdir -p _docxgen
cp <skill-dir>/scripts/Program.cs <skill-dir>/scripts/mmdocx-gen.csproj \
   <skill-dir>/scripts/.gitignore _docxgen/

dotnet run --project _docxgen -- your-doc.md your-doc.docx
```

On success it prints the output path, byte count, and how many independent numbered lists it
created — a cheap sanity signal: that count should equal the number of separate lists in your
markdown, because each one gets its own restart-at-1 numbering instance.

Running in place (`dotnet run --project <skill-dir>/scripts -- in.md out.docx`) also works;
it just leaves build output inside the skill (already gitignored).

## `DOTNET_ROLL_FORWARD=Major`

**Not needed for this generator** — it targets your current SDK. It **is** needed whenever you
invoke minimax-docx's own CLI, which targets `net8.0`:

```bash
DOTNET_ROLL_FORWARD=Major dotnet run \
  --project ~/.claude/plugins/marketplaces/minimax-skills/skills/minimax-docx/scripts/dotnet/MiniMaxAIDocx.Cli \
  -- validate --input your-doc.docx
```

Without it, on a machine that has only .NET 10 installed, the app refuses to launch with
`You must install or update .NET ... Framework: 'Microsoft.NETCore.App', version '8.0.0'`.
Full explanation: ISSUE-003.

## Supported markdown

| Markdown | Rendered as |
|---|---|
| `# H1` | Centered, 黑体 18pt bold |
| `## H2` and deeper | Left, 黑体 14pt bold |
| Paragraph, no line breaks inside | Justified body, 宋体 12pt |
| Paragraph **with** soft/hard line breaks | **Left-aligned** body — this is the info-block and signature-block rule, ISSUE-004 |
| `**bold**` | Bold run (nested inline emphasis preserved) |
| `1.` / `-` lists | Numbered or bulleted, each list restarting at 1, hanging indent |
| Pipe tables | Full six-border table, header row bold, 100% width |
| `---` | Horizontal rule as a bottom-bordered empty paragraph |

Everything else in the markdown AST is skipped silently — blockquotes, fenced code, images,
links-as-hyperlinks are **not** implemented. If a document needs them, add a `case` to the
block switch in `Program.cs` and read the matching `Samples/*.cs` in minimax-docx first.

Page setup is fixed at A4 with 1440-twip margins and a centered `PAGE` field footer.

## Where things are in `Program.cs`

| Concern | Lines |
|---|---|
| Font constants, sizes, run properties (CJK dual slot) | 17-39 |
| Inline walker + line-break detection (drives the alignment rule) | 41-77 |
| Paragraph builder (justification, spacing, numbering ref) | 79-91 |
| Table builder (six borders) | 93-125 |
| Block dispatch — heading / paragraph / list / table / rule | 135-173 |
| Alignment decision for body paragraphs | 144-147 |
| Section properties (A4, margins) | 175-177 |
| Numbering part (abstract nums, per-list restart) | 183-197 |
| Footer with `PAGE` field | 199-210 |

## After generating

Generation succeeding proves nothing about how the file looks in Word. Run the verification
chain in `references/verification_protocol.md` — it is mandatory, and `qlmanage` is not an
acceptable substitute for it.
