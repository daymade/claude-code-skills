# 驱动 Kimi.app：两种宿主的逐步操作流

> 证据边界：Claude Code 侧实测于 2026-08-18（computer-use MCP）；Codex 侧实测于 2026-06-29 与 2026-07-02 两轮（computer 插件 v1.0.857）。均在 macOS。工具签名按实测记录原样给出；版本演进可能增删工具，**以你当前环境实际加载到的工具清单为准**。

## Contents

- Claude Code：computer-use MCP（截图 + 坐标）
- Codex：computer 插件（AX 树 + element_index）
- 授权：排他锁与模式安全（Chat vs Work）
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
- **type 之后、Return 之前，截图（或 batch 尾部挂 screenshot）确认文本真的进了输入框**。实测踩过：页面切换后按旧坐标 type，字全打进了空气——这个失败**不报错**，发送前的截图是唯一能在发出前抓住它的检查点。
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
- **中文输入是实测雷区（2026-07-02）**：Work 模式里用 `type_text` 逐键打中文，**被客户端吞掉大部分字符，只剩数字和符号**——界面还会把残缺 prompt 折叠成标题气泡，不点开根本发现不了，于是发出一条残缺查询、拿到答非所问的结果。两条生路：①**优先 `set_value` 整体设值**（2026-06-29 实测长中文一次成功）；②set_value 不可用时走剪贴板粘贴——`pbcopy` 备好文本 → `click` 聚焦输入框 → `press_key` super+a → super+v → Return（实测当轮还叠加了「改用英文 prompt」的双保险）。
- 发送前同样要确认进框：`get_app_state` 重读输入框内容，看文本完整再发送。
- **复用上下文**：如果 Kimi 里已有一个同主题的对话/任务（AX 树里看得到标题），在同一个任务里继续问，比新开一个更省——历史上下文（实体核对结论等）都还在。

## 授权：排他锁与模式安全（Chat vs Work）

**computer-use 授权是同机排他锁（2026-08-18 实测）：**

- 同一时刻全机只有一个 session 持有授权；并行 session 请求会被拒，提示锁在别处。
- **工具集没有 release/交还接口**——被拒时不能「让对方释放」，只能等持锁方结束，或请持锁方代跑。
- 被拒时先 `list_granted_applications()` 自查：确认锁是不是真的在别的 session 手里（返回里看得到已授权 app 与 tier），别把「锁被占」误判成「工具坏了」。
- `request_access` 是显式授权闸，需要用户在场批准：`apps` 只列本次真要操作的 app，`reason` 写清取数目的（用户看得到）。**被拒绝或长时间无人批准 = 停下报告用户**，不要重试轰炸，更不要改用 osascript/screencapture 绕过——那不叫 computer use。

**模式安全：**

- **Kimi 的 Work 模式会挂载一个项目目录，Kimi 可以直接读写那个仓。** 实测遇到过 Work 模式挂在活跃工作仓上：那等于把写权让给了第三个进程。
- **怎么识别与切换**：打开后截图看窗口的模式指示——Work 模式会在界面上（输入区/顶部区域）显示挂载的项目目录名；模式标签本身就是切换入口，点击在 Chat/Work 间切换。以你截图里实际看到的为准。
- **只取数优先 Chat 模式；但 Chat 有实测跑偏记录（2026-07-02）**：一次在 Chat 里发了点名「优先调用同花顺 iFind」的完整查询，Kimi 退回普通聊天行为（复述公司概况的普通搜索摘要，还引用了错误数据），没调插件。所以发出后必须有**确认检查点**：工具轨迹可见 / 字段带来源标签 = 真调了；没有 → 切 Work/Agent 模式重发。**跑偏过的会话不要继续用**（错误上下文会污染后续回答）。
- Kimi 任务运行中若要人工介入（登录过期、权限弹窗），停下来交给用户，别硬点授权对话框。

## 等待与轮询（含客户端自身未就绪）

两层「没好」要分开：

1. **客户端/工作区没就绪**：实测遇到过 Work 空间卡在「初始化」然后「reconnecting」——这时发查询等于发给一个没启动的引擎。识别：界面/AX 树里工作区状态停在不正常态。处置：等它完成初始化；卡死就切到普通 Chat 模式（或反过来），别对着 reconnecting 空发。
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
2. **Kimi 生成到磁盘的文件**：Work 模式/任务产物（报告 `.md`、数据 `.csv`）会写进**挂载工作目录的根部**——实测一批 CSV 直接落在当时挂载仓的根目录，用完要移动到该去的子目录，别留在仓根漂移。
3. **沙盒翻找（兜底 + 取证）**：Kimi 的沙盒在 `~/Library/Application Support/kimi-desktop/`，任务脚本在 `daimon-share/daimon/agents/main/code/python-run/<uuid>/`。**按 mtime 倒序找、别全盘 `find ~`**（又慢又会翻出无关私人内容）：
   ```bash
   find "$HOME/Library/Application Support/kimi-desktop" -name '*.csv' -print0 2>/dev/null \
     | xargs -0 stat -f '%m %N' | sort -nr | head -20
   ```
   两个用途：①找产物文件；②**取证**——读 `python-run/<uuid>/script.py` 能审计 Kimi 这次实际调了哪些接口字段、用的什么口径，比它的自述更硬。
   注意：有些附件只活在任务上下文里、从不落盘——找不到文件不代表任务没跑，以复制通道拿到的全文为准。
