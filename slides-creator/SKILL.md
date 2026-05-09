---
name: slides-creator
description: Narrative-first slide deck creation. Guides users through structured narrative design (ABCDEFG model), then delegates visual generation to baoyu-slide-deck. Triggers on "create slides", "make a presentation", "generate deck", "slide deck", "PPT", or when user needs to turn content into visual slides.
context: fork
agent: general-purpose
---

# Slides Creator

**Narrative-first slide deck creation.**

This skill does what machines can't do — narrative co-design with humans — and delegates everything else to the best tool for the job (`baoyu-slide-deck`).

## First Law: The User's Voice Is Primary

**This is the highest-priority rule. Nothing overrides it.**

> AI cannot write high-quality content for the user. It can only help the user express their own content better.
>
> **Step 1 is ALWAYS: collect the user's original words.** Their transcripts, their articles, their notes, their voice. AI-generated content without user source material is garbage — polished, plausible, unusable garbage.
>
> **Weight hierarchy**: User's own words > User-approved external material > AI synthesis > AI invention.
>
> The output must sound like the user, at their best. Something they could actually say, confidently, in their own voice.

**Corollary**: If the user has no existing content, your job is to help them articulate their thoughts through structured conversation — NOT to fabricate content for them.

**Corollary**: External materials (articles, references) must be presented to the user for selection and validation. AI does not decide what is relevant. The user does.

**See**: `references/content-creation-first-law.md` for full principle, application to all content types, and failure modes.

## Architecture

```
slides-creator (this skill)
├── Phase 0: Source Collection    ← Gather user's original words
├── Phase 1: Narrative Design     ← Human expertise + ABCDEFG discussion
├── Phase 2: Content Structuring  ← Convert narrative to machine-readable input
├── Phase 3: Delegate to baoyu-slide-deck
│   ├── --prompts-only  → outline + prompts
│   └── --images-only   → images + PPTX + PDF
└── Phase 6: Post-processing      ← Directory reorg + speaker notes extraction
```

**Rule**: If `baoyu-slide-deck` can do it, we call it. We only do what baoyu-slide-deck cannot: narrative discussion, ABCDEFG methodology, and user's preferred directory structure.

---

## Phase 0: Source Material Collection

**CRITICAL**: Do NOT proceed to Phase 1 until user source materials are collected.

**Goal**: Gather the user's own words and their approved external references.

### Step 0.1: Request User's Original Content

Ask the user for:
- **Transcripts** of their past talks, meetings, or discussions
- **Articles** they have written or approved
- **Notes** or drafts they have prepared
- **Previous decks** they have delivered
- **Voice memos** or any recorded thoughts

If none exist, proceed to Phase 1 with the understanding that the entire narrative must be extracted from the user's head through structured conversation.

### Step 0.2: Gather External References (Optional)

- Search for relevant external materials (articles, reports, references)
- **Present findings to the user for selection** — do not assume relevance
- Only include materials the user explicitly approves

### Step 0.3: Organize Source Materials

Save all source materials to `00-上游/`（根目录或 `source-materials/` 子目录均可）：
```
00-上游/
├── prompt-最初提示词.txt       # 用户原始 prompt（如有）
├── narrative-brief.md          # Phase 1 输出
├── content.md                  # Phase 2 输出（baoyu 输入）
├── style-instructions.md       # 视觉设计 SSOT
├── outline.md                  # 来自 baoyu-slide-deck
├── source-materials/           # （可选子目录）
│   ├── user-transcript-1.md
│   ├── user-article-2.md
│   ├── user-notes-3.md
│   └── external-ref-4.md (user-approved)
```

**Note**: 对于已有项目，源文件可直接放在 `00-上游/` 根目录；新建议项目时可用 `source-materials/` 子目录保持整洁。

**Self-check**: Do we have the user's own words? If not, are we prepared to extract everything through conversation? Do NOT invent content.

---

## Phase 1: Narrative Structure Discussion

**CRITICAL**: Do NOT generate any files in this phase. Only discuss.

**Goal**: Align on the narrative arc, emotional journey, and slide-level logic before any visual work begins.

**Principle**: "你不要直接去写，你应该跟我讨论"

**Input**: Phase 0 source materials. Every insight in this discussion must be grounded in the user's own words or their explicitly approved references.

### Discussion Framework (ABCDEFG Model)

