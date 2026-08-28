# Hook Patterns — runnable skeletons

Battle-tested shapes plus the shlex command-position walker. Every snippet
here is distilled from a hook that has run in production. Copy, rename the
TRIGGER, keep the structure.

> ⚠️ **Known divergence from SKILL.md's skeleton — read before copying an
> opening.** Every pattern below still starts with `INPUT=$(cat)`, while SKILL.md
> now opens with the builtin `IFS= read -rd '' INPUT || true` plus a `case`
> pre-filter, because on a Bash matcher those two lines cost forks on **every**
> call including the irrelevant ones (pitfall #22, which carries the conversion
> recipe and its measured floor). These patterns have not been converted yet: the
> swap is not purely cosmetic — `$(cat)` drops NUL bytes and keeps what follows,
> `read -d ''` stops at the first NUL — and converting a blocking guard also
> requires #22's payload gate, so each one needs its own re-test rather than a
> find-and-replace. **Take the structure from here and the opening from SKILL.md.**

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
  "session_id": "…",                         // stable for the whole session
  "cwd": "…",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",                       // or "Agent", "WebFetch", "Edit", …
  "tool_input": { "command": "…" }           // Bash: .command; Agent: .prompt; Edit: .file_path/.new_string
}
```

Non-tool events carry a different shape, and **the user's text is a field on
stdin — never an environment variable.** There is no `USER_PROMPT_TEXT` or
anything like it; a hook that reads one gets an empty string on every
invocation and exits before doing anything, which for an injecting hook is
indistinguishable from a healthy skip (#38 — it survived two months that way):

```jsonc
// UserPromptSubmit
{
  "session_id": "…",
  "transcript_path": "…",
  "cwd": "…",
  "hook_event_name": "UserPromptSubmit",
  "prompt": "…"                              // the user's text, top-level — NOT tool_input
}

// SessionStart
{
  "session_id": "…",
  "cwd": "…",                                // where claude was started — the only
                                             // trustworthy cwd; do not assume $PWD
  "hook_event_name": "SessionStart",
  "source": "startup"                        // or "resume" / "clear" / "compact" / "fork"
}
```

```bash
PROMPT=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('prompt',''))" 2>/dev/null||echo "")
```

Two consequences worth stating separately. Whatever a UserPromptSubmit hook
prints on stdout at exit 0 is **injected as context** — that is the injection
channel, and it makes the message the hook's entire product, so exit-code
assertions alone cannot test it (#40, #14). And `.prompt` being populated does
not prove a human typed it: a background task notification's report text
arrives through the same field with nothing marking the difference (#30).

**`session_id` is the only correct key for per-session state** a hook keeps
(counters, cool-downs — rule 7 mechanisms 3 and 4). Nothing else is stable:
`$$` / `$PPID` change on every invocation because each hook run is a fresh
process, and a fixed path makes the state global, which turns a one-shot guard
into a permanently dead one.

Extract them defensively (never assume the shape — a parse failure should
**allow**, not crash):

```bash
INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null||echo "")
CMD=$(printf '%s' "$INPUT"  | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null||echo "")
```

**Exit codes:** `0` = allow / proceed; `2` = block (PreToolUse) — stderr is shown
to the model; anything else = non-blocking error — **but that last clause holds
only while stdout carries no valid JSON**: Claude Code reads JSON output on every
exit code, and valid JSON decides the outcome instead of the code. Every skeleton
in this file prints nothing on stdout, so the rule as stated applies to all of
them. SessionStart should always exit 0 — **not because a non-zero could block it
(no exit code can block a session start)** but because a non-zero prints a hook
error notice to the user on every single session start.

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
migration candidate, not a model to copy. (Pitfall #7 cites the same hook approvingly
for a *different* property — it correctly exempts git write segments. Both are true:
copy its segment-exemption logic, not its awk splitting.))

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
printf '%s' "$CMD" | grep -qw 'TRIGGER' || {
  # Quote-splice is the standard evasion: `TRIG''GER` EXECUTES but contains no
  # literal token, so the raw substring check above misses it and the walker
  # would never run (final-review F1 — bash executes `ec''ho MARKER` just fine).
  # The fast path must be a SUPERSET filter: de-splice (strip quotes/backslashes)
  # and check again. A false positive here only costs one python run — the
  # walker arbitrates; a false negative is a full bypass.
  printf '%s' "$CMD" | tr -d "\\'\"\\\\" | grep -qw 'TRIGGER' || exit 0
}

# Precise detection AND the guidance message BOTH live inside python — so `set -e`
# can't swallow the message. If the BLOCKED text sat in a SECOND bash step after
# the heredoc (`rc=$?; if [ "$rc" = 2 ]…`), `set -e` would kill the script the
# instant python exits 2, and you'd get a bare exit 2 with ZERO guidance — a real
# bug (SKILL.md's whole point is that stderr IS the message the model sees). One
# process: print, then exit.
# (Size ceiling worth knowing: HOOK_CMD travels as an env var, so a command near
# the kernel's ARG_MAX (~1-2MB) makes python3 fail to start with E2BIG — the hook
# exits 126, a non-2 code, i.e. fail-open; it also leaks one raw shell line to
# stderr. Pathological input, but declare it.)
HOOK_CMD="$CMD" python3 - <<'PY'
import os, sys, shlex, re
cmd = os.environ["HOOK_CMD"]
SEPS = {";","&&","||","|","&","(",")","{","}","|&"}   # NOT <> — a redirect target is a filename, not a command
ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
GIT_WRITES = {"commit","rebase","tag","am","cherry-pick"}
WRAPPERS = {"command","env","sudo","time","timeout","nice","stdbuf","nohup","builtin","exec","xargs"}
# Introspection flags make a wrapper a QUERY, not an execution — `command -v
# TRIGGER` is the standard existence probe (health checks use it); blocking it
# is a false-block. Bundled single-dash flags count too (`command -vp` = -v -p).
INTROSPECT = {"command": {"-v","-V"}, "sudo": {"-l","-V","--list","--version","--help"}}
INTROSPECT_CLUSTER = {"command": "vV", "sudo": "lV"}

