---
name: necl-content-poster
description: "Turn one draft into three platform-tuned posts: Telegram (RU), LinkedIn (EN), Threads (EN). 8 hook formulas, anti-AI-marker rules, per-platform structures. Use when the user wants posts across channels — 'write a post', 'cross-post', 'превратить в пост'."
author: NeCL
homepage: https://neclco.com
license: MIT
version: 0.1.0
tags:
  - content
  - social-media
  - copywriting
  - telegram
  - linkedin
  - threads
  - cross-platform
  - bilingual
---

# NeCL Content Poster

> Take one rough draft, idea, news item, or product update — get back three polished posts, each tuned to its platform's audience and algorithm.

## When to Use This Skill

User asks for any of:
- "Write a post about X"
- "Turn this into posts for Telegram / LinkedIn / Threads"
- "Cross-post this"
- "Make this into social content"
- "Напиши пост / превратить в пост"
- Provides a draft, idea, news item, announcement, or thought and wants social-media output.

## Before you start — load company context

If a `company-context.md` (or similar) file exists in the user's project root or `.claude/` folder, **read it first**. It should contain:

- Company name, role, what you build/sell
- Mission and key products
- Tone of voice rules
- Target audience and key personas
- Any banned phrases or brand guidelines

If no such file exists, **ask the user for**:
1. Company / personal brand name and 1-line description
2. Audience and what they care about
3. Tone preference (casual / professional / contrarian / etc.)
4. Whether to include CTAs and where they should point (Calendly, DM handle, website, etc.)

Without this context, posts will be generic. Don't skip it.

## Output format

For every input, generate three versions, in this order:

### 1. Telegram post (Russian) 🇷🇺

**Audience:** founders, AI engineers, product people, the kind of crowd that reads operator-channels in Russian.

**Voice:** warm, personal, founder-shares-cool-stuff. Not marketing. Not lecture. Like telling a friend over coffee about something you found today.

**Structure (flexible, not rigid):**
- **Hook line:** emoji + concrete fact / number / observation. NOT a philosophical opener, NOT "let's talk about…".
- **2–5 short paragraphs** with rhythm. Bullet block with emoji markers (📌 ✅ ❌ → •) when listing concrete points.
- **Middle or near-end:** your take — "why it matters", "what we noticed", "how we do this at our place".
- **Closing:** soft CTA (question to comments) OR light pitch if it fits OR observation-only if reflection-post.

**Length:** 80–220 words.

