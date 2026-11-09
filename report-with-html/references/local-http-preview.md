# Local HTTP preview

Keep the HTML file as the durable artifact; preview its selected frozen snapshot over HTTP.

## Existing HTML restoration

Use this route when the user wants to reopen or host existing pages and preserve
their content. Bind the requested edition and recover its entry and dependencies;
the history reader owns recovery from conversations. Distinguish original files,
regenerated assets, screenshot-only evidence and missing content. Old progress or
decisions remain historical, and changing origin does not transfer browser-local
annotations, login state or stored judgments.

Keep originals intact. Correct local URLs only in a hosted copy, using real
relative directory names and an explicit asset list. Preserve the page's text,
layout and controls. Mark missing dependencies and access gaps without inventing
replacement content; a partial page is not a complete recovery. Use the manifest
and delivery checks below. This is transport maintenance: do not start new-report
design, masked renders or reader-review rounds unless the user also requests
content, layout or interaction changes.

Use a permitted browser-control channel that is currently available. A connector
transport failure does not establish that the browser cannot be controlled; an
already authorized alternative may continue the same task. An explicit host
policy refusal retains its actual boundary and is not bypassed by another route.
Once the page is readable and one primary action succeeds (including actual video
playback/seek when relevant), return to the calling task. Capture an image only
when needed to resolve a visual question; screenshots are not the default result.

## Prepare the exact snapshot

Use Python 3.10+ on POSIX with `O_NOFOLLOW` and `dir_fd`. The helper fails explicitly
when those primitives are unavailable; do not substitute a whole-directory server.
Keep reports, manifests, readiness files and logs outside the update-owned Skill
bundle. Select only reviewed report files and necessary assets, never a repository
root, credentials, private evidence directories, or a recursively discovered set.
Resolve a platform temporary-directory alias before choosing `--root`; the helper
rejects symlink components rather than following them.

Read `scripts/preview_report.py --help` for the executable interface, then run:

```bash
python3 <skill-dir>/scripts/preview_report.py manifest \
  --root <absolute-report-directory> --entry page.html \
  --file page.html --file assets/figure.png \
  --output <absolute-runtime-directory>/preview-manifest.json
python3 <skill-dir>/scripts/preview_report.py serve \
  --manifest <absolute-runtime-directory>/preview-manifest.json \
  --ready-file <absolute-runtime-directory>/preview-ready.json
```

Omit the asset argument for a self-contained HTML. Add each required file with a
separate `--file`; no globs or directory arguments. The schema binds an absolute
root, relative entry, and exact relative file paths plus SHA256. Repeated JSON
field names, unrecognized fields, missing/null/empty values, absent entry, non-HTML entry, duplicate
files, traversal, symlinks, nonregular files, or stale hashes fail before serving.
The existing schema-1 manifest and commands also accept media libraries. The
[preview helper](../scripts/preview_report.py) defines memory-selection, metadata
and chunk-size bounds. Small selections use memory; larger selections use a
private disk snapshot and bounded reads/copies. Source edits or removal after
startup cannot change the served bytes; payload size is limited by available storage.

Disk mode makes a complete temporary copy of the explicitly listed payload. Before
copying, the helper checks free space on the selected destination volume against
file allocation and snapshot metadata estimates. A competing writer can still
exhaust that space; startup fails and removes only this attempt's private snapshot.
Choose a volume with enough room rather than removing required media or loading
it all into memory:

```bash
python3 <skill-dir>/scripts/preview_report.py serve \
  --manifest <absolute-runtime-directory>/preview-manifest.json \
  --snapshot-parent <existing-canonical-directory-on-selected-volume> \
  --ready-file <absolute-runtime-directory>/preview-ready.json
```

Without `--snapshot-parent`, disk mode uses the resolved system temporary directory.
The supplied parent must already exist and have no symlink components. Only a new
private child directory is owned by this preview. Its copies are removed on normal
exit, Ctrl-C and handled startup failures; forced process termination can leave that
child behind. Do not delete the parent or another process's snapshots.

The foreground server uses an OS-selected port unless `--port` is supplied.
An occupied explicit port fails; never stop its owner. A readiness file must be
new: an existing one fails instead of overwriting another preview's state. Hashes
are checked and file bytes frozen before binding. Later source changes cannot
silently change the served snapshot; regenerate into new manifest/readiness files
after report edits and any review applicable to those edits. The readiness record
reports `storage` and `snapshot_bytes` as well as the selected entry and manifest hash.

GET supports one byte range (`bytes=start-end`, `bytes=start-` or `bytes=-count`)
with 206 and `Content-Range`, enabling video playback and seeking. Malformed,
multiple or unsatisfiable ranges return 416. HEAD returns full-file metadata and
no body, ignoring Range. Neither mode rereads live source paths during requests;
a missing or changed private disk copy returns 409 rather than live source bytes.

## Verify in the actual delivery browser

1. Read the newly emitted `http-ready` record. Check its PID is the process this
   task started, then GET its exact `url` and compare response bytes with the
   selected entry hash. A stored readiness record does not prove liveness.
2. Open that HTTP URL using the host's permitted browser tool. Observe a unique
   expected heading/content and exercise the report's primary action in the
   rendered page. Treat refusal, unavailable browser, blank/error content or a
   missing asset as incomplete delivery even if HTTP returned 200. For a media
   page, play a representative video and seek to another point; a thumbnail or
   successful range request alone does not establish browser playback.
3. Deliver the verified URL together with the durable artifact path. Keep the
   owning process alive while the reader needs the preview. Stop only this task's
   own process through its session handle/Ctrl-C when its use is finished; never
   terminate foreign processes or trust a stale PID alone.

The executing agent performs these checks with its actual browser capabilities.
The helper establishes HTTP readiness; it cannot establish rendered delivery.
Record those observations separately. Retain an unavailable
browser step as unresolved with its exact recovery condition.

## Exposure boundary

The helper binds IPv4 `127.0.0.1` only, accepts the exact loopback Host/port, and
serves GET/HEAD only for manifest-listed URL paths. It has no directory listing,
filesystem resolver during requests, upload, proxy, shutdown endpoint or CORS
allowance. Cross-origin Origin/Fetch-Metadata requests are rejected; response CSP
limits resource and connection reads to this origin (plus embedded data/blob
resources), so use local listed assets instead of CDN dependencies. It is not a
sandbox for arbitrary untrusted HTML or protection from other software running
as the same local user. Serve only the authorized reviewed report snapshot.

Maintainers: run the narrow safety suite from a source repository checkout after
helper changes. The packaged Skill omits `tests/`; installed consumers use the
manifest/serve commands above and perform the stated HTTP/browser checks.

```bash
python3 -m unittest discover \
  -s <skill-dir>/tests -p test_preview_report.py
```
