---
name: tibo-reset-codex
description: >-
  查询 ChatGPT/Codex 重置公告及多个 Pro 账号的剩余额度、备用 Full reset；复用 Google
  登录逐个核实并恢复网页账号，换算北京时间。区分 Tibo 官宣、未官宣的平台静默重置、banked
  reset 与账户级周期重置。Use when 用户问「什么时候重置」「额度什么时候恢复」「下次全员重置几点」
  「banked reset 到了吗」「Tibo 说了什么」「usage limit when reset」，或说「额度突然回到
  100%」「好像/肯定又重置了」，或问「几个账号都用完了吗」「哪个还满额」。必须用实时产品状态、独立用户实测与公告交叉核验；禁止因
  Tibo Radar 没有新条目就否定已经发生的重置，并须把太平洋时间当场换算为北京时间。
---

# Tibo Reset — ChatGPT/Codex 额度重置速查

## 这是什么

「Tibo reset」= OpenAI Codex/ChatGPT Work 负责人 **Thibault Sottiaux（X: @thsottiaux）**
在 X 上宣布的广域额度重置传统。社区昵称「Lord Tibo」，有第三方追踪站 **Tibo Radar**
（`codex-reset.com`）和「祈祷重置」亚文化。Tibo 官宣没有固定排期；但平台也会在限额
配置切换时**不发 reset 帖而直接重置账户**。所以「没有 Tibo 帖」只证明没有官宣，不能证明
没有重置。

**先分清用户问的是哪种重置**：

| 类型 | 谁触发 | 在哪看 | 性质 |
|---|---|---|---|
| **官宣广域 RESET** | Tibo / OpenAI | 官方 X 原帖；追踪站只作公告索引 | 无固定排期，常用于里程碑或故障补偿 |
| **静默平台重置** | OpenAI 后端或限额配置发布 | 产品 usage 状态 + 同时段多账户第一手实测 + 排除各自正常周期；官方限额变更只作上下文 | 可以没有 reset 帖；未获官方范围声明时只能称「大范围观测到」，不能称「全员」 |
| **BANKED reset** | Tibo 推文 | 官宣：追踪站 API（`type=credits`）；到账确认：ChatGPT 产品内余额 | 一次性「存着随你用」的额度包，**到账后不自动消耗**，由用户在 usage 页手动兑现；官宣 ≠ 人人到账（有过分批延迟）。触发形态含里程碑庆祝与故障补偿——§1 所述 rollout 延迟补偿属后者（按无访问天数累积，可一人多笔；2026-09 GPT-6 Astra 补偿即此形态） |
| **账户级周重置** | 系统按该账户当前用量窗口 | ChatGPT 产品内「Next reset: …」 | 每人时间不同；使用 Full reset 也会改变周重置日期，不从订阅开通日推算 |

## 入口分流

- 每次调用先按[本地预测反馈](references/forecast-feedback.md)读取已有记录；查询获得相关事件
  证据后回填未决预测。只读记录为空时不创建文件；提出新预测时保存窗口、依据与本轮反馈。
  实际抓取外部数据的调用先落 findings 记录，record/review 用 evidence_refs 挂链（schema 与
  规则见该文档「findings：原始读数层」节）。
- 用户已经知道结果，追问「为什么漏了 / 哪一环没覆盖 / 下次怎么避免」→ 切到**历史证据链
  诊断**：按当时可得的索引、原帖全文、reply / quote / parent 覆盖、解析结果与 findings 逐层
  定位；没有当轮原始记录时保留「获取 / 解析 / 提炼 / 记录哪一步丢失 = unknown」。不要重复查询
  已知结果来代替诊断，也不要再次核对用户已明确说不用查的 banked reset。用户同时明确要求
  当前账户状态，或当前读数会改变这次诊断时，才并行走账号 SOP；这一分流不阻止明确的实时查询。
