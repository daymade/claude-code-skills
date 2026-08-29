---
name: claude-code-ping-start-5h-quota
description: >-
  睡前/离开前额度耗尽时，设置一次性本机定时器，在 Claude 订阅额度重置后自动发一条极简
  claude -p 消息，立刻开启新的 5 小时用量窗口——用户睡醒时新窗口已跑掉大半，等于白赚一个
  冷却期。Use when 用户说「还有 X 小时重置额度，帮我定时戳一下 Claude」「我去睡觉了，
  到点 ping 一下开启新窗口」「额度用完了，重置后帮我踩个点」「设个定时器开启新的 5 小时
  冷却期」，或提到 定时戳、戳 Claude、quota ping、开窗、额度重置后自动发消息。
  仅限一次性定时任务与 macOS 本机（caffeinate/BSD date）；周期性任务用 /loop 或 cron，
  查询 ChatGPT/Codex 何时重置用 tibo-reset-codex，分析额度为什么烧完用 claude-usage-analyst。
---

# Claude Code Ping · Start 5h Quota — 额度重置后定时戳一下，开启新的 5 小时窗口

## 原理（为什么这么做有价值）

Claude 订阅的 5 小时用量窗口从**窗口内第一条请求**开始计时，而不是按固定时刻轮转。
所以额度耗尽后如果没人发消息，新窗口就一直不开始计时；用户睡醒后亲自发第一条消息，
等于从那一刻才开始一个全新的 5 小时。反过来，在重置时刻刚过时由定时任务替用户发一条
极简消息，新窗口就从深夜开始计时——用户睡醒时这个窗口已经消耗掉大半时长（而几乎没
消耗额度），相当于把一个冷却期藏进了睡眠时间。

一次戳的成本极小：一条 `claude -p` 单轮消息。2026-08-29 实测全流程成功。

## 入口分流

- 用户给**相对时间**（「还有 1 小时 20 分钟重置」）→ 等待分钟数 = 相对分钟数 + 5 分钟缓冲。
- 用户给**绝对时刻**（「6 点 15 重置」）→ 先 `date` 拿当前时间算差值；目标钟面时刻早于或等于
  当前时间，一律按**次日**同刻理解（深夜说「6 点 15 重置」指明早，睡前跨零点是本 skill 的
  常态输入，不是用户输错），算出差值后再加 5 分钟缓冲。
- 用户要**周期性/每天都戳** → 超出本 skill 边界，用 /loop 或系统 cron，别用一次性 sleep 链。
- 用户问 **ChatGPT/Codex 什么时候重置** → tibo-reset-codex skill。
- 用户问**额度为什么烧这么快** → claude-usage-analyst skill。

## 执行步骤

### Step 0：幂等检查（已有定时器就别再起一个）

```bash
ps -ef | grep -E 'claude -p "Reply with exactly: ok"' | grep -v grep
```

有输出说明已有一个 ping 定时器在跑——报告用户现有定时器的启动时间，问清是否要替换，
不要默默叠加第二个。替换的做法：按 Troubleshooting「用户中途改主意要取消」行的特征串
pkill 杀掉旧链，ps 确认干净后按新参数重走 Step 1–4 全流程（尤其 Step 4——新定时器的
output 路径必须重新交代，否则唤醒通知一旦丢失，兜底路径还指着已被杀掉的旧定时器）。

### Step 1：算时间并报告

```bash
date '+%Y-%m-%d %H:%M:%S'; date -v+<等待分钟数>M '+目标时刻 %H:%M:%S'
```

换算公式（占位符全文统一）：`等待分钟数 = 距重置分钟数 + 5`；`SLEEP_SECONDS = 等待分钟数 × 60`。
例：「还有 1 小时 20 分钟重置」→ 85 分钟 → `SLEEP_SECONDS=5100`。
把具体的触发时刻（几点几分）报告给用户，不要只说「85 分钟后」——用户睡前想知道的是墙钟时刻。

### Step 2：启动定时进程（run_in_background）

用 Bash 工具、`run_in_background: true` 运行：

```bash
caffeinate -is /bin/sh -c 'sleep <SLEEP_SECONDS> && cd "$HOME" && claude -p "Reply with exactly: ok"'
```

**必须 run_in_background**：前台 sleep 会被 harness 拦截；后台任务是 detached 进程，
且退出时会重新唤醒当前会话（见 Step 5）。启动回执里有任务 output 文件路径——记住它，
Step 4 要把它写进给用户的交代（这是路径唯一可靠的持久化机会）。

### Step 3：独立读回验证

启动回执不算数，用 ps 确认进程链真的存在：

```bash
ps -ef | grep -E 'caffeinate -is|sleep <SLEEP_SECONDS>' | grep -v grep
```

**预期输出**：至少三行——`/bin/sh -c sleep ...`、`caffeinate -is ...`、`sleep <SLEEP_SECONDS>`。
少了 `sleep` 行说明进程没起来，回到 Step 2 查报错。

### Step 4：向用户交代清楚

