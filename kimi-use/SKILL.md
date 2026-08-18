---
name: kimi-use
description: >-
  Drive the Kimi desktop app (Kimi.app) through computer-use to query its built-in data plugins — 天眼查 company records, 同花顺 iFinD financials, 财新数据, 标普全球市场财智, 恒生聚源, SEC, IMF, 世界银行公开数据, 学术数据库, 法律数据库 and more — through the user's own logged-in Kimi session, with no separate API keys. Use whenever the user says "用 Kimi 查" / "操作 Kimi 客户端" / "Kimi 插件", asks to fetch company shareholders, financial statements, market data, or academic/legal records via Kimi, or needs a data source that has no standalone API but exists as a Kimi plugin. Covers both Claude Code (computer-use MCP) and Codex (computer plugin) driving, query-prompt patterns that force source-labeled honest answers, and the cross-checking discipline that screen-transcribed data requires. Not for kimi.com browser automation (that is kimi-webbridge) or for direct credentialed iFinD API access.
---

# kimi-use — 把 Kimi 桌面客户端当零凭据数据源网关

## 这个通道是什么

Kimi 桌面客户端（Kimi.app，`com.moonshot.kimichat`）自带一个插件生态：天眼查、同花顺 iFinD、财新数据、标普全球市场财智、恒生聚源、SEC、IMF、世界银行、学术数据库、法律数据库等。这些插件跑在**用户自己的登录态**上——不需要额外 API key，不需要爬虫，权限来自用户账号已有的订阅。

用 computer-use 驱动这个客户端的 GUI，agent 就把这一整排数据源变成了自己的取数通道。实测：2026-08-18（Claude Code computer-use MCP）与 2026-06-29、2026-07-02 两轮（Codex computer 插件）共三次跑通完整取数。

这个通道有两个不显而易见、且都付出过真实代价的性质，决定了本 skill 一半讲驱动、一半讲核验：

1. **能力是不可见的，且「已安装」≠「可调用」。** 插件列表要打开客户端「插件 → 已安装」页才看得到；而装了不代表能调——实测万得插件在已安装列表里、实际调用时不在可调用数据源列表内。某个插件能不能用，只能实跑一次探针查询，不能看安装状态。
2. **答案是渲染在屏幕上的。** 屏幕转录会静默抄错中文专名、会把截断当全量（实测：20 个股东名抄错 6 个、持股比例却逐位全对；「全 20 条」实为 50 条）。从这条通道落盘的数据，**不过权威源复核不许写进交付物**。

## 路由：什么时候用这条通道

有专用通道的先走专用通道——本 skill 是「没有专用通道时的宽面网关」，不是万能首选：

| 需求 | 走哪条 |
|---|---|
| 企业工商数据，且本机有专用 CLI（如 qcc） | 专用 CLI 为权威源；Kimi 天眼查插件当**对照通道** |
| 有 iFinD 自己的账号凭据 | 直连 API 类工具（本机若装有 iFinD API skill/客户端）——结构化、无 GUI 开销 |
| 驱动浏览器里的 kimi.com 网页版 | `kimi-webbridge` skill（本地 daemon，不走 GUI） |
| **无凭据 / 只有插件形态的数据源 / 一次要横跨多个源** | **本 skill** |

路由表管的是「默认该走哪条」；用户当面指定「就用 Kimi 查」时不挡路——Kimi 是取数通道、专用 CLI 是复核通道，两个角色不冲突。

**环境边界**：仅在 macOS 上实测过（Kimi.app 桌面客户端）。Windows 版 Kimi 客户端存在，但本流程未在 Windows 验证——在 Windows 上用时按「未验证」对待，先把驱动链路跑通再取数。

## Step 0：驱动器检查（30 秒，不可省）

两种宿主环境的驱动机制不同，详见 `references/driving-kimi-app.md`：

