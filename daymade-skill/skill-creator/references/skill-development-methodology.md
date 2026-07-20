# Skill Development Methodology

综合 Anthropic 官方最佳实践、skill-creator 工作流、社区经验和实战教训的完整方法论。

## Contents

- Phase 1 先手动解决问题 · Phase 2 并行调研 · Phase 3 真实数据验证（3.1 完整性 / 3.2 记录失败 / 3.3 隔离复现+反证+权威源）
- Phase 4 写作补充（4.1 不能做什么 / 4.2 失败过什么 / 4.3 安全 / 4.4 console 示例 / 4.5 脚本健壮性 / 4.6 三资产分流）
- Phase 5 测试迭代（5.1 删竞争旧 skill / 5.2 量化对比 / 5.3 grep 断言误判 / 5.4 baseline 揭示事实错误 / 5.5 增量为 0 / 5.6 完整性两道闸）
- Phase 6 Counter Review（6.1 视角 / 6.2 final gate / 6.3 常见发现 / 6.4 findings 过滤 / 6.5 多层验证）
- Phase 7 & 8 Description + Packaging · Phase 9 实战案例库（Case 1-16）· 来源

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

**知识型 skill(内容主体是外部系统的事实——API 端点/参数/字段/平台行为)先读 [knowledge-skill-grounding.md](knowledge-skill-grounding.md)**:权威源阶梯(实际观察 > 机器可读规范 > 已运行代码 > 官方文档 > 记忆)、证据边界标注、发布前文档示例冒烟、改事实 grep 全目录、受众环境声明、Windows 兼容清单、多角度审核菜单。未做 source-grounding 的抽象案例见 Phase 9 Case 9。

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

### 4.6 三资产分流：知识进 references，会被重写的代码进 scripts，认可产物的模式进原则

从对话 / 实战 session 蒸馏 skill 时，盘点**三类资产**——它们的归宿不同：

- **知识**（端点、参数、坑、判断规则）→ SKILL.md 指引或 `references/`
- **session 不得不写的代码**（helper 脚本、注入片段、渲染器、模板）→ `scripts/` 候选：这个 session 写过一次，未来每次调用都得重写
- **用户认可产物里反复出现的模式**（≥3 个认可样例共有的风格 / 结构 / 语言惯例）→ **原则层**（principles reference 的决策规则），样例本身只进语料库当索引与校准材料

只提取知识的蒸馏，会产出「解释了一切、却让每个未来 session 重写同一批 helper」的 skill——根因是框架里只有知识→references 通道、没有代码→scripts 通道。判据（收尾自问）：*这次对话写了什么代码，是未来每次调用必然重写的？* 参数化、脱敏、进 `scripts/`，文档改为指针——**脚本管执行、文档管理解**。

第三通道有对称的失败形态（Case 15）：只把认可样例**登记**进语料库（名字 × 路径 × 组件清单），不改变 skill 的任何决策规则——**登记 ≠ 提炼**。判据同构：*这批认可产物里，什么模式是未来每次生成都该遵守、却还只活在样例里的？* 量化提取、归纳成带证据的规则、写进原则层——**语料库管校准素材，原则管下次怎么做**。完整操作序见 `workflows/artifact-corpus-distillation/workflow.md`。

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

### 5.3 客观 grep 断言会误判，benchmark 是信号不是结论

用 grep/脚本做客观断言评分很方便，但 **grep 断言两头都会误判**：同词不同义**误命中**（一个词在 with-skill 里指 A、在 baseline 里指 B，grep 都算命中），用词差异**漏命中**（skill 讲了同一件事、换了个词，被判 miss）。所以 benchmark 的 pass 率是**信号、不是结论**。

- 真质量差异常常**不在断言计数里**：一个 case 里 with-skill 给"验证过的当前信息"、baseline 给"会导致失败的过期信息"，两者可能命中同样的断言、benchmark 显示平手，但一个对一个错。
- **拿到 benchmark 后必须抽查几个断言的实际命中内容**，确认 grep 判对了；别拿 pass 率直接下"skill 好 X%"的结论。
- 战例：某 skill eval 出 90% vs 72%，抽查发现 grep 把 baseline 的**老通道标识**误当成 skill 的**新标识**（误命中）、把"可用余额"当成不同于"可用额度"（漏命中）——真正的决定性差异（给对 vs 给会退汇的老信息）grep 根本抓不出。

