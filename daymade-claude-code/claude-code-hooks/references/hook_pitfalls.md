# Hook Pitfalls — real failure modes, symptom → cause → fix

Every entry here is a bug that shipped. When a hook misbehaves, match the
**symptom** first — the cause is rarely where you'd look.

---

## 1. Hook silently allows everything (stdin consumed by heredoc)

- **Symptom:** the hook is registered, `bash -n` passes, but it never blocks —
  every case exits 0, including obvious triggers. Your test table is all-green on
  the "allow" rows and all-wrong on the "block" rows.
- **Cause:** you fed the python via `python3 - <<'PY' … PY`. That heredoc IS the
  script and consumes **stdin**, so the hook's JSON event never reaches python —
  `json.load(sys.stdin)` reads the script text, throws, and a defensive
  `except: sys.exit(0)` turns the crash into "allow everything."
- **Fix:** read stdin in bash into a var, pass it to python via an **env var**:
  ```bash
  INPUT=$(cat)
  HOOK_JSON="$INPUT" python3 - <<'PY'
  import os, json
  data = json.loads(os.environ.get("HOOK_JSON") or "{}")
  PY
  ```
  (Shipped in qlmanage-guard 2026-07-21; caught because the test table's block
  rows all read exit 0.)

---

## 2. Hook false-blocks a healthy command (awk-split ignores shell quoting)

- **Symptom:** a plain command gets blocked — e.g. `grep -E "a|TRIGGER|b" file`
  is stopped even though it only *searches* for the word, doesn't execute it.
  Often the hook's *very first real use* is a false-block.
- **Cause:** the hook split the raw command string on shell separators with awk
  (`gsub(/&&|\|\||;|\|/,"\n")`). awk doesn't understand shell quoting, so the `|`
  *inside the quoted regex* is treated as a pipe, the string splits, and
  `TRIGGER` lands at a segment head → looks like a command.
- **Fix:** parse with `shlex.split()` (quotes honored — the regex stays one
  token) and check **command position**, not mere presence. See the walker in
  [hook_patterns.md](hook_patterns.md#the-shlex-command-position-walker).
- **Why this is the worst class of bug:** *误杀健康输入比漏报更糟* — a guard that
  blocks healthy input trains the operator (human or model) to bypass it
  reflexively, and a reflexively-bypassed guard protects nothing. When choosing
  between over- and under-matching, **bias to under** (miss a rare case) rather
  than over (block a common healthy one).

---

## 3. A corrupted hook poisons the ENTIRE session

- **Symptom:** after you install/edit a hook, *unrelated* Bash calls start
  failing weirdly — output truncated or duplicated, commands that clearly ran
  reported as failed, `git log` showing commits that don't exist, `mv` "errors"
  that didn't happen. It feels like "the environment is acting up."
- **Cause:** a syntax or logic break in a **PreToolUse Bash** hook runs on
  *every* Bash call, so one broken guard corrupts the whole session's tool I/O.
  (2026-07-05: a `[^;&|]` character class broke in one edit; `;&` became a bash
  `case` fallthrough token; it poisoned half a session until `bash -n` located
  it. The tell that it's a hook and not the environment: it started right after
  you touched a hook.)
- **Fix (prevention):** never register a hook that hasn't passed **`bash -n` +
  a real-JSON end-to-end run** — "my unit test passed at deploy" is insufficient
  because the file can corrupt in a *later* edit. Prefer regex that can't
  degenerate: a `.*` inside a shlex-segmented context is safe where a
  `[^;&|]` class is not.
- **Fix (detection):** a SessionStart health check that `bash -n`s every hook and
  checks symlinks (Pattern C) surfaces this class at startup instead of after
  hours of misdiagnosis.

---

## 4. A guard the model can bypass by itself (static env escape hatch)

- **Symptom:** the guard "exists" but the banned action still happens — the model
  set an env var to wave itself through.
- **Cause:** the release valve was a static `GUARD_OK=1` / `SCOPE_OK=1` env var.
  Anything the model can add to its own command is not a gate.
- **Fix:** a **human-confirmation gate** the model physically can't drive — a
  native macOS `osascript` dialog (can't click) and/or a typed `YES` on
  `/dev/tty` (can't type into the user's terminal); refuse/cancel/timeout = hard
  NO; log every bypass. Pattern B in [hook_patterns.md](hook_patterns.md#pattern-b--pretooluse-with-a-human-confirmation-release-gate).
  (Both `WORKTREE_GUARD_OK` and `GIT_COMMIT_SCOPE_OK` were retired to this in
  2026-07.)
- **Nuance — an ack marker that's a real acknowledgement, not a free pass:** the
  subagent-scope guard accepts a `SCOPE_VERIFIED=yes` suffix, but only *after* the
  operator has gone through an AskUserQuestion authorization. The marker records
  that a human step happened; it isn't a self-serve toggle. If the marker can be
  added without any out-of-band human step, it's pitfall #4 again.

---

## 5. A guard registered in only one profile (multi-profile under-registration)

- **Symptom:** the guard works in your main profile but the mistake still happens
  in another profile (a model-switch profile, a student profile). One profile ran
  with **zero** PreToolUse guards for weeks.
- **Cause:** hooks are registered per-profile in each profile's `settings.json`.
  A hook file present in `~/.claude/hooks/` does nothing unless the *active*
  profile calls it.
- **Fix:** register in the main profile, then **converge all profiles** (this
  setup: `sync-profile-settings.py --all`, owned by `claude-switch-models-setup`).
  Add the guard's name to the SessionStart health check's registration grep so
  drift is visible.

---

## 6. A dangling symlink silently disarms a Tier-0 guard

- **Symptom:** a guard that worked for months just … stops, with no error.
- **Cause:** the hook lived only in `~/.claude/hooks/`, and a `~/.claude`
  reinstall/migration wiped it — or the symlink target moved. No signal either way.
- **Fix:** keep the **SSOT in a version-controlled dir** (`~/scripts/claude-hooks/`)
  and symlink into `~/.claude/hooks/`; recovery is one `ln -s`. The SessionStart
  health check's `[ -e "$h" ]` test (which follows the link) reports a dangling
  symlink at startup.

---

## 7. Self-block while testing a live hook

- **Symptom:** you try to test a freshly-registered guard by running a command
  containing its trigger, and your **test command itself** gets blocked.
- **Cause:** the hook is already live in the session, so any Bash command you
  issue that contains the trigger token is inspected (and blocked) before it runs.
- **Fix:** put the test cases in a **script file** and run `bash test_hook.sh` —
  the outer command (`bash test_hook.sh`) doesn't contain the trigger, so it isn't
  self-blocked; the triggers live inside the file where the PreToolUse hook
  doesn't see them. This is what `scripts/test_hook.sh` is for.

---

## Meta-principle: the ordering of these fixes

When a guard is misbehaving, check in this order — cheapest and most common first:
1. Is it **allowing everything**? → stdin/heredoc (#1) or wrong `tool_name` gate.
2. Is it **blocking a healthy command**? → awk-split / presence-not-position (#2).
3. Did **unrelated Bash calls** break right after you touched it? → corruption (#3), run `bash -n`.
4. Does the **banned action still happen**? → escape hatch (#4) or wrong profile (#5) or dead symlink (#6).
