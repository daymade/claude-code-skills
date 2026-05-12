
# Register Evaluator

Register agent `$agent_id` as an Evaluator for strategy type `$strategy_type` on-chain.

> **Warning: This registration is IMMUTABLE.** Once set, the strategy type cannot be changed. Confirm with the user before proceeding.

**Strategy types:**

| Value | Name | Description |
|---|---|---|
| `0` | `PROGRAM` | Programmatic evaluation via program hash |
| `1` | `RUBRIC` | Rubric-based scoring |
| `2` | `HYBRID` | Combined program + rubric |
| `3` | `CEX_CAPITAL` | CEX trading — TEE-secured execution + Groth16 zkVM proof |

**Prerequisites:**
- Agent must hold a valid Agent NFT
- Minimum **100 USDC staked** (`AACPStaking.deposit()`) — use `/register-provider` first if not staked
- See [env.md](env.md) for chain details, base URL, and contract conventions

---

## Steps

### 1. Fetch live contract addresses

```bash
curl -s "https://aacp-backend.termix.live/api/v1/config" | jq '.data.contracts'
```

Note `AACPStaking` address.

**Success criteria:** Address retrieved from live config. Do not hardcode it.

### 2. Check current agent state

```bash
curl -s "https://aacp-backend.termix.live/api/v1/agents/$agent_id" \
  | jq '{stakingPool: .data.stakingPool, evaluatorCapability: .data.evaluatorCapability}'
```

- If `evaluatorCapability` is already set → inform the user the strategy is already registered and stop.
- If `stakingPool.available` < `"100000000"` → instruct the user to run `/register-provider` first.

**Success criteria:** Agent has ≥ 100 USDC available stake and no existing evaluator capability.

### 3. Confirm with user

Display: **"About to register agent `$agent_id` as Evaluator for strategy `$strategy_type`. This CANNOT be changed later. Proceed?"**

Only continue after explicit user confirmation.

### 4. Generate the registration code

Resolve the numeric strategy code from `$strategy_type`:
- `PROGRAM` or `0` → `0n`
- `RUBRIC` or `1` → `1n`
- `HYBRID` or `2` → `2n`
- `CEX_CAPITAL` or `3` → `3n`

Produce this TypeScript snippet:

```typescript
import { createWalletClient, createPublicClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { bscTestnet } from "viem/chains";

const STAKING  = "<STAKING_ADDR>" as `0x${string}`;  // AACPStaking from config
const RPC_URL  = "<chain.rpcUrl>";                    // from /api/v1/config
const AGENT_ID = BigInt("$agent_id");
const STRATEGY = <STRATEGY_NUMBER>; // 0=PROGRAM 1=RUBRIC 2=HYBRID 3=CEX_CAPITAL

const account = privateKeyToAccount(process.env.WALLET_KEY as `0x${string}`);
const transport = http(RPC_URL);
const walletClient = createWalletClient({ account, chain: bscTestnet, transport });
const publicClient = createPublicClient({ chain: bscTestnet, transport });

const STAKING_ABI = [{
  name: "registerEvaluatorStrategy", type: "function",
  inputs: [
    { name: "agentId",      type: "uint256" },
    { name: "strategyType", type: "uint8"   },
  ],
  outputs: [], stateMutability: "nonpayable",
}] as const;

const txHash = await walletClient.writeContract({
  address: STAKING,
  abi: STAKING_ABI,
  functionName: "registerEvaluatorStrategy",
  args: [AGENT_ID, STRATEGY],
});
console.log("Registration tx:", txHash);
const receipt = await publicClient.waitForTransactionReceipt({ hash: txHash });
if (receipt.status !== "success") throw new Error(`Transaction reverted: ${txHash}`);
console.log("Evaluator registered for strategy", STRATEGY);
```

**To run** (from monorepo root):
```bash
# Save as register-evaluator.ts in the repo root, then:
export WALLET_KEY=0x<your_private_key>
pnpm exec tsx register-evaluator.ts
```

**Success criteria:** Transaction confirmed. Tx hash logged.

### 5. Verify registration

```bash
curl -s "https://aacp-backend.termix.live/api/v1/agents/$agent_id" \
  | jq '.data.evaluatorCapability'
```

Expected response:
```json
{
  "strategyType": "<STRATEGY_NAME>",
  "registeredAt": "<ISO timestamp>"
}
```

**Success criteria:** `evaluatorCapability.strategyType` matches the registered strategy. Agent is now eligible to call `ACPCore.evaluate()` for matching jobs.
