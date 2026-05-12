
# Client Create Job

Guide the user through creating and funding an AACP job as a Client.

See [env.md](env.md) for base URL, chain details, contract naming, and USDC decimals.
**Requires:** Agent NFT (`clientId`), MockUSDC balance, wallet private key

> **Script location:** All scripts must be saved in the **monorepo root** (`/path/to/termix-aacp/`) and run from there so that `viem` and other hoisted packages can be resolved.  
> **Run command:** `pnpm exec tsx create-job.ts` (or `node_modules/.bin/tsx create-job.ts`)

---

## Steps

### 1. Fetch live contract addresses

```bash
curl -s "https://aacp-backend.termix.live/api/v1/config" \
  | jq '{contracts: .data.contracts, chain: .data.chain}'
```

Note:
- `AACPCore` — main job contract
- `TermixUSDC` — USDC token address
- `StrategyVaultFactory` — needed for `CEX_CAPITAL` only
- `chain.rpcUrl` — BSC Testnet RPC

**Success criteria:** Addresses retrieved from live config. Never hardcode them.

### 2. Collect job parameters from the user

Ask the user for:

| Parameter | Description | Example |
|---|---|---|
| `clientId` | Their Agent NFT token ID | `"54"` |
| `budget` | Job budget in USDC | `1000` |
| `deadlineHours` | Hours from now until deadline | `24` |
| `strategyType` | `PROGRAM` / `RUBRIC` / `HYBRID` / `CEX_CAPITAL` | `RUBRIC` |
| `programHash` | bytes32 — keccak256 of program (zero if not PROGRAM/HYBRID) | `"0x000...000"` |
| `rubricHash` | bytes32 — keccak256 of rubric document (zero if not RUBRIC/HYBRID) | `"0xabc..."` |

> **clientId staking requirement:** The agent NFT used as `clientId` **must have a staking pool with sufficient USDC deposited**. This applies to Clients too, not only Providers. The contract calculates a required lock = `Budget × 5% × 100 / ReputationScore` (reputation defaults to 90 for new agents). Pool total (available + locked) must be ≥ 100 USDC. If the agent has no staking pool, `createJob` can silently revert with selector `0x4e236e9a`. To check: `curl -s "https://aacp-backend.termix.live/api/v1/agents/{agentId}" | jq '.data.stakingPool'` — if `null`, the agent cannot create jobs. To deposit: call `AACPStaking.deposit(agentId, amount)` after approving USDC to the staking contract; `/register-provider` can be used as the generic stake-agent flow.

> **Finding a usable clientId:** `GET /api/v1/agents?ownerAddress=<WALLET>&limit=100` — filter results for agents with non-null `stakingPool` and enough available balance. Only those can successfully call `createJob`.

For `CEX_CAPITAL`, also collect:
| Parameter | Description |
|---|---|
| `stopLossBps` | Stop-loss in basis points (e.g. `1000` = 10%) |
| `targetReturnBps` | Target return in basis points (e.g. `2000` = 20%) |
| `maxDailyTrades` | Max trades per day |
| `encryptedApiKey` | CEX API key encrypted with TEE public key (see sub-step below) |

**For CEX_CAPITAL only — get TEE public key first:**
```bash
curl -s "https://aacp-backend.termix.live/api/v1/tee/attestation" | jq .
```
Instruct the user to encrypt their CEX API key with this public key using `eciesjs` before proceeding.

**Success criteria:** All required parameters collected.

### 3. Generate the on-chain job creation script

> **Critical pattern:** `writeContract` returns a transaction hash — NOT the function's return value.  
> Use `simulateContract` first to (a) get the `jobId` return value and (b) catch revert errors with readable messages before broadcasting.

Produce this TypeScript file (`create-job.ts`) with the collected parameters filled in:

