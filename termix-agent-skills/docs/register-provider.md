
# Register Provider / Stake Agent

Deposit MockUSDC stake on-chain so agent `$agent_id` has an AACP staking pool.

Provider agents need this to submit offers and act as Providers. Client agents also need a staking pool before calling `createJob`; without one, `createJob` can revert with selector `0x4e236e9a`.

**Minimum stake:** 100 USDC  
See [env.md](env.md) for chain details, base URL, and contract conventions.
**Requires:** wallet private key with BNB for gas + MockUSDC balance

---

## Steps

### 1. Fetch live contract addresses

```bash
curl -s "https://aacp-backend.termix.live/api/v1/config" | jq '.data.contracts'
```

Note the following addresses from the response:
- `AACPStaking` — staking contract
- `MockUSDC` — USDC token to approve

**Success criteria:** Addresses retrieved. Do not hardcode them.

### 2. Check current stake (optional)

```bash
curl -s "https://aacp-backend.termix.live/api/v1/agents/$agent_id" \
  | jq '.data.stakingPool'
```

Display current `available` and `locked` balances (divide by 1e6 for USDC). If the pool is `null`, deposit before using the agent as a Provider or as a Client for `createJob`. If already ≥ 100 USDC available, the agent can submit offers; Clients also need enough available stake for the create-job lock.

### 3. Generate the stake deposit code

Produce this TypeScript snippet for the user to run. Replace `<STAKING_ADDR>` and `<USDC_ADDR>` with the addresses from Step 1, and `<AMOUNT_USDC>` with `$amount_usdc` (default 200 if not specified):

```typescript
import { createWalletClient, createPublicClient, http, parseUnits } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { bscTestnet } from "viem/chains";

const STAKING  = "<STAKING_ADDR>" as `0x${string}`;  // AACPStaking from config
const USDC     = "<USDC_ADDR>"    as `0x${string}`;   // MockUSDC from config
const RPC_URL  = "<chain.rpcUrl>";                     // from /api/v1/config
const AGENT_ID = BigInt("$agent_id");
const AMOUNT   = parseUnits("<AMOUNT_USDC>", 6);       // 6 decimals

const account = privateKeyToAccount(process.env.WALLET_KEY as `0x${string}`);
const transport = http(RPC_URL);
const walletClient = createWalletClient({ account, chain: bscTestnet, transport });
const publicClient = createPublicClient({ chain: bscTestnet, transport });

const ERC20_APPROVE_ABI = [{
  name: "approve", type: "function",
  inputs: [{ name: "spender", type: "address" }, { name: "amount", type: "uint256" }],
  outputs: [{ type: "bool" }], stateMutability: "nonpayable",
}] as const;

const STAKING_ABI = [{
  name: "deposit", type: "function",
  inputs: [{ name: "agentId", type: "uint256" }, { name: "amount", type: "uint256" }],
  outputs: [], stateMutability: "nonpayable",
}] as const;

// Step 1: Approve staking contract to spend USDC
const approveHash = await walletClient.writeContract({
  address: USDC, abi: ERC20_APPROVE_ABI,
  functionName: "approve", args: [STAKING, AMOUNT],
});
console.log("Approve tx:", approveHash);
await publicClient.waitForTransactionReceipt({ hash: approveHash });
console.log("Approved");

// Step 2: Deposit stake
const depositHash = await walletClient.writeContract({
  address: STAKING, abi: STAKING_ABI,
  functionName: "deposit", args: [AGENT_ID, AMOUNT],
});
console.log("Deposit tx:", depositHash);
await publicClient.waitForTransactionReceipt({ hash: depositHash });
console.log(`Staked <AMOUNT_USDC> USDC for agent ${AGENT_ID}`);
```

**To run** (from monorepo root):
```bash
# Save as stake-provider.ts in the repo root, then:
export WALLET_KEY=0x<your_private_key>
pnpm exec tsx stake-provider.ts
```

**Success criteria:** Both transactions confirmed on BSC Testnet. Tx hashes logged.

### 4. Verify stake was recorded

After the transactions confirm (~3–5 seconds), check the updated balance:

```bash
curl -s "https://aacp-backend.termix.live/api/v1/agents/$agent_id" \
  | jq '.data.stakingPool'
```

Display:
- `available` ÷ 1e6 USDC — funds available for offer submissions
- `locked` ÷ 1e6 USDC — funds currently locked in active jobs
- `violationCount` — slash violations

**Success criteria:** `available` shows the newly deposited amount. Provider agents can now submit offers (requires ≥ 100 USDC available and reputation ≥ 70); Client agents can now pass the `createJob` staking-pool precondition.
