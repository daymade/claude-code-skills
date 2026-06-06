# Translation Workflow (optional)

Read this only when the user wants the HTML in a different language than the PDF.
Translation runs as a Dynamic Workflow so pages translate in parallel and a final
pass keeps terminology consistent. It must run in the **main context** (this skill
is inline) — a subagent cannot spawn the workflow's agents.

## Contents
- When to translate
- Step A: prepare translation units
- Step B: run the workflow (parallel translate → caption charts → reconcile)
- Glossary discipline
- Fidelity rules
- Chart handling — ask the user
- Text-overlay convention
- Step C: merge back and build

## When to translate
Only when the user asks ("translate to X", "中文版", "make an English version").
Otherwise build directly from the original text — don't translate unprompted.

## Step A: prepare translation units
Extract the text to translate, each with a stable id that **matches the key
`build_html.py` expects** (`p{page}_t{Nth-text-block-on-that-page}`, page numbers
skipped). This is what lets the translation merge back onto the right block.

```python
import json
struct = json.load(open("build/structure.json"))
units = []
for pg in struct["pages"]:
    p, ti = pg["page"], 0
    for b in pg["blocks"]:
        if b["type"] != "text":
            continue
        t = b["text"].strip()
        if t.isdigit() and len(t) <= 4:   # page number — skip, same rule as build_html.py
            continue
        units.append({"id": f"p{p}_t{ti}", "page": p, "src": b["text"]})
        ti += 1
json.dump(units, open("build/units_src.json", "w"), ensure_ascii=False, indent=1)
print(len(units), "units")
```

## Step B: run the workflow
Before launching, read the rendered `pages/*.png` and decide the **register**
(who reads this, how formal) and a **glossary** — these go into every agent prompt
so the whole document sounds like one translator. Skeleton (adapt the bracketed
parts; keep the structure):

```javascript
export const meta = {
  name: 'translate-pdf-units',
  description: 'Translate extracted PDF units in parallel, caption charts, reconcile terminology',
  phases: [{ title: 'Translate' }, { title: 'Captions' }, { title: 'Reconcile' }],
}

const BG = `[1-2 sentences: what this document is, who the reader is, target language + register].`
const GLOSSARY = `[key term -> target-language definition; list names/orgs/products to keep verbatim].`
const CONV = `Output convention: blank line = paragraph break; lines starting "- " = list items; ` +
  `a numbered sub-heading on its own line gets prefixed "## ". Keep ALL numbers, percentages, ` +
  `years and proper nouns verbatim. Never invent a translated name for a real person.`

const U = { type:'object', properties:{ units:{ type:'array', items:{ type:'object',
  properties:{ id:{type:'string'}, tr:{type:'string'} }, required:['id','tr'] } } }, required:['units'] }
const C = { type:'object', properties:{ chart:{type:'string'}, title:{type:'string'}, caption:{type:'string'} },
  required:['chart','title','caption'] }

phase('Translate')                                  // one agent per page, in parallel
const pages = [/* 1, 2, ... N */]
const translated = await parallel(pages.map(p => () =>
  agent(`${BG}\n\nRead /ABS/build/units_src.json. Translate every unit whose page==${p}.\n` +
        `${CONV}\n\n${GLOSSARY}\n\nReturn units:[{id,tr}] with ids exactly as in the file; omit none.`,
        { label:`tr p${p}`, phase:'Translate', schema:U })))

phase('Captions')                                   // one agent per data chart
const charts = [/* { file:'img-p5-1.png' }, ... only real data charts */]
const caps = await parallel(charts.map(c => () =>
  agent(`Read /ABS/build/images/${c.file}. It is a data chart labeled in the source language. ` +
        `Output a target-language title and a 2-4 sentence reading of the REAL data (axes, what rises/` +
        `falls, key values, highest/lowest). State only values actually visible — invent nothing. chart="${c.file}".`,
        { label:`cap ${c.file}`, phase:'Captions', schema:C })))

phase('Reconcile')                                  // one pass to unify terminology
const all = translated.filter(Boolean).flatMap(t => t.units || [])
const fixed = await agent(`${BG}\n\nUnify terminology per the glossary, smooth cross-page seams, ` +
  `change no meaning, add or drop nothing, keep the markdown convention. Return all ${all.length} units, ` +
  `ids unchanged.\n${GLOSSARY}\n\n${JSON.stringify(all)}`, { label:'reconcile', schema:U })

return { units: (fixed && fixed.units) || all, captions: caps.filter(Boolean) }
```

Notes: per-page agents each Read the same units file and filter by page — simple
and robust for a short document. If a page agent dies on a socket close, **resume**
the workflow (failure_cases #5), don't re-run all of them.

## Glossary discipline
Fix the glossary before translating and pass it to every agent. Without it,
recurring terms drift across pages (the same word translated three ways). The
reconcile pass enforces it globally.

## Fidelity rules
A translation is faithful, not a rewrite. Copy numbers/percentages/years and
proper nouns verbatim. **Never give a real person an inferred translated name**
(failure_cases #6). For charts, match the original image pixel-by-pixel. Do not
add a TL;DR, a localization "why this matters to you" aside, or a conclusion the
source didn't write — that's overreach a reviewer will praise and the author never
asked for.

## Chart handling — ask the user
A data chart's internal labels are in the source language. Three options; the
default is the safest. Use AskUserQuestion:
- **Keep original image + target-language caption** (default — zero data risk; the
  caption explains the chart in the reader's language).
- **Keep original + unify a heading bar / frame** (the `--captions` path already
  draws a heading bar; reduces the "pasted from elsewhere" look).
- **Redraw as a native target-language chart** (best integration, but you must read
  every value off the original correctly — only do this once the data is verified,
  and re-draw line charts from real endpoints/trend, not guessed points).

## Text-overlay convention
Translated text uses light markdown: blank line = paragraph, `- ` = list item,
`## ` = sub-heading. `build_html.py`'s renderer understands these, and they also
fix the common case where a PDF splits "...end of section. Next-heading" into one
block across a page break — mark the heading with `## ` and it lays out correctly.

## Step C: merge back and build
Turn the workflow result into the two overlay files `build_html.py` consumes.
Mind two traps: the workflow output is wrapped in `result` (failure_cases #3), and
each string must be `html.unescape`d once (failure_cases #4).

```python
import json, html
res = json.load(open("workflow-output.json"))["result"]      # <-- ["result"], not top level
units = {u["id"]: html.unescape(u["tr"]) for u in res["units"]}
caps = {c["chart"]: {"title": html.unescape(c["title"]),
                     "caption": html.unescape(c["caption"])} for c in res.get("captions", [])}
json.dump(units, open("build/units.json", "w"), ensure_ascii=False, indent=1)
json.dump(caps,  open("build/caps.json",  "w"), ensure_ascii=False, indent=1)

# Verify no unit was dropped before building.
src_ids = {u["id"] for u in json.load(open("build/units_src.json"))}
missing = src_ids - set(units)
print("missing translations:", missing or "none")
```

Then build with the overlays and the right `lang`:

```bash
uv run --with Pillow python build_html.py build/structure.json --out output.html \
    --translation build/units.json --captions build/caps.json --lang zh-CN --title "..."
```