def _is_introspect(wrapper_base, flag):
    if flag in INTROSPECT.get(wrapper_base, ()): return True
    return (flag.startswith("-") and not flag.startswith("--")
            and any(c in INTROSPECT_CLUSTER.get(wrapper_base, "") for c in flag[1:]))

def toks(c):
    lex = shlex.shlex(c, posix=True, punctuation_chars=True); lex.whitespace_split = True
    return list(lex)                       # |;&<>() are boundaries even without spaces

def segments(line):
    """(head, tokens) per command segment in ONE line (shlex keeps quotes atomic)."""
    try: TS = toks(line)
    except ValueError: TS = line.split()   # unbalanced quotes → best effort (SKILL.md Rule 1 nuance)
    at_cmd, head, cur = True, "", []
    for t in TS:
        if t in SEPS:
            if head: yield head, cur
            at_cmd, head, cur = True, "", []
            continue
        if at_cmd and ENV.match(t): continue   # VAR=val prefix, command is still ahead
        if at_cmd: head = t; at_cmd = False
        cur.append(t)
    if head: yield head, cur

def is_git_write(seg):
    # seg[0]=="git"; the subcommand is the first non-flag token (skip flag values)
    skip = False
    for t in seg[1:]:
        if skip: skip = False; continue
        if t in ("-C","-c","--git-dir","--work-tree"): skip = True; continue
        if t.startswith("-"): continue
        return t in GIT_WRITES
    return False

def eff_head_idx(toks):
    """Effective command index: skip ENV prefixes and transparent wrappers —
    including their VALUED flags and positional args, or `sudo -u root git
    commit` (value 'root' would become the "command") and `timeout 5 git commit`
    ('5' would) slip past. Tables mirror production qlmanage-guard's."""
    WRAPPER_VALUED = {
        "sudo":  {"-u","-g","-p","-C","-U","-r","-t","-D","-T","-h",
                  "--user","--group","--prompt","--close-from","--role","--type",
                  "--other-user","--chdir","--command-timeout","--host"},
        "env":   {"-u","--unset","--chdir","-C","-S","--split-string"},
        "xargs": {"-n","-P","-I","-d","-a","-E","-s","-L","-R",
                  "--max-args","--max-procs","--replace","--delimiter","--arg-file"},
        "timeout": {"-k","-s","--kill-after","--signal"},
        "nice":  {"-n","--adjustment"},
        "stdbuf": {"-i","-o","-e","--input","--output","--error"},
    }
    WRAPPER_POSITIONAL = {"timeout": 1}
    i = 0
    while i < len(toks):
        t = toks[i]
        if ENV.match(t): i += 1; continue
        if t in WRAPPERS or t.rsplit("/", 1)[-1] in WRAPPERS:   # /usr/bin/sudo 同效
            w = t.rsplit("/", 1)[-1]; i += 1
            while i < len(toks) and toks[i].startswith("-"):
                if toks[i] in WRAPPER_VALUED.get(w, ()):
                    if toks[i] in ("-S", "--split-string") and w == "env" and i + 1 < len(toks):
                        toks[i+1:i+2] = toks[i+1].split()   # env -S 的值本身是一行命令,展开再扫
                    i += 2            # flag + its value (not the command)
                else:
                    i += 1
            i += WRAPPER_POSITIONAL.get(w, 0)   # timeout's DURATION
            continue
        return i
    return -1

