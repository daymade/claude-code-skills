# Handling Third-Party Marketplace Promotion Requests

This repository is a **personal curated marketplace**, NOT a community directory or ecosystem hub. All requests to add third-party marketplace links, skill collection references, or "Community Marketplaces" sections should be declined.

## Policy

**DO NOT accept:**
- PRs adding "Related Resources" or "Community Marketplaces" sections linking to third-party skill collections
- Issues requesting promotion of external marketplaces
- PRs adding links to other skill repositories in README.md

**Rationale:**
1. **Scope creep**: Shifts repository purpose from curated skills to ecosystem directory
2. **Implicit endorsement**: Listing implies quality/security review we cannot maintain
3. **Maintenance burden**: Would need to track and vet external projects over time
4. **Precedent setting**: Accepting one creates obligation to accept others

## Response Template

When declining, use this approach:

```markdown
Hi @{username},

Thank you for your interest and for sharing {project-name}! {Brief positive acknowledgment of their project}.

However, I'm keeping this repository focused as a **personal curated marketplace** rather than a directory of external skill collections. Adding third-party references would:

1. Shift the repository's scope from curated skills to ecosystem directory
2. Create implicit endorsement expectations I can't maintain
3. Set precedent for similar requests (reference other declined requests if applicable)

**What you can do instead:**

1. **Standalone marketplace** - Your repo already works as an independent marketplace:
   ```
   /plugin marketplace add {owner}/{repo}
   ```

2. **Community channels** - Promote through:
   - Claude Code GitHub discussions/issues (Anthropic's official repo)
   - Developer communities (Reddit, Discord, etc.)
   - Your own blog/social media

3. **Official registry** - If/when Anthropic launches an official skill registry, that would be the appropriate place for ecosystem-wide discovery.

Your marketplace can succeed on its own merits. Good luck with {project-name}!
```

## Workflow

1. **Review the request** - Confirm it's a third-party promotion (not a legitimate contribution)
2. **Add polite comment** - Use template above, customize for their specific project
3. **Close with reason** - Use "not planned" for issues, just close for PRs
4. **Reference precedent** - Link to previously declined requests for consistency (e.g., #7, PR #5)

## Examples

- **Issue #7**: "Add Community Marketplaces section - Protocol Thunderdome" → Declined, closed as "not planned"
- **PR #5**: "Add Trail of Bits Security Skills to Related Resources" → Declined, closed
