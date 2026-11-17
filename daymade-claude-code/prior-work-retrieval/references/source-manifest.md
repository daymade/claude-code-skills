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
        "/absolute/history_index.py", "recall", "--terms", "{terms}", "{query}",
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

The manifest declares possible sources, not current-task read authorization.
`retrieve --filesystem-scope <absolute-project-directory>` is required to run a
filesystem source; repeat it only for separately authorized project or asset
directories. The source's resolved root must be inside a supplied scope. A scope
inside a broad source root does not authorize that parent scan. With no matching
scope, the source reports `manual_required` before launching an adapter, including
Git freshness probes. This applies to optional and required sources alike; globs,
`max_results` and timeouts do not bound the number of directories visited.
Resolve source and scope aliases before comparing bounds, and do not follow
descendant symlinks during either content or filename search. All filesystem
ripgrep calls, including the freshness matcher, use `--no-config` and
`--no-follow`: inherited configuration cannot add search roots or enable link
traversal. Declare needed case/glob matching in `includes`/`excludes` rather than
ambient ripgrep configuration.

Use scoped sources or an existing index when a shared manifest lists collection
roots. Keep an unresolved required source visible, and record only the actual
scoped/indexed verification through `complete --manual-complete`. Do not enlarge
scope to satisfy a receipt. Command adapters retain their declared index contract;
this flag does not grant permission for a command adapter to scan raw collections.

Command sources require an `argv` array. Only `{query}`, `{limit}`,
`{session_id}`, and `{terms}` are expanded (`{terms}` is optional: it expands to
the space-joined implementation terms — add it once as a single argv element, as
in the example above; a manifest without the slot keeps working unchanged and the
receipt records `terms_passed: false`). The executable is invoked directly, never
through a shell. Supported
result formats are named in the script; an unknown format fails validation.

For a lexical command adapter, prefer `{terms}` when it accepts implementation
keywords; retain `{query}` when the adapter requires the original request or
semantic input. Check the adapter's documented token/AND semantics rather than
feeding it a long outcome sentence by default. Treat `command_timeout` as an
unresolved source failure: inspect the query shape and source health before
raising `timeout_seconds`. Do not infer that every timeout has the same cause or
copy timings measured on another index.

A command adapter's payload may carry `last_indexed_at` and `complete_frontier`.
They surface on the receipt as readable freshness fields (`freshness`:
`fresh`/`stale`/`unknown` plus `freshness_reason`) — visibility, never a gate:
`status` stays `searched`, so a stale index means "may have missed something",
not "does not exist", and can never block receipt completion.

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
