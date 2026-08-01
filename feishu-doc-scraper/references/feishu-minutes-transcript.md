# Feishu Minutes (妙记) Transcript (Path C)

How to export the **text transcript** of a Feishu Minutes recording. Verified end-to-end 2026-05; re-verified against lark-cli 1.0.80 on 2026-08-01, which is when the `+detail` route below replaced the raw-API-only advice this file used to give.

## Contents

- Start here: `minutes +detail` exports transcripts, and it batches
- The raw endpoint (SRT, or transcripts without speaker/timestamp)
- Output paths: the one restriction both routes share
- Verify the output — with `command grep`, not a bare `grep`
- The scope and the `99991679` error
- Granting the scope via device-flow (and the timeout trap)
- Permission is per-minute, not per-tenant
- Never re-ASR

## Start here: `minutes +detail` exports transcripts, and it batches

```bash
export LARK_CLI_NO_PROXY=1
cd <target-dir> && lark-cli minutes +detail --profile <profile> \
  --minute-tokens <tokenA>,<tokenB>,<tokenC> \
  --transcript --output-dir ./out --overwrite
```

Each token writes **speaker labels + millisecond timestamps** into its own directory under `./out`. The command prints per-token progress and ends with `done: N total, N succeeded, N failed`, so a partial failure is visible instead of silent. Batch limit is **50 tokens per call** (enforced client-side: 51 → exit 2).

Three things about that command that are not obvious:

- **`--profile` — get the value from `lark-cli profile list`, don't guess.** It reports each profile's name, which one is `active`, and a `tokenStatus` that can be `valid` / `expired` / `needs_refresh`. Picking an expired one fails at auth, not at permissions, so it looks nothing like the `2091005` case below.
- **Read the output path from the response, don't reconstruct it.** Each result carries `artifacts.transcript_file` with the real relative path. The naming pattern is `artifact-<title>-<token>/transcript.txt`, but `<title>` is the *server-side* minute title — it can be arbitrary CJK, and in practice frequently contains **spaces**, which is enough on its own to break an unquoted downstream path. You do not know it before the call. Any grep/move/index built on a hand-built path silently finds nothing.
  ```bash
  … --transcript --output-dir ./out | jq -r '.data.minutes[].artifacts.transcript_file'
  ```
- **`--overwrite` is what makes a re-run work.** Without it, a token whose file already exists errors (`file already exists: … (use --overwrite to overwrite)`). Since the whole argument for this route is that failures are visible and therefore retryable, the retry has to actually be runnable — otherwise a second pass reports failures that are really just "already downloaded", and the permission section below then reads as license to skip them.

> An earlier version of this file stated that `lark-cli minutes` could not export transcripts and sent readers straight to the raw API. That was wrong — `+detail` has carried `--transcript` for many releases. If you are pulling more than one or two transcripts, this is the route; the raw endpoint below costs you the batching, the progress reporting, and the failure count.

## The raw endpoint (SRT, or transcripts without speaker/timestamp)

Reach for the raw endpoint in three cases; otherwise use `+detail`.

1. **You need SRT subtitles.** `+detail` writes plain text only; `file_format` is a raw-endpoint parameter (verified: returns standard `00:00:14,920 --> 00:00:16,040` cue blocks).
2. **You want the transcript *without* speaker labels or timestamps.** `+detail` emits both unconditionally. Here they are opt-in flags — so a clean prose body for a Markdown knowledge base is only reachable this way.
3. **You need to control the output filename exactly.** `+detail` derives it from the server-side title.

```
GET https://open.feishu.cn/open-apis/minutes/v1/minutes/:minute_token/transcript
```

| Param | In | Required | Notes |
|---|---|---|---|
| `minute_token` | path | yes | the last segment of the Minutes URL |
| `need_speaker` | query | no | `true` → speaker labels |
| `need_timestamp` | query | no | `true` → per-line timestamps |
| `file_format` | query | no | `txt` or `srt`; `txt` is best for a Markdown KB |

Auth: `--as` takes `user` or `bot` (there is no `--as tenant`; a tenant token is supplied through the environment instead). `--as user` is what these calls want.

```bash
export LARK_CLI_NO_PROXY=1
cd <target-dir> && lark-cli api GET /open-apis/minutes/v1/minutes/<minute_token>/transcript \
  --profile <profile> \
  --params '{"need_speaker":true,"need_timestamp":true,"file_format":"srt"}' \
  --as user -o ./<name>.srt
```

**`--profile` matters on every call, both routes.** It is a global lark-cli flag, and *which identity fetches* is decisive: minutes are shared per-account, so the wrong profile returns `2091005` on a minute another profile reads fine. Run as the default and the "permission is per-minute" section below will tell you to skip a minute that was never out of reach.

## Output paths: the one restriction both routes share

**lark-cli refuses to write outside the working directory** — this applies to `--output-dir` on `+detail` and to `-o` on `api` alike, with the same error text, so switching routes does not escape it. Measured against 1.0.80:

| You pass | Result |
|---|---|
| `./out` or `./sub/name.txt` | works; missing directories are created for you |
| `name.txt` (no `./`) | works, same as `./name.txt` |
| `../out` | refused — `--output "../out" resolves outside the current working directory` |
| `/abs/path` | refused — `--output must be a relative path within the current directory` |
| `~/out` | **not refused — and not expanded either.** Exit 0, writing to a literal directory named `~` |

