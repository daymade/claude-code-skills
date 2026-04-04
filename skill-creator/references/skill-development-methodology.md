# Skill Development Methodology

综合 Anthropic 官方最佳实践、skill-creator 工作流、社区经验和实战教训的完整方法论。

本文档只包含 SKILL.md 中**没有覆盖**的内容。SKILL.md 已经详细描述的流程（Prior Art 8 渠道表、决策矩阵、Inline vs Fork、测试用例格式、描述优化循环等）不在此重复——请直接参考 SKILL.md 对应章节。

## Phase 1: 先手动解决问题，不要上来就建 skill

SKILL.md 的 "Capture Intent" 章节覆盖了意图收集的 4 个问题和 skill 类型分类。本节补充一个被忽略的前置步骤：

**不要一开始就写 skill。** 先用 Claude Code 正常解决用户的问题，在过程中积累经验——哪些方案有效、哪些失败、最终的 working solution 是什么。如果你没有亲自失败过，你写不出能防止别人失败的 skill。

很多 skill 都是从"把我们刚做的变成一个 skill"中诞生的。先从对话历史中提取已验证的模式（SKILL.md "Capture Intent" 第三段已提及），然后才开始规划 skill 结构。

## Phase 2: 用 Agent Team 做并行调研

SKILL.md 的 "Prior Art Research" 章节覆盖了 8 个搜索渠道、clone-and-verify 检查清单、和 Adopt/Extend/Build 决策矩阵。本节补充 SKILL.md 未提及的**并行调研模式**：

遇到不确定的技术方案时，不要串行尝试（太慢），也不要凭经验猜（太危险）。同时启动 3+ 个研究 agent，每个负责一个调研方向：

| Agent | 职责 | 搜索范围 |
|-------|------|---------|
| 工具调研 | 找已有成熟工具 | GitHub stars、npm/PyPI、社区 skill 注册表 |
| API 调研 | 找可用 API 端点 | 官方文档、逆向工程、移动端 API |
| 约束调研 | 理解技术限制 | 反爬机制、认证要求、平台限制 |

每个 agent 必须独立验证（读源码、确认 API 可达、检查最近提交日期），不能只看 README。

**案例**：开发一个数据导出 skill 时，3 个 agent 并行跑了 5-20 分钟，分别发现：一个关键工具当前版本 broken（605 stars 但 PR 待合并）、一个未公开的移动端 API（唯一可行方案）、目标平台升级了 PoW 反爬（所有 HTTP 抓取失效）。没有并行研究，这些信息需要串行试错 3+ 小时才能获得。

## Phase 3: 用真实数据验证原型

SKILL.md 的 Evaluation-Driven Development 流程覆盖了"先跑 baseline → 建 eval → 迭代"的过程。本节补充两个 SKILL.md 未强调的验证原则：

### 3.1 数据完整性验证

"it runs without errors" ≠ "it exported all items correctly"。必须：
- 对比 API 报告的 total 和实际导出行数
- 检查字段格式（评分、日期、编码是否符合预期）
- 用不同规模的数据测试（0 条、100 条、1000+ 条）

**常见静默 bug**：
- 分页逻辑：某些页面返回的数据量少于请求值（如请求 50 条返回 48 条），被误判为最后一页导致提前终止。修复：检查 `total` 而非 `page_size`
- 数据转换：API 返回 `{value: 2, max: 5}` 表示 2/5 星，但代码按 `max: 10` 处理后变成 1 星。修复：检查 `max` 字段确定 scale

### 3.2 记录失败

详细记录每个失败方案的方法、失败模式、根因。这些将成为 skill 中 "Do NOT attempt" 部分的内容——这是 skill 最独特的价值，防止未来的 agent 重走弯路。

失败记录的结构：

| 方案 | 结果 | 根因 |
|------|------|------|
| 方案名称 | 具体失败表现（HTTP 状态码、错误信息） | 架构层面的原因分析 |

## Phase 4: Skill 写作补充原则

SKILL.md 的 "Skill Writing Guide" 已覆盖 frontmatter、progressive disclosure、bundled resources、命名规范等。本节补充 SKILL.md 未提及的内容层面原则：

### 4.1 写清楚 skill 不能做什么

防止 agent 尝试不可能的操作。例如：
- "Cannot export reviews (长评) — different API endpoint, not implemented"
- "Cannot filter by single category — exports all 4 types together"

### 4.2 写清楚失败过什么

在 SKILL.md 或 references 中保留失败方案的摘要（详见 Phase 3.2），加上明确的"Do NOT attempt"警告。这比正面指令更有效——agent 看到 7 种方案的失败记录后，不会尝试第 8 种类似方案。

