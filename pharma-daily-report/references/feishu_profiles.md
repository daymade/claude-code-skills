# 飞书（Lark）CLI 日报发送配置

## lark-cli 检查与安装

```bash
# 检查是否已安装
which lark-cli

# 未安装的话
npm install -g @larksuite/cli
```

## 登录

```bash
# 登录（浏览器扫码）
lark-cli auth login --recommend
```

## 代理注意

飞书是国内服务，lark-cli 调用前**必须**取消代理：

```bash
LARK_CLI_NO_PROXY=1 lark-cli <子命令> ...
```

否则请求会走翻墙代理失败。

## 查找飞书 chat_id

日报发送需要一个 `chat_id`（以 `oc_` 开头）：

```bash
# 列出最近有消息的会话
LARK_CLI_NO_PROXY=1 lark-cli im +chat-search --query " " --page-size 20
```

- 发给**自己**：找"<你的名字>'s Feishu Assistant"，那个 chat_id 就是自己的对话
- 发给**群**：用群名搜索

## 测试发送

```bash
LARK_CLI_NO_PROXY=1 lark-cli --profile <profile名> im +messages-send \
  --chat-id "oc_xxx" \
  --text "测试消息"
```

如果发 markdown：

```bash
LARK_CLI_NO_PROXY=1 lark-cli --profile <profile名> im +messages-send \
  --chat-id "oc_xxx" \
  --markdown "**加粗** 测试"
```

## 常见错误

| 错误码 | 含义 | 解决 |
|--------|------|------|
| 230002 | Bot/User not in chat | 换一个 chat_id（飞书 Assistant 群 bot 不在，不能发），用 P2P 对话或群聊 |
| need_user_authorization | token 过期 | `lark-cli auth login --recommend` 重新授权 |
| timeout / proxy error | 代理问题 | 检查 `LARK_CLI_NO_PROXY=1` 是否生效 |

## Profile 管理

```bash
# 列出所有 profile
lark-cli profile list

# 切换默认
lark-cli profile use <profile名>
```