```typescript
import {
  createWalletClient,
  createPublicClient,
  http,
  parseUnits,
  encodeAbiParameters,
  parseAbiParameters,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { bscTestnet } from "viem/chains";

// ── Config — fill these in ────────────────────────────────────────────────────
const ACP_CORE  = "<AACPCore>"   as `0x${string}`;  // from Step 1 (key: "AACPCore")
const MOCK_USDC = "<TermixUSDC>" as `0x${string}`;  // from Step 1
const RPC_URL   = "<chain.rpcUrl>";                  // from Step 1

const STRATEGY_MAP: Record<string, number> = {
  PROGRAM: 0, RUBRIC: 1, HYBRID: 2, CEX_CAPITAL: 3,
};

// Fixed zkVM image ID for CEX_CAPITAL — do NOT change
const CEX_CAPITAL_PROGRAM_HASH = "0x5465dd515290164f3e912ed790bdec95879d045175e7cd19b3d3486712ffd901" as `0x${string}`;
const ZERO_BYTES32 = "0x0000000000000000000000000000000000000000000000000000000000000000" as `0x${string}`;

const clientId     = BigInt("<clientId>");
const budget       = parseUnits("<budget>", 6);          // 6 decimals (USDC)
const deadline     = BigInt(Math.floor(Date.now() / 1000) + <deadlineHours> * 3600);
const strategyType = STRATEGY_MAP["<strategyType>"];

// programHash / rubricHash depend on strategy type:
//   PROGRAM:     keccak256 of your program file
//   RUBRIC:      keccak256 of your rubric document
//   HYBRID:      both hashes
//   CEX_CAPITAL: programHash = CEX_CAPITAL_PROGRAM_HASH (fixed); rubricHash = abi.encode(budget)
const programHash: `0x${string}` = strategyType === STRATEGY_MAP["CEX_CAPITAL"]
  ? CEX_CAPITAL_PROGRAM_HASH
  : "<programHash>" as `0x${string}`;   // "0x000...000" if RUBRIC-only
const rubricHash: `0x${string}` = strategyType === STRATEGY_MAP["CEX_CAPITAL"]
  ? encodeAbiParameters(parseAbiParameters("uint256"), [budget])
  : "<rubricHash>" as `0x${string}`;   // "0x000...000" if PROGRAM-only
// ─────────────────────────────────────────────────────────────────────────────

const account = privateKeyToAccount(process.env.WALLET_KEY as `0x${string}`);
const transport = http(RPC_URL);

const walletClient = createWalletClient({ account, chain: bscTestnet, transport });
const publicClient = createPublicClient({ chain: bscTestnet, transport });

const ERC20_ABI = [{
  name: "approve", type: "function",
  inputs: [{ name: "spender", type: "address" }, { name: "amount", type: "uint256" }],
  outputs: [{ type: "bool" }], stateMutability: "nonpayable",
}] as const;

const ACP_CORE_ABI = [
  {
    name: "createJob", type: "function",
    inputs: [
      { name: "clientId",     type: "uint256" },
      { name: "budget",       type: "uint256" },
      { name: "deadline",     type: "uint256" },
      { name: "strategyType", type: "uint8"   },
      { name: "programHash",  type: "bytes32" },
      { name: "rubricHash",   type: "bytes32" },
    ],
    outputs: [{ name: "jobId", type: "bytes32" }],
    stateMutability: "nonpayable",
  },
  {
    name: "setBudget", type: "function",
    inputs: [{ name: "jobId", type: "bytes32" }, { name: "amount", type: "uint256" }],
    outputs: [], stateMutability: "nonpayable",
  },
] as const;

// ── 1. Simulate createJob — get jobId return value + catch revert errors ──────
console.log("Simulating createJob...");
const { result: jobId } = await publicClient.simulateContract({
  account,
  address: ACP_CORE,
  abi: ACP_CORE_ABI,
  functionName: "createJob",
  args: [clientId, budget, deadline, strategyType, programHash, rubricHash],
});
console.log("Simulation OK — jobId will be:", jobId);

// ── 2. Submit createJob tx ────────────────────────────────────────────────────
const createHash = await walletClient.writeContract({
  address: ACP_CORE,
  abi: ACP_CORE_ABI,
  functionName: "createJob",
  args: [clientId, budget, deadline, strategyType, programHash, rubricHash],
});
console.log("createJob tx submitted:", createHash);
const createReceipt = await publicClient.waitForTransactionReceipt({ hash: createHash });
if (createReceipt.status !== "success") throw new Error(`createJob reverted: ${createHash}`);
console.log("createJob confirmed. Job ID:", jobId);

// ── 3. Approve USDC spending ──────────────────────────────────────────────────
const approveHash = await walletClient.writeContract({
  address: MOCK_USDC,
  abi: ERC20_ABI,
  functionName: "approve",
  args: [ACP_CORE, budget],
});
console.log("approve tx submitted:", approveHash);
await publicClient.waitForTransactionReceipt({ hash: approveHash });
console.log("USDC approved");

// ── 4. setBudget — transfer USDC into escrow (job → FUNDED) ──────────────────
const fundHash = await walletClient.writeContract({
  address: ACP_CORE,
  abi: ACP_CORE_ABI,
  functionName: "setBudget",
  args: [jobId, budget],
});
console.log("setBudget tx submitted:", fundHash);
await publicClient.waitForTransactionReceipt({ hash: fundHash });
console.log("Job funded. Status: FUNDED");
console.log("\nDone! Job ID:", jobId);
```

