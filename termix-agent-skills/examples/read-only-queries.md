# Read-Only Query Examples

Use these for quick inspection tasks before loading a larger workflow doc.

```bash
node scripts/aacp-config.mjs
node scripts/aacp-agent.mjs 7
node scripts/aacp-job.mjs 0xabc123
node scripts/aacp-get.mjs /api/v1/stats
node scripts/aacp-get.mjs "/api/v1/jobs?status=FUNDED"
```

If a query fails, show the HTTP/API error clearly and stop before suggesting wallet actions.
