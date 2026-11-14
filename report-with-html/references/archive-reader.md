# Course and archive reader

Use this reference implementation when the reader needs to browse a course,
open lesson documents and attachments, and play retained media. Start with the
source's course → chapter → lesson relationships, then attach materials to their
lesson. Search and type filters complement this hierarchy; a flat list does not
replace it. Unknown parents stay visibly unassigned rather than being invented.

## Build the hierarchy

Use `scripts/build_archive_reader.py --catalog <catalog.json> --out <new.html>`.
For an update, also pass `--previous <previous-catalog.json>`; preserve that
source-owned previous snapshot before generating the new catalog.

```json
{
  "title": "Course archive",
  "nodes": [
    {"id":"course","title":"Course","parent":null,"status":"current"},
    {"id":"chapter","title":"Chapter","parent":"course","status":"current"},
    {"id":"lesson","title":"Lesson","parent":"chapter","status":"current"}
  ],
  "items": [
    {"id":"notes","node":"lesson","title":"Lesson notes","kind":"document","url":"/document/notes","status":"captured"},
    {"id":"recording","node":"lesson","title":"Recording","kind":"video","url":"/asset/recording","status":"NAS retained"},
    {"id":"reference","node":"lesson","title":"Reference PDF","kind":"pdf","url":"/pdf/reference","status":"captured"}
  ]
}
```

Use existing stable node/material IDs, never filtered row numbers. Take current
sibling/parent relationships from a fresh source navigation observation; retain
its observation time separately from the frozen body capture. Mark removed source
nodes `historical`, preserving their materials and IDs. The builder rejects a
missing old node or material; only explicitly listed `resolved_gap_ids` whose
previous kind was `gap` may retire. This check proves ID retention, not that the
source-derived parent or title is correct: compare those with the source tree.

The generated page embeds its catalog without `fetch()`, renders source text
inertly, groups related assets under their lesson, searches titles plus paths,
and offers a historical-chapter switch. Hash links reveal and expand the target.
It leaves fetching, access identity, permanent storage and asset routing to the
existing archive owner. Preserve that owner's actual directory names and URLs.
The reference is a starting implementation, not a new report-wide visual style
or a substitute for the approved interaction shelf.

## Preview registered PDF pages

When native embeds are blocked or unreadable, use `scripts/pdf_preview.py` in
the **existing loopback server**. Install Poppler through the environment's
existing dependency owner if `pdfinfo`/`pdftoppm` are absent. Register only
verified local PDFs by stable ID and exact relative path:

```python
from pdf_preview import PDFPreview
pdfs = PDFPreview(archive_root, {
    "reference": {"path": "attachments/reference.pdf", "mime": "application/pdf",
                  "bytes": verified_bytes, "title": "Reference PDF"}
})
# In the existing handler, after its normal host/access checks:
response = pdfs.get(parsed.path, parsed.query)
if response is not None:
    status, mime, body = response
    # Send exact Content-Length; HEAD omits body. Use script-src 'none' for this
    # generated PDF page and the server's existing loopback/no-store policy.
```

`/pdf/<id>?page=N` renders navigation plus a readable page image;
`/pdf-page/<id>?page=N` renders one 1600px PNG on demand. Unregistered IDs,
non-PDF records, invalid page values, changed size and unavailable renderers fail
explicitly. No arbitrary filesystem-path endpoint is added. Keep the original
`/asset/<id>` binary response and its MIME, bytes and Range behavior unchanged.
This adapter does not freeze changing sources; use the existing snapshot owner
when immutability is required. It does not certify a browser's native PDF viewer.

## Verify as a reader

Open a known course → chapter → lesson and confirm its associated documents,
PDF and media against the source-owned catalog. Search a lesson term and verify
the breadcrumb and original identity. Reveal a historical chapter and follow a
deep link after reload; compare all old material IDs with the new catalog.

For PDF, inspect the actual first page, click next and read the correct second
page; a button, successful HTTP response or blank native iframe is insufficient.
For media, start playback, observe time advance, seek to a nonzero point and
observe continued playback of the selected source. Keep screenshot, decoded page
and player-time evidence separate; a screenshot timeout does not prove failure
or successful capture. Record any untested original-quality, audio or native
viewer axis explicitly. Stop at verified navigation and source actions.
