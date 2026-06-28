// Dynamic Workflow: 6-dimension health check for a Claude Code skills marketplace repo.
//
// HOW TO RUN (see SKILL.md): Read this file, then launch it with the Workflow tool via the
// `script` parameter (inline) so there is no path-resolution dependency on the installed
// skill location. Pass a pre-run scout result as args for accurate per-agent context:
//
//   Workflow({ script: <contents of this file>, args: { repo: "owner/name", scale: "<one-liner>" } })
//
// args is OPTIONAL — if omitted, each inspector self-discovers the repo scale first.
// This is READ-ONLY: inspectors must not modify files, comment on PRs/issues, or push.

export const meta = {
  name: 'marketplace-health-check',
  description: 'Full 6-dimension health check of a Claude Code skills marketplace repo: code/scripts, docs/SSOT, security/PII, open PRs, open issues, marketplace integrity',
  phases: [{ title: 'Inspect', detail: '6 parallel inspectors, one per dimension' }],
}

const CHECK_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    dimension: { type: 'string' },
    health: { type: 'string', enum: ['good', 'minor-issues', 'needs-attention', 'critical'] },
    summary: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'info'] },
          title: { type: 'string' },
          detail: { type: 'string' },
          location: { type: 'string' },
          recommendation: { type: 'string' },
        },
        required: ['severity', 'title', 'detail', 'recommendation'],
      },
    },
    stats: { type: 'string' },
  },
  required: ['dimension', 'health', 'summary', 'findings', 'stats'],
}

// Optional scout context passed in via args (recommended — scout once, share across all 6 agents).
const ctx = (args && typeof args === 'object') ? args : {}
const repoName = ctx.repo || 'this Claude Code skills marketplace repo'
const scale = ctx.scale || 'NOT pre-supplied — quickly self-discover it before inspecting (gh pr list --state open, gh issue list --state open, find . -name SKILL.md -not -path "*-workspace/*" | wc -l, and the metadata.version + skill count in .claude-plugin/marketplace.json).'

const COMMON = [
  `You are ONE inspector in a full health check of ${repoName} — a PUBLIC GitHub repo, a Claude Code skills marketplace. Your cwd IS the repo root.`,
  `Repo scale (as of this run): ${scale}`,
  'Inspect ONLY your dimension. Work efficiently: prefer grep/find/gh/scripts over reading every file; sample the highest-risk targets. Return structured findings — each with severity, what, where (file / PR# / issue#), and a concrete recommendation. Set health honestly. This is READ-ONLY: do NOT modify files, comment on PRs/issues, or push. gh CLI is authenticated.',
  '',
].join('\n')

