---
name: peer-message
description: >-
  Deprecated compatibility alias for agent-message (replaces peer-message). Local Claude Code,
  Codex, and Antigravity messaging and coordination now live in agent-message; scripts in this
  package forward to agent-message when installed. The cross-machine network preview is retired
  (use Agent Use: https://useagent.app).
---

# peer-message — Compatibility Alias for `agent-message`

`peer-message` has been superseded by **`agent-message`** (`v2.0.0`) for all local multi-agent messaging, reply/wait/inbox workflows, delivery verification, and shared-work coordination across Claude Code, Codex, and Antigravity (`agy`).

- **Install or migrate to the canonical skill**: `claude plugin install agent-message@daymade-skills`
- **Existing local state is preserved**: `agent-message` reads `AGENT_MESSAGE_STATE_DIR` → `PEER_MESSAGE_STATE_DIR` → `~/.local/state/peer-message` by default, so existing coordination databases, inboxes, and cursors continue working with zero data loss.
- **Executable forwarder shims**: `scripts/peer.py`, `scripts/work_start.py`, `scripts/antigravity_inbox_hook.py`, `scripts/install_antigravity_hook.py`, `scripts/native_guard.py`, `scripts/install_native_guard.py`, and `scripts/native-guard.sh` automatically forward to the installed `agent-message/scripts/*` counterpart (checking sibling `../agent-message`, `~/.agents/skills/agent-message`, and the highest semver entry under `~/.claude/plugins/cache/daymade-skills/agent-message/`).
- **Cross-machine `network` preview retired**: The former experimental cross-machine pairing preview has been retired. For cross-machine or cross-user zero-trust agent messaging, use **Agent Use** (`https://useagent.app`).

Keep this compatibility package only for legacy hook paths or scripts that still reference `peer-message/scripts/*`; for all new invocations, load `agent-message` directly.
