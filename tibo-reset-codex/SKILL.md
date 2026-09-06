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
| **BANKED reset** | Tibo 推文 | 官宣：追踪站 API（`type=credits`）；到账确认：ChatGPT 产品内余额 | 一次性「存着随你用」的额度包，**到账后不自动消耗**，由用户在 usage 页手动兑现；官宣 ≠ 人人到账（有过分批延迟）。触发形态含里程碑庆祝与故障补偿——§1 所述 rollout 延迟补偿属后者（按无访问天数累积，可一人多笔；2026-09 GPT-6 Astra 补偿即此形态） |
| **账户级周重置** | 系统按开通日 | ChatGPT 产品内「Next reset: …」 | 每人时间不同，与 Tibo 无关 |

## 入口分流

- 用户问「Tibo 说了什么 / 下一次几点」→ 查**公告路径**。
- 用户说自己的 weekly/5h 回到 100%、`Next reset` 改了，或贴出 usage 截图 → 先把它记为
  **该账户的直接观测**，再查是个人周期还是跨账户事件。
- 用户明确说「肯定又重置了」且聚合器无记录 → 立即走**静默重置路径**；禁止重复查询同一
  聚合器后再次用空结果驳回用户。
- 用户只问自己的周期性时间 → 以产品 usage 页或 Codex CLI `/status` 为权威，不拿 Tibo
  时间线代替。**在本机能读到 `~/.codex` 时，先走 §2 的 rollout 快照**——它同样是账户第一手
  证据，且能直接给出历史曲线，不必让用户去截图。

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
    if ow: print('   窗口:', ow.get('label'), '=', ow.get('start_at'), '→', ow.get('end_at'), 'UTC')
    print('   url:', e.get('url'))"
```

新条目在前。关键字段：`announced_at`（UTC ISO）、`summary`（可能截断）、`url`（原帖）、
`official_window`、`reset_verification_status`。`type` 是内部小写值：`reset` = 广域
重置公告、`credits` = banked/额度包、`boost`/`promo` = 消耗规则类。

⚠️ **`type` 是 Radar 编辑者打的标签，不是事件性质的机器判定——跨平台互动也会被打上
`reset`。** 2026-09-05 实测：Tibo 回复 Anthropic 的 Lydia Hallie（原帖：「We've just reset
weekly limits for everyone on a Claude Max plan」，Claude 官方学重置传统），只回了句
「Wow, huge, wonder why!」的调侃，Radar 照样给它 `type=reset`。读原帖是唯一消歧手段；
fxtwitter 响应里的 `replying_to`（被回复人）+ `replying_to_status`（被回复帖 id）就是为
这一步准备的字段。

`url` 已在上面命令的输出里（2026-08-31 起直接打印，免去二次查询），拿到后优先读原帖。X 帖正文的制胜通道是 **fxtwitter 公开镜像 API**（2026-08-30 实测：
免登录、直连即可、返回完整 JSON；**完整正文在 `tweet.text` 字段——不是 `full_text`**，该键
不存在、照抄会 KeyError；note_tweet 长文全文也给，8-29 官宣长文实测 2324 字符完整拿到、以
自然结尾收束）：

```bash
curl -sS --max-time 20 "https://api.fxtwitter.com/<user>/status/<status-id>" \
  | python3 -c "import json,sys; t=json.load(sys.stdin)['tweet']; print(t['created_at']); print('reply_to:', t.get('replying_to'), t.get('replying_to_status') or ''); print(t['text'])"
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
- fxtwitter 不返回回复**内容**（`replies` 字段只是数值计数）；帖子下的 Tibo 澄清需要 WebSearch
  找转录源补充。但它返回 `replying_to`（被回复人 handle）与 `replying_to_status`（被回复帖
  id）——**足够判断「这条是不是回复、回复给谁」**，这正是上面 `type` 误标消歧的唯一字段；
  被回复帖本身再用同一条命令取一次即可。

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

### 2. 本机取证：Codex rollout 快照 = 可脚本化的第一手账户证据

`~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl` 每轮都写 `rate_limits` 快照。**这比引导
用户去看产品页更强**：可回溯历史、能把归零定位到分钟级区间、不需要 GUI，也不需要让用户替你
看屏幕（2026-09-01 实测：5 天 48748 条快照，重建出 7 次重置的完整时间线）。字段形状：

```json
{"limit_id":"codex","primary":{"used_percent":76.0,"window_minutes":10080,"resets_at":1788753995},
 "secondary":null,"credits":{"has_credits":false,"balance":"0"},"plan_type":"pro"}
```

