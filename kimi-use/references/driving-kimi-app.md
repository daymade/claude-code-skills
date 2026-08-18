# 驱动 Kimi.app：两种宿主的逐步操作流

> 证据边界：Claude Code 侧实测于 2026-08-18（computer-use MCP）；Codex 侧实测于 2026-06-29 与 2026-07-02 两轮（computer 插件 v1.0.857）。均在 macOS。工具签名按实测记录原样给出；版本演进可能增删工具，**以你当前环境实际加载到的工具清单为准**。

## Contents

- Claude Code：computer-use MCP（截图 + 坐标）
- Codex：computer 插件（AX 树 + element_index）
- 授权：provider 前提（k3 段无此工具）与排他锁；模式与模型铁律（Work/Agent + K3 极致，禁 Chat）
- 等待与轮询（含客户端自身未就绪）
- 提取产物（复制通道 / 落盘文件 / 沙盒位置）

---

## Claude Code：computer-use MCP（截图 + 坐标）

**工具是 deferred 的，先加载：**

```
ToolSearch(query="computer-use", max_results=30)   →  mcp__computer-use__* 进入工具列表
ToolSearch(query="select:<工具名>")                 →  精确补载单个工具
```

**实测用到的工具与调用序：**

```
mcp__computer-use__request_access(apps=["Kimi"], reason="<向用户说明取数目的>")
  → 返回 granted: [{bundleId: "com.moonshot.kimichat", ...}] + 窗口所在显示器信息
mcp__computer-use__list_granted_applications()     # 自查当前持锁/授权状态（见「排他锁」节）
mcp__computer-use__open_application(app="Kimi")
mcp__computer-use__screenshot()          # 返回截图 + 拍摄于哪台显示器
mcp__computer-use__zoom(region=[x1,y1,x2,y2])   # 局部放大读面板文字（只产图，不改坐标基准）
mcp__computer-use__left_click(coordinate=[x,y]) / double_click(...)
mcp__computer-use__type(text="...")      # 向当前焦点输入框打字
mcp__computer-use__key(text="Return")    # 发送
mcp__computer-use__wait(duration=20~30)  # 等生成
mcp__computer-use__scroll(coordinate, scroll_direction, scroll_amount)
mcp__computer-use__computer_batch(...)   # 一次调用打包多步（click+wait+type+wait+screenshot），
                                         # 实测后段的主力形态：round-trip 少，且尾部挂 screenshot
                                         # 正好当「发送前确认进框」的检查点
```

要点：

- **坐标系**：click/type 的坐标相对于**最近一次全屏 screenshot**。每次全屏截图后基准刷新；窗口若移动/滚动，先重新截图再点。**`zoom` 只产出一张放大图、不切换坐标基准**——在放大图里看到的位置要换算回全屏坐标（region 原点偏移）再点；没把握换算就重新全屏截图直接在新图上量。
- **type 之后、Return 之前，截图（或 batch 尾部挂 screenshot）确认三样：输入框文本、当前模式、模型选择器。** 实测踩过两种不同的静默失败，只确认文本抓不住第二种：①页面切换后按旧坐标 type，字全打进了空气——**不报错**；②新建任务时点错入口，app 跳到 Chat、模型掉成「快速 进阶」、挂载点掉成「选择项目」，而查询全文已经打好在输入框里——差一个回车就发出一条**结论无效**的查询（Chat/快速模型下的否定证词一律作废，见下方模式与模型铁律）。发送前的截图是唯一能在发出前抓住这两种的检查点；模型选择器字小，用 `zoom` 放大看，别在全屏图里眯眼认。
- **多显示器**：`open_application` 之后第一次 `screenshot` 可能拍在另一台显示器上（返回里会列出所有显示器及 id/label）——按返回文本的提示用 `switch_display` 切到 Kimi 窗口所在那台，否则你点的是另一块屏的空气。（诚实边界：实测那次截图恰好落在正确的屏，`switch_display` 本身未被真实调用过，参数形态以工具 schema 为准。）
- **权限分层**（来自 computer-use 注入的工具文档，非实测推断）：浏览器类 app 是 read 层（不给点）、终端/IDE 是 click 层（不给打字）、其余是 full 层。Kimi.app 实测经 `list_granted_applications` 返回确认为 full 层（可 click + type）。目标 app 点不动时，先怀疑它在限制层，不是坐标错了。

## Codex：computer 插件（AX 树 + element_index）

