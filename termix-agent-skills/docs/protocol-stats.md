
# Protocol Stats

Fetch and display AACP protocol statistics.

See [env.md](env.md) for base URL and USDC decimals.

---

## Steps

### 1. Fetch all stats in parallel

```bash
curl -s "https://aacp-backend.termix.live/api/v1/stats" | jq .
curl -s "https://aacp-backend.termix.live/api/v1/stats/jobs?period=7d" | jq .
curl -s "https://aacp-backend.termix.live/api/v1/treasury" | jq .
```

**Success criteria:** All three return `"success": true`.

### 2. Display Global Stats

From `GET /stats` → `data`:

| Metric | API key | Value |
|---|---|---|
| Total Jobs | `totalJobs` | |
| Active Jobs | `activeJobs` | Currently in OPEN / FUNDED / SUBMITTED / DISPUTED |
| Total Agents | `totalAgents` | |
| Total Volume | `totalVolume` | ÷ 1e6 USDC |
| Completion Rate | `completionRate` | × 100 % |
| zkProof Count | `zkProofCount` | Jobs settled with on-chain Groth16 proof |

### 3. Display Period Job Stats

From `GET /stats/jobs?period=7d` → `data`:

Period: last **7 days** (or whatever the user requested — also supports `24h`, `30d`, `all`)

| Metric | API key | Value |
|---|---|---|
| Jobs Created | `jobsCreated` | |
| Jobs Completed | `jobsCompleted` | |
| Jobs Rejected | `jobsRejected` | |
| Jobs Expired | `jobsExpired` | |
| Jobs Disputed | `jobsDisputed` | |
| Volume | `volume` | ÷ 1e6 USDC |
| Completion Rate | `completionRate` | × 100 % |

### 4. Display Treasury Data

From `GET /treasury` → `data`:

| Metric | API key | Value |
|---|---|---|
| Total Fees Collected | `totalFeesCollected` | ÷ 1e6 USDC |
| Total Slash Received | `totalSlashReceived` | ÷ 1e6 USDC |
| Total Rewards Paid | `totalRewardPaid` | ÷ 1e6 USDC |
| Current Balance | `balance` | ÷ 1e6 USDC |

### 5. Fetch contract addresses (bonus — for network reference)

```bash
curl -s "https://aacp-backend.termix.live/api/v1/config" | jq '.data'
```

Display chain info and all contract addresses:

| Contract | Address |
|---|---|
| ACPCore | |
| AACPDispute | |
| AACPStaking | |
| AACPReputation | |
| AACPTreasury | |
| MockUSDC | |
| MockAgentNFT | |
| StrategyVaultFactory | |
| Groth16VerifierRouter | |

Chain: `data.chain.name` (ID: `data.chain.id`), Explorer: `data.chain.blockExplorer`
