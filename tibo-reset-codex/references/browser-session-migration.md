# 迁移已有 ChatGPT 会话到隔离 Chrome

仅在用户授权读取源登录态、写入精确目标目录时执行。使用同一台 macOS 上的同一
Google Chrome 安装；不把本流程用于 ego、其他浏览器或其他机器的密文转换。
需要 Python 3.10+、Node.js 22+、已安装的 Google Chrome，以及源 Chrome 中尚有效的
ChatGPT 会话。依赖缺失时沿对应工具的现有安装入口处理，不另装 Playwright 或浏览器。

先固定预期账号邮箱和任务自有目标目录。检查已有目标是否已能通过验证；已通过就继续
原任务，不重新导入。目标不存在时用 `--initialize` 创建；该参数拒绝覆盖已有目录。
源 Cookie 库缺失时定位实际 Chrome profile，通过 `--source-cookie-db` 显式传入，不从
历史对话提取凭据。源没有 ChatGPT 会话时继续正常登录，不把 Google 账号选择器里的
账号记忆当成活会话。

```bash
# 从本 Skill 目录运行。先设置两个已核对的值；目录应属于本次任务。
: "${MIGRATION_PROFILE:?set the isolated Chrome directory}"
: "${EXPECTED_EMAIL:?set the expected account email}"

# 仅在目录尚不存在时执行。
node scripts/verify-chatgpt-profile.mjs --profile-dir "$MIGRATION_PROFILE" --initialize

# 目标 Chrome 必须关闭。--yes 只用于已有授权，不代替授权。
python3 scripts/import-google-cookies.py --site chatgpt --destination "$MIGRATION_PROFILE" --yes

# 单独检查上一命令退出码，再启动验证。
node scripts/verify-chatgpt-profile.mjs --profile-dir "$MIGRATION_PROFILE" --expected-email "$EXPECTED_EMAIL"
```

每条命令成功后再执行下一条。命令可从当前宿主获准的本地脚本通道执行；宿主只允许
自带浏览器工具、拒绝启动外部浏览器时，保留该边界，不改通道绕过。

导入器只读源库，通过 SQLite 事务读取当前已提交状态，包含 WAL 中尚未 checkpoint 的
记录。Google 模式保持原有的合并行为；ChatGPT 模式完整替换目标站点 Cookie 集合，避免
旧会话的多余 token 分片残留。其他站点不改动。schema 不一致直接停止，不取字段交集
凑出成功。写入前保留目标库的权限为 0600 的完整备份，写入出错则回滚事务。

验证器只启动本次任务的目标 Chrome，用临时调试端口连接，完成后关闭自己启动的进程。
它读取当前系统 HTTPS 代理；也可用 `--proxy` 显式传入已核对的代理。默认使用普通 Chrome
窗口；`--headless` 是可选模式，验证页出现 challenge 时保持未通过，不将其判为登录失效。
真实安全提示、本人接管或工具拒绝时按当前宿主边界交接，不重复输入。

完成判据为 `status=verified`：重开的目标浏览器返回预期邮箱，且官方额度接口返回非空、
有效用量窗口，响应的账号 ID 与该浏览器会话一致、邮箱与预期一致。`initialized` 只表示
目录已准备，导入器的退出码 0 只表示 Cookie 写入完成。`login_verified=true` 但
`status=unconfirmed` 表示身份已确认、额度读取尚未通过；保留具体缺口并继续原任务允许的
诊断，不调用备用重置、不更换账号补数。返回 2 为未通过，1 为工具错误。

需要撤回本次导入时，先核对目标仍属于本任务且没有后续人工登录或新工作，再关闭目标
Chrome，用导入器输出的**精确备份路径**恢复。恢复会覆盖目标 Cookie 库；它先备份当前
目标状态，拒绝其他目录或其他名称的备份，不触碰源 Chrome：

```bash
: "${COOKIE_BACKUP:?set the exact backup path printed by the importer}"
python3 scripts/import-google-cookies.py --destination "$MIGRATION_PROFILE" --restore-backup "$COOKIE_BACKUP" --yes
```

恢复后重新验证原先应有的状态；备份存在或恢复命令成功不证明网站登录状态。备份含登录
凭据，留在目标 profile 的用户本地目录，不放入 Skill、日志附件、Git 或共享报告。

原有 `--profile a|b` 与默认 Google 模式继续可用；Google Cookie 迁移不保证 Google 服务端
接受会话，也不证明目标已登录 ChatGPT。本流程不迁移历史记录、书签、扩展或密码库。
