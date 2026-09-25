# 驱动 Kimi.app：按当前宿主选择输入路径

> 证据边界：Claude Code 侧实测于 2026-08-18（computer-use MCP）；Codex 旧 computer 插件实测于 2026-06-29 与 2026-07-02；Codex 当前 CUA 实测于 2026-09。均在 macOS。工具签名按实测记录原样给出；版本演进可能增删工具，**以你当前环境实际加载到的工具清单为准**。

## Contents

- Claude Code：computer-use MCP（截图 + 坐标）
- Codex：computer 插件（AX 树 + element_index）
- Codex：当前 CUA（`cua_repl`）富文本输入
- Chat 深度研究：2026-09-25 实测入口、完成判据与 ZIP 原件
- 授权：provider 前提（k3 段无此工具）与排他锁；插件取数的模式与模型限制
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
- **type 之后、Return 之前，截图（或 batch 尾部挂 screenshot）确认三样：输入框文本、当前模式、模型选择器。** 实测踩过两种不同的静默失败，只确认文本抓不住第二种：①页面切换后按旧坐标 type，字全打进了空气——**不报错**；②新建任务时点错入口，app 跳到 Chat、模型掉成「快速 进阶」、项目选项回到「选择项目」，而查询全文已经打好在输入框里——差一个回车就发出一条**结论无效**的插件查询（Chat/快速模型下的否定证词一律作废，见下方模式与模型限制）。「选择项目」本身不是失败判据：当前 Work 可选「不使用文件夹」；要同时核对模式与模型。模型选择器字小，用 `zoom` 放大看，别在全屏图里眯眼认。
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
- **旧 computer 插件的中文输入（2026-07-02，Work 模式）**：`type_text` 逐键打中文时曾被客户端吞掉大部分字符，只剩数字和符号，折叠成标题气泡后不易发现。该插件优先使用当时验证过的 `set_value` 整体设值；不可用时用 `pbcopy` 备好文本 → `click` 聚焦 → `press_key` super+a → super+v，发送前展开并读回全文。这个结论不适用于下方的当前 CUA API。
- 发送前同样要确认进框：`get_app_state` 重读输入框内容，看文本完整再发送。
- **复用上下文**：如果 Kimi 里已有一个同主题的对话/任务（AX 树里看得到标题），在同一个任务里继续问，比新开一个更省——历史上下文（实体核对结论等）都还在。

## Codex：当前 CUA（`cua_repl`）富文本输入

先通过当前 CUA 工具文档获取 Kimi app，再读 AX 状态定位输入框。实际富文本输入框中，`setValue` 曾把文本附在占位提示后且发送按钮仍禁用，`typeText` 曾吞掉中文只留下数字；两者的工具成功回执均不能证明消息可发送。已验证的路径是点击输入框、全选、使用 `app.paste(text, {format: "text"})`，再读 AX 状态核对**全文、所选任务模式、模型和发送按钮已启用**；Work 插件取数还要核对选择的是「不使用文件夹」还是具体目录，最后才点击发送。不要把旧插件的 `set_value` 优先级机械迁移到 CUA。若当前 API 签名不同，以加载到的文档为准；读回仍不完整就停止，不发送残缺查询。

## Chat 深度研究（一次实测）

这一路的目标是**完整研究报告**，不是逐字段插件回执。用户截图与本次 Kimi.app 实操显示：左侧有「深度研究」入口，Chat 输入框内有「深度研究」标识，模型显示「K3 极致」。入口和选项以当前界面读回为准；仅进入普通 Chat 或只选 K3，不能证明深度研究已开启。

1. 在 Kimi.app 进入「深度研究」；写入研究任务后、发送前读回**题目全文、输入框中的「深度研究」状态、K3 极致和发送按钮**。当前 CUA 富文本输入可沿用上节已验证的 `app.paste(text, {format: "text"})` 路径。不要把 Work 的挂载点当作 Chat 的必需条件，也不要拿 Chat 研究回答去判断金融插件可否调用。
2. 等客户端给出**任务完成后的完整报告**再提取；流式摘要和中间搜索记录不当作最终报告。实测报告包含 Markdown 正文和图表；未来任务可能没有附件，按当次实际产物记录。
3. 通过客户端的下载入口保存**原始 ZIP**，记录会话 URL、任务题目、模式/模型、完成时间和 ZIP 路径。该次 ZIP 含一份 Markdown、图表 HTML/PNG 与 ECharts JS；这是单次产物形态，不能写成平台固定合同。
4. 在独立目录解包并保留原 ZIP，macOS 本轮成功命令是 `ditto -xk <下载的ZIP> <目标目录>`。读回解包目录里的 Markdown 与附件清单，检查图表的相对引用是否仍能解析；不要只凭下载回执或报告标题声称已归档。下载名、内部目录和报告名按当次实际值发现，不写死案例名。
5. 报告中的承重断言需要独立源核验；Kimi 报告只能算一个研究输出，不能因为搜索轮数多或附件齐全就把结论升级成业务事实。归档时把原文和后续校正分开，保留可回溯来源。

