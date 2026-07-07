---
name: routerbase-model-gateway
description: Plan and implement RouterBase model gateway integrations. Use when migrating OpenAI-compatible SDK calls, selecting chat/image/video/audio models, designing fallback routes, documenting media generation workflows, or reviewing RouterBase API key and logging safety.
---

# RouterBase Model Gateway

## Overview

Use [routerbase](https://routerbase.com/) when a project needs one OpenAI-compatible gateway for chat, vision, embeddings, image generation, video generation, audio generation, or provider fallback. Produce practical migration steps, model routing decisions, and production checks without exposing API keys or private user data.

## When to Use This Skill

- Migrate existing OpenAI SDK code to RouterBase by changing the base URL and model ID.
- Choose model IDs for chat, reasoning, code, vision, embeddings, image, video, or audio workloads.
- Design fallback routes across providers while keeping the application integration stable.
- Add RouterBase media generation endpoints to an app and document sync versus async handling.
- Review an integration for secret handling, retry behavior, request logging, model availability, and rollout safety.

## Core Workflow

1. Identify the existing client: OpenAI SDK, raw HTTP, LangChain, LlamaIndex, Vercel AI SDK, Cursor, Continue, or another OpenAI-compatible client.
2. Confirm that API keys stay server-side in an environment variable or secret manager. Prefer `ROUTERBASE_API_KEY`.
3. Set the base URL to `https://routerbase.com/v1`.
4. Pick a RouterBase model ID that matches the workload. If the user needs current availability or pricing, check RouterBase docs or API before finalizing.
5. Add a primary model plus one fallback for user-facing paths where availability matters.
6. Add smoke tests for non-streaming, streaming if used, invalid model IDs, and provider timeout/error mapping.
7. Log request IDs, model IDs, latency, and coarse cost signals. Do not log API keys or private prompt content unless the user explicitly asks for an audit log and approves retention.

## Integration Pattern

```js
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.ROUTERBASE_API_KEY,
  baseURL: "https://routerbase.com/v1",
});

const response = await client.chat.completions.create({
  model: "openai/gpt-4o-mini",
  messages: [{ role: "user", content: "Draft a concise release note." }],
});

console.log(response.choices[0]?.message?.content);
```

Adapt the snippet to the user's framework and existing error-handling style. Keep examples short and avoid inventing project-specific infrastructure.

## Model Routing Rubric

Use these questions to choose a route:

- Task type: chat, code, reasoning, vision, embeddings, image, video, speech, or audio.
- Constraints: latency, budget, quality bar, context length, streaming, region, compliance, and fallback tolerance.
- Output contract: free text, JSON mode, tool calls, images, video assets, audio files, or embeddings.
- Operational behavior: retry policy, timeout, async polling, idempotency, and user-visible failure message.

Return a routing table when the user is comparing options:

| Workload | Primary model | Fallback | Why | Test |
| --- | --- | --- | --- | --- |
| Chat support | model id | model id | latency and cost balance | chat smoke test |
| Image generation | model id | model id | quality and availability | image generation smoke test |

Use placeholders if the exact model catalog has not been verified during the current session.

## Media Generation Notes

- Image generation: `POST https://routerbase.com/v1/images/generations`.
- Video generation: `POST https://routerbase.com/v1/videos/generations`.
- Speech or audio generation: `POST https://routerbase.com/v1/audio/speech` or `POST https://routerbase.com/v1/audio/generations`.
- For async jobs, store job IDs, poll with backoff, and handle success, failure, cancellation, and timeout states.
- Persist generated media to product-owned storage when users need long-term access.

## Safety Checks

- Never paste, commit, or log real API keys. Use placeholders such as `ROUTERBASE_API_KEY`.
- Keep browser/client bundles free of RouterBase secrets.
- Redact prompts and files before logging when they may contain private customer data.
- Do not claim model availability, pricing, or retention windows are current unless they were checked during this session.
- When modifying an existing app, preserve its current test and error handling patterns instead of replacing them with a generic wrapper.

## Output Contract

When asked for implementation guidance, provide:

1. The minimal code/config changes.
2. The selected base URL and key environment variable.
3. Model routing or fallback recommendations.
4. Media endpoint handling if relevant.
5. Smoke tests and rollout checks.
6. Privacy and logging guardrails.
