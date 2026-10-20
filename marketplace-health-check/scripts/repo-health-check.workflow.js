// workflow-agent-limit: 6
// Dynamic Workflow: health check for a Claude Code skills marketplace repo.
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
  description: 'Full health check of a Claude Code skills marketplace repo: code/scripts, docs/SSOT, security/PII, open PRs, open issues, marketplace integrity',
  phases: [{ title: 'Inspect', detail: 'Parallel inspectors, one per dimension' }],
}

const CHECK_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    dimension: { type: 'string' },
    status: { type: 'string', enum: ['checked', 'not_checked'] },
    health: { type: 'string', enum: ['good', 'minor-issues', 'needs-attention', 'critical'] },
    summary: { type: 'string', minLength: 1 },
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
    stats: { type: 'string', minLength: 1 },
  },
  required: ['dimension', 'status', 'health', 'summary', 'findings', 'stats'],
}

// Optional scout context passed in via args (recommended — scout once, share across inspectors).
const ctx = (typeof args === 'object' && args !== null) ? args : {}
const repoName = ctx.repo || 'this Claude Code skills marketplace repo'
const scale = ctx.scale || 'NOT pre-supplied — follow SKILL.md Step 1 to read the manifest as JSON and obtain server totals or complete paginated inventories before inspecting. Never treat gh list default output as an ALL-items inventory.'

const COMMON = [
  `You are ONE inspector in a full health check of ${repoName} — a GitHub repo hosting a Claude Code skills marketplace. Confirm the scout visibility before applying public-publication risk judgments. Your cwd IS the repo root.`,
  `Repo scale (as of this run): ${scale}`,
  'Inspect ONLY your dimension. Work efficiently: prefer grep/find/gh/scripts over reading every file; sample the highest-risk targets. Return structured findings — each with severity, what, where (file / PR# / issue#), and a concrete recommendation. Set status=checked only after the dimension\'s required checks finish; report the actual scope and sample sizes in stats. If an essential command/data source is unavailable, a page fails, or coverage cannot be established, set status=not_checked, health=needs-attention, and explain what remains unexamined without judging it a repo defect. Set health honestly for checked work. This is READ-ONLY: do NOT modify files, comment on PRs/issues, or push. gh CLI is authenticated.',
  '',
].join('\n')