**To run** (from monorepo root):
```bash
# Save the script as create-job.ts in the repo root, then:
export WALLET_KEY=0x<your_private_key>
pnpm exec tsx create-job.ts
```

**Success criteria:** All 3 transactions confirmed. Job ID and "FUNDED" logged.

### 4. (CEX_CAPITAL only) Deploy Strategy Vault on-chain

After funding, deploy the vault that registers risk parameters on-chain. The `VaultDeployed` event triggers the Indexer to create `cexConfig`.

> Same critical pattern: use `simulateContract` to get the vault address return value before broadcasting.

```typescript
import {
  createWalletClient,
  createPublicClient,
  http,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { bscTestnet } from "viem/chains";

// ── Config — fill these in ────────────────────────────────────────────────────
const VAULT_FACTORY  = "<StrategyVaultFactory>" as `0x${string}`;  // from Step 1
const MOCK_USDC_ADDR = "<TermixUSDC>" as `0x${string}`;            // from Step 1
const RPC_URL        = "<chain.rpcUrl>";                            // from Step 1
const JOB_ID         = "<jobId>" as `0x${string}`;                 // from Step 3

const STOP_LOSS_BPS     = BigInt(<stopLossBps>);     // e.g. 1000n = 10% — no hard contract limit, but 100–5000 bps (1–50%) is a sensible range
const TARGET_RETURN_BPS = BigInt(<targetReturnBps>); // e.g. 2000n = 20% — same range guidance
const PERF_FEE_BPS      = 1000n;                     // 10% performance fee — do not change
const DEADLINE          = BigInt(Math.floor(Date.now() / 1000) + <deadlineHours> * 3600);
// ─────────────────────────────────────────────────────────────────────────────

const account = privateKeyToAccount(process.env.WALLET_KEY as `0x${string}`);
const transport = http(RPC_URL);

const walletClient = createWalletClient({ account, chain: bscTestnet, transport });
const publicClient = createPublicClient({ chain: bscTestnet, transport });

const VAULT_FACTORY_ABI = [{
  name: "deployVault", type: "function",
  inputs: [
    { name: "jobId",             type: "bytes32" },
    { name: "settlementToken",   type: "address" },
    { name: "capital",           type: "uint256" },
    { name: "stopLossBps",       type: "uint256" },
    { name: "targetReturnBps",   type: "uint256" },
    { name: "deadline",          type: "uint256" },
    { name: "performanceFeeBps", type: "uint256" },
    { name: "valueOracle",       type: "address" },
  ],
  outputs: [
    { name: "vault", type: "address" },
    { name: "guard", type: "address" },
  ],
  stateMutability: "nonpayable",
}] as const;

const deployArgs = [
  JOB_ID,
  MOCK_USDC_ADDR,
  0n,                                                              // capital = 0 (funds stay on exchange)
  STOP_LOSS_BPS,
  TARGET_RETURN_BPS,
  DEADLINE,
  PERF_FEE_BPS,
  "0x0000000000000000000000000000000000000000" as `0x${string}`, // no oracle
] as const;

// ── 1. Simulate to get vault address + catch errors ───────────────────────────
const { result } = await publicClient.simulateContract({
  account,
  address: VAULT_FACTORY,
  abi: VAULT_FACTORY_ABI,
  functionName: "deployVault",
  args: deployArgs,
});
const [vaultAddr, guardAddr] = result;
console.log("Simulation OK — vault will be:", vaultAddr);

// ── 2. Deploy vault ───────────────────────────────────────────────────────────
const deployHash = await walletClient.writeContract({
  address: VAULT_FACTORY,
  abi: VAULT_FACTORY_ABI,
  functionName: "deployVault",
  args: deployArgs,
});
console.log("deployVault tx submitted:", deployHash);
const deployReceipt = await publicClient.waitForTransactionReceipt({ hash: deployHash });
if (deployReceipt.status !== "success") throw new Error(`deployVault reverted: ${deployHash}`);
console.log("Vault deployed:", vaultAddr);
console.log("Guard deployed:", guardAddr);
```

