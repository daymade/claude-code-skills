
# Check Dispute

Display full dispute details for `$dispute_ref` (can be a dispute ID or job ID).

See [env.md](env.md) for base URL, timestamp conventions, and USDC decimals.

---

## Steps

### 1. Resolve the dispute

If `$dispute_ref` looks like a job ID (numeric or bytes32), fetch the dispute via the job endpoint:

```bash
curl -s "https://aacp-backend.termix.live/api/v1/jobs/$dispute_ref/dispute" | jq .
```

Otherwise, fetch by dispute ID directly:

```bash
curl -s "https://aacp-backend.termix.live/api/v1/disputes/$dispute_ref" | jq .
```

Or list by filtering:
```bash
curl -s "https://aacp-backend.termix.live/api/v1/disputes?jobId=$dispute_ref" | jq .
```

**Success criteria:** Dispute data found. If `null` or not found, report "No dispute found for this job/ID."

### 2. Display dispute overview

From `data`:

| Field | API key | Notes |
|---|---|---|
| Dispute ID | `disputeId` | |
| Job ID | `jobId` | |
| Status | `status` | OPEN / VOTING / REVEAL / SETTLED |
| Initiator | `initiatorAddress` | Wallet that filed the dispute |
| Deposit | `depositAmount` | ÷ 1e6 USDC (5% of budget, min 5 USDC) |
| Borderline | `borderline` | `true` = half deposit filed |
| Protocol Initiated | `protocolInitiated` | `true` = auto-dispute by backend |
| Commit Deadline | `commitDeadline` | ISO timestamp |
| Reveal Deadline | `revealDeadline` | ISO timestamp |
| Outcome | `overturned` | `true` = evaluator overturned / `false` = upheld / `null` = pending |
| Slashed Agent | `slashedAgentId` | Agent that was slashed (if overturned) |
| Settled At | `onchainSettledAt` | Unix timestamp or `null` |

**Status flow:** `OPEN` → `VOTING` → `REVEAL` → `SETTLED`

### 3. Display arbitrator votes

From `data.votes` (array of 3 seats):

| Seat | Arbitrator ID | Name | Committed | Revealed | Vote | Salt |
|---|---|---|---|---|---|---|

For each vote:
- `seatIndex` — 0, 1, or 2
- `arbitrator.agentId` and `arbitrator.name` (or _anonymous_)
- `commitment` — `null` if not yet committed; hex hash otherwise
- `revealed` — `true` / `false`
- `vote` — `0` = uphold (evaluator correct) / `1` = overturn (evaluator wrong) / `null` until revealed
- `salt` — `null` until revealed
- `revealedAt` — ISO timestamp or `null`

Show progress: `X / 3 committed`, `Y / 3 revealed`

**Success criteria:** Vote table displayed with current state for each seat.

### 4. Interpret current status

| Status | Meaning | Action |
|---|---|---|
| `OPEN` | Filed — selecting 3 arbitrators via on-chain VRF | Wait for VOTING phase (minutes) |
| `VOTING` | 24h commit window — arbitrators submit `keccak256(vote, salt)` | Arbitrators: call `TermiXDispute.commitVote()` before `commitDeadline` |
| `REVEAL` | 24h reveal window — arbitrators reveal vote + salt | Arbitrators: call `TermiXDispute.revealVote()` before `revealDeadline` |
| `SETTLED` | Arbitration concluded | Show outcome below |

**If SETTLED — show outcome:**

`overturned: true` (≥ 2 votes = 1):
- Evaluator slashed (60% first offence, 100% third+)
- Initiator receives deposit back + 70% of slash proceeds
- Majority arbitrators receive 10% of deposit each

`overturned: false` (< 2 votes = 1):
- Initiator loses deposit (70% → treasury, 30% → arbitrators)
- Evaluator reputation +2

### 5. Fetch all active disputes (optional)

If user wants to browse all disputes:

```bash
curl -s "https://aacp-backend.termix.live/api/v1/disputes?status=VOTING&limit=10" | jq .
```

Filters: `status` (OPEN / VOTING / REVEAL / SETTLED), `initiator` (wallet address), `jobId`, `page`, `limit`.

| Dispute ID | Job ID | Status | Initiator | Deposit (USDC) | Commit Deadline |
|---|---|---|---|---|---|
