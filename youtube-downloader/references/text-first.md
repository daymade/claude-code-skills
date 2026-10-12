# Text-First Ladder: Get the Spoken Content Without Downloading the Video

Load this when the user's goal is the **text** of a video (transcript, subtitles,
meeting notes, archive, "what was said") rather than the video/audio file itself.
When the user wants the file, ignore this ladder and use the normal download flow
in SKILL.md — a text-first miss never blocks a file request.

Climb down the ladder; stop at the first level that yields usable text. Every
level names its own failure exit. Do not batch-download media to hunt for text:
each level targets only the specific video(s) the user named.

**Identity rule (all levels):** match sources by the video's ID (the `v=` parameter
or platform equivalent), never by title alone. A title hit is a candidate, not a
match — confirm the archived/API record's video ID equals the requested one before
reusing its text.

## L1 — Existing archives you already own

**Trigger:** always start here.

**Entry:**
1. If available, use `skills-search` across owned sources for a skill that already archives this
   content (e.g. favorites/web-archive owners), then query that owner's archive.
2. If available, use `favorites-search` over the existing favorites/subscription collections for the
   video ID. If either helper or its archive is unavailable, record that route as
   unchecked and continue to L2/L3; do not require installation of an inaccessible
   helper or treat its absence as proof that no transcript exists.

Reuse archived text as-is when the record's video ID matches and the snapshot is
complete (full transcript, not a stub). Do not re-download or re-transcribe what
is already archived.

**Failure =** no archive record with a matching video ID, or the record is a
stub/pointer without full text. **Exit → L2.**

## L2 — Ready transcripts from existing services

**Trigger:** check the user's already selected transcript services for the video,
including conference talks and other non-podcast videos. This may include Guyu
knowledge-base transcripts or Podwise episodes; do not require a new subscription
or processing purchase to complete this level. Use the available service-owning
Skill and verify its current read route before fetching.

**Podwise owner, when available:** the `podwise-reader` skill (a separate thin bundle: read-only transcript
retrieval + local export). If it is not installed, treat this level as a pointer
only — do not invent CLI invocations or API paths beyond the verified surface below.

Verified read-only surface (from the official Podwise CLI v0.4.2 source): direct
HTTPS GET against the open API, i.e. `GET /api/open/v1/episodes/<episode_seq>` and
its transcript endpoint, using the user's existing token.

**Forbidden for read-only retrieval:** the official CLI v0.4.2 `get transcript` and
`get summary` commands asynchronously call MarkAsRead server-side after a
successful GET — they mutate account state. Do not use them when the goal is only
to read text; use the direct GET methods above or wait for `podwise-reader`.

Match the episode by its source video ID, never by title. If there is no matching
episode, do not auto-process / translate / import anything.

**Failure =** no episode whose source video ID matches, or only mutation-capable
CLI access is available. **Exit → L3.**

## L3 — Original subtitles via yt-dlp (subtitle-only, no media download)

**Trigger:** L1–L2 missed and the platform exposes subtitle tracks (YouTube and
most yt-dlp-supported sites).

**Entry:** list actual tracks first. Select an available original or requested
language; the English/Chinese expression below is an example, not a requirement
for every video. Do not call subtitles missing merely because that example
excludes the source language. Flags were checked against yt-dlp 2026.03.17.

```bash
# 1. List available subtitle tracks (simulates; downloads nothing)
yt-dlp --skip-download --list-subs "VIDEO_URL"

# 2. Fetch subtitles only — --skip-download guarantees no video/audio is written
yt-dlp --skip-download --write-subs --write-auto-subs \
  --sub-langs "en.*,zh-Hans,zh-Hant" --sub-format "srt/vtt/best" --convert-subs srt \
  -o "%(title)s-%(id)s.%(ext)s" "VIDEO_URL"
```

- Prefer uploader-provided tracks (`--write-subs`); auto-generated subs
  (`--write-auto-subs`) are a fallback. Uploaded tracks also do not prove human
  authorship or review; claim a reviewed status only with separate evidence.
- Auto-generated or uncorrected subtitles archived downstream must be labeled
  "auto-generated, not human-reviewed (未精校)" with the source URL and retrieval
  timestamp.
- Subtitle requests hit the same bot-check wall as downloads: the cookie and
  PO Token rules in SKILL.md's Reliable Download SOP apply unchanged. Do not
  restate or weaken them here.

**Failure =** no subtitle track in the wanted language (neither human nor auto),
or retrieval still blocked after the standard cookie/PO-token recovery.
**Exit → L4.**

## L4 — Authorized audio track + ASR after the checked text routes miss

**Trigger:** no usable text was obtained through the checked L1–L3 channels; the
user still wants the text. Record unavailable channels as unknown, not proof that
no transcript exists anywhere.

**Entry:**
1. Confirm the user has the rights/permission for this content — the same
   authorization, playlist, cookie and PO Token rules as a normal file download
   apply unchanged.
2. Download the **audio track only**, never the full video:

```bash
yt-dlp -f bestaudio -x --audio-format mp3 "VIDEO_URL"
# or
yt-dlp -f bestaudio "VIDEO_URL"
```

Require an audio-only format: `-x` alone defaults to `bestaudio/best` and can
fetch a combined video when no separate audio track is offered. An unavailable
`bestaudio` format leaves this route blocked; do not add a video fallback.
For an existing local video/audio file, reuse that file at this level after the
same identity-based text checks, without downloading another copy.

3. Hand the local audio file to `/daymade-audio:asr-transcribe-to-text` for
   GPU transcription. CPU inference is a hard stop, not a fallback: if no
   GPU-capable route is available, report blocked instead of transcribing on CPU.

**Failure =** no authorized audio track, or no GPU ASR route available. **Exit →**
stop and report that no text was obtained; offer the normal file-download flow if
the user also wants the video itself.

## Invariants

- This ladder changes nothing about the download flow: defaults, cookie/account
  authorization, playlist confirmation, PO Token recovery, HLS handling, retry and
  proxy behavior in SKILL.md are all untouched.
- A text-first miss never converts into "just download the video anyway" without
  the user asking for the file.
- Archive results carry their provenance: which level produced the text, source
  URL/video ID, retrieval timestamp, and review status (uploaded, automatic or ASR; unreviewed unless explicitly checked).