const dims = [
  {
    key: 'code-and-script-safety',
    prompt: [
      'YOUR DIMENSION: Code & script quality + safety across all Python + Bash scripts in the repo.',
      'Grep high-risk patterns across all scripts (find . -name "*.py" -o -name "*.sh", exclude *-workspace/), then deep-read 3-5 of the most safety-critical scripts.',
      'Check for: (1) Dangerous deletes — rm -rf without confirmation, shutil.rmtree, os.remove/unlink without a guard — ESPECIALLY any file-deleting skill (e.g. macos-cleaner) and any cleanup / safe_delete script. (2) NO-FALLBACK violations (a repo CLAUDE.md rule): secret fallback like process.env.X || a-literal, apiKey/token default literals, || DEFAULT masking missing config. (3) Hardcoded real user paths /Users/<name>/ or /home/<name>/ (not placeholders). (4) Bare except: that swallows KeyboardInterrupt/SystemExit, and overly broad exception handling. (5) Dangerous eval/exec/os.system with interpolated input (injection). (6) Missing shebang / not executable on directly-run scripts.',
      'Deep-read sample: any deletion-capable skill (e.g. macos-cleaner/scripts/safe_delete.py + cleanup_report.py), repomix-safe-mixer/*, financial-data-collector/*, anything touching credentials or deletion.',
      'stats: how many scripts grepped, hits per pattern.',
    ].join('\n'),
  },
  {
    key: 'doc-consistency',
    prompt: [
      'YOUR DIMENSION: Documentation SSOT consistency. SSOT = .claude-plugin/marketplace.json (versions + registration).',
      'Check: (1) Version coherence — marketplace metadata.version vs README.md + README.zh-CN.md version badge vs CHANGELOG top archived version vs latest git release (gh release view); they should ALL match. (2) skill count — CLAUDE.md overview + README x2 badges/sentences + marketplace must all agree (run python3 daymade-claude-code/marketplace-dev/scripts/check_doc_skill_lists.py — authoritative). (3) plugin-entry count claimed in CLAUDE.md must match the actual number of plugin entries. (4) Broken references — for a sample of SKILL.md files, verify every referenced references/*.md and scripts/* file exists on disk. (5) SKILL.md must NOT contain its own version number (versions live only in marketplace.json) — grep, but EXCLUDE skill-creator instructional "Versioning" content (a known false positive). (6) Persisted derived-value drift (aggregate counts/badges that can go stale). (7) CHANGELOG structural issues — duplicate version-section headers, out-of-order versions.',
      'stats: version-coherence result + count-check result.',
    ].join('\n'),
  },
  {
    key: 'security-pii',
    prompt: [
      'YOUR DIMENSION: Sensitive-info / PII audit for a PUBLIC repo. A green tool scan is NOT enough — grep is blind to keyword-free private content, so ALSO read-judge sampled case files.',
      'Grep across the whole repo (exclude *-workspace/ and .git/): (1) Real absolute user paths /Users/<name>/ or /home/<name>/ (exclude <username>/<user>/example placeholders). (2) Real personal names, esp. CJK names embedded in paths/examples (gitleaks cannot catch these). (3) Secrets: sk-[A-Za-z0-9]{10,}, Bearer tokens, api_key = literal, AWS keys. (4) Real personal emails (exclude the public repo-owner email visible in git history) and CN phone numbers. (5) Private domains/IPs (EXCLUDE RFC-reserved 203.0.113 / 198.51.100 / 192.0.2 / 198.18 / 10. / 127. / 0.0.0.0 and example.com).',
      'SCAN MARKER GAP: compare the number of skills (SKILL.md files) to the number of .security-scan-passed markers — enumerate WHICH skill dirs are MISSING a marker (skill dir has SKILL.md but no sibling .security-scan-passed). Those shipped with no recorded scan. Treat the marker as necessary-not-sufficient: it catches known secret FORMATS, not keyword-free leaks.',
      'Spot-run the bundled scanner on 2-3 real-data skills: cd daymade-skill/skill-creator && uv run python -m scripts.security_scan ../../<skill> --verbose (good targets: skills shipping real-data examples). NOTE: the scanner MUTATES the .security-scan-passed marker as a side effect — git-checkout-restore it afterward so this read-only audit leaves no trace.',
      'Highest risk: case-study / incident-writeup files where real production detail leaks (e.g. debugging-network-issues/references/, skill-creator Phase 9 cases). Read-judge a couple. Distinguish REAL leaks from placeholders. ANTI-TARGET RULE: do NOT recommend adding the real private domains/names into the repo-local .gitleaks.toml — a public allowlist that enumerates real assets is itself a leak. Private-value rules belong in the owner global guard (~/scripts/git-pii-guard), not in this public repo.',
      'stats: the marker-gap skill list + grep hit counts.',
    ].join('\n'),
  },
  {
    key: 'pull-requests',
    prompt: [
      'YOUR DIMENSION: Triage ALL open PRs (fast and decisive, not a deep code audit).',
      'Get them: gh pr list --state open --json number,title,headRefName,author,createdAt,additions,deletions,changedFiles. Where useful, gh pr view <n> --json mergeable,mergeStateStatus.',
      'Produce ONE finding per PR classifying it: Type (new-skill / docs / fix / third-party-marketplace-promotion). Author (external contributor vs the repo owner). Mergeable (CLEAN / CONFLICTING / unknown). Verdict: worth-merging | needs-changes (most external new-skill PRs MISS the repo-mandatory version bump + CHANGELOG entry — flag that) | low-quality-or-spam | SHOULD-DECLINE (third-party marketplace/tool promotion — the repo has a standing decline policy documented at the repo root; declining is the default for "add my external directory/tool" PRs).',
      'Flag stale PRs (old createdAt) and suspicious/spammy accounts. Use severity to encode priority (high = ready-to-merge or needs-owner-action; low = spam/decline).',
      'stats: counts by verdict.',
    ].join('\n'),
  },
  {
    key: 'issues',
    prompt: [
      'YOUR DIMENSION: Triage ALL open issues.',
      'Get them: gh issue list --state open --json number,title,author,createdAt,labels. Read bodies of the substantive ones: gh issue view <n>.',
      'Classify each: real-bug / skill-request / cross-list-or-promotion / question.',
      'KNOWN BUG CLASS to ACTIVELY check (whether or not an issue reports it): do the README / QUICKSTART install commands ever use a SUITE-MEMBER skill name as if it were a standalone plugin? `claude plugin install <suite-member>@<marketplace>` FAILS — only the suite plugin is installable; members are invoked as `<suite>:<member>`. This is the front-door install instruction, so a broken one is HIGH severity. Cross-check each install command against marketplace.json (a name that ONLY appears inside a suite skills[] array is a member, not a plugin).',
      'Flag promotion / cross-list issues (external directories, "list us", revenue-share backlinks) as DECLINE per the repo policy.',
      'stats: counts by type.',
    ].join('\n'),
  },
  {
    key: 'marketplace-integrity',
    prompt: [
      'YOUR DIMENSION: Marketplace manifest integrity.',
      'Run and report exit codes + key output: (1) bash daymade-claude-code/marketplace-dev/scripts/check_marketplace.sh (JSON syntax, claude plugin validate, source+skills resolution, reverse-sync orphan WARN). (2) python3 daymade-claude-code/marketplace-dev/scripts/check_doc_skill_lists.py.',
      'Check: (a) Orphan SKILL.md on disk not registered (reverse-sync WARN) — a gitignored *-workspace/ scratch dir is NOT a real orphan; confirm with git check-ignore before flagging. (b) Every suite (category=suite) entry: each skills[] member exists on disk, and no suite member is ALSO wrongly registered as a standalone plugin. (c) Version sanity: duplicate plugin names, obviously stale versions. (d) Counts reconcile: plugin-entry count and expanded-skill count match what the docs claim and what is on disk.',
      'stats: script exit codes + orphan list.',
    ].join('\n'),
  },
]

phase('Inspect')
const checks = await parallel(dims.map(d => () => agent(COMMON + d.prompt, { label: 'check:' + d.key, phase: 'Inspect', schema: CHECK_SCHEMA })))

return { checks: checks.filter(Boolean) }