**Chat 深度研究**的完成与导出不能证明 **Work/Agent 插件工具版**完成；Work 任务已提交也不能推定插件调用或证据包已交付。

## 授权：排他锁与 provider 前提

**provider 前提（2026-08-18 实测钉死，Claude Code 侧）**：computer-use 的可用性跟随当前 provider——会话切到 Kimi(k3) provider 段时，harness **显式移除** computer-use 与 claude-in-chrome（transcript 里 `mcp_instructions_delta removedNames` 有记录）；切回 Anthropic provider 段，工具重新注入，实测全部 57 次真实调用都跑在 Anthropic 模型下。**所以 ToolSearch 搜不到 computer-use 时，先看自己当前跑在哪个 provider**——k3 段结构性没有这套工具，不是没加载。

**computer-use 授权是同机排他锁（2026-08-18 实测）：**

- 同一时刻全机只有一个 session 持有授权；并行 session 请求会被拒，提示锁在别处。
- **工具集没有 release/交还接口**——被拒时不能「让对方释放」，只能等持锁方结束，或请持锁方代跑。
- 被拒时先 `list_granted_applications()` 自查：确认锁是不是真的在别的 session 手里（返回里看得到已授权 app 与 tier），别把「锁被占」误判成「工具坏了」。
- `request_access` 是显式授权闸，需要用户在场批准：`apps` 只列本次真要操作的 app，`reason` 写清取数目的（用户看得到）。**被拒绝或长时间无人批准 = 停下报告用户**，不要重试轰炸，更不要改用 osascript/screencapture 绕过——那不叫 computer use。

**插件取数的模式与模型（两条缺一条，插件面就不完整）：**

1. **插件取数不用 Chat 模式（2026-08-18 用户对该任务明令）。** 证据：Chat 有调不到插件的实测记录（2026-07-02：点名「优先调用同花顺 iFind」的完整查询，Kimi 退回普通聊天行为——复述公司概况的普通搜索摘要，还引用了错误数据）。**取插件字段用 Work/Agent 模式；Chat 深度研究见上节。** 当前新建 Work 任务可点「选择项目 → 不使用文件夹」；这只表示未给 Kimi 挂载指定项目，**不表示任务不会在 Kimi 自身目录写文件**（见「提取产物」）。若需要产物直接写进指定位置，选隔离目录并读回实际路径。历史上挂到活跃工作仓时，Kimi 将文件写进仓根和 `.tmp/`；只有**选了目录**才适用挂载目录的读写风险与当轮归位要求。
2. **模型必须切到「K3 极致思考」（用户明令，2026-08-18）。** K2.6 快速模型没有完整金融插件面：用户同日对照实测，K2.6 声称「不可调用」的三个插件里有两个在 K3 极致下同查询可调且返回接口细节；K2.6 自报的可用数据源枚举本身就不全。当前选择路径：先在模型菜单选 **K3**；焦点在「思考强度 进阶」按钮时按 **Return** 展开「标准 / 进阶 / 极致」，再点「极致」。本轮仅点按钮或箭头未展开；发送前用 AX 读回 **K3 极致**，不凭点击回执推定成功。**用 K2.6 跑出来的否定结论（不可调用/未覆盖）一律作废，切 K3 极致重问。**
3. **发出后的确认检查点**：工具轨迹可见 / 字段带来源标签 / 自报实际调用的插件名 = 真调了；三者都没有 → 当它没调，检查模式与模型后重发。**跑偏过的会话不要继续用**（错误上下文会污染后续回答）。
4. **2026-08-18 点错新建入口的实测**：Work 的「新建任务」与 Chat 的「新建会话」两个侧栏入口坐标相近；当次误点 Chat 入口后，app 切到 Chat、模型掉成快速档、项目选项回到「选择项目」，而输入框里查询文本还在。**在 Work 模式下用 ⌘K 新建任务**是当次验证过的避错方法；新建后仍要读回模式、K3 极致和项目选项，不假定它们必然保留或重置。「选择项目」本身也是无文件夹任务的正常入口，不单凭它判断误点。**否定型插件探针尤其要检查**：在 Chat/快速模型下得到的「不可调用」结论无效。
- Kimi 任务运行中若要人工介入（登录过期、权限弹窗），停下来交给用户，别硬点授权对话框。

