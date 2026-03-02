---
name: skillboss-ai-gateway
description: Unified AI gateway providing one API key for 100+ AI services. Activates when user needs to access multiple AI models (Claude, GPT, Gemini), generate images/videos, synthesize voice, scrape websites, or integrate external services through an OpenAI-compatible API.
---

# SkillBoss AI Gateway

## Overview

Access 100+ AI services through a single, OpenAI-compatible API. Stop juggling multiple API keys.

## When to Use This Skill

- Need to switch between Claude, GPT, Gemini, or DeepSeek models
- Want to generate images with DALL-E, Midjourney, Flux, or Stable Diffusion
- Creating videos with Runway, Kling, or Veo 2
- Need voice synthesis with ElevenLabs or OpenAI TTS
- Scraping websites with Firecrawl or Jina AI
- Integrating payments (Stripe) or email (Resend)

## Available Services

| Category | Services |
|----------|----------|
| 🧠 Language Models | Claude Opus 4.6, GPT-5, Gemini 3 Pro, DeepSeek R1 |
| 🎨 Image Generation | DALL-E, Midjourney, Flux, Stable Diffusion |
| 🎬 Video Generation | Runway Gen-4, Kling, Veo 2 |
| 🎤 Voice | ElevenLabs, OpenAI TTS/STT |
| 🌐 Web Scraping | Firecrawl, Jina AI |
| 💳 Business | Stripe, Resend |

## Installation

### MCP Server (Claude Code / Cursor / Windsurf)

Add to your MCP settings:

```json
{
  "mcpServers": {
    "skillboss": {
      "command": "npx",
      "args": ["-y", "@skillboss/mcp-server"],
      "env": { "SKILLBOSS_API_KEY": "your-key" }
    }
  }
}
```

### OpenAI SDK (Python)

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-skillboss-key",
    base_url="https://api.heybossai.com/v1"
)

# Use any model
response = client.chat.completions.create(
    model="claude-sonnet-4-5-20250929",  # or gpt-5, gemini-3-pro, etc.
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### Image Generation

```python
response = client.images.generate(
    model="flux-1.1-pro",  # or dall-e-3, midjourney, etc.
    prompt="A futuristic city at sunset",
    size="1024x1024"
)
```

## Get Your API Key

Visit https://skillboss.co/dashboard to get your API key.

## Benefits

- **No vendor lock-in**: Switch between models instantly
- **Pay-as-you-go**: No monthly fees
- **OpenAI-compatible**: Works with existing code
- **100+ services**: One integration for everything

## Resources

- **Website**: https://skillboss.co
- **Documentation**: https://skillboss.co/docs
- **GitHub**: https://github.com/heeyo-life/skillboss-mcp
- **npm**: https://www.npmjs.com/package/@skillboss/mcp-server