| Step | Question | Purpose |
|------|----------|---------|
| A | **Attention** | How do we hook in the first 30 seconds? |
| B | **Benefit** | What's the promised takeaway? |
| C | **Credibility** | Why should the audience trust us? |
| D | **Difference** | What's the contrarian or novel angle? |
| E | **Evidence** | What proof, demo, or story backs this? |
| F | **Framework** | What mental model do we leave them with? |
| G | **Go** | What should they do Monday morning? |

### Required Inputs

Ask user if missing:
- **Topic**: What's the talk about? (1 sentence)
- **Audience**: Who's listening? (technical level, role, context)
- **Duration**: How long is the talk?
- **Key messages**: What must they remember? (3 max)
- **Tone**: Educational? Persuasive? Provocative? Inspirational?
- **Existing content**: Articles, transcripts, notes, previous decks?
- **Constraints**: Must-use content? Avoid topics? Brand guidelines?

### Discussion Checklist

1. **Opening strategy**: Shock? Story? Question? Demo?
2. **The arc**: Where's the tension? Where's the release?
3. **Transition logic**: How does each slide lead to the next?
4. **The "one thing"**: If they forget everything, what's the ONE thing?
5. **Call to action**: What do they do after the talk?

### Anti-patterns to Flag

- ❌ Too many slides for the time (crowded, rushed)
- ❌ Jumping into details without setting context
- ❌ No emotional arc (flat, forgettable)
- ❌ Ending without a clear takeaway
- ❌ Trying to teach too many things at once

### Validation

Summarize agreed narrative arc in 3-5 bullet points. Get explicit user confirmation before proceeding to Phase 2.

**Self-check**: Did we discuss? Or did we jump to generation? If the latter, go back.

---

## Phase 2: Content Structuring

**Goal**: Produce two SSOT files that baoyu-slide-deck can consume.

### 2.1 Create `narrative-brief.md`

Store in `00-上游/`:

```markdown
# Narrative Brief

**Topic**: [Topic name]
**Audience**: [description]
**Duration**: [N min]
**Language**: [zh/en/etc]
**Tone**: [educational/persuasive/provocative/inspirational]
**Key Messages**: (3 max)
1. ...
2. ...
3. ...

## ABCDEFG Arc

| Step | Answer |
|------|--------|
| A - Attention | ... |
| B - Benefit | ... |
| C - Credibility | ... |
| D - Difference | ... |
| E - Evidence | ... |
| F - Framework | ... |
| G - Go | ... |

## Slide Count Recommendation

| Duration | Recommended | Max |
|----------|-------------|-----|
| 10-15 min | 8-12 | 12 |
| 20-30 min | 12-18 | 20 |
| 30-45 min | 15-25 | 28 |
| 45-60 min | 20-30 | 35 |

**Recommended**: [N] slides for [duration] talk

## Content Sources

- [ ] Original user prompt saved
- [ ] Existing articles/notes/transcripts
- [ ] Previous decks

## Style Direction

[User's style preference or "to be decided in Phase 3"]
```

### 2.2 Create `content.md` (for baoyu-slide-deck)

Convert narrative brief into baoyu-slide-deck input format:

```markdown
# [Title]

## Overview

[2-3 paragraph summary of the talk content]

## Key Points

1. [Point 1]
2. [Point 2]
3. [Point 3]

## Structure

### Opening ([duration])
[Hook content]

### Section 1: [Name] ([duration])
[Content]

### Section 2: [Name] ([duration])
[Content]

### Closing ([duration])
[CTA content]

## Audience
[Same as narrative-brief]

## Notes
[Any constraints or special requirements]
```

### 2.3 Create `style-instructions.md` (Optional)

If user has strong style preferences, create this SSOT file in `00-上游/`:

```markdown
<STYLE_INSTRUCTIONS>
Design Aesthetic: [Description]

Background:
  Texture: [clean/grid/organic/etc]
  Base Color: [#HEX]

Typography:
  Headlines: [Style, size, color, weight]
  Body: [Style, size, color, weight]

Color Palette:
  Primary Text: [#HEX] - usage
  Body Text: [#HEX] - usage
  Background: [#HEX]
  Accent 1: [#HEX] - usage
  Accent 2: [#HEX] - usage
  Accent 3: [#HEX] - usage

Visual Elements:
  - [Element 1]
  - [Element 2]

Density Guidelines:
  - Max [N] text elements per slide
  - [Other rules]

Style Rules:
  Do: [List]
  Don't: [List]
</STYLE_INSTRUCTIONS>
```

**Self-check**: Read narrative-brief.md back to user. Confirm it matches the Phase 1 discussion before proceeding.

