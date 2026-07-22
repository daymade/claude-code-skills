---
name: claude-code-hooks
description: >-
  How to write, test, register, and debug Claude Code hooks — PreToolUse /
  PostToolUse / SessionStart / Stop Bash guards that enforce a rule the model
  would otherwise talk itself past. Use whenever the user wants to create a
  hook, block/intercept a tool call, turn a repeatedly-violated rule into a
  hard gate, add a guard rail, debug a hook that misfires or "poisons the
  session", register a hook across profiles, or mentions hooks /
  PreToolUse / Stop hook / 拦截 / 守卫 / 钩子 / 拦下. Bakes in the hard-won
  pitfalls: UserPromptSubmit only ever sees user input, never Claude's own
  text — a rule about Claude's own output belongs on Stop instead;
  token-level shlex matching (never awk splitting); bash -n + real-JSON
  end-to-end testing BEFORE registering (a corrupted PreToolUse hook poisons
  every Bash call); SSOT + symlink so a ~/.claude reinstall can't lose it;
  multi-profile convergence; and human-confirmation release gates. Reach for
  this even for "make it stop doing X" — a durable stop is a hook, not a
  reminder.
---

# Claude Code Hooks

Claude Code fires **hooks** at tool-call boundaries. A hook is a shell command
that receives a JSON event on stdin and, for blocking hooks, decides via its
**exit code** whether the tool call proceeds. This is the only mechanism that
*structurally* stops a behavior — a prose rule in CLAUDE.md is a suggestion the
completion drive can override; a hook is a wall.

## When a hook is the right tool (and when it isn't)

Write a hook when **a rule keeps getting violated even though it's already
written down**. The tell: you added the prose rule, it read clearly, and the
behavior recurred anyway — because at the moment of action, attention is 100%
on "get the thing done" and the reminder loses. That recurrence is the signal
to move the rule from prose (advisory) to a hook (enforced). Governance rule of
thumb: *Tier-0 irreversible action + only prose, no hook → it should be a hook.*