const dims = [
  {
    key: 'code-and-script-safety',
    prompt: [
      'YOUR DIMENSION: Code & script quality + safety across all Python + Bash scripts in the repo.',
      'Grep high-risk patterns across all scripts (find . -name "*.py" -o -name "*.sh", exclude *-workspace/), then deep-read 3-5 of the most safety-critical scripts.',
      'Check for: (1) Dangerous deletes — rm -rf without confirmation, shutil.rmtree, os.remove/unlink without a guard — ESPECIALLY any file-deleting skill (e.g. macos-cleaner) and any cleanup / safe_delete script. (2) NO-FALLBACK violations (a repo CLAUDE.md rule): secret fallback like process.env.X || a-literal, apiKey/token default literals, || DEFAULT masking missing config. (3) Hardcoded real user paths /Users/<name>/ or /home/<name>/ (not placeholders). (4) Bare except: that swallows KeyboardInterrupt/SystemExit, and overly broad exception handling. (5) Dangerous eval/exec/os.system with interpolated input (injection). (6) Missing shebang / not executable on directly-run scripts.',
      'Deep-read sample: any deletion-capable skill (e.g. daymade-macos/macos-cleaner/scripts/safe_delete.py + cleanup_report.py), repomix-safe-mixer/*, daymade-financial/financial-data-collector/*, anything touching credentials or deletion.',
      'stats: how many scripts grepped, hits per pattern.',
    ].join('\n'),
  },
  {
    key: 'doc-consistency',
    prompt: [
      'YOUR DIMENSION: Documentation SSOT consistency. SSOT = .claude-plugin/marketplace.json (versions + registration).',
      'Read the current root instructions and release owner before judging documentation. Run python3 daymade-claude-code/marketplace-dev/scripts/check_doc_skill_lists.py as the authority for registered capability coverage and prohibited derived snapshots; do not require version/count badges or count snapshots in CLAUDE.md. Check: (1) Parse marketplace metadata.version as JSON and evaluate release/changelog consistency only under the current release policy; latest-release absence is not automatically drift. (2) Compare README capability coverage and registration using the checker. (3) Flag persisted derived counts/badges only where the checker/current owner forbids them. (4) Broken references — for a sample of SKILL.md files, verify every referenced references/*.md and scripts/* file exists on disk. (5) SKILL.md must NOT contain its own version number (versions live only in marketplace.json) — grep, but EXCLUDE skill-creator instructional "Versioning" content (a known false positive). (6) Persisted derived-value drift (aggregate counts/badges that can go stale). (7) CHANGELOG structural issues — duplicate version-section headers, out-of-order versions.',
      'stats: version-coherence result + count-check result.',
    ].join('\n'),
  },
  {
    key: 'security-pii',
    prompt: [
      'YOUR DIMENSION: Sensitive-info / PII audit for a PUBLIC repo. A green tool scan is NOT enough — grep is blind to keyword-free private content, so ALSO read-judge sampled case files.',
      'Grep across the whole repo (exclude *-workspace/ and .git/): (1) Real absolute user paths /Users/<name>/ or /home/<name>/ (exclude <username>/<user>/example placeholders). (2) Real personal names, esp. CJK names embedded in paths/examples (gitleaks cannot catch these). (3) Secrets: sk-[A-Za-z0-9]{10,}, Bearer tokens, api_key = literal, AWS keys. (4) Real personal emails (exclude the public repo-owner email visible in git history) and CN phone numbers. (5) Private domains/IPs (EXCLUDE RFC-reserved 203.0.113 / 198.51.100 / 192.0.2 / 198.18 / 10. / 127. / 0.0.0.0 and example.com).',
      'Do NOT infer scan history from missing .security-scan-passed files: packaging_policy.py excludes these local receipts and public clones normally lack them. A present marker is not proof of semantic sanitization. Run generic secret/PII checks and semantic sample reads; record scanner scope and any unavailable optional private asset-value guard separately. That private guard is not a prerequisite for completing this public audit.',
      'For spot scans of 2-3 high-risk skills, load the Skill Creator materialization-budget reference and use prepare → run → finish on explicitly selected immutable inputs. Run uv run --frozen python -m scripts.security_scan <isolated-skill> --verbose from the creator project, only on the isolated arm. The scanner writes a marker: never scan the shared source then restore it with Git. If isolation or the required generic scanner is unavailable, report that missing check with status=not_checked; preserve independent observations.',
      'Highest risk: case-study / incident-writeup files where real production detail leaks (e.g. debugging-network-issues/references/, skill-creator Phase 9 cases). Read-judge a couple. Distinguish REAL leaks from placeholders. ANTI-TARGET RULE: do NOT recommend adding the real private domains/names into the repo-local .gitleaks.toml — a public allowlist that enumerates real assets is itself a leak. Private-value rules belong in the owner global guard (~/scripts/git-pii-guard), not in this public repo.',
      'stats: generic scan exit codes/scope + semantic sample paths + grep hit counts; identify unavailable optional private checks without calling missing markers a defect.',
    ].join('\n'),
  },
  {
    key: 'pull-requests',
    prompt: [
      'YOUR DIMENSION: Triage ALL open PRs (fast and decisive, not a deep code audit).',
      'Read the scout JSON at the path in scale; use open_prs.items only if open_prs.status=checked. If missing or incomplete, run the bundled scout_repository.py with the exact repo/root from SKILL.md Step 1. Its implementation follows the github-ops GraphQL pagination recipe (first:100, states:OPEN, after:$endCursor, pageInfo and totalCount). Use GraphQL fields number,title,headRefName,author{login},createdAt,additions,deletions,changedFiles,mergeable,mergeStateStatus. Validate every page, unique numbers and final count against a stable server total; do not substitute gh pr list default 30 or --limit 1000. A failed page, duplicate or unexplained total drift makes this dimension not_checked.',
      'Produce ONE finding per PR classifying it: Type (new-skill / docs / fix / third-party-marketplace-promotion). Author (external contributor vs the repo owner). Mergeable (CLEAN / CONFLICTING / unknown). Verdict: worth-merging | needs-changes | low-quality-or-spam | SHOULD-DECLINE. Read current CONTRIBUTING.md and promotion-policy.md for admission decisions: new-skill and promotion requests follow those policies; evaluate admitted fixes against the release owner rather than requiring a contributor to duplicate maintainer bookkeeping. External PR merge decisions always remain with the human owner.',
      'Flag stale PRs (old createdAt) and suspicious/spammy accounts. Use severity to encode priority (high = ready-to-merge or needs-owner-action; low = spam/decline).',
      'stats: counts by verdict.',
    ].join('\n'),
  },
  {
    key: 'issues',
    prompt: [
      'YOUR DIMENSION: Triage ALL open issues.',
      'Read the scout JSON at the path in scale; use open_issues.items only if open_issues.status=checked. If missing or incomplete, run the bundled scout_repository.py with the exact repo/root from SKILL.md Step 1. Its implementation follows the github-ops GraphQL pagination recipe: repository.issues(first:100,states:OPEN,after:$endCursor) with pageInfo,totalCount and nodes{number,title,author{login},createdAt,labels(first:100){nodes{name}}}. This connection excludes PRs; if using REST /issues instead, explicitly remove objects with pull_request and reconcile an issue-only total. Validate pages, unique numbers and stable total as for PRs; partial or ambiguous coverage is not_checked. Read substantive bodies with gh issue view <n>; page label connections too if classification requires labels beyond the first page.',
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
      'Check: (a) Orphan SKILL.md on disk not registered (reverse-sync WARN) — a gitignored *-workspace/ scratch dir is NOT a real orphan; confirm with git check-ignore before flagging. (b) Every suite (non-empty skills[] array) entry: each skills[] member exists on disk, and no suite member is ALSO wrongly registered as a standalone plugin. (c) Version sanity: duplicate plugin names, obviously stale versions. (d) Reconcile manifest plugin/member inventory and disk resolution using the authoritative checkers; do not require hardcoded counts or badges in docs.',
      'stats: script exit codes + orphan list.',
    ].join('\n'),
  },
]

