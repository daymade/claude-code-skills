# Feishu Minutes (妙记) Transcript (Path C)

How to export the **text transcript** of a Feishu Minutes recording. Verified end-to-end (2026-05).

## Contents

- The key fact: lark-cli cannot do it directly
- The native endpoint
- The scope and the `99991679` error
- Granting the scope via device-flow (and the timeout trap)
- Permission is per-minute, not per-tenant
- Never re-ASR

## The key fact: lark-cli cannot do it directly

`lark-cli minutes` exposes `minutes get` (metadata), `+download` (audio/video), `search`, `upload`. **None export the transcript text.** `lark-cli minutes minutes get --params '{"minute_token":"<t>"}'` succeeds but returns only title/duration/url — no transcript. The transcript is a native endpoint not wrapped by lark-cli; call it through `lark-cli api`.

## The native endpoint

```
GET https://open.feishu.cn/open-apis/minutes/v1/minutes/:minute_token/transcript
```

| Param | In | Required | Notes |
|---|---|---|---|
| `minute_token` | path | yes | the last segment of the Minutes URL |
| `need_speaker` | query | no | `true` → speaker labels |
| `need_timestamp` | query | no | `true` → per-line timestamps |
| `file_format` | query | no | `txt` or `srt`; `txt` is best for a Markdown KB |

Auth: `user_access_token` (use `--as user`) or `tenant_access_token`.

```bash
export LARK_CLI_NO_PROXY=1
lark-cli api GET /open-apis/minutes/v1/minutes/<minute_token>/transcript \
  --params '{"need_speaker":true,"need_timestamp":true,"file_format":"txt"}' \
  --as user -o <speaker-and-timestamped-transcript>.txt
```

A successful run yields the full transcript with speaker + millisecond timestamps; verify with the U+FFFD check (`LC_ALL=C grep -rl $'\xef\xbf\xbd' .` empty).

> Spec lookups: use `https://open.feishu.cn/llms-docs/zh-CN/llms-minutes.txt` (stable, LLM-friendly). `WebFetch` against `open.feishu.cn/document/server-docs/...` is flaky. If lark-cli has no wrapper for something, the `lark-openapi-explorer` skill is the systematic way to mine the native spec.

## The scope and the `99991679` error

Without the export scope the call returns:

```json
{"ok":false,"error":{"type":"permission","code":99991679,
 "message":"Permission denied [99991679]",
 "detail":{"permission_violations":[
   {"subject":"minutes:minute:download","type":"action_privilege_required"},
   {"subject":"minutes:minutes.transcript:export","type":"action_privilege_required"}]}}}
```

The scope you need is **`minutes:minutes.transcript:export`**.

## Granting the scope via device-flow (and the timeout trap)

```bash
lark-cli auth login --scope "minutes:minutes.transcript:export" --no-wait --json
# → returns a device flow_id + user_code + a verify URL like:
#   https://accounts.feishu.cn/oauth/v1/device/verify?flow_id=...&user_code=XXXX-XXXX
```

- Send the **verify URL to the person who owns / can access the Minutes** so they approve it in a browser.
- Resume polling with `lark-cli auth login --device-code <code>` — do **not** wrap the login in a short `timeout`. lark-cli explicitly warns: each restart invalidates the previous device code, so short-timeout-retry loops never converge. The login command can legitimately block for up to ~10 minutes waiting for approval.
- After approval, re-run the `api … /transcript` call; it now succeeds.

## Permission is per-minute, not per-tenant

One Minutes returning `permission deny` (e.g. code `2091005`) does **not** mean other Minutes in the same tenant are denied. Check each minute_token independently. Before chasing a denied one, check whether its content is already covered by another document you can access (a meeting's AI summary doc often duplicates the transcript) — if so, skip it instead of escalating the permission request.

## Never re-ASR

The platform's native AI transcription is materially better than downloading the media and running ASR yourself (speaker diarization, timestamps, domain vocabulary). Downloading the mp4/mp3 and re-transcribing is a regression — do not do it, even though `lark-cli minutes +download` makes it tempting.