1. **几点戳**：具体墙钟时刻。
2. **output 文件路径**：把 Step 2 启动回执里的任务 output 文件路径原样写进交代。
   触发时刻和路径进了对话历史，即使 85 分钟后上下文被压缩、或唤醒通知丢失，
   也能靠它们找回现场（Troubleshooting 的兜底全指着这条）。
3. **前提**：机器别关机、别合盖（`caffeinate -is` 防自动睡眠，但物理合盖挡不住）。
4. **冗余设计**：终端/会话即使被关，戳也照常执行（`claude -p` 是独立进程）；
   会话留着的话，到点后你还会被唤醒、帮用户确认结果。

### Step 5：被唤醒后收尾

定时进程退出时 harness 会用 task-notification 唤醒本会话。此时：

1. Read 任务的 output 文件（通知里带路径；丢了用 Step 4 交代里记的那份）。
2. **预期内容**：`ok` + `[exited with code 0]`——说明 `claude -p` 真实发出请求并拿到回复，
   新窗口已从实际触发时刻开始计时。
3. **实际触发时刻以 output 文件修改时间为准**：`stat -f '%Sm' <output文件>`。
   它与 Step 1 的计划时刻偏差超过几分钟，说明机器中途睡过、sleep 顺延了——
   报告用户时用实际时刻，新窗口的下次重置时刻 = 实际触发时刻 + 5 小时。
4. 顺带说明 caffeinate 已随进程退出自动释放，无遗留进程需要清理。

被唤醒这件事本身也是一次 API 请求，与 `claude -p` 互为双保险——任何一个发生都能开窗。

## 命令解剖（改动任何组件前先读这里）

| 组件 | 为什么在这里，改掉会怎样 |
|---|---|
| `caffeinate -is` | 防 idle 睡眠（-i）与插电时系统睡眠（-s），撑住等待期；机器睡眠时 sleep 不计时，戳会延迟到唤醒后。进程结束自动释放。防不了物理合盖 |
| `sleep <秒>` | 一次性定时的最简载体。macOS 上别依赖 `at`；ScheduleWakeup 工具的 delay 上限 3600 秒，撑不住更长的等待 |
| `cd "$HOME"` | 避免在项目目录启动 `claude -p`——会加载项目 CLAUDE.md 和 hooks，白烧数千 token 且可能触发项目副作用 |
| `claude -p "Reply with exactly: ok"` | 单轮 print 模式，回一个词就退出，不探索不干活。这是「戳」本身：一次真实 API 请求。不指定 `--model`（减少参数失败面；刚重置的窗口里一次默认模型调用可忽略） |
| `run_in_background` | 双保险的来源：detached 进程不依赖会话存活；退出时又会唤醒会话来确认结果 |
| +5 分钟缓冲 | 重置时刻按用户口述估算有误差；早于重置时刻戳到的是旧窗口，纯浪费 |

## Troubleshooting

| 症状 | 处置 |
|---|---|
| 启动命令被沙箱拦（caffeinate 报权限错） | 用 `dangerouslyDisableSandbox: true` 重试一次 |
| 前台 sleep 被拒绝 | 说明忘了 `run_in_background: true`，不是 sleep 不可用 |
| output 文件里不是 `ok` 而是限流/网络错误 | 戳早了（旧窗口还没结束）或网络问题。读具体报错；若是限流，说明缓冲不够，重起一个 10-15 分钟的短定时器补戳 |
| 到点没被唤醒 | 用 Step 4 交代里记的路径直接读 output 文件（戳本身可能已成功）。路径也丢了就 ps 查进程链：`sleep` 还在 = 未到点；链已消失且已过计划时刻 = 已执行过。读不到任何本地证据时如实说「无法本地确认」，请用户看产品内用量状态，不要谎报已确认 |
| 用户中途改主意要取消 | `pkill -f 'Reply with exactly: ok'`——按命令特征串匹配，2026-08-29 实测可杀掉 caffeinate 与 sh；残留的孤儿 `sleep` 无害（sh 已死，`&&` 后不会执行），到点自灭。**禁止按秒数 `pkill -f 'sleep <SLEEP_SECONDS>'`**：本机长驻脚本的心跳 sleep 可能恰好同秒数，实测发生过误杀 |

## 边界

- **仅 macOS**：`caffeinate` 与 `date -v` 都是 macOS 专属。Linux 对应物（`systemd-inhibit`、
  `date -d`）未经本 skill 验证——遇到非 macOS 环境就明说不支持，不要现场即兴移植。
- **一次性**任务专用。周期性保活、每日定时属于 /loop、系统 cron 或 launchd 的领域。
- 只戳**本机已登录的 Claude CLI 账号**；不涉及 API key 计费账号（API 按量计费无窗口概念）。
- 不查询、不预测重置时刻——重置时间以用户口述或产品内显示为准；Codex 侧的重置查询归 tibo-reset-codex。
- 机器关机/合盖期间无法履约，这是本机方案的固有边界；接受不了就别承诺，明确告诉用户。
