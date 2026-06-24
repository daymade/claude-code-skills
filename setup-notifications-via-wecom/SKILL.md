---
name: setup-notifications-via-wecom
description: >-
  Set up and send technical status notifications through WeCom (Enterprise WeChat) webhooks.
  Use this skill whenever the user needs to send notifications, alerts, backup completion reports,
  or status updates via WeCom; when they mention 企业微信, 企微机器人, webhook, or alerting;
  or when a message needs to be clear, unambiguous, and technically precise rather than vague or
  condescending.
---

# Setup Notifications via WeCom

## Overview

This skill helps you send clear, unambiguous technical notifications through a WeCom group bot webhook.
It covers two things:

1. **One-time setup**: store the webhook URL, test connectivity, and create a reusable sender script.
2. **Send messages**: craft messages that distinguish state from delta, define every number, and avoid
   the misleading patterns that made earlier backup-sync notifications confusing.

The bundled script `scripts/send_wecom.py` handles the actual HTTP call, including the proxy-unset rule
required for Tencent services in mainland China.

## When to Use This Skill

Trigger this skill when the user:
- Says "send a WeCom notification", "企业微信通知", "企微机器人", or "webhook 通知".
- Wants to set up alerting for a backup, sync, cron job, or service status.
- Asks you to write a status/alert message and you need to make it clear and unambiguous.
- Mentions a message was confusing or misleading and wants it fixed.

## Quick Start: Configure the Webhook

1. **Check existing config**:
   ```bash
   cat ~/.config/setup-notifications-via-wecom/config.json
   ```
   If it exists and contains `webhook_url`, skip to [Send a Message](#send-a-message).

2. **Get the webhook URL** from the WeCom group bot settings. It looks like:
   ```
   https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
   ```

3. **Store it privately** (outside the skill bundle, so it survives updates):
   ```bash
   mkdir -p ~/.config/setup-notifications-via-wecom
   echo '{"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"}' \
     > ~/.config/setup-notifications-via-wecom/config.json
   chmod 600 ~/.config/setup-notifications-via-wecom/config.json
   ```

4. **Test connectivity** by sending a test message (run from the skill directory):
   ```bash
   uv run --with requests scripts/send_wecom.py --message "WeCom webhook test ✅"
   ```
   If you see the message in the WeCom group, setup is done.

## Message Best Practices

These rules come from real corrections. Apply them to every notification.

### 1. Headline First
The first line must say what happened. Do not bury the conclusion.

```
Claude Code 备份同步完成 ✅
```

### 2. Distinguish State vs Delta
- **State**: current totals (e.g., source has 1075 main sessions, backup has 2328).
- **Delta**: what changed in this run (e.g., 13 main sessions + 230 other files were added since 03:00).

Never say "synced 1075 sessions" if only 13 were new today.

### 3. Define Every Number
Every count must be accompanied by what it counts. Prefer:

```
- 源目录主 session：1075 个
- 备份主 session：2328 个
```

Avoid undefined terms like "session" alone — it may include workflow journals, subagent files, or tool outputs.

### 4. Use Plain Location Names, Not Jargon
Prefer:
- "电脑上" / "源目录"
- "备份里" / "备份仓库"

Avoid:
- "当前"
- "含历史"
- "旧 session" (unless defined)

### 5. Omit Noise
Do not include commit hashes, file paths, internal documentation references, or verbose explanations unless the user explicitly asks for them.

### 6. Be Technically Precise, Not Condescending
Use correct technical terms and define them. Do not translate everything into "大白话" simplifications that hide precision.

### 7. Include Verification Metrics
When the user asked "does it miss anything?", answer directly:

```
- 验证：0 缺失，0 滞后
```

### 8. End with a Next Action
Tell the user whether they need to do anything:

```
- 下一步：无需操作，下次自动同步 03:00
```

## Notification Templates

### Backup Sync Completion

Use when a backup/sync job finishes and you need to report completeness.

```
Claude Code 备份同步完成 ✅

- 自动同步：今日 03:00 正常执行
- 本次手动同步：补充 03:00 后的增量
  - 主 session：13 个
  - 子代理/工具输出/工作流：230 个
  - 合计：243 个文件
- 验证：0 缺失，0 滞后
- 当前状态：
  - 源目录主 session：1075 个
  - 备份主 session：2328 个
- 下一步：无需操作，下次自动同步 03:00
```

### Alert

Use when something requires **immediate action**. Do not use this template for routine "all good" updates.

```
🚨 [P?] [服务/任务名] [症状]

- 影响：[谁/什么受影响，程度如何]
- 严重程度：[P1–P5 等级]
- 开始时间：[YYYY-MM-DD HH:MM TZ]
- 已采取：[正在做的动作]
- 下一步：[建议动作或预计下次更新时间]
- 相关链接：[dashboard/runbook，可选]
```

Rules:
- Alert on symptoms, not causes (e.g., "API error rate > 10%" not "CPU 99%").
- If the recipient cannot do anything concrete, do not send it as an alert.
- Be honest about uncertainty; do not guess at root cause.

### Status Update

Use for routine "all good" updates.

```
[任务名] 状态正常 ✅

- 检查时间：2026-06-24 03:00 CST
- 关键指标：
  - 源目录主 session：1075 个
  - 备份主 session：2328 个
- 本次变更：无
- 下一步：无需操作
```

## Send a Message

### Option A: Use the bundled script directly

```bash
uv run --with requests scripts/send_wecom.py \
  --message "你的消息内容"
```

For multiline messages, use a file:

```bash
cat > /tmp/wecom_msg.txt <<'EOF'
Claude Code 备份同步完成 ✅

- 验证：0 缺失，0 滞后
EOF

uv run --with requests scripts/send_wecom.py \
  --file /tmp/wecom_msg.txt
```

### Option B: Inline curl

If you prefer not to use the script:

```bash
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  curl -s -X POST 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "msgtype": "text",
    "text": {
      "content": "YOUR_MESSAGE"
    }
  }'
```

**Critical**: Tencent services (WeChat/WeCom) must bypass the local proxy. The `env -u ...` prefix is required.

## Workflow: Add WeCom Notification to a Script

When a user asks "let my backup script send WeCom notifications", do the following:

1. Confirm the webhook is configured (see Quick Start).
2. Identify the notification type (backup-complete, alert, status-update, custom).
3. Collect the exact numbers and their definitions from the script output.
4. Craft the message using the templates above.
5. Call `scripts/send_wecom.py` with the message.
6. Verify the message arrived in the WeCom group.

## What This Skill Does NOT Do

- It does not create or manage WeCom group bots — get the webhook key from WeCom first.
- It does not handle rich media messages (markdown cards, news, images) — only plain text.
- It does not retry indefinitely — the script retries transient errors 3 times and then fails.
- It does not send messages without the proxy-unset guard.

## Troubleshooting

### `Connection closed` or timeout

WeCom endpoints may fail if local proxy env vars leak into the request. The script and inline curl examples already unset them. If it still fails:

```bash
env | grep -i proxy
```

Unset any that are set before running the sender.

### Message not received, but curl returned 200

Check the response body. WeCom returns 200 even for errors like invalid key or message-too-long. The script prints the full response; read it.

### Config file not found

Run the setup step again. The script expects `~/.config/setup-notifications-via-wecom/config.json` with a `webhook_url` field.

## References

- `references/message_best_practices.md` — condensed checklist distilled from this session's corrections.
- `scripts/send_wecom.py` — the sender script.
