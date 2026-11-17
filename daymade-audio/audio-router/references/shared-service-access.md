# Shared service access

Use this route in a deployment that already supplies daudio. Its deployment owner
provides the endpoint, originating device identity, enabled provider profiles and
frozen client artifacts. If those are unavailable, retain the unresolved setup
step; do not borrow another environment or invent configuration. Unbound standalone
workflows continue through their existing specialist.

## Choose the consumer boundary

| Consumer | Entry and retained responsibility |
|---|---|
| Ordinary application | Independent Python `daudio-client` or JS `@daymade/daudio-client`; one configured HTTP service contract. Capture, presentation and playback remain with the application. |
| Trusted service/native worker | Full runtime and explicitly bound engine/profile near its input. Credentials, identity decisions and durable execution remain here. |
| Explicit local/realtime deployment | Use the application's declared local mode and existing hardware adapter. A transport error never selects local execution automatically. |

Install only the selected client artifact through the application's dependency
owner. Install the Python wheel into the interpreter that actually consumes the
binding; a successful import in another virtual environment proves no readiness.
The full runtime, model assets and long-lived provider credentials do not belong
in a default application client. Client mode does not grant server permissions.

Before a paid or mutating operation, retain its specialist's authorization and
verify the configured provider/profile. Do not silently substitute another engine.
Submit through the normal job entry; an application does not start a competing
queue. The domain service owns any dqueue binding and HomeLab worker lifecycle.

## Equivalent SDK calls

These prepare one probe without executing it. Supply the configured endpoint,
existing versioned recording URI and task-specific key; do not replace them with
guessed values. Obtain matching thin packages from the deployment's release kit.

```python
import os
from daudio_client import DaudioClient

client = DaudioClient()  # configured DAUDIO_ENDPOINT / DAUDIO_CONFIG
job = client.submit_job(
    "probe", os.environ["DAUDIO_SOURCE_URI"], "ffprobe",
    idempotency_key=os.environ["DAUDIO_IDEMPOTENCY_KEY"], execute=False,
)
```

```javascript
import {DaudioClient} from '@daymade/daudio-client/node';

const endpoint = process.env.DAUDIO_ENDPOINT;
const sourceUri = process.env.DAUDIO_SOURCE_URI;
const idempotencyKey = process.env.DAUDIO_IDEMPOTENCY_KEY;
if (!endpoint || !sourceUri || !idempotencyKey) throw new Error('Missing deployment input');
const client = new DaudioClient({endpoint});
const job = await client.submitJob({
  operation: 'probe', sourceUri, provider: 'ffprobe', options: {}, idempotencyKey, execute: false,
});
```

Browser consumers use the package root with explicit application configuration;
the `/node` entry's environment/profile discovery is not a browser interface.
Python uses snake_case arguments and JS uses the documented camelCase fields.

## Read the usable result

Keep the returned job identity, original source version and result references.
Read the selected operation's actual payload: probe format/streams may live in
`metadata.provider_result` with empty `outputs`; ASR needs its readable transcript,
and TTS needs its accessible audio. A queued job, workflow success or an empty
output list alone decides none of those outcomes. Replay the same request through
the existing idempotency path; unknown completion is not permission to infer again.

Read shared dictionary, roster, context and identity evidence through their bound
versioned resource references. Preserve human labels and the distinction between
candidate, explicit human mapping and calibrated identity evidence. Do not create
another application-local identity truth or enroll a proposed name as voice truth.