`resets_at` 是 epoch 秒；`window_minutes` 10080 = 周窗口、300 = 5h 窗口；`credits` 就是
banked 余额（`has_credits:false` + `balance:"0"` = 没有 banked reset 在手）。

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
   **修法：多扫 2 天目录，再按时间戳过滤**（已内置在下面脚本的 `SCAN` / `cutoff` 两行）。

**窗口锚点的形状把归零分成三类——注意「干净 +7d」本身不是重置的证据**（2026-09-01 与
2026-09-03 两次实测）：

- **干净 +7d**：新 `resets_at` ≈ 归零时刻 + 窗口长度。这**只说明窗口从归零那刻重新起算**，
  它同时是按钮式重置和「换到另一个有额度的账号」的形状——两者在这个维度上不可分。**单看
  +7d 就叫重置是本节最贵的错误**：2026-09-03 实测的一台机器上，8 天内出现 **8 次**干净 +7d
  （按新锚点去重后；去重前 9 条），按这条读会得出「静默重置 8 次」，而真相是账号轮替。要
  定性必须再过下面的多账号三层检查。
- **锚点回拨**：新锚点被设到**过去**（实测 -12.6h、-23h，后者甚至早于它替换掉的旧锚点）。
  历史上归因为窗口重排 / 限额配置切换，但**在多账号机器上它同样是「切回另一个账号」的
  签名**（那个账号的窗口开得更早）——先排除账号，再谈配置切换。
- **账号切换**：见下面的多账号检查。它可以伪装成上面任何一种。

**并发 session 会让同一次重置输出两条。** 滞后的 session 先报旧值、再各自更新，于是脚本会
打印两条时间相邻、**新锚点相同**的归零记录（实测 08-28 00:26 与 00:27 是同一次）。**按新锚点
去重再数次数**，否则会把 7 次数成 8 次。

⚠️ **别把「并发 session 滞后」当成万能解释——它专门用来掩盖多账号。** 按锚点去重合并的是
**新锚点相同**的两条，机械上碰不到锚点不同的记录；真正的风险在**判断层**：看到两条时间相邻
而数值矛盾的记录，顺手归给「滞后 session」，就把多账号最硬的证据解释掉了。那条证据是
**`used_percent` 往回涨**——额度不会用回去，所以 used% 上升 + 锚点变化只有一个解释：这条
快照来自另一个额度桶。2026-09-03 实测的 `used 0%→82%`（锚点 09-04 → 09-03）正是如此。

它**不在归零列表里**，而在脚本第 1 步的「回跳」输出里（两段是不同的代码路径）——去归零输出
里找它一定找不到。所以：**先读第 1 步的回跳行，再去数第 2 步的归零次数。**

另注：脚本本身**不做去重**，第 2 步会把重复的两条都打印出来（锚点相同即可辨认）；
「按新锚点去重再数次数」是人工步骤。

#### 多账号排除：三层检查（这是本节的头号伪信号）

rollout **不记 `account_id`**，所以切账号产生的交错快照与真重置在所有只读信号上同形。

**先说清楚一个结构性陷阱：直觉上的那个检查永远返回「只有一个」。** `~/.codex/auth.json`
只保存**当前登录的那一个**账号，切走的账号不留痕；`~/.cc-switch/cc-switch.db` 只记它自己
管过的条目，手工 `codex login` 换的账号它完全看不见。**拿这两处的当前状态去回答「历史上
用过几个账号」，是用当前快照回答历史问题——它不会报错，只会给一个貌似合理的错答案。**
（2026-09-03 实测：一台确有两个 Pro 账号在轮替的机器，这两个探针都报「只有一个」，导致整份
归因写反。）

按下面三层查。**任一层命中 → 按多账号处理**。

但三层都干净时**只能说「没有找到多账号的阳性证据」，不能说「已证明单账户」**——这三层都是
阳性检测，没有一层能证否：A 层只覆盖它那一个时间戳（见下）、B 层看不见手工 `codex login`、
C 层在轮替恰好让锚点单调向前时读数为 0。**本节最贵的那个错误（把账号轮替读成静默重置）正好
发生在三层同时安静的情况下**，所以三层干净之后，结论的措辞仍然是「未发现多账号迹象；若你在
这段时间切过账号，下面所有归因都不成立」，并且——**这是最省事的一步——直接问用户有没有切过
账号**。这是唯一能证否的证据源，代价是一句话。

**执行顺序：先跑本节最后那段重建脚本**（它同时产出归零区间与 C 层的回跳），**再跑 A、B 层**
——因为 A 层需要拿归零区间去对齐，先跑 A 层手上没有区间可对。

