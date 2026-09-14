# 本地预测反馈

把预测和兑现情况写入本机数据台账，供下次调用读取并调整判断。它是业务记录，不是
聊天 memory，也不自动修改 Skill。没有定时任务：用户再次调用本 Skill 时才回看。

## 存在哪里、如何执行

在 Skill 目录运行 `scripts/forecast_log.py`，需要 Python 3.10+ 与 macOS/Linux。
默认文件是 `${XDG_STATE_HOME:-~/.local/state}/tibo-reset-codex/forecasts.jsonl`；
未设置 `XDG_STATE_HOME` 时解析用户家目录，已设置时使用该环境变量的目录。
可用全局参数 `--state-dir` 显式选择另一个数据目录，之后查询与追加必须使用同一目录。

```bash
uv run python scripts/forecast_log.py --help
uv run python scripts/forecast_log.py summary
```

脚本只读写本地 JSONL，不联网、不取账号凭据、不兑换额度。首次写入创建权限为 0600 的文件，
并以文件锁串行追加；读写遇到损坏或未写完的记录会报错并保留原文件。不要清空台账来消除错误。
记录中只放预测、公开证据链接与分析，不放邮箱、token 或产品凭据，不提交到公开仓库。
本地保存不等于已有异机备份，本流程不宣称提供备份或后台追踪。

## 每次调用先回看

1. 运行 `summary`，读 `pending` 和 `recent_resolved`。`pending` 同时含未核验与证据不足的
   记录；`window_elapsed` 只说明窗口已过，不判输赢。没有历史时按当前证据预测，记录为空
   不构成错误。
2. 按主 Skill 取得本轮本来要查的事件证据，核对它能否回答未决预测。明确只有个人额度的
   查询无需为台账另开一轮全局调查；缺证据的记录继续保留，下次有相关证据再核验。
3. 对可核验的记录追加 `review`。核对**预测发出后首个同类型事件**，不能挑后面恰好命中
   窗口的那次；不能用备用重置兑现全局重置预测，也不能用个人额度回满证明全局发生。
4. 读最新结果再预测。关注是否持续偏早/偏晚、哪个催化信号有效（预测的 `catalyst_expected`
   对照回填的 `catalyst_actual`）、窗口是否过宽；结合当前
   产品规则判断旧结果是否仍可比。用一句话说明本次因此怎样调整窗口/信心/信号权重；
   不调整也写理由。一次失误不足以归纳固定规律，不能把本来不知道的信息写成当时应知。

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
| `rationale` | 基线、当前信号与主要反证，含输入样本范围 |
| `revision_trigger` | 哪些新消息或时间条件会使预测提前、推迟或失效 |
| `feedback_applied` | 本地历史的命中/偏差如何影响本次判断；首次记录或不调整时写原因 |

以 `summary` 独立读回原样窗口、依据与 ID 后再说「已记录」。窗口端点要在回答里说清；
若还给出日内偏好，把它及依据写进 `rationale`，日内偏好不参与日期窗口命中统计。
不支持日期的等待策略无需造出一个 `record`；可以在下一条有日期的预测中解释沿用的判断。

修改已发出的预测时再追加一条 `record`，不能编辑历史行。同类型且 `anchor_event_url` 相同
会自动标为 `revision_of`；必须沿用同一规范原帖 URL，不用不同镜像伪造不同轮次。
完全相同的输入重试返回原记录。脚本记录真实写入时刻，不为以前的口头预测伪造精确发出时间。

## 回填证据：review

准备 UTF-8 JSON 对象文件后运行：

```bash
uv run python scripts/forecast_log.py review --input /tmp/tibo-outcome.json
uv run python scripts/forecast_log.py summary
```

输入包含 `forecast_id`、`reason`、`lesson`。取不到证据时另加 `"unknown": true`，说明缺口；
有事件证据时再提供 `kind`、`event_start`、`event_end`、`evidence_urls`，以及：

- `catalyst_actual`：可选，回填事件实际的催化类型（枚举同上），与预测时的
  `catalyst_expected` 对照后，「哪个催化信号有效」才可机械统计。它与是否有事件证据
  无关——`unknown: true` 的核验同样接受（代码先于 unknown 早退解析该字段）。
- 本机 rollout 快照覆盖落地窗口时，用观测到的归零区间收窄 `event_start`/`event_end`，
  不要把确认帖时刻当唯一上界——窗口收窄到日内量级时，这决定 hit 与 unknown 的差别
  （2026-09-12 实测：两条官宣帖夹逼出 4.8h 宽区间，本机快照的 79%→0% 归零
  （11:03→17:52 北京）可再收窄）。

- `time_basis`：`occurrence` 表示明确发生时刻（起止相同）；`observed_interval` 表示已核实的
  发生区间；`confirmation_only` 表示只有完成帖时间，不能把它冒充发生时间。
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
