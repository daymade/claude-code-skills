# 逐账号额度查询与网页登录恢复

## 先固定账号范围

把用户确认的账号清单作为查询范围。区分三个集合：用户拥有的订阅账号、浏览器当前保存的
ChatGPT 登录态、本机已经登录的 Google 账号。它们的数量可以不同。Google 选择页里的
其他邮箱不自动属于本次授权范围，也不能直接计为 Pro 账号。

用户确认有四个账号，就查询四行；不要因浏览器只保存两个而把分母改成二。只读到两个时继续
寻找另外两个的合法入口。只有实际遇到密码、验证码、账号拒绝访问或工具不可用等具体阻塞，
才报告对应账号未核实。遵守当前宿主的登录、验证码和凭据确认规则。

用户说没有使用某个账号管理器时，停止从那个工具推断当前账号状态。其历史记录至多提供
待核对的邮箱线索；“会话过期”证明查询通道失效，不证明额度耗尽。

**入口裁定（不因「这次形态不太一样」重开）**：2026-09-08 用户已裁定这批账号**不用
CC Switch 管理**——即使 `~/.cc-switch/cc-switch.db` 存在且记有 codex providers，也只把
它当上面的邮箱线索来源，不作查询通道。首选入口是官网的 Google 登录态；本机凭据文件
（`~/.codex/auth.json`）只覆盖当前 CLI 登录的那一个账号。2026-09-10 二次实测：仍然
因为优先去翻 CC Switch 与本机备份目录被当场纠正——裁定之后不重开，直接走正路。

## 实时 API：只读一个明确账号

在技能源码目录执行；依赖与参数以脚本帮助为准：

```bash
uv run python scripts/query_usage.py --help
uv run python scripts/query_usage.py
uv run python scripts/query_usage.py --auth-file /path/to/authorized/auth.json --expected-email account@example.com
```

显式参数示例需替换为用户明确授权的文件和邮箱；有符合帮助要求的 Python 时可省略 `uv run`。
Windows 未实测。请求、认证文件默认位置、参数和退出行为的可执行 SSOT 是
[query_usage.py](../scripts/query_usage.py)。不从对话历史寻找凭据，也不从别的账号借 token。
脚本使用的端点是客户端内部接口，2026-09-08 实测，
不是稳定的公共 API 契约；接口失效时转官网 Usage 页，不猜新端点。

| 字段 | 读法 |
|---|---|
| `rate_limit.primary_window` / `secondary_window` | 两个槽位不是固定的周/5h 标签；脚本按窗口时长解释 |
| `used_percent` | 已用比例，不是剩余比例；使用脚本的 `remaining_percent` 输出 |
| `reset_at` | 原始时间交由脚本转换，展示时再转用户时区；缺失保留未知 |
| `rate_limit_reset_credits.available_count` | 保存的备用重置数量 |
| `rate_limit_reset_credits.applicable_available_count` | 此刻可适用的数量；不替代保存总数 |
| `credits.balance` / `has_credits` | 购买的额外 credits；不能据此判断备用重置 |

实测同一响应可以同时出现 `available_count: 2`、`applicable_available_count: 0`、
`credits.balance: "0"`。这仍然是存着两次备用重置。不要把“现在不能适用”或“购买余额为零”
改写成“没有备用重置”。API 计数未提供类型和逐笔到期明细时，不把它擅自命名为 Full reset；
到官网逐条读 `Full reset` 与到期时间。也不按名字猜 `applicable` 为零的原因。

按脚本返回的 `status`、`notes`、各窗口及空字段判断可报告范围；请求成功不等于所有字段齐全。
脚本的状态判定覆盖用量窗口与备用重置读数；可选的套餐或购买余额仍可能缺失，不能把 `ok`
解释为这些字段已核实。字段未知时保留空值并按需要转官网，不补零、不把其他窗口当周额度。

维护脚本或响应解释时，在源码中的技能目录运行离线测试（分发包不含测试目录）：

```bash
uv run python -m unittest discover -s tests -v
```