def split_shell_lines(c):
    r"""Split on newlines as SHELL sees them:
    - quote state tracked (a newline inside '…' or "…" does not split —
      `gh pr create -b "…\nTRIGGER…"` never executes it), `$'…'` ANSI-C
      escapes honored (`\'` does not close), backslash-newline joined (posix);
    - a word-start `#` starts a comment that ends at the physical newline —
      quotes INSIDE comments are inert, so `# it's fine` must not open a
      phantom quote that glues the next line's real command into the previous
      one (Finding: `echo hi # it's fine⏎TRIGGER` really executes TRIGGER).
    Heredoc bodies are not quote syntax and still fragment (declared residual)."""
    lines, cur, quote, ansi, i = [], [], None, False, 0
    n = len(c)
    while i < n:
        ch = c[i]
        if quote is None and ch == "#" and (i == 0 or c[i-1] in " \t\n;&|(){}"):
            while i < n and c[i] != "\n": i += 1
            ch = c[i] if i < n else ""
        if ch == "\\" and i + 1 < n:
            nx = c[i + 1]
            if nx == "\n" and (quote != "'" or ansi): i += 2; continue
            if quote == '"' and nx in ('"', "\\", "$", "`"): cur.append(ch); cur.append(nx); i += 2; continue
            if quote is None and nx in ("'", '"', "\\"): cur.append(ch); cur.append(nx); i += 2; continue
            if quote == "'" and ansi: cur.append(ch); cur.append(nx); i += 2; continue
        if quote is None and ch in ("'", '"'):
            quote = ch; ansi = ch == "'" and len(cur) > 0 and cur[-1] == "$"
        elif quote == ch:
            quote = None; ansi = False
        if ch == "\n" and quote is None:
            lines.append("".join(cur)); cur = []
        else:
            cur.append(ch)
        i += 1
    lines.append("".join(cur))
    return lines

# Pitfall #7 (whole command, BEFORE any splitting): a git *write*'s message is DATA —
# `git commit -F - <<EOF` whose body quotes `foo|TRIGGER` reaches the walk below as
# pseudo-command-text and the guard blocks its own fix commit (this skill's own
# qlmanage-guard shipped exactly that). Exempt the whole command when any segment's
# EFFECTIVE command is a git write. Bias-to-under (pitfall #11): this also lets
# `git commit -m x && TRIGGER` — and the multiline form (`git commit -m x`⏎`TRIGGER`) —
# through; the rare miss is the deliberate trade for a blocker.
# Declared hole in the same trade: git's own argv EXECUTIONS are not data —
# `git rebase --exec 'TRIGGER'` and `git -c core.editor=TRIGGER commit` have git run
# the string for real, and the whole-command exemption swallows them (production
# shares this hole; narrowing it is heuristics-on-heuristics, so it is declared,
# not patched).
if any(
    (idx := eff_head_idx(seg[1])) >= 0
    and (seg[1][idx] == "git" or seg[1][idx].endswith("/git"))
    and is_git_write(seg[1][idx:])
    for seg in segments(cmd)
):
    sys.exit(0)

def blocks(seg_toks):
    """Is TRIGGER executed in this segment — wrapper-aware (sudo/env/xargs/timeout
    are transparent; their introspection flags are queries, not executions)."""
    idx = eff_head_idx(seg_toks)
    if idx < 0: return False
    for w in (t for t in seg_toks[:idx] if t.rsplit("/", 1)[-1] in INTROSPECT):
        wb = w.rsplit("/", 1)[-1]
        if any(_is_introspect(wb, f) for f in seg_toks[1:idx]): return False
    head = seg_toks[idx]
    if head != "TRIGGER" and not head.endswith("/TRIGGER"):
        return False
    # `TRIGGER()` starts a function DEFINITION, not a call (measured false-block;
    # punctuation_chars groups `()` into ONE token, so check both forms).
    nxt = seg_toks[idx+1] if idx + 1 < len(seg_toks) else ""
    if nxt == "()" or (nxt == "(" and idx + 2 < len(seg_toks) and seg_toks[idx+2] == ")"):
        return False
    return True

# Pitfall #11: shlex treats newlines as ordinary whitespace, so a multiline command
# (`cd /x\ngit add\nTRIGGER -y`) collapses into ONE segment whose head is `cd` and
# the trigger is never in command position — replayed trigger rate 0 on real
# transcripts. Split shell-aware FIRST, then walk each line.
for line in split_shell_lines(cmd):
    for _head, seg in segments(line):
        if blocks(seg):                        # execution hit → print guidance + block
            sys.stderr.write("BLOCKED: <BANNED THING> is not allowed here.\n"
                             "WHY: <the failure mode this prevents>.\n"
                             "USE INSTEAD: <the correct command / workflow>.\n")
            sys.exit(2)
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

def _segments(line: str):
    """(head, tokens) per command segment in ONE physical line."""
    try: toks = _tokens(line)            # quotes honored, # comment dropped, |;& are boundaries
    except ValueError: toks = line.split()  # unbalanced quotes → best effort (see SKILL.md Rule 1 nuance)
    at_cmd, head, cur = True, "", []
    for t in toks:
        if t in SEPS:
            if head: yield head, cur
            at_cmd, head, cur = True, "", []
            continue
        if at_cmd and ENV.match(t): continue  # skip VAR=val prefixes
        if at_cmd: head = t; at_cmd = False
        cur.append(t)
    if head: yield head, cur

_WRAPPERS = {"command","env","sudo","time","timeout","nice","stdbuf","nohup","builtin","exec","xargs"}

def _eff_head_idx(toks):
    """Effective command index: skip ENV prefixes and transparent wrappers.
    Compact form — Pattern A carries the full per-wrapper valued-flag tables
    (`sudo -u root`, `timeout 5`); use those if your targets ride wrappers often."""
    i = 0
    while i < len(toks):
        t = toks[i]
        if ENV.match(t): i += 1; continue
        if t in _WRAPPERS or t.rsplit("/", 1)[-1] in _WRAPPERS:
            i += 1
            while i < len(toks) and toks[i].startswith("-"): i += 1
            continue
        return i
    return -1

