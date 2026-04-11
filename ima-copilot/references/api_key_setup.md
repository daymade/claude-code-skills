# API Key Setup — Deep Dive

This document covers the full flow for provisioning IMA OpenAPI credentials and verifying they work. The agent reads this when the user asks to configure credentials, or when `diagnose.sh` reports ❌ on API credentials.

## Where credentials go

Credentials are stored XDG-style, completely decoupled from any agent's skill directory:

| Path                         | Purpose            | Mode |
|------------------------------|--------------------|------|
| `~/.config/ima/`             | Config directory   | `700` |
| `~/.config/ima/client_id`    | IMA Client ID      | `600` |
| `~/.config/ima/api_key`      | IMA API Key        | `600` |

The two files contain raw values, one per file, with an optional trailing newline. No JSON, no env wrapping, no key prefixes. This keeps the files trivially readable by both the `diagnose.sh` bash script and `search_fanout.py`.

### Why not one file?

Two files are easier to rotate independently — you can update the API key without touching the client ID, and a leaked `cat` of one file doesn't expose the other.

### Why not `~/.ima/`?

`~/.config/ima/` follows the XDG Base Directory Specification, which is the convention for user-level configuration on Linux and increasingly on macOS. Tools that honor `$XDG_CONFIG_HOME` will find the credentials in a predictable place.

## Environment variable fallback

The wrapper reads environment variables first, then falls back to the config files:

| Env var                  | Fallback file               |
|--------------------------|-----------------------------|
| `IMA_OPENAPI_CLIENTID`   | `~/.config/ima/client_id`   |
| `IMA_OPENAPI_APIKEY`     | `~/.config/ima/api_key`     |

Use env vars when:
- Running in CI or ephemeral containers where persisting a file is awkward
- Rotating credentials mid-session without editing a file
- Testing with different credentials without touching the committed config

Use the files when:
- Running locally for long sessions (no need to re-export every time)
- Sharing a machine with multiple users (files have per-user permissions)

## Walkthrough

### Step 1 — Obtain credentials

Open `https://ima.qq.com/agent-interface` in a browser. If the user isn't signed in, they'll be prompted. The page shows a panel titled "API Key" with buttons to generate a new Client ID + API Key pair.

The page currently talks about "发给小龙虾以完成配置" ("send to OpenClaw to finish config") — the user can ignore that. What they need is just the Client ID value and the API Key value shown on that page.

### Step 2 — Save to files

```bash
mkdir -p ~/.config/ima
chmod 700 ~/.config/ima
printf '%s' "<paste client id here>" > ~/.config/ima/client_id
printf '%s' "<paste api key here>"   > ~/.config/ima/api_key
chmod 600 ~/.config/ima/client_id ~/.config/ima/api_key
```

`printf '%s'` writes the value without a trailing newline — slightly more paranoid than `echo` since some tools choke on trailing whitespace when comparing credentials. The wrapper code strips newlines anyway, so either works, but this is the cleaner form.

### Step 3 — Liveness test

The simplest safe call is `search_knowledge_base` with an empty query, limit 1. It's authenticated, returns success quickly on valid credentials, and doesn't create or modify any data.

```bash
CLIENT_ID=$(cat ~/.config/ima/client_id)
API_KEY=$(cat ~/.config/ima/api_key)

curl -sS -X POST "https://ima.qq.com/openapi/wiki/v1/search_knowledge_base" \
  -H "ima-openapi-clientid: $CLIENT_ID" \
  -H "ima-openapi-apikey: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "", "cursor": "", "limit": 1}'
```

Expected response on success:

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "info_list": [ /* 1 kb */ ],
    "is_end": false,
    "next_cursor": "…"
  }
}
```

Any `code` other than `0` indicates a problem. Common codes:

| Code       | Meaning                               | Fix                                |
|------------|---------------------------------------|------------------------------------|
| `0`        | Success                               | N/A — you're done                  |
| Non-zero with "没有权限" | Wrong API key, or key lacks scopes | Regenerate on the agent-interface page |
| Non-zero with "客户端" errors    | Wrong client ID       | Regenerate                         |

If curl returns an empty body or times out, check network reachability to `ima.qq.com` — this API does not respond to ICMP ping, so use `curl -sS -o /dev/null -w "%{http_code}\n" https://ima.qq.com/` as a reachability probe instead.

`diagnose.sh` does this liveness check automatically whenever credentials are present, so after saving the files the user can simply run it and see a ✅ line.

## Credential rotation

To rotate without losing the current session:

```bash
# 1. Generate new Client ID + API Key on https://ima.qq.com/agent-interface
# 2. Overwrite the files
printf '%s' "<new client id>" > ~/.config/ima/client_id
printf '%s' "<new api key>"   > ~/.config/ima/api_key
# 3. Rerun diagnose.sh to confirm the new values are accepted
bash scripts/diagnose.sh
```

The wrapper reads the files on every call, so no cache to invalidate.

## Security considerations

- Both files are user-only readable (`600`) and the containing directory is user-only accessible (`700`). Make sure this remains the case after rotation.
- Do not check these files into git, not even into a private repo. The easiest way to prevent accidents is to keep them in `~/.config/ima/` rather than inside any project directory.
- If the user runs a backup tool that syncs `~/.config/`, be aware that the credentials will be included in the backup. Consider excluding `~/.config/ima/` from backups that leave the local machine.
- The IMA API currently does not scope credentials per-device — a leaked API key can be used from anywhere on the internet until it's rotated.
