# Read a large exact-Session briefing

Use this route before a large or unmeasured exact-Session read, a `--full`
expansion, or recovery from truncated briefing output. The executing agent uses
the existing reader; this procedure does not parse raw JSONL or change its
identity, source-discovery, authorship or compaction checks.

## Capture once outside the tool response

Select the exact Session and resolve the bundled reader before capture. Keep
the authorized working directory and any intentional `--project` restriction.
Use a new absolute private directory outside the repository and shipped Skill;
do not overwrite a prior briefing or put raw history in a public artifact.

Run the existing command with complete stdout and stderr redirected. Substitute
the observed paths and Session ID; keep these as separate files:

```bash
umask 077
briefing_dir=$(mktemp -d /tmp/claude-session-XXXXXXXX) || exit 1
briefing_exit=0
python3 "<absolute-skill-dir>/scripts/read_claude_session.py" \
  --session "<SESSION_ID>" --full \
  > "$briefing_dir/briefing.md" 2> "$briefing_dir/reader.stderr" \
  || briefing_exit=$?
printf '%s\n' "$briefing_exit" > "$briefing_dir/reader.exit"
printf 'reader_exit=%s\nbriefing_dir=%s\n' "$briefing_exit" "$briefing_dir"
exit "$briefing_exit"
```

Preserve a host-provided running handle and wait for its terminal result before
reading the exit file. A missing exit file, lost handle or interrupted command
leaves capture incomplete; a file's presence or nonzero size does not repair it.
For a nonzero reader exit, inspect the saved diagnostic in bounded ranges and
resolve that failure before using the briefing as evidence. Do not turn a
partial file into a successful receipt.

After exit 0, record the briefing's SHA-256, line count and Session identity with
the reader's source/time coverage and compaction boundaries in the task's
existing evidence. Hashes bind the saved bytes; they do not prove every line
reached the model or that the user's business task finished.

## Read bounded coordinates without dropping requests

1. Read the Session-info block first. Locate headings with a bounded search of
   the saved Markdown, then read the end-reason, unresolved-call and gap sections.
   Treat the compact summary as a locator, not verbatim human evidence.
2. Locate every chronological `### Record` heading, paging the heading list
   itself when necessary. Read the full bodies of all retained `USER` entries,
   including queued human input, in physical order. Use the reader's record
   boundaries; a heading-shaped line inside quoted content is only a locator,
   and record labels alone do not establish human authorship.
   Preserve pasted or uncertain-provenance content until its context resolves it.
3. Read the assistant handoffs and evidence surrounding each governing request,
   correction or unfinished action. Use the bundled exact tool-evidence mode
   when the conclusion depends on original tool inputs/results; a briefing
   preview is not that payload.
4. Choose one line or character range below both the command's and the outer
   tool response's budgets. Read it in a separate call, tied to the same saved
   artifact hash. A truncated range remains unread: split it and read the
   missing part before using it. Do not aggregate several large ranges into one
   capped outer response.
5. Track consumed coordinates in the existing task evidence. Read all ranges
   needed for the requested result and disclose the rest as unexamined. A full
   chronology claim requires the full relevant coverage; heading matches,
   selected quotes and the last turns alone cannot establish it. Never claim
   every human request was recovered while a `USER` body remains unread.

For a shell range read, locate headings with `rg -n '^## |^### Record ' <briefing>`
and read the selected lines with `sed -n '<first>,<last>p' <briefing>`. Bound the
heading search too; use the host's character-range reader if one line is too
large. These inspect the saved Markdown, not the raw history store.

## Reuse and recover

Reuse an existing verified briefing or extract when its exact source snapshot,
artifact hash, original coverage and the current question still match. Reuse
does not expand coverage: retain its unread ranges, attachment gaps and uncertain
authorship. A matching Session ID alone does not establish unchanged input.
If newer source records or a different question can change the answer, obtain
only the missing evidence through the existing exact reader into a new private
artifact. Keep the prior artifact and the distinction between their snapshots.

If an unsaved tool response was truncated, rerun only the authorized read into
the private files above. If complete output was already saved, read that file
instead of rerunning the Session or printing the whole briefing again. Keep
identity failures and source gaps visible; never shorten the chronology or skip
pre-compaction/queued requests merely to fit the response budget.
