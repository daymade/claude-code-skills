# OpenClaw Model Config — Trap Catalog

Field-tested failure modes when an OpenClaw instance's model "is configured wrong".
Each trap lists: symptom → why it really happens → how to prove it → fix.

## Contents

- Trap 1: 401 "Invalid token" — env var hijacks the provider's wire key
- Trap 2: "Thinking level not supported" — provider plugin hardcodes thinking levels
- Trap 3: "No available channel" — relay availability is group/network dependent
- Trap 4: `/v1/models` listing is not authority
- Trap 5: Edit "saved" but nothing changed — wrong file / mirror / restart
- Appendix: wire-capture recipe (echo server)

## Trap 1: 401 `new_api_error: Invalid token` — the wire key is not the key you configured

**Symptom.** Gateway log shows `LLM error new_api_error: Invalid token` and
`model_fallback_decision ... reason: auth, status: 401`, yet the same token succeeds
when you curl the endpoint by hand.

**Why.** Two separate facts collide:

1. For `api: anthropic-messages` providers, OpenClaw authenticates with the
   `x-api-key` header (Anthropic SDK style), not `Authorization: Bearer`. Some relays
   treat these differently — a token that passes as Bearer may fail as x-api-key.
2. The key on the wire may not be `models.providers.<p>.apiKey` at all. OpenClaw's
   built-in secrets registry maps env vars to providers, and **a non-empty env var
   beats `provider.apiKey`**. For the `kimi-coding` provider the mapped vars are
   `KIMI_API_KEY` (checked first) and `KIMICODE_API_KEY`. If the config's `env` block
   sets `KIMI_API_KEY`, that value is what gets sent — your provider apiKey is ignored.

**Prove it (wire capture, 2 min).** Point the provider at a local echo server and read
the exact header OpenClaw sends — see the appendix. If `x-api-key` differs from the
`apiKey` you wrote in the provider block, an env var is hijacking it.

**Fix (pick one):**

- Empty the hijacking var: `"env": {"KIMI_API_KEY": ""}` → resolution falls through to
  `KIMICODE_API_KEY`, then to `provider.apiKey`. Before emptying, check what else reads
  it (plugin configs with their own explicit keys are unaffected).
- Or set `KIMICODE_API_KEY` to the intended key (provider-specific, loses only to
  `KIMI_API_KEY`).
- Or use a custom provider id the registry doesn't map (see Trap 2 bypass) — then
  `provider.apiKey` is the only source, no env magic.

## Trap 2: `Thinking level "max" is not supported for <provider>/<model>`

Two variants, same root area:

**Variant A — `Use one of: off, on`.** A provider plugin (e.g. `@openclaw/kimi-provider`
for `kimi-coding`) hardcodes a binary thinking profile (`resolveThinkingProfile` returns
only off/on) for every model it owns. The active plugin's profile is consulted BEFORE
any config-derived profile, so **no model-definition field can override it**.

*Fix:* move the model to a provider id the plugin does not claim. The plugin claims its
id and aliases (kimi: `kimi`, `kimi-coding`) — anything else (e.g. `kimi-relay`) is a
plain custom provider and gets the normal anthropic-messages thinking resolution:

```json
"models": { "providers": {
  "kimi-relay": {
    "baseUrl": "<endpoint>", "apiKey": "<key>", "api": "anthropic-messages",
    "models": [{ "id": "k3", "name": "k3", "reasoning": true,
      "input": ["text","image"], "contextWindow": 1048576, "maxTokens": 32768,
      "params": { "canonicalModelId": "claude-opus-4-7" } }]
  }
}}
```

Then point `agents.defaults.model.primary` (and any plugin `defaultModel` override) at
`<custom-provider>/<model>`. Side benefit: custom providers aren't in the env-var
secrets registry, so `provider.apiKey` is authoritative (avoids Trap 1 entirely).

