
# Provider Submit

Submit the deliverable for job `$job_id` on-chain as Provider.

See [env.md](env.md) for base URL, chain details, and contract conventions.
**Requires:** Provider wallet private key (owner of assigned Provider Agent NFT)

---

## Steps

### 1. Check job status

```bash
curl -s "https://aacp-backend.termix.live/api/v1/jobs/$job_id" \
  | jq '{status: .data.status, strategyType: .data.strategyType, providerId: .data.providerId, onchainDeadline: .data.onchainDeadline}'
```

Check:
- `status` must be `FUNDED` — `submit()` is only valid in this state
- Note `strategyType` — determines which flow to follow below
- Note `onchainDeadline` for operator context. For `CEX_CAPITAL`, do not treat decoded deadline values from raw `jobs(bytes32)` reads as authoritative; see Flow B notes.

**Success criteria:** Job is FUNDED and assigned to this Provider.

### 2. Fetch contract addresses

```bash
curl -s "https://aacp-backend.termix.live/api/v1/config" \
  | jq '.data.contracts.AACPCore'
```

**Success criteria:** `ACPCore` address retrieved from live config. Do not hardcode it.

---

## Flow A — Standard strategies (PROGRAM / RUBRIC / HYBRID)

### A.1 Prepare the deliverable hash

The `deliverableHash` is `keccak256` of the Provider's deliverable (e.g. IPFS CID, computation result, or output file hash). The Provider must compute this from their actual output.

```typescript
import { keccak256, toHex } from "viem";

// Example: hash of a deliverable string or file content
const deliverableHash = keccak256(toHex("your deliverable content here"));
console.log("deliverableHash:", deliverableHash);
```

### A.2 Call submit() on-chain

```typescript
import { createWalletClient, createPublicClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { bscTestnet } from "viem/chains";

const ACP_CORE    = "<AACPCore>"          as `0x${string}`;  // from config (key: "AACPCore")
const RPC_URL     = "<chain.rpcUrl>";                         // from /api/v1/config
const JOB_ID      = "<job_id>"            as `0x${string}`;
const DELIVERABLE = "<deliverableHash>"   as `0x${string}`;

const account = privateKeyToAccount(process.env.WALLET_KEY as `0x${string}`);
const transport = http(RPC_URL);
const walletClient = createWalletClient({ account, chain: bscTestnet, transport });
const publicClient = createPublicClient({ chain: bscTestnet, transport });

const ABI = [{
  name: "submit", type: "function",
  inputs: [
    { name: "jobId",           type: "bytes32" },
    { name: "deliverableHash", type: "bytes32" },
  ],
  outputs: [], stateMutability: "nonpayable",
}] as const;

console.log("Simulating submit()...");
await publicClient.simulateContract({
  account,
  address: ACP_CORE,
  abi: ABI,
  functionName: "submit",
  args: [JOB_ID, DELIVERABLE],
});
console.log("Simulation OK");

const txHash = await walletClient.writeContract({
  address: ACP_CORE, abi: ABI,
  functionName: "submit",
  args: [JOB_ID, DELIVERABLE],
});
console.log("submit() tx:", txHash);
const receipt = await publicClient.waitForTransactionReceipt({ hash: txHash });
if (receipt.status !== "success") throw new Error(`submit() reverted: ${txHash}`);
console.log("Deliverable submitted. Status will move to SUBMITTED.");
```

**To run** (from monorepo root):
```bash
# Save as submit-job.ts in the repo root, then:
export WALLET_KEY=0x<provider_private_key>
pnpm exec tsx submit-job.ts
```

---

## Flow B — CEX_CAPITAL strategy

For `CEX_CAPITAL` jobs, the deliverable hash comes from the TEE enclave.

> **Current contract behavior:** Older notes said `submit()` requires both TEE closure and elapsed deadline. Live testing showed `CEX_CAPITAL submit()` can simulate and execute successfully before that expected deadline gate, so follow the deployed contract behavior: simulate first, and if simulation succeeds, submit. Use TEE closure as the preferred operational signal for final deliverable data, not as a guaranteed on-chain lock.
>
> **Deadline decoding caveat:** Reading `jobs(bytes32)` with the nominal ABI can return an impossible `deadline` for `CEX_CAPITAL` jobs, for example `500000000` (1985-11-05 UTC). This appears to be a struct layout / ABI mismatch for that strategy. Prefer the backend job API and TEE status for display, and do not block `submit()` solely because raw viem decoding reports a strange deadline.

### B.1 Wait for TEE to close

Poll until `state === "closed"`:

```bash
curl -s "https://aacp-backend.termix.live/api/v1/tee/jobs/$job_id/status" | jq .
```

TEE closes automatically when:
- `onchainDeadline` is reached (TEE auto-liquidates all positions), OR
- Stop-loss is triggered

Expected response when closed:
```json
{
  "state": "closed",
  "closed_reason": "deadline",
  "balance_report": { "usdt_balance": "1050.00", "positions": [] },
  "enclave_signature": "0x..."
}
```

**On-chain deadline note:**
Do not require `block.timestamp ≥ job.deadline` for `CEX_CAPITAL` unless simulation reverts for that reason. Current deployed behavior has allowed immediate `submit()` after successful simulation/execution.

**Success criteria:** Prefer `state === "closed"` when deriving the TEE deliverable hash. If the job must be submitted earlier, rely on `simulateContract` against the deployed contract and submit only if simulation succeeds.

### B.2 Compute deliverableHash from TEE output

```typescript
import { keccak256, toHex } from "viem";

const enclaveSignature = "<enclave_signature from TEE>";
const finalBalance     = "<balance_report.usdt_balance from TEE>";

// deliverableHash = keccak256(enclave_signature + "|" + final_balance)
const deliverableHash = keccak256(
  toHex(`${enclaveSignature}|${finalBalance}`)
);
console.log("deliverableHash:", deliverableHash);
```

### B.3 Call submit() on-chain

Same code as Flow A, using the `deliverableHash` computed in B.2.

Alternatively, use the reference script if available:
```bash
export WALLET_KEY=0x<provider_private_key>
python3 packages/backend/scripts/settle_job.py $job_id
```

---

## Step 3 — Verify submission

```bash
curl -s "https://aacp-backend.termix.live/api/v1/jobs/$job_id" \
  | jq '{status: .data.status, deliverableHash: .data.deliverableHash, onchainSubmittedAt: .data.onchainSubmittedAt}'
```

Expected: `"status": "SUBMITTED"`, `deliverableHash` set, `onchainSubmittedAt` populated.

**Success criteria:** Job is `SUBMITTED`. The Evaluator will now be able to call `evaluate()`. Use `/client-view-job $job_id` to monitor final outcome.
