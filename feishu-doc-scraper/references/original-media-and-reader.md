---
name: original-media-and-reader
description: >-
  Archive authorized Feishu original previews and render relative local media for
  Obsidian. Read when text capture succeeds but media export fails or embeds break.
---

# Original media and Markdown reader handoff

## Select the failure branch

The executing agent records the selected account/profile and operation before
classifying an error. A document read, attachment export and original preview
are separate operations. Preserve the error JSON/stderr outside the public bundle.

| Observation | Next action | Stop condition |
|---|---|---|
| Selected identity cannot read the body (`131006`) | Use the existing permission/owner-export route | Do not replay credentials or guess an alternate token |
| Body is readable; media export is denied and the CLI recommends preview | Read the installed CLI's media-preview guide; attempt that authorized operation once | Preview permission refusal is a boundary, not a transport retry |
| Preview returns `INTERNAL_ERROR` / unexpected EOF | Inspect the same source in an already authorized browser session | No identical retry loop; do not label EOF as an ACL refusal |
| Browser actually plays/displays the requested original | Capture its observed original request URL and narrowly scoped headers through the browser owner | No invented URL, token enumeration, login-wall bypass or cross-account credential borrowing |
| No authorized original request is available | Retain text and source token; report the media gap | Do not claim an original was saved |

Read command availability from the installed CLI. An older command failure does
not establish the permissions or behavior of a current original-preview operation.

## Download one original per destination

The agent prepares a private mode-0600 request JSON outside the archive/Git tree.
Use the URL and headers actually observed for the selected original. Supply
`identity` as its stable token plus captured source revision, `size` from original
metadata, and `width`/`height` together for video. `sha256` is optional when a
previous independently verified original hash exists. Never store cookies or
temporary signed URLs in the durable manifest or print the request file.

```bash
uv run --script <skill-dir>/scripts/download_original_preview.py \
  <private-request.json> <archive>/media/<original-name.mp4>
```

Expected: `status=complete`, exact `bytes`, `sha256`, `proxy=false`, and matching
video dimensions/duration. An existing verified original returns
`already_verified`; a competing writer is refused. A failed transfer retains
`.part` and its range journal. Resume with the same source identity and output;
corrupted local chunks are downloaded again. A changed identity/layout is refused.
If a signed request expires, recapture the same authorized original request;
do not clear state or launch a second writer. Missing ffprobe for video is a
dependency gap. Remove the task-owned private request file after use.

