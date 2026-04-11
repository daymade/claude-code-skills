# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **gangtise-copilot** v1.0.0: One-stop installer and companion for the full Gangtise (岗底斯投研) OpenAPI skill suite — 19 official skills covering data retrieval (OHLC 行情, 财务, 估值, 研报, 首席观点, 会议纪要, 调研纪要), research workflows (个股研究 L1-L4, 观点 PK 对抗性分析, 主题研究, 事件复盘, 公告摘要), and utility (股票池管理, 公开网页搜索). Distilled from a 5-round discovery session that reverse-engineered the complete Gangtise skill catalog — the Gangtise OBS bucket has LIST permission disabled, so the full 19-skill inventory is not discoverable from any public manifest. Ships with 4 preset install modes (full / workshop / minimal / custom), zero-config multi-agent distribution to Claude Code / OpenClaw / Codex via symlink from a single canonical install location, shared XDG credential file at `~/.config/gangtise/authorization.json` that rotates all 19 skills in one edit, and a read-only diagnostic script with scoped liveness checks (`auth` scope + `rag` scope). Ships: `scripts/install_gangtise.sh` (408 lines), `scripts/configure_auth.sh` (310 lines), `scripts/diagnose.sh` (320 lines), and 5 reference docs covering installation flow, credentials setup, the complete 19-skill registry with per-script capability matrix, known ecosystem traps (parallel product lines, bundle-only hidden skills, double-Bearer token bug, admin endpoint 1009 errors), and workshop best practices. Target use case: the 2026 Q2 investor Workshop series where students need to install a large skill suite quickly without reverse-engineering the catalog themselves.

### Changed
- **Renamed**: `markdown-tools` → `doc-to-markdown` — clearer name for DOCX/PDF/PPTX → Markdown conversion
- **doc-to-markdown**: Added 8 DOCX post-processing fixes (grid tables, simple tables, CJK bold spacing, JSON pretty-print, image path flattening, pandoc attribute cleanup, code block detection, bracket fixes)
- **doc-to-markdown**: Added 31 unit tests (`test_convert.py`)
- **doc-to-markdown**: Added 5-tool benchmark report (`references/benchmark-2026-03-22.md`)
- **marketplace-dev** v1.0.0 → v1.1.0: Added evidence intake from Claude Code history, plugin boundary decision guidance, source/cache patterns for single-skill and suite plugins, source+skills resolution validation, and cache footprint testing based on real marketplace debugging sessions.
- **marketplace-dev** v1.1.0 → v1.2.0: Refined against Anthropic's official skill-authoring best practices. Extracted the inline Node.js resolution check and diff pipeline into `scripts/check_marketplace.sh` — a one-shot validator that runs JSON syntax → `claude plugin validate` → source+skills resolution → reverse sync (disk SKILL.md → manifest) in a single command. Moved the two PostToolUse hook scripts from `scripts/` to `hooks/` for semantic clarity (scripts execute during skill workflow, hooks guard the editor) and updated the plugin manifest's hook paths accordingly. Added tables of contents to `anti_patterns.md` and `cache_and_source_patterns.md` (both >100 lines, per best practices). Corrected Phase 0 subagent history-mining paths to `<session-id>/subagents/agent-*.jsonl`. Documented the auto-activated hook behaviour in a new "Bundled hooks" section.

## [1.46.0] - 2026-04-11

### Added
- **claude-export-txt-better** v1.0.0: Fixes broken line wrapping in Claude Code exported `.txt` conversation files. Reconstructs tables, paragraphs, paths, and tool calls that were hard-wrapped at fixed column widths. Ships with an automated validation suite of 53 generic, file-agnostic checks. Triggers on export files with broken formatting or when the user mentions "fix export" / "fix conversation" / references a `YYYY-MM-DD-HHMMSS-*.txt` file. Bundled: `scripts/fix-claude-export.py`, `scripts/validate-claude-export-fix.py`, `evals/`.
- **douban-skill** v1.0.0: Exports and syncs Douban (豆瓣) book / movie / music / game collections to local CSV files via the reverse-engineered Frodo API. Supports full export and RSS incremental sync. No login, no cookies, no browser. Pre-flight user-ID validation and CSV output with UTF-8 BOM (Excel-compatible). Ships with a complete troubleshooting log of 7 tested scraping approaches and why each failed. Bundled: `scripts/douban-frodo-export.py`, `scripts/douban-rss-sync.py`, `references/troubleshooting.md`, `.gitleaks.toml` (allowlisting the public APK credentials).
- **terraform-skill** v1.0.0: Operational traps for Terraform provisioners, multi-environment isolation, and zero-to-deployment reliability. Every failure pattern documented caused a real incident. Covers provisioner timing races, SSH connection conflicts, DNS record duplication, volume permissions, database bootstrap gaps, snapshot cross-contamination, Cloudflare credential format errors, hardcoded domains in Caddyfiles/compose, and init-data-only-on-first-boot pitfalls. Organised as *exact error → root cause → copy-paste fix*. Bundled: `references/` with detailed remediation patterns.

### Changed
- Updated marketplace skills count from 44 to 47
- Updated marketplace version from 1.45.1 to 1.46.0
- Updated marketplace plugin entries from 47 to 50
- Updated README.md badges and skill listings (English and Chinese)
- Updated CLAUDE.md skill count (44 → 47) and plugin entry count (47 → 50)

## [1.45.1] - 2026-04-11

### Fixed
- **daymade-docs** v1.0.0 → v1.0.1: Narrowed the suite plugin source to `suites/daymade-docs/` so the installed cache contains only the documentation skills in the suite instead of a full repository snapshot.
- Moved the daymade-docs member skills under `suites/daymade-docs/` as their canonical source and repointed the corresponding single-skill plugin entries to those same directories.
- **doc-to-markdown** v2.1.0 → v2.1.1, **mermaid-tools** v1.0.1 → v1.0.2, **ppt-creator** v1.0.0 → v1.0.1, **pdf-creator** v1.3.1 → v1.3.2, **docs-cleaner** v1.0.0 → v1.0.1, and **meeting-minutes-taker** v1.1.0 → v1.1.1 now install from their suite canonical source paths.

### Changed
- Updated marketplace version from 1.45.0 to 1.45.1

## [1.45.0] - 2026-04-11

### Added
- **daymade-docs** v1.0.0: Documentation suite plugin that exposes `doc-to-markdown`, `mermaid-tools`, `pdf-creator`, `ppt-creator`, `docs-cleaner`, and `meeting-minutes-taker` under one namespace. This keeps the existing single-skill plugins available while providing `/daymade-docs:<skill-name>` slash commands for users who want a combined documentation workflow install.

### Changed
- Updated marketplace version from 1.44.0 to 1.45.0
- Updated README.md, README.zh-CN.md, and CLAUDE.md to document suite plugin architecture while preserving the existing single-skill plugin model.

## [1.44.0] - 2026-04-11

