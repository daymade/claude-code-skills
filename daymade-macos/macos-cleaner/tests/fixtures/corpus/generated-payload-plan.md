# Generated-payload decision replay

Sanitized task-shape replay: an old plan referenced a retired release, and a
finished CI task left a generated source copy. This fixture contains declared
observations, not evidence about the reader's machine. No deletion is executed.

| Target | Class | Governing rule | Expected physical release | Verdict |
|---|---|---|---|---|
| /opt/example/releases/old | REBUILDABLE | "Protect unique source edits, local Git state, credentials, databases and user records." | unknown | in action set |
| /opt/example/ci/source-copy | REBUILDABLE | "Protect unique source edits, local Git state, credentials, databases and user records." | unknown | in action set |
| /opt/example/releases/current | PRESERVE | "Protect unique source edits, local Git state, credentials, databases and user records." | unknown | not in action set |
| /opt/example/ci/unique-copy | USER-DATA | "Protect unique source edits, local Git state, credentials, databases and user records." | unknown | not in action set |
| /opt/example/ci/unreadable-copy | PRESERVE | "Protect unique source edits, local Git state, credentials, databases and user records." | unknown | not in action set |
| /opt/example/releases/kept | PRESERVE | "Protect unique source edits, local Git state, credentials, databases and user records." | unknown | not in action set |

| Target | Payload kind | Current use | Unique state | Recovery input | Restoration cost | Retention basis | Backup plan |
|---|---|---|---|---|---|---|---|
| /opt/example/releases/old | release | inactive: current selector and running process point to current; no task uses old | absent: bundle matches retained source manifest, no local edits/state | git:example/source@0123456789abcdef0123456789abcdef01234567 and lockfile; verified through source owner | rebuild takes minutes and may download locked dependencies | historical-only: old plan and retired config mention old | none: retain source, create no full backup |
| /opt/example/ci/source-copy | generated-test-copy | inactive: CI and all readers finished; result/coverage retained outside copy | absent: source files match immutable ref; no edits or local-only Git/database/auth files | git:example/source@0123456789abcdef0123456789abcdef01234567; verified source owner | export again only if another consumer needs it; do not rerun finished CI | none: consumer completed | none: generated copy needs no backup |
| /opt/example/releases/current | release | active: live selector and process use this exact path | absent: generated bundle verified | git:example/source@0123456789abcdef0123456789abcdef01234567 | rebuild takes minutes | current-use: live process uses current | none: preserve current payload |
| /opt/example/ci/unique-copy | generated-test-copy | inactive: task finished | present: local source edits, local Git objects and database/auth state remain | unknown: preserve unique files before deciding any generated subtree | unknown: inspect unique work with its owner | unique-state: original edits and state | none: no backup authorized in this plan |
| /opt/example/ci/unreadable-copy | generated-test-copy | unknown: query consumer owner before selecting files | unknown: inspect only selected source-copy contents | unknown: verify source ref through owner | unknown: verify rebuild cost | unknown: current use and unique work not yet checked | none: no copy authorized |
| /opt/example/releases/kept | release | inactive: no process or selector uses this path | absent: generated content matches source | git:example/source@0123456789abcdef0123456789abcdef01234567 | rebuild takes minutes | user-requested: "Keep this exact old payload for my comparison" | none: preserve the requested payload in place |
