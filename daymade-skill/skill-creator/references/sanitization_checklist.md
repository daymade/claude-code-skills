# Skill Sanitization Checklist

When extracting a skill from a business project for public distribution, systematically remove all business-specific content to make it generic and reusable.

## Step 0: decide the destination — this checklist may not apply at all

Everything in this file describes what goes wrong when a skill reaches people who are not
the author. **A skill living in the author's own private repo is a different artifact with a
different failure mode**, and running this checklist against it does damage:

| | Public destination | Private destination |
|---|---|---|
| A real absolute path | breaks on every other machine | **is why the script runs** |
| A pre-filled credential / entity in a template | leak | saves the next run from re-filling it |
| A real project name in an example | leak | the example everyone there recognizes |
| Correct action | sanitize | **report, and let the owner decide** |

How to tell: `gh repo view --json isPrivate` on the repo the skill lives in. `quick_validate`
does this automatically and prints a `🔒 audience: private` note when it applies; pass
`--audience=public` to force the strict pass when preparing a private skill for release.

**Why this matters more than it looks.** A checker that flags healthy input teaches people to
ignore it. The research is unambiguous: ~90% of developers accept a false-positive rate up to
5%, only 24% tolerate 20%, and developers actively **prefer tools that find fewer real bugs
over tools that cry wolf** — false positives are the dominant barrier to static-analysis
adoption ([Chou, *False Positives Over Time*](https://www.cs.umd.edu/~pugh/BugWorkshop05/papers/34-chou.pdf);
[Why do or why don't developers use static analysis tools](https://ceur-ws.org/Vol-4077/paper17.pdf)).
Sanitizing a private skill's working paths is exactly that failure: the owner learns the
checker costs them a working tool, and turns it off everywhere — including on the public
skill where it was the only thing standing between them and a real leak.

**Real incident (2026-07-19):** a validator warning about an absolute path in a *private*
skill was read as a defect. The path was replaced with `<project-root>/合同/<合同名>` and the
script stopped running. The same pass rewrote a hardcoded assertion "to make it reusable" and
silently dropped one branch of an `or`, so a case that used to pass began failing. The owner's
words: 「这是我的私人仓库啊，按照我们已有的规则，不要管它，不然的话你反而去影响我自己的正常使用。」
Everything was reverted. The warning had never said to fix it — it said `Skill is valid!` —
the escalation from *warning* to *work order* was the whole error.

## The rule that matters most: read it yourself, don't just grep

Scanners — gitleaks, the grep patterns below, `security_scan.py` — only match what you **thought to list**: known secret formats, a name list you wrote, specific path shapes. They are blind to the most dangerous leak of all: **real content with no proper noun to catch.** A verbatim spoken line from a real transcript (a casual aside with no name in it), a specific real-world example dropped into an illustration, a real meeting or project mentioned in passing, a codename you simply forgot to add to the word list — none of these have a keyword for grep to hit, so every scanner sails right past them.

The primary sanitization method is therefore **you reading the entire skill** — SKILL.md, every reference file, every example, every bundled doc — and judging each concrete noun, example, and snippet semantically:

> "Does this read like a generic placeholder or a public entity (Claude, GitHub, LangChain, `<project>`), or like it was lifted from a real project / person / transcript?"

Anything in the second category gets replaced — **even if no scanner flagged it.**

**"grep returned no matches" is not a clean bill of health.** It only means the word list you guessed didn't fire. Run the scanners below as a cheap first pass for the obvious stuff, then do the read-through as the actual gate. If you only do one, do the read-through.

## Quick Scan Commands

Run these grep patterns to identify potential sensitive content:

```bash
# Business/product names (case-insensitive)
grep -rniE "acme|globex|[company-name]|[product-name]" skill-folder/

# Person names (look for capitalized names)
grep -rniE "\b(Carol|John|Alice|Bob|小华|小明)\b" skill-folder/

# Absolute paths and usernames
grep -rniE "/Users/|/home/|/mnt/c/Users|OneDrive|username" skill-folder/

# Chinese characters (if skill should be English-only)
grep -rn '[一-龥]' skill-folder/

# Internal jargon
grep -rniE "ultrathink|internal-only|confidential" skill-folder/
```

## Categories to Sanitize

### 1. Product and Project Names

**What to find:**
- Project codenames (e.g., "Acme Prepared", "Project Phoenix")
- Internal product names (e.g., "Ops Console", "Admin Dashboard")
- Tool-specific names (e.g., "Globex Gemini" → just "Gemini")
- **CJK project/instance nicknames** (e.g., real pet-names for your own instances). gitleaks ignores CJK entirely, and the person-name grep above only lists a few given names — a Chinese project nickname sprinkled through your examples sails past every scanner.

> **War-story (2026-06-28):** the `openclaw` skill used two real private instance nicknames as examples in 13+ places across SKILL.md and an architecture doc. `security_scan` was green, gitleaks found nothing, every grep pattern missed them — they were caught only by reading the file and recognizing the names as a real project, then replaced with generic placeholders. **A green scan on a config / personal-workflow skill is exactly when to slow down and read every example noun**, because those skills are built around your own real instances.

**How to replace:**
- Use generic terms: "the system", "the application", "the service"
- Use placeholder patterns: `<project-name>`, `<product-name>`
- Use generic examples: "e-commerce platform", "user management system"

### 2. Person Names

**What to find:**
- Real employee names in examples: "Carol will handle...", "小华你来..."
- Team member references in action items
- Author attributions that reveal identity

**How to replace:**
- Use generic names: "Alice", "Bob", "the developer", "the reviewer"
- Use role-based references: "Backend team", "PM", "Designer"
- Remove author attributions or use placeholders

### 3. Entity and Data Model Names

**What to find:**
- Business-specific entities: `REVIEW_RESULT`, `RISK_MODEL`, `INSPECTION_FACTOR`
- Domain-specific hierarchies: `Section → Area → Item → Evidence`
- Field names revealing business logic: `risk_level`, `underwriting_status`

**How to replace:**
- Use generic entities: `ORDER`, `ORDER_ITEM`, `USER`, `PRODUCT`
- Use generic hierarchies: `Category → Subcategory → Item → Detail`
- Use generic fields: `status`, `quantity`, `customer_name`

### 4. Folder Structures and Paths

**What to find:**
- Team-specific folders: `10-team-collaboration/Meeting Minutes`
- Project-specific paths: `ops-console-api-design`
- Environment-specific paths: user home directory project paths

**How to replace:**
- Use generic paths: `project-docs/meeting-minutes`
- Use placeholder paths: `<project-root>/docs/`
- Use relative paths within skill bundle

### 5. Internal Terminology and Jargon

**What to find:**
- Internal slang: "ultrathink", "deep dive session"
- Company-specific processes: "Acme standup", "Portal review"
- Abbreviations without context: "MP", "RP", "UW"

**How to replace:**
- Use industry-standard terms: "deep review", "thorough analysis"
- Expand or remove unexplained abbreviations
- Use generic process names

### 6. Language-Specific Content

**What to find:**
- Chinese phrases in English skills: "后面再说", "MVP 先不做"
- Mixed language examples that assume bilingual context
- Culture-specific references

**How to replace:**
- Translate to the skill's primary language
- Use language-neutral examples
- Or explicitly support multilingual with clear labels

### 7. Business Logic Examples

**What to find:**
- Domain-specific workflows: "Underwriting system conflicts"
- Business rules: "Inspection Factor vs Risk Factor"
- Industry-specific terminology without explanation

**How to replace:**
- Use generic software examples: "Note field conflicts with Comment system"
- Use universal patterns: "UserProfile vs Account naming conflict"
- Add context if domain terms are necessary

### 8. External Service References

**What to find:**
- Internal APIs: `POST /evaluate (push to Risk Model)`
- Company-specific integrations: "Sync with Underwriting system"
- Internal tool names: "Globex search", "Internal Wiki"

**How to replace:**
- Use generic services: `POST /process (send to External Service)`
- Use placeholder APIs: `<external-api>/endpoint`
- Use generic tool categories: "enterprise search", "knowledge base"

## Sanitization Process

### Phase 1: Automated Scan

```bash
# Run all grep patterns above
# Export results to a file for review
grep -rniE "pattern1|pattern2|pattern3" skill-folder/ > sanitization_report.txt
```

### Phase 2: Manual Review

For each match:
1. Determine if it's truly business-specific or generic
2. Decide on appropriate replacement
3. Check if replacement maintains meaning
4. Verify no broken references

### Phase 3: Verification (the read-through is the real gate)

After sanitization:
1. **Read the whole skill again yourself** — SKILL.md + every reference + every example — re-asking the semantic question above on each concrete noun and snippet. This is what catches the no-keyword leaks (a verbatim transcript line, a real spoken example) that scanners structurally cannot see. **This step, not the grep, is what "passes" sanitization.**
2. Re-run the grep patterns + `security_scan.py` as a secondary check — but read "no matches" as "the obvious stuff is gone", never as "it's clean"
3. Test skill functionality still works (no broken references after replacements)
4. If you can, have a fresh reader — a person, or a subagent with no prior context — read it cold; fresh eyes catch what you've already read past

## Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| Over-sanitizing generic terms | "reviewer" as a role is fine; "Ops Console" is not |
| Breaking examples by removing context | Replace with equivalent generic examples |
| Leaving orphaned references | Check all cross-references after renaming |
| Inconsistent replacements | Use find-and-replace for consistency |
| Sanitizing technical terms | Keep industry-standard terms (API, JSON, MVP) |

## Checklist Before Completion

- [ ] No product/project codenames remain
- [ ] No real person names in examples
- [ ] No business-specific entity names
- [ ] No internal folder structures
- [ ] No unexplained jargon or abbreviations
- [ ] No language-specific content (unless intentional)
- [ ] No internal API or service references
- [ ] All examples are generic and universally understandable
- [ ] Skill still functions correctly after changes
- [ ] Someone unfamiliar with original project can understand it
