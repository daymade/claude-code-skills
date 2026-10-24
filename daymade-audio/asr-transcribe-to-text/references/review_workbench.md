# Listening Desk / 声间

Use one local desktop workspace to hear a recording, compare recorders, assign
the current speaker, correct the actual transcript and retain the decision.
The Python server uses the standard library and no external web assets.
CSV preparation requires `ffprobe` and `ffmpeg` on PATH; it performs no ASR or
speaker inference. Original audio and transcript inputs remain unchanged.

## Open an existing transcript

Run the absolute bundled `scripts/review-workbench/prepare_project.py` with
`--csv`, `--audio` and `--output` absolute paths. Add repeatable `--person` names
to provide the on-screen roster. Names from automatic transcript labels remain
candidates; a roster is not evidence that those people spoke a particular turn.
One CSV preparation binds one recording. A CSV containing multiple `file`
values is rejected rather than pairing unrelated turns with one audio file.

Then run `scripts/review-workbench/server.py --project <absolute-project.json>
--state-dir <absolute-private-state-directory>`. The default URL is
`http://127.0.0.1:8780/`; `--port` selects another available port and
`--no-browser` suppresses automatic opening. The server accepts loopback hosts
only; `--host ::1` uses IPv6 loopback and prints a bracketed URL. Keep it running
while reviewing; closing the page does not close it.

## Review in one place

- **Voice samples / 待认声:** selected snippets appear first when supplied. Their
  locator text is read-only and is not a replacement for the transcript. Open
  the corresponding original turn to correct its words, then return to the sample.
- **Full transcript / 整场逐字稿:** search words, speakers or notes, filter by
  speaker or pending speaker identity, and navigate nearby turns without exporting.
  Identity confirmation does not certify the words or the source of the speech.
- **Listen:** `Q` or Space plays/pauses; `J/K` changes turn. Extend the clip with
  available context, loop it, change speed, or select a source at the same canonical
  meeting time. An unavailable source stays disabled. The transport distinguishes
  reading, buffering, playing, paused, ended and failed states. Retry reloads
  failed media; switching turns cancels pending playback before changing position.
- **Compare voices:** expand the confirmed-voice drawer to hear a short reference
  from another human-confirmed item. The current turn, cursor and judgment
  remain in place; resume the current turn directly after listening. Candidate,
  unknown, skipped and unsaved identities are excluded from the reference bank.
  The capped reference excerpt must be fully covered by its selected source;
  a longer turn extending beyond the recording does not exclude a covered excerpt.
- **Decide:** keys `1–4` select the first four roster members; enter another
  name when needed. A name click saves that item only. `U` records unknown,
  `S` skips and `Z` undoes the latest saved edit. Typing does not trigger shortcuts.
  A delayed skip acknowledgment saves its original item without moving you away
  from a newer turn, seek or recorder selection.
- **Correct:** edit the actual transcript or a note; typing is saved after a
  short pause. Model candidates, unknowns, pending saves and human confirmations
  remain distinct. A note or word edit does not certify a candidate's identity.
  Changed text exposes a collapsible original/current comparison. `Esc` returns
  focus from editing to the listening control; IME composition stays protected.
  Read-only sample text does not disable the listening shortcuts.
- **Export:** JSON includes decisions and derived items; CSV and Markdown carry
  readable derived transcripts with identity status. Exports do not modify a
  canonical file, cloud labels, a voiceprint library or a correction dictionary.

The offline audit generator remains available for portable batch browsing and
historical browser-local flags/aliases. Existing `transcript-fixer` queue and
dictionary actions retain their CLI state machine; this desk does not silently
accept those actions or replace their guarded apply step. Return manual text
corrections through that workflow's exact-file reconciliation and anchor checks.

## Several recorders or selected voice samples

The project JSON is explicit. `people` defines the roster; `sources` defines
audio files and clocks; `items` defines timestamped transcript turns or samples.
All item times use one canonical meeting clock. For a source with `offset` and
`scale`, its local playback time is `(canonical_time - offset) / scale`.
Determine that mapping from actual matching audio; never infer it from filenames
or assume two devices started together.

When a downstream correction uses external evidence files to map excerpts back
to their originals, set project `evidence_hashes` before review. It is a nonempty
map of ASCII identifier keys to lowercase SHA-256 digests of those files. The
map joins the project fingerprint; changing it requires a new review binding.
Omitting it preserves the existing project fingerprint contract. An old state
cannot silently acquire a new evidence association. This binds a review to the
declared files; it does not authenticate their author or prove their contents.