### Added
- **skill-creator** v1.7.1 → v1.7.2: Completeness pass for the `workflows/wrapper-skill/` methodology within its scope (zip-archive skill packages distributed via `npx skills add`). A fifth adversarial agent review audited the wrapper-skill workflow docs against the canonical `ima-copilot` implementation and surfaced 13 on-scope lessons that were implicit in the reference code but not elevated to named patterns in the workflow. This release lands all 13.
  - `patterns.md` install template: replaced the `<download and extract>` placeholder with a concrete defensive block covering `curl --fail` with HTTP-code branching, `wc -c` download-size sanity check rejecting suspiciously small archives before extraction, Node.js ≥18 numeric check (separate from `command -v node`), and a documented zero-agents-detected fallback policy (abort vs silent-skip vs default-to-claude-code, with the session's chosen answer named). Every defensive pattern has an accompanying "Lessons baked into this template" bullet explaining *why* it's there.
  - `patterns.md` known_issues template: added `**Why upstream probably hasn't fixed it**` as a required field (the field that keeps repair blocks load-bearing across upstream upgrades), added `Strategy skip` as a first-class documented third option (users on tolerant platforms may legitimately not want the repair and naming the skip path explicit prevents the "did I forget?" failure mode), and added detailed notes on the `[ -f ... ] && \` guard rationale, `sed -i.bak ... && command rm -f *.bak` BSD/GNU portability dance, and backup directory naming convention.
  - `patterns.md` diagnose template: added a new "Detection function return-code contract" subsection spelling out the required return codes for every post-repair state (untouched-good, untouched-broken, not-present, each Strategy-applied state, and the dual-state conflicted code). The dual-state code is the single hardest lesson from the ima-copilot session — a detection function that doesn't recognize it silently passes conflicted installs as healthy.
  - `patterns.md` diagnose template: added variadic `find_install` rationale explaining that agents whose home-directory layout has not stabilized (like OpenClaw) should be probed against an ordered list of candidate paths, and that designing the helper as variadic from day one avoids a painful refactor when a second candidate path becomes necessary.
  - `patterns.md` SKILL.md template: added explicit checklist for the description field (literal error strings from the session, tool name in every language the session used, self-disambiguation clause naming the upstream package to prevent wrapper-vs-upstream trigger fighting, symptoms that triggered the original session), plus a reference to the enforced 1024-character cap in `quick_validate.py:184`. Added "when in doubt → diagnose" as a recommended routing table default since diagnose is the only read-only entry point.
  - `patterns.md` credentials section: added explicit guidance that liveness checks must match on **response-body shape**, not just HTTP status. Many APIs return 200 OK with an error JSON body, and a naive `curl --fail` check will pass a credential that fails the first real operation.
  - `workflow.md` Step 5: expanded the install-script bullet list with prerequisite-check discipline (curl/unzip/npx loop plus separate Node.js ≥18 parse), download integrity defense in depth (HTTP code branching + size sanity), and the zero-agents fallback policy.
  - `workflow.md` Step 6: expanded the known_issues schema to include the `Why upstream probably hasn't fixed it` field and the `Strategy skip` branch, and documented the `sed -i.bak` cross-BSD/GNU portability rule alongside the existing `command cp/mv` guidance.
  - `workflow.md` Step 7: replaced the "returns OK / TRIGGERED / N/A / post-fix-state" shorthand with an explicit enumeration of the return-code contract, and added the variadic `find_install` guidance for agents with unstabilized layouts.

### Changed
- Updated marketplace version from 1.43.0 to 1.44.0

## [1.43.0] - 2026-04-11

### Fixed
- **ima-copilot** v1.0.0 → v1.0.1: Contract compliance and dogfood-driven fixes
  - `SKILL.md`, `references/known_issues.md`, `references/installation_flow.md`: removed hardcoded references to upstream version `1.1.2`. Install script keeps the version as an overridable default which is explicitly allowed by the architecture contract. Fixes a principle 6 (independent evolution) violation that would have forced a skill version bump on every upstream release.
  - `references/known_issues.md`: added `command` prefix to the `sed -i.bak` and `rm -f` commands in Strategy A repair block and to the `rm -f` command in Strategy A rollback, matching the contract's alias-safe requirement. Previously, a user shell with `alias rm='rm -i'` or `alias sed='sed -i'` would hang the repair on an interactive prompt.
  - `scripts/install_ima_skill.sh`: added a Node.js ≥18 preflight check. The `npx skills add` distribution path needs a modern Node runtime and the failure message on old Node is opaque.
  - `scripts/diagnose.sh`: `check_submodule` now recognizes and explicitly warns on the dual-state where both `SKILL.md` and `MODULE.md` exist simultaneously (can happen when a user switched repair strategies mid-session or restored a partial backup). Previously this reported clean while the install was in a conflicted state.
  - `scripts/search_fanout.py`: `rank_groups` now sorts tied hit counts by KB name for deterministic byte-identical output. Previously the tie-break depended on `concurrent.futures.ThreadPoolExecutor.map` completion order, which varied with network timing.
- **skill-creator** v1.7.0 → v1.7.1: Wrapper-skill workflow hardening from counter-review findings
  - `workflows/wrapper-skill/workflow.md` Step 2: added a "How to access the conversation" subsection with concrete guidance for three cases (same session / follow-up session / neither available) and an explicit "do not fabricate content" rule for the last case. Fresh agents were previously left to guess.
  - `workflows/wrapper-skill/workflow.md` Step 1: added an "AskUserQuestion fallback" subsection explaining that the consent requirement is the explicit user choice, not the specific tool name, and showing a plain-text fallback pattern for harnesses without `AskUserQuestion`.
  - `workflows/wrapper-skill/patterns.md`: added a new "Runtime-logic patterns shared across wrappers" section with three generalizable insights distilled from ima-copilot's `search_fanout.py` — **capability partitioning** (enumerate vs operate permission asymmetry with four-way result bucketing), **undocumented limit detection** (silent truncation heuristics for APIs that cap results without emitting pagination tokens), and **scoped liveness checks** (probe the lowest-privilege operation the skill actually performs, not the easiest API call). Each pattern includes example code, real-world examples across multiple APIs (GitHub, Slack, Notion, Google Drive), and a cross-reference to the ima-copilot implementation.
  - `workflows/wrapper-skill/verification_protocol.md`: restructured into Track 1 (session cross-reference for literal transcriptions) and Track 2 (smoke test / unit test for runtime logic). The previous "verification is not dogfood" dogma was too strict — it correctly applied to Track 1 files but wrongly exempted Track 2 runtime code from end-to-end testing. Track 2 files like `search_fanout.py` now have an explicit mandatory-smoke-test rule.

### Changed
- Updated marketplace version from 1.42.0 to 1.43.0

## [1.42.0] - 2026-04-11

### Added
- **skill-creator** v1.6.0 → v1.7.0: New `workflows/wrapper-skill/` specialized workflow for retrospectively distilling an install-and-debug session into a reusable companion skill for a third-party CLI tool
  - `workflows/wrapper-skill/workflow.md` — the retrospective distillation workflow with Step 2 conversation mining at its core (install flow, credential setup, bugs encountered and resolved, design decisions made, noise to discard)
  - `workflows/wrapper-skill/architecture_contract.md` — seven non-negotiable principles that every generated wrapper skill must follow (never vendor upstream, runtime repair over ship-time patches, explicit user consent for any upstream file modification, idempotent/reversible/alias-safe repair commands, teaching agents over humans, independent evolution from upstream, private preferences stay private)
  - `workflows/wrapper-skill/patterns.md` — copy-pasteable templates for SKILL.md, install script, diagnose script, known_issues registry, and credential setup, each annotated with the lessons baked in and cross-referenced to the canonical ima-copilot implementation
  - `workflows/wrapper-skill/verification_protocol.md` — post-generation verification focused on cross-referencing generated artifacts against the source conversation rather than re-running the full install (the install already ran in the source session)
  - `workflows/wrapper-skill/scripts/init_wrapper_skill.py` — bootstrap scaffold that creates the wrapper skill directory layout with placeholder markers pointing back at specific steps in the workflow
  - `SKILL.md` root entry now includes a "Specialized Workflow: Wrapper Skills for Third-Party CLI Tools" routing section between Capture Intent and Prior Art Research that redirects agents to the wrapper workflow when the signals apply
  - Canonical reference implementation: [`ima-copilot`](./ima-copilot) — the Tencent IMA wrapper that was the first product of this methodology, distilled during a real session whose lessons (shell alias bypass, root SKILL.md detection, realpath-based symlink dedup, idempotent reversible repairs) were captured in the patterns and propagated into this workflow

### Changed
- Updated marketplace version from 1.41.0 to 1.42.0

## [1.41.0] - 2026-04-11

### Added
- **New Skill**: ima-copilot v1.0.0 — One-stop companion and installer for the official Tencent IMA skill (ima.qq.com), with wrapper-layer architecture that never vendors upstream files
  - Zero-config installation to Claude Code, Codex, and OpenClaw via `npx skills add` ([vercel-labs/skills](https://github.com/vercel-labs/skills)) with auto-detection of installed agents and default symlink mode, so that a repair or upgrade applied once propagates automatically to every agent that shares the canonical install
  - XDG-style credential management at `~/.config/ima/{client_id, api_key}` with env-var fallback (`IMA_OPENAPI_CLIENTID` / `IMA_OPENAPI_APIKEY`)
  - Bundled `scripts/diagnose.sh` for read-only health check covering install presence, credential liveness, and known upstream issues with structured `✅/⚠️/❌` report
  - Bundled `scripts/install_ima_skill.sh` with version override via `--version` flag or `IMA_VERSION` env var
  - Bundled `scripts/search_fanout.py` for client-side cross-knowledge-base search with priority-based KB boosting, skip-list filtering, 100-result silent-truncation detection, and permission-denied KB partitioning (typical for subscribed KBs)
  - Detects and repairs ISSUE-001 (submodule SKILL.md files missing YAML frontmatter in upstream v1.1.2) with two user-selectable strategies: Strategy A (rename to `MODULE.md` and patch root references — respects upstream design intent) or Strategy B (prepend minimal frontmatter — smallest diff)
  - All repair commands are idempotent, reversible (with automatic timestamped backups to `/tmp/ima-copilot-backups/`), and use `command cp`/`command mv` to bypass interactive shell aliases
  - Personalization via `~/.config/ima/copilot.json` with `priority_kbs` and `skip_kbs` lists — template at `config-template/copilot.json.example` uses illustrative-only values so the skill ships with zero real KB names
  - Comprehensive reference documentation in `references/` covering installation flow, API key setup, known issues (source of truth for repairs), and search best practices
  - Never vendors, forks, or mirrors upstream files — every repair is a runtime instruction executed with explicit user consent

### Changed
- Updated marketplace skills/plugins count from 43 to 44
- Updated marketplace version from 1.40.1 to 1.41.0

## [1.39.0] - 2026-03-18

### Added
- **New Skill**: scrapling-skill v1.0.0 - Reliable Scrapling CLI installation, troubleshooting, and extraction workflows for HTML, Markdown, and text output
  - Bundled `diagnose_scrapling.py` script to verify CLI health, detect missing extras, inspect Playwright browser runtime, and run real smoke tests
  - Static-first workflow for choosing between `extract get`, `extract fetch`, and `stealthy-fetch`
  - Verified WeChat public article extraction pattern using `#js_content`
  - Verified recovery path for local TLS trust-store failures via `--no-verify`
  - Bundled troubleshooting reference covering extras, browser runtime, and output validation

### Changed
- **skill-creator** v1.5.0 → v1.5.1: Fixed `scripts/package_skill.py` so it works when invoked directly from the repository root instead of only via `python -m`
- **continue-claude-work** v1.1.0 → v1.1.1: Replaced newer Python-only type syntax in `extract_resume_context.py` so the script runs under the local `python3` environment
- Updated marketplace skills/plugins count from 42 to 43
- Updated marketplace version from 1.38.0 to 1.39.0
- Updated marketplace metadata description to include Scrapling CLI extraction workflows
- Updated README.md and README.zh-CN.md badges, installation commands, skill listings, use cases, quick links, and requirements
- Updated CLAUDE.md counts, version reference, and Available Skills list (added #43)

## [1.38.0] - 2026-03-07

### Added
- **New Skill**: continue-claude-work v1.1.0 - Recover local `.claude` session context and continue interrupted work without `claude --resume`
  - Bundled Python script (`extract_resume_context.py`) for one-call context extraction
  - Compact-boundary-aware extraction using `isCompactSummary` flag (highest-signal context from session compaction summaries)
  - Subagent workflow recovery — parses `subagents/` directory to report completed vs interrupted agents with last outputs
  - Session end reason detection — classifies clean exit, interrupted (ctrl-c), error cascade, or abandoned
  - Size-adaptive reading strategy based on file size and compaction count
  - Noise filtering — skips progress/queue-operation/api_error (37-53% of session lines)
  - Self-session exclusion, stale index fallback, ghost session warnings
  - MEMORY.md and session-memory integration, git workspace state fusion

### Changed
- **skill-creator** v1.4.1 → v1.5.0: SKILL.md rewrite, added eval benchmarking system (run_eval, run_loop, aggregate_benchmark), agents (analyzer, comparator, grader), eval-viewer, and improve_description script
- **transcript-fixer** v1.1.0 → v1.2.0: `--domain` defaults to all domains, added `get_domain_stats()`, cross-domain listing, and zero-match hints
- **tunnel-doctor** v1.3.0 → v1.4.0: Added Step 2C-1 for local vanity domain proxy interception, bundled `quick_diagnose.py` automated diagnostic script
- **pdf-creator** v1.0.0 → v1.1.0: Replaced Python `markdown` library with pandoc for MD→HTML conversion, removed `_ensure_list_spacing` workaround
- **github-contributor** v1.0.2 → v1.0.3: Fixed gh CLI field name (`stargazersCount` → `stargazerCount`), added Prerequisites section
- Updated marketplace skills/plugins count from 41 to 42
- Updated marketplace version from 1.37.0 to 1.38.0
- Updated README.md and README.zh-CN.md badges, installation commands, skill listings, use cases, quick links, and requirements
- Updated CLAUDE.md counts, version reference, and Available Skills list (added #42)

## [1.37.0] - 2026-03-02

### Added
- **New Skill**: excel-automation - Create formatted Excel files, parse complex xlsm models, and control Excel on macOS
  - Bundled scripts for workbook generation and complex XML/ZIP parsing
  - Bundled reference: formatting-reference.md for styles, number formats, and layout patterns
  - AppleScript control patterns with timeout-safe execution guidance
- **New Skill**: capture-screen - Programmatic macOS screenshot capture workflows
  - Bundled Swift script for CGWindowID discovery
  - AppleScript + screencapture multi-shot workflow patterns
  - Clear anti-pattern guidance for unreliable window ID methods
- Added missing `promptfoo-evaluation/scripts/metrics.py` referenced by skill examples

### Changed
- Updated marketplace skills/plugins count from 39 to 41
- Updated marketplace version from 1.36.0 to 1.37.0
- Bumped `promptfoo-evaluation` plugin version from 1.0.0 to 1.1.0 (skill content update + missing script fix)
- Updated README.md and README.zh-CN.md badges, installation commands, skill listings, use cases, quick links, and requirements
- Updated CLAUDE.md counts, version reference, and Available Skills list (added #40 and #41)

## [1.36.0] - 2026-03-02

### Added
- **New Skill**: financial-data-collector - Collect real financial data for US public companies via yfinance
  - Structured JSON output with market data, income statement, cash flow, balance sheet, WACC inputs, analyst estimates
  - Validation script with 9 checks (field completeness, cross-field consistency, sign conventions, NaN detection)
  - Reference docs: output-schema.md, yfinance-pitfalls.md (NaN years, field aliases, FCF definition mismatch)
  - NO FALLBACK principle: null for missing data, never default values

### Changed
- Updated marketplace skills count from 38 to 39
- Updated marketplace version from 1.35.0 to 1.36.0
- Updated README.md and README.zh-CN.md badges (skills count, version)
- Updated CLAUDE.md skills count and list

## [1.34.1] - 2026-02-23

### Changed
- Bumped marketplace metadata version from 1.34.0 to 1.34.1 in `.claude-plugin/marketplace.json`
- Added product-analysis entries to `README.md` and `README.zh-CN.md` and aligned skills count / version badges to 38 / 1.34.1
- Added product-analysis quick links in both READMEs and added use-case section in both READMEs
- Added **product-analysis** to `CLAUDE.md` and updated CLAUDE skill counts / version references to 38 and v1.34.1
- Bumped `skills-search` plugin version in `marketplace.json` from 1.0.0 to 1.1.0
- Bumped updated skill versions in `marketplace.json` after documentation updates:
  - `skill-creator`: 1.4.0 -> 1.4.1
  - `iOS-APP-developer`: 1.1.0 -> 1.1.1
  - `macos-cleaner`: 1.1.0 -> 1.1.1
  - `competitors-analysis`: 1.0.0 -> 1.0.1
  - `tunnel-doctor`: 1.2.0 -> 1.2.1
  - `product-analysis`: 1.0.0 -> 1.0.1

## [1.33.1] - 2026-02-17

### Changed
- **tunnel-doctor** v1.1.0 → v1.2.0: Add Layer 4 SSH ProxyCommand double tunnel diagnostics
  - New conflict layer: SSH ProxyCommand double tunneling causing intermittent git push/pull failures
  - New diagnostic step 2F: detect and fix redundant HTTP CONNECT tunnel when Shadowrocket TUN is active
  - Structural improvements per skill best practices:
    - Eliminate content duplication between SKILL.md and reference (73 → 27 lines)
    - Rename `proxy_fixes.md` → `proxy_conflict_reference.md` for clarity
    - Trim SKILL.md to 487 lines (under 500 limit)
    - Fix "apply all four" listing 5 items (separate anti-pattern warning)
    - Clarify Layer 4's relationship to Tailscale theme

## [1.33.0] - 2026-02-16

### Changed
- **tunnel-doctor** v1.0.0 → v1.1.0: Added remote development SOP with SSH tunnel and Makefile patterns
  - New SOP section: proxy-safe Makefile pattern (`--noproxy localhost` for all health checks)
  - New SOP section: SSH tunnel Makefile targets (`tunnel`/`tunnel-bg` with autossh)
  - New SOP section: multi-port tunnel configuration
  - New SOP section: SSH non-login shell setup (deduped, references proxy_fixes.md)
  - New SOP section: end-to-end workflow (first-time setup + daily workflow)
  - New SOP section: pre-flight checklist (10 verification items)
  - New diagnostic step 2D: auth redirect fix via SSH local port forwarding
  - New diagnostic step 2E: localhost proxy interception in Makefiles/scripts
  - Fixed step ordering: 2A→2B→2C→2D→2E (was 2A→2C→2D→2E→2B)
  - Fixed description to third-person voice per skill best practices
  - Replaced hardcoded IP with `<tailscale-ip>` placeholder (5 occurrences)
  - Added SSH non-login shell pitfall to references/proxy_fixes.md
  - Added localhost proxy interception section to references/proxy_fixes.md
  - Strengthened `--data-binary` vs `-d` warning in references/proxy_fixes.md
  - New keywords: ssh-tunnel, autossh, makefile, remote-development
- Updated marketplace version from 1.32.1 to 1.33.0

## [1.32.0] - 2026-02-09

### Added
- **New Skill**: windows-remote-desktop-connection-doctor - Diagnose AVD/W365 connection quality issues
  - 5-step diagnostic workflow for transport protocol analysis
  - UDP Shortpath vs WebSocket detection and root cause identification
  - VPN/proxy interference detection (ShadowRocket, Clash, Tailscale)
  - Windows App log parsing for STUN/TURN/ICE negotiation failures
  - ISP UDP restriction testing and Chinese ISP-specific guidance
  - Bundled references: windows_app_log_analysis.md, avd_transport_protocols.md

### Changed
- Updated marketplace skills count from 36 to 37
- Updated marketplace version from 1.31.0 to 1.32.0
- Updated README.md badges (skills count, version)
- Updated README.md to include windows-remote-desktop-connection-doctor in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include windows-remote-desktop-connection-doctor in skills listing
- Updated CLAUDE.md skills count from 36 to 37

## [1.31.0] - 2026-02-07

### Added
- **New Skill**: tunnel-doctor - Diagnose and fix Tailscale + proxy/VPN route conflicts
  - 6-step diagnostic workflow for route conflict detection and resolution
  - Shadowrocket, Clash, Surge proxy tool fix guides
  - Tailscale SSH ACL configuration (check vs accept)
  - WSL snap vs apt Tailscale installation guidance
  - Bundled references: proxy_fixes.md with per-tool instructions
  - Shadowrocket config API documentation

### Changed
- Updated marketplace skills count from 35 to 36
- Updated marketplace version from 1.30.0 to 1.31.0
- Updated README.md badges (skills count, version)
- Updated README.md to include tunnel-doctor in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include tunnel-doctor in skills listing
- Updated CLAUDE.md skills count from 35 to 36

## [1.30.0] - 2026-01-29

### Added
- **New Skill**: competitors-analysis - Evidence-based competitor tracking and analysis
  - Pre-analysis checklist to ensure repositories are cloned locally
  - Forbidden patterns to prevent assumptions and speculation
  - Required patterns for source citation (file:line_number)
  - Tech stack analysis guides for Node.js, Python, Rust projects
  - Directory structure conventions for competitor tracking
  - Bundled references: profile_template.md, analysis_checklist.md
  - Management script: update-competitors.sh (clone/pull/status)

### Changed
- Updated marketplace skills count from 34 to 35
- Updated marketplace version from 1.29.0 to 1.30.0
- Updated README.md badges (skills count, version)
- Updated README.md to include competitors-analysis in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include competitors-analysis in skills listing
- Updated CLAUDE.md skills count from 34 to 35
- Added competitors-analysis use case section to README.md
- Added competitors-analysis use case section to README.zh-CN.md

## [1.29.0] - 2026-01-29

### Added
- **Enhanced Skill**: skill-creator v1.4.0 - Comprehensive YAML frontmatter documentation
  - Complete YAML frontmatter reference table with all available fields
  - `context: fork` documentation - critical for subagent-accessible skills
  - Invocation control comparison table showing behavior differences
  - `$ARGUMENTS` placeholder explanation with usage examples
  - `allowed-tools` wildcard syntax examples (`Bash(git *)`, `Bash(npm *)`, `Bash(docker compose *)`)
  - `hooks` field inline example for pre-invoke configuration
  - Updated init_skill.py template with commented optional fields

### Changed
- Updated marketplace version from 1.28.0 to 1.29.0
- Updated skill-creator plugin version from 1.3.0 to 1.4.0

### Contributors
- [@costa-marcello](https://github.com/costa-marcello) - PR #6: Initial frontmatter documentation

## [1.28.0] - 2026-01-25

### Added
- **Enhanced Skill**: meeting-minutes-taker v1.1.0 - Speaker identification and pre-processing pipeline
  - Speaker identification via feature analysis (word count, segment count, filler ratio, speaking style)
  - Context file template (`references/context_file_template.md`) for team directory mapping
  - Intelligent file naming pattern: `YYYY-MM-DD-<topic>-<type>.md`
  - Pre-processing pipeline integration with markdown-tools and transcript-fixer
  - Transcript quality assessment workflow

### Changed
- Updated marketplace version from 1.27.0 to 1.28.0
- Updated meeting-minutes-taker plugin version from 1.0.0 to 1.1.0

## [1.27.0] - 2026-01-25

### Added
- **Enhanced Skill**: markdown-tools v1.2.0 - Multi-tool orchestration with Heavy Mode
  - Dual mode architecture: Quick Mode (fast) and Heavy Mode (best quality)
  - New `convert.py` - Main orchestrator with tool selection matrix
  - New `merge_outputs.py` - Segment-level multi-tool output merger
  - New `validate_output.py` - Quality validation with HTML reports
  - Enhanced `extract_pdf_images.py` - Image extraction with metadata (page, position, dimensions)
  - PyMuPDF4LLM integration for LLM-optimized PDF conversion
  - pandoc integration for DOCX/PPTX structure preservation
  - Quality metrics: text retention, table retention, image retention
  - New references: heavy-mode-guide.md, tool-comparison.md

### Changed
- Updated marketplace version from 1.26.0 to 1.27.0
- Updated markdown-tools plugin version from 1.1.0 to 1.2.0

## [1.26.0] - 2026-01-25

### Added
- **New Skill**: deep-research - Format-controlled research reports with evidence mapping
  - Report spec and format contract workflow
  - Multi-pass parallel drafting with UNION merge
  - Evidence table with source quality rubric
  - Citation verification and conflict handling
  - Bundled references: report template, formatting rules, research plan checklist, source quality rubric, completeness checklist

### Changed
- Updated marketplace skills count from 33 to 34
- Updated marketplace version from 1.25.0 to 1.26.0
- Updated README.md badges (skills count, version)
- Updated README.md to include deep-research in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include deep-research in skills listing
- Updated CLAUDE.md skills count from 33 to 34
- Added deep-research use case section to README.md
- Added deep-research use case section to README.zh-CN.md
- Added deep-research documentation quick link to README.md
- Added deep-research documentation quick link to README.zh-CN.md

## [1.25.0] - 2026-01-24

### Added
- **New Skill**: meeting-minutes-taker - Transform meeting transcripts into structured minutes
  - Multi-pass parallel generation with UNION merge strategy
  - Evidence-based recording with speaker quotes
  - Mermaid diagrams for architecture discussions
  - Iterative human-in-the-loop refinement workflow
  - Bundled references: template and completeness checklist

### Changed
- Updated marketplace skills count from 32 to 33
- Updated marketplace version from 1.24.0 to 1.25.0
- Updated skill-creator to v1.3.0:
  - Added Step 5: Sanitization Review (Optional)
  - New references/sanitization_checklist.md with 8 categories of content to sanitize
  - Automated grep scan commands for detecting sensitive content
  - 3-phase sanitization process and completion checklist

## [1.24.0] - 2026-01-22

### Added
- **New Skill**: claude-skills-troubleshooting - Diagnose and resolve Claude Code plugin and skill configuration issues
  - Plugin installation and enablement debugging
  - installed_plugins.json vs settings.json enabledPlugins diagnosis
  - Marketplace cache freshness detection
  - Plugin state architecture documentation
  - Bundled diagnostic script (diagnose_plugins.py)
  - Batch enable script for missing plugins (enable_all_plugins.py)
  - Known GitHub issues tracking (#17832, #19696, #17089, #13543, #16260)
  - Skills vs Commands architecture explanation

### Changed
- Updated marketplace skills count from 31 to 32
- Updated marketplace version from 1.23.0 to 1.24.0
- Updated README.md badges (skills count, version)
- Updated README.md to include claude-skills-troubleshooting in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include claude-skills-troubleshooting in skills listing
- Updated CLAUDE.md skills count from 31 to 32
- Added claude-skills-troubleshooting use case section to README.md
- Added claude-skills-troubleshooting use case section to README.zh-CN.md

## [1.23.0] - 2026-01-22

### Added
- **New Skill**: i18n-expert - Complete internationalization/localization setup and auditing for UI codebases
  - Library selection and setup (react-i18next, next-intl, vue-i18n)
  - Key architecture and locale file organization (JSON, YAML, PO, XLIFF)
  - Translation generation strategy (AI, professional, manual)
  - Routing and language detection/switching
  - SEO and metadata localization
  - RTL support for applicable locales
  - Key parity validation between en-US and zh-CN
  - Pluralization and formatting validation
  - Error code mapping to localized messages
  - Bundled i18n_audit.py script for key usage extraction
  - Scope inputs: framework, existing i18n state, target locales, translation quality needs

### Changed
- Updated marketplace skills count from 30 to 31
- Updated marketplace version from 1.22.0 to 1.23.0
- Updated README.md badges (skills count, version)
- Updated README.md to include i18n-expert in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include i18n-expert in skills listing
- Updated CLAUDE.md skills count from 30 to 31
- Added i18n-expert use case section to README.md
- Added i18n-expert use case section to README.zh-CN.md

### Changed
- None

### Deprecated
- None

### Removed
- None

### Fixed
- None

### Security
- None

## [1.22.0] - 2026-01-15

### Added
- **New Skill**: skill-reviewer - Reviews and improves Claude Code skills against official best practices
  - Self-review mode: Validate your own skills before publishing
  - External review mode: Evaluate others' skill repositories
  - Auto-PR mode: Fork, improve, and submit PRs to external repos
  - Automated validation via bundled skill-creator scripts
  - Evaluation checklist covering frontmatter, instructions, and resources
  - Additive-only contribution principle (never delete files)
  - PR guidelines with tone recommendations and templates
  - Self-review checklist for respect verification
  - References: evaluation_checklist.md, pr_template.md, marketplace_template.json
  - Auto-install dependencies: automatically installs skill-creator if missing

- **New Skill**: github-contributor - Strategic guide for becoming an effective GitHub contributor
  - Four contribution types: Documentation, Code Quality, Bug Fixes, Features
  - Project selection criteria with red flags
  - PR excellence workflow with templates
  - Reputation building ladder (Documentation → Bug Fixes → Features → Maintainer)
  - GitHub CLI command reference
  - Conventional commit message format
  - Common mistakes and best practices
  - References: pr_checklist.md, project_evaluation.md, communication_templates.md

### Changed
- Updated marketplace skills count from 28 to 30
- Updated marketplace version from 1.21.1 to 1.22.0
- Updated README.md badges (skills count: 30, version: 1.22.0)
- Updated README.md to include skill-reviewer in skills listing
- Updated README.md to include github-contributor in skills listing
- Updated README.zh-CN.md badges (skills count: 30, version: 1.22.0)
- Updated README.zh-CN.md to include skill-reviewer in skills listing
- Updated README.zh-CN.md to include github-contributor in skills listing
- Updated CLAUDE.md skills count from 28 to 30
- Added skill-reviewer use case section to README.md
- Added github-contributor use case section to README.md
- Added skill-reviewer use case section to README.zh-CN.md
- Added github-contributor use case section to README.zh-CN.md

## [1.21.1] - 2026-01-11

### Changed
- **Updated Skill**: macos-cleaner v1.0.0 → v1.1.0 - Major improvements based on real-world usage
  - Added "Value Over Vanity" principle: Goal is identifying truly useless items, not maximizing cleanup numbers
  - Added "Network Environment Awareness": Consider slow internet (especially in China) when recommending cache deletion
  - Added "Impact Analysis Required": Every cleanup recommendation must explain consequences
  - Added comprehensive "Anti-Patterns" section: What NOT to delete (Xcode DerivedData, npm _cacache, uv cache, Playwright, iOS DeviceSupport, etc.)
  - Added "Multi-Layer Deep Exploration" guide: Complete tmux + Mole TUI navigation workflow
  - Added "High-Quality Report Template": Proven 3-tier classification report format (🟢/🟡/🔴)
  - Added "Report Quality Checklist": 8-point verification before presenting findings
  - Added explicit prohibition of `docker volume prune -f` - must confirm per-project
  - Updated safety principles to emphasize cache value over cleanup metrics

## [1.21.0] - 2026-01-11

### Added
- **New Skill**: macos-cleaner - Intelligent macOS disk space analysis and cleanup with safety-first philosophy
  - Smart analysis of system caches, application caches, logs, and temporary files
  - Application remnant detection (orphaned data from uninstalled apps)
  - Large file discovery with automatic categorization (videos, archives, databases, disk images)
  - Development environment cleanup (Docker, Homebrew, npm, pip, Git repositories)
  - Interactive safe deletion with user confirmation at every step
  - Risk-level categorization (🟢 Safe / 🟡 Caution / 🔴 Keep)
  - Integration guide for Mole visual cleanup tool
  - Before/after cleanup reports with space recovery metrics
  - Bundled scripts: `analyze_caches.py`, `analyze_dev_env.py`, `analyze_large_files.py`, `find_app_remnants.py`, `safe_delete.py`, `cleanup_report.py`
  - Comprehensive safety rules and cleanup target documentation
  - Time Machine backup recommendations for large deletions
  - Professional user experience: analyze first, explain thoroughly, execute with confirmation

### Changed
- Updated marketplace skills count from 27 to 28
- Updated marketplace version from 1.20.0 to 1.21.0
- Updated README.md badges (skills count: 28, version: 1.21.0)
- Updated README.md to include macos-cleaner in skills listing
- Updated README.zh-CN.md badges (skills count: 28, version: 1.21.0)
- Updated README.zh-CN.md to include macos-cleaner in skills listing
- Updated CLAUDE.md skills count from 27 to 28
- Added macos-cleaner use case section to README.md
- Added macos-cleaner use case section to README.zh-CN.md

## [1.20.0] - 2026-01-11

### Added
- **New Skill**: twitter-reader - Fetch Twitter/X post content using Jina.ai API
  - Bypass JavaScript restrictions without authentication
  - Retrieve tweet content including author, timestamp, post text, images, and thread replies
  - Support for individual posts or batch fetching from x.com or twitter.com URLs
  - Bundled scripts: `fetch_tweet.py` (Python) and `fetch_tweets.sh` (Bash)
  - Environment variable configuration for secure API key management
  - Supports both x.com and twitter.com URL formats

### Changed
- Updated marketplace skills count from 26 to 27
- Updated marketplace version from 1.19.0 to 1.20.0
- Updated README.md badges (skills count: 27, version: 1.20.0)
- Updated README.md to include twitter-reader in skills listing
- Updated README.zh-CN.md badges (skills count: 27, version: 1.20.0)
- Updated README.zh-CN.md to include twitter-reader in skills listing
- Updated CLAUDE.md skills count from 26 to 27
- Added twitter-reader use case section to README.md
- Added twitter-reader use case section to README.zh-CN.md

### Security
- **twitter-reader**: Implemented secure API key management using environment variables
  - Removed hardcoded API keys from all scripts and documentation
  - Added validation for JINA_API_KEY environment variable
  - Enforced HTTPS-only URLs in Python script

## [1.18.2] - 2026-01-05

### Changed
- **claude-md-progressive-disclosurer**: Enhanced workflow with safety and verification features
  - Added mandatory backup step (Step 0) before any modifications
  - Added pre-execution verification checklist (Step 3.5) to prevent information loss
  - Added post-optimization testing (Step 5) for discoverability validation
  - Added exception criteria for size guidelines (safety-critical, high-frequency, security-sensitive)
  - Added project-level vs user-level CLAUDE.md guidance
  - Updated references/progressive_disclosure_principles.md with verification methods
- Updated claude-md-progressive-disclosurer plugin version from 1.0.0 to 1.0.1

## [1.18.1] - 2025-12-28

### Changed
- **markdown-tools**: Enhanced with PDF image extraction capability
  - Added `extract_pdf_images.py` script using PyMuPDF
  - Refactored SKILL.md for clearer workflow documentation
  - Updated installation instructions to use `markitdown[pdf]` extra
- Updated marketplace version from 1.18.0 to 1.18.1

## [1.18.0] - 2025-12-20

### Added
- **New Skill**: pdf-creator - Convert markdown to PDF with Chinese font support (WeasyPrint)
- **New Skill**: claude-md-progressive-disclosurer - Optimize CLAUDE.md with progressive disclosure
- **New Skill**: promptfoo-evaluation - Promptfoo-based LLM evaluation workflows
- **New Skill**: iOS-APP-developer - iOS app development with XcodeGen, SwiftUI, and SPM

### Changed
- Updated marketplace skills count from 23 to 25
- Updated marketplace version from 1.16.0 to 1.18.0
- Updated README/README.zh-CN badges, skill lists, use cases, quick links, and requirements
- Updated QUICKSTART docs to clarify marketplace install syntax and remove obsolete links
- Updated CLAUDE.md skill counts and added the new skills to the list

## [1.16.0] - 2025-12-11

### Added
- **New Skill**: skills-search - CCPM registry search and management
  - Search for Claude Code skills in the CCPM registry
  - Install skills by name with `ccpm install <skill-name>`
  - List installed skills with `ccpm list`
  - Get detailed skill information with `ccpm info <skill-name>`
  - Uninstall skills with `ccpm uninstall <skill-name>`
  - Install skill bundles (web-dev, content-creation, developer-tools)
  - Supports multiple installation formats (registry, GitHub owner/repo, full URLs)
  - Troubleshooting guidance for common issues

### Changed
- Updated marketplace skills count from 22 to 23
- Updated marketplace version from 1.15.0 to 1.16.0
- Updated README.md badges (skills count: 23, version: 1.16.0)
- Updated README.md to include skills-search in skills listing (skill #20)
- Updated README.zh-CN.md badges (skills count: 23, version: 1.16.0)
- Updated README.zh-CN.md to include skills-search with Chinese translation
- Updated CLAUDE.md skills count from 22 to 23
- Added skills-search use case section to README.md
- Added skills-search use case section to README.zh-CN.md
- Added installation command for skills-search
- Enhanced marketplace metadata description to include CCPM skill management

## [1.13.0] - 2025-12-09

### Added
- **New Skill**: claude-code-history-files-finder - Session history recovery for Claude Code
  - Search sessions by keywords with frequency ranking
  - Recover deleted files from Write tool calls with automatic deduplication
  - Analyze session statistics (message counts, tool usage, file operations)
  - Batch operations for processing multiple sessions
  - Streaming processing for large session files (>100MB)
  - Bundled scripts: analyze_sessions.py, recover_content.py
  - Bundled references: session_file_format.md, workflow_examples.md
  - Follows Anthropic skill authoring best practices (third-person description, imperative style, progressive disclosure)

- **New Skill**: docs-cleaner - Documentation consolidation
  - Consolidate redundant documentation while preserving valuable content
  - Redundancy detection for overlapping documents
  - Smart merging with structure preservation
  - Validation for consolidated documents

### Changed
- Updated marketplace skills count from 18 to 20
- Updated marketplace version from 1.11.0 to 1.13.0
- Updated README.md badges (skills count: 20, version: 1.13.0)
- Updated README.md to include claude-code-history-files-finder in skills listing (skill 18)
- Updated README.md to include docs-cleaner in skills listing (skill 19)
- Updated README.zh-CN.md badges (skills count: 20, version: 1.13.0)
- Updated README.zh-CN.md to include both new skills with Chinese translations
- Updated CLAUDE.md skills count from 18 to 20
- Added session history recovery use case section to README.md
- Added documentation maintenance use case section to README.md
- Added corresponding use case sections to README.zh-CN.md
- Added installation commands for both new skills
- Added quick links for documentation references
- **skill-creator** v1.2.0 → v1.2.1: Added cache directory warning
  - Added critical warning about not editing skills in `~/.claude/plugins/cache/`
  - Explains that cache is read-only and changes are lost on refresh
  - Provides correct vs wrong path examples
- **transcript-fixer** v1.0.0 → v1.1.0: Enhanced with Chinese domain support and AI fallback
  - Added Chinese/Japanese/Korean character support for domain names (e.g., `火星加速器`, `具身智能`)
  - Added `[CLAUDE_FALLBACK]` signal when GLM API is unavailable for Claude Code to take over
  - Added Prerequisites section requiring `uv` for Python execution
  - Added Critical Workflow section for dictionary iteration best practices
  - Added AI Fallback Strategy section with manual correction guidance
  - Added Database Operations section with schema reference requirement
  - Added Stages table for quick reference (Dictionary → AI → Full pipeline)
  - Added new bundled script: `ensure_deps.py` for shared virtual environment
  - Added new bundled references: `database_schema.md`, `iteration_workflow.md`
  - Updated domain validation from whitelist to pattern matching
  - Updated tests for Chinese domain names and security bypass attempts

## [youtube-downloader-1.1.0] - 2025-11-19

### Changed
- **youtube-downloader** v1.0.0 → v1.1.0: Enhanced with HLS streaming support
  - Added comprehensive HLS stream download support (m3u8 format)
  - Added support for platforms like Mux, Vimeo, and other HLS-based services
  - Added ffmpeg-based download workflow with authentication headers
  - Added Referer header configuration for protected streams
  - Added protocol whitelisting guidance
  - Added separate audio/video stream handling and merging workflow
  - Added troubleshooting for 403 Forbidden errors
  - Added troubleshooting for yt-dlp stuck on cookie extraction
  - Added troubleshooting for expired signatures
  - Added performance tips (10-15x realtime speed)
  - Updated skill description to include HLS streams and authentication
  - Updated "When to Use" triggers to include m3u8/HLS downloads
  - Updated Overview to mention multiple streaming platforms

## [1.11.0] - 2025-11-16

### Added
- **New Skill**: prompt-optimizer - Transform vague prompts into precise EARS specifications
  - EARS (Easy Approach to Requirements Syntax) transformation methodology
  - 6-step optimization workflow: analyze, transform, identify theories, extract examples, enhance, present
  - 5 EARS sentence patterns (ubiquitous, event-driven, state-driven, conditional, unwanted behavior)
  - Domain theory grounding with 10+ categories (productivity, UX, gamification, learning, e-commerce, security)
  - 40+ industry frameworks mapped to use cases (GTD, BJ Fogg, Gestalt, AIDA, Zero Trust, etc.)
  - Role/Skills/Workflows/Examples/Formats prompt enhancement framework
  - Advanced optimization techniques (multi-stakeholder, non-functional requirements, complex logic)
  - Bundled references: ears_syntax.md, domain_theories.md, examples.md
  - Complete transformation examples (procrastination app, e-commerce, learning platform, password reset)
  - Progressive disclosure pattern (metadata → SKILL.md → bundled resources)

### Changed
- Updated marketplace skills count from 17 to 18
- Updated marketplace version from 1.10.0 to 1.11.0
- Updated README.md badges (skills count, version)
- Updated README.md to include prompt-optimizer in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include prompt-optimizer in skills listing
- Updated CLAUDE.md skills count from 17 to 18
- Added prompt-optimizer use case section to README.md
- Added prompt-optimizer use case section to README.zh-CN.md
- Enhanced marketplace metadata description to include prompt optimization capability
- **prompt-optimizer v1.1.0**: Improved skill following Anthropic best practices
  - Reduced SKILL.md from 369 to 195 lines (47% reduction) using progressive disclosure
  - Added new reference: advanced_techniques.md (325 lines) for multi-stakeholder, non-functional, and complex logic patterns
  - Added 4th complete example (password reset security) to examples.md
  - Added attribution to 阿星AI工作室 (A-Xing AI Studio) for EARS methodology inspiration
  - Enhanced reference loading guidance with specific triggers for each file
  - Improved conciseness and clarity following skill authoring best practices

## [1.10.0] - 2025-11-10

### Added
- **New Skill**: qa-expert - Comprehensive QA testing infrastructure with autonomous LLM execution
  - One-command QA project initialization with complete templates and tracking CSVs
  - Google Testing Standards implementation (AAA pattern, 90% coverage targets)
  - Autonomous LLM-driven test execution via master prompts (100x speed improvement)
  - OWASP Top 10 security testing framework (90% coverage target)
  - Bug tracking with P0-P4 severity classification
  - Quality gates enforcement (100% execution, ≥80% pass rate, 0 P0 bugs, ≥80% code coverage)
  - Ground Truth Principle for preventing doc/CSV sync issues
  - Day 1 onboarding guide for new QA engineers (5-hour timeline)
  - Bundled scripts: `init_qa_project.py`, `calculate_metrics.py`
  - Bundled references: master_qa_prompt.md, google_testing_standards.md, day1_onboarding.md, ground_truth_principle.md, llm_prompts_library.md
  - Complete test case and bug tracking templates
  - 30+ ready-to-use LLM prompts for QA tasks
  - Progressive disclosure pattern (metadata → SKILL.md → bundled resources)

### Changed
- Updated marketplace skills count from 16 to 17
- Updated marketplace version from 1.9.0 to 1.10.0
- Updated README.md badges (skills count, version)
- Updated README.md to include qa-expert in skills listing
- Updated CLAUDE.md skills count from 16 to 17
- Added qa-expert use case section to README.md
- Enhanced marketplace metadata description to include QA testing capability

## [1.9.0] - 2025-10-29

### Added
- **New Skill**: video-comparer - Video comparison and quality analysis tool
  - Compare original and compressed videos with interactive HTML reports
  - Calculate quality metrics (PSNR, SSIM) for compression analysis
  - Generate frame-by-frame visual comparisons with three viewing modes (slider, side-by-side, grid)
  - Extract video metadata (codec, resolution, bitrate, duration, file size)
  - Multi-platform FFmpeg installation instructions (macOS, Linux, Windows)
  - Bundled Python script: `compare.py` with security features (path validation, resource limits)
  - Comprehensive reference documentation (video metrics interpretation, FFmpeg commands, configuration)
  - Self-contained HTML output with embedded frames (no server required)

### Changed
- Updated marketplace skills count from 15 to 16
- Updated marketplace version from 1.8.0 to 1.9.0
- Updated README.md badges (skills count, version)
- Updated README.md to include video-comparer in skills listing
- Updated CLAUDE.md skills count from 15 to 16
- Added video-comparer use case section to README.md
- Added FFmpeg to requirements section

## [1.6.0] - 2025-10-26

### Added
- **New Skill**: youtube-downloader - YouTube video and audio downloading with yt-dlp
  - Download YouTube videos and playlists with robust error handling
  - Audio-only download with MP3 conversion
  - Android client workaround for nsig extraction issues (automatic)
  - Format listing and custom format selection
  - Network error handling for proxy/restricted environments
  - Bundled Python script: `download_video.py` with yt-dlp availability check
  - Comprehensive troubleshooting documentation for common yt-dlp issues
  - Demo tape file and GIF showing download workflow

### Changed
- Updated marketplace.json from 12 to 13 skills
- Updated marketplace version from 1.5.0 to 1.6.0
- Enhanced marketplace metadata description to include YouTube downloading capability
- Updated CLAUDE.md with complete 13-skill listing
- Updated CLAUDE.md marketplace version to v1.6.0
- Updated README.md to reflect 13 available skills
- Updated README.md badges (skills count, version)
- Added youtube-downloader to manual installation instructions
- Added youtube-downloader use case section in README
- Added youtube-downloader to documentation quick links
- Added yt-dlp to requirements section

## [1.5.0] - 2025-10-26

### Added
- **New Skill**: ppt-creator - Professional presentation creation with dual-path PPTX generation
  - Pyramid Principle structure (conclusion → reasons → evidence)
  - Assertion-evidence slide framework
  - Automatic data synthesis and chart generation (matplotlib)
  - Dual-path PPTX creation (Marp CLI + document-skills:pptx)
  - Complete orchestration: content → data → charts → PPTX with charts
  - 45-60 second speaker notes per slide
  - Quality scoring with auto-refinement (target: 75/100)

### Changed
- Updated marketplace.json from 11 to 12 skills
- Updated marketplace version from 1.4.0 to 1.5.0

## [1.4.0] - 2025-10-25

### Added
- **New Skill**: cloudflare-troubleshooting - API-driven Cloudflare diagnostics and troubleshooting
  - Systematic investigation of SSL errors, DNS issues, and redirect loops
  - Direct Cloudflare API integration for evidence-based troubleshooting
  - Bundled Python scripts: `check_cloudflare_config.py` and `fix_ssl_mode.py`
  - Comprehensive reference documentation (SSL modes, API overview, common issues)
- **New Skill**: ui-designer - Design system extraction from UI mockups and screenshots
  - Automated design system extraction (colors, typography, spacing)
  - Design system documentation generation
  - PRD and implementation prompt creation
  - Bundled templates: design-system.md, vibe-design-template.md, app-overview-generator.md
- Enhanced `.gitignore` patterns for archives, build artifacts, and documentation files

### Changed
- Updated marketplace.json from 9 to 11 skills
- Updated marketplace version from 1.3.0 to 1.4.0
- Enhanced marketplace metadata description to include new capabilities
- Updated CLAUDE.md with complete 11-skill listing
- Updated README.md to reflect 11 available skills
- Updated README.zh-CN.md to reflect 11 available skills

## [1.3.0] - 2025-10-23

### Added
- **New Skill**: cli-demo-generator - Professional CLI demo generation with VHS automation
  - Automated demo generation from command lists
  - Batch processing with YAML/JSON configs
  - Interactive recording with asciinema
  - Smart timing and multiple output formats
- Comprehensive improvement plan with 5 implementation phases
- Automated installation scripts for macOS/Linux (`install.sh`) and Windows (`install.ps1`)
- Complete Chinese translation (README.zh-CN.md)
- Quick start guides in English and Chinese (QUICKSTART.md, QUICKSTART.zh-CN.md)
- VHS demo infrastructure for all skills
- Demo tape files for skill-creator, github-ops, and markdown-tools
- Automated demo generation script (`demos/generate_all_demos.sh`)
- GitHub issue templates (bug report, feature request)
- GitHub pull request template
- FAQ section in README
- Table of Contents in README
- Enhanced badges (Claude Code version, PRs welcome, maintenance status)
- Chinese user guide with CC-Switch recommendation
- Language switcher badges (English/简体中文)

### Changed
- **BREAKING**: Restructured README.md to highlight skill-creator as essential meta-skill
- Moved skill-creator from position #7 to featured "Essential Skill" section
- Updated CLAUDE.md with new priorities and installation commands
- Enhanced documentation navigation and discoverability
- Improved README structure with better organization

### Removed
- skill-creator from "Other Available Skills" numbered list (now featured separately)

## [1.2.0] - 2025-10-22

### Added
- llm-icon-finder skill for AI/LLM brand icons
- Comprehensive marketplace structure with 8 skills
- Professional documentation for all skills
- CONTRIBUTING.md with quality standards
- INSTALLATION.md with detailed setup instructions

### Changed
- Updated marketplace.json to v1.2.0
- Enhanced skill descriptions and metadata

## [1.1.0] - 2025-10-15

### Added
- skill-creator skill with initialization, validation, and packaging scripts
- repomix-unmixer skill for extracting repomix packages
- teams-channel-post-writer skill for Teams communication
- Enhanced documentation structure

### Changed
- Improved skill quality standards
- Updated all skill SKILL.md files with consistent formatting

## [1.0.0] - 2025-10-08

### Added
- Initial release of Claude Code Skills Marketplace
- github-ops skill for GitHub operations
- markdown-tools skill for document conversion
- mermaid-tools skill for diagram generation
- statusline-generator skill for Claude Code customization
- MIT License
- README.md with comprehensive documentation
- Individual skill documentation (SKILL.md files)

---

## Version Numbering

We use [Semantic Versioning](https://semver.org/):

- **MAJOR** version when you make incompatible API changes
- **MINOR** version when you add functionality in a backward compatible manner
- **PATCH** version when you make backward compatible bug fixes

## Release Process

1. Update version in `.claude-plugin/marketplace.json`
2. Update CHANGELOG.md with changes
3. Update README.md version badge
4. Create git tag: `git tag -a v1.x.x -m "Release v1.x.x"`
5. Push tag: `git push origin v1.x.x`

[Unreleased]: https://github.com/daymade/claude-code-skills/compare/v1.10.0...HEAD
[1.10.0]: https://github.com/daymade/claude-code-skills/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/daymade/claude-code-skills/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/daymade/claude-code-skills/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/daymade/claude-code-skills/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/daymade/claude-code-skills/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/daymade/claude-code-skills/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/daymade/claude-code-skills/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/daymade/claude-code-skills/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/daymade/claude-code-skills/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/daymade/claude-code-skills/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/daymade/claude-code-skills/releases/tag/v1.0.0
