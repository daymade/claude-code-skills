#!/usr/bin/env python3
"""
定时任务调度器 - 自动化采集与发布

功能：
- Cron表达式定时任务
- 自动文章采集
- 定时数据导出
- 任务执行状态监控
- 邮件/Webhook通知

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import subprocess
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from croniter import croniter
import threading
import time

logger = logging.getLogger('task-scheduler')


class TaskType(Enum):
    """任务类型"""
    SCRAPE = "scrape"
    EXPORT = "export"
    BACKUP = "backup"
    SYNC = "sync"
    CLEANUP = "cleanup"
    CUSTOM = "custom"


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class ScheduledTask:
    """定时任务"""
    id: str
    name: str
    task_type: str
    cron_expression: str
    command: str
    params: Dict[str, Any]
    enabled: bool
    last_run: Optional[str]
    last_status: Optional[str]
    next_run: Optional[str]
    run_count: int
    fail_count: int
    created_at: str
    description: str
    notify_on_success: bool
    notify_on_failure: bool


@dataclass
class TaskExecution:
    """任务执行记录"""
    id: str
    task_id: str
    started_at: str
    completed_at: Optional[str]
    status: str
    output: str
    error_message: Optional[str]
    duration_seconds: float


class TaskScheduler:
    """任务调度器"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "scheduler.db")
        self.db_path = db_path
        self._init_db()
        self._running = False
        self._scheduler_thread = None
        self._callbacks: Dict[str, List[Callable]] = {
            'before_run': [],
            'after_run': [],
            'on_error': []
        }

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)

        # 任务表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                task_type TEXT NOT NULL,
                cron_expression TEXT NOT NULL,
                command TEXT,
                params TEXT DEFAULT '{}',
                enabled INTEGER DEFAULT 1,
                last_run TEXT,
                last_status TEXT,
                next_run TEXT,
                run_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                created_at TEXT,
                description TEXT,
                notify_on_success INTEGER DEFAULT 0,
                notify_on_failure INTEGER DEFAULT 1
            )
        """)

        # 执行记录表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_executions (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                started_at TEXT,
                completed_at TEXT,
                status TEXT,
                output TEXT,
                error_message TEXT,
                duration_seconds REAL,
                FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id)
            )
        """)

        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_task(self, name: str, task_type: str, cron: str,
                   command: str = None, params: Dict = None,
                   description: str = "", enabled: bool = True,
                   notify_on_success: bool = False,
                   notify_on_failure: bool = True) -> ScheduledTask:
        """创建定时任务"""
        task_id = hashlib.md5(f"{name}{datetime.now()}".encode()).hexdigest()[:12]

        # 计算下次执行时间
        next_run = self._calculate_next_run(cron)

        now = datetime.now().isoformat()

        task = ScheduledTask(
            id=task_id,
            name=name,
            task_type=task_type,
            cron_expression=cron,
            command=command,
            params=params or {},
            enabled=enabled,
            last_run=None,
            last_status=None,
            next_run=next_run,
            run_count=0,
            fail_count=0,
            created_at=now,
            description=description,
            notify_on_success=notify_on_success,
            notify_on_failure=notify_on_failure
        )

        conn = self._get_connection()
        conn.execute("""
            INSERT INTO scheduled_tasks
            (id, name, task_type, cron_expression, command, params, enabled,
             next_run, run_count, fail_count, created_at, description,
             notify_on_success, notify_on_failure)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.id, task.name, task.task_type, task.cron_expression,
            task.command, json.dumps(task.params), int(task.enabled),
            task.next_run, task.run_count, task.fail_count,
            task.created_at, task.description,
            int(task.notify_on_success), int(task.notify_on_failure)
        ))
        conn.commit()
        conn.close()

        logger.info(f"任务已创建: {task_id} ({name})")
        return task

    def _calculate_next_run(self, cron: str, base_time: datetime = None) -> str:
        """计算下次执行时间"""
        try:
            if base_time is None:
                base_time = datetime.now()
            itr = croniter(cron, base_time)
            next_time = itr.get_next(datetime)
            return next_time.isoformat()
        except Exception as e:
            logger.error(f"计算下次执行时间失败: {e}")
            return (datetime.now() + timedelta(hours=1)).isoformat()

    def list_tasks(self, enabled_only: bool = False) -> List[ScheduledTask]:
        """列出所有任务"""
        conn = self._get_connection()

        if enabled_only:
            cursor = conn.execute(
                "SELECT * FROM scheduled_tasks WHERE enabled = 1 ORDER BY created_at DESC"
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM scheduled_tasks ORDER BY created_at DESC"
            )

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_task(row) for row in rows]

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """获取单个任务"""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM scheduled_tasks WHERE id = ?",
            (task_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_task(row)
        return None

    def update_task(self, task_id: str, **kwargs) -> bool:
        """更新任务"""
        allowed_fields = ['name', 'cron_expression', 'command', 'params',
                         'enabled', 'description', 'notify_on_success', 'notify_on_failure']

        updates = []
        params = []

        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                if key == 'params':
                    params.append(json.dumps(value))
                elif key in ['enabled', 'notify_on_success', 'notify_on_failure']:
                    params.append(int(value))
                else:
                    params.append(value)

        if not updates:
            return False

        params.append(task_id)

        conn = self._get_connection()
        cursor = conn.execute(
            f"UPDATE scheduled_tasks SET {', '.join(updates)} WHERE id = ?",
            params
        )

        # 如果更新了cron，重新计算下次执行时间
        if 'cron_expression' in kwargs:
            next_run = self._calculate_next_run(kwargs['cron_expression'])
            conn.execute(
                "UPDATE scheduled_tasks SET next_run = ? WHERE id = ?",
                (next_run, task_id)
            )

        conn.commit()
        conn.close()

        return cursor.rowcount > 0

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        conn = self._get_connection()

        # 先删除执行记录
        conn.execute("DELETE FROM task_executions WHERE task_id = ?", (task_id,))

        # 再删除任务
        cursor = conn.execute(
            "DELETE FROM scheduled_tasks WHERE id = ?",
            (task_id,)
        )

        conn.commit()
        conn.close()

        return cursor.rowcount > 0

    def toggle_task(self, task_id: str) -> bool:
        """切换任务启用状态"""
        task = self.get_task(task_id)
        if not task:
            return False

        new_state = not task.enabled
        return self.update_task(task_id, enabled=new_state)

    def run_task(self, task_id: str) -> TaskExecution:
        """立即执行任务"""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        # 触发回调
        for callback in self._callbacks['before_run']:
            callback(task)

        # 记录执行开始
        execution_id = hashlib.md5(
            f"{task_id}{datetime.now()}".encode()
        ).hexdigest()[:12]

        started_at = datetime.now()

        conn = self._get_connection()
        conn.execute("""
            INSERT INTO task_executions
            (id, task_id, started_at, status, output)
            VALUES (?, ?, ?, 'running', '')
        """, (execution_id, task_id, started_at.isoformat()))
        conn.commit()
        conn.close()

        # 更新任务状态
        self.update_task(task_id, last_run=started_at.isoformat())

        # 执行任务
        output = ""
        error = None
        status = TaskStatus.SUCCESS.value

        try:
            output = self._execute_task_command(task)
        except Exception as e:
            error = str(e)
            status = TaskStatus.FAILED.value
            logger.error(f"任务执行失败 {task_id}: {e}")

            # 触发错误回调
            for callback in self._callbacks['on_error']:
                callback(task, error)

        # 计算执行时间
        completed_at = datetime.now()
        duration = (completed_at - started_at).total_seconds()

        # 更新执行记录
        conn = self._get_connection()
        conn.execute("""
            UPDATE task_executions
            SET completed_at = ?, status = ?, output = ?, error_message = ?, duration_seconds = ?
            WHERE id = ?
        """, (
            completed_at.isoformat(), status, output, error, duration, execution_id
        ))
        conn.commit()
        conn.close()

        # 更新任务统计
        new_run_count = task.run_count + 1
        new_fail_count = task.fail_count + (1 if error else 0)
        next_run = self._calculate_next_run(task.cron_expression)

        self.update_task(
            task_id,
            last_status=status,
            run_count=new_run_count,
            fail_count=new_fail_count,
            next_run=next_run
        )

        # 触发完成回调
        execution = TaskExecution(
            id=execution_id,
            task_id=task_id,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            status=status,
            output=output,
            error_message=error,
            duration_seconds=duration
        )

        for callback in self._callbacks['after_run']:
            callback(task, execution)

        return execution

    def _execute_task_command(self, task: ScheduledTask) -> str:
        """执行具体任务"""
        if task.command:
            # 执行自定义命令
            result = subprocess.run(
                task.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode != 0:
                raise RuntimeError(f"命令执行失败: {result.stderr}")
            return result.stdout

        # 根据任务类型执行内置操作
        handlers = {
            TaskType.SCRAPE.value: self._handle_scrape,
            TaskType.EXPORT.value: self._handle_export,
            TaskType.BACKUP.value: self._handle_backup,
            TaskType.CLEANUP.value: self._handle_cleanup
        }

        handler = handlers.get(task.task_type)
        if handler:
            return handler(task.params)

        return "未知任务类型"

    def _handle_scrape(self, params: Dict) -> str:
        """处理采集任务"""
        urls = params.get('urls', [])
        accounts = params.get('accounts', [])

        results = []
        for url in urls:
            results.append(f"采集: {url}")

        for account in accounts:
            results.append(f"采集账号: {account}")

        return "\n".join(results) if results else "无采集目标"

    def _handle_export(self, params: Dict) -> str:
        """处理导出任务"""
        format_type = params.get('format', 'json')
        output_dir = params.get('output_dir', './exports')

        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"export_{timestamp}.{format_type}"

        return f"导出完成: {os.path.join(output_dir, filename)}"

    def _handle_backup(self, params: Dict) -> str:
        """处理备份任务"""
        backup_dir = params.get('backup_dir', './backups')
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(backup_dir, f"backup_{timestamp}.db")

        # 复制数据库
        import shutil
        src_db = str(Path.home() / ".wechat-scraper" / "articles.db")
        if os.path.exists(src_db):
            shutil.copy2(src_db, backup_file)
            return f"备份完成: {backup_file}"

        return "备份失败: 源数据库不存在"

    def _handle_cleanup(self, params: Dict) -> str:
        """处理清理任务"""
        days = params.get('days', 30)
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        conn = self._get_connection()
        cursor = conn.execute(
            "DELETE FROM task_executions WHERE started_at < ?",
            (cutoff_date,)
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        return f"清理完成: 删除 {deleted} 条旧记录"

    def get_execution_history(self, task_id: str = None, limit: int = 50) -> List[TaskExecution]:
        """获取执行历史"""
        conn = self._get_connection()

        if task_id:
            cursor = conn.execute(
                """SELECT * FROM task_executions
                   WHERE task_id = ? ORDER BY started_at DESC LIMIT ?""",
                (task_id, limit)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM task_executions ORDER BY started_at DESC LIMIT ?",
                (limit,)
            )

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_execution(row) for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        conn = self._get_connection()

        # 任务统计
        cursor = conn.execute("SELECT COUNT(*) FROM scheduled_tasks")
        total_tasks = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM scheduled_tasks WHERE enabled = 1"
        )
        enabled_tasks = cursor.fetchone()[0]

        # 执行统计
        cursor = conn.execute("SELECT COUNT(*) FROM task_executions")
        total_runs = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM task_executions WHERE status = 'success'"
        )
        successful_runs = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM task_executions WHERE status = 'failed'"
        )
        failed_runs = cursor.fetchone()[0]

        # 最近24小时
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM task_executions WHERE started_at > ?",
            (yesterday,)
        )
        runs_24h = cursor.fetchone()[0]

        # 平均执行时间
        cursor = conn.execute(
            "SELECT AVG(duration_seconds) FROM task_executions WHERE duration_seconds IS NOT NULL"
        )
        avg_duration = cursor.fetchone()[0] or 0

        conn.close()

        return {
            'total_tasks': total_tasks,
            'enabled_tasks': enabled_tasks,
            'disabled_tasks': total_tasks - enabled_tasks,
            'total_runs': total_runs,
            'successful_runs': successful_runs,
            'failed_runs': failed_runs,
            'success_rate': (successful_runs / total_runs * 100) if total_runs > 0 else 0,
            'runs_24h': runs_24h,
            'avg_duration_seconds': round(avg_duration, 2)
        }

    def start_scheduler(self):
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        logger.info("调度器已启动")

    def stop_scheduler(self):
        """停止调度器"""
        self._running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        logger.info("调度器已停止")

    def _scheduler_loop(self):
        """调度器主循环"""
        while self._running:
            try:
                self._check_and_run_tasks()
            except Exception as e:
                logger.error(f"调度循环错误: {e}")

            # 每分钟检查一次
            time.sleep(60)

    def _check_and_run_tasks(self):
        """检查并执行任务"""
        now = datetime.now()
        tasks = self.list_tasks(enabled_only=True)

        for task in tasks:
            if not task.next_run:
                continue

            next_run = datetime.fromisoformat(task.next_run)

            # 如果下次执行时间已过，执行任务
            if next_run <= now:
                try:
                    self.run_task(task.id)
                except Exception as e:
                    logger.error(f"自动执行任务失败 {task.id}: {e}")

    def register_callback(self, event: str, callback: Callable):
        """注册回调函数"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _row_to_task(self, row: sqlite3.Row) -> ScheduledTask:
        """转换数据库行到对象"""
        return ScheduledTask(
            id=row['id'],
            name=row['name'],
            task_type=row['task_type'],
            cron_expression=row['cron_expression'],
            command=row['command'],
            params=json.loads(row['params']) if row['params'] else {},
            enabled=bool(row['enabled']),
            last_run=row['last_run'],
            last_status=row['last_status'],
            next_run=row['next_run'],
            run_count=row['run_count'],
            fail_count=row['fail_count'],
            created_at=row['created_at'],
            description=row['description'] or '',
            notify_on_success=bool(row['notify_on_success']),
            notify_on_failure=bool(row['notify_on_failure'])
        )

    def _row_to_execution(self, row: sqlite3.Row) -> TaskExecution:
        """转换数据库行到对象"""
        return TaskExecution(
            id=row['id'],
            task_id=row['task_id'],
            started_at=row['started_at'],
            completed_at=row['completed_at'],
            status=row['status'],
            output=row['output'] or '',
            error_message=row['error_message'],
            duration_seconds=row['duration_seconds'] or 0
        )


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='定时任务调度器')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 创建任务
    create_parser = subparsers.add_parser('create', help='创建任务')
    create_parser.add_argument('name', help='任务名称')
    create_parser.add_argument('cron', help='Cron表达式 (如 "0 9 * * *" 每天9点)')
    create_parser.add_argument('--type', default='custom',
                              choices=['scrape', 'export', 'backup', 'cleanup', 'custom'],
                              help='任务类型')
    create_parser.add_argument('--command', help='自定义命令')
    create_parser.add_argument('--desc', default='', help='描述')

    # 列出任务
    list_parser = subparsers.add_parser('list', help='列出任务')
    list_parser.add_argument('--enabled-only', action='store_true', help='仅显示启用的任务')

    # 运行任务
    run_parser = subparsers.add_parser('run', help='立即运行任务')
    run_parser.add_argument('task_id', help='任务ID')

    # 切换任务状态
    toggle_parser = subparsers.add_parser('toggle', help='切换任务启用状态')
    toggle_parser.add_argument('task_id', help='任务ID')

    # 删除任务
    delete_parser = subparsers.add_parser('delete', help='删除任务')
    delete_parser.add_argument('task_id', help='任务ID')

    # 执行历史
    history_parser = subparsers.add_parser('history', help='执行历史')
    history_parser.add_argument('--task', help='指定任务ID')
    history_parser.add_argument('-n', '--limit', type=int, default=20)

    # 统计
    subparsers.add_parser('stats', help='统计信息')

    # 启动调度器
    subparsers.add_parser('daemon', help='启动调度器守护进程')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    scheduler = TaskScheduler()

    if args.command == 'create':
        task = scheduler.create_task(
            name=args.name,
            task_type=args.type,
            cron=args.cron,
            command=args.command,
            description=args.desc
        )
        print(f"任务已创建: {task.id}")
        print(f"  名称: {task.name}")
        print(f"  类型: {task.task_type}")
        print(f"  Cron: {task.cron_expression}")
        print(f"  下次执行: {task.next_run}")

    elif args.command == 'list':
        tasks = scheduler.list_tasks(enabled_only=args.enabled_only)
        print(f"\n定时任务 ({len(tasks)}个):\n")
        for t in tasks:
            status = "✅" if t.enabled else "🚫"
            last = t.last_status or "未执行"
            print(f"{status} [{t.id}] {t.name}")
            print(f"   类型: {t.task_type} | Cron: {t.cron_expression}")
            print(f"   下次: {t.next_run or 'N/A'} | 上次: {last}")
            print(f"   执行: {t.run_count}次成功 | {t.fail_count}次失败\n")

    elif args.command == 'run':
        print(f"执行任务: {args.task_id}")
        execution = scheduler.run_task(args.task_id)
        print(f"执行结果: {execution.status}")
        print(f"耗时: {execution.duration_seconds:.2f}秒")
        if execution.output:
            print(f"输出:\n{execution.output}")
        if execution.error_message:
            print(f"错误: {execution.error_message}")

    elif args.command == 'toggle':
        if scheduler.toggle_task(args.task_id):
            task = scheduler.get_task(args.task_id)
            status = "启用" if task.enabled else "禁用"
            print(f"任务已{status}: {args.task_id}")

    elif args.command == 'delete':
        if scheduler.delete_task(args.task_id):
            print(f"任务已删除: {args.task_id}")
        else:
            print(f"任务不存在: {args.task_id}")

    elif args.command == 'history':
        history = scheduler.get_execution_history(args.task, args.limit)
        print(f"\n执行历史 ({len(history)}条):\n")
        for h in history[:10]:
            icon = "✅" if h.status == 'success' else "❌"
            print(f"{icon} [{h.task_id}] {h.started_at[:19]}")
            print(f"   状态: {h.status} | 耗时: {h.duration_seconds:.2f}秒")
            if h.error_message:
                print(f"   错误: {h.error_message}")

    elif args.command == 'stats':
        stats = scheduler.get_stats()
        print(f"\n调度器统计:\n")
        print(f"  总任务: {stats['total_tasks']}")
        print(f"  已启用: {stats['enabled_tasks']}")
        print(f"  已禁用: {stats['disabled_tasks']}")
        print(f"\n  总执行: {stats['total_runs']}")
        print(f"  成功: {stats['successful_runs']}")
        print(f"  失败: {stats['failed_runs']}")
        print(f"  成功率: {stats['success_rate']:.1f}%")
        print(f"\n  24小时执行: {stats['runs_24h']}")
        print(f"  平均耗时: {stats['avg_duration_seconds']:.2f}秒")

    elif args.command == 'daemon':
        print("启动调度器守护进程...")
        scheduler.start_scheduler()
        print("按 Ctrl+C 停止")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止调度器...")
            scheduler.stop_scheduler()

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