- 裸调用（没带具体问题，只想知道现在什么情况）→ 组合执行：台账回看 → 公告线（Radar 索引 +
  独立的 Tibo 主帖时间线 + 有界 reply 发现，按 §1 三腿）+ 故障线（§1）→
  本机落地状态（§2 脚本）→ [监测轮的线索决策](#监测轮从信息到可行动信号)与台账回填。
  按输出合同先给当前重置状态结论，再附下一窗口主判断（走预测路径）；公告线、故障线与
  本机扫描的每次实际抓取先落 findings 记录，回填时用
  evidence_refs 挂链（见[预测反馈的 findings 节](references/forecast-feedback.md)）。**§2 之后必须再跑一次实时 banked 查询**（`scripts/query_usage.py`，读法与字段表见
  [账号 SOP](references/account-usage.md)）——§2 的 rollout 快照结构上没有备用重置字段，不跑就
  答不全「现在什么情况」这个最常被问的维度；只取 banked 一个数即可，本条其余部分仍只管重置状态。
  ⚠️ **scan 与 banked 不要 `&&` 串联**：scan_rollouts 无快照时 exit 1，`&&` 会把 banked 查询直接
  短路掉——表面上全套像跑过了，实际少一维（2026-09-19 实测）。两条分开跑，或串联时给 scan
  加 `|| true`。**循环场景下 skill 里的裸命令被 `same-cmd-resend-guard` 拦**（端点抖动失败一次
  后逐字节重发即拦）——命令开头加 `cd <skill 绝对路径> &&` 换结构即放行（2026-09-19 实测）。
  定时循环（如 `/loop`）重复触发时，若距上次检查间隔很短（<10 分钟）且上轮无改判信号，可只跑
  公告线确认无新官宣、跳过 incidents/banked/本机扫描全套；这是降成本的取舍，未查的维度
  仍标 uncovered。间隔正常、台账里的线索到达复查条件，或上轮出现过新信号时仍跑全套。
  **按时段降频**（与按间隔那条正交，两者叠加）：Tibo 睡眠时段（太平洋 1AM–8AM = 北京 16–23）
  只跑公告线一个请求确认无新官宣，跳过 incidents/banked/本机扫描全套——官宣型重置从不落在他
  睡眠时段（历史模式，见「Tibo 的时间写法」节），补偿型不依赖他的作息。**降频不能省掉新条目
  的全文判读**：Radar 成功返回比上次已裁决更新的索引项时，先按 §1 读取原帖全文，再决定是否
  继续降频；`official_window=null` 不能提前结束。**升级例外**包括：`official_window` 明确给窗；
  正文出现未来承诺；正文中的时间、类型或范围会改变安排；或台账里已有未决承诺到达跟进条件。
  命中任一项就升级回全套，并按承诺的改判条件跟进；都未命中才保留单请求降频。代价要说清：
  睡眠时段万一发生无官宣的静默重置，会延迟到活跃时段才发现——静默重置也是人触发的，历史
  模式支持睡眠时段不会发生，按可接受处理。（2026-09-18 用户拍板保留正常降频分支；2026-09-24
首次实战：睡眠时段裸调用因 Tuesday 承诺跟进到期升级全套——到期项从 summary 的
`due_for_followup` 直接读（见「监测轮」step 1），不用翻 rationale。）
  **正常轮与覆盖自审**：固定检查腿是当前已知来源的起点，不是完整信源表，更不保证「不漏
  新重置」。每轮按下文的线索决策处理新证据、未决问题与反馈；连续无新信号也要在下一次
  正常轮检查是否出现了值得追查的来源、上下文或反证。用户问「有没有漏信号 / 别人怎么预测」
  时，直接核对来源盲区与当时可得信息，不能用「全套已跑」作答。
  点名额度/余额本身的问法整条走账号 SOP，本条只管重置状态。
- 本 Skill 改善的是**每次调用或宿主已安排循环时**的读取、判定和记录；它本身没有后台调度、
  主动通知或 ACK 机制。没有另行部署并实测这些运行层，就不能声称已保证持续发现、送达或确认已阅。
- 用户问「我们几个账号 / 都用完了吗 / 还有两个满额 / 还有几次 Full reset」→ 先读
  [逐账号额度查询与网页登录恢复](references/account-usage.md)。
- 用户问「Tibo 说了什么」或明确只要官宣 → 查**公告路径**。
- 用户问「下一次是什么时候 / 明天会不会重置 / 值不值得等」，包括上一轮刚重置后的追问 →
  查公告后读[下一轮重置预测](references/next-reset-forecast.md)，给出主判断、依据和更新时间。
  默认继承上文的重置类型；明确问个人周期时仍走账号 SOP，不用个人周重置日期代答全局预测。
- 用户说自己的 weekly/5h 回到 100%、`Next reset` 改了，或贴出 usage 截图 → 先把它记为
  **该账户的直接观测**，再查是个人周期还是跨账户事件。
- 用户明确说「肯定又重置了」且聚合器无记录 → 立即走**静默重置路径**；禁止重复查询同一
  聚合器后再次用空结果驳回用户。
- 用户只问当前剩余或下一次周期重置 → 同样进入账号 SOP 的实时查询；需要解释历史跳变时
  再走 §2 的 rollout 快照。当前余额查询不要求先跑整段历史重建或重查公告。
- 想跳过网页手动登录、把日常 Chrome 已登录的 Google 账号直接接到隔离查询 profile →
  `scripts/launch-usage-profile.sh <a|b>` 建/开隔离 Chrome profile，`scripts/import-google-cookies.py --profile <a|b>`
  搬运 `.google.com` 系 cookie（机制与安全论证见脚本自身 docstring，2026-09-15 验证过）。
- 想**自动**驱动隔离 Chrome 查第二账号用量 → `node scripts/read-usage-profile.cjs`（依赖
  `~/.chrome-profiles/tibo-cdp/` 的 playwright；默认 profile a）。读模式直接解析当前登录账号
  usage；加 `--drive-login` 在未登录时自动点 `Continue with Google` 驱动到 Google 账号选择器
  并列出全部账号。**实测边界（2026-09-16）**：隔离 profile 无 Google 会话 token，账号选择器
  每个账号都标 `Signed out`，免密直登做不到——密码/验证码交人工，首登一次后读模式才全自动。
  踩过的可执行细节（代理、真实输入通道对哪个按钮有效、登录态判据、OAuth 轮询）见
  [account-usage.md 隔离 Chrome 自动化节](references/account-usage.md#隔离-chrome-profile-自动化真实输入通道的适用边界2026-09-16-实测)。

## 输出合同：先给结论，再交代边界

用户原话（2026-08-26）：「**你必须给出结论而不是让我给结论。**」

- 第一段第一句必须给出当前证据支持的**唯一最强结论**，禁止用「可能是 A/B/C、请你再看」
  把分类责任交还用户。
- 不确定性用于**收窄结论的属性**，不是取消结论：
  - 只证实一个账户 → 「该账户已经重置；触发原因与影响范围未核实」。
  - 多账户提前跳变且正常周期解释不了 → 「发生了未官宣的大范围静默重置」。
  - 官方明确 all/every → 「官方确认全员重置」。
- 证据、竞争解释和待核字段放在结论之后。拿不到某账户的 `Next reset` 或 banked 状态时，
  仍先对已知事实下结论，再说明哪一层属性不能确认；禁止以「你检查后自行判断」收尾。
- 后续核验动作只用于证实/证伪这个结论，不得把它写成让用户代替 agent 做判断的选择题。
- **未来时间问题要给预测判断。** 有明确预告时先报换算后的官宣窗口；没有时继续分析近期同类
  事件与当前信号，按[预测路径](references/next-reset-forecast.md)给出有依据的主窗口、信心和
  改判条件。「未官宣 / 没有固定排期 / There is no schedule」只说明公告状态，不能独自结束
  回答。资料不足以支持日期时，给出等待是否值得的判断及缺口，不编日期或精确概率。

## 监测轮：从信息到可行动信号

适用于裸调用、预测询问和宿主重复调用本 Skill 的正常轮；明确只问账户余额、只问已知帖原文
或历史漏报归因时，按入口分流缩小范围。降频轮保留上述取舍，但不能丢掉未决线索；未决线索
到达复查条件时升级为正常轮。每轮按以下顺序执行，停止于证据已足够改变或维持当前行动、
且下一次需要什么新信息已经写清，而不是停止于固定端点返回空值。

1. **接上上轮的问题。** 读 `forecast_log.py summary`，先看 `due_for_followup`（窗口已过期或
   即将关闭、尚无定论的预测——到期跟进项从这里第一眼读，不用翻 rationale；closing_soon 的
   阈值定义见 forecast-feedback.md），再从同一
   state-dir 的 `findings.jsonl` 读取最新一条 `invocation=monitor` 原始行；`findings` 子命令
   的紧凑列表不显示 `notes`，不能用它代替交接正文。
   其中的 `notes` 记录上轮尚未解决的具体问题、候选来源、下一次复查条件和用户反馈。上轮
   没有记录就从当前问题与现有预测的 `revision_trigger` 建立这些项，不把空台账说成已覆盖。
   本轮即使只做降频查询，也要在新 finding 的 `notes` 里结转未决项或写明已由哪条证据关闭，
   使它始终能从最新轮次读回；逐字读数仍只放 `readings`，判断不得伪装成原始数据。
2. **先取增量，再问它改变什么。** 以 §1 的 Radar、Tibo 主帖、reply、故障与社区监测为
   基线，比较上次已读的 ID/时间和本次实际覆盖；新发现的旧帖也按**首次发现时间**进入本轮
   判读，不能因为发帖时间早于本轮起点就丢弃。阅读完整正文及承重的 parent / quote / 图片
   文字；同一原帖的镜像和群截图只算一份事实，但群截图作为新的发现路径应保留。先判断
   「这条信息若为真，会改变哪一个关于时间、范围、类型、到账或使用策略的判断」，再决定
   是否追下一跳；不能以 `reset` 等固定关键词或 tracker 标签作语义闸门。
3. **沿问题扩来源，而非无限抓取。** 已知来源空白、上下文指向别处、或候选会改变行动时，
   从帖子引用、回复对象、官方事故、独立账户观测和用户已授权的社区记录中选最有辨别力的
   下一跳。用户已指出「VIP 1群｜一支烟花社区」是本案有效的补充发现源；正常轮若尚无该群
   的新鲜覆盖，就用现有 `read-wechat-messages` 读取其增量，包含纯图片与语音，随后回原帖
   核验。相关群会随用户反馈和实际信号增减，不把这个群写成永远完整的来源清单。群消息是
   发现与交叉核对渠道，转发次数不是独立证据。每跳写明它要区分的竞争解释；查不到时
   保留 unknown 与下一次可执行的复查条件。证据已足以决定下一步、
   或追加来源不会改变判断时停止扩展。
4. **分层输出并保留行动差异。** 已核实的事件、未来承诺和行动提示可构成信号；含糊回复、
   里程碑或第三方解读先列候选，若会改变当前安排仍及时提示其歧义与补证条件，不升格为
   明文承诺。明确区分 `global`、`banked`、`both`、个人周期和类型未明：`global` 到来前可
   评估把原本值得做的工作提前；`banked` 先关注到账、到期与手动兑现，不因它将发放就建议
   提前耗尽现有额度；`both` 分开跟进两类容量；类型未明时可记录账户基线、准备既有任务，
   只在本账户读数与机会成本支持时作可撤销的条件性安排。未发现新信号时只说
   「本轮已覆盖范围内无新增可行动信息」，连同 uncovered / unknown 与下一复查条件报告，
   不说全域无信号。若本轮有新判断，用原帖、上下文和产品观测说明它比上轮多了什么，
   以及是否要通知、等待或改变用量策略；不能把发送回执当用户 ACK。
5. **把下一轮要接的状态落下。** 在本轮最后追加一条 `invocation=monitor` 的交接 finding；
   `query` 写当前监测问题，`endpoints=[]`、`readings={}`，`notes` 写本轮 UTC 检查时刻、新线索、已排除解释、
   未决问题、候选来源、各来源覆盖、下次触发条件及用户纠偏。重要判断另按预测路径保存或
   修订预测，并以 `evidence_refs` 链接原始读数。没有新信息也更新下一轮应检查的条件；不得以「连续数日
   没信号」自行拉长宿主调用间隔。Skill 只能规定被调用时的行为，不能凭一次执行证明未来
   定时唤起、消息送达或 ACK 已生效。

## 查证工作流

### 1. 公告路径：Radar、Tibo 主帖与 reply 是三条覆盖腿

**正常轮次必须实际尝试三条腿：Radar、Tibo 主帖时间线、下文的有界 reply 发现。** Radar 可能
完全没有索引一条新的独立主帖；主帖时间线也不含 replies，所以前两条都无新仍不能跳过 reply
发现。宿主没有可用的已登录 X 通道时，reply 腿的执行结果是 `unknown`，不是静默省略。按时段
降频的已批准例外仍按入口分流执行：降频轮只查 Radar 时，把 `main_posts` 与 `replies` 都记为
`uncovered`，不能把结果写成全量无新。

本机已登录且 `twitter-cli` 可用时，主帖入口使用下面的只读命令（v0.8.5，2026-09-23 实测；
帮助与 JSON 输出均核对过）：

```bash
twitter user-posts thsottiaux -n 50 --json
```

把返回项按 `createdAtISO` / `id` 与上次 finding 的主帖游标比较；新主帖逐条读完整 `text`，并保留
`quotedTweet` 关系。若两轮间发帖量超过当前窗口、最旧返回项仍晚于上次游标，扩大 `-n`（最多
200）补齐，不把截断窗口记成 covered。`user-posts` 只列主帖，不能认证 replies。没有该 CLI 的
宿主使用已有可用的 Web/X 原站通道；这些通道也不可用时写 `main_posts=unknown`，不能伪造完全覆盖。

Radar 继续作为结构化索引腿。用 Tibo Radar JSON API 找最新公开公告（2026-08-26 实测 200）：

```bash
curl -s -m 15 "https://codex-reset.com/api/timeline" | python3 -c "
import json,sys
for e in json.load(sys.stdin)['events'][:5]:
    print(e['announced_at'], '|', e.get('type'), '|', str(e.get('summary'))[:100])
    ow = e.get('official_window')
    if ow: print('   窗口:', ow.get('label'), '=', ow.get('start_at'), '→', ow.get('end_at'), 'UTC')
    print('   url:', e.get('url'))"
```

新条目在前。关键字段：`announced_at`（UTC ISO）、`summary`（可能截断）、`url`（原帖）、
`official_window`、`reset_verification_status`。`type` 是内部小写值：`reset` = 广域
重置公告、`credits` = banked/额度包、`boost`/`promo` = 消耗规则类。

**Radar 成功取得新索引项后，必须先读该项原帖全文，再判它是否包含未来承诺或会改变安排的
时间、类型、范围。** 摘要、`type`、`official_window` 与核验标签只用于定位和交叉检查；任何一个
为空都不能短路全文读取。全文判读结果与未决字段写入 finding / forecast；只有全文也无承诺、
台账也没有到期未决承诺时，才能把这一轮记为「已覆盖范围内无新决策信号」。

**摘要截断也会藏住预告**：2026-09-08 实测最新条目的 `summary` 只截到开头玩笑，
`official_window=null`、`announcement_state=none`、核验标签为 pending；
[原帖全文](https://x.com/thsottiaux/status/2097043464538264003) 却明确预告所有付费订阅的全局重置，
时间为发帖当日太平洋 18:00 左右。先读全文再判断，不能按索引字段宣布“无新预告”。
当次发帖北京 09-08 03:24、太平洋 09-07 12:24，故预告换算为北京 09-08 09:00；
这是当次预告的换算案例，不是固定排期，也不是已到账证据。

⚠️ **`type` 是 Radar 编辑者打的标签，不是事件性质的机器判定——跨平台互动也会被打上
`reset`。** 2026-09-05 实测：Tibo 回复 Anthropic 的 Lydia Hallie（原帖：「We've just reset
weekly limits for everyone on a Claude Max plan」，Claude 官方学重置传统），只回了句
「Wow, huge, wonder why!」的调侃，Radar 照样给它 `type=reset`。读原帖是唯一消歧手段；
fxtwitter 响应里的 `replying_to`（被回复人）+ `replying_to_status`（被回复帖 id）就是为
这一步准备的字段。

`url` 已在上面命令的输出里（2026-08-31 起直接打印，免去二次查询），拿到后优先读原帖。twitter-cli 不可用（未登录/未装）时，X 帖正文的制胜通道才是 **fxtwitter 公开镜像 API**（2026-08-30 实测：
免登录、直连即可、返回完整 JSON；**完整正文在 `tweet.text` 字段——不是 `full_text`**，该键
不存在、照抄会 KeyError；note_tweet 长文全文也给，8-29 官宣长文实测 2324 字符完整拿到、以
自然结尾收束；2026-09-24 实测它可整段不可用（12 连败），而已登录 twitter-cli 的
`user-posts --json` 本身就带完整正文——通道排位按能力排，别按文档惯性先打 fxtwitter）：

```bash
curl -sS --max-time 20 "https://api.fxtwitter.com/<user>/status/<status-id>" \
  | python3 -c "import json,sys; t=json.load(sys.stdin)['tweet']; q=t.get('quote'); print(t['created_at']); print('reply_to:', t.get('replying_to'), t.get('replying_to_status') or ''); print('quote:', json.dumps(None if not q else {'id':q.get('id'),'url':q.get('url'),'text':q.get('text')}, ensure_ascii=False)); print(t['text'])"
```

备胎与死路（同日实测）：
- `cdn.syndication.twimg.com/tweet-result?id=<id>&lang=en&token=a`（官方端点，200）：**正文截断
  276 字符**、note_tweet 只给 id 不给内容——只能核对开头与元数据，长文拿不到。
- `publish.twitter.com/oembed`：301 落到 `publish.x.com` 后（加 `-L`）返回 200+JSON，但可见
  文本同样截断（~273 字符、以省略号收尾，截断点与 syndication 相同）——**与 syndication
  同一档**，够核对开头与元数据，拿不到 note_tweet 全文。
- ~~Jina Reader~~ **可用但间歇，不作主通道依赖**：匿名访问 x.com 会因他人滥用被**间歇性全局
  封禁**（403，2026-08-30 实测：封禁数小时后解除，解除后匿名仍能拿到帖子正文；错误信息点名
  触发滥用的第三方账号）；本仓 jina key 已 402 余额尽。fxtwitter 优先，Jina 只作它的备用。
- fxtwitter 不返回回复**内容**（`replies` 字段只是数值计数）。它返回的 `replying_to`
  （被回复人 handle）与 `replying_to_status`（被回复帖 id）足够判断一条已知帖子是否为回复，
  被回复帖本身再用同一条命令取一次；但它**不能枚举主帖下有哪些回复**。主帖零命中、主帖时间线
  无新项，或某个 CLI search 返回 404，都不能写成「没有回复」。
- 已知候选帖（官宣帖、落地帖）的回复链核验有更便宜的路：`twitter tweet <id> --json` 一次返回
  主帖＋replies（作者字段是 `data[].author.screenName`——不是 `userName`，2026-09-24 实测
  50 items，据此确认承诺帖下 Tibo 本人零回复）。它只给「这一条帖下的回复」；「他最近回过谁」
  的发现性扫描仍走下面的网页滚动法。`twitter search`（含 `from:` 查询）实测 HTTP 404，搜索路线不可用。
- **有界 reply 发现路径**（2026-09-23 已登录 X 原站实测能看到一条主帖入口遗漏的旧回复）：
  1. 先固定起点：上次**可靠** reply 检查的 UTC；没有就用本任务窗口或当前未决承诺的起点。
     打开 `https://x.com/thsottiaux/with_replies`，记录本轮 URL、起点与开始时间。
  2. 只记录页面实际显示、作者为 Tibo 的条目：逐条保存 status ID 和 UTC，连续向旧滚动，直到
     页面已越过起点，或出现明确的加载停止 / 资源上限 / 网站失败。网页滚过时间边界只表示观察
     到该处，**不证明区间穷尽**；不得据此写 covered。
  3. 发现会改变安排的承诺、时间、类型或范围线索后即可停止继续翻旧内容，把它形成候选并补证。
     对每个重要候选，用上面的 fxtwitter 单帖命令读取正文、`replying_to_status` 及 `quote` 的
     id / URL / 正文。存在 parent 时再用同一命令读取 parent；存在 quote 且其内容承重时，再按
     quote URL 读取原帖。`quote: null` 是健康的无引用形态，不是未核；只有实际存在的承重节点
     取不到时，相应判断才保持 unknown。
  4. finding 记录 `window_start/window_end`、观察到的 status IDs、最旧可见 UTC 与停止原因：
     `boundary_observed` / `loading_stopped` / `resource_stop` / `site_failed` / `not_logged_in`。
     没有登录态或网站失败即 `unknown`；到边界但只有网页滚动证据即 `partial`，阴性结果只能写
     「本轮观察到的回复中无相关线索」。
- 每轮按对象写回复覆盖：`covered(candidate_chain:<id>)` 只用于一个已知候选的正文及其实际存在的
  parent / quote 承重节点已完整核验，或某个接口提供了真实穷尽信号且记录了明确范围；
  `partial(<window>)` 用于有界网页
  观察；`uncovered` 表示本轮只有结构上不含 replies 的主帖/镜像入口；`unknown` 表示 reply 通道
  失败或不可用。后三种都不能宣布该时段没有回复或全局无新信号。主帖入口始终只算 main-post
  coverage，不因它返回零条或返回完整正文而升级 reply coverage。
- **落地确认帖的回复链要读；tracker 的条目数不等于事件数**（2026-09-10 实测）：09-08
  「All reset for everyone」官宣帖下，Tibo 回复「You forgot the part where I reset usage
  twice in the middle」——正式落地之前当天已中途全局重置两次，这个口径只存在于回复里。
  codexrunway 把这条回复标成了**第二条独立的** Completed Global reset（Confidence 93%）。
  预告＋中途加码＋落地是一轮事件（归并规则见 next-reset-forecast），读回复用同一条
  fxtwitter 命令；回复帖 id 从 tracker 页面里的 x.com 状态链接提取（2026-09-10 即从
  codexrunway 静态 HTML 中 grep 得到），fxtwitter 自身没有 replies 列表。

`codexlimitwatch.com/codex-reset-history` 与 Radar 都以 Tibo 动态为核心上游，属于**同一来源
家族**，只能互查转录/解析是否一致，不能称为独立双源。**LunarWerx Codex Forecast**
（`codex.lunarwerx.com`）介于两者之间：它的**核验腿**独立（站点自述且 meta description 实测
「checked against OpenAI's own status page」），但**数据上游**仍是公开重置记录（含 Tibo 动态、
社区描述其模型由 Tibo hints 驱动）——所以它适合作「第三方对 Tibo 信号的**解读**交叉验证」
（2026-08-30：对 celebration 帖它独立给出同样的「明天重置」读法，标注 95% confident），
**不能当「独立观测到重置事件」的第二源**，否则就犯了本 skill 警告的同源错误。它是 SPA，
静态抓取只能拿到 meta 与壳，正文内容经 WebSearch 引用。HTML
`codex-reset.com/tibo` 是 SPA，静态内容可能滞后；只作人类视图。

**codexrunway.com**（`www.codexrunway.com`，2026-09-01 实测静态可抓、无需 JS）同属这一家族，
但有两个便宜的附加值：给出**带概率的预测窗口**（实测「≥65% 概率、窗口为 PT 当日全天」），
以及会**主动引用官方故障帖**。预测仍是同族解读，不算独立观测源。
**预测腿：可抓 `www.codexrunway.com/api/status.json`（2026-09-18 起纳入裸调用轮询）**——静态页
之外还有这个 JSON 端点，给三个便宜信号：①`events[]` 里每条 completed 事件带 `confidence`
（09-12 全局重置实测 0.96）；②`Expected next reset` 字段——**它给 `None` 本身就是信息**，连最
激进的第三方预测器在 Tibo 沉默超窗后都不再外推，比自建窗口更该参考；③`monitor.status`
自健康。定位说清：它验证的是「多一个独立预测读数」，**不**验证「读它提高了预测准确率」——
至今没有用它做过 hit/miss 回测的完整周期（台账首次真实预测核验仍待未来调用完成），所以是
「值得进循环的便宜交叉信号」，不是「已证明提升预测质量」。抓取：`curl` 直连该端点，3 次重试
（同其他端点，会间歇抖动）。⚠️ **事件完成判定的字段是 `kind=='reset_completed'`，不是
`status=='completed'`**——按 status 过滤会读到 `completed: 0` 的错答案（2026-09-19 实测）；
可直接复制的过滤：`[e for e in d['events'] if e.get('kind')=='reset_completed']`，再按
`announcedAt` 排序取最新。

**Radar 索引不到官方故障线——这是公告路径的结构性盲区。** Radar 只索引 @thsottiaux，而
ChatGPT/Codex 的故障由 **@ChatGPT** 账号和 **status.openai.com** 发布。Tibo 的重置惯例上有
两个触发（里程碑庆祝、**故障补偿**），漏了故障线就漏掉一半的预测信号。2026-09-01 实测教训：
@ChatGPT 在北京 9/1 02:30 发「ChatGPT Work isn't working right now」，只跑 Tibo 通道的那次
回答完全没看到它，7 小时后才从第三方 tracker 的引用里发现。**每次回答前把故障线一起查。**

```bash
# 官方状态页（2026-09-01 实测 200，返回 Partial System Degradation + 未解决事故）
# 重试是必须的，不是保险：不带重试的裸命令实测会间歇吐 JSONDecodeError 而不是「站点挂了」
for i in 1 2 3; do
  o=$(curl -s -m 20 -A "Mozilla/5.0" "https://status.openai.com/api/v2/summary.json")
  if printf '%s' "$o" | head -c1 | grep -q '{'; then
    printf '%s' "$o" | python3 -c "
import json,sys
d=json.load(sys.stdin); print(d['status']['description'])
for c in d.get('components',[]):
    if c.get('status')!='operational': print(' 异常组件:', c['name'], '→', c['status'])
for i in d.get('incidents',[]): print(' 未解决事故:', i['name'],'|',i['status'],'|',i['created_at'])"
    break
  fi
  echo "  attempt $i 空响应，重试中"; sleep 3
done
```

@ChatGPT 的帖子用 fxtwitter 同一条命令，把 `<user>` 换成 `ChatGPT` 即可。**本节所有外部端点
（Radar、fxtwitter、状态页）都会间歇抖动**——本机走代理时实测同一分钟内 `status.json` 取空
而 `summary.json` 成功、Radar 首跑吐空响应体直接 `JSONDecodeError`、fxtwitter 连续两次
`SSL_ERROR_SYSCALL` 第三次成功（2026-09-07 独立复测）——**失败先重试 2–3 次再判定端点
不可用**，一次失败不构成「站点挂了」。

**⚠️ `summary.json` 只看当前绿不绿，读不到历史故障——必须同时查 `incidents.json`。**
只跑 summary 会漏掉两类事件，都落在「上一轮官宣后无新重置」窗口内，是「补偿型重置／静默重置」
（Tibo 两个触发）的候选触发点：①「补偿型」= Codex/Work 故障（例 09-14 02:46 UTC「Elevated
error rates for Codex and ChatGPT Work」）；②**「静默型」= 平台主动调查意外额度重置**（例
09-09 17:29「Investigating unexpected usage limit resets」，正文 "Some Codex users may be
experiencing unexpected usage limit resets"）。**第②类比①更直接，且名字不含 Codex——只按
Codex/Work 命名 flag 会漏掉它。** 只看当前状态页 = 放弃这两条预测信号。每轮把下面这条和
summary 一起跑：

```bash
# 近期 incident + 完整正文（summary.json 看不到）。flag 命中两类：
#   [补偿型] 名字含 Codex/Work
#   [静默型] 名字或正文含 usage limit / unexpected reset / billed / quota（不依赖 Codex 命名）
for i in 1 2 3; do
  o=$(curl -s -m 20 -A "Mozilla/5.0" "https://status.openai.com/api/v2/incidents.json")
  if printf '%s' "$o" | head -c1 | grep -q '{'; then
    printf '%s' "$o" | python3 -c "
import json,sys,re
d=json.load(sys.stdin)
silent=re.compile(r'usage limit|unexpected.*reset|billed|billing|quota|payment',re.I)
for inc in d.get('incidents',[])[:14]:
    name=inc.get('name','')
    body=' '.join((u.get('body') or '') for u in inc.get('incident_updates',[]))
    f=''
    if 'Codex' in name or 'Work' in name: f+=' [补偿型]'
    if silent.search(name) or silent.search(body): f+=' [静默型-额度]'
    print(f\"{inc.get('created_at','')[:16]} | {inc.get('impact',''):6} | {inc.get('status','')} | {name[:52]}{f}\")"
    break
  fi
  echo "  attempt $i 空响应，重试中"; sleep 3
done
```

命中候选时用 `incident_updates[].body` 读正文再判：含补偿/reset/额度措辞 → 升级为强信号（对照
09-12 的 "reset is also landing by midnight today"）；纯错误率抖动无补偿措辞 → 只记候选。
`impact: none` 且 <2h 恢复、正文无额度语义的按噪声忽略。

**③ 社区 monitor —— 静默重置下唯一的独立第二眼，纳入常规轮询。** Radar 只索引 @thsottiaux、
incidents 是 OpenAI 自述；两者都空时，社区实测是能独立发现"静默重置已发生"的通道。每轮和上面
一起跑（两站同源家族，只作交叉不增独立计数；verdict=No 是正常态，只有变 Yes 才触发静默路径）：

```bash
# 社区 reset monitor（独立第二眼，判 verdict）。http!=200 就跳过，不阻塞。
for u in "https://hascodexratelimitreset.today" "https://lidless.app/did-codex-reset-today"; do
  f="/tmp/tibo_c_$(echo "$u"|md5).html"
  code=$(curl -sS -m 15 -A "Mozilla/5.0" -o "$f" -w '%{http_code}' -L "$u" 2>/dev/null)
  [ "$code" = "200" ] || { echo "  $u http=$code 跳过"; continue; }
  python3 -c "
import re,html
t=open('$f',encoding='utf-8',errors='replace').read()
txt=re.sub(r'<script.*?</script>|<style.*?</style>','',t,flags=re.S)
txt=re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',txt))).strip()
m=re.search(r'(No sign.{0,80}|Verdict: (Yes|No))',txt)
print('  monitor:', (m.group(0) if m else 'verdict 未解析')[:90])"
done
```

`verdict` 变 **Yes**、或 lidless 文案从 "No sign" 变实锤 → 立即走 §3 静默重置路径（用实时 API +
同时段实测交叉，按证据范围命名，不外推全员）。verdict=No / 解析不到 → 正常态，不动。

### 2. 本机取证：Codex rollout 快照 = 可脚本化的第一手账户证据

`~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl` 每轮都写 `rate_limits` 快照。**这比引导
用户去看产品页更强**：可回溯历史、能把归零定位到分钟级区间、不需要 GUI，也不需要让用户替你
看屏幕（2026-09-01 实测：5 天 48748 条快照，重建出 7 次重置的完整时间线）。字段形状：

```json
{"limit_id":"codex","primary":{"used_percent":76.0,"window_minutes":10080,"resets_at":1788753995},
 "secondary":null,"credits":{"has_credits":false,"balance":"0"},"plan_type":"pro"}
```

本节命令针对默认 `~/.codex` 主页；使用自定义 `CODEX_HOME` 时，将本节 auth 与 sessions 路径
统一替换为同一个已授权主页，不能将两个主页的快照混用。
`resets_at` 是 epoch 秒；`window_minutes` 10080 = 周窗口、300 = 5h 窗口。快照中的
`credits` 与备用重置的区别，见[账号 SOP 的字段读法](references/account-usage.md#实时-api只读一个明确账号)。
**要备用重置数量就别在这份快照里找**：该键只有 `balance`/`has_credits`/`unlimited`，
实测 143 万条快照 `has_credits` 恒为 `false`，**它不携带 banked 数量**。这是「换源」，
不是「这次没查到」——直接跑 `scripts/query_usage.py`。

**会给出貌似合理错答案的陷阱（每一条都不报错；1–3 于 2026-09-01 同一次会话里连踩，4 于 2026-09-03 补）**：

1. **`primary` 槽位不固定指向周窗口。** 同期快照里 `primary` 有时是 300（5h）。按
   `window_minutes` 分桶，别假设 `primary` = weekly——混着读会把 5h 窗口的 0% 当成周额度重置。
2. **`limit_id` 有多个桶，其中有恒零的诱饵。** 实测同期存在 `codex`、`premium`、
   `codex_bengalfox`，而 `codex_bengalfox` 的两个窗口**恒为 0%**，混进序列会凭空造出几十次
   「重置」。**先 `limit_id == "codex"` 过滤再做任何判断。**
3. **`resets_at` 每条快照都秒级微漂。** 用「`resets_at` 变了」判重置会得到几百个假阳性；
   判据用 `used_percent` 大幅下降（>20 点）。
4. **目录日期 ≠ 时间戳范围——按 `sessions/<Y>/<M>/<D>/` 数天数会静默少采样。** 跨午夜的
   长 session 把**次日**的时间戳继续写进**前一天**的目录，所以「扫最近 N 个日期目录」拿不全
   最近 N 天。实测同一分钟窗口 `08-28 00:25–00:29`：扫 7 个目录得 9 行，扫 9 个目录得 **67 行**
   ——少掉的正是长 session 交错写入的那些行，**而多账号交错恰好就长这样**。当天决定性的
   `used 0%→82%` 记录就住在前一天的目录里，按目录数天数的版本结构上看不见它。
   **修法：多扫 2 天目录，再按时间戳过滤**（已内置在 `scripts/scan_rollouts.py` 的
   days+2 目录扫描与时间戳裁剪）。

**窗口锚点的形状——注意「干净 +7d」本身不是重置的证据**（2026-09-01 与
2026-09-03 两次实测）：

- **干净 +7d**：新 `resets_at` ≈ 归零时刻 + 窗口长度。这**只说明窗口从归零那刻重新起算**，
  它同时是按钮式重置和「换到另一个有额度的账号」的形状——两者在这个维度上不可分。**单看
  +7d 就叫重置是本节最贵的错误**：2026-09-03 实测的一台机器上，8 天内出现 **8 次**干净 +7d
  （按新锚点去重后；去重前 9 条），按这条读会得出「静默重置 8 次」，而真相是账号轮替。要
  定性必须再过下面的多账号归因检查。
- **锚点回拨**：新锚点被设到**过去**（实测 -12.6h、-23h，后者甚至早于它替换掉的旧锚点）。
  历史上归因为窗口重排 / 限额配置切换，但**在多账号机器上它同样是「切回另一个账号」的
  签名**（那个账号的窗口开得更早）——先排除账号，再谈配置切换。
- **账号切换**：见下面的多账号检查。它可以伪装成上面任何一种。

**并发 session 会让同一次重置输出两条。** 滞后的 session 先报旧值、再各自更新，于是脚本会
打印两条时间相邻、**新锚点相同**的归零记录（实测 08-28 00:26 与 00:27 是同一次）。**按新锚点
去重再数次数**，否则会把 7 次数成 8 次。

⚠️ **别把「并发 session 滞后」当成万能解释——它专门用来掩盖多账号。** 按锚点去重合并的是
**新锚点相同**的两条，机械上碰不到锚点不同的记录；真正的风险在**判断层**：看到两条时间相邻
而数值矛盾的记录，顺手归给「滞后 session」，就会漏掉账号交错的线索。
**`used_percent` 是已用量，正常使用本来就会上升**。短间隔内大幅上升并伴随锚点回拨时，
核对身份、取样间隔、会话来源和限额配置；不能仅凭形状排除其他解释。
2026-09-03 实测的 `used 0%→82%`（锚点 09-04 → 09-03）是当时检查账号轮替的重要线索。

它**不在归零列表里**，而在脚本第 1 步的「回跳」输出里（两段是不同的代码路径）——去归零输出
里找它一定找不到。所以：**先读第 1 步的回跳行，再去数第 2 步的归零次数。**

另注：脚本本身**不做去重**，第 2 步会把重复的两条都打印出来（锚点相同即可辨认）；
「按新锚点去重再数次数」是人工步骤。

#### 多账号归因检查

本节采用的 rollout 快照**不记 `account_id`**，仅凭这些无身份快照不能区分账号交错与真实重置。

**先说清楚一个结构性陷阱：直觉上的那个检查永远返回「只有一个」。** `~/.codex/auth.json`
只保存**当前登录的那一个**账号，切走的账号不留痕；`~/.cc-switch/cc-switch.db` 只记它自己
管过的条目，手工 `codex login` 换的账号它完全看不见。**拿这两处的当前状态去回答「历史上
用过几个账号」，是用当前快照回答历史问题——它不会报错，只会给一个貌似合理的错答案。**
（2026-09-03 实测：一台确有两个 Pro 账号在轮替的机器，这两个探针都报「只有一个」，导致整份
归因写反。）

按下面 A/B/C 检查收集线索，再按 §3 的证据范围命名。身份不一致证明机器用过多个账号；
要判断某次跳变的原因，仍需把前后读数绑定到具体身份。

没有发现异常也**不能证明单账户**：A 只保留最近刷新时刻，B 不覆盖手工登录，C 看不到锚点
恰好单调的账号轮替。若用户尚未说明该时段是否切号，且答案会改变历史归因，再问一次；
已经确认的事实不重复问。身份无法分离时报告混合记录的归因限制，不把检查全绿当证明。

**执行顺序：先跑本节最后那段重建脚本**，取得归零区间与 C 的回跳；再读 A，只有用户确实
使用 cc-switch 才读 B。A 的刷新时刻需要与归零区间对齐。

**A 层 —— 当前身份 +（指示性的）最后一次刷新时刻**

分别读取身份与刷新时刻，两者证据强度不同：

1. **当前登录身份**（`id_token` 解出的 email / `chatgpt_account_id` / plan）——这是硬事实，
   在 B 层适用时作身份比对。
2. `last_refresh` 时刻——**指示性，不是判决**：
   - **语义未标定**：字段名就叫 refresh，token 续期也会写它。实测该机 `last_refresh` 与
     `id_token` 的 `iat` 同刻、`exp` 恰好 +3600s，**与一次纯 token 续期无法区分**。所以
     「落在归零区间内」不能单独定案；归因条件见 §3。
   - **覆盖面只有一个点**：它是单个时间戳，最多解释**一个**归零区间。本机 7 天窗口内有
     10 个归零事件，A 层对其余 9 个**什么都没说**。
   - **不落在区间内 ≠ 该层干净**：只说明「最近一次刷新不在这个区间」，更早的切换早已被
     覆盖掉（这正是 `auth.json` 只存当前状态的后果）。

```bash
python3 -c "
import json,os,base64
d=json.load(open(os.path.expanduser('~/.codex/auth.json')))
t=d.get('tokens') or {}
print('last_refresh:', d.get('last_refresh'), ' <-- 与归零区间对齐')
print('account_id  :', t.get('account_id'))
idt=t.get('id_token')
if idt:
    p=idt.split('.')[1]; p+='='*(-len(p)%4)
    pl=json.loads(base64.urlsafe_b64decode(p))
    a=pl.get('https://api.openai.com/auth') or {}
    print('email       :', pl.get('email'))
    print('plan_type   :', a.get('chatgpt_plan_type'))
"
```

**B 层 —— 这台机器上还存过哪些账号（仅在用户确实使用 cc-switch 时检查）**

这是历史归因的可选线索，不是账号盘点入口。用户明确不用 cc-switch 就跳过本层，转官网和
Google 已登录账号。（逐账号额度查询的入口裁定见 account-usage：这批账号 2026-09-08 已
裁定不用 CC Switch 管理——B 层的 providers 记录只作邮箱线索，不为查询额度重开此裁定。）
下面的 `providers` 只证明其记录里出现过的身份，不能证明账号清单完整。

`profiles` 表实测可能是空的（2026-09-03 该机 0 行），账号存在 `providers` 里；每条的
`settings_config` 内嵌一个完整 `auth` 对象，解它的 `id_token` 才能拿到身份。

```bash
python3 -c "
import sqlite3,os,json,base64
db=os.path.expanduser('~/.cc-switch/cc-switch.db')
if not os.path.exists(db): raise SystemExit('no cc-switch.db (不构成单账户证据)')
c=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
for pid,name,cur,cfg in c.execute(\"select id,name,is_current,settings_config from providers where app_type='codex'\"):
    auth=(json.loads(cfg).get('auth') or {}); tk=auth.get('tokens') or {}; email=None
    if tk.get('id_token'):
        p=tk['id_token'].split('.')[1]; p+='='*(-len(p)%4)
        email=json.loads(base64.urlsafe_b64decode(p)).get('email')
    mode=auth.get('auth_mode')
    kind='ChatGPT 账号(计入)' if mode=='chatgpt' and email else 'API-key provider(不是账号,忽略)'
    print(f'{name!r} is_current={cur} auth_mode={mode} email={email}  <- {kind}')
"
```

判读规则（**只数真正的 ChatGPT 订阅账号**）：`app_type='codex'` 底下混着 API-key provider
（实测该机有一条 DeepSeek，`auth_mode=None`、`email=None`）——那不是 ChatGPT 账号，**不参与
账号计数**。只看 `auth_mode='chatgpt'` 且 email 非空的行。

- 这类行里出现**与 A 层不同的 email** → 两个账号的直接证据（2026-09-03 与 2026-09-04 两次
  实测都是这样命中的）。
- 只有一行且与 A 层一致 → 该层无阳性证据。
- `email=None` 或 `auth_mode` 非 `chatgpt` 的行 → **忽略**，别拿它跟 A 层比「不一致」。

⚠️ **`is_current=1` 不是「当前登录」的判据。** 它只表示 cc-switch 自己最后切换到谁；用户绕过
它手工 `codex login` 之后这个标记不会更新。2026-09-04 实测：该机 is_current 指向的
email 与 A 层 `auth.json` 显示的实际登录 email 是**两个不同的真实账号**——同一份
读数同时演示了这条陷阱和 B 层的命中形态（两处 email 不一致本身就是多账号的直接证据）。
**当前 CLI 登录身份以 A 层为准；网页身份另从网页核对。is_current 只回答旧工具记录过谁。**

B 层安静**不代表单账户**——它看不见手工 `codex login`。

**C 层 —— 行为签名：锚点回跳（只靠 rollout，A/B 都失效时仍然有效）**

回跳检查不依赖 auth 文件，但它只检测快照形状，不输出账号身份。窗口配置、取样间隔与
账号交错都需要核对；判读：

- `回跳次数 = 0` → 没有阳性证据（**不等于单账户**，见本节开头的闸门说明）
- 回跳带 **used% 上升** → 标记需核对的交错/配置线索，不直接写成多账号事实。
- **大幅**回跳（实测 10.9h、18.7h）→ 优先查账号切换与限额配置变化，归因条件见 §3。
- 回跳存在但**既不大幅、也没有 used% 上升**（中间带）→ 保留待核，不忽略，也不直接定性。
  这一带里限额配置切换与账号切换真的不可分；不要因为「看起来不够大」就默默放行。
  另外注意：`clean` 判定用的是 600 秒容差，而相邻快照间隔实测可达 9.65h——**取样稀疏本身
  就会把一次干净重置误标成锚点回拨**，所以单凭一个中间带回跳不足以下多账号结论。

- ❌ **「同分钟 + 同锚点 + 不同 used%」不是账号交错检测器**（2026-09-16 实测否决，这条路已堵，
  别再花一轮去试）：全量快照里这种组合有 **12924 处**，绝大多数是并发 session 的相邻整数
  （`6.0/7.0`、`7.0/8.0`）的轮询滞后，且**多数只涉及 1 个 session**——纯噪声，与账号数无关。
  它看起来像个便宜的机械信号，但噪声比信号高几个量级。免费的账号交错信号目前只有上一节的
  锚点回跳与 `try again at` 指纹，没有第三种。

**辅助判据 —— 归零前的用量峰值（先验，不是判决）**

- **打满触发**（归零前 99–100%，且几十秒到几十分钟内归零）：先验偏向「撞上限后换账号」。
- **非打满**（归零时用量明显没满，实测 82% / 72% / 50%）：先验偏向平台推送，因为平台重置
  不挑你用到几成。2026-09-03 实测：**3 次**非打满归零（去重后；去重前 4 条）**一条不差地各
  对上一条 Tibo 公告**。注意公告时刻与按钮时刻的关系并不固定：08-28 那次按钮早于发帖 9 分钟，
  08-31 那次的归零区间（10:10–12:06）反而把发帖时刻 10:34 包在里面。**公告时间不能当落地
  时刻用**，只能用来判断「这次归零有没有对应的官宣」。

**别把它当判决**：同一份数据里 08-27 那次是打满触发、却落在一条 Tibo 公告前 62 分钟——平台
重置**可以**发生在你已经撞上限的时刻，那时它看起来就是打满触发。峰值只调整先验，定性仍然
按 §3 的证据范围命名。

**免费的账号指纹 —— usage-limit 报错里的 `try again at`**

撞上限时 Codex 会写一条 `task_complete` 错误，正文形如：

```
You've hit your usage limit. Visit <codex usage settings URL> to purchase more credits
or try again at Sep 7th, 2026 3:23 PM.
```

`try again at` 是产生报错的登录上下文当时报告的重置时刻。**非单调回退**可提示账号交错，
但不携带身份，也不能独自排除窗口配置变化。下面这条
命令扫全量历史并自己标出回退，实测该机打印 **17 次**（两个桶来回交替时每次切换都记一次，
所以它是「有没有交替」的指示器，不是「切了几次账号」的计数）。最硬的一处是 `08-25 14:46`
同一分钟内出现 4 个不同取值——几个并发 session 各挂在不同账号上同时撞墙。（不是「聚成两簇」：
每次重置都会生成新窗口，取值本来就一直在变，簇数不是信号，单调性才是。）

⚠️ **用指纹支持某个具体归因前，先核对回退时刻是否落在该区间内。** 序列在 A 段单调、在更早的
B 段有回退，不构成 A 段账号交错的证据——「这台机器历史上换过号」和「这次跳变是换号引起的」
是两个命题，共用一条命令的输出不等于共用证据。实测踩过（2026-09-16）：引用 09-09→09-15
的取值论证该区间账号交错，实际该区间零回退、取值单调递增，全部回退都在 08-25→09-08，
即被论证区间之前。这类错误的成本不在算错数字，而在于它把一个「原因未核实」的跳变写成了
确定性归因——**这正是 §3 要求先按证据范围命名的原因**。

```bash
python3 -c "
import json,glob,os,datetime,re
BJ=datetime.timezone(datetime.timedelta(hours=8))
T=lambda x: datetime.datetime.fromisoformat(x.replace('Z','+00:00')).astimezone(BJ)
rows=[]; prevdt=None
for f in sorted(glob.glob(os.path.expanduser('~/.codex/sessions/*/*/*/rollout-*.jsonl'))):
    for line in open(f,encoding='utf-8',errors='replace'):
        if 'usage limit' not in line: continue
        try: d=json.loads(line)
        except: continue
        e=((d.get('payload') or {}).get('error') or {})
        m=e.get('message') if isinstance(e,dict) else None
        if not m or not d.get('timestamp'): continue
        v=m.split('try again at')[-1].strip().rstrip('.')
        try: dt=datetime.datetime.strptime(re.sub(r'(\d+)(st|nd|rd|th)',r'\1',v),'%b %d, %Y %I:%M %p')
        except Exception: continue
        rows.append((T(d['timestamp']),v,dt))
rows.sort(); prev=None; back=0
for t,v,dt in rows:
    if v==prev: continue                      # 只看取值变化
    mark=''
    if prevdt is not None and dt<prevdt:
        back+=1; mark='   <-- 非单调回退：需核对账号或窗口配置'
    print(f'{t:%m-%d %H:%M} | try again at {v}{mark}')
    prev=v; prevdt=dt
print(f'\n非单调回退次数: {back}   （只报告形状，不证明账号数量或归零原因）')
"
```

**归零只能报区间，不能报时刻。** 相邻快照间隔可达小时级（2026-09-03 实测最宽 **9.65h**；
7 天窗口内有 39 个相邻间隔超过 600 秒），写「落地在
A–B 之间」，别把「首个见到 0% 的快照时间」当成到账时刻。**另外快照只更新到用户最后一次跑
Codex 的时刻**——下「至今没有重置」之前先看最新快照有多旧，那之后是盲区。
按账号 SOP 读取实时接口或产品页可以确认当前状态，但补不上过去的历史盲区。

**rollout 还有一个覆盖边界：每条只观测产生它的登录上下文，历史集合可能混有多个账号，且没有
逐条身份标签。** 没运行过 Codex 的其他账号没有快照，不能从集合的最后一行推断全部账号——
2026-09-04~06 实测快照停在 09-03 连续三个 session 不动（用户一直没跑 Codex，盲区
28h→49h→70h），那只是「这个账号没新观测」，不是「所有账号都没动静」。此时用户从产品 usage
页抄出的**多账号统计**（每个账号的重置倒计时 + 「有 N 次 full reset」）是覆盖全部账号的
第一手观测，证据级别等同产品页，还能直接闭环「官宣≠到账」（09-06 实测：4 个付费账号各显示
两次 full reset，确认前一日官宣的 full banked reset 已全部到账）。引用这类相对倒计时时
折算成绝对时刻并标注折算时刻（读数时刻 + 已流逝时间），别把「21 小时之后」原样抄给用户。

**序列尾部的身份绑定技巧**：`query_usage.py` 返回的 `reset_at` 与扫描输出的最新锚点对拍，
一致即可把无身份混合序列的尾部绑到当前 CLI 账号（2026-09-24 实测：API 09-30 11:31 UTC 与扫描
最新锚点同刻）。它只绑尾部，解不了历史区段。

```bash
# 重建本机周额度曲线 + 多账号回跳检查（上述陷阱已全部内置；2026-09-12 与内联版同窗口逐行对拍一致）
uv run python scripts/scan_rollouts.py --days 7
# 复现历史某时刻的切面（回填台账、复核旧结论时用）：加 --as-of "2026-09-12T17:44:00+08:00"
# 自定义 CODEX_HOME 时：--codex-home <已授权主页>（auth 与 sessions 必须同属一个主页，不混用）
```

### 3. 静默重置路径：查账户事实，而不是继续等帖子

在用户直接观测与公告索引冲突时，按顺序取证：

1. **定账户事实**：记录 weekly 与 5h 是否回到 100%、`Next reset` 是否移动、banked reset
   是否仍在，以及变化是否正好发生在此前已显示的正常重置时刻。产品 usage 页或 `/status`
   只证明该账户，但证据级别高于聚合器的空结果。**用户口头或聊天里转述的产品页观测**（多账号
   额度统计、banked 余额、「有 N 次 full reset」）**记为直接观测，与产品页同级**——不必为了
   「亲眼看」逼用户再截图或跑命令。**本机有 `~/.codex` 就先跑 §2**：它给的是
   同一层证据，但带历史曲线和分钟级归零区间，能直接回答「这次跳变能不能被正常周期解释」。
2. **找同时段实测**：用当前 UTC/PT 日期搜索最近帖子，例如 `Codex reset today back to 100%`、
   `Codex reset again 5h`、`site:reddit.com/r/codex reset today`。优先截图、明确的前后百分比、
   `Next reset` 变化和「banked 仍在」；转载同一条消息不增加独立性。用户说「群里看到的」
   且当前环境有群聊归档能力时，再搜「重置/reset/Tibo」核对群友实测，并分清截图是产品状态
   还是 Radar 转发。
3. **找发布上下文**：搜索 Tibo/OpenAI 是否正在切换 5h/weekly 限额、修计量或处理事故。上下文
   与重置同刻发生只支持因果推断；官方没说「因此重置」就明确标为推断。
4. **按证据范围命名**：
   - 先排除账号轮替。A/B 身份不一致证明机器用过多个账号，不证明某次归零必然由换号引起；
     `last_refresh` 落在区间里也只能作提示。能把该次前后读数绑定到不同身份时才称「这次是
     账号切换」；否则写「混合账号记录，归零原因未核实」，不升级为平台重置。
   - 只有一个账户 → 「该账户已重置；原因未定」，不能外推。
   - 多个不同账户在紧邻时间内回满，但尚未排除各自正常周期 → 「观测到跨账户近同时重置；
     是否为同一平台事件未定」。
   - 多个独立账户的预告 `Next reset`/正常周期均解释不了这次提前跳变 → 「观测到大范围
     静默重置」；同期限额发布只能补上下文，不能代替这项反证。
   - 只有官方明确写 all/every paid account → 才称「全员重置」。

静默事件没有官宣时间戳时，报告「最迟在最早公开证据的时间前已发生」，不要把发帖时间伪装成
精确落地时刻。

### 4. 公告时间换算

`official_window` 存在时优先读其 `start_at`/`end_at`；再按下方规则自己换算一遍。
不一致时报告差异，以操作系统时区数据库的实测换算为准。

### 5. 通道失败时

Radar API 挂 → twitter-cli（已登录时：`user-posts` 拿主帖时间线与完整正文、`tweet <id> --json`
拿已知帖回复链；2026-09-24 实测 Radar 连续 4 次空响应、fxtwitter 12 连败当天，它单独撑起公告与
reply 两腿）→ fxtwitter 读原帖（§1 的命令）→ syndication 官方端点（截断 276 字符，只够核对元数据）→
codexlimitwatch 单源（标注同源镜像）+ LunarWerx（仅 Tibo 信号解读交叉验证，非独立观测第二源）→
WebSearch `thsottiaux reset`
找转录。用户报告产品已变化时，公告通道全空仍要走静默重置路径；全部产品/社区
证据也取不到，才写「只能确认该用户的观测，无法核实影响范围」，不要写「没有重置」。
外部站优先用 `curl` 直连；WebFetch 被安全校验拦截不证明站点已挂。`feed.xml` 的历史实测
比 API 更滞后，不作 fallback。

**循环抓多站时别复用同一个临时文件。** `curl -o /tmp/x.html` 失败（`http_code=000`）时既不
清空也不删除旧文件，下一轮的解析脚本会照常打印**上一站**的内容且不报任何错（2026-09-01
实测：`codexreset.org` 取回 0 字节，输出的却是上一轮 codexrunway 的正文，看起来完全像成功）。
每站用独立文件名，并先判 `http_code` 再解析。

**「他还没发新帖」这个否定断言有明确的尽头。** fxtwitter 只有 `/status/<id>` 端点，
**没有 user timeline**（`api.fxtwitter.com/<user>` 只返回 profile，不含推文列表），无法直接
遍历他的最新推文。所以「无新官宣」只能靠聚合器（同族）+ WebSearch 交叉得到，本质是「这些
通道里没有」，不是「他没发」——按这个强度措辞，并补一句「不等于后端没动作」。twitter-cli
已登录时此界后移：`user-posts` 直接遍历主帖时间线，「本覆盖窗口内主帖无新」可实指；replies
不在此内，不能顺带宣布。

## Tibo 的时间写法是糙的（解读规则）

实测原话：`Reset will land around 14pm PST tomorrow.`（2026-08-23 06:29 UTC 发）

- 「14pm」= 14:00 = 下午 2 点（他混用 24 小时制和 am/pm，照字面取数即可）
- 他常年写「PST」，但美国夏令时是 **3 月第二个周日～11 月第一个周日**，
  期间太平洋实为 PDT（UTC-7）——按**重置落地时刻**的时令换算，不是发推日期
  （跨夏令时切换日的「tomorrow」按发推日偏移计算会错 1 小时）
- 「tomorrow / today」以**他发推时刻的太平洋日期**为锚：`announced_at`（UTC）减 7（PDT）
  或 8（PST）小时得到发推的太平洋日期，再读 tomorrow 指哪天
- 「midnight」同锚（2026-09-12 实测：「a reset is also landing by midnight today」发于
  03:20 UTC = 太平洋前一日 20:20，「today」= 太平洋 9/11，即北京 9/12 15:00 前；
  落地确认帖实际发于北京 16:09）
- 历史模式（非承诺）：重置从不落在太平洋 1AM–8AM（他的睡眠时段），高峰在太平洋下午

## 时区换算（命令已实测，2026-08-23；**macOS only**——BSD `date -j`/`-f`，GNU date 无此参数）

```bash
# 免查时令写法（推荐）：让 OS 自己解 PDT/PST。注意 macOS BSD date 的 -f 不支持
# 直接解析 "PDT" 字样（illegal time format），所以要嵌套
TZ=Asia/Shanghai date -j -r "$(TZ=America/Los_Angeles date -j -f '%Y-%m-%d %H:%M' '2026-08-23 14:00' '+%s')" '+%F %H:%M %Z'
# 输出: 2026-08-24 05:00 CST  ← 太平洋夏令时下午2点 = 北京次日凌晨5点

# 已知时令时的直给写法：夏令时偏移 -0700（PDT），冬令时 -0800（PST）
TZ=Asia/Shanghai date -j -f "%Y-%m-%d %H:%M %z" "2026-08-23 14:00 -0700" "+%F %H:%M %Z"

# 反查：此刻太平洋几点（判断「tomorrow」锚哪天用）
TZ=America/Los_Angeles date "+%F %T %Z(%z)"
```

## 证据纪律（踩过的坑）

- **聚合器没记录 ≠ 没重置**：Radar 与 codexlimitwatch 主要回答「Tibo 公开说了什么」，不是
  「后端账户状态发生了什么」。2026-08-25 的实测反例：两站都停在 8-24，用户却在
  2026-08-25 14:18 UTC 起密集贴出 weekly 回到 100% 的截图/前后值，且多人明确表示原
  `Next reset` 尚未到期或被意外后移、banked 仍在；同日 Tibo 只官宣恢复 Plus 5h 限额。
  正确结论是「观测到未官宣的大范围静默重置」，
  不是「没有新重置」，也不是未经官方范围证明的「全员重置」。
- **先分清证据证明哪一层**：产品页证明一个账户；多个不同账户的同时段实测只证明「跨账户
  近同时观测」，各自的正常周期仍是竞争解释；再证明这些账户尚未到预告重置时刻，才支持共同的
  静默平台事件；官方 all/every wording 才证明全员范围。把这些层级写进结论，禁止一条截图
  外推全局，也禁止一条聚合器空结果抹掉产品事实。
- **tracker 的 confirmed 类标签对未来的预告也会打**（两站均有此形态：codexlimitwatch 给
  8-23 那条预告打了「Reset confirmed」——预告未落地也标 confirmed；Radar 历史上也有）。判「已到账」
  只看落地后的实际信号，不看标签：API 的 `reset_verification_status` 只有 pending/rejected/null
  （2026-08-23 全量 51 条实测：落地两天的「has landed」条目仍是 pending）——**结构上不提供
  「已到账」正向信号**，别去等一个永不触发的字段翻转。到账证据 = Tibo 后续确认推
  （会作为新 event 出现；实测两种措辞：「has landed」类，以及 2026-08-31 的「we have
  now reset usage for all paid subscriptions…」），或产品内余额实测。
- **「celebration」在他的语义里 = 重置动作本身，不是发帖庆祝**（2026-08-30 实战教训：把
  「This celebration is moved to tomorrow as the button was already pressed today」读成
  「只是庆祝帖、无重置」，被两个独立源当场证伪；次日完整兑现——12:24 PT 发「reset will
  land at 6pm PST」预告，19:34 PT 发「hit 25M active users…we have now reset usage
  for all paid subscriptions」落地确认）。他固定把重置绑在用户里程碑庆祝上——
  7M/8M/20M/25M 里程碑均以 banked/reset 兑现，8M 时原话「Tomorrow might be 8M active user
  celebration day」，逼近 9M 时发起过「要不要再重置」的投票（poll 本体
  x.com/thsottiaux/status/2077271889626706300）。所以「celebration 改期到明天」应读作**预告
  明天有一次重置**。
  分寸：这仍是暗示级官宣（他没写「we will reset again tomorrow」字面），结论措辞用「官方
  暗示 + 多个独立 tracker 一致解读 = 大概率有」，并按惯例预测太平洋下午落地；只有官方明文
  才能升格为「官宣确认」。
- **多源时间有张力时先换算再叙述，别糅合**：2026-08-21 官宣 banked reset「8pm PST 前到账」，
  tracker 记落地推为 UTC 8/22 00:50——换算回太平洋是 8/21 17:50，**早于**承诺线；
  而媒体报道「8pm 过了很多账户没收到」。两个来源不矛盾（官宣早、部分账户晚到），
  不换算就写「跳票了几小时」会造出两个来源都没说的结论。
- **UTC 与北京时间出现相同「HH:MM」数字时，先换算再比较，别把数字相同当同刻**
  （2026-09-10 实测踩坑）：官宣帖 09-08 04:05:53 **UTC** 与本机快照归零 09-08 04:04
  **北京**被当成「同一分钟互证」，实际相差 8 小时——北京 04:04 = PT 13:04，对应的是
  Tibo 在回复帖里确认的「中途两次重置」之一；官宣落地对应的是本机 07:34→14:15 的宽归零
  区间（PT 23:15 才见到 1%）。跨源绑定时间时每一条都过「时区换算」节的命令，结论里给
  每个时刻标注时区；「小时:分钟数字一样」在 UTC vs 北京之间每小时都在发生，零证据价值。
- **官宣 ≠ 你的账户已到账**：banked reset 有过分批延迟史，用户问「我怎么还没有」时
  引导看产品内余额，而不是拿官宣时间打包票。**2026-09-01 用本机 rollout 量化过这个差距**：
  25M 那次官方承诺 6pm PST（北京 09:00）、Tibo 落地确认帖发于北京 10:34，而账户实际归零
  区间是北京 10:10–12:06——比承诺线晚 1h10m 到 3h06m。「官方确认已落地」与「你的额度回来了」
  之间有小时级差距，两件事分开说。**兑现端也有实测故障**：2026-09-09 官方确认部分 banked
  reset 在 ChatGPT Work/Codex 使用时未完全生效，受影响时段内的使用者补发一个并收到道歉
  邮件——用户报「用了 banked 没变化」时先核对是否落在该故障窗口。
- **「单账户」这个前提本身要先证，不能默认**（2026-09-03 修正了 2026-09-01 的一次结论）。
  09-01 那次取证报「7 次归零，4 次对上 Tibo 公告，另 3 次无公告、其中 2 次是锚点回拨」，
  并据此写下「一个账户能同时看到官宣重置与无公告的窗口重排」。**这个结论已被推翻**：那台
  机器当时就在两个 Pro 账号之间轮替，「另 3 次无公告」里含账号切换，而当时用来排除多账号的
  检查（数 `auth.json` 里的 `account_id`）结构上不可能失败。数字本身没错，错的是把它们全
  归给一个账户。
  仍然成立的那半条教训：**单账户证据永远只支撑单账户结论**，所以措辞用「该账户另有 N 次
  无公告的归零，原因与范围未核实」，不能升格成「平台静默重置了 N 次」。新增的那半条：
  下历史归因结论前使用 §2 收集身份与窗口线索，再按 §3 命名；检查未命中不能证明单账户。