Do **not** reach for a hook when: the rule has never actually recurred (don't
pre-build guards for hypothetical mistakes — cost with no proven benefit), or
the "rule" is a judgment call with no mechanical signature (a hook can only
match tokens/patterns; it can't judge whether a design is good).

## Hook types and what the exit code means

| Type | Fires | Exit 0 | Exit 2 | Other |
|---|---|---|---|---|
| **PreToolUse** | before a tool runs | allow | **block** the call (stderr → shown to model as guidance) | non-blocking error |
| **PostToolUse** | after a tool ran | quiet | inject feedback (can't un-run the tool) | — |
| **SessionStart** | session begins | proceed | — | **always exit 0** — never block a session |
| **Stop** (+ `SubagentStop`) | the model is about to finish responding | let it stop | **block the stop** — forces the model to keep going (stderr → fed back as the reason) | must check `stop_hook_active` or it can loop |

- **PreToolUse** is the workhorse — the only one that can *stop* an action.
  `matcher` selects the tool (`Bash`, `Agent`, `WebFetch`, …). Exit 2 blocks and
  the hook's **stderr** becomes the message the model sees — so put the *why* and
  the *correct alternative* there, not just "blocked".
- **PostToolUse** can't undo, but it can **inject authoritative context** so a
  later hallucination can't stand (e.g. re-read the real git HEAD after a commit
  and surface it — the model can't "believe it committed" against injected truth).
- **SessionStart** is for **health checks of the guard rails themselves** —
  silent when healthy, warn on breakage, always exit 0.
- **Stop is the odd one out, and the one most often reached for by mistake**:
  it's the *only* hook type that can react to what the model **itself just
  generated** (its own reply text). Every other hook type — including
  `UserPromptSubmit`, which sounds like a plausible place to police "what gets
  said" — only ever sees the **user's** input; it structurally cannot see the
  model's own output. A rule like "the model must not invent a shorthand name
  for something it hasn't verified" belongs on Stop; put it on
  `UserPromptSubmit` instead and it will (a) never once catch what it was
  built for, since that text never flows through that event, and (b)
  false-block the user's own unrelated typing whenever it happens to contain
  the trigger pattern. This is a category mistake, not a tuning problem — no
  amount of regex refinement on the wrong event fixes it. Full contract
  (`last_assistant_message` vs `transcript_path`, the anti-loop check) in
  Pattern E below.

Full runnable skeletons: [references/hook_patterns.md](references/hook_patterns.md).

## The skeleton (PreToolUse Bash guard)

```bash
#!/usr/bin/env bash
set -euo pipefail
INPUT=$(cat)                                   # the JSON event on stdin
TOOL=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null||echo "")
[ "$TOOL" != "Bash" ] && exit 0                # only guard the tool you mean to
CMD=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null||echo "")
[ -z "$CMD" ] && exit 0
printf '%s' "$CMD" | grep -qw 'TRIGGER' || exit 0   # fast path: not relevant → allow
# ... precise detection here ...
if <command actually does the banned thing>; then
  echo "BLOCKED: ... WHY ... USE INSTEAD: ..." >&2   # stderr = the guidance shown
  exit 2
fi
exit 0
```

## Four rules that separate a working guard from a session-poisoning one

Not style preferences — each is a specific failure we shipped and traced back.

### 1. Match at the **token level with shlex**, never awk-split the raw string

A guard that **false-blocks a healthy command is worse than one that misses** —
a guard people must bypass gets bypassed reflexively, and then it protects
nothing (the core discipline: *误杀健康输入比漏报更糟*). The recurring cause of
false-blocks is matching on the raw command string.

- **Wrong**: `awk '{gsub(/&&|\|\||;|\|/,"\n")}'` to split into segments — awk
  doesn't understand shell quoting, so `grep -E "a|TRIGGER|b"` gets split at the
  `|` *inside the quoted regex*, `TRIGGER` becomes a phantom command, and the
  guard blocks a plain grep. (Shipped 2026-07-21; the guard's very first real use
  was a false-block on my own grep.)
- **Right**: parse the whole command with `shlex.split()` in python. A quoted
  `"a|TRIGGER|b"` stays **one token**, so a regex argument is never mistaken for
  a command. Then check whether your target is in a **command position**
  (token[0], or right after a `;`/`&&`/`||`/`|` separator, skipping `VAR=val`
  env-assignment prefixes). Command-position walker in
  [references/hook_patterns.md](references/hook_patterns.md).
- Corollary: `echo "…TRIGGER…"`, `grep TRIGGER`, `# TRIGGER`, `man TRIGGER` must
  all pass. Your test set MUST include these mention-not-execute cases.
- **But shlex isn't a silver bullet, and *what* you detect changes whether
  fail-open is safe.** `shlex.split()` itself throws `ValueError` on an unbalanced
  quote — a multi-line `git commit -m "…` message with a `#` or an unclosed quote
  is the classic trigger. The `except ValueError: cmd.split()` fallback then
  *allows*, which is right when you're detecting a **banned modifier** (does this
  carry `--no-verify`? — missing it errs safe, Rule 1's direction), but
  **dangerous when you're detecting whether the command IS your target at all**
  (is this a `git commit`? — a ValueError there means the guard never recognises
  the commit and silently doesn't fire; a real cross-domain commit shipped with no
  confirmation dialog this way). For the *is-this-the-command* decision, prefer a
  narrow **regex** (`git` and `commit` as separate words, any flag tokens between)
  that's immune to multi-line-quote breakage; reserve the shlex walker for the
  *command-position / modifier* checks where fail-open is the safe direction.

### 2. Test with **bash -n + a real JSON event, end-to-end, BEFORE registering**

**A corrupted or wrong-logic PreToolUse hook poisons the *entire* session** —
every later Bash call gets truncated / duplicated / falsely-failed / looks
hallucinated-executed, and you'll blame "the environment" when it's the hook you
just installed. (2026-07-05: a `[^;&|]` regex broke in one edit, `;&` became a
bash case-fallthrough token, poisoned half a session until `bash -n` found it.)
"My tests passed at deploy" isn't enough — the file can corrupt in a *later* edit.

Gate before registering ANY hook:
```bash
bash -n hook.sh                                # syntax
printf '%s' '{"tool_name":"Bash","tool_input":{"command":"<trigger case>"}}'    | ./hook.sh; echo "exit=$?"  # want 2
printf '%s' '{"tool_name":"Bash","tool_input":{"command":"<healthy lookalike>"}}'| ./hook.sh; echo "exit=$?"  # want 0
```
Bundle the harness: [scripts/test_hook.sh](scripts/test_hook.sh) runs a whole
table of trigger/allow cases. **Self-block gotcha:** once the hook is live in the
session you cannot test it by putting the trigger string in your *own* Bash
command — the live hook blocks your test command. Put the cases in a **script
file** and run `bash test_hook.sh`; the outer command doesn't contain the
trigger, so it isn't self-blocked.

**Once a hook has caused one real incident (a false-block or a silent miss),
solo re-reading the code is not enough** — a same-day rewrite of a Stop-hook
guard was itself re-broken twice by the author while fixing the first bug (a
quote inside a Python comment, invisible on re-read, only surfaced by running
the actual failing JSON case). The escalation is a multi-lens agent-team
review where every finding must be reproduced by *executing* a real payload
against the live script, not by reading the code and agreeing — this is the
general Counter Review methodology
([skill-development-methodology.md](../../daymade-skill/skill-creator/references/skill-development-methodology.md)
Phase 6), applied to a hook instead of a skill. In one such pass, 3 lenses (matching
logic / shell-embedding safety / event-contract robustness) surfaced 13
confirmed, independently-reproduced bugs and 1 finding whose own cited
evidence turned out to be a hallucinated doc quote — caught only because the
verifier was required to curl the raw source and grep for the exact string
rather than trust the citation.

### 3. SSOT + symlink so a reinstall can't silently disarm the guard

Real script in a version-controlled dir, **symlinked** into the hooks dir Claude reads:
```
~/scripts/claude-hooks/<name>.sh      # SSOT (git: private repo)
~/.claude/hooks/<name>.sh             # symlink → SSOT
```
A `~/.claude` reinstall wipes the hooks dir; the symlink target survives, and
recovery is one `ln -s`. A dangling symlink disables a Tier-0 guard with **zero
signal** — which is why a SessionStart health check exists (rule 4).

### 4. Registration is per-profile — converge ALL profiles, release via a HUMAN gate

- A hook in `~/.claude/hooks/` protects **nothing** if the *active profile's*
  `settings.json` doesn't call it. Multi-profile users ran with zero guards until
  every profile was converged. Register in the **main** profile's `settings.json`
  (PreToolUse → matcher `Bash` → your hook), then converge the rest (this setup
  uses `sync-profile-settings.py --all`, owned by the `claude-switch-models-setup`
  skill). A SessionStart health check greps each profile for the Tier-0 guards to
  catch drift.
- **If the guard needs a release valve, make it a *human* gate, not an env var.**
  A static `GUARD_OK=1` escape hatch is no gate — the model can set the env var
  itself. Replace with: a native macOS dialog (`osascript` — model can't click)
  and/or a typed `YES` on `/dev/tty` (model can't type into the user's terminal);
  refuse/cancel/timeout = hard NO; log every prompt/bypass to an audit file.
  Pattern in [references/hook_patterns.md](references/hook_patterns.md).

## Build order (in sequence)

1. **Confirm it's a real recurrence**, not hypothetical — else don't build it.
2. Write the script in the SSOT dir; `chmod +x`.
3. **Detection** with shlex token-level matching (rule 1).
4. **`bash -n` + `test_hook.sh`** with trigger AND healthy-lookalike cases (rule 2) — do not register until green.
5. **Symlink** into `~/.claude/hooks/` (rule 3).
6. **Register** in main `settings.json` + converge profiles (rule 4).
7. For a Tier-0/irreversible action, add the **human-confirmation release gate** (rule 4).
8. **Persist**: commit the SSOT to its private repo. Optionally add a CLAUDE.md line (prose says *why* + the alternative; the hook enforces).

## Known pitfalls (read before debugging a misfiring hook)

Full catalog with symptom → cause → fix: [references/hook_pitfalls.md](references/hook_pitfalls.md).
Headliners: `stdin` consumed by a `python3 - <<PY` heredoc (hook silently allows
everything), awk-split false-blocks (rule 1), corrupted hook poisoning the session
(rule 2), a quote or backtick inside a Python *comment* silently corrupting a
`python3 -c "…"` block with no syntax error (pitfall #9 — use the quoted-heredoc
form from Pattern E instead), static env escape hatch (rule 4), multi-profile
under-registration.

**The harness is the hidden variable — use `scripts/test_hook.sh`, don't hand-roll
one.** Every hand-rolled failure mode below produces the *same* output as a clean
pass, so it reads as success (2026-07-22, three in one sitting while fixing a Stop
hook's whitelist):

1. **Wrong event shape.** A Stop hook reads `last_assistant_message` /
   `transcript_path`, not `tool_name`/`tool_input`. Feed a PreToolUse-shaped event
   and it finds no text → exits 0 → "no false blocks!"
2. **JSON quoting.** `'{\"a\":1}'` inside single quotes emits a literal
   backslash-quote; `json.loads` throws, the hook's `2>/dev/null || exit 0` swallows
   it, every case "passes".
3. **A test case the rule legitimately exempts.** The baseline string used
   `X 群里` while the regex deliberately excludes `群里/群内/群聊` — so the one row
   meant to prove the guard still bites didn't bite.

The common shape: **all-cases-agree is a smell, not a green light.** `test_hook.sh`
resists all three because it asserts an explicit `expected-exit` per row (not "did
it print something") and forces trigger rows alongside healthy-lookalike rows — a
trigger row that returns 0 fails loudly instead of blending in. Always assert a
known-good trigger *first*; if it doesn't fire, fix the harness before touching the
hook's logic.

## Reference material

- [references/hook_patterns.md](references/hook_patterns.md) — runnable skeletons for every hook type covered here, the shlex command-position walker, and the JSON event contract.
- [references/hook_pitfalls.md](references/hook_pitfalls.md) — every real failure mode with symptom → cause → fix.
- [scripts/test_hook.sh](scripts/test_hook.sh) — end-to-end test harness; copy it next to any new hook.