The helper is POSIX-only, uses an explicit empty proxy handler and rejects
cross-host redirects carrying browser credentials. It accepts only exact HTTP
206 ranges with matching `Content-Range` and byte counts, following
[HTTP range semantics](https://www.rfc-editor.org/rfc/rfc9110.html#name-range).
It never accelerates, transcodes, uploads or chooses durable storage. Record the
stable source locator and verification in the existing archive manifest. Its
`.verified.json` sidecar is local verification state, not source authority.

## Render the captured body

Keep the original API JSON/HTML unchanged. For an Obsidian deliverable, place the
verified originals under that archive's `media/`, then run the actual pandoc path:

```bash
uv run --script <skill-dir>/scripts/render_api_capture.py \
  <document-fetch.json> <archive-manifest.json> <archive>/<new-pilot-name.md> \
  --source <original-feishu-url>
```

The renderer defines its archive root as the manifest's parent directory. Put the
manifest at that root; its local artifact paths are relative to the same directory.

Expected: `status=converted_reader_pending`, nonzero `media_references` when the
source contains media, and `actual_reader=not_verified`. The output note must
remain under the manifest's archive directory; an outside output is refused. The helper localizes img/source tokens from the
manifest, preserves image alt text, converts attachment figures to native
Markdown embeds plus filename links, and refuses missing originals/overwrites.
It does not resolve whiteboards or replace the reference-graph worklist. Continue
the existing raw-HTML residual check within the user's selected capture scope.

Before expanding a batch, the agent opens this pilot in the recipient's real
Obsidian reading canvas: inspect images and captions, briefly play each affected
video, follow a filename link, then reopen the note. Coordinate window ownership
before native input. User-performed acceptance is valid; record it as such.
When the reader is unavailable or concurrently occupied, keep that observation
pending instead of substituting a standalone image tab, parser or qmd result.
Use frontend-visual-qa's Markdown reader handoff for the actual-reader protocol.
If the user excludes playback or another reader check, preserve that exclusion:
do not operate the reader or create evidence for the excluded action. Report the
authorized structural result separately; a missing reader receipt remains pending.

Native embedding follows [Obsidian's embed contract](https://obsidian.md/help/embeds).
Keep local asset references relative to the Markdown directory so moving the
delivered folder as a unit preserves them. A hidden global cache is not the
reader-facing attachment directory. Keep source/Git/OSS authority and binary
ignore/LFS policy with the archive storage owner; do not change it merely to
make the note display. Download, conversion, actual-reader and search checks
remain separate observations.

## Delivery completion gate

The executing agent runs `check_reader_delivery.py` before declaring a local
reader-facing archive complete. Conversion exit 0 establishes conversion only.
Use the actual user-selected delivery root and reader; do not choose a hidden
cache as that root to make a bad note pass. The root is the folder the recipient
can move as a unit. Keep the storage manifest current before this check.

```bash
uv run --script <skill-dir>/scripts/check_reader_delivery.py inspect \
  --root <archive> --manifest <archive>/manifest.json \
  --note '<entry-note.md>' --reader Obsidian --report <private-inspect.json>
```

Repeat `--note` for every delivered entry note. Expected: `status=reader_pending`,
`actual_reader=not_verified`, and the examined note/file counts. The helper parses
GFM/reference links and Obsidian wikilinks with actual pandoc, follows linked local
Markdown, and checks every referenced local file against the manifest's bytes
and SHA-256. Absolute/file URLs, escaping paths, symlinks, missing targets, external
media embeds and raw-HTML media are refused. Remote source hyperlinks, anchors,
code examples and text-only notes remain valid. This byte/closure check is not a
visual or playback verdict. A video thumbnail or play button alone is not playback:
observe time advancing and decoded frames/audio; if the actual reader buffers or
reports failure, leave playback unverified and record the failure.

Perform the real-reader protocol above on that snapshot. Preserve native tool
observations/captures or the user's actual acceptance message outside the public
Skill. Reader evidence JSON supplies `kind` (`native-reader-observation` or
`user-acceptance`), exact `reader`, `artifact_fingerprint` from inspect,
`source_reference` to the original observation/message, and timezone-aware
`observed_at` after inspection. User acceptance also needs the exact `quote` and
`entry_notes` matching inspect; do not retroactively bind an old approval to new
bytes. Native evidence needs one `observations` row per inspected note, including
linked local Markdown: `note`,
`images_displayed`, `videos_played`, `links_opened` lists covering the inspected
paths and `reopened=true`, plus `evidence_files` with absolute `path` and `sha256`
for retained native captures/tool records. Missing checks are unfinished work.

```bash
uv run --script <skill-dir>/scripts/check_reader_delivery.py record-reader \
  --report <private-inspect.json> --evidence <private-reader-evidence.json> \
  --receipt <private-reader-receipt.json>
uv run --script <skill-dir>/scripts/check_reader_delivery.py finalize \
  --root <archive> --manifest <archive>/manifest.json \
  --note '<entry-note.md>' --reader Obsidian \
  --reader-receipt <private-reader-receipt.json>
```

Repeat the same entry-note set at finalize. Missing receipt returns exit 3 and
`reader_pending`; invalid paths, changed files/manifest/evidence, incomplete
observation coverage or a different reader return exit 1. Exit 0 with
`ready_with_reader_evidence` means current bytes and retained observation
coverage agree. Re-rendering or updating a note, asset, source manifest or entry
set invalidates that binding. Do not overwrite old inspect/evidence files;
retain the earlier result and create a new snapshot for a new real observation.

The gate cannot authenticate who wrote an observation or decide that screenshots
actually show readable images or playing video. It prints
`provenance_authenticated=false` even on a healthy finish. The agent must obtain
and inspect the named original evidence; invented JSON or its own unsupported
"checked" statement is not reader acceptance. This is a workflow-local completion
command, not a global Stop hook or a claim of universal behavior enforcement.

## Declare a selected personal collection

When the user has selected the destination and requested personal favorites,
the source producer can publish the captured body catalog there:

```bash
uv run --script <skill-dir>/scripts/build_manual_catalog.py <source-archive-root> \
  --collection fav-feishu --display-name '<selected-source-name>' --share-scope private
```

The catalog source root may contain several archive folders. Keep SOPs and other
process notes outside that root's Markdown mask; the producer rejects Markdown
without captured source identity rather than treating it as course content.

Expected: `status=declared`, the actual item count and `share_scope=private`.
The producer creates `_data/source.json` and `_data/items.jsonl` from explicit
Feishu source/qmd identities and body hashes. Markdown bodies remain unchanged;
no classification or team promotion occurs. Do not label a manually selected
course as a subscription. The lock file is transient local state; ignore it
according to the destination's existing policy. Rebuild the catalog after body
changes. Hand its parent directory to favorites-search's `--manual-favorites`
registration entry; that consumer validates rather than reconstructs the catalog.
