# 本地预测反馈

把预测和兑现情况写入本机数据台账，供下次调用读取并调整判断。它是业务记录，不是
聊天 memory，也不自动修改 Skill。没有定时任务：用户再次调用本 Skill 时才回看。

## 存在哪里、如何执行

在 Skill 目录运行 `scripts/forecast_log.py`，需要 Python 3.10+ 与 macOS/Linux。
默认状态目录是 `${XDG_STATE_HOME:-~/.local/state}/tibo-reset-codex/`；其中
`forecasts.jsonl` 保存预测与核验，`withdrawals.jsonl` 保存撤回，`findings.jsonl` 保存原始读数。
有明确时刻的官宣由 `announce` 追加到独立的 `announcements.jsonl`，标为
`entry_type=official_announcement`；它不进入预测样本数或命中率统计。官宣的 review 仍保存为
旧格式兼容的 review 行，旧读取器可继续读 forecasts.jsonl，不会碰到缺少窗口字段的新官宣行。
未设置 `XDG_STATE_HOME` 时解析用户家目录，已设置时使用该环境变量的目录。
可用全局参数 `--state-dir` 显式选择另一个数据目录，之后查询与追加必须使用同一目录；
`--no-git` 关闭本地 git 快照（规则见下方 findings 节）。

```bash
uv run python scripts/forecast_log.py --help
uv run python scripts/forecast_log.py summary --compact
# 审计、复盘或需要完整叙述时：
uv run python scripts/forecast_log.py summary
```

写入命令默认返回紧凑回执：`id`、`record_type`、`recorded_at`、`append_status`、
`journal` 与独立的 `snapshot` 状态。原始 `readings` 仍完整追加到 JSONL，不随终端显示缩短。
需要旧版完整 JSON 返回时，把全局参数 `--full` 放在子命令之前，例如
`forecast_log.py --full finding --input <input.json>`；只读 `handoff` 保留完整交接。
调用器按记录 ID 从回执指定的 journal 读取原行；不要为查看正文再创建一条不同记录。

脚本只在本地工作：读写 JSONL，并为每次成功追加做一次 best-effort 的本地 git 快照
（自动 init、逐次 commit、失败不阻塞，规则见下方 findings 节）；不联网、不取账号凭据、
不兑换额度。首次写入创建权限为 0600 的文件，
并以文件锁串行追加；读写遇到损坏或未写完的记录会报错并保留原文件。不要清空台账来消除错误。
记录中只放预测、公开证据链接与分析，不提交到公开仓库；不得写入的字段见 findings 节的隐私契约。
本地保存不等于已有异机备份，本流程不宣称提供备份或后台追踪。

## 每次调用先回看

1. 正常监测轮运行 `summary --compact`；审计、复盘或需要完整叙述时运行 `summary`。compact
   是同一个完整 summary 的投影，只省略 forecast 的 `rationale`、`feedback_applied`，以及
   `latest_review` / `latest_withdrawal` 的 `reason`、`lesson`；其他字段保持不变，包括各队列及其顺序、ID、kind、状态、窗口、`revision_trigger`、
   证据引用、账号观测、`withdrawal_conflicts` 与 `snapshot`。先读 `due_for_followup`（窗口已过期或即将关闭、尚无定论的 pending；
   临近关闭阈值以脚本常量 `CLOSING_SOON_HOURS` 为准，完整 id 可直接喂 review），
   再核对 `withdrawal_conflicts`，然后读 `pending`、`recent_resolved` 和 `recent_withdrawn`。`pending`
   同时含未核验与证据不足的记录；`window_elapsed` 只说明窗口已过，不判输赢。没有历史时
   按当前证据给判断，记录为空不构成错误。接续监测轮用 `handoff` 读取最新完整交接；
   需要其他轮次的原始读数时再读数据目录的 `findings.jsonl` 原始行。
   `findings` 命令只返回摘要（id/invocation/query/endpoints 数），不含 `readings` 与 `notes`。
   `confirmed_unscored` 是已确认事件但仍不可评分的记录，已退出事件待查队列；
   `account_followup` 是绑定账号后仍未确认到账的独立队列。运行 `followup` 取得本轮证据任务，
   再按主 Skill 的监测轮实际获取；它不联网、不安排后台任务，也不证明清单已完成。
   `summary` 还带 `snapshot`（只读探测，不创建目录）：`ok` 表示已存在的台账文件都已进 git
   快照（还没有任何台账文件时也是 `ok`）；`lagging` 并列出 `uncommitted` 文件（含被
   `.gitignore` 挡住、从没进过快照的），另带一句 `hint`。这只证明内容尚未进入快照，
   不区分锁阻塞、提交检查拒绝或其他 Git 失败；原因按下方恢复入口核实。
   追加成功不代表 Git 快照完成。自动快照只处理本次
   追加的台账；同一失败且 Git 控制状态未变化时返回 `deferred/unchanged_failure`，
   不因增加另一条读数反复启动已失败的提交。修正原因后按下面的快照恢复入口重试。
   `no_repo` 是快照还没建立（全新目录也是这样，不算故障）；`disabled` 是用了 `--no-git`；
   `unknown` 是 git 自身出错。快照失败只在追加当时的 stderr 打一行，`summary` 是每轮第一眼
   读到它的地方。
