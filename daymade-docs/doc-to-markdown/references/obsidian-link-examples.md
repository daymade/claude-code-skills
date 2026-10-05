---
name: obsidian-link-examples
description: >-
  Exercise HTML fragments and numbered source labels in an actual Obsidian note.
  Read before batch handoff when navigation or citations must work in Obsidian.
---

# Obsidian link examples

Use these neutral, synthetic samples for a one-page reader pilot. Resolve assets
from this loaded skill; keep source HTML unchanged and adapt the delivered note.

| Asset | Purpose |
|---|---|
| [source.html](../assets/obsidian-links/source.html) | Ordinary HTML IDs and a literal `[1]` source label |
| [legacy.md](../assets/obsidian-links/legacy.md) | Intentionally bad handoff: raw HTML anchors and `[[1]](#source-1)` |
| [fixed.md](../assets/obsidian-links/fixed.md) | Reader-specific targets and escaped numbered source labels |

The legacy sample models manual assembly, an older formatter or a later
post-processing regression. It is not output attributed to the current converter.
The current Pandoc route already emits the numbered label as `[\[1\]](#source-1)`.
Inspect actual target markup too: source IDs may be retained or lost depending on
the element. Even a retained ID does not prove a working recipient jump.

## Read the target, then choose the repair

1. Convert the source through the existing HTML quick path. Read the actual
   output before diagnosing its numbered labels; do not assume it emitted
   the constructed legacy syntax.
2. Open both notes in Obsidian's reading view. In legacy, try Chapter and inspect
   the numbered source's rendered label/target. Once it visibly routes to a wiki
   note instead of the source, record failure; do not click it to create that note.
   In fixed, click Chapter and `[1]` and inspect their actual landing text. The
   titles Evaluation chapter and Reference details deliberately differ from IDs;
   the healthy Controls heading link is a separate control, not an HTML-ID verdict.
3. The fixed sample maps `#chapter` → `#^chapter` and `#source-1` → `#^source-1`.
   Its IDs are at the end of nonempty destination paragraphs:

   ```markdown
   Chapter landing marker. ^chapter
   Source landing marker. Synthetic reference for this test page. ^source-1
   ```

   Use the actual intended landing paragraph. A heading link is another option
   when the note's headings are stable; prove its exact destination before batch
   use. Do not assume a standalone empty ID block is equivalent.
4. For a numbered source label, preserve the author's visible `[1]` while writing
   `[\[1\]](#^source-1)`. Repair only the observed broken link instances.
   Keep the healthy controls: intentional `[[Note]]`, escaped ordinary bracket
   text, and every character inside the fenced code sample. Do not run a global
   bracket or wiki-link regex across the document.
5. Record rewritten source→reader targets and verify each target exists and the
   clicked label lands there. The source-href validator expects original targets;
   a deliberate reader-specific remap needs this mapping and actual reader proof,
   not a claim that the unchanged-target validator passed it.

## Pilot completion

The pilot passes only when both intended jumps reach their correct text in the
actual reading view, the citation retains its visible label, and the healthy
controls survive. Preserve canonical note identity and the tested source/asset
bytes. If Obsidian is unavailable, mark reader behavior partial and retain the
conversion evidence separately. Continue the batch only after the pilot's
required reader behavior is proven; repeat for a materially different link form.

## Bind the repair before automated expansion

Use [the gated batch route](html-conversion.md#gate-a-batch-through-the-existing-recipe)
when expanding through `batch_html.py`. Keep the raw sample unchanged; create
prepared HTML with the authorized reader targets and nonempty landing paragraphs,
for example `<p>Chapter landing marker. ^chapter</p>`. Declare
`#chapter` → `#^chapter` and `#source-1` → `#^source-1` in the plan's provenance.
Preserve the source anchor text `[1]`; let the existing Pandoc owner emit its
escaped Markdown label. Materialize any figure derivative under its actual
relative asset path before `prepare`.

Observe the reproducible pilot note in reading view, then complete a workspace
copy of [the evidence template](../assets/reader-pilot-evidence-template.json).
Set each navigation/citation record's `source_href` to the prepared HTML target;
retain the original→prepared target mapping separately in `provenance`.
Record the exact rendered label, clicked destination and landing text. Bind the
source capture to its explicit raw/prepared role and the recipient capture to
the final pilot note/assets/settings. Run the gate's `check`, then the batch
owner's `run` only after the required reader observations pass.

Keep manually repaired notes supported by the manual protocol above. Do not use
one to authorize automated expansion through a recipe that would omit its repairs;
the fixed sample is a reader control, not proof that batch conversion executed it.
