---
name: sequenzy-email-marketing
description: Use Sequenzy to manage subscribers, lists, tags, segments, templates, campaigns, sequences, stats, and SaaS/Shopify lifecycle email workflows from an AI agent.
version: 1.0.0
author: Sequenzy
license: MIT
metadata:
  hermes:
    tags: [email-marketing, lifecycle-email, saas, shopify, campaigns, subscribers, transactional-email]
    homepage: https://sequenzy.com
---

# Sequenzy Email Marketing

Use this skill when a user asks an agent to operate Sequenzy: inspect account/company state, manage subscribers, create lists or segments, draft templates, build campaigns, create lifecycle sequences, send campaign tests, or review email performance.

## Setup

Install the CLI:

```bash
npm install -g @sequenzy/cli@latest
```

Authenticate interactively:

```bash
sequenzy login
sequenzy whoami
```

For automation, set an API key:

```bash
export SEQUENZY_API_KEY="seq_live_..."
```

## Safety rules

1. Inspect before mutating: run `sequenzy whoami` and the relevant `list`/`get` command before creating or updating records.
2. Never send or enable a campaign/sequence without explicit user approval.
3. Validate recipient emails, company IDs, list IDs, template IDs, and segment rules before mutation.
4. Prefer test sends before live sends.
5. If a requested workflow is not available in the CLI, say so and use the dashboard or API docs as the fallback.

## Common commands

```bash
# Identity and account
sequenzy whoami
sequenzy account
sequenzy companies list

# Subscribers
sequenzy subscribers list
sequenzy subscribers add --email person@example.com --first-name Jane
sequenzy subscribers get person@example.com
sequenzy subscribers remove person@example.com

# Lists, tags, and segments
sequenzy lists list
sequenzy lists create --name "Trial Users"
sequenzy tags list
sequenzy segments list
sequenzy segments create --name "Active Trials" --conditions '{"status":"trial"}'
sequenzy segments count <segment-id>

# Templates
sequenzy templates list
sequenzy templates get <template-id>
sequenzy templates create --name "Trial welcome" --subject "Welcome to {{company_name}}" --html-file welcome.html
sequenzy templates update <template-id> --subject "Updated subject"

# Campaigns and sequences
sequenzy campaigns list
sequenzy campaigns get <campaign-id>
sequenzy campaigns create --name "Launch follow-up" --subject "Quick follow-up" --html-file campaign.html
sequenzy campaigns test <campaign-id> --to you@example.com
sequenzy sequences list
sequenzy sequences create --name "Trial onboarding" --goal "Convert trial users to paid customers"
sequenzy sequences enable <sequence-id>
sequenzy sequences disable <sequence-id>

# Stats
sequenzy stats
sequenzy stats --campaign <campaign-id>
sequenzy stats --sequence <sequence-id>
```

## Agent workflow

1. Confirm auth with `sequenzy whoami`.
2. Inspect the target company, list, segment, campaign, sequence, or template.
3. Draft copy that matches the user's brand and goal.
4. Create or update the Sequenzy object.
5. Send a test when supported.
6. Summarize exactly what changed and what still needs approval before anything goes live.

## Example tasks

- "Create a 4-email trial onboarding sequence for a B2B SaaS."
- "Add this CSV of subscribers to my Sequenzy list."
- "Draft and create a Product Hunt launch follow-up campaign."
- "Show me campaign stats for the last 30 days."
- "Create a winback segment for users who have not opened in 60 days."

## References

- Website: https://sequenzy.com
- CLI package: https://www.npmjs.com/package/@sequenzy/cli
