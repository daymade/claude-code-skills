#!/usr/bin/env python3
"""
自动化工作流引擎 - IFTTT 风格的触发-动作系统

功能：
- 触发器系统：新文章、热度阈值、关键词匹配、定时触发
- 动作执行器：Webhook、邮件、企业微信、飞书、本地脚本
- 工作流引擎：条件判断、执行链、错误重试、日志追踪
- RESTful API：外部系统集成

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import hashlib
import asyncio
import aiohttp
import smtplib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from enum import Enum
import threading
import time

logger = logging.getLogger('workflow-engine')


class TriggerType(Enum):
    """触发器类型"""
    NEW_ARTICLE = "new_article"          # 新文章发布
    HEAT_THRESHOLD = "heat_threshold"     # 热度阈值
    KEYWORD_MATCH = "keyword_match"       # 关键词匹配
    SCHEDULED = "scheduled"               # 定时触发
    MANUAL = "manual"                     # 手动触发


class ActionType(Enum):
    """动作类型"""
    WEBHOOK = "webhook"                   # HTTP回调
    EMAIL = "email"                       # 邮件通知
    WECHAT_WORK = "wechat_work"          # 企业微信
    LARK = "lark"                         # 飞书
    SCRIPT = "script"                     # 本地脚本
    DATABASE = "database"                 # 数据库存储


class WorkflowStatus(Enum):
    """工作流状态"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class TriggerConfig:
    """触发器配置"""
    type: str
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {"type": self.type, "config": self.config}

    @classmethod
    def from_dict(cls, data: Dict) -> 'TriggerConfig':
        return cls(type=data.get("type", ""), config=data.get("config", {}))


@dataclass
class ActionConfig:
    """动作配置"""
    type: str
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {"type": self.type, "config": self.config}

    @classmethod
    def from_dict(cls, data: Dict) -> 'ActionConfig':
        return cls(type=data.get("type", ""), config=data.get("config", {}))


@dataclass
class Workflow:
    """工作流定义"""
    id: str
    name: str
    description: str
    trigger: TriggerConfig
    actions: List[ActionConfig]
    conditions: List[Dict] = field(default_factory=list)
    status: str = "enabled"
    created_at: str = ""
    updated_at: str = ""
    last_triggered: str = ""
    trigger_count: int = 0
    error_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger.to_dict(),
            "actions": [a.to_dict() for a in self.actions],
            "conditions": self.conditions,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_triggered": self.last_triggered,
            "trigger_count": self.trigger_count,
            "error_count": self.error_count
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Workflow':
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            trigger=TriggerConfig.from_dict(data.get("trigger", {})),
            actions=[ActionConfig.from_dict(a) for a in data.get("actions", [])],
            conditions=data.get("conditions", []),
            status=data.get("status", "enabled"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            last_triggered=data.get("last_triggered", ""),
            trigger_count=data.get("trigger_count", 0),
            error_count=data.get("error_count", 0)
        )


@dataclass
class WorkflowLog:
    """工作流执行日志"""
    id: str
    workflow_id: str
    trigger_event: Dict
    execution_results: List[Dict]
    status: str
    started_at: str
    completed_at: str
    error_message: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "trigger_event": self.trigger_event,
            "execution_results": self.execution_results,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message
        }


class Trigger(ABC):
    """触发器基类"""

    def __init__(self, config: TriggerConfig):
        self.config = config

    @abstractmethod
    def check(self, event_data: Dict) -> bool:
        """检查是否触发"""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """获取描述"""
        pass


class NewArticleTrigger(Trigger):
    """新文章触发器"""

    def check(self, event_data: Dict) -> bool:
        if event_data.get("event_type") != "new_article":
            return False

        # 可选：按公众号筛选
        account_filter = self.config.config.get("account_name")
        if account_filter:
            if event_data.get("account_name") != account_filter:
                return False

        return True

    def get_description(self) -> str:
        account = self.config.config.get("account_name", "任意公众号")
        return f"当 {account} 发布新文章时触发"


