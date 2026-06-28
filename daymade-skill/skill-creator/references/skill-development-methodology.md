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

### 3.3 隔离复现 + 反证 + 扒到权威源

「跑通不报错」≠「修好了」，也≠「验证过了」。三个补强：

**隔离复现**：定位一个 bug 后，造一个最小的、一次性的隔离环境，专门复现这个 exact 故障，再确认修复让它消失——这才叫验证修复（而不是「我改了代码、看着对」）。例：怀疑某 skill 在「没有任何已装内容」时会无限新建备份目录，就搭一个空环境跑两遍，确认第二遍不再新建——旧逻辑会、修复后不会，bug 坐实、修复证实。

**反证**：下根因结论前先问自己「什么证据会让我立刻放弃这个假设？」然后去找它。N 个来源都「证实」某假设 ≠ 它为真；一个「证伪」证据才能真正定位根因。例：曾假设「统一一个规范路径就能满足所有场景」，一个实验直接证伪了它，逼出真正的根因。

**扒到权威源，别猜依赖的行为**：当一个工具 / 依赖行为异常，不要凭文档或直觉猜它怎么实现——去源头取证：读源码、`strings` / 反编译二进制、读它的校验器。例：从一个 225MB 的编译二进制里 `strings` 出校验逻辑，发现它用 `path.resolve()`（不解析 symlink）而非 `realpath()`——这一个事实同时证伪了上面的路径假设、并指明了正确设计。（同一个 dump 既是「反证」也是「扒权威源」，是一回事的两面。）

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

基本错误处理之外，补充实战中反复踩到的遗漏。

**错误处理 / 输入：**
- 只捕获 HTTPError，遗漏 URLError / socket.timeout / JSONDecodeError
- 无限分页循环（API 异常时）——需要 max-page 安全阀
- CSV 中的换行符 / 回车符——`csvEscape` 必须处理 `\r`
- 用户输入是完整 URL 而非 ID——脚本应自动提取

**状态 / 并发 / 数据安全（处理本地状态文件、可能多实例并发的 skill 尤其重要）：**
- **Fail-fast，不要用残缺数据覆盖权威文件**：当一个权威输入读不出来（损坏 / 截断 / 编码异常），宁可报错退出，也不要静默跳过它、再拿「缺了它的结果」覆盖原文件——那等于把用户数据删了。要么值存在且正确，要么报错，没有中间地带。
- **原子写**：写共享 / 状态文件用「写临时文件 + `os.replace()`」而非直接 `open(path,"w")`。两个实例并发时，非原子写会让读者读到半截或空文件。
- **幂等判定别太严**：「是否已处理过」的判据若依赖一个不稳定信号（如某个可选子目录在不在），会把「已处理」误判成「未处理」，于是每次运行都重做重活——曾因此每次启动都新建一个 backup 目录、无限膨胀。判据要选稳定、必然存在的标志。
- **缩小操作范围**：只需处理一个目标时，别每次全量重建所有目标（既浪费，又放大并发写冲突面）。给脚本一个「只处理 X」的参数。
- **清理悬挂引用**：当源消失（如某个 marketplace 被删），主动清掉指向它的悬挂 symlink / 死引用，否则它们会一直留在每个副本里、触发后续报错。

**打包形态的坑：**
- **单文件 `uv run --script`（PEP-723 内联依赖）无法中途模块化**：它是 import-coupled 的，把一个 2600+ 行的单文件脚本拆成 package 会破坏全部测试、引发上百轮反复（建目录 / 改名 / 删 / `git stash` 冲突 / 后台 refactor 也失败），最终只能 revert。脚本变大时：要么一开始就改依赖模型（建真正的 package + pyproject），要么保持单文件、配一个「各段行号索引」的导航注释块，**别中途拆**。

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

**Findings 是假设，不是结论——逐条 triage，不要无脑「修复所有 Critical/HIGH」。** 先用 6.4 的过滤器把每条 Critical/HIGH 过一遍：确认为真的修，判为虚构 / 过度防御的记录下来并说明为何不修。修完真问题后，再启动 final gate reviewers 验证修复正确性，评分 >= 8 才放行。

### 6.3 常见发现模式

根据实战经验，reviewer 经常发现的问题类型：
- **SKILL.md 和 references 内容重复**（每次都会犯，包括本文档自己）
- **异常类型遗漏**（只捕获 HTTPError，漏掉 URLError/socket.timeout）
- **substring 误匹配**（`content.includes(url)` 导致 `/1234/` 匹配 `/12345/`）
- **docstring 与实际行为不一致**（写了 "4.5 → 5" 但实际行为是 "4.5 → 4"）
- **误导性注释**（注释说"每个分类写入后立即保存"但代码在最后才写入）
- **时间敏感数据**（特定日期的测试结果、版本号——下周就过时了）

