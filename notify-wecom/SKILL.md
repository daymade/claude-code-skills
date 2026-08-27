---
name: notify-wecom
description: >-
  Send a single one-off message to a WeCom (Enterprise WeChat) group bot. Use this skill whenever
  the user says "/notify-wecom", "send a quick WeCom message", "企微通知一下", "临时发一条企业微信",
  or any one-shot notification that does not need a reusable template or setup workflow.
argument-hint: "[message]"
---

# /notify-wecom

Send a single message to a WeCom group bot.

## Human confirmation boundary

Read the explicit `recipient_scope` and `recipient_label` from the shared config.
`self` is the user's own delivery channel and may send without authorization.
`others` requires the active human-confirmation gate with the exact label and
message. Missing/invalid scope is a configuration error: stop and classify the
target; do not guess. A local alert/outbox item still needs identity/content
validation before either route.

## Usage

```
/notify-wecom Claude Code 备份完成 ✅
```

The skill reads the webhook URL from the shared config file:

```
~/.config/setup-notifications-via-wecom/config.json
```

If the config is missing, it prints the one-line setup command and stops.

## Prerequisite

This skill is a lightweight companion to `setup-notifications-via-wecom`. Either:

- Install `setup-notifications-via-wecom` first (recommended — it provides the webhook setup steps and its bundled sender), or
- Create the config file manually as shown below.

## What It Does

1. Reads `~/.config/setup-notifications-via-wecom/config.json` for `webhook_url`, `recipient_scope`, and `recipient_label`.
2. Unsets all local proxy env vars (Tencent endpoints must be reached directly).
3. If scope is `self`, sends without an authorization prompt. If scope is `others`, presents the exact label and message for human confirmation.
4. Sends via the WeCom webhook using the sender from `setup-notifications-via-wecom` (or an equivalent inline curl call).
5. Reports success or the exact WeCom error; authorization alone is not delivery proof.

## Examples

```
/notify-wecom 服务上线成功 🚀
/notify-wecom 告警：build 失败，请检查
/notify-wecom 今日同步完成，0 缺失 0 滞后
```

## Multi-line Messages

For multi-line messages, wrap in triple quotes or use a file:

```
/notify-wecom "第一行
第二行
第三行"
```

## Failure Modes

- **Config missing**: Run the setup step from `setup-notifications-via-wecom`, or create the config file manually.
- **Recipient or sender identity missing/invalid**: Use `setup-notifications-via-wecom`'s `set_recipient.py` command; never infer self versus others from the webhook URL, and never trust a script merely because its basename is `send_wecom.py`.
- **Webhook key invalid**: WeCom returns an `errcode`; the skill prints it.
- **Proxy still interfering**: If you have proxy vars set outside the standard names, unset them first.

## Limitations

- Plain text only. No markdown cards, images, or @mentions.
- Message length limit is 4096 bytes (UTF-8).
- No templating — use `setup-notifications-via-wecom` for structured backup/alert/status messages.
- A prepared pending item is not a delivery receipt; only the sender response proves delivery.
