---
name: tibo-reset-codex
description: >-
  查询 ChatGPT/Codex 额度重置时间，区分 Tibo 官宣、未官宣的平台静默重置、banked reset
  与账户级周期重置。Use when 用户问「什么时候重置」「额度什么时候恢复」「下次全员重置几点」
  「banked reset 到了吗」「Tibo 说了什么」「usage limit when reset」，或说「额度突然回到
  100%」「好像/肯定又重置了」。必须用实时产品状态、独立用户实测与公告交叉核验；禁止因
  Tibo Radar 没有新条目就否定已经发生的重置，并须把太平洋时间当场换算为北京时间。
---

# Tibo Reset — ChatGPT/Codex 额度重置速查

## 这是什么

「Tibo reset」= OpenAI Codex/ChatGPT Work 负责人 **Thibault Sottiaux（X: @thsottiaux）**
在 X 上宣布的广域额度重置传统。社区昵称「Lord Tibo」，有第三方追踪站 **Tibo Radar**
（`codex-reset.com`）和「祈祷重置」亚文化。Tibo 官宣没有固定排期；但平台也会在限额
配置切换时**不发 reset 帖而直接重置账户**。所以「没有 Tibo 帖」只证明没有官宣，不能证明
没有重置。

**四种「重置」别混淆**（回答用户前先分清问的是哪种）：

| 类型 | 谁触发 | 在哪看 | 性质 |
|---|---|---|---|
| **官宣广域 RESET** | Tibo / OpenAI | 官方 X 原帖；追踪站只作公告索引 | 无固定排期，常用于里程碑或故障补偿 |
| **静默平台重置** | OpenAI 后端或限额配置发布 | 产品 usage 状态 + 同时段多账户第一手实测 + 排除各自正常周期；官方限额变更只作上下文 | 可以没有 reset 帖；未获官方范围声明时只能称「大范围观测到」，不能称「全员」 |
| **BANKED reset** | Tibo 推文 | 官宣：追踪站 API（`type=credits`）；到账确认：ChatGPT 产品内余额 | 一次性「存着随你用」的额度包；官宣 ≠ 人人到账（有过分批延迟） |
| **账户级周重置** | 系统按开通日 | ChatGPT 产品内「Next reset: …」 | 每人时间不同，与 Tibo 无关 |

## 入口分流

- 用户问「Tibo 说了什么 / 下一次几点」→ 查**公告路径**。
- 用户说自己的 weekly/5h 回到 100%、`Next reset` 改了，或贴出 usage 截图 → 先把它记为
  **该账户的直接观测**，再查是个人周期还是跨账户事件。
- 用户明确说「肯定又重置了」且聚合器无记录 → 立即走**静默重置路径**；禁止重复查询同一
  聚合器后再次用空结果驳回用户。
- 用户只问自己的周期性时间 → 以产品 usage 页或 Codex CLI `/status` 为权威，不拿 Tibo
  时间线代替。

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

## 查证工作流

### 1. 公告路径：Radar 是索引，不是产品状态

用 Tibo Radar JSON API 找最新公开公告（2026-08-26 实测 200）：

```bash
curl -s -m 15 "https://codex-reset.com/api/timeline" | python3 -c "
import json,sys
for e in json.load(sys.stdin)['events'][:5]:
    print(e['announced_at'], '|', e.get('type'), '|', str(e.get('summary'))[:100])
    ow = e.get('official_window')
    if ow: print('   窗口:', ow.get('label'), '=', ow.get('start_at'), '→', ow.get('end_at'), 'UTC')"
```

新条目在前。关键字段：`announced_at`（UTC ISO）、`summary`（可能截断）、`url`（原帖）、
`official_window`、`reset_verification_status`。`type` 是内部小写值：`reset` = 广域
重置公告、`credits` = banked/额度包、`boost`/`promo` = 消耗规则类。

拿到 `url` 后优先读原帖。X 帖正文的制胜通道是 **fxtwitter 公开镜像 API**（2026-08-30 实测：
免登录、直连即可、返回完整 JSON；**完整正文在 `tweet.text` 字段——不是 `full_text`**，该键
不存在、照抄会 KeyError；note_tweet 长文全文也给，8-29 官宣长文实测 2324 字符完整拿到、以
自然结尾收束）：

