#!/usr/bin/env python3
"""
Webhook 通知系统 - 新文章检测时发送通知

功能：
- 支持多种通知渠道 (钉钉、飞书、企业微信、Slack、Discord、Telegram)
- 新文章检测时自动发送
- 支持自定义消息模板
- 与 monitor.py 集成
- 支持 RSS 更新通知

吸取竞品精华：
- IFTTT: 灵活的 webhook 配置
- Zapier: 多平台支持

作者: Claude Code
版本: 1.0.0
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('wechat-notifier')


@dataclass
class NotificationMessage:
    """通知消息"""
    title: str
    content: str
    url: Optional[str] = None
    author: Optional[str] = None
    publish_time: Optional[str] = None
    tags: List[str] = None
    image_url: Optional[str] = None
    priority: str = "normal"  # low, normal, high


class WebhookNotifier:
    """Webhook 通知器"""

    def __init__(self):
        self.channels: Dict[str, Callable] = {
            'dingtalk': self._send_dingtalk,
            'lark': self._send_lark,
            'wecom': self._send_wecom,
            'slack': self._send_slack,
            'discord': self._send_discord,
            'telegram': self._send_telegram,
        }

    def _send_request(self, url: str, payload: Dict, headers: Optional[Dict] = None) -> bool:
        """发送 HTTP 请求"""
        import requests

        headers = headers or {'Content-Type': 'application/json'}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            logger.info(f"通知发送成功: {url[:50]}...")
            return True
        except Exception as e:
            logger.error(f"通知发送失败: {e}")
            return False

    def _send_dingtalk(self, webhook_url: str, message: NotificationMessage) -> bool:
        """发送钉钉通知"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": message.title,
                "text": f"## {message.title}\n\n"
                        f"**作者**: {message.author or '未知'}\n\n"
                        f"{message.content[:500]}...\n\n"
                        f"[阅读原文]({message.url})"
            }
        }

        if message.image_url:
            payload['markdown']['text'] += f"\n\n![]({message.image_url})"

        return self._send_request(webhook_url, payload)

    def _send_lark(self, webhook_url: str, message: NotificationMessage) -> bool:
        """发送飞书通知"""
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": message.title},
                    "template": "blue" if message.priority == "normal" else "red"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**作者**: {message.author or '未知'}\n\n{message.content[:400]}..."
                        }
                    },
                    {"tag": "hr"},
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "阅读原文"},
                                "url": message.url,
                                "type": "primary"
                            }
                        ]
                    }
                ]
            }
        }
        return self._send_request(webhook_url, payload)

    def _send_wecom(self, webhook_url: str, message: NotificationMessage) -> bool:
        """发送企业微信通知"""
        payload = {
            "msgtype": "news",
            "news": {
                "articles": [
                    {
                        "title": message.title,
                        "description": f"{message.content[:300]}...",
                        "url": message.url,
                        "picurl": message.image_url or ""
                    }
                ]
            }
        }
        return self._send_request(webhook_url, payload)

    def _send_slack(self, webhook_url: str, message: NotificationMessage) -> bool:
        """发送 Slack 通知"""
        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": message.title}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*作者*\n{message.author or 'Unknown'}"},
                        {"type": "mrkdwn", "text": f"*发布时间*\n{message.publish_time or 'N/A'}"}
                    ]
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message.content[:500] + "..."}
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Read Article"},
                            "url": message.url,
                            "style": "primary"
                        }
                    ]
                }
            ]
        }
        return self._send_request(webhook_url, payload)

    def _send_discord(self, webhook_url: str, message: NotificationMessage) -> bool:
        """发送 Discord 通知"""
        payload = {
            "embeds": [
                {
                    "title": message.title,
                    "description": message.content[:500] + "...",
                    "url": message.url,
                    "color": 3447003,
                    "fields": [
                        {"name": "Author", "value": message.author or "Unknown", "inline": True},
                        {"name": "Published", "value": message.publish_time or "N/A", "inline": True}
                    ],
                    "timestamp": datetime.utcnow().isoformat()
                }
            ]
        }
        if message.image_url:
            payload["embeds"][0]["image"] = {"url": message.image_url}

        return self._send_request(webhook_url, payload)

    def _send_telegram(self, bot_token: str, message: NotificationMessage, chat_id: str = None) -> bool:
        """发送 Telegram 通知"""
        import requests

        if not chat_id:
            chat_id = os.getenv('TELEGRAM_CHAT_ID')

        if not chat_id:
            logger.error("Telegram 需要 chat_id")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        text = f"**{message.title}**\n\n"
        text += f"*{message.author or 'Unknown'}*\n\n"
        text += f"{message.content[:400]}...\n\n"
        text += f"[Read more]({message.url})"

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False
        }

        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Telegram 发送失败: {e}")
            return False

    def send(self, channel: str, webhook_url: str, message: NotificationMessage, **kwargs) -> bool:
        """
        发送通知

        Args:
            channel: 通知渠道 (dingtalk, lark, wecom, slack, discord, telegram)
            webhook_url: Webhook URL
            message: 通知消息
            **kwargs: 额外参数

        Returns:
            bool: 是否成功
        """
        if channel not in self.channels:
            logger.error(f"不支持的通知渠道: {channel}")
            return False

        return self.channels[channel](webhook_url, message, **kwargs) if channel == 'telegram' else self.channels[channel](webhook_url, message)


