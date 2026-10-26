# Cookie Copy 接入

仅在用户已授权读取源登录态、写入精确目标目录，且当前宿主允许外部 Chrome 脚本时走此分支。

1. 加载独立 `cookie-copy`，按其入口准备、复制及验证登录身份。缺失时先安装
   `cookie-copy@daymade-skills`，通过当前宿主的 Skill 安装／源同步入口读回；不从缓存猜路径，
   不把安装或命令发现当作任务完成。保留预期邮箱、源和目标目录，依赖准备后从缺失步骤继续。
2. 将加载到的 `cookie-copy` 根目录设为 `COOKIE_COPY_SKILL_DIR`。同一源码仓中的兄弟目录
   可自动解析；独立安装的插件必须显式传入该目录，缺失或空值报错。不要更改全局配置。
3. 登录身份通过后，运行本 Skill 的额度验证器，仍使用相同目标和预期邮箱：

```bash
: "${COOKIE_COPY_SKILL_DIR:?set the resolved cookie-copy Skill directory}"
: "${MIGRATION_PROFILE:?set the selected isolated Chrome directory}"
: "${EXPECTED_EMAIL:?set the expected account email}"
COOKIE_COPY_SKILL_DIR="$COOKIE_COPY_SKILL_DIR" node scripts/verify-chatgpt-profile.mjs --profile-dir "$MIGRATION_PROFILE" --expected-email "$EXPECTED_EMAIL"
```

本 Skill 的 `status=verified` 仍要求预期邮箱匹配、官方额度接口 HTTP 200、响应账号
与浏览器会话一致且用量窗口有效。`cookie-copy` 的 `status=verified` 只证明登录身份。
`login_verified=true` 而额度结果未确认时，保留具体缺口；不消耗备用重置、不换账号补数。

原命令 `scripts/import-google-cookies.py --profile a|b`、默认 Google 模式，以及
`--site chatgpt --destination`、`--source-cookie-db`、`--restore-backup` 继续通过适配器调用
`cookie-copy/scripts/copy-cookies.py`。`--profile a|b` 仍映射到原来的 Tibo 隔离目录。
目标初始化的 `scripts/verify-chatgpt-profile.mjs --initialize` 也保留，依赖同一 `cookie-copy`。
复制、备份、恢复与登录验证的权限和故障处理只在 `cookie-copy` 维护；源无会话时恢复正常登录，
不把 Google 账号记忆当作活会话。需要密码、验证码或人工确认时沿当前宿主边界交接，
不重复输入或更换通道。现有目标已可查询时直接继续，不重新复制。