// Bind each schema to its expected identity, then also validate at the collection boundary.
// Retain every expected row: null means interrupted/unrecoverable, never healthy or absent.
const healthValues = CHECK_SCHEMA.properties.health.enum
const severityValues = CHECK_SCHEMA.properties.findings.items.properties.severity.enum
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const hasOnly = (value, keys) => Object.keys(value).every(key => keys.includes(key))
const text = value => typeof value === 'string' && value.trim().length > 0
const incompletePrefix = 'Audit incomplete; overall repository health not determined: '
const incompleteSummary = reason => reason.startsWith(incompletePrefix) ? reason : incompletePrefix + reason
function notChecked(key, reason) {
  return { dimension: key, status: 'not_checked', health: 'needs-attention',
    summary: incompleteSummary(reason),
    findings: [], stats: 'Coverage not established for this dimension.' }
}
function normalize(key, value) {
  if (!isObject(value) || value.dimension !== key ||
      !hasOnly(value, ['dimension', 'status', 'health', 'summary', 'findings', 'stats']) ||
      !['checked', 'not_checked'].includes(value.status) || !healthValues.includes(value.health) ||
      !text(value.summary) || !text(value.stats) || !Array.isArray(value.findings) ||
      !value.findings.every(f => isObject(f) &&
        hasOnly(f, ['severity', 'title', 'detail', 'location', 'recommendation']) &&
        severityValues.includes(f.severity) && ['title', 'detail', 'recommendation'].every(k => typeof f[k] === 'string') &&
        (!('location' in f) || typeof f.location === 'string'))) {
    return notChecked(key, 'Inspector returned no usable result or violated its dimension/schema contract.')
  }
  if (value.status === 'not_checked') {
    return { ...value, health: 'needs-attention', summary: incompleteSummary(value.summary) }
  }
  return value
}
// Keep an explicit operating budget; review usage cost before adding inspection tasks.
if (dims.length > 6) throw new Error('Inspection tasks exceed the workflow maximum task budget of 6.')
phase('Inspect')
let results
try {
  results = await parallel(dims.map(d => async () => {
    try {
      const schema = { ...CHECK_SCHEMA, properties: {
        ...CHECK_SCHEMA.properties, dimension: { type: 'string', enum: [d.key] },
      } }
      return normalize(d.key, await agent(COMMON + d.prompt,
        { label: 'check:' + d.key, phase: 'Inspect', schema }))
    } catch (_) {
      return notChecked(d.key, 'Inspector failed before it could return a validated result.')
    }
  }))
} catch (_) {
  results = null
}
const checks = dims.map((d, i) => normalize(d.key, Array.isArray(results) ? results[i] : null))
// complete describes audit coverage, not repository health: critical can still be complete.
return { complete: checks.every(check => check.status === 'checked'), checks }