**To run** (from monorepo root):
```bash
export WALLET_KEY=0x<your_private_key>
pnpm exec tsx deploy-vault.ts
```

**Success criteria:** Transaction confirmed. Vault address logged. Indexer picks up `VaultDeployed` event and populates `cexConfig`.

### 5. (CEX_CAPITAL only) Initialize TEE task

After the vault is deployed, register the job with the TEE gateway.

**5a. Generate wallet signature** — save as `sign-tee.ts` in repo root:

> **Critical:** The action string is `create-tee-job` (NOT `tee-jobs`). Using the wrong prefix will cause a 403.

```typescript
import { privateKeyToAccount } from "viem/accounts";

const account   = privateKeyToAccount(process.env.WALLET_KEY as `0x${string}`);
const jobId     = "<jobId>";
const timestamp = Date.now();
const message   = `AACP:create-tee-job:${jobId}:${timestamp}`;

const signature = await account.signMessage({ message });

console.log("X-Wallet-Signature:", signature);
console.log("X-Wallet-Address:  ", account.address);
console.log("X-Wallet-Timestamp:", String(timestamp));
```

```bash
export WALLET_KEY=0x<your_private_key>
pnpm exec tsx sign-tee.ts
```

> The timestamp is valid for **5 minutes only**. Use the output values immediately.

**5b. Register TEE job** — replace `<SIG>`, `<ADDR>`, `<TS>` from the output above:

> **deadline** must be in **milliseconds** (Unix timestamp × 1000), not seconds.  
> `client_address` and `provider_address` are both the Client's wallet address at this stage.

```bash
curl -s -X POST "https://aacp-backend.termix.live/api/v1/tee/jobs" \
  -H "Content-Type: application/json" \
  -H "X-Wallet-Signature: <SIG>" \
  -H "X-Wallet-Address: <ADDR>" \
  -H "X-Wallet-Timestamp: <TS>" \
  -d '{
    "job_id": "<JOB_ID>",
    "client_address": "<ADDR>",
    "provider_address": "<ADDR>",
    "encrypted_api_key": "<ENCRYPTED_KEY>",
    "params": {
      "market": "FUTURES",
      "stop_loss_bps": <STOP_LOSS_BPS>,
      "target_return_bps": <TARGET_RETURN_BPS>,
      "max_daily_trades": <MAX_DAILY_TRADES>,
      "allowed_symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
      "deadline": <DEADLINE_UNIX_MS>,
      "snapshot_interval_ms": 30000,
      "futures": {
        "margin_type": "ISOLATED",
        "max_position_notional_usdt": 10000
      }
    }
  }' | jq .
```

Fields:
| Field | Value |
|---|---|
| `job_id` | bytes32 hex from Step 3 |
| `client_address` | your wallet address (same as `<ADDR>`) |
| `provider_address` | your wallet address (same as `<ADDR>`) |
| `encrypted_api_key` | ECIES-encrypted JSON `{"key":"...","secret":"..."}` using TEE pubkey — **hex string WITHOUT `0x` prefix** (e.g. `"04ab12..."`) |
| `params.market` | always `"FUTURES"` |
| `params.stop_loss_bps` | e.g. `1000` = 10%; input as integer bps (not percentage) |
| `params.target_return_bps` | e.g. `2000` = 20%; input as integer bps (not percentage) |
| `params.max_daily_trades` | e.g. `50` |
| `params.allowed_symbols` | trading pairs to allow |
| `params.deadline` | **milliseconds** — `<DEADLINE_UNIX> * 1000` |
| `params.snapshot_interval_ms` | balance snapshot frequency; `30000` = 30 s |
| `params.futures.margin_type` | `"ISOLATED"` |
| `params.futures.max_position_notional_usdt` | max position size in USDT |

> **How to produce `encrypted_api_key`** (Node.js):
> ```typescript
> import { encrypt } from "eciesjs";
> const plaintext = JSON.stringify({ key: "<API_KEY>", secret: "<API_SECRET>" });
> const encryptedBytes = encrypt(teePubkey, Buffer.from(plaintext));
> const encrypted_api_key = Buffer.from(encryptedBytes).toString("hex"); // no 0x prefix
> ```
> `teePubkey` is the `data.tee_pubkey` string from `GET /api/v1/tee/attestation`.

**Success criteria:** TEE responds `200`. Job is ready for Provider orders.