### 5.4 baseline 不只是对照组——它会揭示 skill 的事实错误

baseline（without-skill）跑同一 prompt 时，如果它**用了 with-skill 没用的方法、或发现了 skill 声称不存在的东西**，那不是"baseline 走运"——那是 **skill 的潜在事实错误信号**，必须一手验证 + 修 skill。

- skill 里写死的**否定性断言**（"X 不在 API"、"只能手动做 Y"）最容易是这类错误——它是你当初没找到、就写成了"不存在"。
- 战例：一个 finance skill 铁律写"信用卡数据不在 API、需手动网页导"，eval 的 baseline agent 自己摸出了一个 `/credit` endpoint；一手 curl 验证属实 → 那条铁律是错的 → 改成"信用卡在 `/credit`、脚本自动拉"，让 skill 少干一半手动活。
- **这是 eval 最高价值的产出之一**：不是"证明 skill 好"，是"抓出 skill 里你没发现的错"。

### 5.5 诚实接受 skill 增量为 0 的 case

不是每个 case 里 skill 都碾压 baseline。强 baseline agent 自己就会的**通用工程能力**（带 date range、找全数据源、做核对），skill 增量可能≈0；能 WebSearch 到的公开**机制知识**，baseline 也能补。

- **这不是 skill 失败**——它诚实告诉你 skill 的**真价值集中在哪**：编码的**独有知识 / 私有 SOP**（搜不到、baseline 拿不到的），而非"帮 agent 做它本来就会的事"。
- 据此决定 skill 该**保留/强化**什么（独有知识）、哪些通用能力**不必在 skill 里啰嗦重复**。
- 别为了 justify skill 存在而夸大 benchmark——诚实的"这几个 case skill 没用、这一个 case 决定性"比"全面 90%"有用得多。

### 5.6 现有 skill 改写：完整性是前后两道闸，不是用户追问后的补救

可执行流程与 disposition 枚举的 SSOT 已提升到 SKILL.md Step 4；这里解释为什么工具只能**列候选**、不能替人做语义判断。

此前的规则把完整性审视放在“迭代后期、或用户问有没有丢”才触发，而且只回看源对话，没有对照旧 skill bundle。结果是一次大型 visual-QA skill 重构虽然结构更清楚、脚本更强、eval 也更全，却把多项旧运行时契约压没了：固定投影画布、已登录但无角色/租户的状态、图表单位/来源/时间范围、runtime 状态文案真实性等。最具迷惑性的一项仍存在于 trigger eval，但 eval 默认不打包——测试知道这个能力，运行时 skill 已经不知道。

因此每次修改**现有** skill 都有两条独立基线：

- **旧 bundle 基线**：旧 SKILL.md、references、scripts、assets、workflows、evals 中已经存在的能力与接口；
- **本次意图基线**：用户明确要求、源对话与新证据决定本次应增加、迁移或明确退役什么。

前一道闸在首次编辑前保存旧 bundle：非 Git / dirty 来源用 `audit_skill_regression.py snapshot` 生成带 provenance manifest 的副本，Git 来源则从显式 ref 重建；任意复制一份目录再自称 old baseline 不算。后一道闸用 `audit_skill_regression.py compare --baseline-origin ...` 先核对 snapshot manifest 或 Git commit tree，再生成 exact-removal 候选并逐项 disposition。降低字数、拆 references、统一术语都不是删除授权；只有用户明确要求退役时，才能用可追溯 approval 关闭旧能力。

验证通过后工具会写入 `.skill-regression-reviewed` 内容哈希收据；它不进入分发包，也不计入自身哈希。后续内容一变收据立即失效，但即使收据仍有效，它也只是变更提示、不是独立放行权：`package_skill.py` 对 Git HEAD 已存在的 skill 每次都重验完整 review。这样先 commit 让 working tree 变干净、手写 marker、或只算当前 tree hash 都不能跳过旧能力审计。

