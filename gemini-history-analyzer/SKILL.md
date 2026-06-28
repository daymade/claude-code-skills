---
name: gemini-history-analyzer
description: Analyze Google Takeout exports of Gemini conversation history. Use when the user mentions Gemini takeout, Gemini export, Gemini history, Gemini conversation analysis, Google Takeout zip analysis, or drags a takeout zip into the project. Also use when the user asks to "analyze my Gemini data", "what did I talk to Gemini about", or wants to extract insights from Gemini chat logs.
argument-hint: [takeout-zip-path]
---

# Gemini History Analyzer

Extract, categorize, and analyze Google Takeout ZIP exports of Gemini Apps activity. The skill handles:
- Extraction (with Chinese/Unicode filename support)
- Content categorization and topic analysis
- User profile extraction from conversation patterns
- Domain-specific keyword search with context verification
- PII/sensitive content detection
- Structured report generation with optional memory file creation

## Quick Judgment: Meeting Transcripts vs Prompt-Response

Before full analysis, sample 3-5 files to determine the **conversation type**:

| Signal | Meeting Transcript | Prompt-Response |
|--------|-------------------|-----------------|
| Speaker labels | "张三:"、"李四:"、"Speaker 1:" | "User:"、"Assistant:"、"You:" |
| Content pattern | Discussion flow, turn-taking, small talk | Q&A, instruction→output |
| Length distribution | Variable, lots of short turns | Longer assistant responses |
| File naming | Often Chinese, meeting-style titles | English, topic-based titles |

The analysis approach differs:
- **Meeting transcripts** → topic categorization, speaker analysis, decision tracking, user profile extraction
- **Prompt-response** → usage pattern analysis, capability assessment, interest domain mapping

## Step 1: Extract the ZIP

Google Takeout files contain Chinese/Unicode filenames. **macOS `unzip` corrupts these — always use `unar`.**

```bash
# Install unar if missing
brew install unar 2>/dev/null || true

# Extract to a target directory
unar -o <output-dir> -q "<takeout-zip-path>"
```

The standard structure:
```
Takeout/
└── My Activity/
    └── Gemini Apps/
        ├── *.txt          # Conversation transcripts
        ├── *.html         # Web-format backups (rare)
        ├── *.png/jpg      # Images from conversations
        ├── *.mp3/mp4/wav  # Audio/video attachments
        ├── *.pdf          # Uploaded/shared documents
        ├── *.xlsx/docx    # Office documents
        └── *.zip          # Nested archives (animation frames, etc.)
```

## Step 2: Inventory and Categorize

Run a full inventory before reading any single file:

```bash
# Count by extension
find <extract-dir> -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn

# List all txt files (these are the primary content)
find <extract-dir> -name "*.txt" -type f | sort

# Get total size per type
find <extract-dir> -type f -exec du -sh {} \; | sort -rh | head -30
```

Build a table of:
- Total file count, total size
- Breakdown by file type (txt count/size, media count/size, etc.)
- Date range if file timestamps are meaningful

## Step 3: Sample and Classify

Read 3-5 txt files spread across the file list (not just the first few — timestamps/file sizes may cluster by type). For each:

1. Read the first ~100 lines to determine conversation type
2. Identify language (Chinese/English/mixed)
3. Classify topic area at a high level
4. Note speaker count and pattern

Use this sample to decide the analysis strategy for the remaining files.

## Step 4: Full Content Analysis

For each txt file, read and extract:

### 4a. Metadata
- Title (filename minus hash suffix)
- Approximate duration (from transcript timestamps)
- Speaker count and identities
- Language mix (Chinese % / English %)

### 4b. Topic Classification
Assign primary + secondary topics. Default categories (adjust based on actual content):
- Software Development
- AI/LLM Tools & Workflows
- Infrastructure/Cloud/DevOps
- Business/Strategy
- Product/Design
- Team/HR/Personnel
- Finance/Investment (this is often the target of analysis)
- Legal/Compliance
- Personal/Other

### 4c. Key Findings Per File
For each file, capture:
- Main discussion points (3-5 bullets)
- Decisions made or action items
- Notable quotes (verbatim, with context)
- Relationships mentioned (people, companies, projects)

## Step 5: Domain-Specific Keyword Search

When looking for content in a specific domain (finance, legal, etc.):