2. 按主 Skill 取得本轮本来要查的事件证据，核对它能否回答未决预测。明确只有个人额度的
   查询无需为台账另开一轮全局调查；缺证据的记录继续保留，下次有相关证据再核验。
   窗口刚过期的未决预测趁观测区间未漂移立即核验；拖延会扩大观测区间，使窗口跨边界。
   banked 的判别器是 query_usage 的计数变化，不是落地确认帖。
3. 对可核验的记录追加 `review`。核对**预测发出后首个同类型事件**，不能挑后面恰好命中
   窗口的那次；不能用备用重置兑现全局重置预测，也不能用个人额度回满证明全局发生。
4. 读最新结果，再决定能否给出有依据的日期预测。关注是否持续偏早/偏晚、哪个催化信号有效
   （预测的 `catalyst_expected` 对照回填的 `catalyst_actual`）、窗口是否过宽；结合当前产品
   规则判断旧结果是否仍可比。若给日期窗口，说明本次为何调整窗口、信心或信号权重；不调整也
   写理由。没有可支持的日期时给等待判断，不创建窗口。一次失误不足以归纳固定规律，不能把
   本来不知道的信息写成当时应知。

## 社区增量读取

本节用于已有监测游标的补查，不替代用户要求的完整阅读。执行者先加载当前安装的
`read-wechat-messages`，沿其入口核对部署、账号、talker 和预检，再读取其
阅读请求参考页的「最近消息与分页」接口；该 Skill 是独立依赖，不随本包分发。
依赖或预检不可用时保留 `uncovered` 和具体恢复条件，不绕过身份检查。

1. 从上轮 handoff 取得同一部署与 talker 的时间、seq 游标及独立的媒体缺口；只有日期而
   没有消息游标时，从该日近期小片段开始，不能用旧消息总数推算新 offset。
2. 在游标日期至本轮日期内，用现有 `read_chat.py --talker <id> --time <起日~止日>
   --last <本轮小片段条数> --page-size <页大小> --layout json` 选择连续片段。条数按实际
   交流量选择，不默认重读整日；读取 JSON 正文、引用与媒体，不只读取窗口元数据。
3. 保存首次返回的 `window.before_seq`。同一选区的后续页沿用 time、last、page-size 和
   before-seq，只更新 offset。若整个选区仍晚于旧游标，保持这个最新边界、扩大 last 并
   从新选区 offset 0 读取，直到见到旧游标或确认可读历史／本轮资源边界；扩大选区不能
   沿用旧 offset。按实际消息 seq 区分新增与必要上下文，不能把页数或条数当客户端未读。
4. 命中旧游标且选区中新消息已逐条读取时停止向旧扩展；若有未解引用或承重旧媒体，按
   原坐标补读。未见游标、历史补录或缺失造成覆盖不明时保留缺口，不宣称增量穷尽。