**不要用模糊相似度自动放行。** “检查 permission-denied”与“用真正 role-less account 验证已登录无权限时不暴露 privileged shell”词义相关，但不是等价契约。工具只会自动证明内容原样搬到运行时可达位置、CLI flag 仍在、或文件原样改名；搬到 eval/tests/未被 SKILL.md 直接或递归引用的 orphan reference 仍算丢失。其余必须人工判断，并给当前文件、行号和可定位的 `contains` 短引文。脚本/资产整文件变化还必须有具名 semantic review；文件 fingerprint 只能证明当前文件是哪一个，不能证明旧行为仍在。runtime 候选不能用一句 `not_reusable` 退休，boundary 迁出也要用户批准。候选结果同 counter-review finding 一样是风险假设，不是“全都恢复”的命令。

新 skill 没有旧 bundle，不触发 migration gate；Git 无法证明它是新 skill 时必须显式传 `--new-skill`，不能用“目录不在 Git”静默猜。即使是新 skill，从源对话蒸馏时仍要在收尾回看源材料。grep 只能 surface 候选：关键词不对会误报 gap，同词不同义也会误判保留，必须复查语义。

## Phase 6: Counter Review — 用 Agent Team 做对抗性审查

这是 SKILL.md 未覆盖的独立环节。SKILL.md 的 "Improving the skill" 章节关注用户反馈驱动的迭代，但没有系统化的多视角审查流程。

### 6.1 第一轮：3 个常规视角；现有 skill 再加 1 个保真视角

用 Task 工具同时启动 3 个 review agent：

| Reviewer | 视角 | 关注点 |
|----------|------|--------|
| Skill 质量 | 对标 Anthropic 最佳实践 | 描述质量、简洁性、progressive disclosure、可操作性、错误预防、示例、术语一致性 |
| 代码健壮性 | 高级工程师找 bug | 错误处理、安全性、跨平台、边界情况、依赖、幂等性 |
| 用户视角 | 首次使用者体验 | 首次成功率、输入容错、输出预期、隐私顾虑、失败恢复 |
| 旧能力保真（修改现有 skill 时） | old bundle vs edited bundle | 触发范围、运行时契约、命令/flags、边界案例、资源与 eval 是否被迁移、明确退役或误删 |

### 6.2 修复后 Final Gate

**Findings 是假设，不是结论——逐条 triage，不要无脑「修复所有 Critical/HIGH」。** 先用 6.4 的过滤器把每条 Critical/HIGH 过一遍：确认为真的修，判为虚构 / 过度防御的记录下来并说明为何不修。修改现有 skill 时还必须让旧能力保真 reviewer 对照 immutable baseline；它不能被“新版本看起来更简洁”这一单版本评价替代。修完真问题后，再启动 final gate reviewers 验证修复正确性，评分 >= 8 才放行。

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

**过滤纪律也针对你自己的评分脚本/grep，不只 sub-agent findings**：你写的 grep 断言、评分脚本、benchmark 也是**工具**，也会误判（同词不同义误命中、用词差异漏命中）。别盲信自己的脚本输出——benchmark 数字出来后抽查实际命中内容校准（详见 Phase 5.3）。"agent findings 是假设"这条纪律，对"我自己的工具输出"同样成立（一次 eval 里 grep 断言两头误判、把决定性差异判成平手，就是靠抽查内容才纠正）。

### 6.5 counter-review 只是验证的一层——多层验证互补

对抗性 counter-review 抓工程健壮性 + skill 质量，但它不是唯一一层。完整的 skill 验证是**三层互补，各抓不同类问题、各有独立盲区**：

| 层 | 抓什么 | 独立盲区 |
|----|--------|---------|
| **对抗审查**（本 Phase，内部多视角 agent） | 工程健壮性、skill 质量、UX | 同 model 多视角，**共同盲区抓不到** |
| **外部 review**（如 Codex 等**别的模型**） | 你和你的审查 agent 的**共同盲区**——尤其撞用户自己的铁律（如 NO FALLBACK 兜底） | 依赖该工具可用 |
| **eval**（with/without-skill baseline） | skill 的**事实错误**（baseline 揭示，见 5.4）+ 真价值分布（见 5.5） | 客观断言有水分（见 5.3） |