_INTROSPECT = {"command": "vV", "sudo": "lV"}

def _is_query(seg, idx):
    """Wrapper introspection (`command -v TRIGGER`, `sudo -l`, incl. bundled
    `-vp` clusters) is a probe, not an execution."""
    for w in (t for t in seg[:idx] if t.rsplit("/", 1)[-1] in _INTROSPECT):
        wb = w.rsplit("/", 1)[-1]
        for f in seg[1:idx]:
            if f.startswith("-") and not f.startswith("--") and any(c in _INTROSPECT[wb] for c in f[1:]):
                return True
    return False

def split_shell_lines(c: str):
    r"""Split on newlines as SHELL sees them (production: qlmanage-guard).
    - Newlines inside single/double quotes do NOT split — `gh pr create -b
      "line1\nTRIGGER was the culprit\nline3"` never executes TRIGGER, and a
      text-level split would put it at a line head and false-block (a more
      common shape than heredocs).
    - Backslash-newline continuations are deleted and joined (posix), so
      `echo a \⏎TRIGGER` keeps TRIGGER as an argument of echo.
    - `$'…'` ANSI-C quoting is tracked: `\'` inside it is an escaped quote,
      not a close — `$'a\'⏎TRIGGER'` does not execute TRIGGER.
    Heredoc bodies are not quote syntax: they still fragment (residual below)."""
    lines, cur, quote, ansi, i = [], [], None, False, 0
    n = len(c)
    while i < n:
        ch = c[i]
        if quote is None and ch == "#" and (i == 0 or c[i-1] in " \t\n;&|(){}"):
            # word-start comment → EOL; quotes inside comments are inert
            while i < n and c[i] != "\n": i += 1
            ch = c[i] if i < n else ""
        if ch == "\\" and i + 1 < n:
            nx = c[i + 1]
            if nx == "\n" and (quote != "'" or ansi):
                i += 2
                continue
            if quote == '"' and nx in ('"', "\\", "$", "`"):
                cur.append(ch); cur.append(nx); i += 2
                continue
            if quote is None and nx in ("'", '"', "\\"):
                cur.append(ch); cur.append(nx); i += 2
                continue
            if quote == "'" and ansi:
                cur.append(ch); cur.append(nx); i += 2
                continue
        if quote is None and ch in ("'", '"'):
            quote = ch
            ansi = ch == "'" and len(cur) > 0 and cur[-1] == "$"
        elif quote == ch:
            quote = None
            ansi = False
        if ch == "\n" and quote is None:
            lines.append("".join(cur)); cur = []
        else:
            cur.append(ch)
        i += 1
    lines.append("".join(cur))
    return lines