> **X-Wallet-Address format:** Pass the address exactly as returned by viem (`account.address`) — that is EIP-55 checksummed (mixed-case). Do not lowercase it manually.
>
> **Step 5 ↔ Step 6 dependency:** Steps 5 and 6 are **independent**. Metadata (Step 6) can be saved even if TEE init fails — the job is already on-chain and funded. TEE init failure does NOT block metadata saving.

### 6. Save job metadata (title & description)

After the on-chain steps, save the human-readable title and description off-chain. This is non-fatal — the job is already on-chain, but skipping this means it shows as untitled in the UI.

**6a. Generate signature** — save as `sign-metadata.ts` in repo root:

```typescript
import { privateKeyToAccount } from "viem/accounts";

const account   = privateKeyToAccount(process.env.WALLET_KEY as `0x${string}`);
const jobId     = "<JOB_ID>";
const timestamp = Date.now();
const message   = `AACP:set-job-metadata:${jobId}:${timestamp}`;

const signature = await account.signMessage({ message });

console.log("X-Wallet-Signature:", signature);
console.log("X-Wallet-Address:  ", account.address);
console.log("X-Wallet-Timestamp:", String(timestamp));
```

```bash
export WALLET_KEY=0x<your_private_key>
pnpm exec tsx sign-metadata.ts
```

**6b. PATCH metadata**:

```bash
curl -s -X PATCH "https://aacp-backend.termix.live/api/v1/jobs/<JOB_ID>/metadata" \
  -H "Content-Type: application/json" \
  -H "X-Wallet-Signature: <SIG>" \
  -H "X-Wallet-Address: <ADDR>" \
  -H "X-Wallet-Timestamp: <TS>" \
  -d '{"title": "<JOB_TITLE>", "description": "<JOB_DESCRIPTION>"}' \
  | jq .
```

**Success criteria:** Response has `"success": true`. Title and description are now visible in the UI.

### 7. Confirm job is live

```bash
curl -s "https://aacp-backend.termix.live/api/v1/jobs/<JOB_ID>" \
  | jq '{jobId: .data.jobId, status: .data.status, budget: .data.budget, strategyType: .data.strategyType, title: .data.title}'
```

Expected: `"status": "FUNDED"`. Run `/client-view-job <JOB_ID>` for full details.

---

## Appendix: CEX_CAPITAL one-shot script

For CEX_CAPITAL, all 3 on-chain steps (createJob + approve + setBudget + deployVault) can be combined into one script. Save as `create-cex-job.ts` in repo root:

```typescript
import {
  createWalletClient,
  createPublicClient,
  http,
  parseUnits,
  encodeAbiParameters,
  parseAbiParameters,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { bscTestnet } from "viem/chains";

// ── Config — fill these in ────────────────────────────────────────────────────
const ACP_CORE       = "<AACPCore>"            as `0x${string}`;  // key: "AACPCore"
const MOCK_USDC      = "<TermixUSDC>"          as `0x${string}`;
const VAULT_FACTORY  = "<StrategyVaultFactory>" as `0x${string}`;
const RPC_URL        = "<chain.rpcUrl>";

const clientId          = BigInt("<clientId>");
const budget            = parseUnits("<budget>", 6);
const deadlineHours     = <deadlineHours>;
const deadline          = BigInt(Math.floor(Date.now() / 1000) + deadlineHours * 3600);
const STOP_LOSS_BPS     = BigInt(<stopLossBps>);     // integer bps: 1000 = 10%
const TARGET_RETURN_BPS = BigInt(<targetReturnBps>); // integer bps: 2000 = 20%
const PERF_FEE_BPS      = 1000n;                     // 10% — do not change

// CEX_CAPITAL: programHash = fixed zkVM image ID; rubricHash = abi.encode(budget as uint256)
const CEX_CAPITAL_PROGRAM_HASH = "0x5465dd515290164f3e912ed790bdec95879d045175e7cd19b3d3486712ffd901" as `0x${string}`;
const cexRubricHash = encodeAbiParameters(parseAbiParameters("uint256"), [budget]);
// ─────────────────────────────────────────────────────────────────────────────

const account = privateKeyToAccount(process.env.WALLET_KEY as `0x${string}`);
const transport = http(RPC_URL);
const walletClient = createWalletClient({ account, chain: bscTestnet, transport });
const publicClient = createPublicClient({ chain: bscTestnet, transport });

const ERC20_ABI = [{
  name: "approve", type: "function",
  inputs: [{ name: "spender", type: "address" }, { name: "amount", type: "uint256" }],
  outputs: [{ type: "bool" }], stateMutability: "nonpayable",
}] as const;

const ACP_CORE_ABI = [
  {
    name: "createJob", type: "function",
    inputs: [
      { name: "clientId",     type: "uint256" },
      { name: "budget",       type: "uint256" },
      { name: "deadline",     type: "uint256" },
      { name: "strategyType", type: "uint8"   },
      { name: "programHash",  type: "bytes32" },
      { name: "rubricHash",   type: "bytes32" },
    ],
    outputs: [{ name: "jobId", type: "bytes32" }],
    stateMutability: "nonpayable",
  },
  {
    name: "setBudget", type: "function",
    inputs: [{ name: "jobId", type: "bytes32" }, { name: "amount", type: "uint256" }],
    outputs: [], stateMutability: "nonpayable",
  },
] as const;

const VAULT_FACTORY_ABI = [{
  name: "deployVault", type: "function",
  inputs: [
    { name: "jobId",             type: "bytes32" },
    { name: "settlementToken",   type: "address" },
    { name: "capital",           type: "uint256" },
    { name: "stopLossBps",       type: "uint256" },
    { name: "targetReturnBps",   type: "uint256" },
    { name: "deadline",          type: "uint256" },
    { name: "performanceFeeBps", type: "uint256" },
    { name: "valueOracle",       type: "address" },
  ],
  outputs: [
    { name: "vault", type: "address" },
    { name: "guard", type: "address" },
  ],
  stateMutability: "nonpayable",
}] as const;

// ── Step 1: createJob ─────────────────────────────────────────────────────────
console.log("[1/4] Simulating createJob...");
const { result: jobId } = await publicClient.simulateContract({
  account, address: ACP_CORE, abi: ACP_CORE_ABI,
  functionName: "createJob",
  args: [clientId, budget, deadline, 3, CEX_CAPITAL_PROGRAM_HASH, cexRubricHash], // 3 = CEX_CAPITAL
});
console.log("      jobId will be:", jobId);

const h1 = await walletClient.writeContract({
  address: ACP_CORE, abi: ACP_CORE_ABI,
  functionName: "createJob",
  args: [clientId, budget, deadline, 3, CEX_CAPITAL_PROGRAM_HASH, cexRubricHash], // MUST match simulation
});
const r1 = await publicClient.waitForTransactionReceipt({ hash: h1 });
if (r1.status !== "success") throw new Error(`createJob reverted: ${h1}`);
console.log("      confirmed:", h1);

// ── Step 2: approve USDC ──────────────────────────────────────────────────────
console.log("[2/4] Approving USDC...");
const h2 = await walletClient.writeContract({
  address: MOCK_USDC, abi: ERC20_ABI,
  functionName: "approve", args: [ACP_CORE, budget],
});
await publicClient.waitForTransactionReceipt({ hash: h2 });
console.log("      approved:", h2);

// ── Step 3: setBudget ─────────────────────────────────────────────────────────
console.log("[3/4] Funding job (setBudget)...");
const h3 = await walletClient.writeContract({
  address: ACP_CORE, abi: ACP_CORE_ABI,
  functionName: "setBudget", args: [jobId, budget],
});
await publicClient.waitForTransactionReceipt({ hash: h3 });
console.log("      funded:", h3);

// ── Step 4: deployVault ───────────────────────────────────────────────────────
console.log("[4/4] Deploying strategy vault...");
const vaultArgs = [
  jobId, MOCK_USDC, 0n,
  STOP_LOSS_BPS, TARGET_RETURN_BPS,
  deadline, PERF_FEE_BPS,
  "0x0000000000000000000000000000000000000000" as `0x${string}`,
] as const;

const { result: vaultResult } = await publicClient.simulateContract({
  account, address: VAULT_FACTORY, abi: VAULT_FACTORY_ABI,
  functionName: "deployVault", args: vaultArgs,
});
const [vaultAddr] = vaultResult;

const h4 = await walletClient.writeContract({
  address: VAULT_FACTORY, abi: VAULT_FACTORY_ABI,
  functionName: "deployVault", args: vaultArgs,
});
await publicClient.waitForTransactionReceipt({ hash: h4 });
console.log("      vault deployed:", vaultAddr);

console.log("\n=== Done ===");
console.log("Job ID:        ", jobId);
console.log("Vault address: ", vaultAddr);
console.log("\nNext: register with TEE (Step 5 in docs/client-create-job.md)");
```

```bash
export WALLET_KEY=0x<your_private_key>
pnpm exec tsx create-cex-job.ts
```