**A 层 —— 当前身份 +（指示性的）最后一次刷新时刻**

它给两样东西，强度完全不同：

1. **当前登录身份**（`id_token` 解出的 email / `chatgpt_account_id` / plan）——这是硬事实，
   拿去和 B 层比对。
2. `last_refresh` 时刻——**指示性，不是判决**。两条限制必须一起记住：
   - **语义未标定**：字段名就叫 refresh，token 续期也会写它。实测该机 `last_refresh` 与
     `id_token` 的 `iat` 同刻、`exp` 恰好 +3600s，**与一次纯 token 续期无法区分**。所以
     「落在归零区间内」只是**升高**换账号的可能，不能单独定案；要定案靠 B 层身份不一致或
     C 层回跳带 used% 上升。
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

**B 层 —— 这台机器上还存过哪些账号（读 `providers`，不是 `profiles`）**

`profiles` 表实测可能是空的（2026-09-03 该机 0 行），账号存在 `providers` 里；每条的
`settings_config` 内嵌一个完整 `auth` 对象，解它的 `id_token` 才能拿到身份。

```bash
python3 -c "
import sqlite3,os,json,base64
db=os.path.expanduser('~/.cc-switch/cc-switch.db')
if not os.path.exists(db): raise SystemExit('no cc-switch.db (不构成单账户证据)')
c=sqlite3.connect(db)
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
**当前登录身份永远以 A 层为准；is_current 只用来回答「这台机器还存过哪些账号」。**

B 层安静**不代表单账户**——它看不见手工 `codex login`。

**C 层 —— 行为签名：锚点回跳（只靠 rollout，A/B 都失效时仍然有效）**

单账户连续重置的锚点必然**单调递增**。锚点变小 = 切到了一个窗口开得更早的额度桶。这层已
内置在下面的重建脚本里（`回跳次数` 一行），**它是三层里唯一不依赖任何 auth 文件的**，也是
用户绕过 cc-switch 手工换号时唯一还亮的灯。判读：

- `回跳次数 = 0` → 没有阳性证据（**不等于单账户**，见本节开头的闸门说明）
- 任一次回跳带 **used% 上升** → 多账号，没有别的解释（相邻快照间额度不会用回去）
- **大幅**回跳（实测 10.9h、18.7h）→ 多账号，除非有独立证据支持限额配置切换
- 回跳存在但**既不大幅、也没有 used% 上升**（中间带）→ **按「命中」处理，然后去问用户**。
  这一带里限额配置切换与账号切换真的不可分；不要因为「看起来不够大」就默默放行。
  另外注意：`clean` 判定用的是 600 秒容差，而相邻快照间隔实测可达 9.65h——**取样稀疏本身
  就会把一次干净重置误标成锚点回拨**，所以单凭一个中间带回跳不足以下多账号结论。

**辅助判据 —— 归零前的用量峰值（先验，不是判决）**

- **打满触发**（归零前 99–100%，且几十秒到几十分钟内归零）：先验偏向「撞上限后换账号」。
- **非打满**（归零时用量明显没满，实测 82% / 72% / 50%）：先验偏向平台推送，因为平台重置
  不挑你用到几成。2026-09-03 实测：**3 次**非打满归零（去重后；去重前 4 条）**一条不差地各
  对上一条 Tibo 公告**。注意公告时刻与按钮时刻的关系并不固定：08-28 那次按钮早于发帖 9 分钟，
  08-31 那次的归零区间（10:10–12:06）反而把发帖时刻 10:34 包在里面。**公告时间不能当落地
  时刻用**，只能用来判断「这次归零有没有对应的官宣」。

**别把它当判决**：同一份数据里 08-27 那次是打满触发、却落在一条 Tibo 公告前 62 分钟——平台
重置**可以**发生在你已经撞上限的时刻，那时它看起来就是打满触发。峰值只调整先验，定性仍然
由 A/B/C 三层决定。

**免费的账号指纹 —— usage-limit 报错里的 `try again at`**

撞上限时 Codex 会写一条 `task_complete` 错误，正文形如：

```
You've hit your usage limit. Visit <codex usage settings URL> to purchase more credits
or try again at Sep 7th, 2026 3:23 PM.
```

`try again at` 就是**该账号**的窗口重置时刻，所以单账户下它随时间**只会往后走**。判据是
**非单调**：某条错误报的 `try again at` 早于前一条报的，那两条来自不同的额度桶。下面这条
命令扫全量历史并自己标出回退，实测该机打印 **17 次**（两个桶来回交替时每次切换都记一次，
所以它是「有没有交替」的指示器，不是「切了几次账号」的计数）。最硬的一处是 `08-25 14:46`
同一分钟内出现 4 个不同取值——几个并发 session 各挂在不同账号上同时撞墙。（不是「聚成两簇」：
每次重置都会生成新窗口，取值本来就一直在变，簇数不是信号，单调性才是。）

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
        back+=1; mark='   <-- 非单调回退 = 另一个额度桶'
    print(f'{t:%m-%d %H:%M} | try again at {v}{mark}')
    prev=v; prevdt=dt
print(f'\n非单调回退次数: {back}   （0=与单账户一致；>0=多账号）')
"
```

