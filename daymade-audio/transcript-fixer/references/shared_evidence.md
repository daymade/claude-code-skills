# Shared dictionary, roster and domain contexts

An optional `DAYMADE_AUDIO_CONFIG` JSON profile (otherwise
`$XDG_CONFIG_HOME/daymade-audio/config.json`, default `~/.config`) binds existing
source resources. Without these bindings, standalone loading and writing retain
their original behavior. The Skill does not require a Python SDK or daemon.

```json
{
  "device": {"id": "configured-device-id"},
  "source_reader": {"protocol": 1, "argv": ["/absolute/runtime/bin/daudio", "get"]},
  "source_publisher": {"protocol": 1, "argv": ["/absolute/runtime/bin/daudio", "import"]},
  "evidence_bindings": {
    "transcript-fixer.dictionary": {"uri": "daudio://dictionary/RESOURCE_ID", "domain": null, "owner_device_id": "configured-device-id"},
    "transcript-fixer.roster": {"uri": "daudio://context/ROSTER_ID/versions/1", "domain": null},
    "transcript-fixer.contexts": [
      {"uri": "daudio://context/CONTEXT_ID", "domain": "project-domain"}
    ]
  }
}
```

`source_reader` receives the literal resource URI as one appended argument. A
stable URI resolves once per CLI operation; a pinned URI keeps its exact version.
The response must include matching `uri`, `version`, `version_uri`, `kind`,
`metadata.domain`, source byte hash/size, and original bytes. Dictionary resources
use `transcript_fixer_sqlite` with a verified consistent `sqlite_backup` image;
roster/context resources use `text` with the matching `text_kind`. Missing,
foreign, malformed or drifted configured evidence fails before opening the
native writer. Other Skills' bindings are ignored.

Shared SQLite images use the existing repository selectors through read-only
connections. The native DB remains the only writer for learning, disabling,
history and manual edits. Active native rules win over shared rules in their
domain; an inactive rule vetoes only its exact `(domain, from, to)` pair. Original
ordered-domain and regex priority rules still decide processing order. Shared
IDs are diagnostics, never native mutation IDs. Reporting a shared-only false
positive writes an exact-pair decision to the native audit log; a native active
rule and its explicit reactivation retain precedence.

The original people-roster parser reads shared ASR variants; local roster entries
win a conflict. The original context parser reads traps from both the pinned
shared context and local domain file, retaining local vetoes. Stage 2 receives
only the selected domains' actual context text with pinned source references.
Names, context text and source claims do not confirm a speaker identity.

`source_publisher` is optional and separate from the reader. It appends
`dictionary <native-path> --source-key <configured-owner-key>` and optional
`--domain`, calling the existing importer. Publication requires the configured
source original file URI to match the native dictionary path and its source key
to belong to `source-import:dictionary:`. It does not derive a write command from
the reader or publish another owner's path.

Publishing also requires the same profile's nonempty `device.id` to match the
dictionary binding's `owner_device_id`. Missing or foreign identity leaves work
pending; a device change cannot relabel another device's pending work. Reads can
share sources across devices. This is a configured identity boundary, not
hardware attestation or protection against copying the same identity profile.
Historical pending work with missing identity remains pending after profile
repair; the original owner must resolve it explicitly rather than infer ownership.

After native commits, `shared-publications.json` under the native configuration
directory records pending audit cursors before attempting publication. Failures
retain the native commit and pending work; a later ordinary CLI operation
replays it. A receipt records the pinned version and the consistent snapshot's
`captured_through_audit_cursor`; several commits captured together are one
snapshot, not fabricated intermediate versions. Captured command output is
private and never printed into logs or the compact outbox. The Skill does not
retry the original correction or add a scheduler. The configured importer keeps
its existing explicitly configured dependent-refresh behavior.

Run the isolated real-CLI cases with the declared script dependencies:

```bash
uv run --with pytest --with httpx --with filelock --with jieba --with 'rapidfuzz>=3.14,<4' \
  python -m pytest scripts/tests/test_shared_evidence.py -q
```

Fixtures clear provider credentials, bind temporary configuration/DB paths and
reject socket connections, including the canonical service port. They test
Stage 2 with a local fake processor, without calling a model.