### 6.4 Findings 是假设，不是结论（过滤纪律）

Counter-review 的价值不是「列出所有风险」，而是 surface 你没想到、但真实存在的风险。Agent 擅长找风险、不擅长权衡——它会把每一个理论上可能出问题的点都列出来，不区分触发概率、修复成本、是否真会在现实场景遇到。所以 agent 的每条 finding（无论 positive「这是 bug」还是 negative「这个没用 / 该删」）都是**假设**，必须过滤后再行动，禁止原样照搬给用户、也禁止直接全改。

逐条过四个问题：

1. **概率**——这真会发生吗？（真实场景 / 边缘 case / 纯虚构）
2. **成本**——修 vs 不修，各自代价多少？
3. **现实场景**——在这个 skill 的真实用法里会不会触发？
4. **可验证**——能不能用 5 分钟的命令 / 脚本证实或证伪？能就去验，别停在嘴上。

然后分级：✅ 真问题（真 + 低成本 → 直接修；真 + 高成本 → 告诉用户权衡）/ ⚠️ 部分对（说明边界再定）/ ❌ 驳回（虚构、过度防御、或把一个 by-design 的选择当成 bug）。**最危险的一类**：agent 在你给它的单一框架内全力论证「X 该删 / 没价值」——它的结论只在那个框架内成立。删之前先确认 X 不在任何受众的 must-have 里；是某受众 must-have 的，agent 的单维否定不构成删它的理由。

给用户汇报时按 ✅ / ⚠️ / ❌ 分类，不要把 N 个 agent 的 M 条 finding 一股脑倒给用户让他自己挑。

## Phase 7 & 8: Description Optimization + Packaging

SKILL.md 已完整覆盖描述优化循环（20 个 eval query、60/40 train/test split、5 轮迭代）和打包流程（prerequisites、security scan、marketplace.json）。无补充。

## Phase 9: 实战案例库（每条规则背后的事故）

SKILL.md 中的若干行级规则来自下面这些真实事故。规则本身在 SKILL.md 在场，这里只存浓缩战例——当你怀疑某条规则是否值得遵守时来查它的代价。

### Case 1: YAML frontmatter 跨解析器分叉（2026-06）

某 PDF skill 的 description 是未加引号的 YAML plain scalar，值内含 `**Scope: markdown → PDF only.**`。Claude Code 的宽松解析器正常工作数月，codex 的严格解析器直接报 `invalid YAML: mapping values are not allowed`——同一文件跨 runtime 行为分叉。更阴险的同类发现：另一 skill 的 description 内含 ` #`，**不报任何错**——description 被静默截断（985 字符截到约三分之一处），触发关键词全部丢失，所有扫描全绿。发现一例后 grep 全仓，共 3 个 skill 中招。全仓修复方案：description 统一块标量 `>` 写法 + PyYAML 严格解析过闸（62/62 通过）。

→ 对应规则：SKILL.md Step 4 "Validate immediately after every SKILL.md edit" + 块标量约定

### Case 2: 脱敏按目的地，不按内容（2026-06）

从真实生产事故报告蒸馏 debugging skill 时，把私有 repo 的事故报告和公开 skill bundle 一起脱敏 → 违反私有仓库审计透明原则（事故报告的真实 hostname/路径/时间戳是审计价值所在），三轮返工逐文件恢复。期间另踩两坑：第一轮占位符把要隐藏的真实域名编码进了占位符名本身（形如 `<真实项目名-domain>`，替换等于没替换）；批量替换脚本无文件白名单，误改了项目 CLAUDE.md 被迫 git 恢复。

→ 对应规则：SKILL.md Step 5 "Scope the pass by destination" + 占位符命名/白名单两条

### Case 3: 用户词典零丢失的 suite 迁移（2026-05）

某转写纠错 skill 从 standalone 目录迁入 suite（安装路径与调用名同时变化）。用户最关心累积的纠错词典会不会丢——答案是零风险：词典 SSOT 在 `~/.<skill-name>/` 下且自带 `.bak` 备份，脚本所有路径从 `Path.home()` 起算，与安装位置完全解耦。同次事故面：marketplace 双重注册（standalone entry + suite skills 数组并存）导致双调用名共存让用户困惑；批量删除 standalone entry 后报 19 个 plugin error——Claude Code **没有**"删 entry 自动清理本地安装"机制，dangling 安装（16 entry × 多 profile ≈ 900MB cache）波及所有外部用户，只能靠 CHANGELOG migration 指引走。

