# Document conversion examples

Run these commands from the Skill directory after following
[converter installation](tool-comparison.md#installation). Use a new output location;
keep the source and any extracted assets together with the delivered Markdown.
The CLI writes Pandoc image references relative to the Markdown output directory,
including when it chooses the default assets directory. Keep that directory when
moving or sharing the output.

## Single files and quoted paths

```bash
# Word: require the Pandoc path for generated-numbering repair.
uv run scripts/convert.py "case questions.docx" --tool pandoc -o "case questions.md"

# PDF and PowerPoint: use the format selection and post-processing in the converter.
uv run --with pymupdf --with pymupdf4llm --with "markitdown[pdf]" scripts/convert.py "report.pdf" -o "report.md"
uv run --with "markitdown[pptx]" scripts/convert.py "presentation.pptx" -o "slides.md"
```

Before delivering a Word questionnaire, follow [DOCX numbering](docx-numbering.md).
For a PDF, follow [PDF acceptance](pdf-acceptance.md). A successful conversion or an
existing output file does not establish fidelity.

## Windows paths from WSL

Use paths visible inside the runtime executing the converter. For example,
`C:\Users\<windows-user>\Documents\case questions.docx` is
`/mnt/c/Users/<windows-user>/Documents/case questions.docx` inside WSL.
The helper also handles other drive letters:

```bash
wsl_path=$(python3 scripts/convert_path.py 'D:\Projects\case questions.docx')
uv run scripts/convert.py "$wsl_path" --tool pandoc -o "case questions.md"
```

## Word batch with directory structure preserved

Run in Bash. Set `input_root` to an existing directory and `output_root` to a new
directory outside it. This recipe stops on conversion failure and does not treat
an old Markdown file as evidence that the source was converted correctly.

```bash
set -euo pipefail
input_root="/path/to/source documents"
output_root="/path/to/new markdown"
test -d "$input_root"
mkdir "$output_root"

find "$input_root" -type f -name '*.docx' -print0 |
while IFS= read -r -d '' source; do
  relative="${source#"$input_root"/}"
  output="$output_root/${relative%.docx}.md"
  mkdir -p "$(dirname "$output")"
  uv run scripts/convert.py "$source" --tool pandoc -o "$output"
done
```

Validate each output against its original before delivery. Inspect a failed
conversion's diagnostic and fix the cause before rerunning it; preserve any
existing work that a rerun would replace. Saved HTML batches have their own
[pilot and reader checks](html-conversion.md#gate-a-batch-through-the-existing-recipe).

## Legacy Word and Confluence exports

Inspect the file's actual format before selecting a converter. A binary `.doc`
needs an exported `.docx` copy from Word or LibreOffice; keep the original and then
apply the DOCX procedure to that copy. Do not promise the numbering repair for
legacy `.doc` input.

Some Confluence downloads named `.doc` contain HTML. If inspection confirms HTML,
save a copy with the matching extension and use the [saved HTML procedure](html-conversion.md).
Do not guess a character encoding or recode a binary Word file to resolve garbled text.