机制完全不同：**不截图、不算坐标**，直接读无障碍树（accessibility tree），元素用 `element_index` 引用。以下是 2026-06 实测会话里记录的函数名形态，注册名以你当前 Codex 环境加载到的为准：

```
list_apps()                              # 找到 Kimi（com.moonshot.kimichat）及运行状态
get_app_state(app="Kimi")                # 返回窗口 AX 树：每个可交互元素带 element_index
set_value(app="Kimi", element_index="340", value="<查询文本>")   # 写进输入框
click(app="Kimi", element_index="364")   # 点发送
get_app_state(app="Kimi")                # 轮询任务进度（生成中/完成可见于树）
type_text / press_key                    # 逐键输入与组合键（用法与坑见下）
```

要点：

- `get_app_state` 就是「读屏」——返回结构化文本树，比截图识别快且准。**先树后图**：能用 element_index 解决就不要退回图像坐标。
- **中文输入是实测雷区（2026-07-02，Work 模式下——同日早些时候是 Chat 跑偏事件，两件事别混）**：用 `type_text` 逐键打中文，**被客户端吞掉大部分字符，只剩数字和符号**——界面还会把残缺 prompt 折叠成标题气泡，不点开根本发现不了，于是发出一条残缺查询、拿到答非所问的结果。两条生路：①**优先 `set_value` 整体设值**（2026-06-29 实测长中文一次成功）；②set_value 不可用时走剪贴板粘贴——`pbcopy` 备好文本 → `click` 聚焦输入框 → `press_key` super+a → super+v → Return（实测当轮还叠加了「改用英文 prompt」的双保险）。
- 发送前同样要确认进框：`get_app_state` 重读输入框内容，看文本完整再发送。
- **复用上下文**：如果 Kimi 里已有一个同主题的对话/任务（AX 树里看得到标题），在同一个任务里继续问，比新开一个更省——历史上下文（实体核对结论等）都还在。

## 授权：排他锁与 provider 前提

**provider 前提（2026-08-18 实测钉死，Claude Code 侧）**：computer-use 的可用性跟随当前 provider——会话切到 Kimi(k3) provider 段时，harness **显式移除** computer-use 与 claude-in-chrome（transcript 里 `mcp_instructions_delta removedNames` 有记录）；切回 Anthropic provider 段，工具重新注入，实测全部 57 次真实调用都跑在 Anthropic 模型下。**所以 ToolSearch 搜不到 computer-use 时，先看自己当前跑在哪个 provider**——k3 段结构性没有这套工具，不是没加载。

**computer-use 授权是同机排他锁（2026-08-18 实测）：**

- 同一时刻全机只有一个 session 持有授权；并行 session 请求会被拒，提示锁在别处。
- **工具集没有 release/交还接口**——被拒时不能「让对方释放」，只能等持锁方结束，或请持锁方代跑。
- 被拒时先 `list_granted_applications()` 自查：确认锁是不是真的在别的 session 手里（返回里看得到已授权 app 与 tier），别把「锁被占」误判成「工具坏了」。
- `request_access` 是显式授权闸，需要用户在场批准：`apps` 只列本次真要操作的 app，`reason` 写清取数目的（用户看得到）。**被拒绝或长时间无人批准 = 停下报告用户**，不要重试轰炸，更不要改用 osascript/screencapture 绕过——那不叫 computer use。

**模式与模型（两条都是铁律，缺一条插件面就不完整）：**

