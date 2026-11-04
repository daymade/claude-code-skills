# YouTube Downloader Internal SOP

1. Quote URLs in shell commands (`'https://www.youtube.com/watch?v=VIDEO_ID'`). Bind the requested video, output type and quality before downloading.
2. Check the current yt-dlp installation, supported JavaScript runtime/EJS setup and the intended proxy. Use the native default clients first; do not install a provider or select Android as a prerequisite. Pass `--js-runtimes node` to the wrapper only when using an already-installed Node runtime.
3. Read the failing diagnostic and available media formats. “Only images”, “Requested format is not available”, 360p-only output and HTTP 403 each need diagnosis; none alone establishes a PO Token requirement. A timeout/SSL failure is not token evidence.
4. If the failed extraction or media request explicitly names a missing/required PO Token, load [provider setup](po-token-setup.md). Within existing installation/service authorization, execute the wrapper with `--auto-po-token`, then verify the original file request. If setup is not authorized, ask only for that missing permission. Do not stop after suggesting a command when it is already authorized.
5. If an account or persistent bot check requires cookies, obtain cookie permission before supplying either cookie option. Preserve the authorized session. Leave client selection native unless a compatible targeted retry is needed; never switch a cookie download to Android/iOS.
6. For an authorized provider branch, use bgutil or browser WPC as documented. Keep the WPC window open while minting tokens and use the same intended network path. Pass that proxy to the provider too; in a bridged container, translate a host-local proxy address to `host.docker.internal`. If browser discovery fails, supply `--wpc-browser-path`. Do not install Docker, restart a shared service, or delete a container as an automatic workaround.
7. For a media 403/fragment error under a quality preset, allow one progressive-format retry and check whether its lower quality still satisfies the request. Preserve custom format selections. For network failures, repair the diagnosed connection issue before another bounded attempt.
8. Validate the actual local file with `ffprobe`: streams, duration and resolution/audio properties. Report the observed path, size and quality; provider health, metadata and format listings do not prove media delivery.

## Existing authorized downloader handoff

After a failed local attempt, the executing agent checks existing authorized
capabilities before requesting browser-cookie extraction or preparing another
provider. If an installed NAS/downloader owner supports the same URL, use that
owner's native task workflow (for example `lazycat-use` when available). Preserve
the exact source identity, requested quality, destination and sharing scope.
Continue through its completed task and actual file, then reconcile the original
archive. A metadata parse, task submission or live service is not media delivery.

Keep this branch optional: an absent owner, unavailable existing login or genuine
permission boundary returns a named prerequisite, while other authorized work
continues. Do not install a downloader, switch devices/accounts, approve new trust,
change shared egress or buy parsing to make this handoff available. If no existing
route can continue, resume the diagnosed local recovery above and request only a
truly missing permission. A media 403 alone does not prove cookies or PO Tokens
are required, and success on another device does not isolate the local cause.
Keep existing yt-dlp version/runtime checks; an old-engine warning is evidence to
inspect, not proof an upgrade will fix the input. No generic script enforces the
owner choice; the agent resolves the available owner and verifies its final file.