**Content Integrity Check**: Every claim, quote, and example in `content.md` must be traceable to:
1. User's own words (from Phase 0 source materials)
2. User-approved external references
3. User's explicit statements during Phase 1 discussion

AI must NOT invent facts, quotes, or examples. If the user said it, use it. If they didn't, ask them. If they don't have it, mark it as `[TODO: user to provide]`.

---

## Phase 3: Delegate to baoyu-slide-deck (Prompts)

**Goal**: Generate outline and prompts using baoyu-slide-deck.

### Step 3.1: Prepare Input

Ensure `content.md` is ready. If `style-instructions.md` exists, note the style preference for passing to baoyu-slide-deck.

### Step 3.2: Call baoyu-slide-deck

在 Claude Code 中调用 baoyu-slide-deck skill（两种等效方式）：

```
/baoyu-slide-deck 00-上游/content.md --prompts-only [--style <preset>]
```

或直接使用 Skill 工具（当 `/` 命令不可用时）：
```
Skill({"skill": "baoyu-slide-deck", "args": "00-上游/content.md --prompts-only [--style <preset>]"})
```

**Pre-call setup**:
1. **Inject narrative-brief**: Append `narrative-brief.md` (or its ABCDEFG arc section) to the top of `content.md` so baoyu receives the narrative structure, not just raw content.
2. **Inject confirmed choices**: Prepend a metadata block to `content.md` with the already-confirmed choices. This acts as a strong signal for baoyu's auto-detect and reduces the chance of style drift during confirmation:
   ```markdown
   <!-- CONFIRMED CHOICES — do not override without discussion -->
   - Style: [preset name or custom]
   - Audience: [audience from Phase 1]
   - Slide count: [N slides for X-min talk]
   - Language: [zh/en/etc]
   - Review preference: [skip outline / skip prompts / none]
   ```
3. **Style selection**: If user specified a baoyu preset → use it; if custom `style-instructions.md` exists → use `--style custom`; otherwise auto-detect.

**⚠️ Confirmation overlap warning**: baoyu-slide-deck Step 2 will ask the user to confirm style, audience, slide count, outline review, and prompt review. Since these were already discussed in Phase 1, **instruct the user to stick with the choices we just made** rather than reconsidering. This prevents confirmation fatigue and style drift.

| User's Description | baoyu Preset |
|-------------------|--------------|
| Flat cartoon, tech explainer | `vector-illustration` or `bold-editorial` |
| Hand-drawn edu, infographic, process | `hand-drawn-edu` |
| Chalkboard, workshop | `chalkboard` or `sketch-notes` |
| Corporate, B2B, investor deck | `corporate` or `minimal` |
| Editorial, magazine, product launch | `bold-editorial` |
| Journalism, explainer, science communication | `editorial-infographic` |
| Dark, gaming, atmospheric | `dark-atmospheric` |
| Retro, pixel, developer talk | `pixel-art` |
| Watercolor, lifestyle, travel | `watercolor` |
| Blueprint, technical, architecture | `blueprint` |
| Academic, research, bilingual | `intuition-machine` |
| Notion, SaaS, product demo | `notion` |
| Story, fantasy, animation | `fantasy-animation` |
| Biology, chemistry, medical | `scientific` |
| History, heritage, vintage | `vintage` |

### Step 3.3: Post-process Prompts

After baoyu-slide-deck generates prompts in `prompts/`:

1. **Copy to user's structure**: Move/copy prompts to `03-prompts/`
2. **Inject custom style**: If `style-instructions.md` exists, ensure FULL content is embedded in every prompt file
3. **Add narrative goal**: Append `// NARRATIVE GOAL` section to each prompt based on `narrative-brief.md`

Prompt template addition:
```markdown
---

## NARRATIVE CONTEXT

// NARRATIVE GOAL
[What this slide achieves in the talk arc]

// SPEAKER NOTES
[What the speaker says while this slide is shown]
```

**Self-check**: All prompts include full style-instructions.md? Narrative goals added? Files in `03-prompts/`?

---

## Phase 4: Prompt Review (Conditional)

**Goal**: Human review before image generation.

**If user wants to review** (recommended):
1. Display prompt summary table
2. Ask user: "Ready to generate images?"
3. If edits needed → user edits `03-prompts/*.md` → regenerate specific prompts via baoyu-slide-deck

**If user skips review**: Proceed to Phase 5.

---

## Phase 5: Delegate to baoyu-slide-deck (Images)

**Goal**: Generate slide images.

### Step 5.1: Call baoyu-slide-deck