- **Claude Code**：computer-use 的 MCP 工具是 **deferred tools**——先 `ToolSearch` 搜 "computer-use" 把它们加载出来，它们才出现在工具列表里。**没搜就断言「这个环境没有 computer use」是事实错误**；fallback 到 `osascript` / `screencapture` 不算 computer use，不要这么替代。**搜索无果或 ToolSearch 本身不存在 = 这个环境没配 computer-use：停下来报告用户、由用户决定配置**，别降级冒充、也别当作已经查过了。
- **Codex**：computer 插件提供无障碍树（AX-tree）工具——`list_apps` / `get_app_state` / `set_value` / `click` / `type_text` / `press_key`，靠 `element_index` 定位元素，**不需要截图坐标**。这些工具不在 = 同样停下报告用户。
- 确认 Kimi.app 已安装（`/Applications/Kimi.app`）。**登录态此刻确认不了**——看屏幕的能力要第 1 步授权之后才有；打开后首屏停在登录页 = 没登录，停下来交给用户扫码。

## 核心循环

逐步操作细节（工具签名、坐标系、多显示器、产物路径）全部在 `references/driving-kimi-app.md`，这里是骨架：

1. **请求访问并打开** Kimi.app（Claude Code 先 `request_access` 拿授权）。⚠️ **授权是同机排他锁**：同一时刻只有一个 session 持有，并行 session 会被拒；工具集没有释放接口——被拒先用 `list_granted_applications` 自查持锁者，等对方结束或请它代跑，别误判成「工具坏了」。
2. **检查模式：Chat 还是 Work。** 打开后截图看模式指示——Work 模式会在界面上显示挂载的项目目录名（实测遇到过挂在活跃工作仓上：那等于把写权让给第三个进程），点模式标签可切换。只取数优先 Chat；**但发出查询后要确认真调了插件**（工具轨迹可见 / 字段带来源标签）——Chat 模式实测过点名插件仍退回普通聊天行为的情况，没调就切 Work/Agent 模式重发，跑偏过的会话不要继续用。
3. **打开「插件 → 已安装」页读权威列表**（分类页是全量目录、含未安装项，两者别混）。选定本次查询要点名的插件。
4. **设计查询**（模式库在 `references/query-and-verification.md`）：点名插件 + 诚实条款（「查不到就明说，不要用训练知识补」）+ 逐字段标来源 + 实体锚定（公司全称/股票代码）+ 时间口径。某插件/数据类型**首次使用**时，先发一个在它声明覆盖面内的探针查询确认真的可调。
5. **发出后轮询等待**——任务彻底跑完再取，半截结果不入库。
6. **提取产物**：结果面板的「复制」按钮 → `pbpaste` 拿全文 Markdown；或收 Kimi 生成到磁盘上的文件（它写在挂载工作目录根部或自己的沙盒里，不一定是你想要的位置——用完要归位）。
7. **落盘前过权威源复核**（见下方陷阱 2/3/4）：错有两层机制——屏幕转录抄错专名、Kimi 源头搞错数值口径——所以**承重的专名与承重的数值都要用独立通道复核**；Kimi 跑的间隙正好并行拉官方源（公告原文、交易所文件）。
8. **落盘时标三样**：数据源、口径（时点/报告期）、获取日期。改过的值保留「原始 + 校正」两层，不静默覆盖。

## 五个用真实数据换来的坑

每个都出自实测会话；战例与证据分放两处——`references/plugin-capabilities.md`（陷阱 1）与 `references/query-and-verification.md`（陷阱 2-4）：

1. **「已安装」≠「可调用」** — 万得插件已安装但不可调用。判断能力只能实跑探针。
2. **屏幕转录抄错中文专名** — 实测 20 个股东名抄错 6 个（形近/音近字错），数字逐位全对。「照抄值」纪律管不到这类错——值确实照抄了，错的是屏幕识别本身——只有换一个权威源才抓得住。
3. **「全 N 条」是截断不是全量** — 「全 20 条」实为 50 条。写「前 N 条」，需要全量就换专用通道。
4. **Kimi 会硬错** — 实测它把某港股 IPO 的回拨比例写成 50%，官方公告是 20%。取数期间并行从权威源拉同一批数，落盘前对账。
5. **没加载就断言没工具** — computer-use 是 deferred 的；先 ToolSearch，别 fallback 到 osascript。

## References

- `references/driving-kimi-app.md` — 两种宿主的逐步驱动流（Claude Code MCP / Codex 插件）、授权与模式安全、产物提取路径
- `references/plugin-capabilities.md` — 插件清单快照与已实测的能力边界（带日期与证据级别）
- `references/query-and-verification.md` — 查询 prompt 模式库 + 数据核验纪律（含战例）
