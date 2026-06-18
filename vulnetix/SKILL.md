---
name: vulnetix
description: Vulnerability intelligence and remediation skills for Claude Code
---

# Vulnetix — Vulnerability Intelligence Suite

7 security skills powered by the [Vulnetix VDB API](https://vulnetix.com):

- `/vulnetix:vuln` — Look up vulnerabilities by ID (CVE/GHSA/etc.) or list all vulns for a package
- `/vulnetix:exploits` — Analyze exploit intelligence with CWSS priority scoring and threat modeling
- `/vulnetix:exploits-search` — Search exploits filtered by ecosystem, severity, EPSS, and source
- `/vulnetix:fix` — Get fix intelligence with Safe Harbour confidence scores and upgrade paths
- `/vulnetix:remediation` — Context-aware remediation plans with CrowdSec threat intelligence
- `/vulnetix:package-search` — Assess package security risk before adding dependencies
- `/vulnetix:dashboard` — View tracked vulnerabilities and their current status

## Installation

See [Vulnetix Claude Code Plugin](https://github.com/Vulnetix/claude-code-plugin) for setup instructions.

## When to Use

- Investigating a CVE or security advisory
- Assessing whether a vulnerability affects your project
- Planning dependency upgrades with security context
- Searching for known exploits before deploying
- Generating remediation plans with verification steps