新片段媒体照常处理；旧媒体缺口单独结转，仅在它会改变当前判断、取得新原件或达到
已记录重试条件时补查。不得用 `--keyword` 或关闭媒体理解伪装增量提速。小片段可能带回
少量已读上下文，现有缓存与冷却策略仍归微信读取器；本流程不保证零重复请求，也不提供
未声明的 `--after-seq` 接口。游标推进只证明所列消息已观察，不能清除其未读媒体缺口。

## 交接结转

执行者每轮生成一份可直接接续的当前交接，不用 `new_notes + previous.notes` 累加旧正文。
`notes` 只保留：本轮检查时刻与判断；各来源最后实际观测时刻、游标和覆盖；仍影响判断的
未决问题及候选来源；下一次触发条件；仍有效的用户纠偏。已排除解释仅保留会改变下一步的部分。

本轮未查的账号或来源明确标为未刷新；必要旧读数附原观测时刻、`account_ref` 与 finding ID，
不换成本轮时间。未决问题逐项结转或写明由哪条证据关闭；不能为缩短交接而丢掉承诺、
账号到账缺口或媒体缺口。已结束的浏览器清理、旧查询过程和重复原文留在原 finding，
交接只引用记录 ID；未完成的资源收尾仍须保留恢复信息。

追加后运行 `handoff`，逐项读回当前问题、旧观测时间与未决项。脚本只选取最新有效 monitor，
不会替执行者去重或判断时效；原始 findings 不改写，本轮更正通过新记录引用旧证据。

## findings：原始读数层

`finding` 命令把每次实际抓取到的外部数据逐字落到同一数据目录的 `findings.jsonl`，
是不可变的原始读数层：判断写进台账（record/review），判断用到的当时读数经
`evidence_refs` 挂链回到这里——业界 trace/annotation 的分层做法，读数不随后来的结论改写。
每次实际抓取外部数据的调用都追加一条：含只读公告线单查、账号查询、降频轮的跳过决策
（读数即「这次看到了什么」）。

```bash
uv run python scripts/forecast_log.py finding --input /tmp/tibo-finding.json
uv run python scripts/forecast_log.py findings              # --limit N 可调
uv run python scripts/forecast_log.py handoff               # 最新完整监测交接；无记录时为 null
```

| 字段 | 含义 |
|---|---|
| `invocation` | 必填；本次调用形态，常用 `bare` / `announcement` / `account` / `incident` / `monitor` / `loop` / `other`，接受任意非空串 |
| `query` | 必填；本次触发问题的一句话概括 |
| `endpoints` | 必填字符串数组（可为空）；实际请求过的 URL |
| `readings` | 必填对象（可为空）；源名 → 逐字字段值，只抄读到的值，不改写不概括（邮箱例外，见隐私契约） |
| `notes` | 可选字符串数组 |
| `session_ref` | 可选；本 session transcript 的本机路径 |
| `invalidates` | 可选 finding id 数组；追加式纠正作废旧 finding，不改写旧行。完整 id 或唯一短前缀；目标必须已存在，空数组与非空数组按字面区分 |

账号查询的 `readings` 只存实际读到的非敏感字段，并必须带账号句柄 `account_ref`（放在该来源的
读数对象里；`query_usage` 输出里有，网页读数按账号 SOP 在本地算）；banked 与用量读数缺
`account_ref` 就不能作后来的基线。账号标签只作 `notes` 里的可读别名（说明它对应哪一次查询），不能替代
`account_ref`，也不能当基线。未核对时
保留账号未知，不把多条「当前账号」读数自动接成同一账号的历史。用户纠正时先逐字记录原话；时间格式、被核对的账号与因果归因若未明说，
放在 `notes` 标为推断，不改写成用户直接观测。