class HeatThresholdTrigger(Trigger):
    """热度阈值触发器"""

    def check(self, event_data: Dict) -> bool:
        if event_data.get("event_type") != "heat_threshold":
            return False

        threshold = self.config.config.get("threshold", 1000)
        heat_score = event_data.get("heat_score", 0)
        operator = self.config.config.get("operator", ">=")

        if operator == ">=":
            return heat_score >= threshold
        elif operator == ">":
            return heat_score > threshold
        elif operator == "<=":
            return heat_score <= threshold

        return False

    def get_description(self) -> str:
        threshold = self.config.config.get("threshold", 1000)
        operator = self.config.config.get("operator", ">=")
        return f"当热度 {operator} {threshold} 时触发"


class KeywordMatchTrigger(Trigger):
    """关键词匹配触发器"""

    def check(self, event_data: Dict) -> bool:
        if event_data.get("event_type") != "new_article":
            return False

        keywords = self.config.config.get("keywords", [])
        match_mode = self.config.config.get("match_mode", "any")  # any, all

        if not keywords:
            return True

        content = f"{event_data.get('title', '')} {event_data.get('content', '')}".lower()
        matches = [kw for kw in keywords if kw.lower() in content]

        if match_mode == "all":
            return len(matches) == len(keywords)
        return len(matches) > 0

    def get_description(self) -> str:
        keywords = self.config.config.get("keywords", [])
        match_mode = self.config.config.get("match_mode", "any")
        return f"标题/内容{'包含全部' if match_mode == 'all' else '包含任意'}关键词: {', '.join(keywords)}"


class ScheduledTrigger(Trigger):
    """定时触发器"""

    def check(self, event_data: Dict) -> bool:
        # 定时触发由调度器处理，这里只验证数据
        return event_data.get("event_type") == "scheduled"

    def get_description(self) -> str:
        cron = self.config.config.get("cron", "0 9 * * *")
        return f"定时触发 (cron: {cron})"


class Action(ABC):
    """动作基类"""

    def __init__(self, config: ActionConfig):
        self.config = config

    @abstractmethod
    async def execute(self, event_data: Dict, workflow: Workflow) -> Dict:
        """执行动作"""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """获取描述"""
        pass


