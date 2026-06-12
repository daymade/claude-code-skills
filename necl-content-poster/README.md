# necl-content-poster

> One draft → three platform-tuned posts: Telegram (RU), LinkedIn (EN), Threads (EN).

Production-tested skill. Built on hook formulas that actually drive engagement on each platform, with strict anti-AI-marker rules that LinkedIn/Threads readers identify in seconds.

## What it does

Give it a draft, idea, news item, or product announcement. Get back:

| Platform | Language | Voice | Length | Goal |
|---|---|---|---|---|
| **Telegram** | Russian | Warm, founder, personal | 80–220 words | Conversational reach + soft CTA |
| **LinkedIn** | English | Calm, technical-founder | 1200–1800 chars | Dwell-time + thought leadership |
| **Threads** | English | Confident, detached | 15–50 words | One sharp inference → screenshot / argue / nod bait |

## Why this skill matters

Most "write a social post" prompts produce AI-default mush — the kind LinkedIn algorithm now buries and Threads readers ignore. This skill encodes:

- **8 hook archetypes** (shock-stat, counter-narrative, confession, provocation, dated story, question, list-teaser, comparison) instead of generic "make it engaging".
- **6-block LinkedIn structure** (Hook → Context → Twist → Core → Close+Q → optional PS) with the Twist as the explicit keystone.
- **Banned-phrases list** (no "in an era where", no "let's dive in", no em-dash sandwich, no "leverage" / "unlock") — kills the AI-text smell.
- **Threads = ONE inference** rule that prevents the model from padding three connected thoughts into a diluted post.
- **Character counts, not word counts** for LinkedIn — matches what the algorithm actually measures.

## Install

```bash
# project-level (recommended — versioned with the project)
mkdir -p .claude/skills
cp -r path/to/necl-content-poster .claude/skills/

# OR personal (available across all your projects)
mkdir -p ~/.claude/skills
cp -r path/to/necl-content-poster ~/.claude/skills/
```

Then in Claude Code:
```
What Skills are available?
```
You should see `necl-content-poster` in the list.

## Plug in your context

Before first use, create a `company-context.md` in your project root (or `.claude/`) describing:
- Who you are, what you build/sell
- Audience and personas
- Tone of voice rules
- CTAs (Calendly, DM, website)

The skill reads this and tunes all three posts to your brand. Without it, posts will be generic — the skill will ask you for context if it's missing.

## Use

Just describe what you want — Claude picks up the skill automatically:

```
Write a post about our new RAG system that cut due-diligence from 2 months to 15 minutes.
```

You get TG/LinkedIn/Threads versions in one shot, each tuned to its platform.

## Examples

See [SKILL.md](./SKILL.md) — bottom section has a full input → 3 outputs example using a real client case.

## Built by NeCL

[neclco.com](https://neclco.com) — production AI engineering. We build content engines, RAG systems, voice agents, and full Telegram bot platforms.

**Need a content engine that posts itself across all your channels?** [Book a call](https://calendly.com/neclcompany/30min?utm_source=marketplace&utm_medium=skill&utm_campaign=content-poster).

Pair this skill with [necl-hn-mcp](https://github.com/adjacentai/necl-hn-mcp) for full HN → drafts pipeline.

## License

MIT — see repo [LICENSE](../LICENSE).