def executes(cmd: str, target: str) -> bool:
    # Two stages, order matters (pitfall #11): shlex swallows newlines as ordinary
    # whitespace, so a multiline block (`cd /x\ngit add\nTRIGGER -y`) would
    # collapse into ONE segment headed by `cd` and hide the trigger. Split into
    # lines shell-aware FIRST (quote state + continuations + comments), then
    # shlex-walk each line — a quoted `a|TRIGGER|b` still stays one token inside
    # its line, so no phantom command is made.
    for line in split_shell_lines(cmd):
        for _head, seg in _segments(line):
            idx = _eff_head_idx(seg)          # wrappers are transparent —
            if idx < 0 or _is_query(seg, idx):  # `sudo TRIGGER` IS a hit, and
                continue                      # `command -v TRIGGER` is NOT
            head = seg[idx]
            if head == target or head.endswith("/" + target):
                # `TRIGGER()` starts a function definition, not a call
                nxt = seg[idx+1] if idx + 1 < len(seg) else ""
                if nxt == "()" or (nxt == "(" and idx + 2 < len(seg) and seg[idx+2] == ")"):
                    continue
                return True
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
- The per-segment walk means `ls | TRIGGER x` matches (after the pipe) but
  `grep TRIGGER f` does not (TRIGGER is grep's argument).
- `ENV` skip means `FOO=1 TRIGGER` matches (TRIGGER is still the command).
- The outer `split_shell_lines(cmd)` means `cd /x\ngit add\nTRIGGER -y` matches (its own
  line) — without it the newline collapses into whitespace and the head stays
  `cd` (pitfall #11: replayed trigger rate 0 on real transcripts). Being
  quote-state-aware it also leaves `gh pr create -b "…\nTRIGGER…"` alone
  (quoted, never executed) and joins `echo a \⏎TRIGGER` back into one line.

**What it catches for free, and what it misses (measured, not guessed):**
unquoted `$(TRIGGER)` IS caught — `(` is in SEPS, so command position resets
right after it and the token lands at a head (`OUT=$(TRIGGER -t x)` blocks;
production shipped this exact correction 2026-07-23 after an earlier version of
this note claimed the opposite). The genuine misses: **backticks**
(`` `TRIGGER` `` — no `(` token), **quoted substitutions** (`"$(TRIGGER)"` and
`'$(TRIGGER)'` — quoted, so never a command), and **process substitution**
(`<(TRIGGER …)`). If you truly need those, detect them in a context that
distinguishes single- from double-quotes — usually not worth it.

**Known gaps by declaration (measured 2026-07-26) — miss-direction (allow when
execution is real):** heredoc bodies are only half-handled — *quoted-string*
newlines and comments are fine, but a heredoc body still fragments (see below);
shell keyword frames (`if TRIGGER; then`, `for … do TRIGGER`, `! TRIGGER`,
`coproc TRIGGER`); redirect PREFIX (`2>/dev/null TRIGGER -t x` — `<>` stays out
of SEPS, so the prefix takes the command slot; a natural retry-after-block
shape, worth a WRAPPER-style fix later); `bash -c 'TRIGGER'` / `eval TRIGGER` /
`ssh host TRIGGER` / `find . -exec TRIGGER` (string payloads need recursive
parsing); backticks, quoted substitutions, and process substitution (above);
variables-as-commands (`CMD=TRIGGER; $CMD -t x`); and mid-word `#` in the
*miss* direction (`foo=#x TRIGGER` — bash treats it as an assignment and DOES
run TRIGGER, shlex's commenter eats the line instead).

**False-block-direction (currently blocks — declared, not patched):** non-git
heredoc bodies (the residual below); multiline `case` patterns (`TRIGGER)` at a
line head is a pattern, not a call); and `TRIGGER#frag` (shlex's posix lexer
starts a comment at the mid-word `#`, bash doesn't — though in that shape bash
itself errors command-not-found, so the practical harm is low).

Each miss-side entry is declared rather than patched per bias-to-under; each
block-side entry is declared because fixing it takes real shell grammar, not
more heuristics. Production qlmanage-guard shares most of these.

**What it splits but cannot fully parse:** a newline **inside a heredoc body** —
a heredoc is not quote syntax, so `git commit -F - <<'MSG'` whose body quotes a
trigger-looking line still fragments into a phantom command even with
quote-state-aware splitting. (Multiline *quoted strings* used to be in this
list too; `split_shell_lines` handles those, and it also strips word-start
`#` comments so a quote inside a comment can't glue lines together —
`echo hi # it's fine⏎TRIGGER` still blocks. The residual is heredoc-only.)
That residual is pitfall #11's: for a fail-open
reminder, declare it and move on; for a fail-closed blocker, lift the git-write
exemption (pitfall #7) to the whole command BEFORE this walk — exactly the
order Pattern A shows. But note the exemption's name: it rescues **git**
heredocs only. A non-git one (`cat <<'EOF'` whose body contains
trigger-looking data) still false-blocks a fail-closed guard, and for that
shape the honest options are declare-it-fail-open or a real shell grammar —
there is no cheap middle ground.

---

## Pattern B — PreToolUse with a human-confirmation release gate

For an irreversible action you want to *allow with explicit human consent*, never
a static env var (the model can set env vars). This is `git-worktree-guard` /
`git-commit-scope-guard`.

> ⚠️ **This pattern ships two channels; only the first one is a channel.** The
> official hooks reference states that hooks run in their own session **without a
> controlling terminal** and "can't open `/dev/tty`" (its replacement for terminal
> output is the `terminalSequence` output field). So Channel 2 below is, per the
> documented contract, unreachable — and the comment inside it, written before that
> was known, treats "exists but won't open" as a *sandbox* quirk rather than the
> general case. Read it that way. **Consequence if you copy this verbatim onto a
> machine with no GUI session: the gate can never be approved by anyone**, because
> Channel 1 can't run and Channel 2 can't open — it falls through to a hard block.
> The code is left in place because a hard block is the safe direction and because
> a live audit log shows the branch has simply never been entered; do not read its
> presence as endorsement. If you need a gate off macOS, this file does not yet
> have a verified answer for you.

Two channels the model physically cannot drive (see the warning above about the
second):

```bash
# ... detection decided this action needs confirmation ...
BYPASS_LOG="${HOME}/.hook-bypass.log"
stamp() { printf '%s\t%s\t%s\n' "$(date '+%F %T')" "$1" "${CMD:0:80}" >> "$BYPASS_LOG"; }

# Channel 1: native macOS dialog — the model cannot click a button.
if command -v osascript >/dev/null 2>&1; then
  # CRITICAL #1 — NEVER splice text into the AppleScript source. `$CMD` (and any
  # file path or name you show) is attacker-controlled: the model chooses it. A
  # payload containing a newline and a quote escapes the string literal and becomes
  # a statement, so `return "button returned:允许"` makes osascript hand back an
  # approval the human never gave. Measured 2026-07-22 against a guard that *did*
  # escape quotes with sed — the escaper assumed single-line input and a filename
  # with an embedded newline walked straight through it. The gate that exists so the
  # model cannot approve its own action was approving it.
  # The fix is parameterization, not better escaping: keep the script a CONSTANT and
  # pass text through `on run argv` (same principle as a prepared statement).
  DLG_FRONT='"'"'on run argv
  tell application (path to frontmost application as text)
    display dialog (item 1 of argv) buttons {"拒绝","允许"} default button "拒绝" cancel button "拒绝" with icon stop giving up after 40 with title "my-guard"
  end tell
end run'"'"'
  DLG_PLAIN='"'"'on run argv
  display dialog (item 1 of argv) buttons {"拒绝","允许"} default button "拒绝" cancel button "拒绝" with icon stop giving up after 40 with title "my-guard"
end run'"'"'
  MSG="Allow <ACTION>?

$CMD"
  # CRITICAL #2: attach the dialog to the FRONTMOST app (the terminal the user is
  # looking at) so it pops up *in front of them*. A bare `osascript -e "$DLG"`
  # opens on some other desktop/Space in fullscreen setups — the user never sees
  # it, it times out at 40s, and the log misreads "declined" (a real 2026-07-21
  # bug this exact snippet used to have). Fall back to the bare form only on a
  # NON-cancel error (some frontmost apps don't support `tell`).
  ERR=$(mktemp); DLG=""
  if DLG=$(osascript -e "$DLG_FRONT" "$MSG" 2>"$ERR"); then :
  elif ! grep -qiE 'user canceled|-128' "$ERR"; then DLG=$(osascript -e "$DLG_PLAIN" "$MSG" 2>"$ERR") || true
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
# ⚠️ DOCUMENTED AS UNREACHABLE — see the warning above this code block. Hooks run
# without a controlling terminal, so the probe below is expected to fail and this
# whole branch to be skipped. Kept because failing to a hard block is the safe
# direction; NOT a working second channel you can rely on.
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

**Make the gate testable — route both channels through overridable names.** A gate
whose confirmation path can't be exercised automatically is a gate nobody ever
verifies: an automated run pops a real dialog at a human who isn't there (the tty channel
itself is already safe — its `(exec 3<>/dev/tty)` probe fails in a non-tty context
and falls through to block rather than hanging). Read both endpoints from a variable with the production value
as the default:

```bash
OSASCRIPT_BIN="${GIT_GUARD_OSASCRIPT:-osascript}"
TTYDEV="${GIT_GUARD_TTY:-/dev/tty}"
```

In production nothing changes. In a test you point them at things that deterministically
decline, and the run stays headless and non-interactive:

```bash
GIT_GUARD_OSASCRIPT=false GIT_GUARD_TTY=/dev/null   # dialog "fails", tty reads nothing
#   → both channels decline → the gate must exit 2
```

That inversion is what makes the gate assertable: **`exit 2` under forced-decline is
positive evidence the guard reached its blocking branch**, which is exactly the fact
a fail-open bug (pitfall #10) hides. Pair it with a negative control in the same run
— one input that *shouldn't* trigger, asserted `exit 0` — because "blocks everything"
and "blocks the right thing" are otherwise indistinguishable. **Be honest about what this costs — the override is itself a bypass surface, and
prose does not close it.** Pointing `GIT_GUARD_TTY` at a file containing `YES`, or
`GIT_GUARD_OSASCRIPT` at a script that echoes the approval string, *grants* approval.
Saying "these may only steer which channel is consulted" is an assertion, not an
enforcement — exactly the shape rule 4 retired (`GUARD_OK=1`), wearing a test-shaped
hat. Either accept that and constrain it, or don't ship the override:

```bash
# Refuse the override outside a test context, and refuse a *granting* one always.
if [ -n "${GIT_GUARD_TTY:-}" ] || [ -n "${GIT_GUARD_OSASCRIPT:-}" ]; then
  [ "${GIT_GUARD_TEST:-}" = "1" ] || { echo "override outside test context" >&2; exit 2; }
  # only decline-shaped targets are honored; anything else is treated as decline
  case "${GIT_GUARD_TTY:-/dev/null}" in /dev/null|/dev/zero) : ;; *) TTYDEV=/dev/null ;; esac
  case "${GIT_GUARD_OSASCRIPT:-false}" in false|/usr/bin/false) : ;; *) OSASCRIPT_BIN=false ;; esac
