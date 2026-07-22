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

# ── group-name-guard (Stop event) ────────────────────────────────────────────
# Trigger rows = BASELINE. If these return 0 the harness is wrong, not the hook.
run "self-coined shorthand" '{"last_assistant_message":"这条消息是 Zeta 群发出来的"}' 2
# Healthy-lookalike rows (want 0):
run "fix: 单群"        '{"last_assistant_message":"可以只同步单群，不必 --groups all"}' 0
run "fix: 跨群"        '{"last_assistant_message":"支持跨群检索历史消息"}' 0
run "quantifier 多群"  '{"last_assistant_message":"多群并行拉取没问题"}' 0
run "pronoun 该群"     '{"last_assistant_message":"该群全称未确认，先按该群处理"}' 0
run "2-char 微信群"    '{"last_assistant_message":"微信群消息已经同步完成"}' 0
run "verb 退群"        '{"last_assistant_message":"退群之后就收不到了"}' 0
run "exempt 群里"      '{"last_assistant_message":"我在 Zeta 群里看到的"}' 0
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