**归零只能报区间，不能报时刻。** 相邻快照间隔可达小时级（2026-09-03 实测最宽 **9.65h**；
7 天窗口内有 39 个相邻间隔超过 600 秒），写「落地在
A–B 之间」，别把「首个见到 0% 的快照时间」当成到账时刻。**另外快照只更新到用户最后一次跑
Codex 的时刻**——下「至今没有重置」之前先看最新快照有多旧，那之后是盲区；要消除盲区就让
用户随便跑一条 Codex 命令再读一次。

**rollout 还有一个覆盖边界：它只覆盖当前登录的那一个账号。** 多账号用户的其余账号完全不在
快照里——2026-09-04~06 实测快照停在 09-03 连续三个 session 不动（用户一直没跑 Codex，盲区
28h→49h→70h），那只是「这个账号没新观测」，不是「所有账号都没动静」。此时用户从产品 usage
页抄出的**多账号统计**（每个账号的重置倒计时 + 「有 N 次 full reset」）是覆盖全部账号的
第一手观测，证据级别等同产品页，还能直接闭环「官宣≠到账」（09-06 实测：4 个付费账号各显示
两次 full reset，确认前一日官宣的 full banked reset 已全部到账）。引用这类相对倒计时时
折算成绝对时刻并标注折算时刻（读数时刻 + 已流逝时间），别把「21 小时之后」原样抄给用户。

