# 本地预测反馈

把预测和兑现情况写入本机数据台账，供下次调用读取并调整判断。它是业务记录，不是
聊天 memory，也不自动修改 Skill。没有定时任务：用户再次调用本 Skill 时才回看。

## 存在哪里、如何执行

在 Skill 目录运行 `scripts/forecast_log.py`，需要 Python 3.10+ 与 macOS/Linux。
默认文件是 `${XDG_STATE_HOME:-~/.local/state}/tibo-reset-codex/forecasts.jsonl`；
未设置 `XDG_STATE_HOME` 时解析用户家目录，已设置时使用该环境变量的目录。
可用全局参数 `--state-dir` 显式选择另一个数据目录，之后查询与追加必须使用同一目录；
`--no-git` 关闭本地 git 快照（规则见下方 findings 节）。

```bash
uv run python scripts/forecast_log.py --help
uv run python scripts/forecast_log.py summary
```

脚本只在本地工作：读写 JSONL，并为每次成功追加做一次 best-effort 的本地 git 快照
（自动 init、逐次 commit、失败不阻塞，规则见下方 findings 节）；不联网、不取账号凭据、
不兑换额度。首次写入创建权限为 0600 的文件，
并以文件锁串行追加；读写遇到损坏或未写完的记录会报错并保留原文件。不要清空台账来消除错误。
记录中只放预测、公开证据链接与分析，不放邮箱、token 或产品凭据，不提交到公开仓库。
本地保存不等于已有异机备份，本流程不宣称提供备份或后台追踪。

## 每次调用先回看

1. 运行 `summary`，先读 `due_for_followup`（窗口已过期或 24h 内将关闭——阈值即脚本常量
   `CLOSING_SOON_HOURS`——且尚无定论的
   pending，带完整 id 可直接喂 review），再读 `pending` 和 `recent_resolved`。`pending`
   同时含未核验与证据不足的记录；`window_elapsed` 只说明窗口已过，不判输赢。没有历史时
   按当前证据预测，记录为空不构成错误。接续监测轮用 `handoff` 读取最新完整交接；
   需要其他轮次的原始读数时再读数据目录的 `findings.jsonl` 原始行。
   `findings` 命令只返回摘要（id/invocation/query/endpoints 数），不含 `readings` 与 `notes`。
2. 按主 Skill 取得本轮本来要查的事件证据，核对它能否回答未决预测。明确只有个人额度的
   查询无需为台账另开一轮全局调查；缺证据的记录继续保留，下次有相关证据再核验。
   窗口刚过期的未决预测趁观测区间未漂移立即核验：每拖一轮，区间宽一轮（2026-09-24 实测：
   banked 预测过期 26h 后才查，0→1 只能夹到跨边界区间，本可判 hit 变 unknown；banked 的
   判别器是 query_usage 的计数变化，不是落地确认帖）。
3. 对可核验的记录追加 `review`。核对**预测发出后首个同类型事件**，不能挑后面恰好命中
   窗口的那次；不能用备用重置兑现全局重置预测，也不能用个人额度回满证明全局发生。
4. 读最新结果再预测。关注是否持续偏早/偏晚、哪个催化信号有效（预测的 `catalyst_expected`
   对照回填的 `catalyst_actual`）、窗口是否过宽；结合当前
   产品规则判断旧结果是否仍可比。用一句话说明本次因此怎样调整窗口/信心/信号权重；
   不调整也写理由。一次失误不足以归纳固定规律，不能把本来不知道的信息写成当时应知。

## findings：原始读数层

`finding` 命令把每次实际抓取到的外部数据逐字落到同一数据目录的 `findings.jsonl`，
是不可变的原始读数层：判断写进台账（record/review），判断用到的当时读数经
`evidence_refs` 挂链回到这里——业界 trace/annotation 的分层做法，读数不随后来的结论改写。
每次实际抓取外部数据的调用都追加一条：含只读公告线单查、账号查询、降频轮的跳过决策
（读数即「这次看到了什么」）。

