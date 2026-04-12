#!/usr/bin/env python3
"""
通知提醒系统 - 多渠道消息推送

功能：
- 邮件通知 (SMTP)
- Webhook 回调
- 桌面通知
- 通知模板管理
- 通知历史记录

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import smtplib
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import urllib.request
import urllib.parse

logger = logging.getLogger('notification-system')


@dataclass
class NotificationChannel:
    """通知渠道"""
    id: str
    name: str
    channel_type: str  # email/webhook/desktop
    config: Dict[str, Any]
    enabled: bool
    created_at: str


@dataclass
class NotificationTemplate:
    """通知模板"""
    id: str
    name: str
    subject_template: str
    body_template: str
    channel_type: str
    variables: List[str]


@dataclass
class NotificationRecord:
    """通知记录"""
    id: str
    channel_id: str
    template_id: str
    subject: str
    body: str
    recipients: List[str]
    status: str
    error_message: Optional[str]
    sent_at: str


class NotificationSystem:
    """通知系统"""

    DEFAULT_TEMPLATES = {
        'task_success': {
            'name': '任务成功通知',
            'subject': '✅ 任务执行成功 - {task_name}',
            'body': '''任务 "{task_name}" 已成功执行完成。

执行时间: {execution_time}
耗时: {duration}秒
输出摘要:
{output_summary}

---
本邮件由微信文章抓取助手自动发送''',
            'variables': ['task_name', 'execution_time', 'duration', 'output_summary']
        },
        'task_failure': {
            'name': '任务失败告警',
            'subject': '🔴 任务执行失败 - {task_name}',
            'body': '''任务 "{task_name}" 执行失败，请及时处理。

执行时间: {execution_time}
错误信息:
{error_message}

建议操作:
1. 检查任务配置是否正确
2. 查看完整日志了解详情
3. 手动重试运行

---
本邮件由微信文章抓取助手自动发送''',
            'variables': ['task_name', 'execution_time', 'error_message']
        },
        'scrape_complete': {
            'name': '采集完成通知',
            'subject': '📰 文章采集完成',
            'body': '''文章采集任务已完成。

采集数量: {article_count}
采集时间: {execution_time}
新增文章: {new_count}
更新文章: {updated_count}

---
本邮件由微信文章抓取助手自动发送''',
            'variables': ['article_count', 'execution_time', 'new_count', 'updated_count']
        },
        'daily_report': {
            'name': '每日数据报告',
            'subject': '📊 每日数据报告 - {date}',
            'body': '''{date} 数据概览:

📈 新增文章: {new_articles}
👁️ 总阅读量: {total_reads}
👍 总点赞数: {total_likes}
📊 平均互动率: {engagement_rate}%

热门文章:
{top_articles}

---
本邮件由微信文章抓取助手自动发送''',
            'variables': ['date', 'new_articles', 'total_reads', 'total_likes', 'engagement_rate', 'top_articles']
        },
        'crisis_alert': {
            'name': '危机预警通知',
            'subject': '🚨 舆情危机预警 - {alert_level}',
            'body': '''检测到 {alert_level} 级别舆情事件，请立即关注！

事件类型: {alert_type}
发现时间: {detected_time}
涉及内容: {content_summary}

建议措施:
{recommended_actions}

---
本邮件由微信文章抓取助手自动发送''',
            'variables': ['alert_level', 'alert_type', 'detected_time', 'content_summary', 'recommended_actions']
        }
    }

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "notifications.db")
        self.db_path = db_path
        self._init_db()
        self._ensure_default_templates()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)

        # 通知渠道表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_channels (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                config TEXT DEFAULT '{}',
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 通知模板表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                subject_template TEXT,
                body_template TEXT,
                channel_type TEXT,
                variables TEXT DEFAULT '[]'
            )
        """)

        # 通知记录表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_records (
                id TEXT PRIMARY KEY,
                channel_id TEXT,
                template_id TEXT,
                subject TEXT,
                body TEXT,
                recipients TEXT,
                status TEXT,
                error_message TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def _ensure_default_templates(self):
        """确保默认模板存在"""
        conn = sqlite3.connect(self.db_path)

        for template_id, template in self.DEFAULT_TEMPLATES.items():
            conn.execute("""
                INSERT OR IGNORE INTO notification_templates
                (id, name, subject_template, body_template, channel_type, variables)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                template_id,
                template['name'],
                template['subject'],
                template['body'],
                'email',
                json.dumps(template['variables'])
            ))

        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def add_email_channel(self, name: str, smtp_host: str, smtp_port: int,
                         username: str, password: str, use_tls: bool = True,
                         from_addr: str = None) -> NotificationChannel:
        """添加邮件渠道"""
        import hashlib
        channel_id = hashlib.md5(f"{name}{datetime.now()}".encode()).hexdigest()[:12]

        config = {
            'smtp_host': smtp_host,
            'smtp_port': smtp_port,
            'username': username,
            'password': password,
            'use_tls': use_tls,
            'from_addr': from_addr or username
        }

        conn = self._get_connection()
        conn.execute("""
            INSERT INTO notification_channels (id, name, channel_type, config, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (channel_id, name, 'email', json.dumps(config), 1, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        logger.info(f"邮件渠道已添加: {channel_id}")
        return NotificationChannel(
            id=channel_id,
            name=name,
            channel_type='email',
            config=config,
            enabled=True,
            created_at=datetime.now().isoformat()
        )

    def add_webhook_channel(self, name: str, webhook_url: str,
                           headers: Dict = None, method: str = 'POST') -> NotificationChannel:
        """添加Webhook渠道"""
        import hashlib
        channel_id = hashlib.md5(f"{name}{datetime.now()}".encode()).hexdigest()[:12]

        config = {
            'url': webhook_url,
            'headers': headers or {'Content-Type': 'application/json'},
            'method': method
        }

        conn = self._get_connection()
        conn.execute("""
            INSERT INTO notification_channels (id, name, channel_type, config, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (channel_id, name, 'webhook', json.dumps(config), 1, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        logger.info(f"Webhook渠道已添加: {channel_id}")
        return NotificationChannel(
            id=channel_id,
            name=name,
            channel_type='webhook',
            config=config,
            enabled=True,
            created_at=datetime.now().isoformat()
        )

    def list_channels(self) -> List[NotificationChannel]:
        """列出所有渠道"""
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM notification_channels ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()

        return [
            NotificationChannel(
                id=row['id'],
                name=row['name'],
                channel_type=row['channel_type'],
                config=json.loads(row['config']) if row['config'] else {},
                enabled=bool(row['enabled']),
                created_at=row['created_at']
            )
            for row in rows
        ]

    def get_template(self, template_id: str) -> Optional[NotificationTemplate]:
        """获取模板"""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM notification_templates WHERE id = ?",
            (template_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return NotificationTemplate(
                id=row['id'],
                name=row['name'],
                subject_template=row['subject_template'],
                body_template=row['body_template'],
                channel_type=row['channel_type'],
                variables=json.loads(row['variables']) if row['variables'] else []
            )
        return None

    def render_template(self, template_id: str, variables: Dict) -> tuple:
        """渲染模板"""
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"模板不存在: {template_id}")

        subject = template.subject_template
        body = template.body_template

        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            subject = subject.replace(placeholder, str(value))
            body = body.replace(placeholder, str(value))

        return subject, body

    def send_email(self, channel_id: str, to_addrs: List[str], subject: str, body: str) -> NotificationRecord:
        """发送邮件"""
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM notification_channels WHERE id = ?", (channel_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise ValueError(f"渠道不存在: {channel_id}")

        config = json.loads(row['config'])
        record_id = self._generate_id()

        try:
            msg = MIMEMultipart()
            msg['From'] = config['from_addr']
            msg['To'] = ', '.join(to_addrs)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            with smtplib.SMTP(config['smtp_host'], config['smtp_port']) as server:
                if config.get('use_tls', True):
                    server.starttls()
                server.login(config['username'], config['password'])
                server.send_message(msg)

            status = 'success'
            error_msg = None
            logger.info(f"邮件发送成功: {subject}")

        except Exception as e:
            status = 'failed'
            error_msg = str(e)
            logger.error(f"邮件发送失败: {e}")

        # 记录
        record = NotificationRecord(
            id=record_id,
            channel_id=channel_id,
            template_id='',
            subject=subject,
            body=body,
            recipients=to_addrs,
            status=status,
            error_message=error_msg,
            sent_at=datetime.now().isoformat()
        )

        self._save_record(record)
        return record

    def send_webhook(self, channel_id: str, payload: Dict) -> NotificationRecord:
        """发送Webhook"""
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM notification_channels WHERE id = ?", (channel_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise ValueError(f"渠道不存在: {channel_id}")

        config = json.loads(row['config'])
        record_id = self._generate_id()

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                config['url'],
                data=data,
                headers=config.get('headers', {}),
                method=config.get('method', 'POST')
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                response.read()

            status = 'success'
            error_msg = None
            logger.info(f"Webhook发送成功: {config['url']}")

        except Exception as e:
            status = 'failed'
            error_msg = str(e)
            logger.error(f"Webhook发送失败: {e}")

        record = NotificationRecord(
            id=record_id,
            channel_id=channel_id,
            template_id='',
            subject='Webhook',
            body=json.dumps(payload),
            recipients=[config['url']],
            status=status,
            error_message=error_msg,
            sent_at=datetime.now().isoformat()
        )

        self._save_record(record)
        return record

    def notify(self, template_id: str, channel_id: str, variables: Dict,
               recipients: List[str] = None) -> List[NotificationRecord]:
        """发送通知（使用模板）"""
        subject, body = self.render_template(template_id, variables)

        channel = self._get_channel(channel_id)
        if not channel:
            raise ValueError(f"渠道不存在: {channel_id}")

        records = []

        if channel.channel_type == 'email':
            if not recipients:
                raise ValueError("邮件通知需要指定收件人")
            record = self.send_email(channel_id, recipients, subject, body)
            records.append(record)

        elif channel.channel_type == 'webhook':
            payload = {
                'subject': subject,
                'body': body,
                'variables': variables,
                'timestamp': datetime.now().isoformat()
            }
            record = self.send_webhook(channel_id, payload)
            records.append(record)

        return records

    def _get_channel(self, channel_id: str) -> Optional[NotificationChannel]:
        """获取渠道"""
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM notification_channels WHERE id = ?", (channel_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return NotificationChannel(
                id=row['id'],
                name=row['name'],
                channel_type=row['channel_type'],
                config=json.loads(row['config']) if row['config'] else {},
                enabled=bool(row['enabled']),
                created_at=row['created_at']
            )
        return None

    def _save_record(self, record: NotificationRecord):
        """保存通知记录"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO notification_records
            (id, channel_id, template_id, subject, body, recipients, status, error_message, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.id, record.channel_id, record.template_id, record.subject,
            record.body, json.dumps(record.recipients), record.status,
            record.error_message, record.sent_at
        ))
        conn.commit()
        conn.close()

    def _generate_id(self) -> str:
        """生成ID"""
        import hashlib
        return hashlib.md5(f"{datetime.now()}".encode()).hexdigest()[:12]

    def get_notification_history(self, limit: int = 50) -> List[NotificationRecord]:
        """获取通知历史"""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM notification_records ORDER BY sent_at DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [
            NotificationRecord(
                id=row['id'],
                channel_id=row['channel_id'],
                template_id=row['template_id'],
                subject=row['subject'],
                body=row['body'],
                recipients=json.loads(row['recipients']) if row['recipients'] else [],
                status=row['status'],
                error_message=row['error_message'],
                sent_at=row['sent_at']
            )
            for row in rows
        ]


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='通知系统')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 添加邮件渠道
    email_parser = subparsers.add_parser('add-email', help='添加邮件渠道')
    email_parser.add_argument('name', help='渠道名称')
    email_parser.add_argument('--host', required=True, help='SMTP服务器')
    email_parser.add_argument('--port', type=int, default=587, help='SMTP端口')
    email_parser.add_argument('--user', required=True, help='用户名')
    email_parser.add_argument('--pass', required=True, dest='password', help='密码')
    email_parser.add_argument('--from', dest='from_addr', help='发件地址')

    # 添加Webhook渠道
    webhook_parser = subparsers.add_parser('add-webhook', help='添加Webhook渠道')
    webhook_parser.add_argument('name', help='渠道名称')
    webhook_parser.add_argument('--url', required=True, help='Webhook URL')

    # 列出渠道
    subparsers.add_parser('list-channels', help='列出渠道')

    # 发送测试邮件
    test_parser = subparsers.add_parser('test', help='发送测试通知')
    test_parser.add_argument('channel_id', help='渠道ID')
    test_parser.add_argument('--to', required=True, help='收件人')
    test_parser.add_argument('--template', default='task_success', help='模板ID')

    # 通知历史
    subparsers.add_parser('history', help='通知历史')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    notifier = NotificationSystem()

    if args.command == 'add-email':
        channel = notifier.add_email_channel(
            name=args.name,
            smtp_host=args.host,
            smtp_port=args.port,
            username=args.user,
            password=args.password,
            from_addr=args.from_addr
        )
        print(f"邮件渠道已添加: {channel.id}")

    elif args.command == 'add-webhook':
        channel = notifier.add_webhook_channel(
            name=args.name,
            webhook_url=args.url
        )
        print(f"Webhook渠道已添加: {channel.id}")

    elif args.command == 'list-channels':
        channels = notifier.list_channels()
        print(f"\n通知渠道 ({len(channels)}个):\n")
        for c in channels:
            status = "✅" if c.enabled else "🚫"
            print(f"{status} [{c.id}] {c.name} ({c.channel_type})")
            if c.channel_type == 'email':
                print(f"   SMTP: {c.config.get('smtp_host')}")
            elif c.channel_type == 'webhook':
                print(f"   URL: {c.config.get('url')}")

    elif args.command == 'test':
        try:
            variables = {
                'task_name': '测试任务',
                'execution_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'duration': 5.2,
                'output_summary': '这是测试输出摘要'
            }
            records = notifier.notify(
                template_id=args.template,
                channel_id=args.channel_id,
                variables=variables,
                recipients=[args.to]
            )
            for r in records:
                print(f"发送状态: {r.status}")
                if r.error_message:
                    print(f"错误: {r.error_message}")
        except Exception as e:
            print(f"发送失败: {e}")

    elif args.command == 'history':
        history = notifier.get_notification_history(20)
        print(f"\n通知历史 ({len(history)}条):\n")
        for h in history:
            icon = "✅" if h.status == 'success' else "❌"
            print(f"{icon} [{h.sent_at[:19]}] {h.subject[:50]}...")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
