# Source Accessibility Policy

**Version**: V6.1  
**Purpose**: Distinguish between legitimate exclusive information advantages and circular verification traps

---

## The Problem

In the "字节跳动" case study, we made a **methodology error**:

**What happened**:
1. User asked to research **their own company**: "字节跳动某子公司"
2. We accessed user's **own Spaceship account** (their private registrar)
3. Found 25 domains **the user already owned**
4. Reported back: "The company owns these 25 domains"

**Why this is wrong**:
- This is **circular reasoning**, not research
- User asked us to *discover* information about their company
- We instead *queried* their private data and presented it as findings
- It's like looking in someone's wallet to tell them how much money they have

**The real question**: Can an external investigator confirm this company exists?
**Answer**: No (WHOIS privacy, no public records)

---

## Core Principle: No Circular Verification

### ❌ FORBIDDEN: Self-Verification

When researching **the user's own assets/company/identity**:

| Scenario | WRONG | RIGHT |
|----------|-------|-------|
| User's company | "I found in YOUR registrar that YOU own these domains" | "Public WHOIS shows privacy protection - ownership not externally verifiable" |
| User's identity | "I checked YOUR email and found YOUR address" | "Please provide address if relevant to the research" |
| User's property | "I accessed YOUR bank to see YOUR balance" | Not applicable to research |

**Rule**: Cannot use user's private data to "discover" what user already knows about themselves.

---

### ✅ ALLOWED: Exclusive Information Advantage

When researching **third parties** (competitors, markets, investments):

| Source Type | Example | Usage |
|-------------|---------|-------|
| **User's paid subscriptions** | Crunchbase Pro, PitchBook, Wind | ✅ Use to research competitors |
| **User's proprietary databases** | Internal CRM, industry databases | ✅ Use to research market |
| **User's private APIs** | Trading APIs, data feeds | ✅ Use for investment research |
| **User's internal documents** | Prior research, memos | ✅ Use as background for new research |

**Rule**: User's exclusive information sources are competitive advantages - USE THEM for third-party research.

---

## The Distinction

```
Research Target: 字节跳动某子公司
├─ Is this the user's own company? → YES
├─ Can we use user's private data about it? → NO (circular)
└─ Must rely on: Public sources only

Research Target: 竞争对手公司 X
├─ Is this the user's own company? → NO
├─ Can we use user's Crunchbase Pro? → YES (competitive advantage)
└─ Can use: Public + User's exclusive sources
```

---

## Corrected Methodology

### When Researching User's Own Company

**Approach**: External investigator perspective

```
User: "Research my company 字节跳动子公司"

CORRECT RESPONSE:
1. Search public sources (WHOIS, web, news)
2. Find: Website placeholder, privacy-protected WHOIS, no news
3. Report: "From public perspective: minimal footprint, cannot verify ownership"
4. Gap: "Internal data not accessible to external investigators"

INCORRECT RESPONSE:
1. Access user's Spaceship account
2. Find: 25 domains user already knows they own
3. Report: "The company owns 25 domains" (user already knows this!)
```

### When User Provides Exclusive Sources

**Approach**: Leverage competitive advantage

```
User: "Research competitor X, I have Crunchbase Pro"
User: "Here's my API key: xxx"

CORRECT RESPONSE:
1. Use provided Crunchbase Pro API
2. Find: Funding history, team info not in public sources
3. Report: "Per Crunchbase Pro [exclusive source], X raised $Y in Series Z"
4. Cite: Accessibility: exclusive (user-provided)
```

---

## Source Classification

### public ✅
- Available to any external researcher
- Examples: Public websites, news, SEC filings

### exclusive-user-provided ✅ (FOR THIRD-PARTY RESEARCH)
- User's paid subscriptions, private APIs, internal databases
- **USE for**: Researching competitors, markets, investments
- **DO NOT USE for**: Verifying user's own assets/identity

### private-user-owned ❌ (FOR SELF-RESEARCH)
- User's own accounts, emails, personal data
- **DO NOT USE**: Creates circular verification

---

## Information Black Box Protocol

When an entity (including user's own company) has no public footprint:

1. **Document what external researcher would find**:
   - WHOIS: Privacy protected
   - Web search: No results  
   - News: No coverage

2. **Report honestly**:
   ```
   Public sources found: 0
   External visibility: None
   Verdict: Cannot verify from public perspective
   Note: User may have private information not available to external investigators
   ```

3. **Do NOT**:
   - Use user's private data to "fill gaps"
   - Present user's private knowledge as "discovered evidence"

---

## Checklist

When starting research, determine:

1. **Who is the research target?**
   - User's own company/asset? → Public sources ONLY
   - Third party? → Can use user's exclusive sources

2. **Am I discovering or querying?**
   - Discovering new info? → Research
   - Querying user's own data? → Circular, not allowed

3. **Would this finding surprise the user?**
   - Yes → Legitimate research
   - No (they already know) → Probably circular verification

---

## Summary

| Situation | Can Use User's Private Data? | Why? |
|-----------|------------------------------|------|
| Research user's own company | ❌ NO | Circular verification |
| Research competitor using user's Crunchbase | ✅ YES | Competitive advantage |
| Research market using user's database | ✅ YES | Exclusive information |
| "Discover" user's own domain ownership | ❌ NO | User already knows this |
