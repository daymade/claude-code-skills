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
  `whitespace_split=True`) — NOT the `shlex.split()` function (the `ls|TRIGGER x`
  divergence is measured in [hook_patterns.md](hook_patterns.md#the-shlex-command-position-walker),
  whose code comments carry it verbatim). Then check **command
  position**, not mere presence — walker in
  [hook_patterns.md](hook_patterns.md#the-shlex-command-position-walker).
- **Caveat — `whitespace_split=True` also swallows newlines.** If your commands
  can be multiline (`cd x\ngit add\ngit push`), tokenizing the whole string
  collapses every line into one segment and hides everything but the first line's
  head. Split on newlines as text *first*; see #11.
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
- **Fix (escape hatch) — you cannot Bash your way out of a broken Bash guard.**
  Every repair you'd reach for (`rm` the symlink, re-`ln -s`, edit `settings.json`
  with sed) is itself a Bash call, and a corrupted PreToolUse Bash hook inspects
  those too. Routes that do **not** go through the Bash tool, cheapest first:
  1. **Edit `settings.json` with the Edit/Write tool** (file tools don't fire the
     Bash matcher) and delete the hook's entry — instant disarm, no shell needed.
  2. **Start a session with a different config home**: `CLAUDE_CONFIG_DIR=<other>`
     — a profile whose settings never registered the broken hook. (Set it when
     launching the CLI, i.e. outside the poisoned session.)
  3. **Fix from outside**: any terminal not running under the agent, since the hook
     only exists on the agent's tool path, not on your shell's.
  This is also the argument for the SSOT+symlink layout: repair is one `ln -s` you
  can run from an ordinary terminal, not surgery on a live config.

---

## 4. A guard the model can bypass by itself (static env escape hatch)

- **Symptom:** the guard "exists" but the banned action still happens — the model
  set an env var to wave itself through.
- **Cause:** the release valve was a static `GUARD_OK=1` / `SCOPE_OK=1` env var.
  Anything the model can add to its own command is not a gate.
- **Fix:** a **human-confirmation gate** the model physically can't drive —
  full two-channel pattern (native dialog / typed YES, hard-NO semantics,
  audit log, testability) in
  [hook_patterns.md](hook_patterns.md#pattern-b--pretooluse-with-a-human-confirmation-release-gate)
  and the rule-of-thumb form in SKILL.md rule 4.
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
  the outer command carries no trigger, so it isn't self-blocked (mechanism in
  SKILL.md rule 2 and the harness header comment).
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
- **Fix:** every command feeding a substitution needs a `|| <fallback>` — the pipe
  included, and the `||` goes **OUTSIDE** the `$(…)`: `STAGED=$(git diff … | wc -l
  | tr -d ' ') || STAGED='?'`. Put it inside (`… | wc -l || echo '?'`) and `wc`
  still prints `0` when git fails, yielding the malformed two-line value `0\n?`.
  (2026-07-21 in git-commit-headcheck.)
- **Alternative shape — keep `-e` and trap the contract:** `set -euo pipefail` +
  `trap 'exit 0' ERR` converts every failure to exit 0 while `-e` keeps guarding
  the plumbing (git-commit-headcheck's production form; the choice between this
  and dropping `-e` is SKILL.md's "-e or trap" bullet).
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

  **The same parser has a second, sharper failure once you give it a fallback:**
  it then answers confidently about the wrong repository instead of failing open.
  Fixing #10 does not fix that — see #28. Note also that the shared-library
  reassurance above has a boundary: it protects the hooks that *source* the
  helper. A hook carrying its own inline parser inherits none of the fix and
  has to be patched separately (that is exactly how #28 survived #10).

## 11. Newline-blind segmentation misses the multiline command (fixtures pass, real corpus barely fires)

- **Symptom:** the hook passes every synthetic fixture (`git push origin main`,
  `cd x && git push`) yet fires far less than expected on real transcripts — in one
  incident its replayed trigger rate was **0** where the targeted population should
  have shown ~5%.
- **Cause:** the git operations this kind of guard targets are usually written as
  *multiline* blocks — `cd /repo\ngit add -A\ngit commit -m x\ngit push`. A
  segmenter built on `shlex.shlex(..., whitespace_split=True)` — the very tokenizer
  #2 recommends for quoting-safety — treats the **newline as ordinary whitespace and
  drops it**, so the lines collapse into ONE token stream with no separator token,
  yielding a single segment whose head is `cd`. The `git push` further down is no
  longer at a segment head, and the command-position check (#2) never sees it.
  Single-line fixtures cannot expose this: they have no newline to swallow.
- **Fix — two stages, and the order matters.** First split on **newlines only, as
  text** (`cmd.split("\n")`). Then, *within each line*, use #2's `shlex` tokenizer
  to segment on `;`/`&&`/`|` and walk for command position. This defeats the common
  #2 trap: a `|` inside `grep -E "a|git push|b"`, or an `&&` inside a *single-line*
  `git commit -m "… && git push"`, stays inside one `shlex` token, so no phantom
  `git push` segment is manufactured. Do **not** instead do the whole job with one
  quote-blind split like `re.split(r"[\n;]|&&|\|\||[|&]", cmd)`: that cuts those same
  separators *inside* quotes — pitfall #2, the worst bug in this file — and orphans
  the inner text from its `git commit` head, defeating #7's exemption.
- **Name its residual, don't hide it.** The text `cmd.split("\n")` is itself
  quote-blind about *newlines*: a newline **inside** a quoted string or a heredoc
  body still fragments. The clean witness is a heredoc — `git commit -F - <<'MSG'`
  whose body contains a bare `git push` line splits that line off and reads it as a
  command it isn't. (A multiline `-m "…\ngit push"` message fragments too, but its
  torn line has an unbalanced quote, so whether it over- or under-fires depends on how
  you handle the `shlex` `ValueError` — a witness for the same residual, less clean.)
  **2026-07-26 refinement (production qlmanage-guard, three review rounds with
  100+ executed probes):** split shell-aware instead — `split_shell_lines`
  (walker section / Pattern A) tracks quote state, backslash continuations, and
  `$'…'` ANSI-C escapes, which removes the *quoted-string* half of the residual
  (the `gh pr create -b "…\nTRIGGER…"` shape — more common than heredocs in real
  tool calls). What remains is heredoc bodies only: they are not quote syntax,
  so no quote-state machine can see them.
  Whether that residual is acceptable follows the same **bias-to-under** call as #2:
  for a **fail-open reminder** an extra over-fire costs nothing — declare it and move
  on; for a **fail-closed blocker** it re-creates #2's false-block, so you must lift
  #7's `git commit`/heredoc exemption to the **whole-command** level *before*
  splitting, or parse with a real shell grammar.
- **Why you only catch it with real data:** this is the `合成 fixture 全绿 ≠ 正确`
  trap — the fixtures you invent share the blind spot that wrote the bug (you think
  in one-liners; production is multiline). So replay the hook over a **real corpus**
  before shipping. And when a replay returns "0 / clean", treat the **harness
  itself** as a suspect too: a random-sample replay can read 0 purely because the
  sample was diluted (measure the *population that can possibly fire*, not a uniform
  sample), and a mutation test can report "survived" because the mutation never
  applied. Both are the same failure as the hook's own — the instrument lying in the
  safe-looking direction. Confirm the harness can report "dirty" on an input you have
  *independently proven* should fire, before you believe any "clean".

---

## 12. The decision reads the string built for humans — and that string is lossy

- **Symptom:** a conditional branch inside the hook works in every test and
  silently stops firing in production. Nothing errors; the branch just never
  matches, so a whole paragraph of guidance (or a whole check) disappears for
  exactly the sessions that needed it most.
- **Cause:** the hook computed a **display string** first — sorted, joined,
  truncated to the first N with a `(+M more)` tail — and then pattern-matched
  its own decision against that string. Truncation is lossy by design, so any
  item past the cutoff is invisible to the branch. The tests never showed it
  because a fixture has two or three items and a real session has ten.
  Real case (2026-07-23): a Stop hook reported `path [kind], path [kind], … (+N
  more)` and then did `case "$REPORT" in *"[skill]"*)`. A session that touched six
  artifacts with the skill sorting sixth dropped the `[skill]` tag out of the
  rendered list, and the skill-specific guidance vanished — in a hook whose entire
  target population is large multi-artifact sessions.
- **Fix:** emit the machine-readable fact on its own channel, never re-derive it
  from the rendering. One extra line is enough — a `KINDS:a,b,c` header line that
  is never truncated, with the human list below it, and the branch matches the
  header. General form: **a rendering is an output, not a data source.** If you
  find yourself grepping something your own code formatted for a reader, you have
  a second, undeclared parser of your own display format — and it will drift the
  moment you change how things look.
- **Test that pins it:** a fixture with **more items than the display cutoff**,
  where the item the branch cares about sorts *after* the cutoff. Without that
  row the bug is invisible; with it, reverting to the display-string match fails
  loudly.

---

## 13. Classification keyed on a naming convention the real layout doesn't follow

- **Symptom:** a whole category of input is never detected. Not misdetected —
  *absent*. The hook reports nothing for it, which is indistinguishable from
  "there was nothing to report."
- **Cause:** the classifier matched a path shape (`/skills?/[^/]+/(references|scripts|assets)/`)
  that encodes one directory convention. Real repositories use others. Real case:
  a marketplace repo lays skills out as `claude-code-skills/<suite>/<skill>/references/…`
  — not one path segment equals `skills`, so every edit to a skill's reference or
  script files was classified `None`. The pattern had been in the table for
  months, tested only against `~/.claude/skills/<name>/…`, which does match.
- **Fix — do NOT just widen the regex.** Widening to `/[^/]+/(references|scripts|assets)/`
  makes every repository on the machine with a `scripts/` directory match, trading a
  silent miss for pervasive false positives — the trade rule 1 explicitly forbids
  (误杀健康输入比漏报更糟). Key the decision on a **verifiable fact** instead: *is
  there a `SKILL.md` next to this `references/` directory?* One `os.path.exists`
  against the filesystem is layout-independent, cannot fire on an unrelated
  project, and stays correct when someone invents a new directory convention
  tomorrow. Wrap it so an `OSError` falls to the safe direction (rule 5).
- **When the candidate IS the anchor.** The question above is "is there a
  `SKILL.md` beside this `references/` directory", which has no answer for a path
  that *is* `…/myskill/SKILL.md`. Classify that one by basename — and note why
  that is not the naming-habit trap this entry warns about: `SKILL.md` is a name
  the platform's spec defines and the loader actually keys on, whereas
  `/skills?/` was a habit of one directory layout. The test is whether something
  outside your head enforces the name.
- **The general rule:** when a hook classifies a resource, prefer a check the
  world can answer (does this file exist, what does the API return, what is the
  actual git ref) over a check that only your naming habit can answer. Conventions
  are per-repo and per-era; facts are not. Reach for a name pattern only when
  there is no fact to query — and then say so in a comment, so the next reader
  knows it is a heuristic standing in for evidence.

---

## 14. The self-test asserts exit codes — but this hook's product is its text

- **Symptom:** the suite is green, the hook exits with the right codes on every
  row, and the message it prints is wrong, missing a paragraph, or emitting a
  section that should have been conditional. Nobody notices until a human reads
  the output.
- **Cause:** for a **blocking** hook the exit code *is* most of the contract, so
  exit-code assertions cover it. But a hook whose real product is the **stderr
  guidance** — a PreToolUse message explaining the correct alternative, a Stop
  reminder telling the model what to do next — has a second output channel that
  exit codes cannot see. Break the message body, invert the condition on an
  optional paragraph, let a heredoc swallow a section: the exit code stays
  exactly 2, and every row still passes. The suite is structurally blind to the
  only thing that hook produces.
- **Fix:** add content assertions alongside the exit-code rows, with the `says`
  helper shipped in [scripts/test_hook.sh](../scripts/test_hook.sh) — its header
  comment carries the full doctrine (both polarities across two fixtures,
  fixed-string matching because a BRE `[skill]` is a character class, and the
  mutation pass that proves each row can die), which SKILL.md's harness section
  repeats at rule length. Use the shipped helper rather than re-typing one — a
  copy in prose drifts from the one people actually run (this entry shipped with
  a copy that had no pass/fail counters, so a failing content row printed FAIL
  and the suite still ended "ALL PASS").
- **Then prove the assertions are not vacuous — mutate and confirm they die.**
  Copy the hook, inject the specific bug each assertion claims
  to catch (invert the branch condition, delete the fact-check, revert to the
  display-string match), and confirm *that* assertion goes red — and ideally only
  that one. Real case: four separate mutations each killed exactly their intended
  row; the same suite had previously been green while two real bugs (#12, #13)
  were live in the file, because no row looked at the text.

---

## 15. Command text that merely *contains* a write, treated as a write

- **Symptom:** a forensic hook (one that scans a transcript or command history to
  decide what a session touched) reports a file nobody wrote — sometimes a path
  that is obviously not a path, like `$AD/SKILL.md`.
- **Cause:** the hook extracts write targets from **command text**, and command
  text routinely carries *data that looks like commands*: a heredoc body being
  written into another file, a fixture string inside a `python3 -` script, a
  snippet of shell being embedded in documentation. The redirect it "found" was
  never executed in this process — it was cargo.
- **Cheap filter, and be honest that it under-reports.** Dropping any candidate
  path that still contains an unexpanded variable or a backtick —
  ``re.compile(r"[$\x60]")`` against the candidate — kills the common cargo case
  in one line. But **do not tell yourself this has no false negatives.** Command
  text is *pre-expansion* (that is #10's whole thesis), so a genuine
  `cat > "$OUT/file"` with `$OUT` set writes a real file whose path arrives with
  the `$` still in it — this filter drops that too. You are trading *missing some
  real writes* for *not inventing fake ones*, which is the right trade for a
  **fail-open reporter** and the wrong one for anything that blocks. Say which you
  are in a comment next to the filter.
- **The same class has a sibling this filter does not cover:** a literal `~`
  survives it, then silently fails whatever you do with the path afterwards —
  `cat > ~/skills/x/references/a.md` passes the `$` filter and then makes an
  `os.path.exists` check (#13) return False for a file that plainly exists. Run
  `os.path.expanduser` before any filesystem check, exactly as #10 requires.
- **The deeper case has no cheap fix, and #11 does not solve it either.** A
  fully-literal path inside a heredoc body needs real heredoc boundary tracking;
  #11 lists that same residual as *unsolved* on its own axis and points at "parse
  with a real shell grammar". So for a blocking hook the over-report is a false
  block and you owe it that parse; for a reporter, accept the noise and say so.
- **Why it matters beyond noise:** a false entry does not just add a line. If
  the hook branches on *kind* (#12), one phantom path of the wrong kind switches
  on guidance the session never needed — the reader is handed a procedure for
  work they did not do, which is exactly the "误杀" that trains people to stop
  reading the hook's output.

---

## 16. The remediation the hook demands re-arms the hook (a loop with no variant)

- **Symptom:** a Stop hook fires, the model does exactly what it asked, the hook
  fires again on the same grounds. Repeat until a human interrupts. No error, no
  crash, green self-test, and `stop_hook_active` **is** handled correctly.
- **Cause:** the hook's condition is a **temporal comparison** whose operand is
  moved by the very remediation it demands. Canonical **fire** condition:
  `last_offending_action > last_remediation`. Remediation that is worth doing
  produces work — findings get adopted, files get edited — so
  `last_offending_action` jumps back ahead and the condition re-arms.
  (Watch the orientation: what you naturally *write* is the **pass** condition —
  "the review must be newer than the last edit". T is its negation. State T as
  the fire condition or you will reason about the wrong operand.) The loop has
  no [variant](https://en.wikipedia.org/wiki/Loop_variant): nothing strictly
  decreases per cycle, so nothing forces termination.
- **Why `stop_hook_active` doesn't cover it.** It means "the stop I just blocked
  is being retried" — one layer of re-entry inside one stop attempt. This loop is
  *cross-turn* (real work, then a fresh Stop with the field `false`). Handling it
  is necessary and buys nothing here. Full contract: SKILL.md rule 7. **Nor does
  the harness's consecutive-block ceiling cover it** — that counter resets on any
  continuation that executed tools, and remediation worth demanding is made of
  tool calls, so it stays pinned at 1 (#27). Both runtime protections are blind
  to exactly this loop; the bound has to be yours.
- **Fix — change the shape of the predicate, not its threshold.** In order:
  (a) if what you're gating is an **action**, move the gate onto that action with
  PreToolUse instead of onto the turn with Stop — one evaluation per attempt, no
  cross-turn re-fire; (b) else test an **existence fact keyed on the thing that
  needed remediating** (`V = 1 - exists` per key — a global key kills the hook
  forever, a time-based key is the temporal predicate again); (c) else a
  per-session **repetition ceiling** (`V = N - fired`), crude but finite. Cool-down
  windows (hysteresis) fix a *different* problem — a condition oscillating around
  a threshold — not one that remediation **resets**. Runnable snippets and the
  design-time `# TERMINATION:` convention: SKILL.md rule 7.
- **The self-test row pair that can see it.** Same event, receipt absent → fires;
  receipt present → quiet, with `rm -f` / `: >` around them (the state lives on the
  filesystem, so a plain `run` row cannot express it). Template in
  [../scripts/test_hook.sh](../scripts/test_hook.sh), "AFTER-REMEDIATION ROWS". If
  the second row also fires, the predicate is temporal — fix the predicate, not
  the fixture.

---

## 17. A Stop guard that reports only the first violation loses the rest (the retry round is a full pass-through)
- **Symptom:** a Stop hook correctly blocks on finding X in the model's reply;
  the model fixes X and stops again — and the reply still contains violation Y
  from the same original turn, never reported, never caught.
- **Cause:** the hook printed the first finding and stopped looking. The retry
  round arrives with `stop_hook_active: true`, which the hook (correctly)
  honors by letting the turn end — so everything it did not say in round one
  sails through permanently. The anti-loop field that saves you from infinite
  re-entry is precisely what makes the first block your only informed bite.
  (The harness's consecutive-block ceiling does not rescue you either: banking
  on "I'll catch it next round" burns it when the remediation is reply-only,
  and never reaches it at all when the remediation involves tool calls — #27.)
- **Fix:** collect *all* findings before printing (cap the list — five is
  plenty — so a pathological reply can't flood the model's context), and write
  the message as an escape manual: each finding plus the exact acceptable fix.
  Test it: a two-violations fixture must exit 2 with BOTH in stderr — a suite
  that only ever feeds one violation per case structurally cannot see this.
- **Real case (2026-07-25):** a group-name guard reported only the first
  coined shorthand in a reply that coined two; the honored retry round fixed
  the first and ended the turn with the second intact. Found by an independent
  reviewer, fixed by collecting all matches (cap 5); regression row
  "多命中一次报全" pins it.

---

## 18. A blocked compound command silently discards the innocent segments' side effects

- **Symptom:** you fixed something and ran the gated command in the SAME Bash
  call (`fix_thing && gated_command`); the guard blocked it; next round the
  SAME error reappears — as if your fix never happened. You re-diagnose,
  "discover" the fix is missing, and only then realize why.
- **Cause:** a PreToolUse block prevents the **whole** command from running —
  including innocent segments (a heredoc updating a file, a map write, an edit)
  chained before or after the gated one. The block error names the gated
  segment, so all attention goes there; the innocent write's silent absence
  leaves no signal of its own.
- **Fix — two habits, one on each side of the block:** when *building*
  commands, put state-changing steps (file writes, edits, map updates) in their
  **own** Bash call, never bundled with a command a guard might block; when
  *recovering* from a block, re-verify every write you *assumed* had landed
  before the block (`grep` for the change) — "the error named the other
  segment" is exactly the situation where your side effect is gone. Real case
  (2026-07-25, twice in one session): a needle-fix heredoc bundled with the
  validation command; the tooling guard blocked the bundle; the validator
  re-reported byte-identical errors because the fix never landed — diagnosed
  only on the second identical failure.

---

## 19. A block whose remediation demands cross-call memory re-fires all session

- **Symptom:** the hook blocks, its message teaches the correct form, you
  comply — and get blocked again for the same reason. And again. (One session
  measured **10** blocks for the identical cause, plus 3 sibling failures —
  including a feature branch created in the *wrong repository*.)
- **Cause:** the remediation the hook demands is a **habit change that must be
  remembered across tool calls** — e.g. "always prefix this command family with
  `cd <tool-root>`" — and three things conspire against that memory, none of
  which is carelessness: **attention resets per call** (the model re-reads the
  lesson and re-forgets it each time, because at the moment of action the goal
  is the task, not the form); **shell state does not persist** (env vars and
  functions are re-initialized from the profile each call — so a remediation
  that relies on an exported variable dies with the call; only settings.json's
  `env` block or the shell profile makes one stick); and **environment drift in
  `cd` behavior** — the documented contract is that the working directory
  *does* persist between calls, yet harnesses/profiles deviate in practice, and
  a `cd` that *does* stick creates its own failure mode (the next command then
  runs in the wrong repo entirely — the sibling failure in the incident below:
  a feature branch created in the wrong repository, which could only happen
  *because* the directory persisted). The hook is correct every time, and it
  does not matter: the remediation's success depends on memory surviving
  boundaries it often doesn't survive, so the block re-fires until the session
  ends or the environment changes. (2026-07-25, one session: **10** identical
  blocks + those 3 sibling failures.)
- **Fix — pick the guard's answer deliberately, knowing the class:** (a) put
  the corrective *in the environment* instead of the message (a wrapper script
  that doesn't care about cwd, a `PYTHONPATH` or variable set in settings.json's
  `env` block or the shell profile — an ad-hoc exported var dies with the call,
  per the Cause above) so the habit is no longer required — strongest, because
  it removes the dependency; (b) convert the block to a fail-open reminder for
  habit-class rules (a noisy PreToolUse block trains bypass exactly as #2
  warns); (c) accept and *measure* the repetition as the cost of enforcement —
  10 blocks can mean "guard working, loudly", but then say so in the header so
  nobody "fixes" it. What does not work: making the block message clearer. It
  was clear every one of the 10 times.

---

## 20. Agent deliveries counted as turn boundaries truncate the detection window

- **Symptom:** a turn-scoped transcript hook (one that judges "did X happen
  THIS turn") goes **quiet** even though unremediated work is sitting right
  there — or its review-tracking never registers completed reviews. Nothing
  errors; the reports just stop matching reality.
- **Cause:** agent deliveries (teammate messages / completion receipts) arrive
  as `type: "user"` records in the transcript. A turn-boundary rule that treats
  every user message as a new turn lets **every delivery start a new "turn"** —
  work done *before* the delivery falls outside the window. Real audit
  (2026-07-26): the last turn-start in a long session sat 6 lines from the
  transcript tail — the entire audit's edits and pushes were outside the window,
  so a compounding-artifact hook reported nothing. The twin blind spot in the
  same incident: the review channel itself was built on one schema
  (`agentId: <hex>` in tool_results) while the environment used another
  (`agent_id: <name>@session-<uuid>` + `teammate_id` deliveries), so no review
  ever registered either — false quiet and false fire coexisting in one hook.
- **Fix:** treat deliveries as events *inside* the turn, not as boundaries.
  Exclude them by wrapper form — content starting `"Another Claude session sent
  a message:"` / `<teammate-message` — in **both** content branches (string and
  list), and audit every other system record the same way (isMeta injections,
  interrupt receipts — compounding-edit-review's `is_turn_start` is the working
  example; its selftest ⑰ pins "teammate must not truncate the window"). And
  validate the *channel* per environment: parse a real transcript from every
  profile/mode you run in — fixture-testing a single schema is how the twin
  blind spot shipped (rule 7's observability form, SKILL.md).

---

## 21. Prefix-based resolution must anchor on a typed tail

- **Symptom:** the hook resolves an entity by glob/prefix (a file, a name, a
  token family) and silently picks the WRONG one — a verdict meant for agent A
  lands on agent B, and the decision is inverted: a delegated write-and-push
  gets the "independent review" stamp, or a genuine review reads as delegation.
  Nothing looks wrong because each file in isolation is valid.
- **Cause:** prefix matching ignores that names are **prefixes of other names**.
  Real case (2026-07-26, reproduced both directions): a review-detection hook
  resolved agent transcripts with `agent-a<name>-*.jsonl` — the agent pair
  `r4-final-reviewer` and `r4-final-reviewer-2` (which really coexisted in the
  session) both matched, and "newest by mtime" made the review read the wrong
  agent's file. Sibling shapes in the same audit: a bundle-arity blind spot
  (`-mn` = `-m n`, not `-n`), a flag-family table (`-am"msg"` attached value),
  and a trailing-separator reset (a state machine whose `first` slot is
  re-zeroed by a trailing `;` or comment line, losing the last real segment).
- **Fix — anchor the typed tail, never the bare prefix:** for filenames,
  require the delimiter + a typed suffix (`agent-a<name>-[0-9a-f]{8,}.jsonl`,
  not `agent-a<name>-*`); for flag families, enumerate the family (`-aXXX`
  bundled counts as `-a`) AND model arity (after a valued flag, the next thing
  is data); for segment state machines, keep the last NON-EMPTY segment's head
  (`last_first`), never the current slot after a trailing separator. Then pin
  the colliding pair in a fixture — a singleton passing proves nothing about
  resolution (compounding-edit-review's selftest grew exactly these).

---

## 22. A hook fleet on every tool call is a fork multiplier — the irrelevant path must cost zero forks

- **Symptom:** the machine runs hot and the battery drops fast under several
  parallel agent sessions; a spawn-rate recorder shows a sustained 40–177
  forks/sec (peak, scaling with session count and agent activity) all day,
  and `syspolicyd` (Gatekeeper) tops the all-day CPU-integrated ranking with
  NO single runaway process. Nothing is "broken" —
  every process has a legitimate owner. Treating this as "normal because it's
  owned" is the mistake: an unthrottled loop and a runaway are structurally
  identical to the system underneath.
- **Cause:** each PreToolUse Bash hook that opens with `INPUT=$(cat)` plus one
  or more `printf … | python3 -c …` parses costs 2–3 forks **even when the
  command is irrelevant to that guard**. With ~13 hooks on the Bash matcher ×
  several parallel agent sessions × sub-second tool-call cadence, that alone
  is 40–200 forks/sec of pure guard overhead, and every `exec` also bills
  `syspolicyd` a Gatekeeper evaluation — which is how a distributed,
  by-design load lands on one system daemon's CPU total. The fleet is fine;
  the per-call cost of the *irrelevant* path is the bug.
- **Fix — the 0-fork fast path, with semantics preserved per guard type:**
  1. Replace `INPUT=$(cat)` with the builtin `IFS= read -rd '' INPUT || true`
     (stdin can only be read once — hand the captured var to the existing
     code, do not leave a later `$(cat)` to read EOF).
  2. Coarse-filter with a **builtin** `case`/`[[ == ]]` on the raw JSON and
     `exit 0` before paying for python3/jq. The filter must be *broader* than
     the hook's decision domain and **never flag-level**: shell normalization
     (`--no-\verify`, `-n` short forms, `VAR=val` prefixes) produces real
     flags that byte-matching cannot see — filter only on "is this command
     even about X" (e.g. `*git*`; `*openrouter*|*claude.ai*` for a domain
     guard). Case-handling: **never narrower in case than the real check** —
     a case-sensitive coarse filter feeding a case-insensitive real check
     silently under-blocks; broader case (e.g. `nocasematch`, or glob bracket
     classes on bash 3.2) is always safe, it only costs a fall-through.
  3. **Fail-closed guards need a legitimate-payload gate — and a marker
     substring alone is NOT enough.** A bare coarse filter exits 0 on
     malformed input the original fail-closed parse layer would have blocked
     — measured: `'not json'` sailed through the first cut of this fix and
     the guard's contract silently changed from block-unknown to
     allow-unknown. But a `*tool_name*` substring gate re-opens the same
     hole from the other side: `echo 'tool_name'` (marker present, not
     parseable, no keyword) ALSO exits 0 where the original blocked
     (independent review, reproduced). The gate that actually closed it
     requires BOTH: the `*tool_name*` marker AND a payload that — after
     trimming trailing whitespace — ends in `}`. The `}` rule is not
     cosmetic: `read -d ''` stops at the first NUL, so a truncated payload
     like `{"tool_name":"Bash",` carries the marker but no keyword and must
     NOT be trusted (measured: old=2 → new=0 without it). Documented
     residue, disclosed not fixed: a malformed payload that still ends in
     `}` (`{"tool_name": invalid}`) passes the gate — it is a heuristic,
     not a validity proof, and the harness never emits one.
  3b. **Disclose the raw-byte blind spot in EVERY blocking guard's comment,
     not just one.** A JSON `\uXXXX`-escaped keyword defeats any raw-byte
     filter — reproduced end-to-end: a fully-escaped `git commit -am`,
     `git reset --hard`, or proxied domain exits 0 through the fast path
     where the original layer decoded and blocked (construct the payload
     with octal `printf '\134'` or a generator that never decodes — two of
     three first attempts accidentally produced literal text and a false
     negative). The harness JSON encoder never escapes ASCII letters, so
     accept the risk — but write the acceptance into **every** blocking
     guard's fast-path comment: fail-closed guards, AND parse-fail-open /
     verdict-blocking hybrids (a form/bypass/proxy guard exits 0 on
     unparseable input yet exit 2 on a matched verdict — the blind spot
     hits their verdict layer, direction block→allow). Pure informational
     hooks (always-exit-0 by contract) are exempt: both paths allow anyway.
  4. Verify per hook with the six-case suite — irrelevant / blocking /
     allowed / empty / malformed / keyword-present-but-irrelevant — plus a
     `python3`-stubbed `PATH` for fail-closed guards (their contract is
     exit 2 exactly there) and the three malformed-marker forms from step 3
     (`echo 'tool_name'`, `["tool_name"]`, NUL-truncated payload). Measure
     the floor: `bash` startup + builtin
     `case` ≈ 6.6 ms/call; the guards that used to cost 45–57 ms per
     irrelevant call now cost ~6 (independently re-measured at 4.7 ms on
     the heaviest one), and that is the entire win — the
     blocking path is intentionally unchanged.
- **Why not a dispatcher instead:** merging N guards into one process saves
  the same forks but couples their blast radius (one corrupted shared file
  poisons every Bash call) and breaks per-guard SSOT/test ownership. Slim
  each guard; keep the fleet.

---

## 23. A "skip the next token" table that no one checked against the real tool's arity swallows the banned flag as "data"

- **Symptom:** a blocking guard keeps a table of "flags whose next token is a
  value, not a flag" (to avoid false positives on `-m "-a"`-style data). One
  day a probe shows the banned form sailing through: `git commit -e -a`
  exits 0, `git commit -e --no-verify` exits 0 through **two independent
  guards at once** — the PII-defense line is pierced while every table entry
  "looks right" and every fixture passes.
- **Cause:** a **boolean** flag was sitting in the valued-flag table, so the
  scanner skipped the token AFTER it — and that token was the banned flag
  itself. Real case (2026-07-26, R7终审 with scratch-repo ground truth):
  git's `-e` is boolean `--edit` (takes NO value — `git commit -e --no-verify
  --dry-run` parses both flags independently), yet `-e` was in THREE tables
  across two files: a form guard's skip set, a bypass guard's DATA_FLAGS, and
  a bundle-arity character set (`-en` read as "e's value is n" — actually
  `-e -n`). The tables were each written by reasoning from flag *names*, not
  by checking arity; the same wrong assumption in two files means
  cross-reviewing one file against the other finds agreement, not truth.
- **Fix — every skip-table entry must trace to the tool's real arity, not
  the flag's vibe:** (1) verify with ground truth (scratch repo / `--help` /
  parsing experiment) — for git commit the valued short flags are `m F C c t
  G` and `-u` with its ATTACHED optional value (`-uall` = `--untracked-files
  =all`, so `u` also absorbs the rest of a bundle); (2) model bundles by
  walking characters left to right and STOPPING at the first valued char —
  `-ma` is message "a" (allow), `-eam` hits `a` before `m` (block), the old
  `startswith("-a")` catches `-am"x"` but misses `-ea`; (3) when the same
  table exists in two guards, fix both in one commit and write the ground-
  truth command into each comment, or the next editor re-derives the error
  from the sibling file.

---

## 24. Every character in a boundary regex's negated class is a blind-spot decision — derive it from the entity's syntax

- **Symptom:** after a "fix the boundary" patch, the guard now blocks the
  impostor (`notclaude.ai`) correctly — but a probe finds the REAL thing
  (`api.claude.ai`, the actual API endpoint a Tier-0 rule exists to cover)
  exiting 0. The fixture list (block impostor ✓, allow bare domain ✓) is
  all green; the regression is invisible because nobody probed the legal
  subdomain.
- **Cause:** the lookbehind `(?<![A-Za-z0-9.-])` added `.` to the negated
  class. A dot before the domain means "subdomain of the SAME zone" —
  exactly what the rule covers (`*.claude.ai`) — and the patch excluded it.
  Each character in that class is a claim about what may precede the needle
  while still being the same entity; adding one silently re-scopes the rule.
  Real case (2026-07-26): this was itself a regression introduced while
  fixing a different boundary complaint — the old substring matcher blocked
  subdomains fine, the "improved" boundary traded one hole for a worse one.
- **Fix — derive the class from the entity's grammar, and probe all three
  cells:** for DNS, a label is `[A-Za-z0-9-]` and `.` is the hierarchy
  separator, so the boundary is exactly `(?<![A-Za-z0-9-])`. Then probe the
  full truth table: impostor-prefixed (`notclaude.ai` → allow), legal
  subdomain (`api.claude.ai` → block), suffix-impostor (`claude.ai.evil.com`
  → block), bare (`claude.ai` → block). A boundary patch that only re-runs
  the fixtures it was written for will green-light its own regression.
  Sibling shape: `startswith("core.hookspath")` key matching eats
  `core.hooksPathValue` — the same "boundary not derived from the entity"
  mistake in plain-string form; match the key exactly.

---

## 25. Blocking a "write" without modeling the tool's read forms blocks the guard's own health check

- **Symptom:** a guard that must stop *persistent* config tampering blocks
  `git config core.hooksPath` — a READ-only query — so the operator (or the
  agent) cannot inspect the very configuration the guard exists to protect.
  The failure direction is the worst one: healthy input killed, reflexive
  bypass trained. Meanwhile `GIT_CONFIG_COUNT=1 make test` — no git anywhere
  in the segment — is also blocked, because the env-injection scan fires
  before anyone checked the segment even runs git.
- **Cause:** mode detection recognized only explicit read flags
  (`--get/--list/-l`), but git's most natural read form is `git config
  <key>` with NO value argument (1 arg = query, ≥2 args = write) — a form
  the flag-list model classifies as "set". And the env-injection detector
  returned its hit the moment it saw a dangerous VAR=val, before the
  git-entry check two sections later; the layers were ordered by where the
  code was added, not by "is this segment even the tool I guard".
  Both found 2026-07-26 by r7 review probes against real git semantics.
- **Fix — model the tool's read/write grammar, and gate side detectors on
  target presence:** (1) enumerate the read forms from the tool's actual
  semantics (`config <key>` no-value = query, `--get-all/--get-regexp/
  --get-urlmatch` are reads too; skip valued flags like `--file` when
  counting args), then classify writes as "≥2 non-flag args or an `--unset`
  family flag"; (2) a side-channel detector (env injection, wrapper smuggle)
  must NOTE its hit and only return it after confirming the segment's
  effective command is the guarded tool — `VAR=x make test` is not your
  jurisdiction; (3) add the tool's own health-check command
  (`git config core.hooksPath`) to the allow fixtures — if the guard blocks
  the command you'd run to debug it, the table is wrong by construction.

---

## 26. A hook that activates mid-session only guards what happens AFTER it — work from before stays unexamined unless something else checks

- **Symptom:** a hook ships mid-session specifically because a systemic
  anti-pattern was just caught, and it works exactly as designed — every
  later attempt at the pattern gets blocked. It is tempting to treat the
  problem as closed for the whole session. It isn't: anything already
  running, already dispatched, or already reported before the hook existed
  sat outside anything the hook could ever have inspected.
- **Why this belongs in a "bug that shipped" catalog when the hook itself
  didn't misbehave:** every other entry here is a broken guard; this one is
  a correctly-working guard paired with a wrong assumption about what it
  covers. It earns a slot anyway because it's exactly the mistake a hook
  author makes in the minutes right after shipping a fix — "I closed this"
  instead of "I closed this going forward" — and the file's own triage
  method ("match the symptom") won't route a reader here unless they
  already suspect coverage, not correctness, is the question.
- **Cause:** a PreToolUse-style gate only ever sees the tool call in front
  of it, at the moment it fires. It has no transcript access and no
  mechanism to scan backward: not the background processes already
  launched under the old pattern, not results already returned and
  believed, not commands already dispatched from earlier in the same
  session. (This is a property of tool-call gates specifically, not of
  every hook type — a Stop hook with transcript access, like the one
  behind entry 20, can and does look backward within a turn; the claim
  here is scoped to hooks that only ever see one tool call at a time.)
  "The guard is now live" and "every prior instance this session is
  accounted for" are two independent facts; shipping the hook only ever
  establishes the first.
- **Real case (2026-07-21, one day; recurred once, six days later):**
  `bg-exitcode-guard` blocks backgrounded Bash commands whose last
  statement is `echo`/`printf` after the script already captured `$?` — the
  always-zero echo/printf exit code overwrites the real command's exit code
  in the task-notification summary. The same session used that exact shape
  13 times within a single ~4.5-hour window on one day, before the hook
  existed. Once, it produced a genuinely misleading "completed (exit code
  0)" notification for a deploy that had actually failed three times in a
  row — and the operator caught the discrepancy within the same turn,
  inside a minute, by habitually re-grepping the real log instead of
  trusting the notification text: a near miss, not a believed-and-acted-on
  failure. After that day the pattern went completely dormant — zero
  backgrounded Bash calls of any kind — for six days, then recurred exactly
  once; the hook, freshly live, blocked it on its very first opportunity.
  None of the 13 pre-hook uses were still running by the time anyone
  looked — they had all already finished, and simply sat unexamined until
  an unrelated end-of-session review (not a sweep prompted by the hook
  itself) happened to check the transcript and surfaced the full count,
  the same day as the hook's only catch.
- **Fix:** don't treat "I have a habit of double-checking" as equivalent to
  "this is closed" — a habit is a per-instance save, not a guarantee, and
  the near miss above didn't stop anything on its own; the pattern simply
  went dormant for six days before recurring once more, and only the hook
  actually ended it. Two things follow, matched to what's actually
  checkable: (1) a genuinely in-flight task dispatched before the fix will
  still deliver its notification normally once it completes — Cause
  implies this risk, but none of the 13 real instances exercised it, since
  all of them had already finished by the time anyone looked — and there
  is no tool that lists "background tasks still outstanding from before
  this hook existed" to check for that in advance, so stay exactly as
  skeptical of a notification from something you dispatched under the old
  broken form as you are of a new one, since the hook cannot have
  retroactively fixed a command that's already running; (2) for the case
  that's actually common — already finished by the time the hook goes
  live — a deliberate sweep isn't the only path: if the session or
  environment already runs some later, broader check (an end-of-session
  review, a periodic audit), confirm it actually covers this exact gap
  rather than assuming it does. In the case above, that's literally what
  surfaced the true count of 13 uses — the same day as the hook's only
  catch, not a later sweep triggered by the fix itself. If the habit in
  (1) or the later check in (2) turns up an instance that was actually
  acted on, not just printed, treat it as its own live incident — verify
  what state it left behind before moving on.

---

## 27. A Stop hook's two runtime loop-protections both have blind spots — and a tool-calling remediation lands in both

- **Symptom:** a Stop hook fires several times inside what the user experiences
  as one request. Nothing errors. `stop_hook_active` is handled correctly. The
  documented consecutive-block ceiling never arrives.
- **Cause — the ceiling counts something narrower than its name suggests.**
  Claude Code caps consecutive Stop-hook blocks (default **8**, overridable via
  `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`; **setting it to `0` disables the cap
  rather than forbidding blocks** — the guard is `cap > 0 &&`). None of this is
  in the docs; it is readable from the shipped binary. The counter driving it is
  **reset to 0 on every continuation that executed tools** — verified across all
  six continuation branches in 2.1.220, each of which writes the counter back as
  `0`; only the block branch increments it. So the cap's real meaning is *"blocked
  eight times in a row without the model doing anything in between"* — it catches
  a model that has stalled, not one that is diligently oscillating. **Any hook
  whose remediation involves tool calls keeps the counter pinned at 1 forever.**
  That is most Stop hooks worth writing: run the tests, dispatch the review,
  regenerate the artifact. Note also that when the cap *does* fire, the turn ends
  with `reason:"completed"` — the harness does not distinguish "forced abort"
  from "genuinely done" (contrast OpenHands, whose goal controller carries an
  explicit `complete` / `capped` split).
- **Cause — the other protection is one bit, not a counter.** `stop_hook_active`
  is a boolean: *"this turn has been blocked by a stop hook at least once."* The
  hook cannot learn how many times it has fired, so "let the third one through"
  is not expressible from the input alone. (Cursor hands its stop hook a numeric
  `loop_count` plus a configurable `loop_limit`; Claude Code hands you the bit.)
  The field is also undocumented — absent from the hooks reference, present in
  the SDK's type declaration with no prose. Within one query loop it behaves as a
  **latch**: once true it stays true.
- **What is NOT the cause (tested, so you don't repeat the experiment):**
  asynchronous background completions arriving *inside* the blocked window do
  **not** clear the latch. Measured over 7 headless runs on 2.1.220 — three with
  the notification verifiably landing after the block, including a real
  subagent reply — the latch held `true` every time. A plausible-sounding
  mechanism is not evidence; this one was wrong.
- **Honest boundary:** one observed session had a Stop hook block **four** times
  within a span containing a single real user message, each time with the latch
  `false` — so *something* started a fresh query loop between them, and the above
  rules out the obvious candidate. **The mechanism is unresolved.** That
  uncertainty is itself the argument for the fix: do not hang termination on a
  protection whose reset conditions you cannot predict.
- **Fix:**
  1. **Carry your own bound.** Neither runtime protection is one. If your hook
     demands a remediation, key a counter on something the hook computes itself
     (the turn-start offset it already derives, plus the session id) rather than
     on a runtime field.
  2. **Suppress the fires that are certainly useless — this is free.** The Stop
     input carries `background_tasks[]`, which lists still-running subagents
     (`type`, `status`, `agent_type`) and empties when they finish. If your
     remediation is "dispatch an agent," firing while that agent is still
     running is pure noise, and noise is what trains readers to ignore the hook
     (#2). Going quiet on non-empty `background_tasks` / `session_crons` is a
     **fact test, not a heuristic** — categorically unlike the semantic
     stuck-detection SWE-agent tried and abandoned for false positives. It
     defers rather than suppresses: the agent's return opens a new turn and the
     hook fires then.
  3. Sanity-check the shape first: #16 (is the predicate temporal, so the
     remediation re-arms it?) and #19 (does the remediation require memory that
     does not survive the call boundary?). This entry is about the layer
     underneath both — what the runtime does *not* do for you either way.
- **Self-test rows that see it:** same must-fire input three ways —
  `background_tasks` non-empty → quiet; `background_tasks: []` → still fires;
  `session_crons` non-empty → quiet. The middle row is the one people skip, and
  without it you cannot distinguish "gate works" from "gate swallows
  everything." Verified by mutation: forcing the gate true fails many rows,
  forcing it false fails **exactly** the two quiet rows — proving no pre-existing
  fixture covered the gate.

---

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
6. Did it stop mid-run with **`Failed with non-blocking status code: No stderr
   output`**, in a hook whose contract is always-exit-0? → `set -e` + `pipefail`
   killing it on a legitimately-empty `grep`/`wc` (#8). Distinct symptom, distinct
   fix: drop `-e`, or `||`-guard every such pipeline.
7. Did your **own test command** get blocked while you were testing the guard you
   just registered? → self-block (#7); move the cases into a script file so the
   outer command doesn't carry the trigger.
8. Does it work when you run the command **in place**, but never fire when the
   command `cd`s somewhere first (or uses `~`, a variable, a glob)? → the guard is
   parsing command text and got an unexpanded string (#10). Note this one has **no
   symptom of its own** when the hook fails open — you find it by testing the
   `cd ~/elsewhere && …` shape explicitly, not by waiting for something to look wrong.
9. Does it pass every fixture but **barely fire on a real corpus** — and the missed
   commands are **multiline / newline-separated** (as opposed to #10's single-line
   `cd ~/x && …` with an unexpanded `~`)? → newline-blind segmentation (#11): the
   tokenizer drops the newline in real multiline commands, so the head is `cd`. Also
   suspect the replay/mutation **harness** itself — make it report "dirty" on a
   known-positive before trusting its "clean".
10. Is one **branch** of the hook — an optional paragraph, a kind-specific check —
    never firing, while everything else works? → either the branch is reading the
    hook's own **display string** and the item fell past a truncation (#12), or the
    **classifier** never produced that kind at all because it keys on a naming
    convention this repo doesn't follow (#13). Distinguish by printing the raw
    classification before it is formatted: present-but-truncated is #12,
    never-classified is #13.
11. Is the suite **green while the output is visibly wrong**? → the assertions only
    check exit codes and this hook's product is its text (#14). Add both-polarity
    content assertions, then mutate to prove they can die.
12. Does it report a file **nobody wrote** — especially one containing a literal
    `$VAR`? → it is reading command text as if every redirect in it executed (#15).
13. Does a **Stop hook** fire **again right after you did exactly what it asked**
    (the turn ends, work happens, and the NEXT stop re-fires on the same grounds)?
    → its condition is a temporal comparison that the remediation itself moves (#16).
    Not a tuning problem: change the predicate's *shape* — move the gate to the
    action with PreToolUse, or test an existence fact keyed on the thing that
    needed remediating — and add the after-remediation row pair that a
    point-in-time suite structurally cannot have. (Same "recurring fire" symptom
    as 15/16 below — split by hook type and by what you check first.)
14. Did it catch the first violation and **silently never mention the second one
    from the same reply**? → first-only reporting (#17): the honored retry round
    is a full pass-through, so collect every finding before printing and assert
    both hits in a two-violations fixture.
15. Did the **same block error return after you "fixed" it** — and your fix was
    bundled into the same command as the gated one? → innocent-segment
    side effects swallowed (#18): separate state changes from gated commands
    into their own Bash call, and after any block re-verify writes you assumed
    had landed. (Cheapest check in the recurrence family — one grep — so run it
    before 13/16's deeper reads.)
16. Does a **PreToolUse hook** block you **repeatedly for the same thing despite
    complying** each time (the block arrives before the command even runs)?
    → the remediation demands cross-call memory (#19): it's a class
    property, not carelessness — fix the environment, downgrade to a reminder,
    or accept-and-measure; a clearer message was never the missing piece.
17. Does a turn-scoped hook see **neither the work nor the review** that should
    bound it — quiet when it should fire, or firing when the review already
    happened? → the window/channel logic is eating system records: agent
    deliveries counted as turn starts truncate the detection window (#20), and
    environment-schema drift blinds the review channel (rule 7's observability
    form — verify the predicate can see R in EVERY environment, not just the
    one you fixture-tested).
18. Does a resolution step hand you the **wrong entity** — a verdict meant for
    A landing on B, or a decision inverted (delegation stamped as review /
    review read as delegation)? → prefix resolution without a typed tail (#21):
    globs must anchor on delimiter+type (name-hex.jsonl, not name-*), flag
    families need enumeration + arity, and segment state machines need the last
    NON-EMPTY head — and only a fixture containing the colliding pair proves
    resolution, a singleton proves nothing.
19. Is the **machine itself** hot under parallel agent sessions — spawn rate
    sustained at 40+/s, `syspolicyd` atop the all-day CPU ranking, and NO
    runaway process anywhere? → fork multiplier (#22): the fleet's per-call
    irrelevant path is the load. Slim every guard's fast path to zero forks;
    do not "fix" it by deleting guards.

---

## 28. The fallback target is right for one reason and wrong for another — and both print the same line

> Worked example in this repo's sibling tooling: `git-push-verify.sh` and
> `git-commit-headcheck.sh` (a private hooks repo, not shipped here) both had
> exactly this defect and were fixed on 2026-08-04 by the prescription below.
> Naming them matters — the entry is useless if you cannot go read a before/after.

- **Symptom:** a verification hook reports a clean, confident, *correct* fact —
  about the wrong object. `git push` to repo B triggers a push-verifier that
  answers with repo A's HEAD, compares it against repo A's remote, and prints
  `✅ push 已落地`. Nothing errored. The hash it printed is real. The comparison
  it performed is sound. It just wasn't about the push you ran. And the message
  opens with `权威源` / "authoritative — do not trust the in-command output",
  which is an instruction to discard the very observation that would have caught
  it.

- **Cause — two different reasons for falling back share one fallback value.**
  Such a hook derives its target from the command text (`git -C <path> …`) and
  falls back to the event's `cwd` when it can't. That fallback is correct for
  *one* of the two reasons it triggers and wrong for the other, and the code
  path is identical:

  | command | target parsed | falls back? | event cwd | verdict |
  |---|---|---|---|---|
  | `git push` | none — **there is no explicit target** | yes | the real target | ✅ correct |
  | `git -C /literal/p push` | `/literal/p` | no | — | ✅ correct |
  | `R=/p; git -C $R push` | `$R` — **explicit target, unreadable value** | yes | *not* the target | ❌ **bound to the wrong object** |

  Rows 1 and 3 emit byte-identical shapes. The hook cannot tell them apart, and
  neither can the reader: one is the strongest verdict the hook can give, the
  other is that same verdict about an unrelated repository. Note the variable is
  not exotic — assigning a path once and reusing it is ordinary shell, and it is
  *more* likely in exactly the multi-repo sessions where the failure bites.

  This is the checking-tool form of the **confused deputy** problem (Hardy,
  1988): a component with the authority to answer becomes confused about *which
  object it is answering for*. The security literature's diagnostic questions
  port over directly — "who is the real requester? what resource is actually
  being touched?" — and for a hook they become **"which target did the command
  name, and is that the one I measured?"**

- **The assumption that hides it.** Both hooks carried a comment asserting this
  fallback was safe *because* "the wrong path will just fail to read, so the
  failure direction is fail-loud — there is no false-green path here." That is
  the reasoning to distrust. It holds only if the fallback lands somewhere
  invalid; in a multi-repo session it lands in **another valid repository**, so
  the read succeeds and returns a real, checkable, entirely irrelevant fact. The
  false green grew directly out of the belief that a false green was impossible.
  When you write "this can only fail loudly," name the input that would make it
  fail quietly and go check that input exists.

- **Why this is worse than a hook that fails open.** A fail-open hook (pitfall
  #10) produces silence, and silence is at least honest about carrying no
  information. This produces a *positive verdict with the wrong referent*, wearing
  the vocabulary of authority. It also survives the reader's instinct to
  double-check, because there is nothing to double-check: the command succeeded,
  the output is well-formed, the hash is real.

- **Fix — make the fallback carry its own reason, and downgrade the one that
  can't be trusted.**
  1. **Distinguish "no explicit target" from "explicit target, unresolvable."**
     Only the first may silently adopt the event `cwd`. The second must refuse
     to render a verdict: `目标是 $VAR，无法解析——本 hook 未核对，请手动比对`.
     A hook that says "I didn't check" costs one manual check; one that says
     "✅" about another object costs the thing it was built to protect.
  2. **Put the referent where it is read, not where it is skipped.** If the
     message must carry a caveat, it belongs *before* the verdict, not after it.
     A trailing "⚠️ if the repo above isn't the one you pushed, this line is
     unrelated" is a correct sentence that arrives after the reader has already
     banked the ✅.
  3. **Never claim more authority than the binding supports.** `权威源` is
     earned by the *measurement* (asking the remote) and spent by the *binding*
     (which repo). A hook whose binding is heuristic should not use the
     vocabulary of a hook whose binding is exact.

- **How this hides during development.** The author writes fixtures with literal
  paths, because that is how you write a readable test. Literal paths are row 2 —
  the one that works. The failure needs a variable, which appears in real
  sessions and almost never in fixtures. Add a fixture whose target is a shell
  variable and assert on the *rendered target string*, not on the exit code
  (pitfall #14's rule applied here: for a hook whose product is text, the exit
  code proves nothing).

- **Calibration note for anyone tempted to "just always warn."** Research on static-analysis
  alerts reports that a large majority of warnings go unacted-on — the
  frequently-cited range is roughly **35%–91%** (Heckman & Williams' work on
  actionable-vs-unactionable warnings is the usual entry point), with
  false-positive rates reaching ~90% in some tools, and names the resulting
  desensitisation *alert fatigue*. (Figures quoted from secondary summaries;
  search "actionable static analysis warnings" for the primary sources and their
  datasets.) That is the budget a hook spends
  every time it emits an unreliable line. Choosing "I didn't check" over a
  confident wrong answer is not timidity; it is spending that budget on the
  cases that earn it.

**The later entries route by shape, not by symptom order** (they were added after
this list and describe defects you reach by asking a different question):

- Does the guard **read a flag as data**, or drop a token it should have judged?
  → arity table vs. the real tool (#23); boundary-regex negated class (#24).
- Does the guard **block its own maintenance** — its health check, its fix commit,
  its own read path? → read forms not modelled (#25); and #7 for the fix-commit form.
- Is the guard **correct from now on but blind to what already happened**?
  → mid-session activation guards only the future (#26).
- Is a **Stop hook firing more times than the documented cap allows**?
  → both loop-protections have blind spots (#27).
- Does the guard emit a **confident verdict about the wrong object** — right facts,
  wrong referent, no error anywhere? → fallback target sharing one value for two
  different reasons (#28). This one does not announce itself as a malfunction;
  you find it by asking "which target did the command name, and is that the one
  the guard measured?"
- Does the guard **look like it fires but never actually blocks** — the guidance
  prints, the state is written, yet the exit code is 0 every time? → a trailing
  `exit 0` swallowing the decision (#29).

## 29. A trailing `exit 0` swallows the exit-code decision — the message prints, the state writes, the guard never blocks

> Worked example: `same-cmd-resend-guard.sh` (a private hooks repo, not shipped
> here), 2026-08-08. A PreToolUse guard whose fire-path ended in python
> `sys.exit(2)` also ended the bash script with an unconditional `exit 0`
> (added as a "safety" line so the script never returned non-zero outside its
> python block). The `exit 0` ran **after** the heredoc, unconditionally
> overriding the python exit code. The guard's entire decision — "block this" —
> was thrown away on every fire.

- **Symptom:** the hook *looks alive*. Run it by hand and it prints the guidance
  to stderr. The state file it writes appears. `bash -n` passes. An end-to-end
  test that only checks "did the message print" passes. But the harness sees
  `exit 0` every time — the block never happens, the model never sees the
  guidance in-session, and the guard is a silent no-op for its entire life. This
  is the "绿成常态 = 没拦" shape: green everywhere, nothing enforced.

- **Why this is worse than a miss.** A guard that never fires is a miss on every
  input, forever — and it *looks* like a working guard (message prints, state
  writes, tests pass). It survives until an independent reader checks the exit
  code itself, because the author's own end-to-end test asserted the wrong
  observable (stderr) and never asserted the decision channel (exit code).

- **Fix — the script's exit code must BE the decision, and the test must assert
  it.**
  1. **Do not add a trailing `exit 0` to a PreToolUse hook that decides.** The
     bash script's exit code is its contract; the last command (the python
     heredoc, or an explicit `exit "$?"`) must be what the harness sees. If the
     python block has fail-open branches, express them *inside* python
     (`sys.exit(0)` on the allow paths), not as a shell-level override after it.
     If python3 is missing, the heredoc's exit 127 is a "non-blocking error"
     which the harness treats as proceed — that is already the fail-open you
     wanted; you do not need the `exit 0`.
  2. **Assert the exit code, not just the stderr.** For a guard whose product is
     a decision, `says` (stderr) rows are necessary but not sufficient — a
     `sys.exit(2)` swallowed by a later `exit 0` keeps every `says` row green.
     Add `assert_exit 2` on the fire path and `assert_exit 0` on every allow
     path, and **mutation-test the exit-code row**: reintroduce the bug (add the
     `exit 0` back), confirm the suite goes red on the exit-code assertion.
     (This pitfall was itself caught that way — the exit-code row is what turned
     red when the bug was re-injected.)
  3. **Watch the "message prints" trap in your own calibration.** Seeing the
     guidance on stderr when you run the hook by hand is not proof the harness
     will block — stderr shows on allow too. The decision channel is the exit
     code; test the channel, not the ink.
