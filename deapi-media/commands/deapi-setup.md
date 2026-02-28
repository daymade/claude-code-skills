---
name: deapi-setup
description: Configure result delivery method for deAPI jobs (polling, webhooks, websockets)
---

# Result Delivery Setup

Configure how your application receives job results.

## Step 1: Determine context

Ask user about their use case:

| Context | Recommended method |
|---------|-------------------|
| CLI tool, local script | **Polling** (default) |
| Backend server, serverless | **Webhooks** |
| Real-time UI, SPA | **WebSockets** |

## Step 2: Configure based on method

### Polling (default)

No configuration needed. Use `/request-status/{id}` endpoint.
Already built into all deAPI commands.

```bash
curl -s "https://api.deapi.ai/api/v1/client/request-status/{request_id}" \
  -H "Authorization: Bearer $DEAPI_API_KEY"
```

Poll every 10 seconds until `status = "done"`.

### Webhooks

Add `webhook_url` to any request:

```json
{
  "prompt": "...",
  "webhook_url": "https://your-server.com/webhooks/deapi"
}
```

**Events received:**
- `job.completed` - contains `result_url`
- `job.failed` - contains `error_code`

**Security:** Verify signature in `X-DeAPI-Signature` header (HMAC-SHA256).

Full docs: https://docs.deapi.ai/execution-modes-and-integrations/webhooks

### WebSockets

Connect via Pusher protocol for real-time updates:

| Setting | Value |
|---------|-------|
| Host | `soketi.deapi.ai:443` |
| Channel | `private-client.{client_id}` |
| Event | `request.status.updated` |

Includes live preview images during generation.

Full docs: https://docs.deapi.ai/execution-modes-and-integrations/websockets

## Step 3: Generate boilerplate

Based on user's choice, generate starter code for their stack.

**Webhook handler (Node.js/Express):**
```javascript
app.post('/webhooks/deapi', (req, res) => {
  const signature = req.headers['x-deapi-signature'];
  // Verify signature with your webhook secret

  const { event, request_id, result_url, error } = req.body;

  if (event === 'job.completed') {
    // Process result from result_url
  } else if (event === 'job.failed') {
    // Handle error
  }

  res.status(200).send('OK');
});
```

**Webhook handler (Python/FastAPI):**
```python
from fastapi import FastAPI, Request, Header

app = FastAPI()

@app.post("/webhooks/deapi")
async def deapi_webhook(
    request: Request,
    x_deapi_signature: str = Header(None)
):
    # Verify signature with your webhook secret
    body = await request.json()

    if body["event"] == "job.completed":
        result_url = body["result_url"]
        # Process result
    elif body["event"] == "job.failed":
        error = body["error"]
        # Handle error

    return {"status": "ok"}
```

**WebSocket client (JavaScript):**
```javascript
import Pusher from 'pusher-js';

const pusher = new Pusher('your-app-key', {
  wsHost: 'soketi.deapi.ai',
  wsPort: 443,
  forceTLS: true,
  disableStats: true,
  enabledTransports: ['ws', 'wss']
});

const channel = pusher.subscribe(`private-client.${clientId}`);

channel.bind('request.status.updated', (data) => {
  if (data.status === 'done') {
    // Fetch result from data.result_url
  }
});
```

## Error handling

| Error | Action |
|-------|--------|
| Webhook timeout | Retry with exponential backoff (1s, 2s, 4s) |
| Invalid signature | Verify webhook secret matches dashboard config |
| WebSocket disconnect | Reconnect with backoff, resubscribe to channel |
| 401 on polling | Check `DEAPI_API_KEY` is valid |
| Missing `result_url` | Job may still be processing, continue polling |

## When to suggest this skill

Proactively suggest `/deapi-setup` when user mentions:
- Building a web app with deAPI
- Server-side integration
- Real-time UI updates
- Production deployment
