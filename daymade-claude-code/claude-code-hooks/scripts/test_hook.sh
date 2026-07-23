#!/usr/bin/env bash
# End-to-end test harness for a Claude Code hook.
#
# WHY a script file (not inline Bash commands): once a PreToolUse hook is live in
# the session, any Bash command you issue that contains the trigger token gets
# blocked by the hook before it runs — you can't test it from your own command
# line. Running `bash test_hook.sh` works because the OUTER command
# ("bash test_hook.sh") doesn't contain the trigger; the triggers live inside
# this file where the live hook never inspects them.
#
# USAGE:
#   1. Copy this file next to your hook.
#   2. Set HOOK to your hook's path.
#   3. Fill the `run` table: trigger cases (want exit 2) + healthy-lookalike
#      cases (want exit 0). The healthy-lookalike rows are the important ones —
#      they prove you don't false-block (误杀健康输入比漏报更糟).
#   4. bash test_hook.sh   # NOT ./test_hook.sh through a live hook's shell
#
# It runs `bash -n` (syntax — a corrupted PreToolUse hook poisons the whole
# session) then every case, and reports pass/fail.

HOOK="${1:-$HOME/scripts/claude-hooks/CHANGE-ME.sh}"

if [ ! -f "$HOOK" ]; then echo "HOOK not found: $HOOK" >&2; exit 1; fi

echo "=== bash -n $HOOK ==="
if bash -n "$HOOK"; then echo "OK syntax"; else echo "SYNTAX ERROR — do not register"; exit 1; fi
echo ""

pass=0; fail=0
# run <label> <json-event> <expected-exit>
run() {
  printf '%s' "$2" | "$HOOK" >/dev/null 2>&1
  local e=$?
  if [ "$e" = "$3" ]; then printf 'PASS exit=%s [%s]\n' "$e" "$1"; pass=$((pass+1))
  else printf 'FAIL exit=%s want=%s [%s]\n' "$e" "$3" "$1"; fail=$((fail+1)); fi
}

# says <label> <json-event> <grep-pattern> <yes|no>
#   Asserts on the hook's stderr TEXT, not its exit code. Needed whenever the
#   hook's real product is its guidance message — a PreToolUse explanation, a Stop
#   reminder. Break the wording, invert an optional paragraph's condition, let a
#   heredoc swallow a section: the exit code is unchanged and every `run` row still
#   passes, so an exit-code-only suite is structurally blind to it (pitfall #14).
#   Assert BOTH polarities, across two fixtures: the paragraph appears for the
#   input it targets (want=yes), and is absent for the lookalike it must skip
#   (want=no). A want=no row alone passes vacuously when the hook prints nothing
#   at all — so it is only meaningful next to a want=yes row proving the hook
#   speaks. Do not try to put both polarities on ONE fixture: a healthy input is
#   supposed to be silent, so it has no want=yes partner — its partner is the
#   trigger fixture.
says() {
  local out hit=no
  out=$(printf '%s' "$2" | "$HOOK" 2>&1 >/dev/null) || true
  # -F (fixed string), NOT a regex: the patterns you actually want to assert are
  # literal phrases, and the most useful ones contain brackets — a hook that tags
  # `path [skill]` is the motivating case. As a BRE, "[skill]" is a CHARACTER
  # CLASS: it matches any text containing s, k, i or l, so `says … "[skill]" yes`
  # is true of almost any English output and the row is decorative. Measured.
  # Need a real regex? call grep -qE explicitly in a copy of this helper.
  printf '%s' "$out" | grep -qF -- "$3" && hit=yes
  if [ "$hit" = "$4" ]; then printf 'PASS text=%s [%s]\n' "$hit" "$1"; pass=$((pass+1))
  else printf 'FAIL text=%s want=%s [%s]\n' "$hit" "$4" "$1"; fail=$((fail+1)); fi
}

