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
Use the setup and sending workflows below:

1. **One-time setup**: store the webhook URL, test connectivity, and create a reusable sender script.
2. **Send messages**: craft messages that distinguish state from delta, define every number, and avoid
   the misleading patterns that made earlier backup-sync notifications confusing.

The bundled script `scripts/send_wecom.py` handles the actual HTTP call, using the host network configuration. Recipient identity is explicit configuration:
`self` may send automatically; `others` requires human confirmation; missing identity fails fast.

When integrating an existing Alibaba Cloud SLS notification pipeline or a recurring
digest, read [the SLS adapter guide](references/sls-recurring-notifications.md).
Reuse the project's sampler, scheduler and SLS sync owner; the bundled sender
continues to own ordinary plain-text sends.

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

4. **Classify the exact target and bind the canonical sender** without exposing or rewriting the webhook value:
   ```bash
   uv run --no-project python scripts/set_recipient.py \
     --scope self --label "My private self channel"
   ```
   Use `self` only when the configured webhook is visible only to the user. Use
   `others` for every other person or group. Do not guess when the target is unknown.
   The command also records this sender's absolute path and digest; after the sender
   is upgraded, rerun the command before sending again.

5. **Test connectivity** by sending a test message (run from the skill directory):
   ```bash
   uv run --no-project python scripts/send_wecom.py --message "WeCom webhook test ✅"
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

Read `recipient_scope` and `recipient_label` before sending. A `self` target is
the user's own delivery channel and needs no authorization. An `others` target
is an external send: show the exact label and message and wait for the active
human-confirmation gate. Missing/invalid metadata is a configuration error, not
permission to guess.

Matching webhook URLs proves the same endpoint, not the recipient scope. If new
observations conflict with the stored `self` label, pause only that send and verify
the exact group and audience. A displayed member name alone does not prove a
different person's identity. Preserve normal automatic delivery for a confirmed
`self` binding; do not relabel a group or rewrite shared metadata to bypass the
confirmation boundary. For recurring delivery to `others`, confirmation must cover
the exact group, report content and schedule, plus any separately required deployment
approval.

### Option A: Use the bundled script directly

```bash
uv run --no-project python scripts/send_wecom.py \
  --message "你的消息内容"
```

For multiline messages, use a file:

```bash
cat > /tmp/wecom_msg.txt <<'EOF'
Claude Code 备份同步完成 ✅

- 验证：0 缺失，0 滞后
EOF

uv run --no-project python scripts/send_wecom.py \
  --file /tmp/wecom_msg.txt
```

### Option B: Inline curl

If you prefer not to use the script:

```bash
curl -s -X POST 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "msgtype": "text",
    "text": {
      "content": "YOUR_MESSAGE"
    }
  }'
```

**Network**: Inherit the host/project HTTP(S) proxy and `no_proxy` policy. A required proxy must remain in use; do not infer a direct-connect requirement from the Tencent domain. Configure an HTTP(S) proxy explicitly when the host requires one: Python urllib does not implement generic SOCKS `ALL_PROXY` routing. On macOS, an empty proxy environment can still select the system proxy. For proxy selection, exceptions and HTTP-bypass versus TUN diagnosis, load `tunnel-doctor` and its proxy-conflict reference (`proxy_conflict_reference.md`, NO_PROXY section); inspect the sender process rather than clearing all proxies.

After upgrading the sender, refresh its configured digest using the existing
`set_recipient.py` workflow, preserving the same scope and label. Do not relabel
a group as `self` merely to pass the guard.

## Workflow: Add WeCom Notification to a Script

When a user asks "let my backup script send WeCom notifications", do the following:

1. Confirm the webhook is configured (see Quick Start).
2. Read the explicit recipient scope/label; auto-send only when scope is `self`.
3. Identify the notification type (backup-complete, alert, status-update, custom).
4. Collect the exact numbers and their definitions from the script output.
5. Craft the message using the templates above.
6. For `others`, obtain human confirmation; then call `scripts/send_wecom.py`.
7. Verify the message arrived at the configured target. For automatic monitor/worker integration, follow the receipt contract below.

### Automatic worker receipts

Use the existing bound sender and target; keep event identity and delivery state in the owning worker. For one automatic event, call `send_message(..., max_attempts=1)` or the supported guard-owned outbox path. The general manual-send retry default is not the worker's delivery policy.

Classify the parsed response before deciding whether a later attempt is permitted:

| Evidence | Worker outcome |
|---|---|
| JSON object with integer `errcode=0` | API accepted; receiver confirmation is a separate observation |
| JSON object with nonzero integer `errcode` | Explicit API rejection |
| Missing/null `errcode`, boolean, string, non-integer, invalid JSON, timeout or lost connection | Unknown; keep the event identity and do not automatically replay it |

For Python, test `type(code) is int`; `isinstance(False, int)` is true and `False == 0` must not become acceptance. If the generic sender raises before returning a valid response, the owning worker keeps the result unknown. A new test must exercise a genuinely distinct event with an explicit test label, not rename or resubmit an ambiguous old event. Verify the actual scheduler/worker → event → sender → receipt path; a standalone bot call does not validate the background chain.

## What This Skill Does NOT Do

- It does not create or manage WeCom group bots — get the webhook key from WeCom first.
- It does not infer who a webhook reaches — classify the target explicitly with `set_recipient.py`.
- It does not handle rich media messages (markdown cards, news, images) — only plain text.
- Manual `--message` / `--file` sends retry transient errors up to 3 times. Guard-owned
  automatic `--outbox` delivery makes exactly one HTTP attempt and requires the
  guard-approved payload digest; a later run never sends a pre-existing payload.
- It does not change host proxy configuration or switch routes automatically after a failure.

## Troubleshooting

### `Connection closed` or timeout

Inspect the configured route without printing proxy credentials. Follow the host's
approved direct/proxy policy and diagnose the failing connection on that route.
Do not silently clear proxies, try another endpoint, or replay an ambiguous send.

### Message not received, but curl returned 200

Check the response body: HTTP 200 with nonzero `errcode` is failure. `errcode=0` means API acceptance, not recipient receipt. Verify the intended group and message where receipt matters. A direct bot test cannot validate an SLS/other scheduler: exercise and inspect that native path separately within the authorized test count.

### Config file not found

Run the setup step again. The script expects `~/.config/setup-notifications-via-wecom/config.json` with a `webhook_url` field.

## References

- `references/message_best_practices.md` — condensed checklist distilled from this session's corrections.
- `references/sls-recurring-notifications.md` — read for SLS-backed recurring reports: result-size limits, evaluation dates, existing-owner reuse and native delivery acceptance.
- `scripts/send_wecom.py` — the sender script.
- `scripts/set_recipient.py` — atomically records `self` versus `others` plus the canonical sender path/digest without printing the webhook.