### 4.3 安全说明

如果脚本包含 API key、HMAC 密钥或其他凭据，必须解释来源和安全性。例如："These are the app's public credentials extracted from the APK, shared by all users. No personal credentials are used."

### 4.4 Console output 示例

展示一次成功运行的完整控制台输出。让 agent 知道"正确运行"长什么样，方便验证（SKILL.md Phase 5 的 self-verification）。

### 4.5 脚本健壮性

SKILL.md 的 "Solve, don't punt" 覆盖了基本错误处理。补充实战中发现的常见遗漏：
- 只捕获 HTTPError，遗漏 URLError / socket.timeout / JSONDecodeError
- 无限分页循环（API 异常时）——需要 max-page 安全阀
- CSV 中的换行符/回车符——`csvEscape` 必须处理 `\r`
- 用户输入是完整 URL 而非 ID——脚本应自动提取

## Phase 5: 测试迭代补充

SKILL.md 的测试流程非常详细（A/B 测试、断言、评分、viewer）。本节补充两个 SKILL.md 未覆盖的实操教训：

### 5.1 删除竞争的旧 skill

如果系统中存在旧版 skill（关键词冲突），eval agent 会被旧 skill 截胡，导致测试结果完全无效。必须在测试前删除旧 skill。

**信号**：eval agent 使用了不同于预期的脚本或方法 → 检查是否有同名/同领域的旧 skill 被加载。

### 5.2 量化迭代对比

SKILL.md 提到 timing.json 和 benchmark，但未给出具体应跟踪哪些指标。推荐：

| 指标 | 为什么重要 |
|------|-----------|
| 数据完整性（实际/预期） | 核心正确性 |
| 执行时间 | 用户体验 |
| Token 消耗 | 成本 |
| 工具调用次数 | skill 引导效率——次数越少说明 skill 的指令越清晰 |
| 错误数 | 必须为 0 |

**案例对比**：某 skill 迭代后，工具调用从 31 次降到 8 次（74% 减少）、Token 从 72K 降到 41K（43% 减少），说明 skill 的指令让 agent 不再需要自己摸索。

## Phase 6: Counter Review — 用 Agent Team 做对抗性审查

这是 SKILL.md 未覆盖的独立环节。SKILL.md 的 "Improving the skill" 章节关注用户反馈驱动的迭代，但没有系统化的多视角审查流程。

### 6.1 第一轮：3 个视角并行

用 Task 工具同时启动 3 个 review agent：

| Reviewer | 视角 | 关注点 |
|----------|------|--------|
| Skill 质量 | 对标 Anthropic 最佳实践 | 描述质量、简洁性、progressive disclosure、可操作性、错误预防、示例、术语一致性 |
| 代码健壮性 | 高级工程师找 bug | 错误处理、安全性、跨平台、边界情况、依赖、幂等性 |
| 用户视角 | 首次使用者体验 | 首次成功率、输入容错、输出预期、隐私顾虑、失败恢复 |

### 6.2 修复后 Final Gate

修复所有 Critical 和 HIGH 问题后，再启动 final gate reviewers 验证修复正确性。评分 >= 8 才放行。

### 6.3 常见发现模式

根据实战经验，reviewer 经常发现的问题类型：
- **SKILL.md 和 references 内容重复**（每次都会犯，包括本文档自己）
- **异常类型遗漏**（只捕获 HTTPError，漏掉 URLError/socket.timeout）
- **substring 误匹配**（`content.includes(url)` 导致 `/1234/` 匹配 `/12345/`）
- **docstring 与实际行为不一致**（写了 "4.5 → 5" 但实际行为是 "4.5 → 4"）
- **误导性注释**（注释说"每个分类写入后立即保存"但代码在最后才写入）
- **时间敏感数据**（特定日期的测试结果、版本号——下周就过时了）

## Phase 7 & 8: Description Optimization + Packaging

SKILL.md 已完整覆盖描述优化循环（20 个 eval query、60/40 train/test split、5 轮迭代）和打包流程（prerequisites、security scan、marketplace.json）。无补充。

## 来源

| 来源 | 本文档引用的独有贡献 |
|------|-------------------|
| Anthropic Official | Evaluation-driven development、conciseness imperative（已由 SKILL.md 覆盖，本文不重复） |
| skill-creator SKILL.md | 完整工作流和工具链（本文引用但不复制，请直接参考 SKILL.md） |
| 社区经验 | 激活率数据（20%→90%）、Encoded Preference > Capability Uplift |
| 实战教训 | 并行研究 agent、失败记录的价值、竞争 skill 删除、量化迭代对比、Counter Review 流程 |
