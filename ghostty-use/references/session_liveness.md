# Session liveness: storage layouts and classification rules

Verified against Claude Code (glm profile on 2026-10-04) and Codex CLI 0.16x
on macOS. All timestamps in this file are evidence anchors — re-verify after a
major app update rather than trusting the dates.

## Claude Code transcript layout

- Per-session file: `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`
  (`/` → `-` encoding of the working directory at session start).
- JSON lines. Load-bearing fields:
  - `timestamp` — ISO-8601 with `Z` suffix; **UTC**.
  - `isApiErrorMessage: true` marks a real API-error event; when its text
    carries "Login expired" the channel is dead. Prose elsewhere in the
    transcript that merely mentions such strings is conversation, not an error
    event — a healthy session that discussed the phrase "Login expired" was
    misread as dead until classification keyed on the structured flag
    (2026-10-04).
  - First user message: `{"type":"user","message":{"content":[...]}}`.
- mtime lies: an idle TUI keeps touching its jsonl, so a same-day mtime
  coexisted with in-file events that stopped at 03:21 (measured 2026-10-04 on
  five sessions). Liveness must read content.
- Profile config dirs that symlink `projects/` into the shared pool make
  session files reachable from any profile: session storage is effectively one
  pool. Detect this at runtime (follow the symlink) instead of assuming either
  shape — a profile's own `projects` dir may be a symlink (`ls -la` shows
  `projects -> /Users/<user>/.claude/projects/`) while another profile's is a
  real directory.

## Codex rollout layout

- Per-session file:
  `~/.codex/sessions/YYYY/MM/DD/rollout-<YYYY-MM-DDTHH-MM-SS>-<ulid>.jsonl`
  — **filename time is local; the embedded `timestamp` is UTC** (Z-suffix).
  This pairing cost one matching round-trip before it was pinned down
  (2026-10-04).
- Filename ULID ≈ creation order. `codex resume <old-id>` may keep appending to
  the original file instead of forking a new one (both behaviors observed).
- Spawned subagents create sibling files named
  `rollout-...-<child>_<parent>.jsonl` (double ULID = spawn artifact, not a
  resume fork).
- Some sessions have **no rollout file at all** while the process lives —
  resume targets whose source rollout left the default tree, plus TUIs never
  used since start. These classify `no-artifact`; restoring replays
  `codex resume <id>` and stays best-effort. Absence is not data loss by
  itself.

## Classification

- `active` / `stale`: last in-file interaction within / beyond 48h (threshold
  is one constant in `scripts/ghostty_session.py`).
- `dead-channel`: structured `isApiErrorMessage` + "Login expired" text.
  Restore reopens history; the TUI stops at `/login`. The keychain may still
  hold a refreshToken with a future expiry while the account itself refuses
  auth — the token's own clock proves nothing about the account.
- `api-error` suffix: other structured API errors in the tail.
- `no-artifact`: no session file found for the UUID.

## Misclassification war stories (why each rule exists)

1. **mtime vs content timestamps** — five sessions read "active this
   afternoon" while in-file events had stopped at 03:21; idle TUI file-touching
   caused it. Rule: liveness reads content.
2. **Prose false positive** — a healthy session that discussed the phrase
   "Login expired" was graded dead-channel; classification now keys on the
   structured flag only.
3. **argv[0] instability** — matching processes by name missed every bare-name
   process and produced two false "all sessions gone" reports in one session.
   Rule: anchor on the command-line UUID at argv-token boundaries, skipping
   companion/snapshot/daemon processes.