```
/baoyu-slide-deck . --images-only
```

Or using Skill tool:
```
Skill({"skill": "baoyu-slide-deck", "args": ". --images-only"})
```

**Important**: baoyu-slide-deck expects prompts in a flat `prompts/` directory (its native output structure). If you have already reorganized to `03-prompts/` (Phase 6), create a temporary copy before calling:
```bash
# From the project root (where 03-prompts/ exists)
cp -r 03-prompts prompts
/baoyu-slide-deck . --images-only
rm -rf prompts  # clean up after
```

**Note on deliverables**: baoyu-slide-deck internally generates `.pptx` and `.pdf` via its own `merge-to-pptx.ts` and `merge-to-pdf.ts` scripts (Step 8 of its workflow). These are the **primary** deliverables — they live in baoyu's flat output directory (`slide-deck/{topic-slug}/`).

The `scripts/merge_to_pptx.py` and `scripts/merge_to_pdf.py` in slides-creator are **not** duplicates. They serve a different purpose:
- **baoyu merge**: for baoyu's flat directory structure (PNG + prompts at same level)
- **slides-creator merge**: for the reorganized directory structure (`02-slides/` + `03-prompts/`)

Use slides-creator's merge scripts only after Phase 6 reorganization, or if baoyu's merge step fails.

### Step 5.2: Visual Verification

After generation:
1. **Test slide**: Read `01-slide-cover.png` (or first generated slide)
2. **Style check**: Compare against `style-instructions.md`
3. **Text check**: Verify Chinese/English text legibility
4. **If issues**: Update affected `03-prompts/*.md` → copy `cp -r 03-prompts prompts` → regenerate via `/baoyu-slide-deck . --regenerate N` (或 `Skill({"skill": "baoyu-slide-deck", "args": ". --regenerate N"})`) → clean up `rm -rf prompts`

**Self-check**: All slides generated? Style consistent? Text legible?

---

## Phase 6: Post-processing & Delivery

**Goal**: Reorganize baoyu-slide-deck output into user's preferred structure.

### 6.1 Directory Reorganization

baoyu-slide-deck outputs to `slide-deck/{topic-slug}/`:
```
slide-deck/{topic-slug}/
├── source-{slug}.md
├── outline.md
├── prompts/
├── *.png
├── {topic-slug}.pptx
└── {topic-slug}.pdf
```

Reorganize to user's structure:
```
{project-name}/
├── 00-上游/                    # Source materials
│   ├── prompt-最初提示词.txt   # Original user prompt (if saved)
│   ├── narrative-brief.md      # Phase 1 output
│   ├── content.md              # Phase 2 output (baoyu input)
│   ├── style-instructions.md   # Visual design SSOT
│   └── outline.md              # From baoyu-slide-deck
├── 01-成品/                    # Final deliverables
│   ├── {project-name}.pdf
│   └── {project-name}.pptx
├── 02-slides/                  # Generated PNGs (当前版本)
│   ├── 01-slide-cover.png
│   └── ...
├── 03-prompts/                 # Per-slide prompts (SSOT)
│   ├── v6/                     # 支持版本子目录（如 v6, v7...）
│   │   ├── 01-slide-cover.md
│   │   └── ...
│   └── 01-slide-cover.md       # 或平铺结构
├── speaker-notes.md            # Auto-extracted from 03-prompts/ via extract_notes.py
├── v6/                         # baoyu-slide-deck 临时输出（需搬迁到 02-slides/）
│   └── ...
└── _archive/                   # Historical versions
    └── v1/
```

**Note on versioning**:
- `03-prompts/` 支持平铺或版本子目录（`v6/`, `v7/`）。当同一项目多次迭代时，用子目录保留历史版本。
- baoyu-slide-deck 可能直接输出到项目根目录的临时文件夹（如 `v6/`）。Post-processing 时需将这些 PNG 移动到 `02-slides/`。

**Archive current version** (before major iteration):
```bash
uv run scripts/archive_version.py --project /path/to/project
```
Archives `02-slides/` + `03-prompts/` to `_archive/v{N}/` (auto-incremented).

### 6.2 Extract Speaker Notes

Use `scripts/extract_notes.py` to extract structured notes from `03-prompts/*.md`:

```bash
uv run scripts/extract_notes.py --prompts 03-prompts --output speaker-notes.md
```

Extracts:
- `// NARRATIVE GOAL` sections
- `// SPEAKER NOTES` sections
- Falls back to `// KEY CONTENT` if neither found