fi
```

The residual risk is `GIT_GUARD_TEST=1` itself, which the model can also set — but
now every path it opens leads to **decline**, so setting it buys a block, not a pass.
That is the property worth having: **the escape hatch may only make the gate stricter.**
If you can't get there, prefer no override and test the gate manually — an
unverifiable gate that cannot be bypassed beats a verifiable one that can.

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
shopt -s nullglob          # else an EMPTY hooks dir yields the literal glob and the
                           # loop below reports it as a dangling symlink — a false
                           # alarm at exactly the moment (fresh profile, reinstalled
                           # ~/.claude) this check matters most. Measured.
for h in "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/hooks/*.sh; do    # active profile, not
                           # hardcoded $HOME — the settings check below already uses
                           # CLAUDE_CONFIG_DIR, and rule 4's whole point is that each
                           # profile is its own config home. Checking one profile's
                           # scripts against another's settings answers nothing.
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
# Contract: ALWAYS exit 0 — a reporter, not a decider. Kept TWO ways in
# production: drop -e entirely (Pattern E's shape), or keep -e and convert every
# failure to exit 0 with `trap 'exit 0' ERR` (git-commit-headcheck's shape —
# used here so set -e still guards the plumbing). See SKILL.md's "-e or trap"
# bullet for the choice.
set -euo pipefail
trap 'exit 0' ERR
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
# CRITICAL: a git PIPE is a trap under pipefail — see pitfall #8. The `||` goes
# OUTSIDE the $(…): `wc` prints 0 even when git fails, so `… | wc -l || echo '?'`
# INSIDE the substitution yields the malformed two-line value `0\n?`.
HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
SUBJ=$(git log -1 --format='%s' 2>/dev/null || echo "?")
STAGED=$(git diff --cached --name-only 2>/dev/null | wc -l | tr -d ' ') || STAGED='?'

# The injection channel is `hookSpecificOutput` JSON on STDOUT, not stderr:
# at exit 0 the CLI routes stderr nowhere the model sees (it only reaches the
# model at exit 2), while a hookSpecificOutput payload is added to the model's
# context as "additional context". Emitting the line below via `>&2` — as an
# earlier version of this pattern did — delivers it to NO ONE. Production
# (git-commit-headcheck) emits exactly this shape.
CTX="[headcheck] real HEAD = $HEAD $SUBJ | staged remaining = $STAGED"
python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':sys.argv[1]}}, ensure_ascii=False))" "$CTX"
exit 0
```

