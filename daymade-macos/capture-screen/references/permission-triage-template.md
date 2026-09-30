# macOS 权限排障模板（Screen Recording / 麦克风 / Full Disk Access）

## 排障目标
- 在系统设置里找不到目标应用
- 权限拒绝但设置项看起来已打开
- 通过终端/脚本入口触发时，用户不知道该给谁授权

## 标准排查顺序（必须按序执行）

1. 确认触发点
   - 明确是哪个权限被拒绝（Screen Recording / 麦克风）。
2. 确认 TCC 实体
   - 不是脚本文件名。
   - **弹窗上显示的名字 ≠ 发起方**。无签名可执行文件（`uv` 管的 python、CLI 工具）在 TCC 里 `identifier=-`，被归因到 responsible 父进程；弹窗标题却显示它当前调用的解释器名（`python3.11`/`python3.14`），会随版本漂移。**授权名字会骗人。**
   - **两个独立真相源，都读，别靠截图/操作回执：**
     - 谁在请求：`log show --predicate 'subsystem=="com.apple.TCC"'` 里 `from Sub:{<path>}` 是发起方；`responsible=` 是归因根。
     - 授权现状：`sudo sqlite3 '/Library/Application Support/com.apple.TCC/TCC.db' "select client,auth_value from access where service='<kTCCService...>' and client like '%<名字>%';"`（`auth_value=2` 已授权 / `0` 未授权）。SIP 保护该库只读——命令行改不了，授权必须走 GUI。
   - 先确认“当前触发进程”与“最终应用体”是否一致。
   - 关注脚本输出里的候选身份列表（invoker/runtime）并逐项核验。
3. 确认设置面板
   - 直接跳转到对应隐私面板
   - 允许该进程/应用
   - 重启进程后复验

## 通用动作模板

```bash
# Screen Recording
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"

# Microphone
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
```

## 不在列表时处理

- 优先确认请求来自真实 .app Bundle（签名、打包）
- 如果当前为 CLI/脚本入口，先给宿主进程授权（Terminal/iTerm/swift/python）
- 在设置面板点击 `+` 手工添加目标 `.app`
- 变更后退出并重启应用，重新测试

## 超出录屏/麦克风的权限问题

本模板只覆盖 capture-screen 自己需要的 Screen Recording / 麦克风。Full Disk Access、
Automation、辅助功能，以及「弹窗一直弹 / 授权对象是谁」的通用诊断，一律走
`daymade-macos:macos-permissions` skill。`from Sub:` 在 TCC 日志中，不在 TCC.db 中；
该 Skill 负责归因、授权状态与后台受保护读取的验证。

## 验收标准（用户侧）

- 用户能看到一条明确的“应授权对象”
- 错误提示中有“找不到对象时下一步该做什么”
- 无需反复猜测在设置里要点击什么