```json
{
  "schema_version": 1,
  "project_id": "example-meeting",
  "title": "Meeting review",
  "people": [{"id": "a", "name": "Participant A", "color": "#5D7A6E"}],
  "sources": [{
    "id": "main", "label": "Recorder A", "audio_path": "/absolute/audio.m4a",
    "duration": 120.0, "clock": {"offset": 0, "scale": 1}, "peaks": []
  }],
  "items": [{
    "id": "turn-1", "kind": "transcript", "start": 10, "end": 15,
    "text": "Synthetic example utterance.", "speaker": "Speaker 1",
    "identity_status": "unknown", "source_id": "main"
  }]
}
```

`identity_status` is `unknown`, `candidate` or `human_confirmed`. Only populate
the last from an explicit confirmed source, not the model's confidence. Add
`kind: "speaker_sample"` for a chosen snippet, with a distinct ID and optional
`title`/`priority`. Its decision is limited to that snippet; it does not relabel
all acoustically similar turns. `peaks` contains real normalized amplitude
samples from zero-start decoding, not fabricated bars. An empty list honestly
omits the waveform while preserving playback.

## Saving and recovery

Roster buttons submit display names. Saved decision names keep that meaning
through later edits and exports, even when a name equals another person's roster
ID. Original item speakers matching a roster ID still resolve as source IDs;
they do not override the reviewed name. Exports attach a roster ID only when the
reviewed name identifies a unique roster member.

The server atomically stores `state.json` under the supplied state directory,
with revisions, request IDs, undo history and an audit trail. The browser stores
only view preferences locally. Do not close a page with unresolved unsaved edits.
A failed save retains the pending choice; retry explicitly. A conflicting
revision reloads current state and requires inspection before a new decision.
Editing, queued requests and unsent changes remain unsaved until their own
acknowledgment arrives. Returning a field to an earlier value does not let an old
response confirm the new edit.

Every save and undo binds the project fingerprint captured when it was queued.
If the service now serves a different project, the page retains the unsaved edit
and refuses to retry it against the replacement. Preserve that edit before
opening the intended project again. A project mismatch is not a revision conflict.

Restart with the same project and state directory to resume. The state binds
recording bytes, source clocks, item IDs, original text and identity evidence.
Changing a title, color or waveform resolution does not invalidate decisions;
changing evidence refuses startup rather than attaching old labels to new audio.
Corrupt state is an explicit error, never an empty successful session. Preserve
the file before investigating; a new state directory starts a separate review
and does not recover earlier judgments.

For supported integer PCM WAV sources, the service streams a sample-bounded WAV
for the selected item, source and context. Its natural end limits playback even
when browser timers are delayed; seeking and the displayed clock retain the
original source offset. Partial source coverage remains visible. Other audio
formats retain full-source playback with an explicit approximate-boundary notice;
they do not acquire the PCM boundary guarantee. The server advertises this
capability from the actual file header, not the filename.

The service supports HTTP Range and detects common audio types by their headers.
It serves only declared audio and its bundled static assets. There is no upload,
cloud synchronization, background inference or automatic voice enrollment.

Playback progress and decoded media do not establish audible output. If progress
moves without sound, use the page's sound-help disclosure: check the browser's
tab/site mute, the page volume and the system output device. Page JavaScript
cannot remove browser-level tab muting. Listening references use the same volume
control and do not create or update a voiceprint profile.

## Verify changes

Run `python3 -m unittest discover -s <skill-root>/scripts/review-workbench/tests -v`
for changed backend/importer code. For frontend changes run
`node --check <skill-root>/scripts/review-workbench/static/app.js` and
`node --test <skill-root>/scripts/review-workbench/tests/*.cjs`.
For source-repository CI, follow
[CI operations](https://github.com/daymade/claude-code-skills/blob/main/references/ci-operations.md)
to inspect the exact candidate's registered-suite results. Keep test totals in
the run's historical evidence rather than maintaining them in this guide.
Then exercise the real browser: hear a clip; change source inside overlap;
confirm an item; refresh; undo; download and open an export. Check failed-save
and revision-conflict recovery without polluting the real review's decisions.
Use a separate project ID/state directory for test judgments. Also compare a
confirmed reference, resume the current turn, and verify the cursor and judgment
stay unchanged. A page blocked by browser permissions leaves these journeys
unverified even when synthetic event regressions pass.
For persistence changes, exercise rapid edits that return to the first value,
lost acknowledgments and a stale tab after the server changes project. For
playback changes, inspect actual decoded media boundaries and distinguish nearby
overlapping recorders from disconnected recordings; a clamped progress display
alone cannot establish where playback stopped.
