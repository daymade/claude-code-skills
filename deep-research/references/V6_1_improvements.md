# Deep Research Skill V6.1 Improvements

**Date**: 2026-04-03  
**Version**: 2.3.0 → 2.4.0  
**Based on**: User feedback and "字节跳动" case study

---

## Summary of Changes

### 1. Source Accessibility Policy - Critical Correction

**Problem Identified**:  
Previously, we incorrectly banned all "privileged" sources. This was wrong because it prevented users from leveraging their competitive information advantages.

**The Real Issue**:  
The problem is not using user's private information—it's **circular verification**: using user's data to "discover" what they already know about themselves.

**Example of the Error**:
```
User: "Research my company 字节跳动子公司"
❌ WRONG: Access user's Spaceship → "You own 25 domains"
   → This is circular: user already knows they own these domains

✅ RIGHT: Check public WHOIS → "Privacy protected, ownership not visible"
   → This is external research perspective
```

**Correct Classification**:

| Accessibility | For Self-Research | For Third-Party Research |
|--------------|-------------------|-------------------------|
| `public` | ✅ Use | ✅ Use |
| `semi-public` | ✅ Use | ✅ Use |
| `exclusive-user-provided` | ⚠️ Careful* | ✅ **ENCOURAGED** |
| `private-user-owned` | ❌ **FORBIDDEN** | N/A |

\* When user provides exclusive sources for their own company, evaluate if it's circular

### 2. Counter-Review Team V2

**Created**: 5-agent parallel review team
- 🔵 claim-validator: Claim validation
- 🟢 source-diversity-checker: Source diversity analysis
- 🟡 recency-validator: Recency/freshness checks
- 🟣 contradiction-finder: Contradiction and bias detection
- 🟠 counter-review-coordinator: Synthesis and reporting

**Usage**:
```bash
# 1. Dispatch to 4 specialists in parallel
SendMessage to: claim-validator
SendMessage to: source-diversity-checker
SendMessage to: recency-validator
SendMessage to: contradiction-finder

# 2. Send to coordinator for synthesis
SendMessage to: counter-review-coordinator
```

### 3. Methodology Clarifications

#### When Researching User's Own Company
- **Approach**: External investigator perspective
- **Use**: Public sources only
- **Do NOT use**: User's private accounts (creates circular verification)
- **Report**: "From public perspective: X, Y, Z gaps"

#### When User Provides Exclusive Sources for Third-Party Research
- **Approach**: Leverage competitive advantage
- **Use**: User's paid subscriptions, private APIs, proprietary databases
- **Cite**: Mark as `exclusive-user-provided`
- **Report**: "Per user's exclusive source [Crunchbase Pro], competitor X raised $Y"

### 4. Registry Format Update

**Added fields**:
- `Accessibility`: public / semi-public / exclusive-user-provided / private-user-owned
- `Circular rejection tracking`: Note when sources are rejected for circular verification

**Updated anti-patterns**:
- ❌ **CIRCULAR VERIFICATION**: Never use user's private data to "discover" what they already know
- ✅ **USE EXCLUSIVE SOURCES**: When user provides Crunchbase Pro etc. for competitor research, USE IT

### 5. Documentation Updates

**New/Updated Files**:
- `source_accessibility_policy.md`: Complete rewrite explaining circular vs. competitive advantage distinction
- `counter_review_team_guide.md`: Usage guide for the 5-agent team
- `SKILL.md`: Updated Source Governance section with correct classification
- `marketplace.json`: Updated description

---

## Key Principles Summary

1. **Circular Verification is Bad**: Don't use user's data to tell them what they already know
2. **Exclusive Information Advantage is Good**: Use user's paid tools to research competitors
3. **External Perspective for Self-Research**: When researching user's own company, act like an external investigator
4. **Leverage Everything for Third-Party**: When researching others, use every advantage user provides

---

## Version History

| Version | Changes |
|---------|---------|
| 2.0.0 | Initial Enterprise Research Mode |
| 2.1.0 | V6 features: source governance, AS_OF, counter-review |
| 2.2.0 | Counter-Review Team |
| 2.3.0 | Source accessibility (initial, incorrect ban on privileged) |
| **2.4.0** | **Corrected: circular vs. exclusive advantage distinction** |
