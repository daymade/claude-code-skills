# Maintainer testing

Use this procedure when changing this Skill's source. Run from
`<repo-root>/daymade-docs/pdf-creator` in a verified source checkout. Installed
packages can omit `scripts/tests`; a missing directory means this source-only
recipe is unavailable there, not that the converter failed. Resolve the declared
source checkout before continuing; do not silently download another test suite.

## Prepare the selected checks

Follow the repository's [Python requirements](https://github.com/daymade/claude-code-skills/blob/main/CLAUDE.md#python-development)
and use `uv`. Inspect the selected tests' native prerequisites before
running: Pandoc for Markdown conversion; Poppler (`pdfinfo`, `pdftotext`,
`pdftoppm`) for PDF text, metadata and raster checks; a working WeasyPrint system
runtime for its integration cases; and the actual Chrome/Edge installation for
browser-specific acceptance. Read each tool's version and perform the affected
small operation. A command on PATH alone does not prove its runtime works.

Install or configure missing prerequisites only within existing authorization.
Retain unavailable integration checks explicitly as gaps while running independent
tests. Do not interpret a pytest skip as evidence that its native operation works.

Run the complete source test suite with its Python dependencies in one isolated
environment, without adding them to an unrelated project's environment:

```bash
uv run --isolated --no-project \
  --with pytest --with pillow --with pdfplumber --with weasyprint --with numpy \
  python -m pytest scripts/tests -q
```

Use the same environment for a bounded selection by replacing `scripts/tests`
with the selected test path or node. Preserve the exit status
and inspect skipped tests and failures. Clear collection/import failures before
claiming any test result. Keep these development dependencies separate from
ordinary converter requirements; Chrome rendering does not require this whole
test environment.

## Accept the affected consumer behavior

For encoding or Windows discovery changes, enter
[QA runtime compatibility acceptance](https://github.com/daymade/claude-code-skills/blob/main/qa-expert/references/runtime-compatibility-acceptance.md#select-encoding-and-execution-path-cases).
Bind the selected cases to the converter's
[backend selection](../SKILL.md#backends) and
[typography lint conditions](../SKILL.md#layer-2-typography-lint-post-render-detection-catches-the-rest).
Include a small table in the fixture to exercise its table checks.
Complete the [visual delivery checks](../SKILL.md#visual-self-check-mandatory--do-not-skip)
on the resulting PDF.