1. **任何时候都不用 Chat 模式（用户明令，2026-08-18）。** 证据：Chat 有调不到插件的实测记录（2026-07-02：点名「优先调用同花顺 iFind」的完整查询，Kimi 退回普通聊天行为——复述公司概况的普通搜索摘要，还引用了错误数据）。**用 Work/Agent 模式。** Work 模式会挂载一个项目目录、Kimi 可以直接读写那个仓（实测遇到过挂在活跃工作仓上：那等于把写权让给第三个进程）——所以发出任务前**先确认挂载点**：模式指示在界面上（输入区/顶部区域）显示当前模式与挂载的目录名，点模式标签切换。任务产生的文件（报告/CSV）会写进挂载目录根部，完成后收走归位，别留在仓根漂移。
2. **模型必须切到「K3 极致思考」（用户明令，2026-08-18）。** K2.6 快速模型没有完整金融插件面：用户同日对照实测，K2.6 声称「不可调用」的三个插件里有两个在 K3 极致下同查询可调且返回接口细节；K2.6 自报的可用数据源枚举本身就不全。模型选择器在输入框附近（实测界面显示「K3 极致」）。**用 K2.6 跑出来的否定结论（不可调用/未覆盖）一律作废，切 K3 极致重问。**
3. **发出后的确认检查点**：工具轨迹可见 / 字段带来源标签 / 自报实际调用的插件名 = 真调了；三者都没有 → 当它没调，检查模式与模型后重发。**跑偏过的会话不要继续用**（错误上下文会污染后续回答）。
4. **新建任务会把模式与模型一起重置（2026-08-18 实测，差一个回车就发出去了）**：Work 的「新建任务」与 Chat 的「新建会话」两个侧栏入口坐标相近，点错的那一下会把 app 切到 Chat、模型掉成快速档、挂载点掉成「选择项目」——三样同时变，而输入框里你打好的文本还在，界面看起来一切正常。**稳妥做法：在 Work 模式下用快捷键 ⌘K 新建任务，不点侧栏**（本轮改用 ⌘K 后探针正常发出）；无论用哪种方式，打字前后各验一次模式与模型。**这条对否定型探针尤其致命**——探针最可能的结果本就是「不可调用」，而那正是 Chat/快速模型下一律作废的那类结论：发出去你会拿到一个看起来正常、实则无效的答案，且没有任何东西提醒你。
- Kimi 任务运行中若要人工介入（登录过期、权限弹窗），停下来交给用户，别硬点授权对话框。

## 等待与轮询（含客户端自身未就绪）

两层「没好」要分开：

1. **客户端/工作区没就绪**：实测遇到过 Work 空间卡在「初始化」然后「reconnecting」——这时发查询等于发给一个没启动的引擎。识别：界面/AX 树里工作区状态停在不正常态。处置：等它完成初始化；卡死就新开工作区或重进客户端，别无措时停下来报告用户——**不要拿「切到 Chat 模式」当绕行**（Chat 模式禁用，见上）。
2. **任务还在生成**：插件取数 + 长报告的实测时长——Claude 侧两次查询约 40 秒与约 3 分钟；Codex 侧一次完整长报告约 9 分钟。节奏：`wait(20~30s)` → `screenshot`/`get_app_state` 看是否还在生成 → 没完就再等，预期放到「几十秒到约 10 分钟」。

**半截结果不入库**：还在流式输出时读到的表格可能缺尾行、编号断裂。等任务彻底完成（停止按钮消失 / 树里出现完成态）再提取。

等的同时别闲着：并行从权威源拉同一批数据（见 `query-and-verification.md` §核验纪律第 4 条）。

## 提取产物

三条通道，按可靠性排序：

1. **复制按钮 → 剪贴板（首选）**：结果面板/预览页有「复制」入口，复制的是**完整 Markdown 原文**（实测 1.3 万字完整无缺）：
   ```bash
   pbpaste | wc -m        # 先看体量，确认不是只复制了可见区域
   pbpaste > result.md    # 落盘
   ```
2. **Kimi 生成到磁盘的文件**：Work 模式/任务产物（报告 `.md`、数据 `.csv`）会写进**挂载工作目录的根部**——实测一批 CSV 直接落在当时挂载仓的根目录，用完要移动到该去的子目录，别留在仓根漂移。2026-08-18 复现两次（仓根 2 个 CSV + 一个新建的 `.tmp/` 里 2 个），**都已归位**。⚠️ **挂载点若是共享 checkout，这就不只是整洁问题**：那个仓可能有别的 session 未提交的 WIP，Kimi 是第三个写者，它落下的文件会混进别人的 `git status`。所以每轮任务结束**当轮**就比对一次仓库状态并归位，别攒到最后；能选就把挂载点选在一个专用目录，而不是活跃工作仓。
3. **沙盒翻找（兜底 + 取证）**：Kimi 的沙盒在 `~/Library/Application Support/kimi-desktop/`，任务脚本在 `daimon-share/daimon/agents/main/code/python-run/<uuid>/`。**按 mtime 倒序找、别全盘 `find ~`**（又慢又会翻出无关私人内容）：
   ```bash
   find "$HOME/Library/Application Support/kimi-desktop" -name '*.csv' -print0 2>/dev/null \
     | xargs -0 stat -f '%m %N' | sort -nr | head -20
   ```
   两个用途：①找产物文件；②**取证**——读 `python-run/<uuid>/script.py` 能审计 Kimi 这次实际调了哪些接口字段、用的什么口径，比它的自述更硬。
   注意：有些附件只活在任务上下文里、从不落盘——找不到文件不代表任务没跑，以复制通道拿到的全文为准。