```bash
curl -sS --max-time 20 "https://api.fxtwitter.com/<user>/status/<status-id>" \
  | python3 -c "import json,sys; t=json.load(sys.stdin)['tweet']; print(t['created_at']); print(t['text'])"
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
- fxtwitter 不返回回复内容（`replies` 字段只是数值计数）；帖子下的 Tibo 澄清需要 WebSearch
  找转录源补充。

`codexlimitwatch.com/codex-reset-history` 与 Radar 都以 Tibo 动态为核心上游，属于**同一来源
家族**，只能互查转录/解析是否一致，不能称为独立双源。**LunarWerx Codex Forecast**
（`codex.lunarwerx.com`）介于两者之间：它的**核验腿**独立（站点自述且 meta description 实测
「checked against OpenAI's own status page」），但**数据上游**仍是公开重置记录（含 Tibo 动态、
社区描述其模型由 Tibo hints 驱动）——所以它适合作「第三方对 Tibo 信号的**解读**交叉验证」
（2026-08-30：对 celebration 帖它独立给出同样的「明天重置」读法，标注 95% confident），
**不能当「独立观测到重置事件」的第二源**，否则就犯了本 skill 警告的同源错误。它是 SPA，
静态抓取只能拿到 meta 与壳，正文内容经 WebSearch 引用。HTML
`codex-reset.com/tibo` 是 SPA，静态内容可能滞后；只作人类视图。

### 2. 静默重置路径：查账户事实，而不是继续等帖子

在用户直接观测与公告索引冲突时，按顺序取证：

1. **定账户事实**：记录 weekly 与 5h 是否回到 100%、`Next reset` 是否移动、banked reset
   是否仍在，以及变化是否正好发生在此前已显示的正常重置时刻。产品 usage 页或 `/status`
   只证明该账户，但证据级别高于聚合器的空结果。
2. **找同时段实测**：用当前 UTC/PT 日期搜索最近帖子，例如 `Codex reset today back to 100%`、
   `Codex reset again 5h`、`site:reddit.com/r/codex reset today`。优先截图、明确的前后百分比、
   `Next reset` 变化和「banked 仍在」；转载同一条消息不增加独立性。用户说「群里看到的」
   且当前环境有群聊归档能力时，再搜「重置/reset/Tibo」核对群友实测，并分清截图是产品状态
   还是 Radar 转发。
3. **找发布上下文**：搜索 Tibo/OpenAI 是否正在切换 5h/weekly 限额、修计量或处理事故。上下文
   与重置同刻发生只支持因果推断；官方没说「因此重置」就明确标为推断。
4. **按证据范围命名**：
   - 只有一个账户 → 「该账户已重置；原因未定」，不能外推。
   - 多个不同账户在紧邻时间内回满，但尚未排除各自正常周期 → 「观测到跨账户近同时重置；
     是否为同一平台事件未定」。
   - 多个独立账户的预告 `Next reset`/正常周期均解释不了这次提前跳变 → 「观测到大范围
     静默重置」；同期限额发布只能补上下文，不能代替这项反证。
   - 只有官方明确写 all/every paid account → 才称「全员重置」。

静默事件没有官宣时间戳时，报告「最迟在最早公开证据的时间前已发生」，不要把发帖时间伪装成
精确落地时刻。

### 3. 公告时间换算

`official_window` 存在时优先读其 `start_at`/`end_at`；再按下方规则自己换算一遍。
不一致时报告差异，以操作系统时区数据库的实测换算为准。

### 4. 通道失败时

Radar API 挂 → fxtwitter 读原帖（上节命令）→ syndication 官方端点（截断 276 字符，只够核对元数据）→
codexlimitwatch 单源（标注同源镜像）+ LunarWerx（仅 Tibo 信号解读交叉验证，非独立观测第二源）→
WebSearch `thsottiaux reset`
找转录。用户报告产品已变化时，公告通道全空仍要走静默重置路径；全部产品/社区
证据也取不到，才写「只能确认该用户的观测，无法核实影响范围」，不要写「没有重置」。
外部站优先用 `curl` 直连；WebFetch 被安全校验拦截不证明站点已挂。`feed.xml` 的历史实测
比 API 更滞后，不作 fallback。

## Tibo 的时间写法是糙的（解读规则）

实测原话：`Reset will land around 14pm PST tomorrow.`（2026-08-23 06:29 UTC 发）

- 「14pm」= 14:00 = 下午 2 点（他混用 24 小时制和 am/pm，照字面取数即可）
- 他常年写「PST」，但美国夏令时是 **3 月第二个周日～11 月第一个周日**（2026：3/8–11/1），
  期间太平洋实为 PDT（UTC-7）——按**重置落地时刻**的时令换算，不是发推日期
  （3/7 发「tomorrow 2pm」就跨时令，按发推日算会错 1 小时；一年只影响 ~2 天）
- 「tomorrow / today」以**他发推时刻的太平洋日期**为锚：`announced_at`（UTC）减 7（PDT）
  或 8（PST）小时得到发推的太平洋日期，再读 tomorrow 指哪天
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

常用对照（PT → 北京）：PDT 14:00 → 次日 05:00；PDT 20:00 → 次日 11:00；PST 各 +1 小时。

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
  「已到账」正向信号**，别去等一个永不触发的字段翻转。到账证据 = Tibo 后续「has landed」类
  推文（会作为新 event 出现），或产品内余额实测。
- **「celebration」在他的语义里 = 重置动作本身，不是发帖庆祝**（2026-08-30 实战教训：把
  「This celebration is moved to tomorrow as the button was already pressed today」读成
  「只是庆祝帖、无重置」，被两个独立源当场证伪）。他固定把重置绑在用户里程碑庆祝上——
  7M/8M/20M 里程碑均以 banked/reset 兑现，8M 时原话「Tomorrow might be 8M active user
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
- **官宣 ≠ 你的账户已到账**：banked reset 有过分批延迟史，用户问「我怎么还没有」时
  引导看产品内余额，而不是拿官宣时间打包票。
