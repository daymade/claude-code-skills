# kimi-cu macOS 桌面自动化操作法

2026-10-02 驱动微信开发者工具（Electron + webview 控制台）一整天实测沉淀。适用：kimi-cu（ai.kimi.cu MCP）驱动任何 macOS 桌面应用，尤其 Electron/webview。

## 可靠性分层：先选通道再动手

默认后台执行，执行 agent 先检查当前工具的激活与投递语义。优先用不抢焦点的 API/CLI、独立浏览器 CDP、AX `set_value` 或已验证的目标应用后台输入；调用有 app 目标不等于它不会抢前台。前台操作仅在用户明确授权具体机器、app/窗口和本次有界目的后使用；普通「操作/测试/验证」请求不是交接。后台失败不得自动 `activate`、`activate_window`、`AXRaise`、允许前台 fallback，或改发全局键鼠。本文规定执行行为，不安装防护，也不保证所有宿主已拦截。

1. **`set_value`（AX 直写）最可靠**——目标窗口被遮挡也生效，且能触发组件的 onChange（React/Vue 表单状态会收进去）。文本框、步进器一律首选。
2. **键盘（press_key Tab/Space/字母）次之**——背景投递可用，焦点在目标上时稳定；焦点不在就不落。
3. **点击（click index/坐标）最不可靠**——只落 kimi-cu 的 primary 窗口；窗口被遮时事件被静默吃掉（返回 ok:true 但无事发生）。**ok:true 只代表事件投递，不代表生效**。

## 「控件不响应」先核对目标与投递

- 合成输入失败先核对目标窗口、primary、遮挡与目标控件焦点，不凭一次无响应判「控件防自动化」。遮挡能解释失败，不构成抬窗授权；先换已验证的后台通道，仍做不到就保留未完成项并请求具体前台交接。
- kimi-cu 截图只拍 primary 窗口——**画面正常 ≠ 点击会落**。
- 窗口真实前后序用 Quartz 查，不信截图：
  `CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly)` 按 owner PID 过滤，返回顺序即 z-order（第一个是最前）。
- `osascript activate` 只把 app 抬到最前，不选 app 内哪个窗口；目标窗口要单独抬。
  这类抬窗动作只在已授权的具体前台交接内执行，不用它修复后台失败。

## 让目标窗口成为 primary 的手法

先用只读 full snapshot 更新 primary 跟踪。下列会打开、关闭或抬起窗口的恢复手法仍保留，但会抢前台的动作必须已有具体前台交接；共享窗口、锁或其他 session 的状态不得绕过。未获授权时继续后台诊断，不自行激活。

- **新开的窗口自动成为 primary**（点工具栏按钮打开的窗口、授权弹窗）——操作不了就关掉重开，这是成本最低的恢复原语。
- AX 树活着时：`perform_secondary_action` action=`AXRaise`，index = 窗口节点（通常是 [1]）。
- **AX 树会死**（get_app_state 只剩 menubar）：重开目标窗口即恢复，**不必重启 app**。重启 app 是最后手段——会断 MCP 连接、模拟器会话和其他 session 的共享状态。
- System Events 的窗口枚举对这个 app 时好时坏（能 `set size of window` 但列不出 windows）——尺寸调整可用 SE，抬窗别依赖 SE。

## 表单/表格填写配方

- **加行按钮（「+ Add a Line」类）最稳走法 = 键盘**：焦点在当前行 value 字段 → Tab（到行尾 delete）→ Tab（到加行按钮）→ Space 激活。聚焦还会让虚拟化塌陷（1px 高）的按钮恢复渲染。
- 塌陷元素（degenerate frame）会被 index 点击拒绝——用键盘走到它，或用 SE `set size of window` 拉高窗口让它进入渲染区。
- 多行 TSV 粘贴进 webview 表格不可靠（合成 paste 不落）——逐字段 set_value。
- 弹窗内滚动：`scroll` 工具 page:-1 对准内容区；报「already at end」但按钮仍塌陷时，说明该容器不走标准滚动，换键盘或拉窗。

## 弹窗（授权/确认）SOP

1. Quartz 发现无名小窗（授权弹窗典型尺寸 400×240，layer 高于主窗）。
2. kimi-cu `get_app_state` full——让弹窗成为 primary（full snapshot 会刷新 primary 跟踪）。
3. 按 index 或截图坐标点按钮。
- **误点风险高的操作（如 Delete）用确认弹窗当核验闸**：截图核对弹窗文字点名的对象无误再确认；对象不对就 Cancel。

## 投递后必须验证

每个关键动作后用 get_app_state（AX 读回或真实渲染截图）确认状态真的变了；有持久业务结果的，再读对应文件/数据库/事件。**没变化立刻换已授权的后台通道（优先 set_value，再核对焦点后的目标应用后台键盘），同一通道原样重试不超过一次**；切前台必须先过具体交接边界。`ok:true`、DOM/AX 字段绿或截图正常都不单独证明业务动作成立。

**可选的本地防护**：宿主已有重复动作检测 hook 时，核实其实际注册、触发条件和执行读回，再把它作为辅助提醒。本 Skill 不分发或安装该 hook，也不保证宿主会自动拦截重复动作；没有已验证的 hook 时，仍须执行上面的读回、换通道和重试限制。