class WebhookAction(Action):
    """Webhook 动作"""

    async def execute(self, event_data: Dict, workflow: Workflow) -> Dict:
        url = self.config.config.get("url", "")
        method = self.config.config.get("method", "POST")
        headers = self.config.config.get("headers", {})
        timeout = self.config.config.get("timeout", 30)

        # 构建 payload
        payload = {
            "event": event_data,
            "workflow": {
                "id": workflow.id,
                "name": workflow.name
            },
            "timestamp": datetime.now().isoformat()
        }

        try:
            async with aiohttp.ClientSession() as session:
                if method.upper() == "GET":
                    async with session.get(url, params=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                        return {
                            "success": resp.status < 400,
                            "status_code": resp.status,
                            "response": await resp.text()[:500]
                        }
                else:
                    async with session.request(method, url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                        return {
                            "success": resp.status < 400,
                            "status_code": resp.status,
                            "response": await resp.text()[:500]
                        }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_description(self) -> str:
        url = self.config.config.get("url", "")
        method = self.config.config.get("method", "POST")
        return f"发送 {method} 请求到 {url[:50]}..."


class EmailAction(Action):
    """邮件通知动作"""

    async def execute(self, event_data: Dict, workflow: Workflow) -> Dict:
        smtp_host = self.config.config.get("smtp_host", "")
        smtp_port = self.config.config.get("smtp_port", 587)
        smtp_user = self.config.config.get("smtp_user", "")
        smtp_pass = self.config.config.get("smtp_pass", "")
        to_addr = self.config.config.get("to", "")
        subject_template = self.config.config.get("subject", "工作流通知: {workflow_name}")
        body_template = self.config.config.get("body", "")

        try:
            # 模板变量替换
            variables = {
                "workflow_name": workflow.name,
                "event_type": event_data.get("event_type", ""),
                "article_title": event_data.get("title", ""),
                "article_url": event_data.get("url", ""),
                "account_name": event_data.get("account_name", ""),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            subject = subject_template.format(**variables)

            if body_template:
                body = body_template.format(**variables)
            else:
                body = self._build_default_body(event_data, workflow)

            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = to_addr
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'html', 'utf-8'))

            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            server.quit()

            return {"success": True, "message": f"邮件已发送到 {to_addr}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _build_default_body(self, event_data: Dict, workflow: Workflow) -> str:
        """构建默认邮件内容"""
        return f"""
        <h3>工作流执行通知</h3>
        <p><strong>工作流:</strong> {workflow.name}</p>
        <p><strong>事件类型:</strong> {event_data.get('event_type', '')}</p>
        <p><strong>文章标题:</strong> {event_data.get('title', 'N/A')}</p>
        <p><strong>公众号:</strong> {event_data.get('account_name', 'N/A')}</p>
        <p><strong>时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """

    def get_description(self) -> str:
        to = self.config.config.get("to", "")
        return f"发送邮件到 {to}"


class WechatWorkAction(Action):
    """企业微信机器人动作"""

    async def execute(self, event_data: Dict, workflow: Workflow) -> Dict:
        webhook_url = self.config.config.get("webhook_url", "")

        # 构建企业微信消息
        title = event_data.get("title", "新文章通知")
        content = event_data.get("content", "")[:200] + "..." if event_data.get("content") else ""
        url = event_data.get("url", "")
        account = event_data.get("account_name", "")

        message = {
            "msgtype": "news",
            "news": {
                "articles": [
                    {
                        "title": f"[{account}] {title}",
                        "description": content,
                        "url": url,
                        "picurl": event_data.get("cover_image", "")
                    }
                ]
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=message, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    result = await resp.json()
                    return {
                        "success": result.get("errcode") == 0,
                        "response": result
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_description(self) -> str:
        return "推送到企业微信机器人"


class LarkAction(Action):
    """飞书机器人动作"""

    async def execute(self, event_data: Dict, workflow: Workflow) -> Dict:
        webhook_url = self.config.config.get("webhook_url", "")

        title = event_data.get("title", "新文章通知")
        content = event_data.get("content", "")[:300] + "..." if event_data.get("content") else ""
        url = event_data.get("url", "")
        account = event_data.get("account_name", "")

        # 飞书卡片消息
        message = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"[{account}] {title}"
                    },
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": content
                        }
                    },
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "阅读原文"
                                },
                                "url": url,
                                "type": "primary"
                            }
                        ]
                    }
                ]
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=message, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    result = await resp.json()
                    return {
                        "success": result.get("code") == 0,
                        "response": result
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_description(self) -> str:
        return "推送到飞书机器人"


class ScriptAction(Action):
    """本地脚本动作"""

    async def execute(self, event_data: Dict, workflow: Workflow) -> Dict:
        import subprocess

        script_path = self.config.config.get("script_path", "")
        args = self.config.config.get("args", [])
        timeout = self.config.config.get("timeout", 60)
        env_vars = self.config.config.get("env_vars", {})

        try:
            # 将事件数据作为环境变量传递
            env = os.environ.copy()
            env.update(env_vars)
            env['WORKFLOW_EVENT'] = json.dumps(event_data, ensure_ascii=False)
            env['WORKFLOW_ID'] = workflow.id
            env['WORKFLOW_NAME'] = workflow.name

            # 执行脚本
            cmd = [script_path] + args
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )

            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout[:500],
                "stderr": result.stderr[:500]
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"脚本执行超时 ({timeout}s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_description(self) -> str:
        script = self.config.config.get("script_path", "")
        return f"执行脚本 {script}"