## 等待与轮询（含客户端自身未就绪）

两层「没好」要分开：

1. **客户端/工作区没就绪**：实测遇到过 Work 空间卡在「初始化」然后「reconnecting」——这时发查询等于发给一个没启动的引擎。识别：界面/AX 树里工作区状态停在不正常态。处置：等它完成初始化；卡死就新开工作区或重进客户端，别无措时停下来报告用户——**插件取数不要拿「切到 Chat 模式」当绕行**（见上）。
2. **Work 插件任务还在生成**：旧案例实测时长——Claude 侧两次查询约 40 秒与约 3 分钟；Codex 侧一次完整长报告约 9 分钟。节奏：`wait(20~30s)` → `screenshot`/`get_app_state` 看是否还在生成 → 没完就再等。这些时长不用于推断 Chat 深度研究的完成时间；该分支以客户端完成态和最终产物为准。

**半截结果不入库**：还在流式输出时读到的表格可能缺尾行、编号断裂。等任务彻底完成（停止按钮消失 / 树里出现完成态）再提取。

等的同时别闲着：并行从权威源拉同一批数据（见 `query-and-verification.md` §核验纪律第 4 条）。

## 提取产物

按本次任务实际出现的产物选择提取路径：

1. **复制按钮 → 剪贴板（首选）**：结果面板/预览页有「复制」入口，复制的是**完整 Markdown 原文**（实测 1.3 万字完整无缺）：
   ```bash
   pbpaste | wc -m        # 先看体量，确认不是只复制了可见区域
   pbpaste > result.md    # 落盘
   ```
2. **Work 不使用文件夹时的任务目录（2026-09-25 实测）**：一项 K3 极致任务实际完成插件调用，并写出 Markdown 与 CSV。等**停止按钮消失**后，在该任务列表项点「更多操作 → 在访达中打开」；当次 Finder 打开的是 `~/Documents/kimi/tasks/<日期>/<任务ID>/`。从**该任务的精确目录**复制原件到目标归档，逐文件核对复制后的内容（例如用 `cmp -s <源文件> <目标文件>`），再记录原目录和完成时间。任务目录层级、文件种类和数量是这一次的观察值，下一次先由 UI 打开并读回，别按路径模板或文件数猜。**不使用文件夹不等于没有本地文件。**
3. **显式选择了工作目录时**：历史 Work 任务的报告 `.md`、数据 `.csv` 曾写进**所选目录的根部**——一批 CSV 直接落在当时挂载仓的根目录。2026-08-18 复现两次（仓根 2 个 CSV + 一个新建的 `.tmp/` 里 2 个），**都已归位**。⚠️ **所选目录若是共享 checkout，这就不只是整洁问题**：那个仓可能有别的 session 未提交的 WIP，Kimi 是第三个写者，它落下的文件会混进别人的 `git status`。要直接写入指定位置就选隔离目录；选了目录后每轮任务结束**当轮**比对状态并归位。
4. **沙盒翻找（兜底 + 取证）**：Kimi 的沙盒在 `~/Library/Application Support/kimi-desktop/`，任务脚本在 `daimon-share/daimon/agents/main/code/python-run/<uuid>/`。**按 mtime 倒序找、别全盘 `find ~`**（又慢又会翻出无关私人内容）：
   ```bash
   find "$HOME/Library/Application Support/kimi-desktop" -name '*.csv' -print0 2>/dev/null \
     | xargs -0 stat -f '%m %N' | sort -nr | head -20
   ```
   两个用途：①找产物文件；②**取证**——读 `python-run/<uuid>/script.py` 能审计 Kimi 这次实际调了哪些接口字段、用的什么口径，比它的自述更硬。
   注意：有些附件只活在任务上下文里、从不落盘——找不到文件不代表任务没跑，以复制通道拿到的全文为准。
