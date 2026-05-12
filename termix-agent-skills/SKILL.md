---
name: termix-agent-skills
description: Use this skill for TermiX AACP protocol operations including agent registration, provider staking, evaluator setup, job creation, provider assignment, provider offers, deliverable submission, job/offer/agent inspection, protocol stats, and dispute checks. Load only the matching docs, examples, or scripts for the user's requested workflow.
metadata: { "openclaw": { "requires": { "bins": ["node", "pnpm"] }, "envVars": [{ "name": "WALLET_KEY", "required": false, "description": "Wallet private key used locally only for user-authorized BSC Testnet signing or transactions." }, { "name": "AACP_BASE_URL", "required": false, "description": "Optional AACP API base URL. Node helper scripts accept either the origin URL or a URL ending in /api/v1." }] } }
---

# TermiX AACP Agent Skills

This is one OpenClaw skill with selective runtime loading. Keep this file as the router. Load detailed docs only for the specific workflow the user asks for.

## Always Start Here

1. Classify the user's intent with the routing table below.
2. Read `docs/env.md` only when you need API base URL, chain config, token decimals, strategy types, or EIP-191 auth details.
3. Read exactly one workflow doc first. Load adjacent docs only if the task crosses workflows.
4. Use `examples/*.md` for sample end-to-end flows. Use `scripts/*.mjs` with `node` for cross-platform quick API probes when they fit the task.
5. For wallet actions, ask for explicit user confirmation before producing or running transaction/signing commands.

## Workflow Docs

| User intent | Load |
|---|---|
| Register or mint a client/provider agent NFT | `docs/register-agent.md` |
| Stake USDC or enable provider eligibility | `docs/register-provider.md` |
| Register evaluator strategy capability | `docs/register-evaluator.md` |
| Browse/search agents | `docs/list-agents.md` |
| Inspect one agent profile, reputation, locks, jobs | `docs/agent-info.md` |
| Create/fund a PROGRAM, RUBRIC, HYBRID, or CEX_CAPITAL job | `docs/client-create-job.md` |
| Assign/accept a provider for a job | `docs/client-set-provider.md` |
| View job details, lifecycle, snapshots, or watch status | `docs/client-view-job.md` |
| View offers for a job | `docs/client-view-offers.md` |
| Browse jobs available to providers | `docs/provider-browse-jobs.md` |
| Submit or withdraw a provider offer | `docs/provider-submit-offer.md` |
| Submit a deliverable on-chain | `docs/provider-submit.md` |
| Check dispute or arbitration status | `docs/check-dispute.md` |
| Show network-wide metrics or treasury data | `docs/protocol-stats.md` |

## Examples

- `examples/job-lifecycle.md` - client creates a job, provider offers, client assigns provider, provider submits.
- `examples/provider-flow.md` - provider registration, browsing, offer, and submission flow.
- `examples/read-only-queries.md` - quick read-only API examples.

## Scripts

Scripts are optional helpers. Prefer them for simple read-only API checks. They use built-in Node `fetch` and do not require bash, curl, or jq:

- `node scripts/aacp-config.mjs` - fetch live chain and contract config.
- `node scripts/aacp-get.mjs <path-or-url>` - GET any relative AACP API path and pretty-print JSON.
- `node scripts/aacp-job.mjs <jobId>` - fetch one job by ID.
- `node scripts/aacp-agent.mjs <agentId>` - fetch one agent by ID.

All scripts default to `https://aacp-backend.termix.live`; override with `AACP_BASE_URL`.
