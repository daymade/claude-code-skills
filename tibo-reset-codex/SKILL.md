---
name: tibo-reset-codex
description: >-
  查询 ChatGPT/Codex 额度重置时间、解读 Tibo（OpenAI Codex 负责人 @thsottiaux）的重置公告。
  Use when 用户问「ChatGPT/Codex 什么时候重置」「额度什么时候恢复」「下次全员重置几点」
  「banked reset 到了吗」「Tibo 说了什么」「usage limit when reset」，或从微信群/社媒看到
  重置截图/转述要核实时间并换算北京时间。覆盖：权威追踪站 API 速查、Tibo 糙时间写法解读、
  太平洋时间→北京时间的当场实测换算。别凭记忆回答重置时间——用本 skill 的通道现查。
---

# Tibo Reset — ChatGPT/Codex 额度重置速查

## 这是什么

「Tibo reset」= OpenAI Codex/ChatGPT Work 负责人 **Thibault Sottiaux（X: @thsottiaux）**
个人在 X 上宣布的**全员额度重置**传统。社区昵称「Lord Tibo」，有第三方追踪站
**Tibo Radar**（域名 `codex-reset.com`）和「祈祷重置」亚文化。重置是**善意姿态，
没有固定排期**——每次由他发推宣布。

**三种「重置」别混淆**（回答用户前先分清问的是哪种）：

| 类型 | 谁触发 | 在哪看 | 性质 |
|---|---|---|---|
| **全员 RESET** | Tibo 推文 | 追踪站 API / X | 无排期，庆祝里程碑或补偿 bug |
| **BANKED reset** | Tibo 推文 | 官宣：追踪站 API（`type=credits`）；到账确认：ChatGPT 产品内余额 | 一次性「存着随你用」的额度包；官宣 ≠ 人人到账（有过分批延迟） |
| **账户级周重置** | 系统按开通日 | ChatGPT 产品内「Next reset: …」 | 每人时间不同，与 Tibo 无关 |

## 速查工作流（30 秒）

1. **主通道 = Tibo Radar 的 JSON API**（2026-08-23 实测 200，51 条，无需登录）：

   ```bash
   curl -s -m 15 "https://codex-reset.com/api/timeline" | python3 -c "
   import json,sys
   for e in json.load(sys.stdin)['events'][:5]:
       print(e['announced_at'], '|', e.get('type'), '|', str(e.get('summary'))[:100])
       ow = e.get('official_window')
       if ow: print('   窗口:', ow.get('label'), '=', ow.get('start_at'), '→', ow.get('end_at'), 'UTC')"
   ```

   新条目在前。关键字段：`announced_at`（UTC ISO）、`summary`（推文内容，长推文可能截断，
   完整原文看 `url` 字段）、`official_window`（见第 3 步）、`reset_verification_status`
   （`pending` = 预告未落地；该字段只有 pending/rejected/null，**永不翻转成「已到账」**，
   见证据纪律节）。`type` 是内部小写值：`reset` = 全员重置、`credits` = banked/额度包、
   `boost`/`promo` = 消耗规则类，别拿大写词去匹配 API。

   ⚠️ **别用 HTML 页面 `codex-reset.com/tibo` 当数据源**：它是 SPA，静态 HTML 只渲染旧条目
   （2026-08-23 实测最新一条滞后两天，且无任何过期提示）；WebFetch 还可能被域名安全拦截。
   页面只作「给人看的视图」，数据永远走 API。
2. **双源核对**：`curl -s -m 30 "https://codexlimitwatch.com/codex-reset-history"`——每次重置带
   UTC 时间戳 + 推文引用，与 API 互证（2026-08-23 实测 curl 200）。**外部站一律 curl 直连为
   主通道**：WebFetch 的域名安全校验走 claude.ai，部分网络环境下不稳定——被拦不是站点挂，
   换 curl 即可。
3. **`official_window` 优先用、自己换算做交叉验证**：API 对带时间的预告已算好窗口
   （`label` 太平洋时刻 + `start_at`/`end_at` UTC）。「几点重置」直接读它；再按下方规则
   自算一遍互证，不一致以实测换算为准并报出差异。
4. **fallback 链**：API curl 挂 → codexlimitwatch curl 单源（标注「单源未交叉」）→ WebSearch
   `thsottiaux reset`。都拿不到就明说「无法核实」，别凭记忆答。`feed.xml` 滞后更多
   （实测最新只到 8-13），不作 fallback。X 原文（x.com/thsottiaux）抓不到，不必试。
5. 用户若说「群里看到的」：截图源头通常就是 Tibo Radar 页面；如有群聊归档可搜关键词
   「重置/reset/Tibo」交叉验证群友实测（如到账与否）。

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

- **tracker 的 confirmed 类标签对未来的预告也会打**（两站均有此形态：codexlimitwatch 给
  8-23 那条预告打了「Reset confirmed」——预告未落地也标 confirmed；Radar 历史上也有）。判「已到账」
  只看落地后的实际信号，不看标签：API 的 `reset_verification_status` 只有 pending/rejected/null
  （2026-08-23 全量 51 条实测：落地两天的「has landed」条目仍是 pending）——**结构上不提供
  「已到账」正向信号**，别去等一个永不触发的字段翻转。到账证据 = Tibo 后续「has landed」类
  推文（会作为新 event 出现），或产品内余额实测。
- **多源时间有张力时先换算再叙述，别糅合**：2026-08-21 官宣 banked reset「8pm PST 前到账」，
  tracker 记落地推为 UTC 8/22 00:50——换算回太平洋是 8/21 17:50，**早于**承诺线；
  而媒体报道「8pm 过了很多账户没收到」。两个来源不矛盾（官宣早、部分账户晚到），
  不换算就写「跳票了几小时」会造出两个来源都没说的结论。
- **官宣 ≠ 你的账户已到账**：banked reset 有过分批延迟史，用户问「我怎么还没有」时
  引导看产品内余额，而不是拿官宣时间打包票。
