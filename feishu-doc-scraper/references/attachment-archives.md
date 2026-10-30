# Archive source-card attachments

Use this branch when the requested result includes original files from a Feishu
document. Keep the body capture and comments workflow; original-file archiving
does not authorize changing source content, permissions or cloud storage.

## Prepare and download

1. Read the installed `lark-doc` fetch and media-download guides through the Lark
   router, or `lark-cli skills read` when the router is not installed. Use an
   already authorized user identity/profile; let its actual read decide access.
2. Save the complete successful `docs +fetch --detail full --format json` response
   to a distinct file per document. Inspect `data.document.content` and retain
   its sidecars. The helper accepts this content branch, not a Markdown-only
   legacy response; keep the existing extraction route for that legacy branch.
3. Enumerate references with `feishu_extract_refs.py` on the raw body. A current
   attachment card is `<source token="…" name="…" size="…" mime="…"/>` inside a
   figure. Attribute order and quote style are not identity. Handle referenced
   documents, sheets, images, whiteboards and Minutes through their existing
   routes; the attachment helper does not recursively fetch them.
4. Run the bundled helper against a new output directory:

```bash
python3 <skill-dir>/scripts/archive_attachments.py <capture.json> \
  --source 'https://example.feishu.cn/wiki/<node-token>' \
  --output <new-archive-directory>
```

Pass `--profile` only for a selected, already authorized profile. `--workers`
defaults to 4 and accepts 1–8; this is a bounded transfer default, not a measured
optimum. `--timeout` bounds each CLI call. The helper sets the CLI's existing
no-proxy/notifier flags, uses `--as user`, and never logs in or changes grants.

The output contains the unchanged `capture.json`, original filenames under
`attachments/`, `attachment-state.json`, and `manifest.json`. The manifest marks
originals as Feishu-authoritative local copies; change durable storage only
through the destination's authorized storage owner. No cookie or signed download
URL is saved by the helper. It does not change content already in the capture.

Successful downloads match captured sizes and receive SHA-256 values. ZIP
containers receive CRC checks; XLSX/DOCX/PPTX also require their core XML and
content-types document. XLSX worksheet metadata is retained. For preview versus
original evidence, follow the [media failure branch](original-media-and-reader.md#select-the-failure-branch).
These checks do not evaluate formulas, macros, document layout or the meaning of
the templates.
Unrecognized binary formats retain `application/octet-stream`; do not invent a
detector result from the filename. Current XLSX source-card downloads were
verified with lark-cli 1.0.96; that evidence does not settle image/video access.

## Resume and permission gaps

Exit 0 means `attachments_complete`, not whole-document or reader completion.
Exit 3 means partial downloads; read each failed item and the remaining resource
worklist. Exit 2 means invalid input/local state. Missing token/name/size,
conflicting metadata, unsafe paths and filename collisions stop preparation.
No destination file is overwritten.

After addressing a transient failure, reuse the same arguments with `--resume`.
The capture bytes, source URL and explicit profile must match the saved binding.
Keep downstream manifest entries, OSS locators, replicas and reader-note records
when resuming. The helper updates its failure/reference worklist and state snapshots,
and removes legacy requested/verified attachment counts from the manifest;
it does not reclassify existing originals' durable storage.
Previously verified originals are reused only after size, structure and hash
readback. Changed or unrecorded existing files are preserved and reported, not
silently replaced. A changed capture needs a new output directory. An interrupted
writer may leave a lock or an unrecorded original; verify the writer and preserve
the files before recovery. The helper does not clear another writer's lock.

A permission refusal stops that operation; `--resume` does not grant retry or
alternate-identity authority. Diagnose through the current CLI guide. Use the
existing [original-preview branch](original-media-and-reader.md#select-the-failure-branch)
only when its operation-specific conditions hold. Do not infer that a body-read
permission or an XLSX success grants access to other media.

## Acceptance

The executing agent reconciles the raw document's requested attachment identities
with local files, verified sizes/hashes and explicit failures. Duplicate tokens
count once; missing results remain missing. Continue the reference graph and
comments capture independently. Preserve source headings and original names when
rendering the body with `render_api_capture.py`; its manifest root must contain
the downloaded originals and any discussion companion. Register newly rendered
Markdown and companions in the same manifest before its final checks.

Choose and report the requested outcome before declaring completion:

- **Original-file archive:** all requested bodies/files are saved and reconciled,
  local links are checked, and any authorized independent-retention requirement
  is verified through the destination's storage SOP. Source-only local cache does
  not prove an independent backup. Keep reader status `not_checked` if unobserved.
- **Reading delivery:** when promising the note's actual reader experience,
  execute [reader completion](original-media-and-reader.md#delivery-completion-gate)
  in that reader. A parsed link or intact file does not prove it opens/displays.
  Preserve user-excluded checks and pending observations; never fabricate evidence.

Do not silently switch outcome because a required check is unavailable. Load
browser/desktop procedures only for an actual fallback or reading-delivery need;
resource discovery should first establish which of those operations is required.