**Variant B — `Use one of: off, minimal, low, medium, high`.** No plugin profile, so the
anthropic-messages fallback profile (base levels only) applies. The model definition's
`params.canonicalModelId` drives which levels the fallback unlocks: set it to a model
family whose native profile includes the level you need (e.g. `claude-opus-4-7` →
xhigh/adaptive/max). With max/xhigh, OpenClaw sends
`thinking: {type:"adaptive"} + output_config: {effort: "<level>"}` instead of the classic
`budget_tokens` form — **probe that exact payload against the endpoint first** (some
upstreams reject `output_config`):

```bash
curl -sS -X POST "<baseUrl>/v1/messages" -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" -H "anthropic-version: 2023-06-01" \
  -d '{"model":"<id>","max_tokens":2000,"thinking":{"type":"adaptive"},"output_config":{"effort":"max"},"messages":[{"role":"user","content":"hi"}]}'
```

`canonicalModelId` side effects to know: it also makes OpenClaw treat the model as that
family for sampling (may strip temperature/top_p) — harmless on most Kimi-style
endpoints, but probe.

## Trap 3: `503 No available channel for model X under group default`

**Why.** new-api style relays serve models per token *group*, and availability can differ
by where the request comes from (geo/edge routing, per-network channels, or a
temporarily auto-disabled channel). A model can work from your workstation and 503 from
a server with the same token.

**Fix.** Always probe **from the host that will run the bot** (Step 2 in SKILL.md). If
the desired variant (e.g. a `[1m]` context variant) 503s from that host, either use the
plain variant that probes 200, or fix the relay's channel config for that group — the
bot's config cannot compensate.

## Trap 4: `/v1/models` is not authority

On new-api relays, `GET /v1/models` is frequently incomplete (models missing from the
list can still serve; listed models can still 503 for your group). Never conclude "the
relay doesn't have model X" from the listing. The POST probe is the only test that
matters; a 200 with real content trumps the listing, and a self-identify prompt
("你是哪家公司开发的什么模型？") tells you whether the channel routes to the expected
model family or silently misroutes.

## Trap 5: Edit saved + gateway restarted, behavior unchanged

Check in order:

1. **Wrong file edited** — multiple `openclaw.json` exist (see Step 1 of SKILL.md);
   `openclaw gateway status` prints the live one. Mirrors must be edited together.
2. **Gateway not actually restarted** — confirm a NEW pid after `openclaw gateway restart`.
3. **A plugin overrides your value** — provider plugins can supply their own baseUrl/auth
   resolution and model normalization; the provider block you edited may not be the
   provider actually serving the model id (check the run metadata's `provider` field in
   the Step-4 verification output).
4. **Fallback masked the failure** — `fallbackUsed: true` means your target failed.

## Appendix: wire-capture recipe (see exactly what OpenClaw sends)

Run a throwaway echo server on the OpenClaw host, point the provider at it, fire one
agent turn, read the captured request:

```bash
cat > /tmp/cap.py <<'EOF'
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with open("/tmp/captured.txt", "a") as f:
            f.write("=== %s ===\n" % self.path)
            for k, v in self.headers.items(): f.write("%s: %s\n" % (k, v))
            f.write("BODY: %s\n\n" % body.decode("utf-8", "replace")[:400])
        resp = b'{"id":"msg_x","type":"message","role":"assistant","model":"m","content":[{"type":"text","text":"ok"}],"stop_reason":"end_turn","usage":{"input_tokens":1,"output_tokens":1}}'
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length", str(len(resp))); self.end_headers()
        self.wfile.write(resp)
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", 8899), H).serve_forever()
EOF
nohup python3 /tmp/cap.py >/dev/null 2>&1 &
# temporarily set models.providers.<p>.baseUrl = http://127.0.0.1:8899 , then:
openclaw agent --local --json --agent main --session-id cap-$(date +%s) -m "hi"
cat /tmp/captured.txt   # <- the real x-api-key / headers / body on the wire
# restore baseUrl, kill the echo server, remove /tmp/cap.py /tmp/captured.txt
```

The captured `x-api-key` value is ground truth for Trap 1; the captured `model` field
proves whether id mapping rewrote your model id; the captured `thinking`/`output_config`
block shows the exact thinking payload (Trap 2 variant B).
