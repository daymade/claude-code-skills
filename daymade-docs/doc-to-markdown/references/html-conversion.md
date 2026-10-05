---
name: html-conversion
description: >-
  Convert saved HTML/HTM to Markdown with Pandoc, verify source links, and assemble
  chapter or book headings without editing code fences. Read for website/manual conversions.
---

# Saved HTML to Markdown

Use the existing Pandoc conversion owner. Acquire remote pages through the
appropriate website-fetching workflow first; this converter consumes local UTF-8
HTML/HTM and does not crawl pages or download assets.

## Convert one page

Run from this skill's directory, or resolve `scripts/convert.py` from its loaded path:

```bash
uv run scripts/convert.py page.html -o page.md
uv run scripts/convert.py page.html -o page.md --html-selector '#main-content'
uv run scripts/convert.py lesson.html -o lesson.md --html-heading-offset 2
```

Pandoc must be installed. HTML uses `-f html -t gfm --wrap=none`; the existing
Office quick/heavy and post-processing paths remain separate. Read
`scripts/convert.py --help` for the current interface before adding flags.

By default the entire body is converted, including navigation present there.
Use `--html-selector` only after inspecting the saved page and deciding the
intended content boundary. It accepts one tag, `#id` or `.class`, requires exactly
one match, and does not accept compound CSS selectors. Zero or multiple matches
fail instead of silently guessing. Keep navigation or link cards that belong to
the authorized content; choosing a smaller selector changes the conversion scope.

Relative link/image targets are retained; prefer output beside the saved source.
On relocation, the caller rebases links and materializes assets in the actual folder.
For HTML `<base>`, resolve targets using the original page URL and its base before conversion
and use that resolved HTML for link verification. `--assets-dir` and `--heavy` fail.
Media is not downloaded. Inline SVG becomes a data URI retaining internal styling;
external CSS, inherited colors and captions still need actual-reader verification.

## Verify link retention

The HTML branch counts source `href` occurrences in the selected content and
compares them with Link nodes obtained by parsing the emitted GFM through Pandoc's
JSON AST. Success prints `HTML links verified`; missing occurrences fail before
atomic output replacement. Inspect both the exit status and that positive result.

An HTML card such as `<a><strong>Title</strong><p>Preview</p></a>` can contain block
content that does not map to one multiline Markdown link. Verify that its title
remains a clickable link and its preview remains readable content; do not repair
it by concatenating raw lines inside `[...](...)` or replacing the converter.

Keep source-side expected destinations for the next stage. After any cleanup,
heading change or merge, parse the final Markdown AST and reconcile expected
destinations and occurrence counts again. For unchanged destinations, run:

```bash
uv run scripts/html_to_markdown.py page.html page.md --html-selector '#main-content'
```

Pass the same selector used for conversion; omit it for the whole-body default.
The validator prints the number of source hyperlinks retained, or fails with the
missing destination/count. If links are deliberately rewritten,
record an explicit old→new mapping and validate the new target/anchor. A check
reporting “zero broken links” can pass after every link was deleted; it cannot
replace this source-to-output comparison.

## Gate a batch through the existing recipe

Use `scripts/batch_html.py` on Linux/macOS for ordered local-page conversion.
Keep the raw sources unchanged. Prepare a dedicated input folder containing the
selected HTML and its complete local dependencies. Resolve `<base>`, page links,
reader fragments and asset paths in these prepared inputs before freezing them.
Keep each source and its planned Markdown output in the same relative parent
directory. Use the delivered folder's actual asset paths. Dynamic scripts and event
handlers, `srcset`, remote rendering dependencies and page links still targeting
HTML are rejected; external HTTP navigation links remain supported.

Record actual reader settings in a JSON file outside the input folder: `reader`,
`version`, `mode` (`reading`), `theme`, positive `body_width_css_px` and
`device_scale`, and `capture_context` identifying the observed canvas/window.
Create a plan with the authorized page order:

```json
{
  "input_root": "/absolute/path/ready-html",
  "reader_settings_path": "/absolute/path/reader-settings.json",
  "pages": [
    {"source": "page-1.html", "output": "page-1.md", "selector": "main", "heading_offset": 0},
    {"source": "page-2.html", "output": "page-2.md", "selector": "main", "heading_offset": 0}
  ]
}
```

