# Source Manifest Contract

The manifest is JSON. Paths are absolute or `~`-prefixed. Nothing is discovered
outside these declarations.

```json
{
  "schema_version": 1,
  "state_dir": "~/.cache/daymade/prior-work",
  "sources": [
    {
      "id": "project-docs",
      "carrier": "docs",
      "mode": "filesystem",
      "root": "/absolute/docs/root",
      "includes": ["**/*.md"],
      "excludes": ["**/.git/**", "**/node_modules/**"],
      "authority": "project_ssot",
      "required": true,
      "max_results": 20
    },
    {
      "id": "claude-history",
      "carrier": "conversation",
      "mode": "command",
      "argv": [
        "/absolute/uv", "run", "--no-project", "python",
        "/absolute/history_index.py", "recall", "{query}",
        "--mode", "auto", "--limit", "{limit}", "--json"
      ],
      "result_format": "finder_recall_v1",
      "authority": "raw_history",
      "required": true,
      "max_results": 10,
      "timeout_seconds": 30
    },
    {
      "id": "live-wechat",
      "carrier": "wechat_live",
      "mode": "manual",
      "route": "read-wechat-messages",
      "instruction": "Search the registered chats and report uncovered voice/media.",
      "authority": "raw_history",
      "required": false
    }
  ]
}
```

## Source fields

| Field | Contract |
|---|---|
| `id` | Unique stable ID; used by receipts |
| `carrier` | `code`, `docs`, `skills`, `meeting`, `wechat_archive`, `wechat_live`, `conversation`, or `other` |
| `mode` | `filesystem`, `command`, or `manual` |
| `authority` | `current_implementation`, `project_ssot`, `verified_history`, `raw_history`, `archive`, or `unknown` |
| `required` | Failure/manual gap prevents a globally complete coverage claim |
| `max_results` | Bounded candidates returned from this source |

Filesystem sources require `root` and non-empty `includes`. `excludes` is
optional. Patterns are passed as explicit `rg --glob` arguments; the script does
not invent an include convention.

Command sources require an `argv` array. Only `{query}`, `{limit}`, and
`{session_id}` are expanded. The executable is invoked directly, never through a shell. Supported
result formats are named in the script; an unknown format fails validation.

Manual sources never pretend to be searched. The receipt reports
`manual_required` until an agent completes the named route and records that
evidence outside the automatic run.

## Authority is not a score of truth

Authority tells the reviewer what the source can establish:

- `current_implementation`: what the system currently does.
- `project_ssot`: current intended rule or decision.
- `verified_history`: a historical fact independently checked.
- `raw_history`: what someone said/did at a time; not automatic current truth.
- `archive`: superseded or frozen evidence only.

The reviewer still opens the source. A current implementation can be buggy; a
raw meeting claim can be wrong; a current decision can deliberately supersede a
successful old tactic.