**Style:**
- Russian. English terms (RAG, MCP, latency, agent) OK — audience is technical.
- Plain text. NO markdown (** _ #). No code blocks unless code is literally the subject.
- Emojis as semantic markers in line-starts: 3–7 per post, not decorative.
- First-person ("я", "мы") natural. Mentioning the company / "we at {{COMPANY}}" is encouraged when it fits — this is a brand channel.
- Light personal emotion OK ("finally live ❤️", "feels like sci-fi", "perfect", 🐺) — sparingly.

**Avoid:**
- Aggressive marketing tone, "Neil Patel" style hype.
- Dry recap of the news without a personal angle.
- Openers like "Let's discuss…", "Interesting article about…".
- Hashtags in the body.
- Jargon dumps and academic register.

### 2. LinkedIn post (English) 🇺🇸

**Audience:** CTOs, VPs of Engineering, fellow founders, AI buyers. Decision-makers reading on mobile.

**Voice:** technical founder writing for fellow leaders. Confident, calm, useful. NOT cynical, NOT ironic, NOT hype. Think: respected operator sharing a practical observation.

**STRICT BAN — no obvious AI markers.** LinkedIn readers identify GPT-text in 2 seconds and scroll past. Banned phrases and patterns:
- "In an era where…", "In today's fast-paced world", "Let's dive in"
- "It's not just X — it's Y" (em-dash sandwich)
- "navigating the landscape", "harness the power of"
- "unlock", "unleash", "leverage", "game-changer", "paradigm shift"
- "at the intersection of"

If a line could be a LinkedIn AI-generator default, REWRITE.

**Structure (every block matters):**
1. **HOOK (1–2 lines)** — visible before the "see more" cut. Pick ONE archetype:
   - *Shock-stat*: "After 4 years with ChatGPT, it still doesn't know who I am."
   - *Counter-narrative*: "Speed is no longer your competitive advantage."
   - *Confession*: "I used to do 10-hour days. The result? Full burnout."
   - *Provocation*: "Most 'AI productivity hacks' are just theater."
   - *Dated story*: "Last Tuesday, our agent stack burned $400 in 90 minutes."
   - *Question*: "What if cache hit rate is now a moat?"
   - *List teaser*: "5 things I stopped doing after we hit $50K MRR."
   - *Comparison*: "I tried 3 frameworks. Only one survived production."
2. **CONTEXT (2–3 short lines)** — what triggered the thought, who it concerns. Anchored in 1–2 specific facts/names/numbers.
3. **TWIST / INSIGHT (1–2 lines)** — the reframe that flips the obvious reading. **The twist is the keystone — never skip it.**
4. **USEFUL CORE** — short list, micro-framework, or 2–3 concrete lessons. Practical, not preachy.
5. **CLOSE + ONE specific question** — name a number, a role, a decision. Not "thoughts?" or "what do you think?".
6. **PS (optional)** — a small aside, counter-point, or softener.

**Length:** 1200–1800 characters (LinkedIn counts characters; sweet spot for dwell time).

**Style:**
- English.
- Short paragraphs (1–3 sentences). White space between blocks.
- Personal "we"/"I" framing as the founder.
- NO URLs or links in the post body. If a link is essential, write `(link in comments)`.
- Sparse emoji as paragraph anchors (▪ 🔹 → ⚡), 2–4 max, never decorative.
- 3–5 niche hashtags at the very end.

### 3. Threads post (English) 🇺🇸

**Audience:** AI builders, indie hackers, tech Twitter crowd that migrated here.

**Voice:** confident, calm, slightly detached. Builder who noticed something. No marketing, no outrage, no industry-mockery.

**Goal — maximize VIEWS.** On Threads, views follow replies and reshares. A post earns those when it is one of:
- **Nod-bait truth** — readers want to add "this."
- **Argue-bait claim** — readers want to push back in replies.
- **Screenshot-bait line** — so sharp readers save it to share elsewhere.

**Write ONE inference.** Not three connected beats. Not an essay. ONE thought, distilled. If you could split it into two posts, cut harder.

**Length:** 15–50 words MAX. Under 30 is usually sharper.

**Style:**
- English. 1–3 short lines. Line breaks for rhythm and screenshot framing.
- Plain prose. NO bullets, emojis, hashtags, markdown, CTAs, questions.
- NO "the article says", NO recap language.
- NO empty aphorism ("technology is a mirror"). If it reads like a fortune cookie, REWRITE.

## Examples

### Input
> Just shipped a RAG system for an investment fund. They were doing due-diligence reviews in 2 months per deal — now 15 minutes. 258 deals processed in the first quarter.

### Output

**Telegram (RU):**

📊 За первый квартал — 258 сделок прошло через нашу RAG-систему.

Раньше каждая сделка = 2 месяца ручного due-diligence в фонде. Аналитики, документы, ссылки, ссылки на ссылки. Теперь — 15 минут.

✅ Загружают пачку PDF → агент находит риски, инвест-тезис, цифры.
✅ Аналитик читает summary, лезет только в спорные места.
✅ Конфиденциально — модель локальная, ничего не уходит в облако.

Мы у себя так и тестим — сначала на собственных кейсах, потом продаём.

Если у вас тонна документов и одни и те же вопросы — пишите в комментарии, разберём.

**LinkedIn (EN):**

Last quarter, we shipped a RAG system that turned a 2-month due-diligence process into 15 minutes per deal.

258 deals went through it in Q1. Same analysts, same depth of review — just no manual document-trawling between insight and decision.

The lesson isn't "AI is fast." Every team knows that by now. The lesson is that the bottleneck in most knowledge work isn't thinking — it's the retrieval layer between the question and the source paragraph. Once retrieval is solved, the rest of the workflow compresses on its own.

For leaders evaluating where to deploy AI first:

▪ Look for processes where 80% of the time is spent finding context, not making decisions.
▪ Measure baseline in hours per output, not in dollars saved — dollars come later, hours are immediate.
▪ Run on-premise where data sensitivity demands it. Public APIs are a no-go for due-diligence-class workflows.

If you're sitting on a knowledge process that takes weeks per cycle, what's the retrieval layer underneath it actually doing?

#AI #RAG #LLMOps #AIEngineering #FintechAI

**Threads (EN):**

Replaced 2 months of analyst work with 15 minutes of retrieval.

The bottleneck in knowledge work was never thinking. It was finding the paragraph that has the answer.

## Final checklist before delivering

- [ ] Did I read the company context file (or ask if missing)?
- [ ] Are all three platforms anchored in the same core message?
- [ ] Telegram post has at least one personal-take line, not pure recap?
- [ ] LinkedIn has all six structural blocks (especially TWIST)?
- [ ] Threads is ONE inference, not three beats?
- [ ] No banned AI-marker phrases anywhere?
- [ ] No links in LinkedIn body (only "link in comments" if needed)?
- [ ] Hashtags only at the very end of LinkedIn, none elsewhere?

If any box fails, revise that block before delivering.

---

*Built by [NeCL](https://neclco.com/?utm_source=marketplace&utm_medium=skill&utm_campaign=content-poster) — production-grade AI engineering. Visit neclco.com if you need a content engine wired to a real publishing pipeline.*