这条命令不访问真实账号。需要验证认证、端点或请求行为的改动时，另做已授权账号的只读冒烟，
并比较查询前后的认证文件哈希；不要用兑换重置或切换 CLI 登录测试查询功能。

## 官网：复用 Google 登录，逐个查完

1. 先记录当前浏览器/配置文件、当前 ChatGPT 邮箱、切换菜单保存的邮箱集合及待恢复目标。
   查看页面身份后再绑定额度，不能用头像名字或当前 CLI 身份替代网页身份。
2. 打开官方用量页：`https://chatgpt.com/codex/settings/usage`。2026-09-08 实测会跳转到
   `https://chatgpt.com/codex/cloud/settings/analytics#usage`，页面标题为 `Codex and Work Analytics`。
   跳转或路径变化时按可见 Settings → Analytics → Usage 导航。
3. 读取 `Weekly usage limit … remaining`、页面实际出现的 5 小时窗口、重置时间、
   `Usage limit resets` 区域内的每笔类型与到期时间。`No usage limit resets available` 才是网页
   对零库存的直接证据；`Credits remaining 0` 不是。
4. 对尚未登录的目标账号，用 ChatGPT 的 `Add another account` / `Log in to another account`
   → `Continue with Google`。如果 Google 已保存该邮箱，直接选择这个已有账号继续登录；
   不要求用户重新提供密码，不创建新账号，不重新注册或购买 Pro。登录成功后重新核对 ChatGPT
   邮箱与计划，再读用量。Google 登录成功本身不能证明 ChatGPT 的计划或额度。
5. 一次只切一个账号，同一浏览器的多标签页共享登录状态。不要并行切账号，也不要让旧标签页
   的缓存余额冒充新账号余额。余额采到后记录时间，进入下一账号；不要因正在消耗而反复全表刷新。

仅使用当前宿主提供的浏览器工具；元素索引与 OAuth URL 都从当前页面取得。索引过期后先取
新状态，不重放旧索引。`Loading`、`Switching accounts` 或禁用的个人信息菜单不是失败终态：
等导航完成后读新状态；菜单已打开但仍禁用时可以关闭后重新打开一次。工具超时先确认当前
标签页已经到哪个页面，不能把一次导航超时解释成登录失败。

2026-09-10 kimi-webbridge 宿主实测的执行细节（原则通用）：读 usage 页数据用脚本提取
目标文本，不整页抓无障碍树——主页快照可上万 token，`document.body.innerText` 加正则
一次即可拿全邮箱、weekly 剩余、reset 时刻与 resets 数量。账号菜单经 portal 渲染，快照
可能抓不到菜单内容，菜单是否展开用**截图**确认，不靠快照下结论。页面按钮普遍校验
`isTrusted`，合成 click 与 PointerEvent 事件点不动，要走宿主的**真实输入通道**
（kimi-webbridge 即 CDP `Input.dispatchMouseEvent` 的 mouseMoved→mousePressed→
mouseReleased 序列）；宿主没有真实输入通道时不自起浏览器、不改用外部自动化（上节
「仅使用当前宿主提供的浏览器工具」仍然适用），把点击步骤标记为需人工完成并如实报告。
身份核对走 UI：`/backend-api/me` 与 accounts/check 端点实测返回空 PII（email 为空
字符串），完整邮箱以账号切换菜单的显示为准。点 `Continue with Google` 后当前标签页
可能被浏览器中**另一个扩展**导到 `chrome-extension://` 页，此后宿主全部工具报
「Cannot access a chrome-extension:// URL」——修复是关掉坏标签页再新开标签页导航
（在同一会话 tab group 内完成）；同一 Google OAuth 步骤第二次被劫持就把该步标记为需
人工完成并如实报告，不反复重试。

缩小读取结果到账号菜单、用量卡片和重置列表，避免反复输出全部聊天侧栏。过滤 tab 清单时
去掉 URL 的查询参数与片段；OAuth 回调可能把 token 或授权码放进 URL。不要保存完整回调
URL，不从聊天记录、浏览器 Cookie 库或旧工具回执中搜 token 来替代正常登录。

