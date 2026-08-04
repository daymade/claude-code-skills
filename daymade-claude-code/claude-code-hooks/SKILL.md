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
(**Tier-0** here = an action whose damage cannot be undone from inside the session:
destroying uncommitted work, pushing secrets to a remote, deleting files, publishing
something outward. The test is reversibility, not severity.)

Do **not** reach for a hook when: the rule has never actually recurred (don't
pre-build guards for hypothetical mistakes — cost with no proven benefit), or
the "rule" is a judgment call with no mechanical signature (a hook can only
match tokens/patterns; it can't judge whether a design is good).

## Hook types and what the exit code means

| Type | Fires | Exit 0 | Exit 2 | Other |
|---|---|---|---|---|
| **PreToolUse** | before a tool runs | allow | **block** the call (stderr → shown to model as guidance) | any other exit = "non-blocking error" → **the call proceeds** |
| **PostToolUse** | after a tool ran | quiet **unless it prints a `hookSpecificOutput` JSON on stdout — that is how context injection works, and it happens at exit 0** | feedback to the model (can't un-run the tool) | — |
| **SessionStart** | session begins | proceed | — | **always exit 0** — never block a session |
| **Stop** (+ `SubagentStop`) | the model is about to finish responding | let it stop | **block the stop** — forces the model to keep going (stderr → fed back as the reason) | loop safety: the hook checks `stop_hook_active` (necessary, **not** sufficient — rule 7). The harness's consecutive-block ceiling (default 8) is **not** a general backstop — its counter resets on any continuation that executed tools, so it never arrives for a hook whose remediation involves tool calls, which is most of them (#27). Carry your own bound. All Stop hooks for an event run **in parallel** — one block round can carry several hooks' feedback |

- **PreToolUse** is the workhorse — the only one that can *stop* an action.
  `matcher` selects the tool (`Bash`, `Agent`, `WebFetch`, …). Exit 2 blocks and
  the hook's **stderr** becomes the message the model sees — so put the *why* and
  the *correct alternative* there, not just "blocked".
- **PostToolUse** can't undo, but it can **inject authoritative context** so a
  later hallucination can't stand (e.g. re-read the real git HEAD after a commit
  and surface it — the model can't "believe it committed" against injected truth).
- **SessionStart** is for **health checks of the guard rails themselves** —
  silent when healthy, warn on breakage, always exit 0.
- **`set -euo pipefail` vs `set -uo pipefail` — pick by contract, and know there
  are two ways to keep an always-exit-0 contract.** A hook that may block
  (PreToolUse) wants `-e`: an unexpected failure aborting the script is
  survivable, because the caller treats a non-0/2 exit as "proceed". A hook whose
  contract is **ALWAYS exit 0** (PostToolUse injectors, SessionStart checks) has
  two honest shapes: (a) **drop `-e`** and `||`-guard every risky command —
  with `-e` on, one `grep` that legitimately finds nothing kills the hook
  mid-way and the CLI surfaces a bare `Failed with non-blocking status code`
  (pitfall #8, Pattern E's shape); or (b) **keep `-e` and add `trap 'exit 0' ERR`**
  so any failure still converts to exit 0 while `-e` keeps guarding the plumbing
  (`git-commit-headcheck`'s production shape, Pattern D). Either is correct;
  what you cannot do is `-e` alone with no trap and no `||`-guards. Rule of
  thumb: **`-e` for hooks that decide; for hooks that report, drop `-e` or trap
  it** (pitfall #8).
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
  Pattern E in [references/hook_patterns.md](references/hook_patterns.md).
- **Stop has two block channels with identical loop protections — pick by
  intent, and make the first (only) block carry everything.** `decision:
  "block"` + `reason`, or plain exit 2 + stderr, shows as a hook *error* — for
  hard gates ("this must not stand"). `hookSpecificOutput.additionalContext`
  shows as neutral "Stop hook feedback" with no error notification — for
  coaching and reminders the model should weigh, not gates. Both count toward
  the same consecutive-block ceiling from the table above, so the choice is
  tone, not safety. What that means for message design: a blocked retry
  round (`stop_hook_active: true`) is let through **with whatever violations
  remain** — so a Stop guard gets exactly **one** informed bite. (The ceiling
  reinforces this only when your remediation is "rewrite the reply"; if it
  involves tool calls the counter resets and the ceiling never lands — #27.
  Either way the one-bite conclusion holds, because it rests on the latch, not
  on the ceiling.) Report *all* findings in that
  one block (a guard that prints only the first loses the rest permanently —
  pitfall #17), and write the message as an escape manual naming the exact
  acceptable fix, not a verdict — the model converges in one round or it burns
  the cap guessing. v2.1.145+ inputs `background_tasks` / `session_crons` let a
  blocking hook tell "the session is done" from "the session is merely paused
  waiting for background work" — blocking a pause forces pointless
  continuations and wastes the same cap.

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

## Rules that separate a working guard from a session-poisoning one

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
- **Right**: tokenize the whole command with the **`shlex.shlex` class**, not the
  `shlex.split()` function — `split()` only treats `| ; & < >` as separators when
  they are space-separated, so `ls|TRIGGER x` tokenizes to `['ls|TRIGGER', 'x']` and
  your command-position check never sees `TRIGGER` at all (measured; the class with
  `punctuation_chars=True` yields `['ls', '|', 'TRIGGER', 'x']`). Use the walker in
  [references/hook_patterns.md](references/hook_patterns.md#the-shlex-command-position-walker)
  verbatim rather than reaching for the one-liner. A quoted
  `"a|TRIGGER|b"` stays **one token**, so a regex argument is never mistaken for
  a command. Then check whether your target is in a **command position**
  (token[0], or right after a `;`/`&&`/`||`/`|` separator, skipping `VAR=val`
  env-assignment prefixes). Command-position walker in
  [references/hook_patterns.md](references/hook_patterns.md).
- Corollary: `echo "…TRIGGER…"`, `grep TRIGGER`, `# TRIGGER`, `man TRIGGER` must
  all pass. Your test set MUST include these mention-not-execute cases.
- **Corollary — exempt `git` write segments before they reach the walker.** A
  commit message is arbitrary data, and the whole message text reaches your
  command-position walk as pseudo-command-text — `git commit -F - <<EOF` with a
  body quoting `foo|TRIGGER` lands `TRIGGER` in command position, and the guard
  blocks its own fix commit (pitfall #7 is exactly this, shipped). Any Bash guard
  that inspects command strings must skip segments whose head is `git` +
  `commit`/`rebase`/`tag`/`am`/`cherry-pick` — and do it at the whole-command
  level, before any line splitting (Pattern A shows the order; the production
  version is `lib-git-commit-detect`'s adjacency check).
- **Corollary — the walker is two-stage for a reason.** `whitespace_split=True`
  treats newlines as ordinary whitespace, so a multiline block
  (`cd /x\ngit add\nTRIGGER -y`) collapses into one segment headed by `cd` and
  the trigger is never in command position — replayed trigger rate 0 on real
  transcripts (pitfall #11). Split into lines **shell-aware** first (quote state
  and backslash continuations honored, so quoted multiline strings don't
  fragment), then shlex-walk each line — both Pattern A and the walker section
  ship that splitter (`split_shell_lines`, production-proven in qlmanage-guard).
  What even it cannot parse is a heredoc body (not quote syntax); when to accept
  that residual is #11's call.
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
  (The boundary: regex when the predicate is "is this a specific common command
  at all" — `git commit`, `git push` — whose own message/arguments are what breaks
  tokenizing; walker when the predicate is "is a *banned* command or modifier in
  command position" — there the banned thing is rare and a ValueError fail-open
  errs safe, Rule 1's direction.)

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
(skill-creator's `skill-development-methodology` reference, Phase 6), applied to
a hook instead of a skill. In one such pass, 3 lenses (matching
logic / shell-embedding safety / event-contract robustness) surfaced 13
confirmed, independently-reproduced bugs and 1 finding whose own cited
evidence turned out to be a hallucinated doc quote — caught only because the
verifier was required to curl the raw source and grep for the exact string
rather than trust the citation.

### 3. SSOT + symlink so a reinstall can't silently disarm the guard

Real script in a version-controlled dir, **symlinked** into the hooks dir Claude reads:
```
~/scripts/claude-hooks/<name>.sh      # SSOT (this setup: a private git repo)
~/.claude/hooks/<name>.sh             # symlink → SSOT

# install / recover:
ln -s ~/scripts/claude-hooks/<name>.sh ~/.claude/hooks/<name>.sh
```
A `~/.claude` reinstall wipes the hooks dir; the symlink target survives, and
recovery is one `ln -s`. A dangling symlink disables a Tier-0 guard with **zero
signal** — which is why a SessionStart health check exists (rule 4; runnable
skeleton: Pattern C in [references/hook_patterns.md](references/hook_patterns.md)).

### 4. Registration is per-profile — converge ALL profiles, release via a HUMAN gate

- A hook in `~/.claude/hooks/` protects **nothing** if the *active profile's*
  `settings.json` doesn't call it. Multi-profile users ran with zero guards until
  every profile was converged. Register in the **main** profile's settings
  (`~/.claude/settings.json` in this setup; the Registration section of
  [references/hook_patterns.md](references/hook_patterns.md) has the exact jsonc
  shape) — PreToolUse → matcher `Bash` → your hook — then converge the rest (this setup
  uses `sync-profile-settings.py --all`, owned by the `claude-switch-models-setup`
  skill). A SessionStart health check greps each profile for the Tier-0 guards to
  catch drift. Settings edits are picked up by the CLI's file watcher (official
  hooks docs), so registration is live without a restart — confirm by watching
  the guard fire on a safe probe, or at next session's health-check line.
- **If the guard needs a release valve, make it a *human* gate, not an env var.**
  A static `GUARD_OK=1` escape hatch is no gate — the model can set the env var
  itself. Replace with: a native macOS dialog (`osascript` — model can't click)
  and/or a typed `YES` on `/dev/tty` (model can't type into the user's terminal);
  refuse/cancel/timeout = hard NO; log every prompt/bypass to an audit file.
  Pattern in [references/hook_patterns.md](references/hook_patterns.md).

### 5. Decide the failure **direction**, and test *that* — not just the happy path

Rule 1 ranked *detection-tuning* errors: given that the guard ran, false-blocking a
healthy command beats missing a rare bad one, because a guard people must bypass
gets bypassed reflexively. **This rule is about a different axis — the guard's
machinery not running at all** — so "which is worse" is not being reversed here;
the two rankings never meet. A tuning miss costs you one case; this costs you the
guard, silently, on every input of that shape.

The failure: the guard **cannot obtain the thing it judges on** — a parse throws, a path doesn't
resolve, a dependency is missing, a subprocess times out — and the very
`2>/dev/null || true` that stops the hook from crashing quietly converts *"I could
not check"* into *"nothing to report."* The hook exits 0. **That output is identical
to a real pass**, which is why this survives for weeks.

So at every point where the hook *obtains* something (parses the command, reads
staged files, queries a service), decide explicitly: **if this comes back empty, does
that mean allow or block?** — and write the answer next to the branch. Fail-open is
often right for a *modifier* check (does this carry `--no-verify`? missing it costs
you one case). Fail-closed is usually right for the *is-this-even-the-thing* check
(is this a cross-domain commit? an empty answer means the guard never fired at all).

**Then test the direction, not the happy path**: hand it an unresolvable path or an
unparseable command on purpose and assert it still does what you decided. A suite
where every row passes *because the hook silently allowed everything* is
indistinguishable from a suite that passes.

**Read those results carefully — the same input has opposite correct answers for
different guard classes.** Take `cd ~/no-such-dir && TRIGGER`:

| Guard class | Judges on | Correct exit | Why |
|---|---|---|---|
| **Token matcher** (is this a banned command form?) | the command text alone | **2, block** | `TRIGGER` is right there in the text; an unresolvable `cd` doesn't make it not-a-trigger, and if the guard goes quiet here it will also go quiet on `cd ~/real-dir && TRIGGER` |
| **State deriver** (does the repo's staged set span domains?) | state read from disk | **0, allow** | `cd` fails, `&&` short-circuits, no commit ever happens — there is nothing to guard |
| **Termination-state reader** (has the remediation already happened?) | a receipt / counter file (rule 7) | **0, allow** — *when the state file IS the termination condition* | an unreadable receipt means the hook cannot know it already fired; failing closed here blocks forever with no remediation possible and no human-visible cause — that *is* the loop, and it is the one failure worse than a missed case. **Inverted sub-case — read this before copying the row:** when the state is only a **budget on top of an independent predicate** (the block still clears by doing the work), allow-on-unreadable **silently disables the entire hook** — one unwritable directory makes it mute for every input, forever, which is the worst failure shape there is. There, fail back to *the behavior before the budget existed* (keep evaluating the predicate), not to silence. **Tell the two apart with one question: if the state vanished, would remediation still be possible?** No → receipt case, allow. Yes → budget case, keep checking |

So decide which class your hook is *before* writing the row, and the harness's
`unresolvable path` template row expects **2** because that template targets the
token-matcher class. Getting this backwards produces a confident FAIL against a
correct guard. For a state-deriving guard the failure you are hunting is: **the command would really
have run and the guard didn't see it** — an unbalanced quote makes tokenizing throw,
the fallback allows, and a genuine cross-domain commit ships with no dialog (rule 1's
ValueError note). Ask of every allowed row: *would this command actually have done
the thing?* If no, the allow is correct.

Running this exact probe against a real state-deriving guard returned two allows on
the first pass: one was correct (the short-circuit above) and one was a genuine
fail-open. **The probe finds things; you still have to classify what it found** —
which is why the class table above comes before the rows.

Real case (2026-07-22): a scope guard read staged files via `git -C "$REPO_DIR"`
with `REPO_DIR` parsed out of the **command text** — so `cd ~/repo && git commit`
handed it a literal `~/repo`, `git -C` failed, staged came back empty, and the guard
concluded "no cross-domain files, allow." Every cross-repo commit went unguarded and
nothing ever looked wrong. Anatomy + the shared-library twist: pitfall #10.

That parser has a second failure direction, and it is the nastier one. Once you
add a fallback so it stops failing open, the fallback becomes correct for one
reason and wrong for another — and both print the same line. `git push` (no
explicit target) legitimately falls back to the event's `cwd`; `git -C "$R" push`
*names* a target the hook cannot resolve, falls back to the same `cwd`, and then
renders a confident ✅ about a different repository. Those two cases render
byte-identically (measured, MD5-equal), so neither the hook nor the reader can
tell the honest verdict from the misbound one. **A fallback value must carry the reason it was
chosen**, and only "no explicit target" earns a verdict. Full anatomy, the
confused-deputy framing, and why fixtures with literal paths never catch it:
pitfall #28.

### 6. Judge on a fact the world can answer — never on your own rendering, never on a naming habit

Rules 1 and 5 are about *how* you match and *which way* you fail. This one is
about **where the thing you match on came from**, and it has two failure shapes
that both go silent:

- **Never branch on a string you formatted for a human.** If the hook builds a
  report — sorted, joined, truncated to the first N with a `(+M more)` tail — and
  then pattern-matches its own decision against that report, the branch inherits
  the rendering's losses. Items past the cutoff simply do not exist to it, so the
  branch works on every small fixture and stops firing on exactly the large
  sessions it was built for. Emit the machine fact on its own channel (one
  untruncated `KINDS:a,b,c` line) and match *that*. A rendering is an output, not
  a data source (pitfall #12).
- **Prefer a checkable fact over a naming convention.** Classifying by path shape
  (`/skills?/[^/]+/references/`) encodes one directory layout; a repo laid out any
  other way is classified `None` — silently, forever. The fix is *not* to widen the
  pattern, which trades a silent miss for machine-wide false positives (rule 1
  forbids exactly that trade); it is to ask a question the filesystem can answer —
  *is there a `SKILL.md` beside this `references/` directory?* Facts survive
  layout changes; conventions do not. (When the candidate **is** a `SKILL.md`,
  there is no sibling to ask about — classify by basename; #13 explains why that
  is a spec-defined fact and not the naming habit this rule warns against.)

The tell for both: a branch that has never once fired in production while its
tests are green. Print the raw pre-formatting classification and you will see
which of the two you have.

### 7. If the hook **demands remediation**, prove the loop terminates

A hook that **blocks** (exit 2) until X is done — Stop hooks especially, since
they re-fire on every subsequent stop — is not a check, it's a **feedback loop**.
(A hook that merely *injects* a demand and exits 0 has no loop at all: nothing
re-evaluates. That is mechanism 0 below, and it is the right default more often
than people reach for it.)

```
condition T is true → hook demands remediation R → model performs R → T checked again
```

**If completing R can make T true again, the loop does not converge.** Nothing
errors, nothing crashes; it burns round after round until a human interrupts —
which is what usually happens, because each round is a *complete* remediation
cycle (dispatch, wait, adopt, edit), not a cheap retry. **And that same
property is why the harness's 8-consecutive-block ceiling will not save you:
its counter resets on every continuation that executed tools, so a remediation
cycle made of tool calls keeps it pinned at 1 forever** (measured — #27). Even
where it does arrive, it is a backstop against a runaway session, not a design:
the turn ends with the violation still standing, and the harness reports that
turn as `reason:"completed"` — indistinguishable from genuinely finishing.
"It eventually stops" is not termination in any sense you want, and here it
does not even eventually stop. `stop_hook_active` does *not* save you here — that field covers
exactly **one layer of re-entry** ("the stop I just blocked is being retried").
It says nothing about the *cross-turn* case, where the model genuinely goes off
and does R (real work, many tool calls), then stops naturally: that is a brand
new Stop, the field is `false`, and the hook fires again on the same grounds.

**The test, borrowed from termination proofs in program verification** — a [loop
variant / ranking function](https://en.wikipedia.org/wiki/Loop_variant): write
down a quantity **V** mapping into a well-founded order (usually just ℕ), and
show that **V strictly decreases across every `trigger → remediate → re-check`
cycle**. No V, no termination proof — don't register the hook.

**V is a design-time obligation, not code** — you never compute it in the hook.
What ships is the *predicate* (the mechanisms below); V is the argument that the
predicate converges. Put it where the next reader will trip over it — the script
header:

```bash
# TERMINATION: V = 1 - exists(<receipt path>)
# decreased by: R writes the receipt; nothing R does afterwards can remove it.
```

"Show it decreases" is three concrete questions, and the answers go in that
comment:

1. **What does R change?** Name the exact file / field / timestamp.
2. **Is that thing an operand of T?** If yes, and R moves it back toward "fire" →
   there is no V.
3. **After R, what is the smallest input that makes T true again?** If the answer
   is "the same input I just fired on" → there is no V. Redesign the predicate;
   do not retune the threshold.

**A real counter-example.** A Stop hook required an independent review before
compounding artifacts (rule files, skills, other hooks) could be pushed:

- **T** (the condition that makes the hook **fire**) = "there are edits no review
  has covered", implemented as the timestamp comparison
  `last_edit > last_review` (`last_edit` = newest mtime across the artifact set,
  `last_review` = mtime of the review record — two single numbers, which is
  exactly what makes the comparison feel safe)
- **R** = dispatch an independent reviewer

But a review that is worth running **has output**: its findings get adopted **by
the same agent, immediately, before it next tries to stop** → that produces new
edits → `last_edit` moves past `last_review` → **T is true again**. (If a human
adopted them later, out of band, there would be no loop — the loop needs the
remediation and the re-check inside one agent's turn, which is exactly what a
Stop hook guarantees.) There is no V — remediation doesn't decrease a quantity, it *resets*
one. The only escape is "review, then change nothing," which is precisely the
case where dispatching the reviewer was pointless. Observed: three consecutive
rounds, each a complete review-and-adopt cycle, exited only by the user saying
stop.

Two things make this hard to see. **The comparison looks perfectly reasonable in
isolation** — "the review must be newer than the last edit" is exactly what you'd
write. And that sentence is the **pass** condition — T is its negation. Copy it
into your head as-is, without that negation, and you are reasoning about the
wrong operand for the rest of the analysis; keep T oriented as the **fire**
condition. (Writing the *code* as an early-exit guard clause — `… && exit 0` — is
normal shell style and not what this is about; the discipline is about which
orientation you reason in. And note equality: same-second mtimes land on the pass
side, i.e. fail-open, which matches what this rule requires of state reads below.) Run the checklist
above and it falls out mechanically: R changes `last_edit` (Q1); `last_edit` is
an operand of T (Q2); the smallest input that re-fires T is the remediation's own
output (Q3) → no V.

**A second failure form: the predicate can't see the remediation at all
(observability gap).** The counter-example above is a temporal predicate that
remediation *moves*. A quieter failure of the same family: remediation happens,
but the channel the predicate reads it through doesn't exist in this
environment. Real case (2026-07-26, found by a full-fleet loop audit): a Stop
hook detected "an independent review happened" by scanning tool_results for
`agentId: <hex>` and reading `subagents/agent-<hex>.jsonl` — correct on the
main profile. Team-mode sessions use a different schema entirely (spawn
receipts `agent_id: <name>@session-<uuid>`, deliveries as `teammate_id`
teammate messages, files `agent-a<name>-<hex>.jsonl`) — zero matches, ever,
so `last_review` stayed `None` forever and every compounding-edit∧push turn
re-fired the demand: a false-positive loop, bounded to one block per stop
sequence but unbounded across turns, and its "2/2 fires" that session were
both on fully-reviewed work. Same family, different medicine: the temporal
loop needs a better *predicate*; the observability loop needs a better
*channel*. Add a fourth question to the checklist — **Q4: in every environment
this hook will run in, can the predicate actually SEE R happen?** For
transcript-reading hooks that means parsing a real session from each
profile/mode, not fixture-testing one schema. (The repair for the case above:
multi-schema detection + teammate deliveries excluded from turn boundaries so
they can't truncate the detection window — pitfall #20.)

**Pick by axis first, then by order — these are not five strengths of one thing.**
0 decides *whether to block at all*; 1 decides *which event to hang it on*; 2–4
are the *predicate's shape* (choose 1 and you still need one of 2–4). The 0→4
order is "how completely the loop is removed", and it runs **inversely to how
much you can enforce** — so take the first one that still gives you the
enforcement you actually need, not simply the first one.

0. **Don't block — inject.** If the demand is advisory (you want the model to
   *consider* R, not to be unable to finish without it), print it and exit 0.
   Nothing re-evaluates, so there is no loop to prove terminating. Right default
   for anything short of Tier-0, and the cost is honest: a reminder can be
   ignored, so say in the header that it is fail-open — rule 4's point stands,
   a gate the subject can walk past is not a gate. If you need a *gate*, use 2
   and pay for the receipt. Injection channel: Pattern D.
   ⚠️ **This option does not exist on Stop** — and rule 7's main subject *is*
   Stop, so read this before reaching for it. On Stop, `exit 0` means "let the
   turn end", so there is no later reasoning step for the text to land in; and
   `hookSpecificOutput.additionalContext` counts toward the same 8-block ceiling
   as `exit 2` (see the hook-types section), i.e. it is also a block. Stop has
   exactly two modes: gate, or silence. Choosing mechanism 0 on Stop therefore
   means **changing the event** — hang the injection on the tool call that
   produced the artifact (PostToolUse, Pattern D) — or admitting you wanted a
   gate after all, and going to mechanism 2.
   ⚠️ **"No loop" holds only if R isn't your own matcher's target.** An injector
   on `Bash` that tells the model to run `git ls-remote` fires again on that very
   command, and re-injects. Same shape, softer — the model can ignore it, so
   there is no forced iteration, but it is broadcast-on-repeat rather than
   nothing. Check that the R you recommend is not an action this hook matches.

1. **Move the check to the action boundary.** If what you want to gate is an
   *action* — a push, a publish, a delete — guard **the action** with PreToolUse
   instead of guarding **the turn** with Stop. **Stop-hook remediation loops are
   often action gates attached to the wrong event**, and this is the concrete
   case of "Stop is the odd one out, and the one most often reached for by
   mistake" from the hook-types section.
   **Be precise about what this buys.** PreToolUse only re-fires when the model
   *voluntarily retries the gated action*, and the model can always decline and
   end its turn normally. So it guarantees **the turn terminates** — the worst
   case drops from "the turn can't end" to "this action doesn't happen". It does
   **not** make a non-converging predicate converge: take the counter-example
   above, move it to PreToolUse unchanged, and the loop survives intact (push →
   blocked → review → findings adopted → new edits → retry → `last_edit` is ahead
   again → blocked). That case is sick in its **predicate**, not in its event, so
   you still pick a shape from 2–4. Note also that PreToolUse has **no** harness
   backstop — the 8-block ceiling in the hook-types table is Stop-only — so a
   self-resetting predicate moved here has *fewer* safety nets, not more.
   ⚠️ Two shapes where this mechanism is the wrong answer: **R has to be done
   with the very tool you gated** (a guard on `Edit` demanding you fix a file
   header first — deadlock, nothing can ever satisfy it), and **an action that
   recurs within one session** (a `git push` gate in a session that pushes five
   repos = five full demands; that is the density problem in the war story
   below, and mechanism 1 doesn't exempt you from it).

2. **Make "already remediated" an existence fact, not a temporal one — and key it
   on the thing that needed remediating.** Have R land an artifact and test *does
   it exist*; the key is what makes this work:

   ```bash
   KEY=$(git rev-parse HEAD 2>/dev/null || printf 'nogit')   # or a hash of the
   RECEIPT="${TMPDIR:-/tmp}/my-guard.${KEY}.ok"              # reviewed content
   [ -f "$RECEIPT" ] && exit 0            # V = 1 - exists, for THIS key
   ```

   `V = 1 - exists` is **per key**: it decreases exactly once per key and can
   never be pushed back up *for that key*. New work mints a *new* key — that is a
   new demand, not a re-arm. Both naive keyings fail: one global path makes the
   hook fire once per machine and then sit dead forever with zero signal, and a
   time-based key is the temporal predicate this rule exists to forbid. **A
   temporal predicate is almost always the wrong shape**, because the remediation
   you demanded is usually what moves the operand you compare against.
   ⚠️ If the **model** can create the receipt, this is rule 4's retired
   `GUARD_OK=1` escape hatch wearing a new hat. Have it written by something the
   model doesn't drive (the reviewer subagent's own output file, a git note), or
   accept that the hook is advisory and say so in its header.

3. **A ceiling on repetitions.** At most N reminders per session per target —
   `session_id` is the only stable key for this (it is on every event; see the
   JSON contract in Pattern references):

   ```bash
   SID=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('session_id','nosid'))" 2>/dev/null || echo nosid)
   CNT="${TMPDIR:-/tmp}/my-guard.${SID}.count"
   N=$(cat "$CNT" 2>/dev/null || echo 0); N=$((N+1)); printf '%s' "$N" > "$CNT"
   [ "$N" -gt 3 ] && exit 0                # V = 3 - N, reaches 0 and stays
   ```

   Crude, and deliberately blind to whether R actually happened — but *finite*,
   which is the property that was missing. Do **not** substitute `$$` or `$PPID`:
   each hook run is a fresh process, so those change every invocation and the
   counter never accumulates. Print the count ("reminder 2 of 3") — see the war
   story below for why that wording earns its place.

4. **Hysteresis / a cool-down window** (the control-theory answer to
   [alert flapping](https://utcc.utoronto.ca/~cks/space/blog/sysadmin/HysteresisMeaningAndAlerts)):
   after firing, suppress re-evaluation for a window — a stamp file plus
   `[ $(( $(date +%s) - <stamp mtime> )) -lt 900 ] && exit 0` (mtime is
   `stat -f %m` on BSD/macOS, `stat -c %Y` on GNU — as are the other snippets
   here). Right for conditions that *oscillate around a threshold*; **wrong** for
   conditions that remediation **resets** — those need 2 or 3.
   ⚠️ **Hysteresis supplies no V — it is a rate limiter, not a termination
   proof.** The loop ends only if the condition subsides on its own, and what
   ends it then is the world, not your hook. So its `# TERMINATION:` line has to
   name that external fact ("by the time the stamp expires, X has been resolved
   by &lt;whom&gt;"). If you can't write that line honestly, what you needed was 2
   or 3. (Family resemblance worth seeing: mechanism 0 is the limit case of both
   — mechanism 3 with the ceiling set to 0, or mechanism 4 with the window set to
   ∞. They differ in enforcement, not in termination.)

**Failure direction for the state itself (rule 5): fail *open*.** If the receipt
or counter can't be read or written — unwritable `TMPDIR`, sandbox, full disk —
**allow the stop**. This is the one place in this skill where fail-open is
mandatory rather than a judgement call: a termination mechanism that cannot read
its own state and blocks anyway *is* the loop, now with no human-visible cause.

**Prose in the demand text does not substitute for a converging predicate.** A
hook whose message says "if you judge this unnecessary, just finish again" still
costs a full remediation cycle every round, because a model that has been told it
must do X will usually do X. The escape hatch has to be in the **predicate**, not
in the advice.

**The testing requirement, and the easiest thing here to skip:** the self-test
needs an **"after remediation"** case — not just "fires when it should," but
**"stops firing once R is complete."** Without it, non-termination is
*structurally invisible*: every fixture is one isolated point-in-time judgment,
while non-termination is a property of the **sequence**. A suite that only
checks single points has zero coverage of convergence no matter how many cases
it has — which is how a hook can ship with a green self-test and still loop on
its first real encounter. The row pair that *can* see it (receipt absent → fires,
receipt present → quiet, with the setup/teardown a plain `run` row can't express)
is templated in `scripts/test_hook.sh` under "AFTER-REMEDIATION ROWS"; symptom →
cause → fix is pitfall #16.

**Termination proved ≠ it *feels* terminated (2026-07-25 war story).** A Stop
hook with a correct existence-fact V fired three times in one session — each
fire a legitimate *new* push from a *different* completed task, the mechanism
working exactly as designed — and the user's experience was still "why is this
thing stuck in a loop?" (No contradiction with mechanism 2's "nothing R does can
push it back up": **V is per key** — three distinct keys, three separate one-way
decreases. That is also the diagnostic when you can't tell which situation you
are in: if each fire carries a *new* key, the mechanism is right and the density
is the problem; if repeated fires share the *same* key — or the predicate has no
key at all because it compares timestamps — you are in the counter-example above
and the predicate needs replacing.) Three independent remediation cycles back-to-back are
indistinguishable from a loop from the outside. The variant-proof settles the
mechanism; it says nothing about **how many distinct remediations a session can
demand**. If your domain produces that density (compounding artifacts ship
several times a day here), consider pairing mechanism 2 (the existence fact) with
mechanism 3 (a session-scoped ceiling), or accept the optics deliberately and say so in the
hook's output — "reminder 2 of at most N" reads as progress, an unadorned
repeat reads as a loop. **(2026-07-26 sequel: the same hook's fires that looked
like this density problem turned out to be 100% false positives — its review
channel was schema-blind in team mode; see the observability form above. Before
accepting density as "legitimate", verify the fires are evidence-based at all.)**

### 8. Waiting needs the same proof — notifications are advisory, polling must carry a budget

Rule 7 covers loops a *hook* creates. The same shape recurs with no hook
involved: **an agent polling for an asynchronous result** — a subagent's
report, a background task's completion notice, a CI status. Real session
(2026-07-25): subagent completion notices arrive through a mailbox that can
delay or drop them; three separate agents finished their work while the
notification sat undelivered, and the waiting agent burned a dozen
`sleep 240` + nag cycles over ~40 minutes until the human asked what it was
even doing. Nothing errored; the loop just had no variant.

Rule 7's mechanisms map over — the first two directly; hysteresis has no
analogue (a wait doesn't oscillate), and its slot is taken by a trap specific to
waiting:

1. **Poll the artifact, not the notification.** If what you actually need is a
   result (a file, a git ref, an API state, a row in a DB), wait on *that*, not
   on "did it say it's done." The notification is a hint; the artifact is the
   fact. An existence check terminates the moment the fact lands, regardless of
   whether any message ever arrives.
2. **Every wait carries a budget, chosen when the loop is written.** Max rounds
   × interval (e.g. 3 × 4 min), and a degradation path that exists *before* the
   first sleep: do it yourself, ask the user, or mark it pending and move on to
   other work. "Wait indefinitely and see" is not a degradation path — it's
   the loop.
3. **Delivery protocols are advisory, not mechanism.** "Report back via
   SendMessage when done — silence counts as incomplete" is worth writing, but
   it governs whether the agent *sends*, not whether the mailbox *delivers*.
   Three agents with the protocol in their prompt all went silent in one
   session. Design the wait as if the notification may never arrive — because
   it may not.

Two adjacent traps, both paid for in the same session: **TaskStopping a
"stuck" agent that is actually mid-work** — mailbox delay is not idleness;
one reviewer doing 20 minutes of real corpus testing was killed as "stuck"
minutes before delivering. And **`--dry-run`-style probes of the wait itself**:
before concluding the other side is silent, confirm your own observation
channel works (in that session, System Events window-counting returned a
confident 0 for a dialog that was on screen — a permission failure masquerading
as evidence).

## Build order (in sequence)

1. **Confirm it's a real recurrence**, not hypothetical — else don't build it.
   If the hook will **demand a remediation** rather than just block, write its
   termination variant **V** into the script header as a `# TERMINATION:` line
   (rule 7) before any logic — and first check whether the thing you're gating is
   an *action*, in which case a PreToolUse guard on that action removes the loop
   instead of taming it. Can't name a quantity that strictly decreases per
   `trigger → remediate → re-check` cycle? The design is non-terminating — fix the
   design, not the regex.
2. Write the script in the SSOT dir; `chmod +x`.
3. **Detection** with shlex token-level matching (rule 1), keyed on a fact the
   world can answer rather than your own rendering or a naming convention (rule 6).
4. **`bash -n` + `test_hook.sh`** with trigger AND healthy-lookalike cases (rule 2) — do not register until green. Include the shapes that carry an unexpanded path (`cd ~/elsewhere && …`, rule 5); if the hook has a human gate, a forced-decline row (Pattern B, "Make the gate testable"); and if it demands remediation, the **after-remediation row pair** — fires without the receipt, quiet with it (template in `scripts/test_hook.sh`; rule 7 — point-in-time fixtures structurally cannot see non-termination).
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
under-registration, a commit message reaching the walker as pseudo-command-text
and false-blocking your own fix commit unless `git` write segments are exempted
(#7), and a path parsed from command text keeping its literal `~` so
the guard fails **open** with no symptom at all (#10 — the one you cannot wait to
notice, because silence is its only sign), a branch reading the hook's own
truncated display string (#12) or keyed on a naming convention this repo doesn't
follow (#13) — both invisible while the suite asserts only exit codes (#14) —
command text that merely *contains* a redirect counted as a write (#15), and a
hook whose **demanded remediation re-arms it**, looping with a green self-test
because point-in-time fixtures structurally cannot see non-termination (#16,
rule 7).

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
   a string the rule *deliberately exempts* (the guard flagged coined nicknames of the
   form `<name> Group`, but exempted the ordinary phrases `in the group` / `group chat`
   — and the baseline row happened to use one of those). The one row meant to prove
   the guard still bites didn't bite, and the whole suite read green.

**And if the hook's product is its message, exit codes cannot test it.** A
blocking hook's contract is mostly its exit code, so `run` rows cover it. But a
hook that exists to *say* something — a PreToolUse explanation of the correct
alternative, a Stop reminder — has a second output channel the codes never see:
break the wording, invert a conditional paragraph, let a heredoc swallow a
section, and the exit code stays exactly 2 while every row passes. Add
`says <label> <event> <pattern> <yes|no>` rows from `scripts/test_hook.sh`,
asserting **both polarities across two fixtures** (present for the input it
targets, absent for the lookalike it skips) — a lone `want=no` passes vacuously
when the hook prints nothing at all, so it only means something beside a
`want=yes` row proving the hook speaks. Match **fixed strings**, not regexes: the
phrases worth asserting often contain brackets, and as a BRE `[skill]` is a
character class matching any text with an s, k, i or l in it. Then **mutate to prove the rows can die**: copy the hook, inject
the exact bug each row claims to catch, and confirm that row goes red. A green
suite carries zero information until you have watched it fail for the right
reason — two real bugs once survived a fully green 24-case suite because every
row looked only at exit codes (pitfall #14).

The common shape: **all-cases-agree is a smell, not a green light.** `test_hook.sh`
catches shapes 1 and 2 above structurally — it asserts an explicit `expected-exit` per `run` row
(not "did it print something") and forces trigger rows alongside healthy-lookalike
ones, so a trigger row that returns 0 fails loudly instead of blending in. It
**cannot** catch #3: whether a row's content accidentally lands in an exemption is a
property of what you wrote, and no harness knows your rule's intent. That one is
caught only by the habit — assert a known-good trigger *first*, and when it doesn't
fire, suspect the row before the hook.

## Reference material

- [references/hook_patterns.md](references/hook_patterns.md) — runnable skeletons for every hook type covered here, the shlex command-position walker, and the JSON event contract.
- [references/hook_pitfalls.md](references/hook_pitfalls.md) — every real failure mode with symptom → cause → fix.
- [scripts/test_hook.sh](scripts/test_hook.sh) — end-to-end test harness; copy it next to any new hook.
- [scripts/test_hook.group-name-guard.sh](scripts/test_hook.group-name-guard.sh) — a worked harness instance for a real Stop guard (event shapes, `says` rows, both polarities).

## Maintenance — where new content goes

New incident backports land outside this file, in the place that already holds
their kind: a fresh pitfall or failure anatomy →
[references/hook_pitfalls.md](references/hook_pitfalls.md); a reusable
skeleton or pattern → [references/hook_patterns.md](references/hook_patterns.md);
a worked harness instance (a test script) → `scripts/`. This file only takes
**contract-level rules**: content every blocking hook consumes (a new hook
type, a changed exit-code contract, a new rule in the `## Rules that separate
a working guard from a session-poisoning one` series). The loaded-at-trigger
surface stays stable while the knowledge base keeps growing; depth lives one
pointer away. (The "Known pitfalls" headliners above are a highlights list,
not an index — they have not been extended since pitfall #16; the numbered
catalog in `hook_pitfalls.md` is the SSOT, and a new pitfall does not owe a
headliner.)

Why this is written down (2026-08-02): backports have in fact always gone to
references — what grew this file 10k→50k chars in one week was *rules* prose
(rules 5–8 landing inline), which this policy deliberately keeps here. The
policy's job is to make the default explicit for the next session holding a
fresh incident, so future growth stays limited to contract-level rules. A
four-frame design review (cost / SSOT / architecture / evidence,
cross-examined) chose this over a structural split of the existing eight
rules. Restart-the-split criteria, for the next time someone proposes one: a
measurement (not a vibe) showing the main file's size degrades rule
compliance, or the whole skill's churn settling (30 consecutive days with no
new rule or backport landing anywhere).