1. **Design keyword list with AND/OR logic** — e.g., finance: `stock OR investment OR fund OR portfolio OR 股票 OR 投资 OR 基金`, but also domain-specific terms like `EPS`, `P/E`, `dividend`, `arbitrage`
2. **Grep every txt file** for each keyword batch
3. **Read surrounding context** (10 lines before/after each match) — keyword matching alone produces massive false positives. "Investment" can mean business strategy, "option" can mean UI choice, "fund" can mean insurance feature
4. **Classify each match** as:
   - Definite hit (the conversation is about this domain)
   - False positive (same word, different meaning)
   - Ambiguous (needs deeper reading)
5. **Re-read full files** for definite + ambiguous hits

Never stop at grep output — context verification is mandatory.

## Step 6: Generate Report

### Report Structure

```markdown
# Gemini History Analysis Report
**Source**: <zip filename>
**Date analyzed**: <today>
**Extraction size**: <N files, N MB>

## 1. Content Overview
- Total conversations: N
- Conversation type: [Meeting Transcripts | Prompt-Response | Mixed]
- Language distribution: X% Chinese, Y% English, Z% Mixed
- Date range: <earliest> to <latest>
- Media attachments: N images, N audio, N video

## 2. Topic Distribution
| Category | Count | % | Notes |
|----------|-------|---|-------|
| ... | | | |

## 3. Key Findings
(Bulleted, organized by significance)

## 4. Domain-Specific Analysis
(If user requested finance/legal/etc. keyword search)
- Matches found: N
- Confirmed relevant: N
- False positives: N (with examples of what caused them)

## 5. Notable Documents
Non-txt files worth attention: PDFs, spreadsheets, etc.

## 6. Valuable Quotes
Verbatim quotes that capture key insights

## 7. PII / Sensitive Content
(Flag if detected — do NOT include the actual PII in the report)
- File: <name>, Type: <resume/background-check/etc.>, Risk: <high/medium/low>
```

## Step 7: Memory File Generation (Optional)

If the user wants to persist findings as project memory (like `.claude/projects/<path>/memory/`):

### When to generate memory files
- User explicitly asks ("build user profile", "remember this")
- The analysis reveals reusable insights about the user's preferences, workflows, or constraints
- The project has a memory system (check for existing `memory/MEMORY.md`)

### Memory file types to offer
1. **User profile** (`user-profile.md`) — if conversations reveal user's role, preferences, personality
2. **Feedback/Workflow** (`feedback-*.md`) — if conversations reveal proven workflows, dos/don'ts
3. **Project context** (`project-*.md`) — if conversations reveal ongoing projects, decisions, constraints

### Memory writing protocol
- Follow the project's existing memory format (check other memory files for frontmatter conventions)
- Include `originSessionId` or source tag pointing back to the analysis
- Update `MEMORY.md` index with new entries
- Never duplicate what's already in memory — update existing files instead

## Step 8: Cleanup

```bash
# Remove extracted files after analysis complete (user confirms)
rm -rf <extract-dir>
```

## Critical Pitfalls (From Real Usage)

### 1. ZIP extraction: ALWAYS use `unar`
macOS `unzip` silently corrupts Chinese filenames — files become garbled paths, many fail to extract. `brew install unar` + `unar -o <dir> <zip>` handles everything correctly.

### 2. Keyword search: grep is step 1, not the answer
Keyword matching on "stock", "investment", "fund", "option", "portfolio", "trading" produced matches in 80%+ of files in a real analysis — **every single one was a false positive**. These words appear in software development contexts constantly. Always read surrounding context for every match.

### 3. Know what you're reading
Gemini Takeout txt files are NOT the original Gemini prompt-response pairs. They can be:
- Meeting transcripts exported by 飞书妙记 (Feishu Miaojii) and then uploaded to Gemini
- Manual notes copy-pasted into Gemini
- PDF/article text pasted for analysis
Read the first ~100 lines of each file before assuming its nature.

### 4. PII is likely present
Resumes, background check forms, contact lists — these routinely appear in conversation history. Flag them, do NOT include their contents in reports. If creating memory files or wiki pages, ensure PII is summarized, not copied.

### 5. Large files need triage
A 63KB transcript is a 2-hour meeting. Don't read the whole thing unless it's flagged as highly relevant. Read the first 10% + last 10% for gist; read fully only if keyword hits or topic relevance warrant it.

### 6. Parallel reads for scale
For 100+ files, spawn parallel sub-agents to read and summarize in batches (10-15 files each). Merge results. One agent reading all files sequentially will exhaust context.
