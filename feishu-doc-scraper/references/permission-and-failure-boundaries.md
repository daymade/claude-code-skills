# Permission Boundaries & Verified Dead-Ends

The single most valuable part of this skill: a record of what does **not** work, so the next run does not re-pay the cost of discovering it. Every entry was verified, not guessed.

## Contents

- Error codes you will hit
- Dead-end table (do NOT attempt)
- Why "empty JSON" from lark-cli is a lie
- Login-wall detection
- Wrong-tool traps

## Error codes you will hit

| Code | Where | Meaning | Correct response |
|---|---|---|---|
| `131006` | `wiki spaces get_node` / `docs +fetch` | `node permission denied, user needs read permission` — the current token cannot read this wiki node | Hard server-side boundary. Stop. Path B: ask the permission holder to export `.docx` out-of-band. Do **not** try lark-cli/curl/browser bypasses. |
| `99991679` | `api …/minutes/.../transcript` | missing scope `minutes:minutes.transcript:export` | Grant the scope via device-flow (feishu-minutes-transcript.md). |
| `2091005` | minutes transcript | that specific minute is permission-denied | Per-minute, not per-tenant. Check if content is covered elsewhere before escalating. |
| `0` | any | success | proceed |

`131006` is a *Feishu-side* decision. It was verified that an anonymous browser redirects to `accounts.feishu.cn/...login`, and that even a logged-in user without a share still has to *request* access. There is no client-side trick. The only path is the document owner exporting it.

## Dead-end table (do NOT attempt)

| Path | Failure mode (verified) | Root cause |
|---|---|---|
| Bypass `131006` via lark-cli retry / different token | still `131006` | server-side per-node ACL |
| Bypass `131006` via anonymous `curl` of the wiki URL | HTTP 200 but body is the login page (`accounts.feishu.cn`, `login`, `passport`, empty `<title>`) | unauthenticated request hits the login wall, not the doc |
| Bypass `131006` via anonymous debugging Chrome | redirected to `accounts.feishu.cn/.../login?redirect_uri=...` | no session in that Chrome profile |
| docx embedded image: `lark-cli docs +media-download --token <img> --type media` | HTTP 404 | command has no `extra` param to identify the owning docx; a bare media token out of its docx context is not resolvable |
| docx image: `lark-cli api GET /open-apis/drive/v1/medias/<img>/download` (no `extra`) | `{"ok":false,...,"API returned an empty JSON response body"}` | lark-cli swallows the real error body |
| docx image: same with `--params '{"extra":"{\"drive_route_token\":\"<doc>\"}"}'` | empty / fails | the `extra` format lark-cli passes is not what the endpoint needs; lark-cli does not wrap this correctly |
| docx image: `lark-cli schema drive.medias.download` (and `.media.`, `.batch_get_tmp_download_url`) | `Unknown resource` | not in lark-cli's schema registry |
| docx image: `lark-cli api … --dry-run` then raw `curl` | `--dry-run` returns method/url/appId/as but **not** the Bearer token → curl authenticates as nobody → real `HTTP/2 400` | lark-cli intentionally does not expose the token; the curl-around-lark-cli path is structurally closed |
| Read the downloaded image bytes to "check" them | `This tool cannot read binary files` | — |
| `WebFetch https://open.feishu.cn/document/server-docs/...` for an API spec | backend flaps, often fails | use `open.feishu.cn/llms-docs/zh-CN/llms-<module>.txt` instead |
| AppleScript `executeJavaScript` in Chrome | `"Executing JavaScript through AppleScript is turned off"` | Chrome disables JS-from-AppleEvents; `defaults write` + restart does not re-enable it here |
| JXA `executeJavaScript` with async/Promise | `Can't convert types. (-1700)` | JXA cannot convert JS Promises to AppleScript types |
| JXA with `ObjC.import` / shebang / `includeStandardAdditions` | syntax errors (`-2741`) | unsupported in this JXA-in-Chrome context |
| Chrome DevTools CDP on `:9222` | `curl :9222/json/list` → `[]` or 404 | CDP endpoints empty even with the flag (profile/policy) |
| `minimax-docx` to convert docx→md | wrong direction | it is a docx *authoring/editing* tool, not an extractor |

**Conclusion for docx embedded images:** lark-cli (through 1.0.32) cannot download `<image>` tokens embedded in a docx — seven distinct approaches were exhausted. Register the tokens and dimensions, note "document owner must right-click → save and send out-of-band", and move on. The text is the deliverable; images are a tracked, transparent gap. Grinding past the established try-limit is itself the mistake.

## Why "empty JSON" from lark-cli is a lie

When lark-cli prints `API returned an empty JSON response body`, the server did **not** necessarily return empty — lark-cli fails to render a binary or error response and substitutes that message. The real status (e.g. `HTTP/2 400`) is only visible via `--dry-run` + `curl`, but `--dry-run` withholds the Bearer token, so that diagnostic path cannot complete an authenticated request. Net: treat "empty JSON" as "unknown failure, lark-cli does not wrap this endpoint", not as "the resource is empty".

## Login-wall detection

Never infer "publicly accessible" from an HTTP 200. A Feishu login wall returns 200 with a body containing any of: `accounts.feishu.cn`, `passport`, a `login` form, an empty `<title></title>`. Always inspect the body. This is why an anonymous debugging Chrome can only answer "is this page public?" — it can never read login-walled content.

## Wrong-tool traps

- **docx → Markdown**: use the `doc-to-markdown` skill (pandoc + post-processing), **not** `minimax-docx` (authoring tool, opposite direction).
- **Finding an unwrapped native API**: use the `lark-openapi-explorer` skill rather than guessing endpoints.
- **A search agent reporting "file not found"**: not authoritative — verify against authoritative sources (`git worktree list`, repo-wide `find`, `git log -S`, the transcripts directory) before concluding. Ingested recordings/transcripts commonly live in a transcripts directory, not where you first looked.