## 登录上限与恢复

2026-09-08，官方帮助页写每个会话最多两个账号；同日实际点击第三个账号入口，弹窗要求
先选择一个账号退出。这是当时该网页会话的限制，不把它写成永久上限。用户说曾看到三个时，
记录其观察并检查当前菜单与添加提示；文档和单次实测都不能抹掉另一时刻的观察。

遇到上限时，保留用户正在工作的账号，明确选择允许临时替换的另一个网页登录位。
用户已授权逐个查账号且临时退出不影响进行中的工作时可继续；若会丢失草稿、打断其他工作，
或必须选择哪个账号长期保留，则先确认。绝不选择 `Log out of all accounts`。

不要把“菜单收起了”当作退出成功。实测 Codex 页点击某账号的 `Log out` 后菜单消失，但
后续清单仍能保留该账号；具体原因未核实。更明确的路径是回到 ChatGPT 首页，
`Add another account` → `Choose an account to log out` → 选择精确邮箱 → `Log out and continue`。
之后沿可见 Google 登录流程进入目标账号，并读回清单。直接打开登录链接可能改变保存组合，
不能用“两个账号都各登录成功过”证明两者同时保留。

上限弹窗的「选择一个退出」流程会**不可预期地改变整个保存集合**，不止被退出的那个账号：
2026-09-10 实测为添加第三个账号退出账号 B 后，终态集合里剩下的「1」不是未被退出的
账号 A，而是刚被退出的账号 B 的可恢复条目（Welcome back 弹窗可一键回登）——**未被
退出的账号 A 登录位反而消失**，且新账号 C 因 OAuth 被劫持未能加成。所以恢复义务覆盖
完整集合：操作前记录集合与当前账号（官网 SOP 第 1 步的要求），操作后逐项读回对比；
缺位与「当前账号不在」分别报告，缺的登录位需要用户手动走一次 Google 登录才能补回，
不冒称已恢复。

查询结束后按开始时记录的目标恢复：确认原邮箱集合重新出现在切换菜单中，再通过菜单选回
原当前账号，最后读回当前身份。CLI 与网页是两套登录面；网页恢复不证明 CLI 未变，任务不要求
切 CLI 时不运行 `codex login/logout`，也不替换 `auth.json`。恢复失败时保留可操作页面，
准确报告原集合、当前集合与剩余动作；不得宣布已恢复。

用户希望四个账号都常驻、当前同一会话只容纳两个时，说明未满足的这一项。多个隔离浏览器
配置文件是可讨论的替代方案，需分别登录与验证；本技能没有实测四账号长期保留，不宣称已经
做到，不自动安装扩展、复制 Cookie 或新建整套账号管理系统。达到当前上限后不循环尝试加入。

## 汇报与停止条件

每个用户确认的账号一行：邮箱/标签、查询时间、周剩余、5 小时剩余（如有）、备用重置数量、
必要的到期时间和来源。省略所有账号都没有的 5 小时列；unknown 与 0 分开。
先回答“是否全部耗尽 / 哪个可继续用”，再放表格。100% 与 97% 分别写满额、接近满额，
不要为了附和用户把两者都叫满额。不跨账号相加剩余百分比；可汇总已核实的备用重置数量，
但未查完时必须标明“已核实小计”。

用户确认的所有账号均有当前读数，或某账号的正常认证路径遇到明确阻塞；且网页登录恢复
已读回或具体缺口已交代，即停止。只完成半张表、只读取过期工具记录、只说明没有现成登录态，
都不是提前结束理由。查询不授权点击 `Use reset`、购买 credits、改套餐或启用自动充值。

## 来源

- [OpenAI：banked resets](https://help.openai.com/en/articles/20001498-how-banked-codex-resets-work)
- [OpenAI：account switching](https://help.openai.com/en/articles/20001068)
- 2026-09-08 已授权现场查询：四个独立 Google 登录、官网用量卡与重置列表、官方用量端点、
  第三个登录位提示、最终邮箱集合与当前身份读回。只将这些操作边界归纳进此文，不保存私人邮箱和凭据。
