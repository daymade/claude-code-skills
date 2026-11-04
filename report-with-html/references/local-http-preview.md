# Local HTTP preview — initial delivery route

Choose this route before the first browser navigation for a new local report.
Keep the HTML file as the durable artifact; preview its reviewed snapshot over HTTP.
Do not try `file://` first. If a browser or permission tool explicitly refuses a
navigation, stop that operation: do not rehost the refused artifact, switch tools,
open it through the shell, or weaken host policy. Resume that artifact only after
an official capability update or explicit permission recovery permits it.

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
The helper permits at most 256 files / 256 MiB in memory; split or reduce an
oversized report within its output contract rather than broadening that bound.

The foreground server uses an OS-selected port unless `--port` is supplied.
An occupied explicit port fails; never stop its owner. A readiness file must be
new: an existing one fails instead of overwriting another preview's state. Hashes
are checked and file bytes frozen before binding. Later source changes cannot
silently change the served snapshot; regenerate into new manifest/readiness files
after report edits and their required review.

## Verify in the actual delivery browser

1. Read the newly emitted `http-ready` record. Check its PID is the process this
   task started, then GET its exact `url` and compare response bytes with the
   selected entry hash. A stored readiness record does not prove liveness.
2. Open that HTTP URL using the host's permitted browser tool. Observe a unique
   expected heading/content and exercise the report's primary action in the
   rendered page. Treat refusal, unavailable browser, blank/error content or a
   missing asset as incomplete delivery even if HTTP returned 200.
3. Deliver the verified URL together with the durable artifact path. Keep the
   owning process alive while the reader needs the preview. Stop only this task's
   own process through its session handle/Ctrl-C when its use is finished; never
   terminate foreign processes or trust a stale PID alone.

The executing agent performs these checks with its actual browser capabilities.
The helper establishes HTTP readiness; it cannot establish rendered delivery or
permission recovery. Record those observations separately. Retain an unavailable
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

Run the narrow safety suite after helper changes:

```bash
python3 -m unittest discover \
  -s <skill-dir>/tests -p test_preview_report.py
```
