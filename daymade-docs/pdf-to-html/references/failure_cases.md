# Failure Cases — Do NOT Attempt

Real traps from building this pipeline. Each one cost a wrong turn; reading them
saves you the same detour. Skim before you start, re-read #6 before translating.

## Contents
- Verification traps (#1, #7)
- Chrome rendering limit (#2)
- Workflow / agent traps (#3, #4, #5)
- Fidelity rule — the important one (#6)
- Image classification (#8)

---

## 1. `grep -c` counts lines, not matches
When you sanity-check the built HTML ("are there 3 `<li>`? 4 `<figure>`?"),
`grep -c '<li>' file` counts **lines that contain a match**. Minified HTML often
puts several `<li>` on one line, so `grep -c` reports `1` when there are really 3
— and you "discover" a structure bug that isn't there.
**Do:** `grep -o '<li>' file | wc -l` to count occurrences.

## 2. Chrome headless screenshot caps around 16384px
A 2x device-scale-factor screenshot of a long page **silently truncates** once
physical height passes ~16384px — no error, the bottom just vanishes. You verify
the top, declare success, and miss that the last sections never rendered.
**Do:** probe real height at 1x first, then pick a scale that keeps the whole
page under the cap. `verify_render.py` already does this; remember it for any
manual screenshot.

## 3. Dynamic Workflow return value is wrapped
A workflow's task-output file is `{summary, agentCount, logs, result}` — the value
your script returned lives under **`result`**. `json.load(f)["units"]` throws
`KeyError`; read `json.load(f)["result"]["units"]`.

## 4. Translated text may arrive HTML-entity escaped
A translation agent sometimes emits `>` as `&gt;`. If you then `html.escape()` it
again you get `&amp;gt;`, which renders as the literal `&gt;`. **Do:**
`html.unescape()` each translated string once before merging it in.

## 5. Agent socket failure → resume, don't restart
In a multi-agent workflow an individual agent can die on a transient socket close
("The socket connection was closed unexpectedly"). Don't re-run the whole batch —
**resume** the workflow: completed agents return from cache, only the failed ones
re-run. (Don't pre-conclude it's a "blip" either — but for a one-off transient,
resume is the cheap correct move.)

## 6. FIDELITY: never invent a name, number, or fact (the important one)
When translating, do **not** give a real person a translated name you inferred.
Real case: a romaji name with no given Han/Kanji form was "helpfully" rendered
into characters by sound — that assigns a real human an identity the source never
stated, and it was probably wrong too. **Keep the original spelling.**

Same rule for everything factual: copy numbers, percentages, years, and proper
nouns (people, companies, institutions, products) verbatim — never infer them.
For any data chart, have the agent Read the original image and match values
**pixel-by-pixel** before writing a caption; don't write numbers "from memory".

And translate faithfully: a translation is not a rewrite. Do not add a TL;DR the
author didn't write, a "why this matters to *you*" localization aside, or a
one-line conclusion the source doesn't state. Those are the reviewer's favorite
overreach; refuse them.

This is where a faithful-looking deliverable most easily goes wrong and where it
most damages trust.

## 7. Text-correct is not render-correct
Confirming the text is right (grep found the words, python read the string) is
**not** enough. Fonts fall back to tofu boxes, tables overflow their column, a
translated heading wraps into an ugly orphan — none of it shows up until you LOOK
at the rendered page. Visual verification is a required step, not an optional one.

## 8. Decorative images vs content images
A PDF carries lots of non-content rasters: footer logos repeated every page,
hairline rules, bullet glyphs. They're tiny (often < 3 KB) or appear at the same
bbox on every page. Inlining them pollutes the reading flow. Classify by byte
size + repeated-bbox-across-pages (`extract_pdf.py` flags `decorative`), and drop
them by default. Keep them only if a document genuinely uses a small image as
content.
