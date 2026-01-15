# Project Evaluation Guide

How to evaluate open-source projects before contributing.

## Quick Health Check

```bash
# Check recent activity
gh repo view owner/repo --json updatedAt,stargazersCount,openIssues

# Check PR response time
gh pr list --repo owner/repo --state merged --limit 10

# Check issue activity
gh issue list --repo owner/repo --limit 20
```

## Evaluation Criteria

### 1. Activity Level

| Signal | Good | Bad |
|--------|------|-----|
| Last commit | < 1 month | > 6 months |
| Open PRs | Being reviewed | Ignored |
| Issue responses | Within days | Never |
| Release frequency | Regular | Years ago |

### 2. Community Health

| Signal | Good | Bad |
|--------|------|-----|
| CONTRIBUTING.md | Exists, detailed | Missing |
| Code of Conduct | Present | Missing |
| Issue templates | Well-structured | None |
| Discussion tone | Friendly, helpful | Hostile |

### 3. Maintainer Engagement

| Signal | Good | Bad |
|--------|------|-----|
| Review comments | Constructive | Dismissive |
| Response time | Days | Months |
| Merge rate | Regular merges | Stale PRs |
| New contributor PRs | Welcomed | Ignored |

### 4. Documentation Quality

| Signal | Good | Bad |
|--------|------|-----|
| README | Clear, comprehensive | Minimal |
| Getting started | Easy to follow | Missing |
| API docs | Complete | Outdated |
| Examples | Working, relevant | Broken |

## Scoring System

Rate each category 1-5:

```
Activity Level:      _/5
Community Health:    _/5
Maintainer Engage:   _/5
Documentation:       _/5
----------------------------
Total:               _/20
```

**Interpretation:**
- 16-20: Excellent choice
- 12-15: Good, proceed with caution
- 8-11: Consider carefully
- < 8: Avoid or expect delays

## Red Flags

### Immediate Disqualifiers

- No commits in 1+ year
- Maintainer explicitly stepped away
- Project archived
- License issues

### Warning Signs

- Many open PRs without review
- Hostile responses to contributors
- No clear contribution path
- Overly complex setup

## Green Flags

### Strong Indicators

- "good first issue" labels maintained
- Active Discord/Slack community
- Regular release schedule
- Responsive maintainers
- Clear roadmap

### Bonus Points

- Funded/sponsored project
- Multiple active maintainers
- Good test coverage
- CI/CD pipeline

## Research Checklist

```
Project Evaluation:
- [ ] Check GitHub Insights
- [ ] Read recent issues
- [ ] Review merged PRs
- [ ] Check contributor guide
- [ ] Look for "good first issue"
- [ ] Assess community tone
- [ ] Verify active maintenance
- [ ] Confirm compatible license
```

## Finding Projects

### By Interest

```bash
# Find by topic
gh search repos "topic:cli" --sort=stars

# Find by language
gh search repos "language:python" --sort=stars

# Find with good first issues
gh search issues "good first issue" --language=rust
```

### By Need

- Tools you use daily
- Libraries in your projects
- Frameworks you're learning
- Problems you've encountered

### Curated Lists

- awesome-for-beginners
- first-timers-only
- up-for-grabs.net
- goodfirstissue.dev