**别只做一层。** 战例：一个 skill 对抗审查过了、Codex 又抓出一个 NO FALLBACK 违规、eval 再抓出一个"数据其实在 API"的事实错误——三层各逮到前两者发现不了的问题。

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

### Case 8: 用 skill-creator 造 finance skill，eval 逼出 skill 的事实错误（2026-07）

用 skill-creator 完整走了一遍（创建→3 视角对抗审查→Codex review→正式 eval→从头审视），暴露 skill-creator 的 eval/验证部分**太乐观**——默认"跑出 benchmark 就知道质量了"。真实是：

- benchmark 90% vs 72% **有水分**：grep 断言误命中（baseline 的老通道标识被当成新的）+ 漏命中（"可用余额"≠"可用额度"）；真质量差异（给对 vs 给会退汇的老信息）grep 抓不出 → **Phase 5.3**
- **baseline 揭示了 skill 的事实错误**：baseline agent 摸出 `/credit` endpoint，推翻 skill "信用卡不在 API" 的铁律，一手验证后修复，让 skill 少干一半手动活 → **Phase 5.4**
- **诚实的增量分布**：对账/机制类 case 强 baseline 自己也做得好（增量小），只有"独有知识"case（搜不到的银行标识）决定性 → **Phase 5.5**
- **三层验证互补**：对抗审查抓工程健壮性、Codex 抓"撞用户自己的铁律"（NO FALLBACK 兜底）、eval 抓事实错误——别只做一层
- 从头审视时**不盲信自己的 grep**（初判的 gap 半数是关键词没对上）→ **Phase 5.6 + 6.4 延伸**

→ 对应规则：Phase 5.3 / 5.4 / 5.5 / 5.6 + 6.4「过滤纪律也针对自己的评分脚本」+ 6.5「多层验证互补」

### Case 9: 知识型 skill 未做 source-grounding(已去除项目指纹)

一个关于外部系统的知识型 skill 从记忆转写并通过表面 review,但全量证据审核发现多条契约断言与实际观察、机器可读规范和已运行代码矛盾。复盘得到的通用结论:

- **每条契约都要逐项对账**:路径、method、参数、字段与输入边界不能靠同一段记忆互相证明。
- **文档示例必须冒烟**:第一次真实执行就能抓到静态 review 漏掉的契约错误。
- **改事实要 grep 整个 skill**:脚本 docstring、`--help` 和代码注释与 Markdown 一样会漂移。
- **"已实证"必须带边界**:一个端点、版本或分支的观察不能自动外推到整个家族。
- **diff-only review 看不到存量错误**:知识型 skill 发布前需要至少一次全量 contract audit。
- **验证器必须用已知坏样本证伪**:存在绿色标记不等于扫描逻辑真的覆盖了目标文件。
- **按目标受众验收**:作者机器能跑不等于干净机器、不同 shell 或不同操作系统能跑。

→ 对应规则:[knowledge-skill-grounding.md](knowledge-skill-grounding.md) 全篇(权威源阶梯 / 证据边界 / 示例冒烟 / grep 全目录 / 受众声明 / Windows 清单 / 审核菜单 / 验证器自证伪)+ `scripts/selftest_validators.py`

### Case 10: 真实数据 happy-path 测过，仍漏掉控制流 / 跨上下文 bug（2026-07）

给一个新写的 Codex 会话解析器做了自认为充分的验证——真实会话全 CLI 模式跑通（list / query / session / all-projects / 默认提取）、空 / 垃圾 / 最小 / 字段全 None 的边界输入不崩、关键函数单测——然后 merge。一个 workflow-backed 对抗审查（fan-out finder + 独立 verifier）却抓出 2 个我**自己引入**、上述测试全没碰到的 bug：

- **控制流 / 不可达分支**：给 end-reason 分类新加了 `in_progress` 分支、排在 `error_cascade` 之前；而 cascade 也以 tool_output/patch 结尾，于是 `error_cascade` 成了永不触发的死代码。happy-path 输入根本不会走到「那条被改得再也点不着的分支」，所以测不出。
- **跨上下文**：`get_git_state` 跑在调用目录、而非被 resume 会话的 cwd。真实数据测试全在同一个 cwd 下，从没喂过「从 A 项目 resume B 项目的会话」这个跨上下文组合，那条路径就没被走过。