Output format (`speaker-notes.md`):
```markdown
# Speaker Notes

## 01-slide-cover
**Narrative Goal**: ...
**Speaker Notes**: ...

## 02-slide-intro
...
```

**Note**: `main.ts` auto-runs this step if `03-prompts/` exists.

### 6.3 Archive Original Prompt

If user provided an original prompt (like the 35KB prompt for 龙虾 vs Claude Code):
- Save as `00-上游/prompt-最初提示词.txt`

### 6.4 Final Verification Checklist

- [ ] PDF opens and all slides render correctly
- [ ] PPTX opens without errors
- [ ] PNG sequence numbered correctly (01, 02, ...)
- [ ] Speaker notes cover all slides
- [ ] Style consistent across all slides
- [ ] No garbled or missing text
- [ ] `00-上游/` contains all source SSOT files
- [ ] `03-prompts/` contains all prompt files

---

## Iteration Workflow

### Path A: Content Changes
```
User feedback → Update narrative-brief.md → Update content.md
→ Regenerate prompts (/baoyu-slide-deck content.md --prompts-only)
→ Regenerate images (/baoyu-slide-deck . --images-only)
→ Reorganize + extract notes
```

### Path B: Style Changes
```
User feedback → Update style-instructions.md
→ Update all prompts (inject new style into 03-prompts/*.md)
→ Regenerate all images (via /baoyu-slide-deck . --images-only)
→ Reorganize + extract notes
```

### Path C: Single Slide Fix
```
User feedback → Update 03-prompts/NN-slide-xxx.md
→ Copy prompts: cp -r 03-prompts prompts
→ /baoyu-slide-deck . --regenerate N
→ Clean up: rm -rf prompts
→ Replace in 02-slides/
→ Regenerate PPTX/PDF
```

**Note on `--regenerate`**: baoyu-slide-deck reads from flat `prompts/` directory. After reorganization to `03-prompts/`, create a temporary copy (`cp -r 03-prompts prompts`) before regenerating. If you haven't reorganized yet (still in baoyu's flat structure), call directly without copying.

---

## Script Reference

| Script | Purpose |
|--------|---------|
| `scripts/main.ts` | Post-processing: validate + extract notes + generate PDF/PPTX |
| `scripts/merge_to_pptx.py` | Merge PNGs to PPTX with structured speaker notes from `03-prompts/*.md` |
| `scripts/merge_to_pdf.py` | Merge PNGs to PDF (reorganized `02-slides/` structure) |
| `scripts/validate_slides.py` | Check aspect ratio, naming, missing slides |
| `scripts/extract_notes.py` | Extract structured speaker notes from `03-prompts/*.md` to `speaker-notes.md` |
| `scripts/archive_version.py` | Archive `02-slides/` + `03-prompts/` to `_archive/v{N}/` |

---

## Failure Log (Do NOT Repeat)

| Failure | Root Cause | Prevention |
|---------|-----------|------------|
| **AI wrote content for the user — polished garbage** | Violated First Law: skipped Phase 0, fabricated quotes/examples. See `references/content-creation-first-law.md` | **First Law is absolute**: collect user's words FIRST. No source material = STOP and ask. AI assists expression, never replaces it |
| Generated 30 slides for 20-min talk | Didn't enforce slide count guide | Check duration ÷ 2 = max slides |
| Style drift between versions | Style instructions not in prompts | Paste FULL style-instructions.md into every prompt |
| Text unreadable in images | Model doesn't support Chinese well | Test with Chinese text first |
| Narrative arc flat | Jumped to prompts without Phase 1 | ALWAYS discuss narrative first |
| User unhappy with first draft | Didn't confirm before batch | Generate ONE test slide, get approval |
| Directory mess | Didn't use consistent structure | Always use 00-上游/01-成品/02-slides/03-prompts |
| Redundant work | Tried to replace baoyu-slide-deck | Delegate visual generation, focus on narrative |
| Merge scripts questioned as duplicates | Baoyu merge scripts exist but: (1) path unstable (`~/.claude/plugins/...`); (2) expect flat `prompts/` dir; (3) inject full base prompt as notes noise | Keep own merge scripts for reorganized structure. Validate before deleting — call baoyu merge first if accessible |

---

## References

- `references/content-creation-first-law.md` — Universal principle: user's voice is primary, applies to all content types (slides, articles, ads, courses)
- `references/narrative-design-guide.md` — ABCDEFG model detailed guide
- `references/prompt-templates/` — Prompt templates for common slide types
- `references/style-gallery.md` — Visual style gallery with examples
