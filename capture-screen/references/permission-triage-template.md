# macOS 权限排障模板（Screen Recording / 麦克风）

## 排障目标
- 在系统设置里找不到目标应用
- 权限拒绝但设置项看起来已打开
- 通过终端/脚本入口触发时，用户不知道该给谁授权

## 标准排查顺序（必须按序执行）

1. 确认触发点
   - 明确是哪个权限被拒绝（Screen Recording / 麦克风）。
2. 确认 TCC 实体
   - 不是脚本文件名。
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

## 验收标准（用户侧）

- 用户能看到一条明确的“应授权对象”
- 错误提示中有“找不到对象时下一步该做什么”
- 无需反复猜测在设置里要点击什么