The value is that the model **cannot forget a check that runs automatically**.
Injected truth beats "I think the commit worked."

**Testing note:** the `says` helper in `scripts/test_hook.sh` captures **stderr**
— right for blocking hooks (their contract text lives there) but blind for this
pattern, whose payload is stdout JSON. For an exit-0 injector, assert on stdout
instead (`out=$(printf '%s' "$2" | "$HOOK" 2>/dev/null)`) and match a fixed
string from `additionalContext`, or stay with `run` rows for the exit contract.

---

## Pattern E — Stop hook: react to Claude's own output

The only pattern here that inspects the **model's own generated text**, not a
tool call or a file. Use it for a rule about what the model itself *writes* —
"never invent a shorthand name for something unverified", "always cite a
source" — never for a rule about what the model writes **into** a file or a
shell command (that's PreToolUse on `Write`/`Edit`/`Bash` instead; Stop only
sees plain chat text). Getting the event wrong here is a category mistake, not
a tuning problem — full argument (why `UserPromptSubmit` structurally cannot
substitute, and the shipped incident) in SKILL.md's Stop bullet.

```bash
#!/usr/bin/env bash
# Stop hook: block the model from ending its turn if its own last reply
# contains <BANNED PATTERN>.
# LOOP CONTRACT — fill every field before registration:
# KEY: <immutable logical target / lineage + one failure axis>
# FIRE T: <condition that starts another cycle>
# REMEDIATION R: <exact action one cycle performs>
# TERMINATION: V = <well-founded quantity>; decreased by <remediation>
# BUDGET: <maximum cycles fixed before cycle 1>
# SUCCESS EXIT: <observable proving this axis is clear>
# CAPPED EXIT: <blocked / unshipped / pending state; never "completed">
set -uo pipefail                                # no -e: every risky step below
INPUT=$(cat)                                     # is explicitly ||-guarded instead

# Anti-loop, and the field this pattern is most likely to get wrong: compare
# by IDENTITY to the JSON boolean, not by Python truthiness. `bool("false")`
# is True (any non-empty string is truthy) — if stop_hook_active ever arrives
# as the JSON *string* "false" instead of the boolean, a naive `bool(...)`
# check treats it as an already-blocked retry and silently, permanently
# disarms the guard for that turn. Test this explicitly: a payload with
# `"stop_hook_active": "false"` (string) must NOT be treated as active.
ACTIVE=$(HOOK_JSON="$INPUT" python3 - 2>/dev/null <<'PY'
import json, os
print(json.loads(os.environ['HOOK_JSON']).get('stop_hook_active') is True)
PY
) || exit 0
[ "$ACTIVE" = "True" ] && exit 0

# Prefer last_assistant_message (official docs: use it INSTEAD OF the
# transcript — transcript_path is written asynchronously and may not yet
# include the current turn's newest message when Stop fires). Its documented
# shape is a plain string, but defensive extraction costs nothing and the
# SAME helper is genuinely required for the transcript fallback below, where
# message.content really is a list of typed blocks in practice.
TEXT=$(HOOK_JSON="$INPUT" python3 - 2>/dev/null <<'PY'
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
) || exit 0
[ -n "$TEXT" ] || exit 0

printf '%s' "$TEXT" | grep -qw 'TRIGGER' || exit 0    # fast path, same idea as Pattern A —
# but NOT the shlex walker below this line: TEXT is free-form prose, not a
# shell command, so match with substring/regex per the JSON event contract's
# "shlex is for shell commands" rule above.
HITS=$(HOOK_TEXT="$TEXT" python3 - 2>/dev/null <<'PY'
import os, re
t = os.environ['HOOK_TEXT']
# ... precise detection here — regex/substring over free text ...
# Collect EVERY finding, not just the first: the blocked retry round
# (stop_hook_active: true) passes with whatever you did not report, so a
# first-only report loses the rest permanently (pitfall #17). Cap the list so
# a pathological text cannot flood the model's context.
hits = [m.group(0) for m in re.finditer(r'TRIGGER', t)]
print(' / '.join(hits[:5]))
PY
) || HITS=''

if [ -n "$HITS" ]; then
  # This message is read by the MODEL, not the user — once Stop blocks, the
  # model sees this text and must act on it before it can actually stop.
  # Write it as an instruction ("rewrite X"), not a user-facing explanation,
  # and name the exact acceptable fix — the model converges in one round or it
  # burns the 8-consecutive-block harness cap guessing.
  echo "BLOCKED: your last reply contains <BANNED THING> (\"$HITS\"). WHY: ...
FIX: rewrite each one using <the correct alternative>, then finish this turn." >&2
  exit 2
fi
exit 0
```

