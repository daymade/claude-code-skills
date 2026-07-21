# Context Window Configuration

Deep technical detail for the `[1m]` context-window marker and the reusable
"did this env var actually change the outgoing request" recipe. The SKILL.md
keeps only the decision rule (what to set per provider) and points here for the
mechanism — because the rule is needed at template-writing time, while the
mechanism is reference knowledge you reach for when something looks wrong.

## Table of contents

- [The `[1m]` marker — full mechanism](#the-1m-marker--full-mechanism)
- [Decision-rule caveat: the step-2-16k war-story](#decision-rule-caveat-the-step-2-16k-war-story)
- [Verifying an env var actually changes the outgoing request](#verifying-an-env-var-actually-changes-the-outgoing-request)

## The `[1m]` marker — full mechanism

When `ANTHROPIC_MODEL` (or `ANTHROPIC_DEFAULT_HAIKU_MODEL` / `ANTHROPIC_DEFAULT_SONNET_MODEL` / `ANTHROPIC_DEFAULT_OPUS_MODEL` / `CLAUDE_CODE_SUBAGENT_MODEL`) ends in the literal four characters `[1m]`, Claude Code's own CLI — not the upstream provider — parses that suffix and does two things before it ever sends a request:

1. Strips `[1m]` off the `model` field, so the upstream provider receives the clean ID (e.g. `moonshotai/kimi-k3`, never `moonshotai/kimi-k3[1m]`).
2. Adds `context-1m-2025-08-07` to the outgoing `anthropic-beta` header.

That's the entire effect — confirmed 2026-07-21 by pointing `ANTHROPIC_BASE_URL` at a local `http.server` that echoes back whatever it receives, then diffing a real Claude Code request sent with `moonshotai/kimi-k3[1m]` against one sent with the bare `moonshotai/kimi-k3`: every other field (`context_management`, `output_config`, `metadata`, the rest of the `anthropic-beta` list) was byte-identical; the beta flag was the only diff. `--debug api` will NOT show you this — it only logs Claude Code's internal state, never the literal bytes on the wire. See "Verifying an env var actually changes the outgoing request" below for the reusable recipe.

Three things follow from this that aren't obvious just from looking at the templates:

- **It's entirely client-side.** The upstream provider never sees `[1m]`. Whatever the provider's real context ceiling is, it's set by their own backend, independent of this flag — a third-party model can genuinely accept 500K+ tokens with `[1m]` absent from the request the whole time (separately confirmed: a bare ~506K-token request to `moonshotai/kimi-k3`, no `[1m]` anywhere, HTTP 200'd and correctly recalled a marker word buried in the middle of it). So a missing `[1m]` does not mean the provider can't handle a big prompt.
- **What `[1m]` actually buys you is Claude Code's own awareness** of that ceiling — the context percentage in the statusline, and, most consequentially, when auto-compact fires. Configure a genuinely-1M-context provider *without* `[1m]` and Claude Code has no way to know it isn't talking to a normal ~200K model; it will compact prematurely on long sessions even though the provider could hold much more.
- **It's a generic suffix match, not a whitelist of Anthropic's own model names.** It fired identically for `moonshotai/kimi-k3[1m]` — an arbitrary third-party ID Claude Code has never heard of — as it does for Anthropic's own native `sonnet-4-6[1m]`/`opus[1m]`-style 1M-beta models (those exist for the real Anthropic API too, and are where this convention originates). Any provider/model name works as the prefix as long as the string ends in exactly `[1m]`.

## Decision-rule caveat: the step-2-16k war-story

Template bug fixed 2026-07-21 (two layers, caught in two passes): `stepfun.json` originally shipped `CLAUDE_CODE_AUTO_COMPACT_WINDOW: "1000000"` on `step-2-16k`. First pass only fixed the internal mismatch (a model whose own name says 16K carrying a 1M claim — a ~60x overclaim, almost certainly left over from copying the deepseek/glm templates without adjusting the number). Second pass caught the deeper problem the first one missed: `step-2-16k` itself is a real but long-superseded model — created 2024-07 per StepFun's own model list, and absent entirely from StepFun's current docs, which describe two live families topped by Step-3.7-Flash (released 2026-05) and Step-3.5-Flash, both **256K context** (verified against StepFun's official docs; a sibling project's own production usage of `step-3.7-flash` independently confirms **262144** as the precise figure). `step-2-16k` had been in this template since the skill's very first commit — it was never checked against StepFun's actual current lineup, just written down as a plausible-looking example. Fixed by switching to `step-3.7-flash` with explicit `CLAUDE_CODE_MAX_CONTEXT_TOKENS`/`CLAUDE_CODE_AUTO_COMPACT_WINDOW` set to `262144` (verified, not guessed).

**Lesson for any template in this skill (or any provider config you write from this skill):** an internally-consistent-looking value is not the same as a currently-correct one — cross-check the model name itself against the provider's live docs, not just the numbers around it.

## Verifying an env var actually changes the outgoing request

Not specific to `[1m]` — reach for this any time you need to know whether a Claude Code env var or CLI flag genuinely changes the bytes sent over the wire, versus only affecting Claude Code's own internal bookkeeping. Trusting a template comment, or trusting `--debug api` (internal state only, never the literal request), is how the `[1m]` gap in this skill went unnoticed for as long as it did.

```bash
# Minimal capture server: logs whatever JSON body/headers it receives, returns a
# valid-enough Anthropic response so Claude Code doesn't just error out.
python3 - <<'PY' &
import http.server, json
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(n))
        print(json.dumps({"model": body.get("model"),
                           "anthropic-beta": self.headers.get("anthropic-beta")}), flush=True)
        resp = json.dumps({"id": "msg_x", "type": "message", "role": "assistant",
                            "model": body.get("model", "x"),
                            "content": [{"type": "text", "text": "OK"}],
                            "stop_reason": "end_turn",
                            "usage": {"input_tokens": 1, "output_tokens": 1}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)
    def log_message(self, *a):
        pass
http.server.HTTPServer(("127.0.0.1", 18765), H).serve_forever()
PY
SERVER_PID=$!
sleep 1  # give the server a moment to bind before the client connects
CLAUDE_CONFIG_DIR=/tmp/cc-probe ANTHROPIC_BASE_URL=http://127.0.0.1:18765 \
ANTHROPIC_AUTH_TOKEN=dummy ANTHROPIC_MODEL="<model-under-test>" \
claude -p "hi" --dangerously-skip-permissions
kill $SERVER_PID
rm -rf /tmp/cc-probe
```

Whatever the server prints is literally what left the machine — no guessing from debug logs, no trusting what a template or a teammate claims the config does. (Skipping the `sleep` is a real trap, not a hypothetical one — the first draft of this exact recipe omitted it and Claude Code intermittently reported "API returned an empty or malformed response" from a race between the server binding and the client's first connection.)
