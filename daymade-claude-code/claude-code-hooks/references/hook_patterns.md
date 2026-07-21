# Hook Patterns — runnable skeletons

Battle-tested shapes plus the shlex command-position walker. Every snippet
here is distilled from a hook that has run in production. Copy, rename the
TRIGGER, keep the structure.

## Table of contents
1. [JSON event contract](#json-event-contract)
2. [Pattern A — PreToolUse block](#pattern-a--pretooluse-block)
3. [The shlex command-position walker](#the-shlex-command-position-walker)
4. [Pattern B — PreToolUse with a human-confirmation release gate](#pattern-b--pretooluse-with-a-human-confirmation-release-gate)
5. [Pattern C — SessionStart health check](#pattern-c--sessionstart-health-check)
6. [Pattern D — PostToolUse context injection](#pattern-d--posttooluse-context-injection)
7. [Pattern E — Stop hook: react to Claude's own output](#pattern-e--stop-hook-react-to-claudes-own-output)
8. [Registration](#registration)

---

## JSON event contract

The hook reads one JSON object on **stdin**. The fields you care about:

```jsonc
// PreToolUse / PostToolUse
{
  "tool_name": "Bash",                       // or "Agent", "WebFetch", "Edit", …
  "tool_input": { "command": "…" }           // Bash: .command; Agent: .prompt; Edit: .file_path/.new_string
}
```

Extract them defensively (never assume the shape — a parse failure should
**allow**, not crash):

```bash
INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null||echo "")
CMD=$(printf '%s' "$INPUT"  | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null||echo "")
```

**Exit codes:** `0` = allow / proceed; `2` = block (PreToolUse) — stderr is shown
to the model; anything else = non-blocking error. SessionStart must always exit 0.

**stdin is single-use.** If you delegate logic to python, do NOT feed the script
via `python3 - <<'PY'` — that heredoc IS the script and consumes stdin, so
`json.load(sys.stdin)` reads the *script text*, fails, and (with a defensive
`except: exit 0`) the hook silently allows **everything**. Read stdin in bash
into a var, pass it to python via an **env var**:

```bash
INPUT=$(cat)
HOOK_JSON="$INPUT" python3 - <<'PY'
import os, json
data = json.loads(os.environ.get("HOOK_JSON") or "{}")
PY
```

**This form has a second benefit beyond fixing stdin consumption: a QUOTED
heredoc delimiter (`<<'PY'`, not `<<PY`) makes the whole body inert literal
text to bash** — no variable expansion, no command substitution, no
quote-parsing. Compare that to the also-common `python3 -c "…multi-line…"`
form, where the embedded Python is still subject to bash's own double-quote
parsing: a single stray `"` or `` ` `` **anywhere** inside — including inside
what looks like a harmless Python `#` comment, since bash has no idea it's a
comment — silently truncates or splices the outer string. Prefer the quoted
heredoc for any multi-line embedded Python; reserve `python3 -c "…"` for
one-liners with no room for a comment to hide a stray character in. Full
failure mode and why `bash -n` doesn't reliably catch it:
[hook_pitfalls.md](hook_pitfalls.md#9-a-literal-quote-or-backtick-inside-a-python-comment-corrupts-a-hook-silently).

**Not every hook guards Bash — pick the match technique from the input's TYPE.**
An `Agent` matcher's `tool_input.prompt` is **free natural-language text**, not a
shell command, so the shlex command-position walker below is meaningless for it —
match with a plain substring (`grep -qF`) on the keywords you're guarding. (The
subagent-scope guard does exactly this: it greps a subagent's prompt for
scope-creep keywords and blocks unless an out-of-band human-authorization marker
is present.) The rule: **shlex is for shell commands; free-text tool inputs
(`Agent`.prompt, an `Edit`.new_string) use substring/keyword matching.** Applying
the shlex walker to natural language is a category error.

---

## Pattern A — PreToolUse block

The workhorse: inspect a Bash command, block if it does the banned thing. This is
the shape of `qlmanage-guard`. (`proxy-guard` predates the shlex walker and still
awk-splits the raw string — the very approach pitfall #2 warns against; it's a
migration candidate, not a model to copy.)

```bash
#!/usr/bin/env bash
# PreToolUse hook: block <BANNED THING>.
# WHY: <one line — why prose couldn't hold this>.
# SSOT: ~/scripts/claude-hooks/<name>.sh, symlinked to ~/.claude/hooks/<name>.sh
set -euo pipefail
INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null||echo "")
[ "$TOOL" != "Bash" ] && exit 0
CMD=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null||echo "")
[ -z "$CMD" ] && exit 0
printf '%s' "$CMD" | grep -qw 'TRIGGER' || exit 0     # fast path: token absent → allow

# Precise detection AND the guidance message BOTH live inside python — so `set -e`
# can't swallow the message. If the BLOCKED text sat in a SECOND bash step after
# the heredoc (`rc=$?; if [ "$rc" = 2 ]…`), `set -e` would kill the script the
# instant python exits 2, and you'd get a bare exit 2 with ZERO guidance — a real
# bug (SKILL.md's whole point is that stderr IS the message the model sees). One
# process: print, then exit.
HOOK_CMD="$CMD" python3 - <<'PY'
import os, sys, shlex, re
cmd = os.environ["HOOK_CMD"]
def toks(c):
    lex = shlex.shlex(c, posix=True, punctuation_chars=True); lex.whitespace_split = True
    return list(lex)                       # |;&<>() are boundaries even without spaces
try: TS = toks(cmd)
except ValueError: TS = cmd.split()        # unbalanced quotes → best effort (SKILL.md Rule 1 nuance)
SEPS = {";","&&","||","|","&","(",")","{","}","|&"}   # NOT <> — a redirect target is a filename, not a command
ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
at_cmd = True
for t in TS:
    if t in SEPS: at_cmd = True; continue
    if at_cmd:
        if ENV.match(t): continue          # VAR=val prefix, command is still ahead
        if t == "TRIGGER":                 # command-position hit → print guidance + block
            sys.stderr.write("BLOCKED: <BANNED THING> is not allowed here.\n"
                             "WHY: <the failure mode this prevents>.\n"
                             "USE INSTEAD: <the correct command / workflow>.\n")
            sys.exit(2)
        at_cmd = False                     # this token is the command; rest are args
sys.exit(0)
PY
# set -e propagates python's exit 2 straight out of the hook — nothing left for
# bash to do, and nothing for set -e to swallow (the message already printed).
```

Note the two-stage match: a cheap `grep -qw` fast-path (allow immediately if the
token is entirely absent), then the precise shlex walker only when it's present.

---

## The shlex command-position walker

The single most important idea. It answers "does this command **execute**
TRIGGER" — not "does the string contain TRIGGER". Handles quotes, pipes, env
prefixes, and compound commands correctly.

```python
import shlex, re
# NOTE: `<` and `>` are deliberately NOT in SEPS. A redirect target is a
# FILENAME, not a command — `echo x > qlmanage` writes a file named qlmanage, it
# doesn't run it, so treating `>` as a command separator would false-block it
# (误杀健康输入比漏报更糟). `|;&` still catch `ls|qlmanage` via punctuation_chars.
SEPS = {";", "&&", "||", "|", "&", "(", ")", "{", "}", "|&"}
ENV  = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

def _tokens(cmd: str):
    # CRITICAL: use the shlex.shlex CLASS with punctuation_chars=True, NOT the
    # plain shlex.split() function. split() does not treat |;&<>() as token
    # boundaries unless they're space-separated, so `ls|TRIGGER x` (no spaces —
    # which bash accepts) tokenizes as one word 'ls|TRIGGER' and slips past the
    # SEPS check entirely. punctuation_chars=True makes them boundaries even
    # without surrounding spaces; whitespace_split=True keeps flags/paths whole.
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)

def executes(cmd: str, target: str) -> bool:
    try: toks = _tokens(cmd)             # quotes honored, # comment dropped, |;& are boundaries
    except ValueError: toks = cmd.split()# unbalanced quotes → best effort (see SKILL.md Rule 1 nuance)
    at_cmd = True                        # start of line is a command slot
    for t in toks:
        if t in SEPS: at_cmd = True; continue   # separator → next token is a command
        if at_cmd:
            if ENV.match(t): continue           # skip VAR=val prefixes
            if t == target: return True         # command-position match
            at_cmd = False                      # this is the command; args follow
    return False
```

Why each piece matters:
- The shlex CLASS keeps a quoted `"a|TRIGGER|b"` as ONE token → a regex arg to
  `grep`/`sed` is never mistaken for a command. This is the whole reason not to
  awk-split the raw string.
- `punctuation_chars=True` makes `|;&<>()` token boundaries **even with no
  surrounding space**, so `ls|TRIGGER x` is caught (plain `shlex.split()` would
  miss it — a real, silent bypass). `whitespace_split=True` stops it from also
  splitting inside flags/paths.
- Comments (`# TRIGGER`) are dropped by the posix lexer, so they don't match.
- The `at_cmd` flag + `SEPS` means `ls | TRIGGER x` matches (after the pipe) but
  `grep TRIGGER f` does not (TRIGGER is grep's argument).
- `ENV` skip means `FOO=1 TRIGGER` matches (TRIGGER is still the command).

**What it deliberately does NOT catch:** `$(TRIGGER)` / backtick command
substitution. A raw-string regex for `$(TRIGGER` would misfire on a *quoted*
literal `'$(TRIGGER)'` (which doesn't execute). Since the real use of most
banned commands is a direct call, missing the rare substitution case beats
false-positives. If you truly need it, detect it in a context that distinguishes
single- from double-quotes — usually not worth it.

---

## Pattern B — PreToolUse with a human-confirmation release gate

For an irreversible action you want to *allow with explicit human consent*, never
a static env var (the model can set env vars). This is `git-worktree-guard` /
`git-commit-scope-guard`. Two channels the model physically cannot drive:

```bash
# ... detection decided this action needs confirmation ...
BYPASS_LOG="${HOME}/.hook-bypass.log"
stamp() { printf '%s\t%s\t%s\n' "$(date '+%F %T')" "$1" "${CMD:0:80}" >> "$BYPASS_LOG"; }

# Channel 1: native macOS dialog — the model cannot click a button.
if command -v osascript >/dev/null 2>&1; then
  DLG_BODY="display dialog \"Allow <ACTION>?\n\n$CMD\" buttons {\"拒绝\",\"允许\"} default button \"拒绝\" cancel button \"拒绝\" with icon stop giving up after 40 with title \"my-guard\""
  # CRITICAL: attach the dialog to the FRONTMOST app (the terminal the user is
  # looking at) so it pops up *in front of them*. A bare `osascript -e "$DLG"`
  # opens on some other desktop/Space in fullscreen setups — the user never sees
  # it, it times out at 40s, and the log misreads "declined" (a real 2026-07-21
  # bug this exact snippet used to have). Fall back to the bare form only on a
  # NON-cancel error (some frontmost apps don't support `tell`).
  ERR=$(mktemp); DLG=""
  if DLG=$(osascript -e "tell application (path to frontmost application as text) to $DLG_BODY" 2>"$ERR"); then :
  elif ! grep -qiE 'user canceled|-128' "$ERR"; then DLG=$(osascript -e "$DLG_BODY" 2>"$ERR") || true
  fi
  if printf '%s' "$DLG" | grep -q 'button returned:允许'; then
    stamp "gui-allow"; rm -f "$ERR"; exit 0
  fi
  # Refusal / cancel / timeout = HARD NO — never fall through to a second channel
  # that could override it. Distinguish timeout from a real decline: at debug time
  # they mean completely different things (was the dialog even seen?).
  if printf '%s' "$DLG" | grep -q 'gave up:true'; then stamp "gui-timeout"; else stamp "gui-declined"; fi
  rm -f "$ERR"; echo "BLOCKED: <ACTION> not confirmed (declined / cancelled / timed out)." >&2; exit 2
fi

# Channel 2 (reached ONLY if there's no GUI session at all): typed YES on the
# user's terminal — the model cannot type there.
if [ -r /dev/tty ] && [ -w /dev/tty ] && (exec 3<>/dev/tty) 2>/dev/null; then
  # The probe is INSIDE the `if` condition (exempt from set -e) — critical,
  # because in sandboxed/subagent contexts /dev/tty can exist and pass -r/-w yet
  # fail to open ("Device not configured"). A bare `printf > /dev/tty` there would
  # fail, set -e would abort with exit 1 = "non-blocking error" = ALLOW — the
  # confirmation gate silently opening exactly when no human can confirm. Guard the
  # body I/O too so a mid-read failure can't do the same.
  printf 'Allow <ACTION>? type YES to proceed: ' > /dev/tty 2>/dev/null || true
  read -r ANS < /dev/tty 2>/dev/null || ANS=""
  [ "$ANS" = "YES" ] && { stamp "tty-allow"; exit 0; }
fi
stamp "blocked"; echo "BLOCKED: <ACTION> requires human confirmation." >&2; exit 2
```

Rules that make this a real gate: **refuse / cancel / timeout = hard NO**, and a
denial on one channel must **not** be overridable by a second channel — note the
GUI branch `exit`s on refusal and only a *no-GUI-at-all* failure reaches the tty
channel. Distinguish **timeout** (`gave up:true` — the dialog may never have been
seen) from a real **decline** in the log; conflating them makes a "why did it
block?" investigation impossible. Log every prompt and outcome — reflexive bypass
is the guards' one collective failure mode, so the audit trail is what keeps it
honest. (Retired anti-pattern: a static `GUARD_OK=1` env var — the model just adds
it. Any gate the model can satisfy by itself is not a gate.)

---

## Pattern C — SessionStart health check

The guards are their own failure domain: a corrupted hook, a dangling symlink
after reinstall, or a profile that never registered the guard all disable
protection with zero signal. This is `hook-health-check` — **silent when healthy,
always exit 0**.

```bash
#!/usr/bin/env bash
# SessionStart hook: verify the guard rails THEMSELVES are alive.
# Contract: SILENT when healthy; warn to stderr on breakage; ALWAYS exit 0
# (a broken health check must never block session start — 误杀 > 漏报).
set -uo pipefail
PROBLEMS=()

# 1. Every installed hook parses and its symlink resolves.
for h in "$HOME"/.claude/hooks/*.sh; do
  [ -e "$h" ] || { PROBLEMS+=("dangling symlink: $h"); continue; }   # -e follows the link
  bash -n "$h" 2>/dev/null || PROBLEMS+=("syntax error: $h")
done
# 2. The ACTIVE profile actually registers the Tier-0 guards.
SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
for g in proxy-guard git-worktree-guard <your-tier0-guards>; do
  grep -q "$g" "$SETTINGS" 2>/dev/null || PROBLEMS+=("not registered in $SETTINGS: $g.sh")
done

if [ "${#PROBLEMS[@]}" -gt 0 ]; then
  { printf '⚠️  hook-health-check: %d problem(s):\n' "${#PROBLEMS[@]}"
    printf '    - %s\n' "${PROBLEMS[@]}"; } >&2
fi
exit 0
```

Register once per profile under `SessionStart`. It's how the 2026-07-05 poisoning
class ("environment acting up" that was really a broken hook) becomes visible at
startup instead of after hours of confusion.

---

## Pattern D — PostToolUse context injection

PostToolUse can't undo a tool call, but it can make the **truth** appear so a
later hallucination can't stand. This is `git-commit-headcheck`: after any real
`git commit`, independently re-read HEAD and inject it.

```bash
#!/usr/bin/env bash
# PostToolUse (matcher: Bash): after a real `git commit`, inject the true HEAD.
set -euo pipefail
INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null||echo "")
printf '%s' "$CMD" | grep -qE '(^|[^[:alnum:]])git[[:space:]].*commit([[:space:]]|$)' || exit 0
printf '%s' "$CMD" | grep -q -- '--dry-run' && exit 0
# This skeleton reads the HOOK PROCESS's own cwd — correct for a plain `git
# commit`. But if the command targets another repo (`git -C <dir> commit`, or
# `cd <dir> && git commit`), this reads the WRONG repo and injects a bogus HEAD
# *as if it were truth* — the exact failure this pattern exists to prevent. A
# real hook must extract the `-C`/`cd` target from $CMD (sed) and run
# `git -C "$dir" …`; kept minimal here on purpose.
# CRITICAL with `set -euo pipefail`: a git PIPE is a trap. If git fails (not a
# repo / dubious ownership / bad `cd`-path), pipefail propagates git's exit code,
# `set -e` kills the WHOLE script, and this hook's "ALWAYS exit 0" promise breaks
# SILENTLY — the CLI shows only "Failed with non-blocking status code: No stderr
# output" (a real 2026-07-21 bug). EVERY git command feeding output MUST have a
# `|| <fallback>`, including the pipe.
HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
SUBJ=$(git log -1 --format='%s' 2>/dev/null || echo "?")
STAGED=$(git diff --cached --name-only 2>/dev/null | wc -l | tr -d ' ' || echo '?')
echo "[headcheck] real HEAD = $HEAD $SUBJ | staged remaining = $STAGED" >&2
exit 0
```

The value is that the model **cannot forget a check that runs automatically**.
Injected truth beats "I think the commit worked."

---

## Pattern E — Stop hook: react to Claude's own output

The only pattern here that inspects the **model's own generated text**, not a
tool call or a file. Use it for a rule about what the model itself *writes* —
"never invent a shorthand name for something unverified", "always cite a
source" — never for a rule about what the model writes **into** a file or a
shell command (that's PreToolUse on `Write`/`Edit`/`Bash` instead; Stop only
sees plain chat text). Getting the event wrong here isn't a tuning problem —
`UserPromptSubmit` structurally cannot see the model's own text, so a hook
built on it will never once fire for what it was built to catch, while still
false-blocking the user's own unrelated typing whenever it happens to contain
the trigger pattern (a real, shipped incident).

```bash
#!/usr/bin/env bash
# Stop hook: block the model from ending its turn if its own last reply
# contains <BANNED PATTERN>.
set -uo pipefail                                # no -e: every risky step below
INPUT=$(cat)                                     # is explicitly ||-guarded instead

# Anti-loop, and the field this pattern is most likely to get wrong: compare
# by IDENTITY to the JSON boolean, not by Python truthiness. `bool("false")`
# is True (any non-empty string is truthy) — if stop_hook_active ever arrives
# as the JSON *string* "false" instead of the boolean, a naive `bool(...)`
# check treats it as an already-blocked retry and silently, permanently
# disarms the guard for that turn. Test this explicitly: a payload with
# `"stop_hook_active": "false"` (string) must NOT be treated as active.
ACTIVE=$(HOOK_JSON="$INPUT" python3 - <<'PY'
import json, os
print(json.loads(os.environ['HOOK_JSON']).get('stop_hook_active') is True)
PY
) 2>/dev/null || exit 0
[ "$ACTIVE" = "True" ] && exit 0

# Prefer last_assistant_message (official docs: use it INSTEAD OF the
# transcript — transcript_path is written asynchronously and may not yet
# include the current turn's newest message when Stop fires). Its documented
# shape is a plain string, but defensive extraction costs nothing and the
# SAME helper is genuinely required for the transcript fallback below, where
# message.content really is a list of typed blocks in practice.
TEXT=$(HOOK_JSON="$INPUT" python3 - <<'PY'
import json, os, sys

d = json.loads(os.environ['HOOK_JSON'])

def extract_text(node):
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return ' '.join(
            b['text'] for b in node
            if isinstance(b, dict) and b.get('type') == 'text'   # skip thinking/tool_use
        )
    if isinstance(node, dict) and 'content' in node:
        return extract_text(node['content'])
    return ''

text = extract_text(d.get('last_assistant_message'))

if not text:
    tp = d.get('transcript_path', '')
    try:
        with open(tp, 'rb') as f:
            tail = f.read().splitlines()[-80:]      # tail only — a long session's
        for line in reversed(tail):                  # transcript can be 100s of MB;
            try:                                      # a bounded backward chunked
                obj = json.loads(line)                 # read scales this to O(80
            except Exception:                          # lines) instead of O(file size)
                continue
            if not isinstance(obj, dict):             # a syntactically-valid but
                continue                                # non-dict line (rare) must
            if obj.get('type') == 'assistant':          # NOT abort the whole scan via
                t = extract_text(obj.get('message', {}).get('content'))  # an uncaught
                if t:                                   # AttributeError on .get() —
                    text = t                            # that would silently discard
                    break                                # an older, still-unscanned
    except Exception:                                    # line that has the violation
        text = ''

print(text)
PY
) 2>/dev/null || exit 0
[ -n "$TEXT" ] || exit 0

printf '%s' "$TEXT" | grep -qw 'TRIGGER' || exit 0    # fast path, same idea as Pattern A —
# but NOT the shlex walker below this line: TEXT is free-form prose, not a
# shell command, so match with substring/regex per the JSON event contract's
# "shlex is for shell commands" rule above.
HIT=$(HOOK_TEXT="$TEXT" python3 - <<'PY'
import os, re
t = os.environ['HOOK_TEXT']
# ... precise detection here — regex/substring over free text ...
for m in re.finditer(r'TRIGGER', t):
    print(m.group(0))
    break
PY
) 2>/dev/null || HIT=''

if [ -n "$HIT" ]; then
  # This message is read by the MODEL, not the user — once Stop blocks, the
  # model sees this text and must act on it before it can actually stop.
  # Write it as an instruction ("rewrite X"), not a user-facing explanation.
  echo "BLOCKED: your last reply contains <BANNED THING> (\"$HIT\"). WHY: ...
FIX: rewrite it using <the correct alternative>, then finish this turn." >&2
  exit 2
fi
exit 0
```

Three things worth calling out beyond what the comments above already say:

- **This skeleton uses `python3 - <<'PY' ... PY` (a QUOTED heredoc) everywhere,
  never `python3 -c "…multi-line…"`.** With a quoted delimiter, bash treats
  the entire body as inert literal text — no variable expansion, no command
  substitution, no quote-parsing at all — so a stray `"` or `` ` `` **inside a
  comment** (which is exactly where one tends to sneak in unnoticed, since
  bash doesn't know it's "just a comment" the way Python does) cannot corrupt
  anything. This is the same technique the JSON event contract section above
  uses to avoid the stdin-consumption trap, and it happens to close the
  quote-embedding hazard too — see
  [hook_pitfalls.md](hook_pitfalls.md#9-a-literal-quote-or-backtick-inside-a-python-comment-corrupts-a-hook-silently)
  for what goes wrong with the `-c "…"` form instead, and why `bash -n` alone
  doesn't always catch it.
- **`stop_hook_active` is the single most safety-critical field in this
  pattern.** Every other mistake in this hook fails toward "block too much" or
  "miss one case"; getting this one wrong in the permissive direction fails
  toward "silently do nothing, forever, with zero error signal."
- **Wrap every python3 subprocess call in the same `2>/dev/null || <fallback>`
  pattern, not just some of them.** An inconsistency here doesn't change the
  block-vs-allow decision (a hook built this defensively is already fail-open
  by construction — nothing prints before a match succeeds), but the
  unguarded call leaks a raw Python traceback straight to the model's stderr
  on any internal crash, instead of degrading cleanly to "no match" like the
  guarded calls do.

---

## Registration

`settings.json` groups hooks by event, then by `matcher` (the tool name):

```jsonc
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [
        { "type": "command", "command": "~/.claude/hooks/my-guard.sh" }
      ]},
      { "matcher": "Agent", "hooks": [ /* scope guards on subagent prompts */ ] }
    ],
    "PostToolUse":  [ { "matcher": "Bash", "hooks": [ { "type": "command", "command": "~/.claude/hooks/headcheck.sh" } ] } ],
    "SessionStart": [ { "hooks": [ { "type": "command", "command": "~/.claude/hooks/hook-health-check.sh" } ] } ],
    "Stop":         [ { "hooks": [ { "type": "command", "command": "~/.claude/hooks/my-stop-guard.sh" } ] } ]
  }
}
```

Note `Stop` (like `SessionStart`) has no `matcher` key — it isn't scoped to a
tool, so its `hooks` array sits directly under the event.

Add to an existing `matcher: "Bash"` entry's `hooks` array (don't create a second
Bash entry). Then **converge every profile** — a guard registered only in the
main profile leaves the others unprotected. Editing settings.json programmatically
with python (read → append if absent → write) is safer than hand-editing JSON.
