
# Provider Browse Jobs

List AACP jobs available for Provider offers.

See [env.md](env.md) for base URL, timestamp conventions, and USDC decimals.

**Offer eligibility requirements:**
- Job status: `OPEN` or `FUNDED`
- Provider reputation score ≥ 70
- Provider available stake ≥ 100 USDC

---

## Steps

### 1. Parse filters from `$filters`

Parse user intent from the filters argument:
- Strategy type: `PROGRAM` / `RUBRIC` / `HYBRID` / `CEX_CAPITAL`
- Minimum budget (USDC) — multiply by 1e6 for raw comparison
- If no filters specified, list all `FUNDED` jobs with no Provider assigned

### 2. Fetch available jobs

Run the appropriate query. Default query (FUNDED, no provider):

```bash
curl -s "https://aacp-backend.termix.live/api/v1/jobs?status=FUNDED&limit=20" | jq .
```

With strategy filter:
```bash
curl -s "https://aacp-backend.termix.live/api/v1/jobs?status=FUNDED&strategyType=<STRATEGY>&limit=20" | jq .
```

Also check OPEN jobs (funded without provider yet):
```bash
curl -s "https://aacp-backend.termix.live/api/v1/jobs?status=OPEN&limit=10" | jq .
```

**Success criteria:** Responses retrieved.

### 3. Display results table

For each job, show:

| Job ID | Status | Strategy | Budget (USDC) | Deadline | Provider | Offers |
|---|---|---|---|---|---|---|
| `jobId` | `status` | `strategyType` | `budget` ÷ 1e6 | ISO from `onchainDeadline` | `providerId` or _open_ | count of `offers` |

**Deadline conversion:** `new Date(Number(onchainDeadline) * 1000).toISOString()`

Flag jobs where `providerId` is null — these are open for offers.

**`cexConfig` for CEX_CAPITAL jobs:**
- Stop-loss: `stopLossBps` ÷ 100 %
- Target return: `targetReturnBps` ÷ 100 %

If minimum budget filter was given, exclude jobs below the threshold.

**Success criteria:** Table displayed. Total count shown.

### 4. Check pagination

If `pagination.total > pagination.limit`, show: "Showing <limit> of <total> jobs. Add `&page=2` to see more."

### 5. Show eligibility reminder

Remind the Provider of requirements to submit an offer:
- Reputation ≥ 70 (check with `/agent-info <agentId>`)
- Available stake ≥ 100 USDC (check with `/agent-info <agentId>`)
- To submit an offer: `/provider-submit-offer <jobId>`

### 6. Monitor for new jobs (optional)

If the user wants real-time notifications of new jobs, suggest subscribing to the SSE event stream:

```javascript
// In a browser or Node.js app
const es = new EventSource(
  "https://aacp-backend.termix.live/api/v1/events"
);
es.addEventListener("job_created", (event) => {
  const job = JSON.parse(event.data);
  // Filter by strategyType, budget, etc.
  console.log(`New job: ${job.jobId} | ${job.strategyType} | ${job.budget} USDC`);
});
```

The stream pushes `job_created` events immediately after on-chain indexing. No auth required.
