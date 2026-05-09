# Troubleshooting Decision Tree

When the statusline misbehaves, run the health check first — it covers most issues:

```bash
bash scripts/health_check.sh
```

If the health check passes but you still see an issue, walk the symptoms below.

---

## Symptom 1: Statusline is blank or never updates

**Most common root cause: the script is not executable.** Claude Code runs the
configured `command` and silently shows nothing if the exec fails. This is the
single biggest source of "I configured it but nothing happens" reports.

**Diagnose:**
```bash
ls -la "$(jq -r '.statusLine.command' ~/.claude/settings.json | sed "s|^~|$HOME|; s|^bash ||")"
```

Look at the leftmost column. If it does not start with `-rwx`, the script is
missing its executable bit.

**Fix:**
```bash
chmod +x ~/.claude/statusline.sh
```

(Substitute the actual path from your `settings.json`.)

**Other possible causes:**
- `settings.json` `statusLine.command` points to a path that no longer exists.
  Run `bash scripts/health_check.sh` to confirm.
- The script's shebang references an interpreter that's not installed. Verify
  with `head -1 ~/.claude/statusline.sh` — should be `#!/usr/bin/env bash` or
  similar.
- The script writes to stderr instead of stdout. Claude Code only displays
  stdout. Pipe a mock stdin and inspect: `echo '{}' | ~/.claude/statusline.sh`.

---

## Symptom 2: `ctx: ...` segment is missing or shows wrong numbers

**Root cause A: `used_percentage` is `null` early in a session.**

The Claude Code docs explicitly warn that `context_window.used_percentage` and
`remaining_percentage` "may be `null` early in the session." If your script
gates the ctx segment on these fields, the segment vanishes until the first
real API response populates them. A naive `// empty` filter swallows the
output entirely.

**Fix:** This skill's `generate_statusline.sh` computes used tokens from
`current_usage.input_tokens + cache_read_input_tokens + cache_creation_input_tokens`,
which is `0` (not null) at session start, so the ctx segment renders even
before any real usage.

**Root cause B: confusing `total_input_tokens` with current context.**

In Claude Code v2.1.131 and earlier, `total_input_tokens` was a session-cumulative
count and could exceed `context_window_size`. Using it as "current usage"
shows percentages above 100% in long sessions.

**Fix:** Use `current_usage.*` summed (this skill's default). It always
reflects the current context state regardless of Claude Code version.

**Root cause C: `context_window_size` missing from JSON.**

Some early versions or non-standard clients omit this field. The script then
divides by zero (or skips the segment).

**Diagnose:**
```bash
export CLAUDE_STATUSLINE_DEBUG=1
# Send any message in Claude Code, then:
jq '.context_window' /tmp/.claude-statusline-last-stdin.json
```

If `context_window_size` is missing, your Claude Code is too old or running
a non-standard runtime. Update Claude Code.

---

## Symptom 3: I want token counts, not percentages

The default layout shows `ctx: 108K / 1M` (token counts only). If yours shows
percentages, you are running the `full` layout.

**Switch to minimal:**

Remove this from your shell rc file:
```bash
export CLAUDE_STATUSLINE_LAYOUT=full
```

Or set it explicitly to minimal:
```bash
export CLAUDE_STATUSLINE_LAYOUT=minimal
```

Then start a new shell so Claude Code inherits the new env.

---

## Symptom 4: Colors look wrong or render as literal escape codes

**Diagnose:**
```bash
echo '{"workspace":{"current_dir":"/tmp"},"model":{"display_name":"M"},"context_window":{"context_window_size":100000,"used_percentage":80,"current_usage":{"input_tokens":80000,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}' | \
  CLAUDE_STATUSLINE_LAYOUT=full ~/.claude/statusline.sh | cat -v
```

If you see `^[[01;33m` instead of yellow text, your terminal is not
interpreting ANSI escape codes.

**Fix:**
- Most modern terminals (iTerm2, Apple Terminal, Kitty, Windows Terminal,
  WezTerm) support these by default. If yours doesn't, switch terminal.
- Claude Code itself renders the statusline output and supports ANSI colors,
  so this issue is rare during actual use — only shows up when you pipe
  the script manually.

---

## Symptom 5: Git status segment is missing (full layout)

**Root cause A:** You're not inside a git repository. Expected — git segment
is silent outside repos.

**Root cause B:** `git` binary not installed.

**Diagnose:**
```bash
command -v git || echo "git not installed"
git -C "$PWD" rev-parse --git-dir 2>&1
```

**Fix:** Install git, or accept that the segment is hidden.

**Root cause C:** Permission errors reading `.git/`.

```bash
ls -la "$(git rev-parse --git-dir 2>/dev/null)" 2>&1 | head -3
```

---

## Symptom 6: Cost segment is missing (full layout)

The cost segment depends on `ccusage` being installed and on PATH. It runs
asynchronously with a 2-minute cache, so the first display after install is
expected to lack it; the cache populates within 5–10 seconds.

**Diagnose:**
```bash
command -v ccusage || echo "ccusage not installed"
ccusage session --json --offline -o desc 2>&1 | head -20
ls -lh /tmp/claude_cost_cache_*.txt 2>/dev/null
```

**Fix:**
- Install `ccusage`: `npm install -g ccusage` (or see the `ccusage` repo for
  current install instructions).
- Wait for the background fetch on first use.
- Force refresh: `rm /tmp/claude_cost_cache_*.txt` then trigger a statusline
  update by sending any message in Claude Code.

For deeper details and offline data structure, see
[`ccusage_integration.md`](ccusage_integration.md).

---

## Symptom 7: I edited the script but my changes have no effect

Claude Code reads the script every refresh, so live edits **should** take
effect on the next statusline update (typically the next assistant message).

**Diagnose:**
```bash
# Confirm Claude Code actually runs your edited script:
export CLAUDE_STATUSLINE_DEBUG=1
# Then send a message in Claude Code and check the dump:
ls -la /tmp/.claude-statusline-last-stdin.json
```

If the dump's mtime updates after your message, the script is being executed.
If your edits still have no effect, try `bash health_check.sh` to confirm the
script being run is actually the one you edited (it might be a stale copy at
a different path).

**Possible mismatch:** `settings.json` `statusLine.command` points to one path,
but you edited a different file. The health check warns when these diverge.

---

## Symptom 8: Script is slow (statusline appears with delay)

**Diagnose:**
```bash
time (echo '{"workspace":{"current_dir":"/tmp"},"model":{"display_name":"M"},"context_window":{"context_window_size":1000,"current_usage":{"input_tokens":0,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}' | ~/.claude/statusline.sh)
```

Should be well under 100ms. If much slower, suspect:

- **`ccusage` blocking:** Should be backgrounded by the script. Verify with
  `time ccusage session --json --offline -o desc | head -1`.
- **`git` slow on a large repo:** Switch to minimal layout to skip git lookup.
- **`python3` fallback hot path:** Install `jq` (`brew install jq`).

---

## When all else fails

Capture both real stdin and the script's actual output, then re-run health check:

```bash
export CLAUDE_STATUSLINE_DEBUG=1
# Send a message in Claude Code, wait 1 second, then:
bash scripts/health_check.sh
echo "---"
echo "Real stdin Claude Code sent:"
jq . /tmp/.claude-statusline-last-stdin.json
echo "---"
echo "Script output for that stdin:"
cat /tmp/.claude-statusline-last-stdin.json | ~/.claude/statusline.sh
```

The combination of `health_check.sh` results plus the captured stdin/output
pair is enough evidence to diagnose virtually any issue.