class NotificationManager:
    """通知管理器 - 与 monitor.py 集成"""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or os.path.expanduser('~/.wechat-scraper/notifications.json')
        self.config = self._load_config()
        self.notifier = WebhookNotifier()

    def _load_config(self) -> Dict:
        """加载配置"""
        config_path = Path(self.config_file)
        if config_path.exists():
            try:
                return json.loads(config_path.read_text(encoding='utf-8'))
            except Exception as e:
                logger.error(f"加载配置失败: {e}")

        return {"channels": []}

    def _save_config(self):
        """保存配置"""
        Path(self.config_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.config_file).write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

    def add_channel(self, name: str, channel_type: str, webhook_url: str, **kwargs):
        """添加通知渠道"""
        self.config['channels'].append({
            'name': name,
            'type': channel_type,
            'url': webhook_url,
            'enabled': True,
            'options': kwargs
        })
        self._save_config()
        logger.info(f"已添加通知渠道: {name}")

    def remove_channel(self, name: str):
        """删除通知渠道"""
        self.config['channels'] = [c for c in self.config['channels'] if c['name'] != name]
        self._save_config()
        logger.info(f"已删除通知渠道: {name}")

    def list_channels(self):
        """列出所有渠道"""
        return self.config['channels']

    def notify_new_article(self, article: Dict):
        """新文章通知"""
        message = NotificationMessage(
            title=article.get('title', '新文章'),
            content=article.get('content', '')[:1000],
            url=article.get('url'),
            author=article.get('author'),
            publish_time=article.get('publish_time'),
            tags=article.get('tags', [])
        )

        success_count = 0
        for channel in self.config['channels']:
            if not channel.get('enabled', True):
                continue

            if self.notifier.send(
                channel['type'],
                channel['url'],
                message,
                **channel.get('options', {})
            ):
                success_count += 1

        logger.info(f"通知已发送到 {success_count}/{len(self.config['channels'])} 个渠道")
        return success_count


def main():
    parser = argparse.ArgumentParser(description='Webhook 通知系统')
    parser.add_argument('--config', help='配置文件路径')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # add
    add_parser = subparsers.add_parser('add', help='添加通知渠道')
    add_parser.add_argument('name', help='渠道名称')
    add_parser.add_argument('type', choices=['dingtalk', 'lark', 'wecom', 'slack', 'discord', 'telegram'])
    add_parser.add_argument('url', help='Webhook URL')

    # remove
    remove_parser = subparsers.add_parser('remove', help='删除通知渠道')
    remove_parser.add_argument('name', help='渠道名称')

    # list
    list_parser = subparsers.add_parser('list', help='列出通知渠道')

    # test
    test_parser = subparsers.add_parser('test', help='测试通知')
    test_parser.add_argument('--channel', help='指定渠道名称')
    test_parser.add_argument('--title', default='测试通知', help='测试标题')
    test_parser.add_argument('--content', default='这是一条测试消息', help='测试内容')

    args = parser.parse_args()

    manager = NotificationManager(args.config)

    if args.command == 'add':
        manager.add_channel(args.name, args.type, args.url)

    elif args.command == 'remove':
        manager.remove_channel(args.name)

    elif args.command == 'list':
        channels = manager.list_channels()
        if not channels:
            print("未配置通知渠道")
        else:
            print(f"已配置 {len(channels)} 个通知渠道:")
            for c in channels:
                status = "✓" if c.get('enabled', True) else "✗"
                print(f"  {status} {c['name']} ({c['type']})")

    elif args.command == 'test':
        message = NotificationMessage(
            title=args.title,
            content=args.content,
            url="https://mp.weixin.qq.com"
        )

        if args.channel:
            channel = next((c for c in manager.list_channels() if c['name'] == args.channel), None)
            if channel:
                success = manager.notifier.send(channel['type'], channel['url'], message)
                print(f"测试结果: {'成功' if success else '失败'}")
            else:
                print(f"未找到渠道: {args.channel}")
        else:
            count = manager.notify_new_article({
                'title': args.title,
                'content': args.content,
                'url': 'https://mp.weixin.qq.com'
            })
            print(f"已发送到 {count} 个渠道")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