**教训**：**真实数据 happy-path 覆盖 ≠ 代码路径覆盖。** happy-path 测试再「充分」（真数据 + 全模式 + 边界），能活下来的恰恰是你的输入没走过的路径——一条被改动变得不可达的分支、一个你没喂的跨上下文组合；它们本质上是 happy-path 的**补集**，靠「再多跑几组真实数据」逮不到，只有一道**专门构造失败输入 / 想清楚分支可达性**的对抗 pass 能补上。这就是 §6.5「别只做一层」的具体代价：**你自己的 happy-path 测试再勤，替代不了对抗那一层。** 同次对抗的 finding 仍按 6.4 过滤——2 条被驳回（一个假「回归」、一个把故意的设计差异当重复），肯定与否定都要亲验。

→ 对应规则：Phase 6.5「多层验证互补」+ 6.4「findings 是假设」；Phase 3「跑通不报错 ≠ 验证过了」在控制流覆盖上的延伸

### Case 11: 语料蒸馏型 skill 的完整性靠独立审计，不靠作者自审（2026-07）

从一份大型私有语料蒸馏一个 taste/方法论 SSOT skill。作者(同一个模型)**两次宣布"内容完整"、两次都在下一轮又冒出遗漏**——先自查补 12 处、再补 4 处，仍不放心。最后派一个**独立子代理**(全新 context,读全部源语料 + 当前 skill,对抗性列缺什么),一次抓出 **15 处真遗漏**(含一条承重操作机制:skill 反复要求"传参考截图"却从没写怎么传)。通用结论:

- **压缩即丢失,而自审用的是同一把压缩尺**:作者的"完整"判断,和造成遗漏的,是同一个模型、同一个盲区;自查(含自己 grep)会系统性放过同型缺口。
- **改现有 skill 有 regression 门禁(`audit_skill_regression`),从大语料新建却没有对应的完整性门**——这是方法论的一个洞。
- **修法 = 独立视角**:派一个不共享作者上下文的子代理,喂它全部一手源 + 成品 skill,要求"假设不完整,逐条对源挑缺失、带出处引用、按承重度分级"。它跳出作者盲区;且"漏"和"AI 味"不同——完整性有客观锚(源里有没有),适合子代理,不像 AI 味必须靠人耳(与「不用 sub-agent 测 AI 味」不冲突)。

→ 对应规则:语料蒸馏 / conversation-mining 型 skill 发布前必过一道**独立完整性审计**(子代理读全源 + 成品,对抗列 gap);与「不盲信自己的 grep」(Case 8)、discipline #4「preserve before compress」同源——那两条管改 skill,这条管从语料新建。

### Case 12: description 优化循环会产出"空洞退化"结果,先用已知正例验 harness（2026-07）

跑 description 触发优化循环(`run_loop`)5 轮,**每轮 recall=0% / precision=100% / 分数一字不差**,脚本照样选出一个"best_description"(其实就是第 1 轮的原始描述)。差点当成"已优化验证"应用上去。真相:

- **precision=100% 是零预测的空值**:一次正例都没触发(recall=0),分母为零、毫无意义;各轮同分 = harness 根本没在区分描述。
- **是 harness 坏了、不是描述坏了**:根因是触发被已装竞品截胡(见 Case 13),harness 反映不出来 → 输出全是噪音。
- **通用铁律「验新功能的 harness 先跑通已知良好 baseline」在此适用**:信优化器的"best"之前,先喂一条**铁定该触发**的 query 看 recall 是否 >0;recall=0 或各轮同分,停,别应用任何"best"。

→ 对应规则:Description Optimization 段加 caveat——`run_loop` 输出前先过 known-good baseline;recall=0/各轮同分 = harness 是隐藏变量,其"best_description"不可信,改手工写 + 真实探针验证。

### Case 13: 触发和"已装 skill 群"抢,散文未必赢;按竞品归属决策（2026-07）

新 skill 内容优秀、已激活,但**自动触发在真实机器上抢不过**:三条真实 query 分别被三个不同第三方 skill 截胡(一个信息图 skill、一个 CLI 委派 skill、一个数据可视化 skill)。改 4 版描述 + 点名 SUPERSEDES 都没扭转。通用结论:

