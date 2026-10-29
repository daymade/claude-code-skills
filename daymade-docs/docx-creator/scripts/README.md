# `mmdocx-gen` — markdown to Chinese formal .docx

A C# console app built on the OpenXML SDK that `minimax-skills:minimax-docx`
provides. It exists because that skill's CLI can only emit headings, paragraphs and page
breaks, which is not enough for a contract (see `references/known_issues.md`, ISSUE-001).

This is verified code — it produced production Chinese agreements that passed XSD validation
and page-by-page visual review. Prefer editing it over rewriting it.

## Requirements

| Requirement | Check | Notes |
|---|---|---|
| .NET SDK | `dotnet --version` | Match `TargetFramework` in [`mmdocx-gen.csproj`](mmdocx-gen.csproj). If adapting that target, verify the generated artifact under the selected SDK. |
| NuGet reachable | first `dotnet run` restores | Package identities and pins are defined by [`mmdocx-gen.csproj`](mmdocx-gen.csproj). |
| LibreOffice | `ls /Applications/LibreOffice.app/Contents/MacOS/soffice` | Needed for verification, not generation. Install check is itself a trap — ISSUE-009. |
| poppler | `which pdftoppm` | `brew install poppler` |

## Run

Stage the generator files next to your markdown so `bin/`, `obj/` and the NuGet restore stay out
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

The generator's target is defined in [`mmdocx-gen.csproj`](mmdocx-gen.csproj); it does not
automatically select the installed SDK's framework. For the engine CLI's launch failure and
per-invocation roll-forward remedy, follow
[`known_issues.md`, ISSUE-003](../references/known_issues.md#issue-003--minimax-docxs-cli-will-not-launch-on-a-net-10-only-machine-p1):

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
| `# H1` | Centered heading |
| `## H2` and deeper | Left-aligned heading |
| Paragraph, no line breaks inside | Justified body with the configured first-line indent |
| Paragraph **with** soft/hard line breaks | **Left-aligned** body, no indent — this is the info-block and signature-block rule, ISSUE-004 |
| `**bold**` | Bold run; Chinese emphasis uses the family selected by `RunProps` rather than faux bold; nested inline emphasis preserved (ISSUE-014) |
| `1.` / `-` lists | Numbered or bulleted, each list restarting at 1, hanging indent |
| Pipe tables | Complete borders, bold header row and configured table width |
| `---` | Horizontal rule as a bottom-bordered empty paragraph |

Everything else in the markdown AST is skipped silently — blockquotes, fenced code, images,
links-as-hyperlinks are **not** implemented. If a document needs them, add a `case` to the
block switch in `Program.cs` and read the matching `Samples/*.cs` in minimax-docx first.

Typography, dimensions, page setup and footer fields are defined in
[`Program.cs`](Program.cs), at the constants, `RunProps`, `BuildTable` and `Main` setup.

## Where things are in `Program.cs`

Search the function/case names below in [`Program.cs`](Program.cs).

| Concern | Find it at |
|---|---|
| Font constants, sizes | `const string SONG`, `const string BODY` (top of `class Program`) |
| Run properties (CJK dual slot, ECMA-376 rPr child order) | `static RunProperties RunProps(...)` |
| Inline walker + line-break detection (drives the alignment rule) | `static (List<Run> runs, bool hasBreak) InlineRuns(...)` |
| Paragraph builder (numPr, spacing, justification — ECMA-376 pPr child order) | `static Paragraph Para(...)` |
| Table builder (tblGrid, complete borders — ECMA-376 tblPr/tblBorders child order) | `static Table BuildTable(...)` |
| Block dispatch — heading / paragraph / list / table / rule | `switch (block)` inside `static void Main(...)` |
| Alignment decision for body paragraphs | the `case ParagraphBlock p:` arm of that switch |
| Section properties (A4, margins) | `new SectionProperties(...)` right after the `switch` block |
| `styles.xml` (Normal / DefaultParagraphFont / TableNormal) | `main.AddNewPart<StyleDefinitionsPart>()` |
| `settings.xml` (compatibilityMode — ISSUE-012 fix) | `main.AddNewPart<DocumentSettingsPart>()` |
| Numbering part (abstract nums, per-list restart) | `main.AddNewPart<NumberingDefinitionsPart>()` |
| Footer with `PAGE` field | `main.AddNewPart<FooterPart>()` |

## After generating

Generation succeeding proves nothing about how the file looks in Word. Run the verification
chain in `references/verification_protocol.md` — it is mandatory, and `qlmanage` is not an
acceptable substitute for it.