完全相同的输入重试返回原记录。`evidence_refs` 链接规则：先 `finding` 后 `record`/`review`
——record/review 输入里的 `evidence_refs` 是 finding id 数组（完整 id，或能唯一解析的短
id 前缀），每个引用必须已存在于 findings.jsonl，否则报错退出（防断链）；缺省不写该键，
旧记录无此键照常解析。重试同一条 record/review 时 `evidence_refs` 需与首次一致：缺省
（不写键）与显式 `[]` 是两个不同状态，幂等匹配按字面比较，不一致会新建记录而非返回原记录。
`summary` 为每个 forecast/review 显示 `evidence_refs_count`。

**用户纠正作废旧归因时，仍走追加，不改原始读数**：

1. 先追加一条纠正 finding，逐字保存用户原话，并用 `invalidates` 指向被证伪的旧 finding；
   需要接替监测状态时，把这条直接写成新的 `invocation=monitor` 完整交接，或紧接着再追加一条完整交接。
2. `handoff` 只返回当前有效的最新 monitor 行：若最新 monitor 已被后续 finding 作废且没有更正规程交接，
   返回 `null`，不会悄悄复活更早的旧交接。此时必须先写纠正后的 monitor，再按它继续。
3. 若旧证据还造成预测 false-hit，沿用既有 `review` 追加 `unknown:true`、`event_status:"unknown"`、
   `score_update:true`，并用 `evidence_refs` 链接纠正 finding；不新增记录类型，不删除旧 review。
4. 完全相同的纠正重试返回原行。缺键与显式 `invalidates:[]` 是不同状态；非法、缺失或有歧义的目标 id
   会拒绝追加，最后一条有效记录保持原样。旧 reader 仍能解析新增可选键，但只有当前实现执行上述
   invalidation 读法，不能把旧 reader 的原始行展示当成有效状态判断。

每次成功追加后脚本尽力在数据目录做一次本地 git 快照（自动 `init`、目录 0700）；
git 任何失败只在 stderr 打一行 note、绝不影响追加成功，也不构成备份承诺；`--no-git` 关闭。
findings 隐私契约（本文件对它唯一的完整表述）：不放邮箱——`query_usage` 输出的 `email` 字段、
`read-usage-profile.cjs` 输出的邮箱行、说明文字里的邮箱都不抄，账号一律用 `account_ref` 指代——
也不放 token 或产品凭据；`readings` 只放逐字读数与公开 URL。
**群/项目/人名一律写全称，不自创简称**（2026-10-07 撞 group-name-guard 后加）：台账会在后续轮次
被 `handoff` 原样读回并照抄进回复——简称进了台账，等于每轮引用它的回复都再撞一次群名闸门。
写微信群名/项目名/人名时，用全称（规则与执行细节在 group-name-guard hook 与 read-wechat-messages skill，本行不复制——写之前先经 chatlog 核对该群的 remark/nickName 全称）；
本轮没核实过全称就写「未确认全称的群」，别从旧台账记录里照抄一个看着像简称的写法。
这条契约有执行层：机器上若配置了全局 pre-commit 的个人信息检查，findings 里出现
邮箱就会让快照提交被拒——追加本身仍然成功，但被拒的内容留在暂存区。
同一失败不会因后续追加自动消失；新脚本在控制状态未变时返回 deferred，显式重试仍会接受原 hooks 检查。
首次快照失败时 stderr 的 note 是一行 JSON：
`{"note": "git snapshot skipped: <git 报错首行，含命令行与状态目录路径> | <stderr 末三行>"}`
（stderr 里含 `@` 的片段会被替换成 `<email>`），用 `git snapshot skipped:` 前缀就能认出。
先按 stderr 的原因分：是个人信息检查拒绝，就查 findings 里是否混入邮箱
（`grep -nE '[^[:space:]]+@[^[:space:]]+' <状态目录>/findings.jsonl`），不要用 `--no-verify` 绕过，已追加的记录不
改写，此后的追加不再写邮箱，已入库的命中记录如何处理（例如是否把既有指纹加进该 hook 的基线）
由用户决定，向用户报告，不自行改 hook 配置；是其他原因（如未配置 git 身份、超时、非仓库），
按 stderr 给出的原因处理，与邮箱无关。

## 快照诊断与显式恢复