# ── EXAMPLE TABLE — replace TRIGGER with your banned command ──────────────────
# Trigger cases (want 2):
run "execute"        '{"tool_name":"Bash","tool_input":{"command":"TRIGGER -x arg"}}' 2
run "after-pipe"     '{"tool_name":"Bash","tool_input":{"command":"ls | TRIGGER -x"}}' 2
run "no-space-pipe"  '{"tool_name":"Bash","tool_input":{"command":"ls|TRIGGER -x"}}' 2
run "after-&&"       '{"tool_name":"Bash","tool_input":{"command":"foo && TRIGGER x"}}' 2
run "env-prefix"     '{"tool_name":"Bash","tool_input":{"command":"FOO=1 TRIGGER x"}}' 2
# Healthy-lookalike cases (want 0) — THESE are what prove you don't false-block:
run "grep-regex-arg" '{"tool_name":"Bash","tool_input":{"command":"grep -E \"a|TRIGGER|b\" file"}}' 0
run "redirect-target" '{"tool_name":"Bash","tool_input":{"command":"echo x > TRIGGER"}}' 0
run "sed-arg"        '{"tool_name":"Bash","tool_input":{"command":"sed s/TRIGGER/x/ file"}}' 0
run "echo-mention"   '{"tool_name":"Bash","tool_input":{"command":"echo do not use TRIGGER"}}' 0
run "grep-search"    '{"tool_name":"Bash","tool_input":{"command":"grep TRIGGER file"}}' 0
run "comment"        '{"tool_name":"Bash","tool_input":{"command":"echo hi # TRIGGER bad"}}' 0
run "unrelated"      '{"tool_name":"Bash","tool_input":{"command":"ls -la /tmp"}}' 0
run "non-bash-tool"  '{"tool_name":"Read","tool_input":{"file_path":"/x/TRIGGER.txt"}}' 0
#
# ── FAILURE-DIRECTION ROWS — add these whenever the hook derives state from the
#    command text (a path, a repo, a target). They assert the hook still behaves
#    when it CANNOT resolve what it parsed. Omit them and a fail-open bug looks
#    exactly like a clean pass (pitfall #10):
# run "trigger behind cd ~"  '{"tool_name":"Bash","tool_input":{"command":"cd ~/somewhere && TRIGGER -x"}}' 2
# run "trigger behind cd abs" '{"tool_name":"Bash","tool_input":{"command":"cd /tmp && TRIGGER -x"}}' 2
# run "unresolvable path"    '{"tool_name":"Bash","tool_input":{"command":"cd ~/no-such-dir && TRIGGER -x"}}' 2
#
# ── CONTENT ROWS — assert the MESSAGE, when the message is the product ────────
# run rows prove the hook decided correctly; says rows prove it said the right
# thing. Both polarities on conditional paragraphs (pitfall #14):
# says "explains alternative" '{"tool_name":"Bash","tool_input":{"command":"TRIGGER x"}}' "USE INSTEAD" yes
# says "quiet on healthy"     '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}'    "BLOCKED"     no
#
# ── PROVE THE SUITE CAN FAIL (mutation) — do this once per assertion you add ──
# A green suite carries ZERO information until you have watched it go red for the
# right reason. For each assertion, copy the hook, inject the exact bug that
# assertion claims to catch, and confirm THAT row dies — ideally only that one:
#     cp "$HOOK" /tmp/mutant.sh
#     # invert a branch condition / delete a fact-check / revert to a display-string match
#     bash test_hook.sh /tmp/mutant.sh     # expect exactly the intended row to FAIL
# If the mutant still passes, the assertion is decorative — it is testing something
# other than what its label claims. Two real bugs once lived in a hook through a
# fully green 24-case suite because every row looked only at exit codes.
#
# ── HUMAN-GATE ROWS — if the hook releases via a confirmation dialog / tty YES,
#    force both channels to decline so the run stays headless, and assert it
#    BLOCKS. Requires the hook to read its channels from overridable names
#    (see Pattern B "Make the gate testable"):
#      GIT_GUARD_OSASCRIPT=false GIT_GUARD_TTY=/dev/null bash test_hook.sh <hook>
#    Never provide an env var that *grants* approval — that recreates the retired
#    static-escape-hatch anti-pattern.
# ──────────────────────────────────────────────────────────────────────────────
#
# ── EVENT SHAPES OTHER THAN PreToolUse (the payload differs per event) ────────
# A hook reads a DIFFERENT field depending on which event it's registered for.
# Feed the wrong shape and the hook can't find any text, exits 0 silently, and
# EVERY case looks like it passed. Verified shapes (2026-07-22):
#
#   Stop / SubagentStop — hook reads the assistant's final message:
#     run "stop-trigger" '{"last_assistant_message":"...text under test..."}' 2
#     (fallback path: '{"transcript_path":"/abs/path.jsonl"}' where the file has a
#      line {"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}};
#      also honors {"stop_hook_active":true} as an early no-op exit)
#
#   UserPromptSubmit — hook reads the user's prompt:
#     run "prompt-trigger" '{"prompt":"...text under test..."}' 2
#
#   PostToolUse — same as PreToolUse plus the result:
#     run "post" '{"tool_name":"Bash","tool_input":{"command":"x"},"tool_response":{...}}' 2
#
# Build the JSON with single quotes as above. Writing '{\"a\":1}' inside single
# quotes emits LITERAL backslash-quote — invalid JSON — and the hook exits 0 on
# the parse failure, which reads as "passed". (Cost a real debugging round.)
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "=== $pass pass / $fail fail ==="
# Harness-sanity check: if NOTHING triggered, suspect the harness before the hook.
# A wrong event shape / malformed JSON makes the hook exit 0 on every case, which
# is indistinguishable from "no false blocks" unless you assert a known-good
# trigger. That's why the trigger rows above are the baseline, not decoration.
if [ "$fail" != "0" ]; then
  echo "FAILURES — fix before registering"
  echo "HINT: if EVERY trigger row failed with exit=0, the hook probably never"
  echo "      saw your text — check the event shape / JSON quoting above before"
  echo "      touching the hook's logic."
  exit 1
fi
echo "ALL PASS — safe to register"; exit 0