For adapted inputs, add ordered `provenance` records, one per page:
`prepared_source`, retained `raw_source` (`path` and `sha256`), `target_mapping`
and `asset_mapping` arrays of `{ "from": "original target", "to": "prepared target" }`.
Declare empty arrays when no remap occurred. Mappings retain provenance; they
do not execute transformations. Without `provenance`, each selected input is
also bound as its raw source.

Run from this skill's directory; use new paths whose parents already exist:

```bash
uv run --no-project python scripts/batch_html.py prepare plan.json --manifest manifest.json --pilot-dir pilot
uv run --no-project python scripts/reader_pilot_gate.py check manifest.json evidence.json
uv run --no-project python scripts/batch_html.py run manifest.json evidence.json --output-dir delivered
```

After `prepare`, open the printed pilot note in the actual reader. Fill a
workspace copy of [the evidence template](../assets/reader-pilot-evidence-template.json)
from retained observations: observer identity/method/time, separate observation
artifact, source and recipient capture bindings, exact navigation and citation
labels/destinations/landing text, whole-figure labels/relations/caption, and the
frozen reader state. Bind raw source captures with `source_role: "raw"` and
recipient captures with `source_role: "prepared"`. Copy manifest values for
source/note/settings hashes; calculate `assets_sha256` with
`reader_pilot_gate.digest_object(manifest["pilot"]["assets"])`.

Require exit 0 and the nonzero observation counts from `check` before `run`.
The gate checks evidence completeness and current bytes, not click or legibility
truth; the observer still performs the reading-view checks. A hand-edited pilot
note cannot authorize this recipe: its bytes must reproduce through the existing
Pandoc owner. Move authorized repairs into prepared HTML/assets and run a new
pilot instead. Changed inputs, recipe, captures or reader settings require fresh
evidence. `run` checks before creating/converting batch outputs, exclusively
writes a new folder, reconciles source hyperlink counts, and reads back final
note/asset hashes. Retain any failed folder for diagnosis; only a `complete`
`batch-result.json` with matching output hashes establishes batch completion.
This route emits ordered page notes; keep the assembly checks below for a book.

## Assemble a manual or book

Before merging, freeze the authorized page order and chapter/lesson mapping from
the collection manifest. Do not infer book order from filenames or fetch order.

- In a combined book, use one H1 for the book, H2 for chapters and H3 for lessons.
  Do not remap standalone pages/chapters automatically: retain their source structure
  or the requested hierarchy (for example, chapter H1 and lesson H2).
- Inventory each page's semantic headings. Replace a duplicate page-title heading
  with the chosen lesson heading only when they identify the same lesson. Promote a
  genuine section heading that was merely bold in HTML, then offset internal
  sections below that lesson while retaining their relative nesting. If meaningful depth
  exceeds H6, resolve the structure explicitly rather than flattening it silently.
- Transform parsed Header nodes (or another fence-aware structural representation),
  not every line beginning with `#`. Preserve code contents during heading changes;
  a heading-looking line in code is not a document heading.
- Rebase image/file paths from each page's original location to the final folder.
  Reconcile internal links with the final heading/anchor map, then run the
  expected-link comparison on the assembled artifact.
- Verify one book title for a combined book, the declared chapter/lesson sequence, internal
  heading nesting, unchanged code blocks, figure/caption association and source
  link retention. Merely concatenating individually valid Markdown pages does
  not establish a valid book hierarchy.

The converter preserves heading levels by default. `--html-heading-offset N`
accepts 0..5 and shifts parsed headings; in a combined book, offset 2 maps H1 to H3
and H2 to H4 without editing fenced code. It rejects headings that would exceed
H6. Add book/chapter headings separately; offset alone cannot recover headings
that were only bold or determine the page-title/lesson mapping.
The assembling agent owns that structure and its checks. Use `frontend-visual-qa`'s
Markdown reader handoff reference when installed; keep conversion success separate
from unverified reader presentation.

For Obsidian chapter jumps or numbered citations, run the one-page handoff in
[obsidian-link-examples.md](obsidian-link-examples.md) before batch assembly;
source-link retention and actual reader target behavior are separate checks.