```bash
uv run python scripts/forecast_log.py snapshot-status
uv run python scripts/forecast_log.py snapshot-retry --journal findings.jsonl
# 不带 --journal 时重试脚本支持且已经存在的台账，不追加业务记录
```

先读 `snapshot-status` 的 journal 健康状态、锁与失败原因。`lock.owner=unknown`
表示未识别属主，不表示锁已过期。现存 Git index 锁令写入快照返回 `blocked/index_locked`；
台账仍正常追加。不得自动删除锁、终止已有进程、跳过 hook 或修改其基线。
进入 `git-safety-net` 的[本地快照恢复流程](https://github.com/daymade/claude-code-skills/blob/main/git-safety-net/references/recovery_playbook.md#blocked-local-snapshots)：
它维护占用与授权核对、原件和索引保全、隔离索引的原 hook 预检、可恢复的锁隔离及停止条件。
先确认该 Skill/正文可读取；缺失时保留具体依赖缺口，继续只读诊断，不自行编造清锁步骤。
锁阻塞与 hook 拒绝分别诊断；邮箱、本机路径、群标识等命中均交给实际 guard 的现行处置流程，
既有授权先回查原文与作用域，不由本 Skill 新增豁免，也不改写已追加的原始读数。
锁释放、提交检查原因解决后，用本页 `snapshot-retry` 续跑。
恢复验收同时要求 `snapshot-status` 的 `snapshot.status=ok`、本次台账原件哈希未变、
每份台账与其已提交 HEAD blob 一致，并保留原锁的恢复副本。脚本发布成功不替代这项运行状态验收。

`.snapshot-status.json` 只保留本地快照失败诊断，不改变既有 JSONL 格式；
`.snapshot-run.lock` 用非阻塞文件锁串行化本脚本的快照尝试。另一尝试在运行时返回
`deferred/snapshot_in_progress`，不等待或停止它。Git 子命令超时上限为 60 秒，
只约束本次启动的 Git 子进程；超时不证明 hooks 或其他进程已退出，必须独立读回。
失败后在 Git 控制文件状态改变或显式重试前保持可见的 deferred；显式重试仍运行原有 hooks。
新版本写入的完整 journal 仍可被旧 JSONL reader 读取；旧 CLI 完整返回用 `--full` 保留。

## 保存预测：record

把真实判断写成 UTF-8 JSON 对象文件，再运行：

```bash
uv run python scripts/forecast_log.py record --input /tmp/tibo-forecast.json
uv run python scripts/forecast_log.py summary
```

`/tmp/tibo-forecast.json` 是本次准备的输入，不是脚本自带文件。字段如下：

| 字段 | 含义 |
|---|---|
| `kind` | `global_reset` 或 `banked_reset` |
| `window_start` / `window_end` | 明确带时区的 ISO 时间；起点在当前时刻之后，终点晚于起点 |
| `confidence` | `low` / `medium` / `high`；定性信心，不是校准概率 |
| `anchor_event_url` | 预测之前最近一轮同类型已确认事件的规范原帖 URL；未知用 `null` |
| `catalyst_expected` | 可选；预测押注的催化类型：`milestone` / `outage_compensation` / `quality_release` / `none` / `other`，缺省 null |
| `evidence_urls` | 支撑本次判断的非空 HTTPS 链接数组 |
| `evidence_refs` | 可选；支撑本次判断的原始读数 finding id 数组，引用必须已存在（规则见 findings 节） |
| `rationale` | 基线、当前信号与主要反证，含输入样本范围 |
| `revision_trigger` | 哪些新消息或时间条件会使预测提前、推迟或失效 |
| `feedback_applied` | 本地历史的命中/偏差如何影响本次判断；首次记录或不调整时写原因 |

以 `summary` 独立读回原样窗口、依据与 ID 后再说「已记录」。窗口端点要在回答里说清；
若还给出日内偏好，把它及依据写进 `rationale`，日内偏好不参与日期窗口命中统计。
不支持日期的等待策略无需造出一个 `record`；可以在下一条有日期的预测中解释沿用的判断。
官方给出的单点时刻用下面的 `announce`，不要为满足 `window_end > window_start` 人造一秒
窗口。`record` 仍用于有依据的判断预测，不因一次查询失败修改窗口或增加宽限。

## 官宣单点时间与事件账号状态

保存已核验原帖的具体目标时间：

```bash
uv run python scripts/forecast_log.py announce --input /tmp/tibo-announcement.json
uv run python scripts/forecast_log.py followup
```

`/tmp/tibo-announcement.json` 是本轮准备的输入。必填：`kind`（沿用 reset 类型）、
`announced_at`（原帖发布时间）、`eta_at`（主解释的单点时刻）、`source_url`、`source_text`
（原帖逐字时间措辞）、`interpretation`（解释与未澄清之处）、`revision_trigger`、
`evidence_urls`（必须包含 source_url）。可选：`alternative_eta_at`（承重的另一时区解释）、
`anchor_event_url`、`evidence_refs`。时间均为带时区的 ISO 字符串；无具体时刻的未来承诺仍
留在监测 finding 中，不造 ETA。官宣可以补录已经过去的目标，实际追加时间不回填为发帖时间。

官宣没有 `confidence` 或预测窗口，不计入 `forecast_count`、`cycle_counts`；
`announcement_count` 单独计数。主 ETA 已过即进入 overdue，不用备选解释推迟复查；回答中
仍保留主解释、承重备选解释与官方澄清状态。官宣的 `review` 可以给出发布之后、补录之前已有的完成确认，
判断预测的发生区间仍必须晚于预测实际发出时间。

`review` 的事件层与评分层独立：

| 输入 / 输出 | 含义 |
|---|---|
| `event_status=confirmed` | 已有该事件的正向确认；不代表任何指定账号到账或预测命中 |
| `event_status=unknown` | 事件仍待核；不按窗口过期推成失败 |
| `outcome=unknown` | 预测暂不可评分；不能据此把已确认事件重新变成待兑现 |
| `account_status` | `delivered` / `not_delivered` / `unknown`，只描述绑定账号 |

使用有效的 `occurrence` / `observed_interval` / `confirmation_only` 事件证据提交 review 时，
事件默认标 confirmed；明确未确认则填 `event_status=unknown`，不评分。`unknown:true` 只表示
缺少可评分证据，默认事件也 unknown；若事件已有独立完成确认，可同时填
`event_status=confirmed`、`confirmed_at`、`evidence_urls`，但评分仍 unknown。
confirmed_at 必须是来源中的确认时刻，不是估计的发生时刻。已存的旧 review 只有在携带
有效 time_basis、事件时间与 evidence_urls 时才派生为已确认；旧的裸 unknown 保持待查。
事件、评分与账号观测各自采用最后一次明确更新：新的裸 unknown 评分不擦掉已有事件确认或账号观测。
要撤销已有事件确认，显式填 `event_status=unknown` 并说明反证；事件与账号的来源 review ID
分别显示为 `event_review_id` 与 `account_review_id`，不把旧读数伪装成本轮的新读数。
多个账号按各自 account_ref 保留最近观测，列表显示为 `account_observations`；一个账号到账
不删除其他账号的待查项。多账号时顶层 account_status 保持 unknown，不伪造全员送达汇总。
单独更新账号时使用 `unknown:true` 与 account_status 字段，默认 `score_update=false`；只提供
完成确认的 review 也默认不修改既有评分。需要明确修订评分时填 `score_update=true`，或用
原来的裸 `unknown:true` 表示证据不足的评分修订。未评分记录仍可以保留 unknown；已有的
hit/early/late 不因补一条到账记录消失。`score_review_id` 与 `score_outcome` 指向实际采用的
评分更新；不更新评分的 review 保留既有 outcome，兼容旧读取器，不冒充新评分依据。

保存账号状态时，非 unknown 的 `account_status` 必须同时带 `account_ref`、
`account_checked_at` 与 `evidence_urls`；已指定账号但到账未知时同样保存这组字段。
`account_ref` 沿用查询脚本的八位本地哈希，不保存邮箱。脚本验证字段形状与时间，原始读数的
真实性、账号绑定和归因仍由调用者核对，需用 `evidence_refs` 链接本轮账号 finding。
未提供账号状态仍为 unknown，不能把事件 confirmed 当作账号 delivered。

事件确认、评分 unknown 的记录进入 `confirmed_unscored`，不再进入 `pending` 或
`due_for_followup`；其 unknown 分数仍留在预测统计中，不伪造命中，也不靠 withdraw 隐藏。
若绑定账号仍 not_delivered 或 unknown，它独立留在 `account_followup`。补查账号后再追加
review 并保留事件确认事实，不编辑旧行；账号送达后退出该账号队列。

`followup` 返回 `event_tasks`、`account_tasks` 和最新监测 `handoff`。按每项事件任务的
`required_sources` 执行相应查询；来源集合由脚本按任务的 `urgency` 生成，不在本文手维护。
沿主 Skill 执行，失败写本轮 unknown/uncovered 与下一复查条件；不由清单推断
实际覆盖，不把别人的失败复述成自己的实测。仅剩 account_tasks 时只核对相应账号。

修改已发出的预测时再追加一条 `record`，不能编辑历史行。同类型且 `anchor_event_url` 相同
会自动标为 `revision_of`；必须沿用同一规范原帖 URL，不用不同镜像伪造不同轮次。
收窄一条仍在进行中的窗口时，新窗口起点必须在未来（脚本约束
`new forecast window must start in the future`，2026-10-11 实测被拒一次）——把官宣原窗口
起算点写进 rationale，`window_start` 改取当前时刻。官宣与判断预测各自建立修订链，不互相算作
同一类记录；官宣修订追加另一条 `announce`。
完全相同的输入重试返回原记录。脚本记录真实写入时刻，不为以前的口头预测伪造精确发出时间。

**`pending` 按 `recorded_at` 递增排序，`recent_resolved` 与 `recent_withdrawn` 分别按核验、
撤回的追加顺序排序。** `pending` 的最后一条只是最近发出且尚未核验或撤回的
预测；若更新的同锚点预测已撤回，它可能是较早的旧判断。先读 `recent_withdrawn` 和监测交接，
再决定是否沿用；不要单靠文件位置或 `pending[-1]` 宣称它当前有效。

## 撤回没有依据的预测：withdraw

预测的时间前提被证伪或发现原本缺少依据时，追加撤回记录，不把 `confidence` 改低后继续保留
同一个无依据窗口，也不编一个替代日期。撤回写入同一 state-dir 的 `withdrawals.jsonl`；
`forecasts.jsonl` 保持原有 forecast/review 格式，让仍使用旧版脚本的会话继续读账。撤回只改
新版摘要中的有效状态，不删除最初判断或修改原始读数。

```bash
uv run python scripts/forecast_log.py withdraw --input /tmp/tibo-withdrawal.json
uv run python scripts/forecast_log.py summary
```

输入 JSON 必填 `forecast_id`、`reason`（具体撤回依据）、`lesson`（下一次怎样避免）；如有
对应 findings，以 `evidence_refs` 挂链。完全相同的输入重试返回原记录；已撤回预测不能再
`review`，已有 `hit` / `early` / `late` 核验的预测也不能用撤回来掩盖结果。`summary` 将它从
`pending` 和 `due_for_followup` 移到 `recent_withdrawn`，但 `forecast_count` 仍包含原预测；
若它是同锚点的首份预测，`cycle_counts` 明列 `withdrawn`，不把撤回算作命中或未知。
若旧版会话在撤回后仍写入有分数的 `review`，新版 `summary.withdrawal_conflicts` 列出
每条冲突记录的 ID 与结果；即使后来又写入 `unknown` 或旧版请求早于撤回开始但晚于撤回落盘，
冲突仍保留。撤回时新版会拒绝已有分数的预测，所以任何共存的有分数 `review` 都需要核对；
不能从任一客户端的单侧摘要直接定案。
下一轮从 `summary` 及 `handoff` 读回后才说“已撤回”；交接文字不能代替台账状态。

## 回填证据：review

准备 UTF-8 JSON 对象文件后运行：

```bash
uv run python scripts/forecast_log.py review --input /tmp/tibo-outcome.json
uv run python scripts/forecast_log.py summary
```

输入包含 `forecast_id`、`reason`、`lesson`。取不到证据时另加 `"unknown": true`，说明缺口；
有事件证据时再提供 `kind`、`event_start`、`event_end`、`evidence_urls`，以及：
核验用到的当时读数用 `evidence_refs` 挂链（规则见 findings 节）。

- `catalyst_actual`：可选，回填事件实际的催化类型（枚举同上），与预测时的
  `catalyst_expected` 对照后，「哪个催化信号有效」才可机械统计。它与是否有事件证据
  无关——`unknown: true` 的核验同样接受（代码先于 unknown 早退解析该字段）。
- 本机 rollout 快照覆盖落地窗口时，先按主 Skill §3 把归零前后读数绑定同一账号，并核对
  该账号原先显示的自然重置时刻。只有证据支持这次跳变属于所复盘的事件，才能用归零区间
  收窄 `event_start`/`event_end`；原因未定时保留 `unknown`，不能用它制造 `hit`。
  `forecast_log.py` 只按输入时间与标志计分，不会替你核验事件归因。已归因的区间可以
  比确认帖时刻给出更窄上界。

- `time_basis`：`occurrence` 表示明确发生时刻（典型时起止相同；秒级窄窗口填两端亦合法）；`observed_interval` 表示已核实的
  发生区间；`confirmation_only` 表示只有完成帖时间，不能把它冒充发生时间。本机 rollout 相邻
  快照**秒级间隔**时，归零迁移本身就已 pin 到秒级，直接记 `occurrence`，不人为拉成区间
  （2026-10-25 实测：相邻快照 1 秒间隔，落地 pin 到 3 秒窗口，评分获得可判分的窄区间；
  分钟级采样间隔时仍用 `observed_interval`）。
- 预测发出前的最后读数不能作 `event_start`——脚本会以
  「event interval must follow forecast issuance」拒绝；取发出后一刻，先验读数写进 `reason`
  （2026-09-24 实测）。**变体（2026-10-25 实测被拒）**：同一事件在 announce 与 forecast 各有
  记录时，`event_start` 按各自记录的发出时刻分别取——announce 侧取官宣后一刻可以通过，但
  forecast 侧复用这个较早起点会被拒，哪怕官宣确实早于预测发出；先验读数写进该条 review 的
  `reason`。
- `first_event_verified`：只有证据足以确认是发出预测后首个同类型事件才填 `true`。
  来源覆盖不足或存在更早事件疑点时填 `false`，在 `reason` 说明，不为得到分数硬填。

脚本按提供的证据计算 `hit`（整个发生区间在预测窗口内）、`early`（完全早于窗口）、
`late`（完全晚于窗口）或 `unknown`（跨边界、只有确认帖或首事件未核实）。这些类别指事件
实际相对窗口的位置；`early` 表示预测偏晚，`late` 表示预测偏早。时间窗过去、索引没新条目
不能直接记为失败。脚本不验证网页内容，证据真伪与范围仍由查询者按主 Skill 核对。

新证据纠正旧核验时追加 `review`；`supersedes_review` 保留旧结论的可追溯关系，`summary`
采用最新核验，并按核验追加顺序展示最近结果，旧预测的新纠正不会因预测日期较早而被挤掉。
同一事件的多次预测都保留，但 `cycle_counts` 只按同类型同锚点的首份预测
计数，未知锚点不进该计数。未决项单列；不要把所有调用次数当独立样本，也不要删去失败的
首份预测、只展示后来改中的版本。结合 `window_hours` 看窗口宽度，不能靠无限放宽刷命中。
撤回记录在 `recent_withdrawn` 单列，不与 `review` 的事件结果混算。

将 `lesson` 用于下次 `feedback_applied`，完成「预测 → 事件核验 → 调整」闭环。没有已核实
结果就诚实保持原先低信心，不宣称准确率提高。结构测试和离线回放只验证记录与判读行为。
