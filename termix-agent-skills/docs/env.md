# AACP Skills — Environment Reference

Global constants referenced by all skills in this package.

---

## API

| Name | Value |
|---|---|
| Base URL | `https://aacp-backend.termix.live` |
| API Key (Bearer) | `HrnsTtFiEchdgq7J76Pmxv9rE8jKy0Nen` |

The Bearer token is used only for the agent metadata staging endpoint (`POST /api/v1/agents/metadata`).
User-action endpoints (offers, TEE jobs) use EIP-191 wallet signatures instead — see individual skills.

---

## Runtime

Use Node.js 18+ and pnpm. The helper scripts in `scripts/` are `.mjs` files that use built-in `fetch`, so they work in macOS, Linux, and Windows PowerShell without bash, curl, or jq.

```bash
node scripts/aacp-config.mjs
node scripts/aacp-get.mjs "/api/v1/jobs?status=FUNDED"
```

For wallet scripts that read `WALLET_KEY`:

```bash
# macOS / Linux
export WALLET_KEY=0x<your_private_key>

# Windows PowerShell
$env:WALLET_KEY = "0x<your_private_key>"
```

Optional API override:

```bash
# macOS / Linux
export AACP_BASE_URL=https://aacp-backend.termix.live

# Windows PowerShell
$env:AACP_BASE_URL = "https://aacp-backend.termix.live"
```

---

## Chain

| Name | Value |
|---|---|
| Network | BSC Testnet |
| Chain ID | `97` |
| RPC URL | `https://data-seed-prebsc-1-s1.binance.org:8545` |
| Block Explorer | `https://testnet.bscscan.com` |

---

## Contract Addresses

**Always fetch live** from `GET /api/v1/config` — never hardcode. Key contract names returned by the API:

| Key in `config.contracts` | Purpose |
|---|---|
| `AgentNFT` | ERC-721 Agent identity NFT; `mint(to, tokenURI)` assigns token ID on-chain |
| `AACPCore` / `ACPCore` | Main job contract — createJob, setBudget, setProvider, submit, evaluate |
| `AACPStaking` / `TermiXStaking` | Provider/evaluator stake — deposit, registerEvaluatorStrategy |
| `TermixUSDC` / `MockUSDC` | Test USDC token (6 decimals); approve before staking or funding jobs |
| `AACPReputation` | On-chain reputation scoring (read-only) |
| `TermiXDispute` / `AACPDispute` | Dispute management — open, commit, reveal, settle |
| `StrategyVaultFactory` | CEX_CAPITAL vault deployment (deployVault) |
| `Groth16VerifierRouter` | zkVM proof verification for PROGRAM strategy |

Fetch example:
```bash
node scripts/aacp-config.mjs
```

---

## Amount Conventions

| Token | Decimals | Raw → Display |
|---|---|---|
| USDC | 6 | `rawAmount / 1e6` → human USDC |

All API responses return USDC amounts as **display values** (already divided by 1e6).  
On-chain calls use raw amounts — use `parseUnits(amount, 6)` from viem.

---

## Timestamp Conventions

All API timestamps are **Unix epoch seconds** returned as BigInt strings.  
Convert to JS Date: `new Date(Number(ts) * 1000)`

---

## Strategy Types

| Enum value | Name | Description |
|---|---|---|
| `0` | `PROGRAM` | zkVM deterministic (Groth16 proof required) |
| `1` | `RUBRIC` | LLM / score-based evaluation |
| `2` | `HYBRID` | Program + Rubric combined |
| `3` | `CEX_CAPITAL` | CEX trading inside TEE enclave |

---

## EIP-191 Wallet Auth (offer endpoints)

Some endpoints require a signed message instead of the API key:

```
Message format: AACP:<resource>:<id>:<timestamp_ms>
Examples:
  AACP:make-offer:<jobId>:<ts>       → offer submit/withdraw
  AACP:create-tee-job:<jobId>:<ts>   → TEE job registration
```

Headers:
- `X-Wallet-Signature: <sig>`
- `X-Wallet-Address: <address>`
- `X-Wallet-Timestamp: <timestamp_ms>`

Timestamp must be within **5 minutes** of server time. Sign with `walletClient.signMessage()`.