```bash
uv run python scripts/forecast_log.py finding --input /tmp/tibo-finding.json
uv run python scripts/forecast_log.py findings              # 最近 20 条；--limit N 可调
uv run python scripts/forecast_log.py handoff               # 最新完整监测交接；无记录时为 null
```

| 字段 | 含义 |
|---|---|
| `invocation` | 必填；本次调用形态，常用 `bare` / `announcement` / `account` / `incident` / `monitor` / `loop` / `other`，接受任意非空串 |
| `query` | 必填；本次触发问题的一句话概括 |
| `endpoints` | 必填字符串数组（可为空）；实际请求过的 URL |
| `readings` | 必填对象（可为空）；源名 → 逐字字段值，只抄读到的值，不改写不概括 |
| `notes` | 可选字符串数组 |
| `session_ref` | 可选；本 session transcript 的本机路径 |

完全相同的输入重试返回原记录。`evidence_refs` 链接规则：先 `finding` 后 `record`/`review`
——record/review 输入里的 `evidence_refs` 是 finding id 数组（完整 id，或能唯一解析的短
id 前缀），每个引用必须已存在于 findings.jsonl，否则报错退出（防断链）；缺省不写该键，
旧记录无此键照常解析。重试同一条 record/review 时 `evidence_refs` 需与首次一致：缺省
（不写键）与显式 `[]` 是两个不同状态，幂等匹配按字面比较，不一致会新建记录而非返回原记录。
`summary` 为每个 forecast/review 显示 `evidence_refs_count`。

每次成功追加后脚本尽力在数据目录做一次本地 git 快照（自动 `init`、目录 0700）；
git 任何失败只在 stderr 打一行 note、绝不影响追加成功，也不构成备份承诺；`--no-git` 关闭。
findings 同台账隐私契约：不放邮箱、token 或产品凭据；`readings` 只放逐字读数与公开 URL。

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

修改已发出的预测时再追加一条 `record`，不能编辑历史行。同类型且 `anchor_event_url` 相同
会自动标为 `revision_of`；必须沿用同一规范原帖 URL，不用不同镜像伪造不同轮次。
完全相同的输入重试返回原记录。脚本记录真实写入时刻，不为以前的口头预测伪造精确发出时间。

**`pending` 按 `recorded_at` 递增排序，`recent_resolved` 按最新核验排序，两者都不依赖台账的
文件顺序**（2026-09-16 起为显式保证；此前 `pending` 只靠 JSONL 追加顺序，任何重写、合并或
按 id 过滤台账的命令都会打乱它）。所以读 `pending` 时**最后一条就是当前有效预测**——它一定
是同一锚点下的最新 `record`，`revision_of` 链上更早的论据不会因为台账被动过而浮到前面。
倒序台账上已验证：`summary` 仍报出递增顺序。据此判断，**不要自己按文件位置挑记录**。

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
- 本机 rollout 快照覆盖落地窗口时，用观测到的归零区间收窄 `event_start`/`event_end`，
  不要把确认帖时刻当唯一上界——窗口收窄到日内量级时，这决定 hit 与 unknown 的差别
  （2026-09-12 实测：两条官宣帖夹逼出 4.8h 宽区间，本机快照的 79%→0% 归零
  （11:03→17:52 北京）可再收窄）。

- `time_basis`：`occurrence` 表示明确发生时刻（起止相同）；`observed_interval` 表示已核实的
  发生区间；`confirmation_only` 表示只有完成帖时间，不能把它冒充发生时间。
- 预测发出前的最后读数（如发出前 7 分钟的 banked=0）不能作 `event_start`——脚本会以
  「event interval must follow forecast issuance」拒绝；取发出后一刻，先验读数写进 `reason`
  （2026-09-24 实测）。
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

将 `lesson` 用于下次 `feedback_applied`，完成「预测 → 事件核验 → 调整」闭环。没有已核实
结果就诚实保持原先低信心，不宣称准确率提高。结构测试和离线回放只验证记录与判读行为；
首次真实预测到期后的核验仍待未来调用完成。
