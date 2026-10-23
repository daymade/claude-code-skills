# Listening Desk / 声间

Use one local desktop workspace to hear a recording, compare recorders, assign
the current speaker, correct the actual transcript and retain the decision.
Python 3.10+ serves the page without Python packages or external web assets.
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
only. Keep it running while reviewing; closing the page does not close it.

## Review in one place

- **Voice samples / 待认声:** selected snippets appear first when supplied. Their
  locator text is read-only and is not a replacement for the transcript. Open
  the corresponding original turn to correct its words, then return to the sample.
- **Full transcript / 整场逐字稿:** search words, speakers or notes, filter by
  speaker or pending status, and navigate surrounding turns without exporting.
- **Listen:** `Q` or Space plays/pauses; `J/K` changes turn. Extend the clip by
  three seconds, loop it, change speed, or select a source at the same canonical
  meeting time. An unavailable source stays disabled.
- **Decide:** keys `1–4` select the first four roster members; enter another
  name when needed. A name click saves that item only. `U` records unknown,
  `S` skips and `Z` undoes the latest saved edit. Typing does not trigger shortcuts.
- **Correct:** edit the actual transcript or a note; typing is saved after a
  short pause. Model candidates, unknowns, pending saves and human confirmations
  remain distinct. A note or word edit does not certify a candidate's identity.
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

The server atomically stores `state.json` under the supplied state directory,
with revisions, request IDs, undo history and an audit trail. The browser stores
only view preferences locally. Do not close a page with unresolved unsaved edits.
A failed save retains the pending choice; retry explicitly. A conflicting
revision reloads current state and requires inspection before a new decision.

Restart with the same project and state directory to resume. The state binds
recording bytes, source clocks, item IDs, original text and identity evidence.
Changing a title, color or waveform resolution does not invalidate decisions;
changing evidence refuses startup rather than attaching old labels to new audio.
Corrupt state is an explicit error, never an empty successful session. Preserve
the file before investigating; a new state directory starts a separate review
and does not recover earlier judgments.

The service supports HTTP Range and detects common audio types by their headers.
It serves only declared audio and its bundled static assets. There is no upload,
cloud synchronization, background inference or automatic voice enrollment.

## Verify changes

Run `python3 -m unittest discover -s <skill-root>/scripts/review-workbench/tests -v`
and `node --check <skill-root>/scripts/review-workbench/static/app.js` for changed
code. Then exercise the real browser: hear a clip; change source inside overlap;
confirm an item; refresh; undo; download and open an export. Check failed-save
and revision-conflict recovery without polluting the real review's decisions.
Use a separate project ID/state directory for test judgments.