So **to land transcripts somewhere else, `cd` there and run lark-cli in the same command**: `cd <target> && lark-cli …`. Two separate steps is the trap, not a style preference — in agent harnesses (Claude Code's Bash tool among them) the working directory **resets between tool calls**, so a `cd` in one call and the fetch in the next writes `./out` relative to wherever the session started. And because `./out` is a perfectly legal relative path there too, you get exit 0, `done: N succeeded, 0 failed`, and N files in the wrong repository. Building an absolute path out of a variable is the other reflex to unlearn — that one at least fails loudly.

Two consequences worth stating outright, because both have produced silent data loss:

- **Omitting `-o` on the raw route is not a neutral default.** The body lands in the current directory under a name lark-cli derives itself — measured for a `txt` transcript: `download.txt`, reused for every subsequent fetch, so pulling several tokens in a row overwrites the same file and leaves only the last one. (The extension appears to follow the content type, so a different `file_format` may land elsewhere; the operative point is that you do not choose the name and it repeats.) `+detail` does not have this failure mode — it derives a per-token directory. Verifying that N tokens are reachable by running the command N times without `-o` leaves you with one file and the false impression that all N worked.
- **The refusal itself is honest — exit code 2, message on stderr, empty stdout.** What destroys that signal is the calling script: `lark-cli … > "$log" 2>&1` without testing `$?` folds both the error text and the failure code into a file nobody reads, so N rejected fetches look exactly like N successful ones until you notice every output is missing. If you wrap lark-cli in a loop, either check `$?` per iteration or assert the output file is non-empty — otherwise you have built a silent-failure channel on top of a tool that was telling you the truth.

## Verify the output — with `command grep`, not a bare `grep`

This applies to **both** routes; run it after any fetch, including a 50-token `+detail` batch:

```bash
LC_ALL=C command grep -rl $'\xef\xbf\xbd' .     # empty = clean
```

A U+FFFD replacement character means an encoding step corrupted the text. **The reason for `command` is that a bare `grep` cannot be trusted to find it.** In some agent shells (Claude Code's Bash tool among them) `grep` resolves to a gitignore-aware implementation that silently skips files matched by `.gitignore`. Measured: in a repo whose `.gitignore` contains `*.txt`, a transcript carrying a genuine U+FFFD sequence returns *nothing* from bare `grep -rl` (exit 1, reads as "clean") while `command grep -rl` finds it. Transcripts are routinely written into exactly such a repo, so the bare form converts the only fidelity check here into a guaranteed pass. (`$'…'` is bash/zsh ANSI-C quoting; under a plain `sh` it degrades to a literal string and also yields a false clean.)

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
lark-cli auth login --profile <profile> --scope "minutes:minutes.transcript:export" --no-wait --json
```

**Pass the same `--profile` you will fetch with.** Omitting it grants the scope to whichever profile is active, and the fetch under a different one still returns `99991679` — with nothing in the error to say the grant landed on the wrong identity, so the natural response is to run the device flow again and get the same result.

- The JSON carries **`device_code`** and **`verification_url`**. `--device-code` takes the **`device_code`** field — not the `flow_id` or `user_code` you can also see embedded as query parameters in the verify URL. Picking either of those looks reasonable and fails on the one step that unblocks everything downstream.
- Send `verification_url` to **the person who owns / can access the Minutes** so they approve it in a browser. Treat the URL as an opaque string — no re-encoding, no reassembling the query.
- **End your turn after sending the URL.** Do not display it and then immediately start polling in the same turn: in a harness that only delivers final messages, the user never sees the URL and the poll blocks against an approval that cannot happen.
- Then resume with `lark-cli auth login --profile <profile> --device-code <device_code>` — and do **not** wrap it in a short `timeout`. Each restart invalidates the previous device code, so short-timeout-retry loops never converge; the command can legitimately block ~10 minutes waiting for approval. Do not cache either value for reuse — re-issue `--no-wait --json` each time you need authorization.
- After approval, re-run the fetch; it now succeeds.

## Permission is per-minute, not per-tenant

One Minutes returning `permission deny` (e.g. code `2091005`) does **not** mean other Minutes in the same tenant are denied. Check each minute_token independently. Before chasing a denied one, check whether its content is already covered by another document you can access (a meeting's AI summary doc often duplicates the transcript) — if so, skip it instead of escalating the permission request.

**Before you conclude a minute is out of reach, confirm you tried it under the right `--profile`.** Minutes are shared per-account, so a `2091005` frequently means "this identity cannot see it" rather than "nobody can" — measured: a document readable under one profile returned a permission error under two others on the same machine. Skipping on the strength of a default-profile failure discards minutes you could have fetched, and it does so quietly, because this section otherwise reads as permission to move on.

## Never re-ASR

The platform's native AI transcription is materially better than downloading the media and running ASR yourself (speaker diarization, timestamps, domain vocabulary). Downloading the mp4/mp3 and re-transcribing is a regression — do not do it, even though `lark-cli minutes +download` makes it tempting.