```bash
# 重建本机周额度曲线 + 多账号回跳检查（2026-09-03 实测；上述陷阱均已内置，见带「陷阱 N」注释的行）
python3 - <<'PY'
import json,glob,os,datetime
BJ=datetime.timezone(datetime.timedelta(hours=8)); DAYS=7
def find_rl(o):
    if isinstance(o,dict):
        if o.get('rate_limits'): return o['rate_limits']
        for v in o.values():
            r=find_rl(v)
            if r is not None: return r
    if isinstance(o,list):
        for v in o:
            r=find_rl(v)
            if r is not None: return r
now=datetime.datetime.now(); rows=[]
SCAN=DAYS+2                                                                # 陷阱 4：目录按天分，
cutoff=datetime.datetime.now(BJ)-datetime.timedelta(days=DAYS)             # 跨午夜的长 session 会把
for i in range(SCAN):                                                      # 次日时间戳写进前一天目录，
    d=(now-datetime.timedelta(days=i)).strftime('~/.codex/sessions/%Y/%m/%d')  # 故多扫再按时间戳裁
    for f in glob.glob(os.path.expanduser(d)+'/rollout-*.jsonl'):
        for line in open(f,encoding='utf-8',errors='replace'):
            if 'rate_limits' not in line: continue
            try: doc=json.loads(line)
            except: continue
            rl=find_rl(doc); ts=doc.get('timestamp')
            if not rl or not ts or rl.get('limit_id')!='codex': continue   # 陷阱 2：滤掉诱饵桶
            p=rl.get('primary')
            if not p or p.get('window_minutes')!=10080: continue           # 陷阱 1：只取周窗口
            rows.append((ts,p['used_percent'],p['resets_at'],(rl.get('credits') or {}).get('balance')))
T=lambda x: datetime.datetime.fromisoformat(x.replace('Z','+00:00')).astimezone(BJ)
A=lambda e: datetime.datetime.fromtimestamp(e,BJ)
rows=[r for r in rows if T(r[0])>=cutoff]                                  # 陷阱 4：按时间戳裁窗
rows.sort()
if not rows:                       # 空不是异常，是一种必须报告的状态：这段时间是盲区
    raise SystemExit('没有可用快照：该窗口内没跑过 Codex，或 ~/.codex/sessions 为空。\n'
                     '这不构成「没有重置」，只说明该区间无观测。')
print(f"采样 {len(rows)} 行 | 最早 {T(rows[0][0]):%m-%d %H:%M} | 扫了 {SCAN} 个日期目录\n")

# —— 第 1 步：多账号回跳检查（在人工去重之前跑）——
# used% 的「不会用回去」只在**严格相邻**的两条快照之间成立，所以这里逐条比相邻快照。
# 别先按锚点分段再比段首：那样 before 值系统性取到整段最小值，会把 100%→0% 印成 0%→0%。
back=0; prev=None
for ts,u,ra,_ in rows:
    if prev is not None:
        pa=A(prev[2]).replace(second=0,microsecond=0)
        ca=A(ra).replace(second=0,microsecond=0)
        rose=u>prev[1]
        # 陷阱 3 的余波：resets_at 秒级微漂跨分钟边界会造出 -0.0h 的假回跳。
        # 阈值 5 分钟滤掉它；used% 上升的一律保留（那不可能是漂移）。
        if ca<pa and ((pa-ca).total_seconds()>=300 or rose):
            back+=1
            up=' ⚠ used% 上升=另一个额度桶（额度不会用回去）' if rose else ''
            print(f"回跳 {T(ts):%m-%d %H:%M:%S} 锚点 {pa:%m-%d %H:%M} → {ca:%m-%d %H:%M} "
                  f"(-{(pa-ca).total_seconds()/3600:.1f}h) used {prev[1]:.0f}%→{u:.0f}%{up}")
    prev=(ts,u,ra)
print(f"回跳次数: {back}  （0=没有多账号的阳性证据，**不等于已证明单账户**；>0=按多账号处理）\n")

# —— 第 2 步：归零事件。峰值只调整先验，定性看上面的回跳与 auth 三层 ——
prev=None
for r in rows:
    if prev and prev[1]-r[1] > 20:                                         # 陷阱 3：按用量降幅判
        a=A(r[2])
        clean=abs((a-(T(r[0])+datetime.timedelta(days=7))).total_seconds())<600
        shape='干净+7d' if clean else '锚点回拨'
        peak='打满触发' if prev[1]>=99 else '非打满(平台推送先验)'
        print(f"归零区间 {T(prev[0]):%m-%d %H:%M:%S} {prev[1]:.0f}% → {T(r[0]):%m-%d %H:%M:%S} "
              f"{r[1]:.0f}% | 新锚点 {a:%m-%d %H:%M} {shape} | {peak}")
    prev=r
if rows:
    last=rows[-1]
    print(f"\n最新快照 {T(last[0]):%F %H:%M:%S} 北京 | 已用 {last[1]:.0f}% | 窗口重置于 "
          f"{A(last[2]):%F %H:%M} | banked={last[3]}")
PY
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
   - §2 的多账号三层检查命中（`last_refresh` 落在归零区间内、A/B 层 email 不一致、或回跳
     带 used% 上升）→ **「这不是重置，是换账号」**。这一级必须排在最前面，因为下面每一级都
     预设「重置发生了」；跳过它会把账号轮替一路升格成平台事件（2026-09-03 实测差点如此）。
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

Radar API 挂 → fxtwitter 读原帖（§1 的命令）→ syndication 官方端点（截断 276 字符，只够核对元数据）→
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
通道里没有」，不是「他没发」——按这个强度措辞，并补一句「不等于后端没动作」。

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
- **官宣 ≠ 你的账户已到账**：banked reset 有过分批延迟史，用户问「我怎么还没有」时
  引导看产品内余额，而不是拿官宣时间打包票。**2026-09-01 用本机 rollout 量化过这个差距**：
  25M 那次官方承诺 6pm PST（北京 09:00）、Tibo 落地确认帖发于北京 10:34，而账户实际归零
  区间是北京 10:10–12:06——比承诺线晚 1h10m 到 3h06m。「官方确认已落地」与「你的额度回来了」
  之间有小时级差距，两件事分开说。
- **「单账户」这个前提本身要先证，不能默认**（2026-09-03 修正了 2026-09-01 的一次结论）。
  09-01 那次取证报「7 次归零，4 次对上 Tibo 公告，另 3 次无公告、其中 2 次是锚点回拨」，
  并据此写下「一个账户能同时看到官宣重置与无公告的窗口重排」。**这个结论已被推翻**：那台
  机器当时就在两个 Pro 账号之间轮替，「另 3 次无公告」里含账号切换，而当时用来排除多账号的
  检查（数 `auth.json` 里的 `account_id`）结构上不可能失败。数字本身没错，错的是把它们全
  归给一个账户。
  仍然成立的那半条教训：**单账户证据永远只支撑单账户结论**，所以措辞用「该账户另有 N 次
  无公告的归零，原因与范围未核实」，不能升格成「平台静默重置了 N 次」。新增的那半条：
  **下这个结论之前，先跑 §2 的多账号三层检查把「单账户」证出来**——否则你连分母是几个账户
  都不知道。
