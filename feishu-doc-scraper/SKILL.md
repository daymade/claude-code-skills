---
name: feishu-doc-scraper
description: Extract Feishu (Lark) Docs, Wiki pages/collections, spreadsheets, and Minutes (妙记) transcripts into faithful local Markdown via the lark-cli API (no LLM rewriting of the body; browser-DOM fallback when lark-cli can't reach the content). Use whenever the source is a Feishu/Lark URL and fidelity matters — 导出飞书文档/合集/妙记转写, 把飞书 wiki/知识库转 markdown, archiving a Feishu collection, exporting a 妙记 transcript, or saving a Feishu page — even if the user only says clipping, archiving, converting, or "save this". Also covers the owner-exported .docx → faithful Markdown path.
compatibility: Primary path needs the `lark-cli` binary (npm `@larksuite/cli`; verified 1.0.32, 2026-05, and re-verified 1.0.80, 2026-08 — the `.data.markdown` field is null on 1.0.80 and the pandoc/`source.html` path in step 3 is load-bearing there) authenticated to the target tenant. Fallback path needs a browser automation surface with an authenticated session (Chrome DevTools MCP / Browser Use / Computer Use). docx path needs `python-docx` and a docx→md converter (the bundled doc-to-markdown skill or pandoc).
argument-hint: "[feishu-url-or-output-path]"
---

# Feishu Doc Scraper

Extract a Feishu/Lark source into faithful local Markdown. **Prefer the lark-cli API** — it extracts the body programmatically (no model paraphrasing), follows a collection's reference graph, and reads permission boundaries from error codes instead of guessing. Treat the rendered browser page as a *fallback*, not the source of truth: in real collection-scraping work the API path consistently does the whole job while the browser path is never needed.

## Scope (read this first)

This skill's contract is **faithful per-source Markdown + a record of what was extracted**. It does *not* decide how the resulting files are named, indexed, deduplicated against existing notes, or organized into a knowledge base — that belongs to the host PKM / the user's own conventions. Stopping at faithful extraction keeps this skill orthogonal and reusable. When the user wants the output filed into a vault, extract first, then hand the clean Markdown to their organizing workflow.

**Extraction and durable storage are separate decisions.** A downloaded MP4/XLSX/DOCX/image is a working copy, not evidence that the file belongs in Git or Git LFS. For a knowledge-base archive, default to:

- Git: faithful Markdown plus structured CSV/JSON/HTML, source locators, revision/permission state, byte counts, MIME types, and hashes.
- Platform original: Feishu remains the source of record for raw binary attachments when the stable document/file token is still retrievable. A local download is an optional cache and may be absent on a fresh clone.
- OSS/object storage: only when the archive needs an independent durable copy or the platform source is not a reliable long-term retrieval path. Uploading is a separate authorized operation, not a fallback the extractor chooses by itself.

Before filing an archive, declare this split in an artifact manifest and run the bundled storage validator. The complete schema and examples are in **[references/archive-storage-contract.md](references/archive-storage-contract.md)**.

## Choose the path

```
Is the source a Feishu/Lark URL (wiki / docx / sheets / minutes / base)?
├── YES → is lark-cli installed and authenticated to that tenant?
│        ├── YES → PATH A: lark-cli API extraction  (primary — start here)
│        │         └── hit code 131006 / 99991679 (permission denied)?
│        │              └── PATH B: owner-exported .docx → faithful Markdown
│        └── NO  → install/auth lark-cli first (it is worth it); only if
│                  truly impossible → PATH D: browser DOM fallback
├── the URL is a Minutes / 妙记 link, or a doc references one → PATH C: Minutes transcript
└── you were handed an exported .docx (not a URL) → PATH B
```

⚠️ **`base` (Bitable) is not actually operationalized in Path A yet** — the extractor only records the token (`DISPATCH["url-base"]`: *"Bitable API (outside this skill) — record token"*) and Step 2 below has no row for it. Listed here for completeness of what a Feishu URL can be, not as a claim that Path A extracts Bitable content end-to-end.

A collection/hub is just a docx whose body references other docs — **Path A handles it by recursively following the reference graph**, not by visiting pages in a browser.

## Path A — lark-cli API extraction (primary)

Full command catalog, recursion engine, cross-tenant and personal-space nuances: **[references/lark-cli-api-extraction.md](references/lark-cli-api-extraction.md)**. The essentials for the common case:

**1. Disable the proxy for Feishu domestic domains.** Feishu's `*.feishu.cn` endpoints are direct-connect in mainland China; routing them through a local proxy leaks credentials through the proxy and gets DNS-hijacked. lark-cli itself warns about this. Always:

```bash
export LARK_CLI_NO_PROXY=1
```

This does not conflict with any "Claude/Anthropic domains must use the proxy" rule — Feishu is a different host and is direct.

**2. Classify the URL, then resolve to a fetchable doc token.**

- `…/wiki/<node_token>` — a wiki node token is **not** a doc token. Resolve it first:
  ```bash
  lark-cli wiki spaces get_node --params '{"token":"<node_token>"}'
  # → .data.node.obj_token  and  .data.node.obj_type  (e.g. "docx")
  ```
- `…/docx/<doc_token>` — already a doc token, fetch directly.
- `…/sheets/<token>` — spreadsheet, use the sheets commands (see reference).
- `…/minutes/<token>` — Minutes, go to **Path C**.

**3. Fetch the body programmatically — never via the model.** The body field moved across lark-cli versions, so probe both rather than hard-coding one (this keeps working whichever version is installed):

```bash
lark-cli docs +fetch --doc <obj_token> --format json > /tmp/fetch.json 2> /tmp/fetch.err
# ≤1.0.32: clean Markdown in .data.markdown.
# 1.0.55: body moved to .data.document.content as HTML (.data.markdown is null).
if jq -e -r '.data.markdown // empty' /tmp/fetch.json > "<sanitized-title>.md" && [ -s "<sanitized-title>.md" ]; then
  : # got clean Markdown directly
else
  jq -r '.data.document.content' /tmp/fetch.json > "<sanitized-title>.html"
  pandoc -f html -t gfm "<sanitized-title>.html" > "<sanitized-title>.md"
fi
```

⚠️ **`<sanitized-title>` must be a distinct name per document, never the literal string "source" reused across fetches.** Step 4 below fetches multiple documents (the hub, then every child it references) into the same working directory — running this exact snippet twice with a hardcoded `source.md`/`source.html` would let the second fetch silently overwrite the first document's saved body before you ever got to check it. The rest of this section still says "`source.html`"/"`source.md`" as shorthand for *whichever document's own saved files you're currently looking at* — not one shared filename for the whole collection.

⚠️ **On this pandoc branch, `pandoc -f html -t gfm` silently strips several of Feishu's custom embedded tags — verified against real documents, 2026-08-16/17, and the damage is worse the deeper you look:**
- **whiteboard** (`<whiteboard token="…">`, an inline diagram block) vanishes with zero trace. Confirmed on a real document: 3 raw tags in `.data.document.content` → 0 trace in the pandoc-converted `source.md` (`grep -c whiteboard` found 3 hits in the raw HTML, 0 in the converted Markdown).
- **mention-doc** — whose real raw tag is `<cite doc-id="…" file-type="wiki|docx" title="…" type="doc"></cite>`, not the `<mention-doc token="…" type="…">Title</mention-doc>` shape this skill originally assumed — also vanishes with zero trace, and worse than just losing the token/type: the title lives in a `title="…"` attribute and the tag body is empty, so pandoc drops the whole element and not even the bare title text survives.
- **sheet** is unconfirmed either way (no real sheet-reference document was found to test) — treat it as capable of silently vanishing too until proven otherwise.
- **image** — whose real raw tag is a standard `<img src="<drive-token>" alt="…" …>`, not `<image token="…">` — does *not* vanish: pandoc passes the raw `<img>` element through mostly intact (`src`/`id`/`href`/`width`/`height`/`alt` survive; `name=` is dropped; `mime=`/`scale=` are renamed `data-mime=`/`data-scale=`).
- **lark-table** turns out not to be a real tag for ordinary docx tables at all — they use plain `<table>` HTML, and pandoc generally converts them intact (clean GFM pipe-table syntax for single-paragraph cells, or a raw `<table>` HTML block for multi-paragraph cells) — not part of this silent-loss class.

Because the loss is real and type-dependent, **extraction (step 4) and the residual-tag check (step 5) must operate on `source.html`, never on `source.md`, whenever this pandoc branch was taken.** On the `.data.markdown` branch (≤1.0.32), if it is still reachable at all, the tags already survive as literal text directly in `source.md`, and checking `source.md` there remains correct — this caveat is specific to the pandoc fallback, which is the **current default**: `.data.markdown` was `null` in every real document checked (11/11 — 3/3 fresh fetches on the currently-installed lark-cli 1.0.80, plus 8/8 archived 2026-07-25 fetches), so whether the old branch is still reachable on any current lark-cli build was not confirmed.

`--format markdown` is **not** a valid value (lark-cli warns and falls back to json). Keep stdout and stderr separate — a harmless `[deprecated]` line goes to stderr, and piping `2>/dev/null` *and* `jq` together produced a false `Exit code 5` in practice. The body must reach disk via `jq`/`pandoc`, never retyped or summarized by the model — paraphrasing silently corrupts source text, the single most important fidelity rule. (pandoc only re-renders HTML structure to Markdown; it does not rewrite prose — the tag-stripping above is a structural loss, not a prose-fidelity one, which is why source.html must stay on disk and stay authoritative for rich-media references.)

**4. If it's a collection/hub, follow the reference graph (BFS).** The hub body contains `<mention-doc>` (real raw tag: `<cite doc-id="…">`), `<sheet>`, `<image>` (real raw tag: `<img src="…">`) tags, `<whiteboard token="…">` blocks, and cross-tenant / Minutes / Tencent-Meeting URLs. Extract every reference, dispatch by type, fetch, and **repeat on each newly fetched doc until no new references remain** (leaf nodes) — **except `whiteboard`, which is never fetched or recursed**: it's inline visual content, not a link to another document (see the dedicated instruction below). Use the bundled extractor so nothing is silently missed (a missed reference = a missing document, the #1 hub-scraping failure):

```bash
python3 scripts/feishu_extract_refs.py "<sanitized-title>.html"   # → JSON list of {type, ref, title, dispatch}
```

Run this once per fetched document — the root, then every newly-fetched child — using that document's own `<sanitized-title>.html` (see step 3's naming caveat). The extractor is a plain regex scan — it works on either the `.html` or `.md` for a given document, since it just checks whether the file's text contains the tags — but **`.html` is the one to trust when both exist**; fall back to `.md` only if no `.html` was ever saved for that document (the `.data.markdown` branch, see step 3). Recursion loop, dispatch table, and the cross-tenant/`my.feishu.cn` personal-space rules are in the reference.

**Whiteboard blocks are not a followable reference — export and read them in place.** A `whiteboard token="…"` tag is Feishu's native diagram/flowchart block, inlined in the current document — it is not a pointer to another document, so don't try to recurse/fetch it like `mention-doc`/`sheet`. It must be understood visually: a flowchart's meaning is not reliably recoverable from raw node coordinates/text-fragment lists alone. Export a preview image and actually look at it:

```bash
lark-cli whiteboard +export --whiteboard-token <token> --output-type preview --output <path>.jpg --overwrite
```

Then use the Read tool on the resulting `.jpg` to see the diagram's actual content. `--output-type raw` is also available (structured node JSON — useful as a cross-check/searchable index, but not a substitute for looking at the rendered image); `svg` and `source` output types also exist. The output path must have a real image extension matching what the command actually produces (it errors if you ask for `.png` when the true format is `.jpg` — match the extension to what the command reports, or omit the extension per its own `--help`). The preview is a **working cache by default**: record the whiteboard token, observed MIME/bytes/hash, and optional cache path in the artifact manifest; do not silently promote the JPEG to Git/LFS. If the durable archive needs an independent binary copy, route it explicitly to OSS. This matters because diagrams frequently carry decision-relevant content absent from the document's plain-text sections — e.g. a swimlane/process diagram can carry role-by-role steps and concrete numeric thresholds nowhere else in the doc. Treating a document as "fully extracted" without opening these blocks silently discards exactly the content most likely to carry its actual operating logic.

**5. Final residual-tag check (acceptance gate — run this on every fetched document, not just collections).** A single standalone document with no cross-doc references still needs this: an inline `whiteboard` or unresolved reference tag can appear with zero other documents involved (this is exactly what happened on a real single-doc extraction 2026-08-16 — no hub, no recursion, just 3 unread whiteboards). Every rich-media reference must have been resolved and rendered. Run this recursively over the whole working directory, not a single file — a collection has one `<sanitized-title>.html`/`.md` pair per document (step 3), and the pandoc-converted `.md` can report "clean" on its own while real tags were silently dropped (see step 3's callout), so the scan needs to reach every `.html` on disk:

```bash
grep -rlE '<(lark-table|lark-tr|sheet token=|mention-doc|cite doc-id=|whiteboard token=|view type=)' . \
  && echo "UNRESOLVED — keep recursing" || echo "clean"
```

`lark-tr` and `view type=` in that pattern are pre-existing, unverified-against-real-HTML terms — unlike the other five, they have no backing regex in `feishu_extract_refs.py` and no dispatch entry, so a hit here has no structured tooling support; treat it as "stop and inspect the raw tag by hand," not as something the extractor already understands.

⚠️ **On each document's saved `.html`, "empty" is not a literal stop condition — treat each hit as a worklist item, not a failure to loop on.** Each `<sanitized-title>.html` is an immutable raw capture of *that* document (nothing in this skill rewrites a document's own file in place once fetched — see step 3's per-document naming caveat), so a parent doc that genuinely references N other docs or M diagrams keeps showing N+M matches forever in its own file, even after every one of them has been correctly handled — chasing this grep to a literal zero across the whole directory will never terminate for a real hub doc. Instead, for every match, verify the corresponding artifact exists on disk: a `mention-doc`/`cite doc-id=`/`sheet` hit is resolved once the referenced child doc has actually been fetched and saved (step 3, applied to that child); a `whiteboard` hit is resolved once its preview `.jpg` was exported and Read (step 4) — **never** by fetching another document, it is not a followable reference. Stop only once every match maps to a verified on-disk artifact. (On the `.data.markdown` fallback branch, where the fetched body is the deliverable Markdown itself rather than an immutable raw capture, a literal empty result remains the simpler signal — but that branch was not confirmed reachable on any current lark-cli build, see step 3.)

## Path B — permission denied → owner-exported .docx

`lark-cli wiki spaces get_node` returning `code 131006 … node permission denied, user needs read permission` (or fetch returning it) is a **hard Feishu-side boundary**. lark-cli, anonymous curl, and the browser all fail it — this has been verified exhaustively; do not spend cycles trying to bypass it. The only correct move: ask the permission holder to export the doc as `.docx` and send it back out-of-band, then convert with fidelity (font-size→heading and `w:shd`→highlight restoration, then visual verification). Full procedure: **[references/docx-export-to-markdown.md](references/docx-export-to-markdown.md)**.

## Path C — Feishu Minutes (妙记) transcript

`lark-cli minutes` only returns metadata and can download audio/video — it **cannot** export the text transcript. The transcript comes from a native endpoint called through `lark-cli api`, and needs an extra scope granted via a device-flow login. Native AI transcription is far better than downloading the media and re-running ASR — never do the latter. Endpoint, scope name, the device-flow timeout trap, and per-minute (not per-tenant) permission behavior: **[references/feishu-minutes-transcript.md](references/feishu-minutes-transcript.md)**.

## Path D — browser DOM fallback (last resort)

Only when lark-cli genuinely cannot reach the content (no install possible, and the doc is not permission-walled). This is the old virtual-scroll / TOC-driven DOM capture workflow. It is slower, depends on a connected browser surface (the in-browser extension frequently fails to connect), and an anonymous debugging Chrome can only tell you whether a page is *publicly* reachable — it cannot read login-walled content. Workflow: **[references/browser-dom-fallback.md](references/browser-dom-fallback.md)**. Battle-tested DOM rules (virtual scroll, `data-block-id` ordering, table/bullet extraction, image streams): **[references/browser-failure-rules.md](references/browser-failure-rules.md)**.

## Hard rules

These are the rules whose violation silently ruins the output. Each has a reason — follow the reason, not just the letter.

- **Never let the document body pass through the model.** Extract with `jq`/`cat`/scripts straight to disk. The model paraphrasing source text is undetectable later and destroys fidelity. This is why Path A beats the browser path structurally.
- **`export LARK_CLI_NO_PROXY=1` for `*.feishu.cn`.** Otherwise credentials transit a local proxy and DNS is hijacked.
- **Transcripts come from the platform's native transcription, never re-ASR.** Downloading media and transcribing again loses speaker labels, timestamps, and accuracy.
- **A generated docx Markdown is not done until it has been *visually* verified** against the source (render to image, read it). Feishu-exported docx uses font-size+bold for headings rather than Word heading styles, so a "no errors, word count matches" check passes while the entire heading hierarchy is silently flat. Text-level checks cannot catch this.
- **Do not 死磕 (grind) on docx embedded-image download.** lark-cli (through 1.0.32) cannot download `<image>` tokens from a docx — exhaustively verified. Register the image tokens and note "needs document owner to right-click → save"; the text is the value, images are a tracked gap.
- **Rich-media tag verification must run on each document's own `.html`, never its `.md`, on the pandoc fallback path — and each document needs its own filename, not a shared literal `source.html`.** `pandoc -f html -t gfm` silently strips Feishu's custom embedded tags — verified on a real document: 3 raw `whiteboard token="…"` tags in `.data.document.content` left zero trace in the converted `.md` (2026-08-16). Checking only the `.md` for residual tags on this path always reports "clean," even when content was silently discarded; reusing one hardcoded filename across a hub's multiple fetches (step 3) would additionally let a later document silently overwrite an earlier one's raw capture before it was ever checked.
- **Never equate "downloaded" with "belongs in Git/LFS."** Raw video, Office files, PDFs, and images default to the Feishu original plus a stable locator; the local file is a cache. Git stores structured/searchable derivatives and provenance. OSS is an explicit durability route when source-only retention is insufficient. Run `python3 scripts/check_archive_storage.py <artifact-manifest.json>` before a package is committed.
- **HTTP 200 from anonymous curl ≠ accessible.** A Feishu login wall returns 200 with a body containing `accounts.feishu.cn` / `login` / `passport` / an empty `<title>`. Check the body, never infer "public" from the status code.
- **A file "not found" by a search agent is not authoritative.** Verify against authoritative sources before concluding (this is general Inference Discipline; relevant when locating where ingested content already lives).
- **U+FFFD final check on every produced file:** `LC_ALL=C grep -rl $'\xef\xbf\xbd' .` must be empty. A replacement character means an encoding step corrupted the text.

## Acceptance contract

Stop only when all that apply are true:

- Every fetched body reached disk via `jq`/script, not retyped by the model.
- **Every fetched document — a lone doc as much as a collection**: every hit from the residual rich-media-tag check (Path A step 5, run recursively over the whole working directory) maps to a handled artifact — every `mention-doc`/`cite doc-id=`/`sheet`/cross-tenant reference was **followed** to a fetched leaf file, and every `whiteboard` reference was **exported and read** (not followed — a whiteboard is inline visual content, never a link to recurse into). Raw binaries then map to a stable platform/OSS locator plus optional verified local cache; structured/searchable derivatives map to versioned files. This is not a collections-only check: a standalone document can contain an unresolved `whiteboard` with zero other documents involved. Each document's own `.html` legitimately keeps showing its tags forever (it's an immutable raw capture, never rewritten — as long as each document got its own filename per step 3) — don't chase the grep itself to a literal zero.
- The artifact manifest passes `python3 scripts/check_archive_storage.py <manifest>`: no raw binary is declared as Git storage, every external artifact has a stable locator, and every local cache is clearly marked as non-authoritative.
- `LC_ALL=C grep -rl $'\xef\xbf\xbd' .` is empty.
- docx path: rendered to an image and visually compared to the source; heading hierarchy and highlights match (see docx reference's checklist).
- Browser fallback only: TOC coverage + scale check (see browser-failure-rules.md).
- Each output file's frontmatter records `source` (the original URL/token) and, if any post-processing was applied, a `post_process` provenance line — the exact YAML shape and field list is **[references/lark-cli-api-extraction.md, Step 7](references/lark-cli-api-extraction.md)** (not shown in Path A's 5 numbered steps above, since it's a per-file finishing step rather than part of the fetch/recurse/check loop).
- Permission gaps (131006 docs not exported yet, undownloadable images) are explicitly listed for the user — a transparent gap beats a silent omission.

## Do NOT attempt

Verified dead-ends — retrying them only wastes the session. Full table with failure modes and root causes: **[references/permission-and-failure-boundaries.md](references/permission-and-failure-boundaries.md)**. The top ones:

- Bypassing `131006` permission-denied by any means (lark-cli / curl / anonymous browser) — it is a server-side boundary.
- Downloading docx embedded images via `docs +media-download`, `api …/drive/v1/medias/<t>/download` (with or without `extra`), or `schema drive.medias.download` — none work; lark-cli even mis-reports the real HTTP 400 as "empty JSON".
- `WebFetch` against `open.feishu.cn/document/server-docs/...` for API specs — backend is flaky; use `open.feishu.cn/llms-docs/zh-CN/llms-<module>.txt` instead (LLM-friendly, stable).
- AppleScript/JXA `executeJavaScript`, Chrome CDP on port 9222 — disabled/empty in this environment (browser path only).
- Using `minimax-docx` to convert docx→md — it is a docx *authoring* tool; use the doc-to-markdown skill instead.

## Bundled resources

- `scripts/feishu_extract_refs.py` — deterministic reference-token extractor; the recursion engine's core. Run it once per fetched document, on that document's own `<sanitized-title>.html` (prefer over `.md` — step 3), to enumerate `<mention-doc>`/`<sheet>`/`<image>`/`<whiteboard>`/cross-tenant/Minutes/Tencent-Meeting references as JSON.
- `scripts/restore_docx_headings.py` — for Path B: reads true font sizes via python-docx, maps them to heading levels, restores `w:shd` highlights to Obsidian `==…==`, without retyping body text.
- `scripts/feishu_dom_capture.js` — Path D: injectable end-to-end browser DOM capture.
- `scripts/download_feishu_images.py` — Path D: SSR image extraction when browser automation is unavailable.
- `scripts/build_feishu_markdown.py` — Path D: render a capture manifest into Markdown.
- `scripts/check_heading_coverage.py` — coverage verification (both paths).
- `scripts/check_archive_storage.py` — fail-closed validator for the source/Git/OSS storage split; blocks raw binaries declared as Git artifacts.
- `references/lark-cli-api-extraction.md` — Path A full reference (commands, recursion, sheets, cross-tenant).
- `references/feishu-minutes-transcript.md` — Path C native transcript API + scope auth.
- `references/permission-and-failure-boundaries.md` — error codes + the full Do-NOT-attempt table.
- `references/docx-export-to-markdown.md` — Path B faithful conversion procedure.
- `references/browser-dom-fallback.md` + `references/browser-failure-rules.md` — Path D.
- `references/capture-manifest.md` — manifest shape for `build_feishu_markdown.py`.
- `references/archive-storage-contract.md` — durable storage contract for structured Git artifacts, platform originals, optional caches, and OSS copies.

## Next step

After extraction completes, the clean Markdown typically feeds the user's own knowledge-base ingestion (filing, indexing, dedup) — which is deliberately out of this skill's scope. If the source went through Path B (a docx), the doc-to-markdown skill is already part of that flow. Offer the handoff; do not auto-organize:

```
Extraction complete: [N] sources → faithful Markdown ([M] permission/image gaps listed).

Options:
A) Hand off to your PKM/organizing workflow — file & index these (Recommended if part of a vault)
B) Run /daymade-docs:docs-cleaner — consolidate redundant content across the extracted files
C) Stop here — the faithful Markdown is the deliverable
```