→ 对应规则：SKILL.md Scripts "User-mutable data lives outside the bundle" + Step 8 breaking change 段 + 跨 skill 引用 namespaced

### Case 4: 历史挖掘撑爆 context（2026-06）

「基于全部对话历史优化 skill」任务在已接近满的主 context 里直接做：发起委派时 tool_use input 流出为空对象（InputValidationError: required parameter missing），下一请求超 token 上限 **17 个 token** 崩溃，整个 session 报废。重试时改为：两个并行 subagent 各自用 python 逐行解析 + 每字段截断提取 + 只返回浓缩教训清单，主 context 只收结论——一次成功，且萃取质量更高（每条教训带证据定位）。

→ 对应规则：SKILL.md Capture Intent 的 past-transcripts 委托段

### Case 5: 64 个 review agent，真正该改的是一部分（2026-06）

把一次根因修复交给 workflow-backed code review：64 个 agent → 61 条 verified findings → 收敛 15 条 distinct。若按 6.2 的旧写法「修复所有 Critical/HIGH」会全盘照搬；逐条过 6.4 过滤器后是分级处理而非全改——大部分是真问题（直接修），其中 1 条被**驳回**：agent 把一个 by-design 的「统一集合」当成 bug，但那判断只在「本该 per-instance 独立」这一个框架内成立，而那恰恰不是设计意图；另 1 条降级为 known-limitation（此前已主动评估、非当前 scope）。独立佐证同一时期另一 session：4 个 review agent 先 idle 半天不返回、回来后约一半 finding 经验证是错的（声称的某 bug 实测正确）。结论：counter-review 的产出是「风险假设清单」，不是「待办清单」。

→ 对应规则：Phase 6.4「findings 是假设，不是结论」+ 6.2 triage 改写

### Case 6: 否定判断也要留痕——别让分类 skill 重判（2026-06）

一个把输入分类到不同去向的 skill，对「判定为不属于任何目标（none）」的输入直接丢弃、零留痕。后果：下次换个场景、或重跑同一批，这些 none 输入被重新抓取、重新分类、重新判一遍——烧 API、烧时间。修复：让「判否」也落一条轻量记录（带判定结果 + 依据），下次直接命中、跳过重判。

**通用原则**：任何**分类 / 过滤 / 判断**类 skill，**否定判断（判为「不相关」「跳过」「失败」）和肯定判断一样要留痕**。否定判断不留痕 = 信息丢失 = 下次必重判。这是「失败也是数据」在 skill **运行期状态**上的体现（Phase 3.2 是开发期记录失败方案；这条是运行期记录每一次否定判断）。再加一个隔离维度（domain/project 标签），让「在 A 场景判否」不污染 B 场景，判否结果就能跨场景安全复用。

→ 对应规则：无现成规则，本 case 即原则

### Case 7: 规则齐全也会犯——示例里混入真名（2026-06）

优化一个 PUBLIC repo 的 skill 时，把刚处理过的真实项目人名（CJK）顺手写进了示例 `--add` 命令和词典规则举例——隐私直接进开源。讽刺的是该 repo 的隐私规则**早就写明**「示例里的真实 CJK 名也要脱敏、gitleaks 不覆盖 CJK、靠 AI 语义通读」——规则齐全，但写示例时没把「例子」当敏感内容过闸。

**教训**：① **示例是隐私盲区**——人会本能地把「刚处理的真实数据」当最顺手的例子，而真实数据就是隐私本身。写任何示例（命令、词典规则、war-story）前先问「这个名/路径/项目是真的还是占位的？」② **规则齐全 ≠ 被执行**——纯靠「记得过 AI 通读」会漏；真正兜底的是**自动 deny-list**（把活跃 private 项目的罕见人名加进 pre-commit 中文兜底扫描，commit PUBLIC repo 时强制拦），不依赖记忆。③ 通用 secret scanner 对 CJK 真名无效（无 secret 签名、低熵），只有 deny-list + AI 语义两条能防。

→ 对应规则：SKILL.md 示例一律占位符/虚构名；claude-code-skills CLAUDE.md「Privacy and Path Guidelines」禁止清单；git-pii-guard `lib.sh` deny-list

## 来源

| 来源 | 本文档引用的独有贡献 |
|------|-------------------|
| Anthropic Official | Evaluation-driven development、conciseness imperative（已由 SKILL.md 覆盖，本文不重复） |
| skill-creator SKILL.md | 完整工作流和工具链（本文引用但不复制，请直接参考 SKILL.md） |
| 社区经验 | 激活率数据（20%→90%）、Encoded Preference > Capability Uplift |
| 实战教训 | 并行研究 agent、失败记录的价值、竞争 skill 删除、量化迭代对比、Counter Review 流程 |