Three things worth calling out beyond what the comments above already say:

- **The Loop Contract header is part of the pattern, not optional
  documentation.** If you cannot fill its key, T, R, V, budget, and two exits,
  do not register the hook. A remediation snapshot stays in the key's original
  lineage. For an agent-driven review loop with no hook, use the same card from
  SKILL.md rule 7; nothing mechanically enforces that case, so the visible
  capped exit is the safety mechanism. For a Stop-hook repetition ceiling,
  implement the capped exit with universal `continue:false` + `stopReason`; if
  an artifact must stay unshipped, separately gate the publish action with
  PreToolUse.

- **This skeleton uses `python3 - <<'PY' ... PY` (a QUOTED heredoc) everywhere,
  never `python3 -c "…multi-line…"`.** The quoted delimiter makes the body inert
  literal text to bash — mechanism in the JSON event contract section above;
  what goes wrong with the `-c "…"` form (a stray quote *inside a comment*
  silently corrupts the block, and `bash -n` can't see it) is
  [hook_pitfalls.md](hook_pitfalls.md#9-a-literal-quote-or-backtick-inside-a-python-comment-corrupts-a-hook-silently).
- **`stop_hook_active` is the single most safety-critical field in this
  pattern.** Every other mistake in this hook fails toward "block too much" or
  "miss one case"; getting this one wrong in the permissive direction fails
  toward "silently do nothing, forever, with zero error signal."
- **The flag is set by ANY stop hook's block, not specifically yours** —
  "already continuing as a result of **a** stop hook": with several Stop hooks
  registered, another guard's block consumes the shared retry round, so your
  first block must be complete (the skeleton above collects all findings —
  pitfall #17 is the failure shape of reporting only the first). The other
  loop-safety layers (the consecutive-block harness ceiling — which only lands
  when the remediation involves no tool calls, see
  [hook_pitfalls.md#27](hook_pitfalls.md), all Stop hooks running in parallel
  per event, the `background_tasks` / `session_crons` pause signal in
  v2.1.145+, and the gate-vs-guidance channel choice) are covered in SKILL.md's
  hook-types table and Stop bullet — both share these same protections.
- **…and handling it correctly still does not make the hook terminate.** The
  field covers **one layer of re-entry** — the stop you just blocked being
  retried. It does nothing for the *cross-turn* loop, where the model actually
  goes and does what you demanded (many tool calls, a natural stop afterwards)
  and arrives at a **fresh** Stop with `stop_hook_active: false`. If this hook
  **demands a remediation** rather than merely reporting, the predicate itself
  must converge: prefer an **existence test** on an artifact the remediation
  lands (`does the record exist` — sets once, can't be unset) over a **temporal
  test** (fire when `last_offense > last_remediation`), because the remediation
  you asked for is usually what moves the operand you are comparing against. Full
  analysis, the converging mechanisms (ordered by how completely each removes the
  loop rather than taming it), and the self-test case that catches it:
  SKILL.md rule 7 and
  [hook_pitfalls.md](hook_pitfalls.md#16-the-remediation-the-hook-demands-re-arms-the-hook-a-loop-with-no-variant).
- **Wrap every python3 subprocess call with the same `2>/dev/null` + `|| <fallback>`
  guard, and put the `2>/dev/null` INSIDE the `$(...)`.** The outer form
  `X=$(python3 … ) 2>/dev/null || fallback` leaks the raw traceback to the
  model's stderr on **both** bash 3.2.57 (macOS system bash) and bash 5.x —
  reproduced on both 2026-07-25 (an earlier note here claiming the outer form
  "only suppresses on bash ≥5" was wrong; the redirection after a command
  substitution does not reliably reach it on either). Inside placement costs
  nothing and is the only portable form. The guard itself is unchanged either
  way: an inconsistency here doesn't change the block-vs-allow decision (the
  hook is already fail-open by construction), it only decides whether a crash
  degrades to "no match" cleanly or noisily.

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

Note `Stop` has no `matcher` key — it isn't scoped to a tool, so its `hooks` array
sits directly under the event. **`SessionStart` is different and this file used to
get it wrong**: it takes a matcher, just not on a tool name — it matches on *how the
session started* (`startup`, `resume`, `clear`, `compact`, `fork`). Omitting it is
still legal and means "all", so Pattern C above fires either way; but if you only
want a health check at real startup and not on every `--resume`, `"matcher":
"startup"` is how you say so.

Add to an existing `matcher: "Bash"` entry's `hooks` array (don't create a second
Bash entry). Then **converge every profile** — a guard registered only in the
main profile leaves the others unprotected. Editing settings.json programmatically
with python (read → append if absent → write) is safer than hand-editing JSON.
