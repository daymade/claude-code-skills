# External video discovery and handoff

Load this branch when a captured document contains external website or video links. The
executing agent owns discovery and reconciliation; platform and storage owners
perform authorized metadata reads, downloads and retention. This Skill does not
implement another platform downloader.

## Discover from every captured body

Run the extractor on each document's raw HTML (or original Markdown when the API
returned Markdown), including child documents:

```bash
python3 <skill-dir>/scripts/feishu_extract_refs.py <captured-body.html> --type external
```

The existing JSON array and `type/ref/title/dispatch` fields remain supported.
External records add `source_url` (first observed URL), `source_urls` (all observed
variants), `platform`, `resource_kind` and `status: discovered`. `ref` is the
canonical locator. Named tracking fields are removed from Bilibili/YouTube query
strings; all other parameters and fragments remain. Bilibili `p`/`cid`, YouTube
`v`/`list`/`index`, and timestamps are not discarded. A playlist, series, unresolved
short link or direct media URL stays distinguishable. Direct-media queries remain
unchanged because they may carry access signatures; keep captures and worklists
within the source's authorized visibility and do not publish signed URLs.

The scan includes quoted links and bare URLs in the raw body, including plain-text
URLs inside tables. `external-web` records inventory opaque website destinations;
they establish neither video availability nor authority to recurse or download.
Keep exact query parameters and fragments. A known video or other handled
reference is not duplicated as a generic webpage. Feishu-native links stay with
their existing handlers.

This is a candidate inventory. `needs_url_review` flags CJK text inside a URL:
it may be a real Unicode path/query or prose touching a bare link. Resolve the
boundary against the source before fetching; do not silently truncate a valid
Unicode URL or count an unverified candidate as an available video.

Video recognition includes Bilibili video/episode/series/playlist and b23 short links,
YouTube watch/shorts/live/embed/playlist and youtu.be links, plus direct
MP4/M4V/WebM/MOV/M3U8/MPD URLs. It does not infer video content from arbitrary
webpages, channel pages, JavaScript players or opaque redirectors. Inspect such
source cards within the selected scope and classify their existing webpage locator; zero
recognized links does not establish that every possible external player was read.

Merge discoveries into the destination's resource worklist by `(type, ref)`;
retain every source-document locator and observed URL variant. Do not overwrite
previous acquisition results with a new extractor run's `discovered` default.
Keep unresolved short links distinct until an authorized platform read establishes
their target. Preserve the original link when recording that resolution.

## Select the authorized job and owner

### Stabilize the batch before transferring it

Before bulk downloads, uploads or child-page creation, reconcile the complete
in-scope URL inventory, including plain-text URLs. Separate native Feishu assets,
selected external media and ordinary websites retained as links. State the
selected roots/depth/parts, local and cloud destinations, and any user-set limits.
Use source metadata to report item counts and byte volume; when unavailable,
label a bounded sample estimate and its uncertainty, or retain `unknown`.
Do not start downloading the entire collection to estimate its size.

Check local capacity and the selected cloud destination's known limits before
expanding the batch. A newly discovered collection or a materially different
volume changes the execution decision: reconcile it against the user's intended
copy and limits, then proceed within existing authorization. Ask only when a
scope/cost choice remains unresolved; an explicit full-collection request remains
supported. Report progress by selected branch and transferred bytes so the user
can see what occupies storage. Changing disks or adding cloud pages is not a
substitute for resolving an uncertain capture boundary.

### Hand off only the selected resources

Before acquisition, carry the requested result (link, text, audio or video), source
document, original and canonical URL, platform identity/part, selected episode or
playlist range, destination and current state into the handoff. A link to one part
does not authorize the whole series. A playlist context on a video does not select
the playlist. Expand a series or playlist only when the user's request covers it;
otherwise retain that extra range as `out_of_scope`. When full acquisition is
authorized, let the platform owner enumerate the actual range and reconcile every
requested item rather than treating the first episode as the whole course.

When the user explicitly selects a NAS downloader or excludes local downloads,
the executing agent routes media acquisition directly to the installed NAS owner
across platforms, including YouTube; do not require a local attempt first. Reuse
the selected NAS destination. If no compatible NAS owner is available, retain
`link_only` with that gap instead of substituting a local download.

Otherwise select the platform owner below. Text-only requests retain their
text-first route; a selected NAS destination does not create a media-file request.

- YouTube: use the installed `youtube-downloader` owner, choosing its ordinary
  file or text-first route from the user's requested result.
- Bilibili: use `bilibili-source` when installed for platform metadata/access
  evidence. Send media acquisition to an installed, user-selected media/storage
  owner; an authorized NAS route may use `lazycat-use` when available. Metadata
  retrieval alone is not a video download.
- Direct media and other manually identified players: use the installed owner
  that supports the actual source and selected destination. Do not guess download
  commands or pass Feishu credentials to another platform.

Read the chosen owner's current entry before executing it. Probe its availability,
selected account/access and destination through its supported interface. Continue
with valid prerequisites; execute already authorized preparation when missing. If
no compatible owner exists, preserve the locator as `link_only` and identify the
missing owner. If a person must complete login or grant access, retain the binding
and resume from that unmet step after re-probing. Do not re-download verified
files or reopen a completed destination choice after interruption. These are
agent reconciliation duties; the extractor itself performs no readiness probes,
access tests, downloads or state updates.

## Resource states and completion

Keep acquisition, cloud upload and cleanup decisions separate in the existing
worklist. On correction, update the selected policy, stop owned controllers and
workers for the excluded branch, and read back their terminal state. Preserve
completed files and cloud copies according to the latest retention instruction;
stopping a job does not authorize deletion. Before resuming, use that current
policy rather than the original batch arguments. Continue authorized branches
without restarting canceled ones.

Acceptance example: after “stop external downloads/uploads, retain local files”
and “keep existing cloud copies”, a later “continue” permits the remaining Feishu
copy/audit. It produces no new website payloads or cloud case pages and deletes
no retained copies. A later explicit request can select external acquisition again.

Use these explicit states in the destination's worklist (existing equivalent
schema names are acceptable when their meanings match):

| State | Required observation |
|---|---|
| `discovered` / 已发现 | Locator extracted; access and acquisition have not been decided. |
| `link_only` / 仅链接 | Locator retained without media; include why (requested scope, missing owner or unmet prerequisite). |
| `saved` / 已保存 | Requested media and part/range match verified files; retain bytes/hash, actual media properties and durable locator under the storage contract. |
| `inaccessible` / 不可访问 | Record the actual failed operation and platform diagnostic; an untested link or missing tool is not an access denial. |
| `out_of_scope` / 范围外 | Record the user-selected boundary that excludes this resource or extra range. |

Record body, transcript/subtitles and media results separately. A saved document,
native transcript, thumbnail or metadata entry never upgrades media to `saved`.
For an authorized original-media request, reconcile every discovered in-scope
identity/part with a verified saved file or an explicit remaining gap. Apply the
existing [storage contract](archive-storage-contract.md#nas-retained-external-media)
for durable retention; neither platform-owner success nor a local cache alone
proves NAS/OSS retention. Report incomplete media acquisition even when the Feishu
body and reference graph have been fully captured.

For link-preserving copies, compare destinations, identity parameters and source
positions. Adjacent same-destination anchors may merge without losing content;
raw anchor-count inequality alone is not a missing-link finding. Destination-set
equality alone also cannot prove that every occurrence remains in its intended place.
