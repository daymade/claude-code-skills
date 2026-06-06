---
name: feishu-doc-scraper
description: Extract Feishu (Lark) Docs, Wiki pages/collections, spreadsheets, and Minutes (妙记) transcripts into faithful local Markdown via the lark-cli API (no LLM rewriting of the body; browser-DOM fallback when lark-cli can't reach the content). Use whenever the source is a Feishu/Lark URL and fidelity matters — 导出飞书文档/合集/妙记转写, 把飞书 wiki/知识库转 markdown, archiving a Feishu collection, exporting a 妙记 transcript, or saving a Feishu page — even if the user only says clipping, archiving, converting, or "save this". Also covers the owner-exported .docx → faithful Markdown path.
compatibility: Primary path needs the `lark-cli` binary (npm `@larksuite/cli`, verified 1.0.32, 2026-05) authenticated to the target tenant. Fallback path needs a browser automation surface with an authenticated session (Chrome DevTools MCP / Browser Use / Computer Use). docx path needs `python-docx` and a docx→md converter (the bundled doc-to-markdown skill or pandoc).
argument-hint: [feishu-url-or-output-path]
---

# Feishu Doc Scraper

Extract a Feishu/Lark source into faithful local Markdown. **Prefer the lark-cli API** — it extracts the body programmatically (no model paraphrasing), follows a collection's reference graph, and reads permission boundaries from error codes instead of guessing. Treat the rendered browser page as a *fallback*, not the source of truth: in real collection-scraping work the API path consistently does the whole job while the browser path is never needed.

## Scope (read this first)

This skill's contract is **faithful per-source Markdown + a record of what was extracted**. It does *not* decide how the resulting files are named, indexed, deduplicated against existing notes, or organized into a knowledge base — that belongs to the host PKM / the user's own conventions. Stopping at faithful extraction keeps this skill orthogonal and reusable. When the user wants the output filed into a vault, extract first, then hand the clean Markdown to their organizing workflow.

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

**3. Fetch the body as Markdown — programmatically, never via the model.**

```bash
lark-cli docs +fetch --doc <obj_token> --format json > /tmp/fetch.json 2> /tmp/fetch.err
# body is .data.markdown — extract with jq, do NOT retype or summarize it
jq -r '.data.markdown' /tmp/fetch.json > source.md
```

Keep stdout and stderr separate. A harmless `[deprecated] docs +fetch with v1 API is deprecated` goes to stderr; piping `2>/dev/null` *and* `jq` together produced a false `Exit code 5` in practice — redirect to files and inspect, don't blind-pipe. The body must reach disk without passing through the model (paraphrasing silently corrupts source text — this is the single most important fidelity rule).

**4. If it's a collection/hub, follow the reference graph (BFS).** The hub body contains `<mention-doc>`, `<sheet>`, `<image>` tags and cross-tenant / Minutes / Tencent-Meeting URLs. Extract every reference, dispatch by type, fetch, and **repeat on each newly fetched doc until no new references remain** (leaf nodes). Use the bundled extractor so nothing is silently missed (a missed reference = a missing document, the #1 hub-scraping failure):

```bash
python3 scripts/feishu_extract_refs.py source.md   # → JSON list of {type, token, title}
```

Recursion loop, dispatch table, and the cross-tenant/`my.feishu.cn` personal-space rules are in the reference.

**5. Final residual-tag check (acceptance gate for collections).** Every rich-media reference must have been resolved and rendered:

```bash
grep -rlE '<(lark-table|lark-tr|sheet token=|mention-doc|view type=)' . && echo "UNRESOLVED — keep recursing" || echo "clean"
```

Must be empty before you stop.

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
- **HTTP 200 from anonymous curl ≠ accessible.** A Feishu login wall returns 200 with a body containing `accounts.feishu.cn` / `login` / `passport` / an empty `<title>`. Check the body, never infer "public" from the status code.
- **A file "not found" by a search agent is not authoritative.** Verify against authoritative sources before concluding (this is general Inference Discipline; relevant when locating where ingested content already lives).
- **U+FFFD final check on every produced file:** `LC_ALL=C grep -rl $'\xef\xbf\xbd' .` must be empty. A replacement character means an encoding step corrupted the text.

## Acceptance contract

Stop only when all that apply are true:

- Every fetched body reached disk via `jq`/script, not retyped by the model.
- Collections: the residual rich-media-tag grep (Path A step 5) is empty — every `mention-doc`/`sheet`/cross-tenant reference was followed to a leaf.
- `LC_ALL=C grep -rl $'\xef\xbf\xbd' .` is empty.
- docx path: rendered to an image and visually compared to the source; heading hierarchy and highlights match (see docx reference's checklist).
- Browser fallback only: TOC coverage + scale check (see browser-failure-rules.md).
- Each output file's frontmatter records `source` (the original URL/token) and, if any post-processing was applied, a `post_process` provenance line.
- Permission gaps (131006 docs not exported yet, undownloadable images) are explicitly listed for the user — a transparent gap beats a silent omission.

## Do NOT attempt

Verified dead-ends — retrying them only wastes the session. Full table with failure modes and root causes: **[references/permission-and-failure-boundaries.md](references/permission-and-failure-boundaries.md)**. The top ones:

- Bypassing `131006` permission-denied by any means (lark-cli / curl / anonymous browser) — it is a server-side boundary.
- Downloading docx embedded images via `docs +media-download`, `api …/drive/v1/medias/<t>/download` (with or without `extra`), or `schema drive.medias.download` — none work; lark-cli even mis-reports the real HTTP 400 as "empty JSON".
- `WebFetch` against `open.feishu.cn/document/server-docs/...` for API specs — backend is flaky; use `open.feishu.cn/llms-docs/zh-CN/llms-<module>.txt` instead (LLM-friendly, stable).
- AppleScript/JXA `executeJavaScript`, Chrome CDP on port 9222 — disabled/empty in this environment (browser path only).
- Using `minimax-docx` to convert docx→md — it is a docx *authoring* tool; use the doc-to-markdown skill instead.

## Bundled resources

- `scripts/feishu_extract_refs.py` — deterministic reference-token extractor; the recursion engine's core. Run it on every fetched body to enumerate `<mention-doc>`/`<sheet>`/`<image>`/cross-tenant/Minutes/Tencent-Meeting references as JSON.
- `scripts/restore_docx_headings.py` — for Path B: reads true font sizes via python-docx, maps them to heading levels, restores `w:shd` highlights to Obsidian `==…==`, without retyping body text.
- `scripts/feishu_dom_capture.js` — Path D: injectable end-to-end browser DOM capture.
- `scripts/download_feishu_images.py` — Path D: SSR image extraction when browser automation is unavailable.
- `scripts/build_feishu_markdown.py` — Path D: render a capture manifest into Markdown.
- `scripts/check_heading_coverage.py` — coverage verification (both paths).
- `references/lark-cli-api-extraction.md` — Path A full reference (commands, recursion, sheets, cross-tenant).
- `references/feishu-minutes-transcript.md` — Path C native transcript API + scope auth.
- `references/permission-and-failure-boundaries.md` — error codes + the full Do-NOT-attempt table.
- `references/docx-export-to-markdown.md` — Path B faithful conversion procedure.
- `references/browser-dom-fallback.md` + `references/browser-failure-rules.md` — Path D.
- `references/capture-manifest.md` — manifest shape for `build_feishu_markdown.py`.

## Next step

After extraction completes, the clean Markdown typically feeds the user's own knowledge-base ingestion (filing, indexing, dedup) — which is deliberately out of this skill's scope. If the source went through Path B (a docx), the doc-to-markdown skill is already part of that flow. Offer the handoff; do not auto-organize:

```
Extraction complete: [N] sources → faithful Markdown ([M] permission/image gaps listed).

Options:
A) Hand off to your PKM/organizing workflow — file & index these (Recommended if part of a vault)
B) Run /daymade-docs:docs-cleaner — consolidate redundant content across the extracted files
C) Stop here — the faithful Markdown is the deliverable
```
