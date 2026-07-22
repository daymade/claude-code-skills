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
- **Fix:** tokenize with the **`shlex.shlex` class** (`punctuation_chars=True`,
  `whitespace_split=True`) — NOT the `shlex.split()` function, which leaves
  `ls|TRIGGER x` as `['ls|TRIGGER', 'x']` and hides the trigger from a
  command-position check entirely. Both forms honor quotes (the regex stays one
  token); only the class also splits unspaced separators. Then check **command
  position**, not mere presence — walker in
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
- **The same trap bites your own `git commit`.** A commit message that merely
  *mentions* the trigger — e.g. a fix whose message quotes `foo|TRIGGER` as an
  example — is parsed by the live hook and blocked: the heredoc message text
  reaches the walker as if it were a command. (This skill's own qlmanage-guard
  blocked its own fix commit exactly this way.) So a real guard should **exempt
  git write segments** (`git commit` / `rebase` / `tag` / `am` / `cherry-pick`):
  a commit message legitimately contains arbitrary words, domains, and a
  `Co-Authored-By` trailer. `proxy-guard` and `git-worktree-guard` both skip these
  segments — a Bash guard that inspects command strings must do the same or it
  false-blocks your commits. (Stop-gap if the exemption isn't there yet: phrase the
  message so the trigger never lands in a command position — but add the exemption,
  don't rely on careful phrasing.)

---

## 8. `set -e` + `pipefail` silently kills a hook that promised "ALWAYS exit 0"

- **Symptom:** a PostToolUse / SessionStart hook that's supposed to never block
  reports a failure — the CLI shows only `Failed with non-blocking status code:
  No stderr output`, no error text, and the hook's own "always exit 0" contract
  is broken with **zero signal** to debug from.
- **Cause:** `set -euo pipefail` + a git (or any) **pipe** whose left side can
  fail — e.g. `git diff --cached --name-only | wc -l` in a non-repo /
  dubious-ownership / bad-`cd`-path context. pipefail propagates the left
  command's non-zero exit through the pipe, `set -e` kills the whole script, and
  the `2>/dev/null` already swallowed the stderr.
- **Fix:** every command feeding a substitution needs a `|| <fallback>` — the
  pipe included: `STAGED=$(git diff … | wc -l || echo '?')`. (2026-07-21 in
  git-commit-headcheck.)
- **Why it's insidious:** it only fires in *edge* contexts (bad path, not-a-repo),
  so it passes every test in a healthy repo and breaks in the field — same class
  as #1 (stdin) and #3 (poisoning): a promise broken, hard to locate. If your hook
  does I/O that can fail on some machines, either drop `set -e` (use `set -uo
  pipefail`) or `||`-guard every such command.

---

## 9. A literal quote or backtick inside a Python comment corrupts a hook silently

- **Symptom:** you edit a multi-line Python block embedded in the hook (the
  `python3 -c "…many lines…"` form), `bash -n` passes clean, you register the
  hook — and a specific case that should block now silently allows (or a case
  that should pass now silently blocks), with no error anywhere. Unlike #3,
  there is no syntax error and no session-wide poisoning — just one wrong
  answer in one narrow code path, which makes it far easier to miss.
- **Cause:** the whole embedded Python source is one long bash **double-quoted
  string**. Bash's parser scans that string for its own terminator (`"`) and
  for `` ` `` (legacy command substitution) and unescaped `$` — it has no
  concept of a Python `#` comment, so a literal `"` or `` ` `` typed inside
  what you intend as a harmless Python comment still ends or splices the
  outer bash string right there. The result can easily still be
  *syntactically valid* bash (the stray quote happens to pair up with another
  nearby one, just scoping a differently-shaped string than you meant) — so
  `bash -n` finds nothing wrong, and only a real end-to-end test that exercises
  the exact affected code path reveals the corruption.
  (2026-07-21, `group-name-guard.sh`: while fixing one bug, a Chinese-language
  comment explaining the fix used a literal `"` to quote an example — inside
  the very block whose job was catching literal-quote citations — and the
  regex logic after it silently stopped matching. `bash -n` passed both times
  this happened; only re-running the real JSON test suite caught it.)
- **Fix — structural (preferred):** don't use `python3 -c "…multi-line…"` at
  all for anything with room for a comment. Use a **quoted heredoc**
  (`python3 - <<'PY'` — note the quotes around `PY`) instead, passing input
  via an env var. A quoted delimiter makes the entire body inert literal text
  to bash: no quote-parsing, no `` ` `` substitution, no `$` expansion — the
  bug class becomes impossible, not just less likely. See the heredoc note in
  [hook_patterns.md](hook_patterns.md#json-event-contract) and
  [Pattern E](hook_patterns.md#pattern-e--stop-hook-react-to-claudes-own-output)
  for the full working shape.
- **Fix — if you're stuck with `-c "…"`:** every literal `"` and `` ` `` in
  the embedded source — code AND comments — must be backslash-escaped
  (`\"`, `` \` ``); for CJK prose comments, prefer corner brackets `「」` or
  book-title marks `《》` over straight quotes — they read naturally in
  Chinese and aren't bash-special, so there's nothing to remember to escape.
  Before registering, audit the embedded span directly rather than trusting a
  visual read: `awk 'NR==<start>,NR==<end>' hook.sh | grep -n '"\|`'` (and
  `grep -nF '$'` for stray dollar signs) — a clean grep on the exact span is
  stronger evidence than "I re-read it and it looked fine," which is
  precisely the check that failed twice in the incident above.

---

## 10. A path parsed from command text keeps its literal `~` — guard fails **open**

**Symptom.** The guard never fires for commands that `cd` somewhere first. No error,
no log line, no misbehavior you can see — it just silently allows. In the case that
surfaced it, two sibling hooks shared one parsing helper and degraded *differently*:
a PostToolUse context-injector kept emitting its own fallback string
(`"cannot read HEAD — not a git repo or bad path"`) for weeks, which everyone read as
"that hook is noisy again"; the PreToolUse scope guard beside it gave **no signal at
all** — it simply stopped guarding. Same root cause, one visible-but-dismissed
symptom and one invisible.

**Cause.** Tilde expansion is done by the **shell**, before a command ever runs. A
hook that determines its target by *parsing the command text* (`cd X && git commit`,
`git -C X commit`) never goes through a shell, so it receives the literal string
`~/repo`. Then:

```bash
git -C "~/repo" log -1        # fatal: cannot change to '~/repo': No such file or directory
git -C "~/repo" diff --cached --name-only   # → empty, exit non-zero, swallowed by 2>/dev/null
```

The headcheck degraded to a visible-but-ignorable message. The scope guard did
something worse: empty staged list → "zero files, so zero cross-domain files" →
**allow**. Rule 5's failure direction, in the wild.

**Fix.** Expand in the parser, once, at the shared source. (The helper here is a `.sh` file whose parsing core is an embedded `python3` block — Pattern A's shape — so the fix is Python even though the file is shell:)

```python
repo_dir = os.path.expanduser(repo_dir) if repo_dir else repo_dir
```

`expanduser` is the identity function for anything not starting with `~`, and
`expanduser('') == ''` — so the `if repo_dir else` guard above is belt-and-braces, not
required; `repo_dir = os.path.expanduser(repo_dir)` alone is correct. Keep whichever
reads better in your parser; the load-bearing part is that the expansion happens
**inside the parser**, so every caller inherits it.

**The shared-library twist — this is the part that bites twice.** The parser was a
common helper (`lib-git-commit-detect.sh`) used by three hooks. Fixing it fixed all
three at once, which is why the SSOT structure is right — but it also means
**"I verified the fix" must mean "I verified every caller."** In the real incident
the author fixed the library, verified two callers (a commit-form guard and the PostToolUse context-injector),
declared it done — and the *third* caller, the scope guard, went unverified. It was
both the one that fails open and the only one of the three that actually blocks. It
took the user asking "so did you fix it?" for the gap to surface. When you patch a
shared helper, enumerate its callers (`grep -l '<lib-name>' *.sh`) and put every one
of them in the test table.

**Generalization (not git-specific).** Any hook that reconstructs state by *reading
the command instead of running it* inherits the whole class: `~` unexpanded, `$VARS`
uninterpolated, `$(cmd)` unexecuted, globs unmatched, relative paths resolved against
the wrong cwd. If your hook takes a path out of command text and hands it to a real
command, expand what the shell would have expanded — or decide, per rule 5, that an
unresolvable path means **block**.

## Meta-principle: the ordering of these fixes

When a guard is misbehaving, check in this order — cheapest and most common first:
1. Is it **allowing everything**? → stdin/heredoc (#1) or wrong `tool_name` gate.
2. Is it **blocking a healthy command**? → awk-split / presence-not-position (#2).
3. Did **unrelated Bash calls** break right after you touched it? → corruption (#3), run `bash -n`.
4. Does the **banned action still happen**? → escape hatch (#4) or wrong profile (#5) or dead symlink (#6).
5. Is `bash -n` clean but **one specific case still gives the wrong answer**
   (and you recently edited an embedded `python3 -c "…"` block, code or
   comments)? → quote/backtick corruption (#9) — `bash -n` cannot see this one,
   only a real-JSON test of that exact case will.
6. Does it work when you run the command **in place**, but never fire when the
   command `cd`s somewhere first (or uses `~`, a variable, a glob)? → the guard is
   parsing command text and got an unexpanded string (#10). Note this one has **no
   symptom of its own** when the hook fails open — you find it by testing the
   `cd ~/elsewhere && …` shape explicitly, not by waiting for something to look wrong.