- **Coexistence 章节只讲"刻意 fork/hardened 版"重叠,漏了更常见一类**:新 skill 和一堆早已安装、同域的 skill 抢同一触发槽位,静默落败。
- **早探,别等交付才发现**:建好后立刻用几条真实 query 走 `claude -p` 探——它真赢了吗?并**点名**输给谁(不同 query 可能输给不同竞品)。
- **散文赢不了拥挤槽位是常态**(即"散文是建议、结构才是强制");解法阶梯:改名 → 描述 tiebreaker → 手动调用 → SessionStart 路由 hook(结构性强制,但改全局配置,须用户明确同意)。
- **决策规则看竞品归属**:竞品是第三方 → 接受手动调用 / 装路由 hook;竞品是你自己写的 → 合并/收敛进一个,别养两个抢触发。

→ 对应规则:Coexistence & Precedence 扩一小节「和已装 skill 群的触发竞争」:早探 + 点名竞品 + 散文未必赢 + 归属决策 + 路由 hook 需 consent。

### Case 14: 触发验证的代理陷阱——调 Skill 工具 ≠ 知识被用;hook 会干扰探针（2026-07）

手写触发探针验"新 skill 会不会被调用",探针"**看到第一个 Skill 调用就早退**"——被一个 UserPromptSubmit hook 注入的无关 skill 抢先触发、据此误报"未触发"。改成"收集整轮所有 Skill 调用"才拿到真结论。更深一层:

- **hook 会在模型选择前注入 skill**:早退式探针把 hook 注入的第一个 skill 当成"模型的选择",误判;要收集整轮。
- **调 Skill 工具只是代理指标**:真正要验的是"skill 知识有没有进产物 / 产物对不对",不是"有没有调那个工具";有时模型没显式调 Skill、却已把内容读进 context。
- **自己写的验证探针也会成隐藏变量**(同 Case 8「不盲信自己的评分脚本」)——探针的 bug 会让你在错误结论上继续调优。

→ 对应规则:Description Optimization / triggering 段加 caveat——`claude -p` 验触发收集整轮全部 skill 调用(防 hook 注入干扰);Skill 调用是代理、真信号是产物体现 skill 内容。

### Case 15: 登记 ≠ 提炼——收录 8 张认可样例后被用户点破「你不能只加示例」（2026-07，已去除项目指纹）

用户给一个报告页生成 skill(已去除项目指纹)贴出 13 张他认可的 HTML 页说「你来学到底什么是我想要的」。第一轮把 8 张新样例**登记**进语料库（register × 路径 × 组件清单 +17 个组件词条），regression audit 全绿、版本照 bump——看起来完成了。用户一句点破：「**你不能只加示例吧。你得去提取出来我真正的喜好是什么，然后把它放到 Skill 里来。**」复盘：登记不改变 skill 下一次运行的任何决策，语料库行只有配合「动手前读最近 register 样例」的触发才有一点被动价值。第二轮才是真提炼：脚本横向抽全部 13 张的 CSS 变量 / 字体 / 尺寸 / 交互计数 / 标题文案层 → 按层归纳（认知 / 语言 / 结构 / 视觉语义 / 量化参数 / 交互 / 诚实）→ 写进原则文件的决策规则层。量化还**修正了既有原则**：「皮随 register 变」太宽泛——13 张报告页基底全是暖纸族、无一例外，真正随受众变的只有 accent 色相；「一个 accent 极少量点缀」实测是红金绿蓝四色语义系统。随后的独立完整性审计（纪律 #5）又抓出 7 条同类型盲区，含一条对当轮新规则的系统性修正（决策页标题必须停在问题句，否则替拍板人预答）。

→ 对应规则:SKILL.md「Distill User Preferences from an Approved-Artifact Corpus」路由段 + `workflows/artifact-corpus-distillation/workflow.md`;§4.6 第三通道（登记≠提炼判据）。

### Case 16: 多 session 并发编辑同一 skill repo——Write 被拒、HEAD 一小时内移动两次（2026-07，已去除项目指纹）