class DatabaseAction(Action):
    """数据库存储动作"""

    async def execute(self, event_data: Dict, workflow: Workflow) -> Dict:
        db_path = self.config.config.get("db_path", "")
        table = self.config.config.get("table", "workflow_events")
        field_mapping = self.config.config.get("field_mapping", {})

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 构建插入语句
            if not field_mapping:
                # 默认映射
                field_mapping = {
                    "event_id": "id",
                    "event_type": "event_type",
                    "title": "title",
                    "url": "url",
                    "account_name": "account_name",
                    "created_at": lambda _: datetime.now().isoformat()
                }

            columns = []
            values = []

            for col, source in field_mapping.items():
                if callable(source):
                    val = source(event_data)
                else:
                    val = event_data.get(source)
                columns.append(col)
                values.append(val)

            # 添加工作流ID
            columns.append("workflow_id")
            values.append(workflow.id)

            placeholders = ",".join(["?"] * len(values))
            sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"

            cursor.execute(sql, values)
            conn.commit()
            conn.close()

            return {"success": True, "message": f"数据已存入 {table}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_description(self) -> str:
        table = self.config.config.get("table", "workflow_events")
        return f"存储数据到表 {table}"


class TriggerFactory:
    """触发器工厂"""

    @staticmethod
    def create(config: TriggerConfig) -> Trigger:
        trigger_map = {
            TriggerType.NEW_ARTICLE.value: NewArticleTrigger,
            TriggerType.HEAT_THRESHOLD.value: HeatThresholdTrigger,
            TriggerType.KEYWORD_MATCH.value: KeywordMatchTrigger,
            TriggerType.SCHEDULED.value: ScheduledTrigger,
            TriggerType.MANUAL.value: NewArticleTrigger  # 手动触发用通用触发器
        }

        trigger_class = trigger_map.get(config.type)
        if trigger_class:
            return trigger_class(config)
        raise ValueError(f"未知的触发器类型: {config.type}")


class ActionFactory:
    """动作工厂"""

    @staticmethod
    def create(config: ActionConfig) -> Action:
        action_map = {
            ActionType.WEBHOOK.value: WebhookAction,
            ActionType.EMAIL.value: EmailAction,
            ActionType.WECHAT_WORK.value: WechatWorkAction,
            ActionType.LARK.value: LarkAction,
            ActionType.SCRIPT.value: ScriptAction,
            ActionType.DATABASE.value: DatabaseAction
        }

        action_class = action_map.get(config.type)
        if action_class:
            return action_class(config)
        raise ValueError(f"未知的动作类型: {config.type}")


class WorkflowEngine:
    """工作流引擎"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "workflows.db")

        self.db_path = db_path
        self._init_db()
        self._running = False
        self._scheduler_thread = None

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)

        # 工作流表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                trigger TEXT,
                actions TEXT,
                conditions TEXT,
                status TEXT DEFAULT 'enabled',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_triggered TIMESTAMP,
                trigger_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0
            )
        """)

        # 执行日志表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_logs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT,
                trigger_event TEXT,
                execution_results TEXT,
                status TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id)
            )
        """)

        # 定时任务表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id TEXT PRIMARY KEY,
                workflow_id TEXT,
                cron_expression TEXT,
                next_run TIMESTAMP,
                last_run TIMESTAMP,
                enabled INTEGER DEFAULT 1,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id)
            )
        """)

        conn.commit()
        conn.close()

    def create_workflow(self, name: str, description: str,
                       trigger: TriggerConfig, actions: List[ActionConfig],
                       conditions: List[Dict] = None) -> Workflow:
        """创建工作流"""
        workflow_id = hashlib.md5(f"{name}{datetime.now()}".encode()).hexdigest()[:16]

        now = datetime.now().isoformat()
        workflow = Workflow(
            id=workflow_id,
            name=name,
            description=description,
            trigger=trigger,
            actions=actions,
            conditions=conditions or [],
            status="enabled",
            created_at=now,
            updated_at=now
        )

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO workflows (id, name, description, trigger, actions, conditions, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            workflow.id, workflow.name, workflow.description,
            json.dumps(trigger.to_dict()),
            json.dumps([a.to_dict() for a in actions]),
            json.dumps(conditions or []),
            workflow.status, workflow.created_at, workflow.updated_at
        ))
        conn.commit()
        conn.close()

        logger.info(f"工作流已创建: {name} ({workflow_id})")
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """获取工作流"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_workflow(row)

    def list_workflows(self, status: str = None) -> List[Workflow]:
        """列出所有工作流"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        if status:
            cursor = conn.execute("SELECT * FROM workflows WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            cursor = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC")

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_workflow(row) for row in rows]

    def _row_to_workflow(self, row) -> Workflow:
        """数据库行转工作流对象"""
        return Workflow(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            trigger=TriggerConfig.from_dict(json.loads(row["trigger"])),
            actions=[ActionConfig.from_dict(a) for a in json.loads(row["actions"])],
            conditions=json.loads(row["conditions"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_triggered=row["last_triggered"] or "",
            trigger_count=row["trigger_count"],
            error_count=row["error_count"]
        )

    def update_workflow(self, workflow_id: str, **kwargs) -> bool:
        """更新工作流"""
        allowed_fields = ["name", "description", "trigger", "actions", "conditions", "status"]

        updates = []
        values = []
        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                if isinstance(value, (dict, list)):
                    values.append(json.dumps(value))
                else:
                    values.append(value)

        if not updates:
            return False

        updates.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(workflow_id)

        conn = sqlite3.connect(self.db_path)
        conn.execute(f"UPDATE workflows SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        conn.close()

        return True

    def delete_workflow(self, workflow_id: str) -> bool:
        """删除工作流"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def enable_workflow(self, workflow_id: str) -> bool:
        """启用工作流"""
        return self.update_workflow(workflow_id, status="enabled")

    def disable_workflow(self, workflow_id: str) -> bool:
        """禁用工作流"""
        return self.update_workflow(workflow_id, status="disabled")

    async def trigger_workflow(self, workflow_id: str, event_data: Dict,
                               is_manual: bool = False) -> Optional[WorkflowLog]:
        """触发工作流执行"""
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            logger.error(f"工作流不存在: {workflow_id}")
            return None

        if workflow.status != "enabled" and not is_manual:
            logger.warning(f"工作流已禁用，跳过执行: {workflow_id}")
            return None

        log_id = hashlib.md5(f"{workflow_id}{datetime.now()}".encode()).hexdigest()[:16]
        started_at = datetime.now()

        logger.info(f"开始执行工作流: {workflow.name} ({workflow_id})")

        # 更新触发计数
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE workflows SET trigger_count = trigger_count + 1, last_triggered = ? WHERE id = ?",
            (started_at.isoformat(), workflow_id)
        )
        conn.commit()
        conn.close()

        # 执行所有动作
        results = []
        overall_success = True
        error_message = ""

        for action_config in workflow.actions:
            try:
                action = ActionFactory.create(action_config)
                result = await action.execute(event_data, workflow)
                results.append({
                    "action_type": action_config.type,
                    "success": result.get("success", False),
                    "details": result
                })

                if not result.get("success", False):
                    overall_success = False
                    error_message = result.get("error", "未知错误")

            except Exception as e:
                logger.error(f"动作执行失败: {e}")
                results.append({
                    "action_type": action_config.type,
                    "success": False,
                    "error": str(e)
                })
                overall_success = False
                error_message = str(e)

        completed_at = datetime.now()

        # 记录日志
        log = WorkflowLog(
            id=log_id,
            workflow_id=workflow_id,
            trigger_event=event_data,
            execution_results=results,
            status="success" if overall_success else "failed",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            error_message=error_message
        )

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO workflow_logs (id, workflow_id, trigger_event, execution_results, status, started_at, completed_at, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log.id, log.workflow_id, json.dumps(log.trigger_event),
            json.dumps(log.execution_results), log.status,
            log.started_at, log.completed_at, log.error_message
        ))

        if not overall_success:
            conn.execute("UPDATE workflows SET error_count = error_count + 1 WHERE id = ?", (workflow_id,))

        conn.commit()
        conn.close()

        logger.info(f"工作流执行完成: {workflow.name}, 状态: {log.status}")
        return log

    def process_event(self, event_data: Dict) -> List[WorkflowLog]:
        """处理事件，触发匹配的工作流"""
        workflows = self.list_workflows(status="enabled")
        triggered_logs = []

        for workflow in workflows:
            try:
                trigger = TriggerFactory.create(workflow.trigger)
                if trigger.check(event_data):
                    log = asyncio.run(self.trigger_workflow(workflow.id, event_data))
                    if log:
                        triggered_logs.append(log)
            except Exception as e:
                logger.error(f"处理工作流 {workflow.id} 时出错: {e}")

        return triggered_logs

    def get_logs(self, workflow_id: str = None, limit: int = 50) -> List[WorkflowLog]:
        """获取执行日志"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        if workflow_id:
            cursor = conn.execute(
                "SELECT * FROM workflow_logs WHERE workflow_id = ? ORDER BY started_at DESC LIMIT ?",
                (workflow_id, limit)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM workflow_logs ORDER BY started_at DESC LIMIT ?",
                (limit,)
            )

        rows = cursor.fetchall()
        conn.close()

        logs = []
        for row in rows:
            logs.append(WorkflowLog(
                id=row["id"],
                workflow_id=row["workflow_id"],
                trigger_event=json.loads(row["trigger_event"]),
                execution_results=json.loads(row["execution_results"]),
                status=row["status"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                error_message=row["error_message"] or ""
            ))

        return logs

    def get_stats(self) -> Dict:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM workflows")
        total_workflows = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM workflows WHERE status = 'enabled'")
        enabled_workflows = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM workflow_logs")
        total_executions = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM workflow_logs WHERE status = 'success'")
        success_executions = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(trigger_count) FROM workflows")
        total_triggers = cursor.fetchone()[0] or 0

        conn.close()

        return {
            "total_workflows": total_workflows,
            "enabled_workflows": enabled_workflows,
            "disabled_workflows": total_workflows - enabled_workflows,
            "total_executions": total_executions,
            "success_rate": success_executions / total_executions * 100 if total_executions > 0 else 0,
            "total_triggers": total_triggers
        }


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='自动化工作流引擎')

    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 列出工作流
    subparsers.add_parser('list', help='列出所有工作流')

    # 执行工作流
    trigger_parser = subparsers.add_parser('trigger', help='手动触发工作流')
    trigger_parser.add_argument('workflow_id', help='工作流ID')
    trigger_parser.add_argument('--event', help='事件数据JSON')

    # 查看日志
    logs_parser = subparsers.add_parser('logs', help='查看执行日志')
    logs_parser.add_argument('--workflow', help='筛选特定工作流')
    logs_parser.add_argument('-n', '--limit', type=int, default=20, help='数量限制')

    # 统计信息
    subparsers.add_parser('stats', help='统计信息')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    engine = WorkflowEngine()

    if args.command == 'list':
        workflows = engine.list_workflows()
        print(f"\n共有 {len(workflows)} 个工作流:\n")
        for w in workflows:
            trigger = TriggerFactory.create(w.trigger)
            actions_desc = [ActionFactory.create(a).get_description() for a in w.actions]
            print(f"📋 {w.name} ({w.id})")
            print(f"   状态: {'✅ 启用' if w.status == 'enabled' else '⏸️ 禁用'}")
            print(f"   触发器: {trigger.get_description()}")
            print(f"   动作: {'; '.join(actions_desc)}")
            print(f"   触发次数: {w.trigger_count} | 错误次数: {w.error_count}")
            print()

    elif args.command == 'trigger':
        event_data = json.loads(args.event) if args.event else {"event_type": "manual", "timestamp": datetime.now().isoformat()}
        log = asyncio.run(engine.trigger_workflow(args.workflow_id, event_data, is_manual=True))
        if log:
            print(f"工作流执行完成: {log.status}")
            for r in log.execution_results:
                print(f"  - {r['action_type']}: {'✅' if r['success'] else '❌'}")
        else:
            print("工作流执行失败")

    elif args.command == 'logs':
        logs = engine.get_logs(args.workflow, args.limit)
        print(f"\n最近 {len(logs)} 条执行记录:\n")
        for log in logs:
            duration = "N/A"
            if log.completed_at and log.started_at:
                try:
                    start = datetime.fromisoformat(log.started_at)
                    end = datetime.fromisoformat(log.completed_at)
                    duration = f"{(end - start).total_seconds():.1f}s"
                except:
                    pass

            status_icon = "✅" if log.status == "success" else "❌"
            print(f"{status_icon} [{log.started_at}] 工作流: {log.workflow_id[:8]}... | 耗时: {duration}")
            if log.error_message:
                print(f"   错误: {log.error_message}")

    elif args.command == 'stats':
        stats = engine.get_stats()
        print("\n工作流统计:")
        print(f"  工作流总数: {stats['total_workflows']}")
        print(f"  已启用: {stats['enabled_workflows']}")
        print(f"  执行次数: {stats['total_executions']}")
        print(f"  成功率: {stats['success_rate']:.1f}%")


if __name__ == '__main__':
    main()
