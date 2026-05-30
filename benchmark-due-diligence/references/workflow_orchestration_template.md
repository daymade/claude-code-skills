# Workflow Orchestration Template

A ready-to-fill `Workflow` script for the four-phase fan-out. Fill the placeholders (`AS_OF`, `FACTS`, `COMMISSIONER_CONTEXT`, `DIMENSIONS`), keep the injection split intact, and run it via the `Workflow` tool. The schemas live in `evidence_grading_rubric.md` — paste them in or reference them.

## The injection split (the thing you must NOT break)

- `FACTS` → every agent (collection, verification, synthesis A)
- `COMMISSIONER_CONTEXT` → **only** synthesis B (the mapping agent), which does no external search

Collection/verification agents run `WebSearch` on their prompt. If commissioner context reaches them, it's searched on the open web. This is Trap 6.

## Template

```javascript
export const meta = {
  name: 'benchmark-dd',
  description: '<one-line: bust the benchmark and map onto the commissioner>',
  phases: [
    { title: '采集' }, { title: '验证' },
    { title: '综合-尽调结论' }, { title: '综合-对你的应用' },
  ],
}

const AS_OF = '<YYYY-MM-DD>'  // stamp freshness; pass it in (Date.now() is unavailable in workflow scripts)

// PUBLIC verified facts about the benchmark — injected into ALL agents.
// Flag the headline trophy claim with ⚠️ as the #1 to-verify target (Trap 2).
const FACTS = [
  '【已核实地基事实（截至 ' + AS_OF + '）。站在此基础上深挖，不推翻已验证项，但为 ⚠️ 项找独立硬证据】',
  '- <verified entity relationships — who owns whom, who only guests/partners (Trap 1)>',
  '- ⚠️ <the headline claim whose attribution + magnitude must be cross-verified>',
].join('\n')

// PRIVATE commissioner reality — injected into the Phase-4 mapping agent ONLY.
const COMMISSIONER_CONTEXT = [
  '【委托人真实资源与诉求 —— 仅映射阶段可见，禁入外部搜索】',
  '- owned assets (valid mapping targets): <...>',
  '- client/partner assets (NOT leverageable — Trap 3): <...>',
  '- what they want to steal / the decision they face: <...>',
].join('\n')

const COLLECT_SCHEMA = { /* see evidence_grading_rubric.md */ }
const VERIFY_SCHEMA  = { /* see evidence_grading_rubric.md */ }

const DIMENSIONS = [
  { key: 'subject-bio',     label: 'subject background + headline-claim attribution', focus: '... ★ verify WHO actually did the trophy stat, and its real magnitude' },
  { key: 'corp-base',       label: 'corporate base + funding',                        focus: 'entity, founding, funding/valuation; qcc for mainland-China subjects' },
  { key: 'product-metrics', label: 'core product real metrics (bubble-bust)',         focus: 'cross-verify user counts / revenue / rankings / awards against third parties' },
  { key: 'playbook',        label: 'playbook teardown',                               focus: 'platform matrix / persona / how they borrow others’ audiences / IP→product funnel; agent-reach for socials' },
  { key: 'comparison',      label: 'comparison sample',                               focus: 'a structurally-similar peer or parallel path' },
  { key: 'sector-peers',    label: 'sector + same-class playbook',                    focus: 'how this class of playbook usually wins AND usually fails' },
]

log('Phase 1+2: fan-out collect → adversarial verify (bubble-bust)')
const verified = await pipeline(
  DIMENSIONS,
  (d) => agent(
    '你是尽职调查研究员，立场客观、只认证据。维度：' + d.label + '\n\n' + FACTS +
    '\n\n【本维度要砸实】\n' + d.focus +
    '\n\n【工具】优先 WebSearch/WebFetch；可 Bash 调 agent-reach(社媒) / qcc(工商) 增强，调不通回退，不卡死。' +
    '\n【纪律】每条 finding 带 source URL + source_kind；查不到写 gaps，禁脑补。',
    { label: '采集:' + d.key, phase: '采集', schema: COLLECT_SCHEMA, agentType: 'general-purpose' }
  ),
  (collected, d) => agent(
    '你是对抗性核查员，默认怀疑，专找水分。逐条打证据等级+裁决。\n维度：' + d.label +
    '\n采集结果：\n' + JSON.stringify(collected) +
    '\n【L4=硬数据可查实 / L3=多独立信源一致 / L2=单一可信第三方 / L1=仅自述营销】' +
    '\n【裁决 坐实/大体可信/存疑/证伪-水分】主动找证伪证据，尤其 headline 战绩/榜单/融资/用户量。bubble_summary 点最大水分。',
    { label: '验证:' + d.key, phase: '验证', schema: VERIFY_SCHEMA, agentType: 'general-purpose' }
  )
)
const clean = verified.filter(Boolean)

phase('综合-尽调结论')
const partA = await agent(
  '资深行业分析师。基于核查结果产出"尽调结论"(中文 markdown)。\n\n' + FACTS +
  '\n核查结果：\n' + JSON.stringify(clean) +
  '\n## 一、真实关系图（已核实，纠正常见误解）' +
  '\n## 二、破泡沫核查表（宣称|证据等级|裁决|依据，水分从大到小）' +
  '\n## 三、打法拆解（可操作动作）' +
  '\n## 四、归因拆解（产品/时机/IP/运营各占%；可复制 vs 运气/时机/禀赋）' +
  '\n要求：用证据说话引用 evidence_level；不确定标存疑，禁补细节。',
  { label: '综合:尽调结论', phase: '综合-尽调结论' }
)

phase('综合-对你的应用')
const partB = await agent(
  '委托人战略顾问，犀利只给能落地的判断。基于尽调结论+委托人资源产出"对你的应用"。\n【尽调结论】\n' + partA +
  '\n\n' + COMMISSIONER_CONTEXT +  // <-- the ONLY place this is injected
  '\n## 五、资源映射表（打法要素 × 委托人资源；✅可借鉴/⚠️不可复制/🔄已在做/🚫泡沫别学）' +
  '\n## 六、落点：委托人具体怎么用（每落点 3-5 个可执行动作）' +
  '\n## 七、行动建议 + 存疑项' +
  '\n要求：紧扣委托人真实资源，禁把客户当委托人自有资产；不说正确的废话。',
  { label: '综合:应用建议', phase: '综合-对你的应用' }
)

return { partA, partB, dimensionsVerified: clean.length }
```

## Scaling to thoroughness

- **Quick read:** 3-4 dimensions, single-vote verification.
- **Deep audit:** 6+ dimensions; add a multi-vote refutation pass on the headline claims (spawn N skeptics per claim, kill if a majority refute) before synthesis.
- **Agent count:** ~2 per dimension (collect + verify) + 2 synthesis. 6 dimensions ≈ 14 agents — a real, token-heavy run. Tell the user the scale before launching.

## After the run

The workflow returns `{ partA, partB }`. Stitch them into one markdown file, drop it where research lives, and offer the Next-Step PDF render (see SKILL.md). Strip any agent self-talk preamble before the first `##` heading.