优化同一个报告页 skill 时另有兄弟 session 同仓工作:①刚做完 pre-edit snapshot、正要写语料库文件,Write 被拒（file has been modified since read）——另一 session 恰好提交了改同一文件同一段的收口 commit;②重建 baseline 后干到一半,HEAD 又因兄弟 session 提交另一个 skill 而移动。三个教训:**工作树快照做 baseline 在并发下天然过期**,repo 干净时用 `git archive <sha>` + `--baseline-origin git-ref:<sha>`;**Write 被拒不是重试信号**,先 `git show <新commit> --stat` 看对方改了什么、把对方意图并进自己的版本再写（那次对方的收口句与本轮重写意图一致,直接吸收）;**commit 前查 HEAD**,移动了就对新 ref 重跑 compare——verify 反正会拒绝过期 review,自己先抓省一轮。连带定了版本节奏:同 session 连续多轮改同一 skill,收敛成一次 bump,除非中间态已被消费。

→ 对应规则:SKILL.md「Concurrent sessions on the same skill repo」五条。

### Case 17: 组件货架——交互纠正当场组件化,「引用即内嵌」催生 lightbox-gallery（2026-07，已去除项目指纹）

用户审一张决策报告页时纠正「看 X →」跳转式引用：「你让我来回跳转……**绝对禁止这种东西**。你如果需要引用，你就放在这个位置，让我直接能看到图片。」修完页面（证据缩略图内嵌决策卡＋原地浮层放大）后，用户提出更深一层要求：「我不希望你每次都是重新写的……交互形式都是沉淀下来的、可以复用的、有复利的组件，代表一致的 Agent 和我交互的喜好和风格。」同 session 三级落地：①页面修复；②纠正**原话**回写进 skill 原则文件，并修掉被证伪的旧契约句——旧文教的正是刚被禁的 goto 锚跳，只加新规则不改旧教条，复发是必然；③把修好的图片浮层抽成该 skill `assets/` 下 components 货架里的 lightbox-gallery 组件（BEGIN/END 逐字嵌入块，← → 循环 / ESC 关 / 原地浮层 / n·N 计数 / 分组，**行为冻结、皮可调**）＋ interaction-components 登记簿 reference（契约＋来源页＋认可日期；**认可才收录**），并用注入式自动化点击测试验证（开 / 计数 / 切换 / 回退 / 关 / 分组 / 循环边界全绿）后才登架。三条教训：①手搓交互的真代价是**漂移**——键位、关闭行为每次微差，交互一致性本身是产品体验；②纠正回写要**同 session、双层**（产物层＋skill 层），且必须检查 skill 旧文是否在教刚被禁的反模式；③组件货架与认可样例语料同纪律——它是「品味的可执行形态」在交互维度的实例，Scripts check（skill 执行的代码）之外的第二条沉淀通道（产出物内嵌的片段）。

→ 对应规则：SKILL.md Step 4「Component-shelf check」＋「Improving the skill」第 5 条（原话回写）。

## 来源

| 来源 | 本文档引用的独有贡献 |
|------|-------------------|
| Anthropic Official | Evaluation-driven development、conciseness imperative（已由 SKILL.md 覆盖，本文不重复） |
| skill-creator SKILL.md | 完整工作流和工具链（本文引用但不复制，请直接参考 SKILL.md） |
| 社区经验 | 激活率数据（20%→90%）、Encoded Preference > Capability Uplift |
| 实战教训 | 并行研究 agent、失败记录的价值、竞争 skill 删除、量化迭代对比、Counter Review 流程、benchmark 有水分需抽查内容、baseline 揭示 skill 事实错误、诚实增量分布、现有 skill old-vs-new 完整性门禁 + 不盲信自己的评分脚本（Case 8）、语料蒸馏型 skill 需独立完整性审计（Case 11）、run_loop 空洞退化输出需先验 harness baseline（Case 12）、和已装 skill 群的触发竞争 + 竞品归属决策（Case 13）、触发验证的代理陷阱 + hook 干扰探针（Case 14）、认可产物语料的登记≠提炼（Case 15）、多 session 并发编辑同仓的 baseline/写入/提交纪律（Case 16）、交互组件货架＋纠正原话双层回写（Case 17） |
