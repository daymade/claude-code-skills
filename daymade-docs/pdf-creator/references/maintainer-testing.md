# Maintainer testing

Use this procedure when changing this Skill's source. Run from
`<repo-root>/daymade-docs/pdf-creator` in a verified source checkout. Installed
packages can omit `scripts/tests`; a missing directory means this source-only
recipe is unavailable there, not that the converter failed. Resolve the declared
source checkout before continuing; do not silently download another test suite.

## Prepare the selected checks

Use Python 3.10+ and `uv`. Inspect the selected tests' native prerequisites before
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

Use the same environment for a bounded selection by appending the test node/path
to the pytest invocation instead of `scripts/tests`. Preserve the exit status
and inspect skipped tests and failures. Clear collection/import failures before
claiming any test result. Keep these development dependencies separate from
ordinary converter requirements; Chrome rendering does not require this whole
test environment.

## Accept the affected consumer behavior

For encoding or Windows discovery changes, enter
[QA runtime compatibility acceptance](https://github.com/daymade/claude-code-skills/blob/main/qa-expert/references/runtime-compatibility-acceptance.md#select-encoding-and-execution-path-cases).
Preserve the original input and expected visible text before testing. Record
the actual executable invoked; `--backend chrome` can select Chrome or Edge and
does not establish which executable ran. Keep modeled discovery/pipe tests
distinct from native Windows rendering.

Use a synthetic mixed Chinese/ASCII document with Unicode metadata and a small
table. Check exact extracted text and metadata, inspect the rendered page, and
follow the Skill's existing visual/table-border checks. When changing optional
Poppler handling, test tools missing and present. Keep previews enabled when
accepting the post-render typography lint: `--no-preview` also disables that lint
and cannot verify its missing-tool handling. Keep test profiles and output paths
isolated without stopping existing browsers or altering user profiles.

Reuse passing evidence for unchanged code and inputs. Finish after the affected
failures, healthy controls and required native observations have evidence; report
any required unavailable observation precisely.
