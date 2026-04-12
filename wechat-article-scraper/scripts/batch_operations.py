#!/usr/bin/env python3
"""
批量操作引擎 - 批量导出/编辑/同步/删除

功能：
- 批量导出：多格式、多文章、进度追踪
- 批量编辑：标签、分类、元数据
- 批量同步：同步到第三方平台
- 批量删除/归档
- 操作队列和进度追踪

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger('batch-operations')


class BatchOperationType(Enum):
    """批量操作类型"""
    EXPORT = "export"
    EDIT = "edit"
    SYNC = "sync"
    DELETE = "delete"
    ARCHIVE = "archive"


class BatchOperationStatus(Enum):
    """批量操作状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchTask:
    """批量任务"""
    id: str
    operation_type: str
    target_ids: List[str]
    params: Dict[str, Any]
    status: str = "pending"
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    total: int = 0
    completed: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "operation_type": self.operation_type,
            "target_ids": self.target_ids,
            "params": self.params,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "errors": self.errors
        }


class BatchOperationEngine:
    """批量操作引擎"""

    def __init__(self, db_path: str = None, articles_db: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "batch_operations.db")

        self.db_path = db_path
        self.articles_db = articles_db or str(Path.home() / ".wechat-scraper" / "articles.db")
        self._init_db()
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self.progress_callbacks: Dict[str, Callable] = {}

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_tasks (
                id TEXT PRIMARY KEY,
                operation_type TEXT,
                target_ids TEXT,
                params TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                total INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                errors TEXT DEFAULT '[]'
            )
        """)
        conn.commit()
        conn.close()

    def _generate_task_id(self) -> str:
        """生成任务ID"""
        import hashlib
        return hashlib.md5(
            f"batch_{datetime.now()}".encode()
        ).hexdigest()[:12]

    def create_task(self, operation_type: str, target_ids: List[str],
                   params: Dict[str, Any]) -> BatchTask:
        """创建批量任务"""
        task_id = self._generate_task_id()

        task = BatchTask(
            id=task_id,
            operation_type=operation_type,
            target_ids=target_ids,
            params=params,
            status="pending",
            created_at=datetime.now().isoformat(),
            total=len(target_ids)
        )

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO batch_tasks
            (id, operation_type, target_ids, params, status, created_at, total)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            task.id, task.operation_type, json.dumps(target_ids),
            json.dumps(params), task.status, task.created_at, task.total
        ))
        conn.commit()
        conn.close()

        logger.info(f"批量任务已创建: {task_id} ({operation_type}, {len(target_ids)} items)")
        return task

    def get_task(self, task_id: str) -> Optional[BatchTask]:
        """获取任务"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM batch_tasks WHERE id = ?", (task_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return BatchTask(
            id=row["id"],
            operation_type=row["operation_type"],
            target_ids=json.loads(row["target_ids"]),
            params=json.loads(row["params"]),
            status=row["status"],
            created_at=row["created_at"],
            started_at=row["started_at"] or "",
            completed_at=row["completed_at"] or "",
            total=row["total"],
            completed=row["completed"],
            failed=row["failed"],
            errors=json.loads(row["errors"])
        )

    def list_tasks(self, status: str = None, limit: int = 50) -> List[BatchTask]:
        """列出任务"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        if status:
            cursor = conn.execute(
                "SELECT * FROM batch_tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM batch_tasks ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )

        rows = cursor.fetchall()
        conn.close()

        tasks = []
        for row in rows:
            tasks.append(BatchTask(
                id=row["id"],
                operation_type=row["operation_type"],
                target_ids=json.loads(row["target_ids"]),
                params=json.loads(row["params"]),
                status=row["status"],
                created_at=row["created_at"],
                started_at=row["started_at"] or "",
                completed_at=row["completed_at"] or "",
                total=row["total"],
                completed=row["completed"],
                failed=row["failed"],
                errors=json.loads(row["errors"])
            ))
        return tasks

    def _update_task_progress(self, task_id: str, completed: int,
                             failed: int = 0, error: str = None):
        """更新任务进度"""
        conn = sqlite3.connect(self.db_path)

        if error:
            cursor = conn.execute(
                "SELECT errors FROM batch_tasks WHERE id = ?", (task_id,)
            )
            row = cursor.fetchone()
            errors = json.loads(row[0]) if row else []
            errors.append(error)

            conn.execute(
                "UPDATE batch_tasks SET completed = ?, failed = ?, errors = ? WHERE id = ?",
                (completed, failed, json.dumps(errors), task_id)
            )
        else:
            conn.execute(
                "UPDATE batch_tasks SET completed = ?, failed = ? WHERE id = ?",
                (completed, failed, task_id)
            )

        conn.commit()
        conn.close()

        # 调用进度回调
        if task_id in self.progress_callbacks:
            task = self.get_task(task_id)
            self.progress_callbacks[task_id](task)

    def _complete_task(self, task_id: str, status: str = "completed"):
        """完成任务"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE batch_tasks SET status = ?, completed_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), task_id)
        )
        conn.commit()
        conn.close()

    async def run_batch_export(self, task_id: str, format: str,
                              output_dir: str, template: Dict = None):
        """执行批量导出"""
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from export_engine import ExportEngine

        task = self.get_task(task_id)
        if not task:
            logger.error(f"任务不存在: {task_id}")
            return

        self._start_task(task_id)

        engine = ExportEngine()

        # 获取文章数据
        articles = self._get_articles_by_ids(task.target_ids)

        # 执行导出
        output_path = os.path.join(
            output_dir,
            f"batch_export_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{engine.get_exporter(format).get_file_extension()}"
        )

        def progress_callback(current, total, message):
            self._update_task_progress(task_id, current)

        success = engine.export(
            articles, format, output_path,
            progress_callback=progress_callback
        )

        if success:
            self._complete_task(task_id, "completed")
            logger.info(f"批量导出完成: {output_path}")
        else:
            self._complete_task(task_id, "failed")
            logger.error(f"批量导出失败")

    def _start_task(self, task_id: str):
        """标记任务开始"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE batch_tasks SET status = ?, started_at = ? WHERE id = ?",
            ("running", datetime.now().isoformat(), task_id)
        )
        conn.commit()
        conn.close()

    def _get_articles_by_ids(self, article_ids: List[str]) -> List[Dict]:
        """根据ID获取文章"""
        if not article_ids:
            return []

        conn = sqlite3.connect(self.articles_db)
        conn.row_factory = sqlite3.Row

        placeholders = ",".join(["?"] * len(article_ids))
        cursor = conn.execute(
            f"SELECT * FROM articles WHERE id IN ({placeholders})",
            article_ids
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    async def run_batch_edit(self, task_id: str, edits: Dict[str, Any]):
        """执行批量编辑"""
        task = self.get_task(task_id)
        if not task:
            return

        self._start_task(task_id)

        conn = sqlite3.connect(self.articles_db)

        completed = 0
        failed = 0
        errors = []

        for article_id in task.target_ids:
            try:
                # 构建更新语句
                set_clauses = []
                params = []

                for field, value in edits.items():
                    set_clauses.append(f"{field} = ?")
                    if isinstance(value, (list, dict)):
                        params.append(json.dumps(value))
                    else:
                        params.append(value)

                params.append(article_id)

                sql = f"UPDATE articles SET {', '.join(set_clauses)} WHERE id = ?"
                conn.execute(sql, params)

                completed += 1
                self._update_task_progress(task_id, completed, failed)

            except Exception as e:
                failed += 1
                errors.append(f"{article_id}: {str(e)}")
                self._update_task_progress(task_id, completed, failed, str(e))

        conn.commit()
        conn.close()

        if failed == 0:
            self._complete_task(task_id, "completed")
        elif completed == 0:
            self._complete_task(task_id, "failed")
        else:
            self._complete_task(task_id, "completed_with_errors")

    async def run_batch_sync(self, task_id: str, integration_name: str):
        """执行批量同步"""
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from integrations import IntegrationManager

        task = self.get_task(task_id)
        if not task:
            return

        self._start_task(task_id)

        manager = IntegrationManager()
        articles = self._get_articles_by_ids(task.target_ids)

        completed = 0
        failed = 0

        for article in articles:
            try:
                result = await manager.sync_article(integration_name, article)
                if result.get("success"):
                    completed += 1
                else:
                    failed += 1
                    self._update_task_progress(
                        task_id, completed, failed, result.get("error")
                    )

                self._update_task_progress(task_id, completed, failed)

            except Exception as e:
                failed += 1
                self._update_task_progress(task_id, completed, failed, str(e))

        if failed == 0:
            self._complete_task(task_id, "completed")
        elif completed == 0:
            self._complete_task(task_id, "failed")
        else:
            self._complete_task(task_id, "completed_with_errors")

    async def run_batch_delete(self, task_id: str, soft_delete: bool = True):
        """执行批量删除"""
        task = self.get_task(task_id)
        if not task:
            return

        self._start_task(task_id)

        conn = sqlite3.connect(self.articles_db)

        completed = 0
        failed = 0

        for article_id in task.target_ids:
            try:
                if soft_delete:
                    # 软删除：标记为已删除
                    conn.execute(
                        "UPDATE articles SET deleted_at = ? WHERE id = ?",
                        (datetime.now().isoformat(), article_id)
                    )
                else:
                    # 硬删除
                    conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))

                completed += 1
                self._update_task_progress(task_id, completed, failed)

            except Exception as e:
                failed += 1
                self._update_task_progress(task_id, completed, failed, str(e))

        conn.commit()
        conn.close()

        if failed == 0:
            self._complete_task(task_id, "completed")
        else:
            self._complete_task(task_id, "completed_with_errors")

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.get_task(task_id)
        if not task or task.status not in ["pending", "running"]:
            return False

        # 如果正在运行，取消async任务
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()

        self._complete_task(task_id, "cancelled")
        return True

    def get_stats(self) -> Dict:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM batch_tasks")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM batch_tasks WHERE status = 'completed'")
        completed = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM batch_tasks WHERE status = 'failed'")
        failed = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM batch_tasks WHERE status = 'running'")
        running = cursor.fetchone()[0]

        conn.close()

        return {
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "success_rate": (completed / total * 100) if total > 0 else 0
        }


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='批量操作引擎')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 列出任务
    list_parser = subparsers.add_parser('list', help='列出任务')
    list_parser.add_argument('--status', help='按状态筛选')
    list_parser.add_argument('-n', '--limit', type=int, default=20)

    # 创建导出任务
    export_parser = subparsers.add_parser('export', help='创建批量导出任务')
    export_parser.add_argument('--ids', required=True, help='文章ID列表(JSON数组)')
    export_parser.add_argument('--format', required=True,
                              choices=['excel', 'pdf', 'word', 'markdown', 'json', 'csv'])
    export_parser.add_argument('--output', required=True, help='输出目录')

    # 创建编辑任务
    edit_parser = subparsers.add_parser('edit', help='创建批量编辑任务')
    edit_parser.add_argument('--ids', required=True, help='文章ID列表')
    edit_parser.add_argument('--tags', help='设置标签(JSON数组)')
    edit_parser.add_argument('--category', help='设置分类')

    # 查看任务状态
    status_parser = subparsers.add_parser('status', help='查看任务状态')
    status_parser.add_argument('task_id', help='任务ID')

    # 统计
    subparsers.add_parser('stats', help='统计信息')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    engine = BatchOperationEngine()

    if args.command == 'list':
        tasks = engine.list_tasks(args.status, args.limit)
        print(f"\n批量任务 ({len(tasks)}个):\n")
        for t in tasks:
            status_icon = {
                "completed": "✅",
                "failed": "❌",
                "running": "🔄",
                "pending": "⏳",
                "cancelled": "🚫"
            }.get(t.status, "❓")
            print(f"{status_icon} {t.id} | {t.operation_type} | "
                  f"{t.completed}/{t.total} | {t.status}")

    elif args.command == 'export':
        ids = json.loads(args.ids)
        task = engine.create_task(
            "export", ids,
            {"format": args.format, "output_dir": args.output}
        )
        print(f"导出任务已创建: {task.id}")
        print(f"  格式: {args.format}")
        print(f"  数量: {len(ids)} 篇文章")

    elif args.command == 'edit':
        ids = json.loads(args.ids)
        edits = {}
        if args.tags:
            edits["tags"] = json.loads(args.tags)
        if args.category:
            edits["category"] = args.category

        task = engine.create_task("edit", ids, {"edits": edits})
        print(f"编辑任务已创建: {task.id}")

    elif args.command == 'status':
        task = engine.get_task(args.task_id)
        if task:
            print(f"\n任务详情:\n")
            print(f"  ID: {task.id}")
            print(f"  类型: {task.operation_type}")
            print(f"  状态: {task.status}")
            print(f"  进度: {task.completed}/{task.total}")
            print(f"  失败: {task.failed}")
            if task.errors:
                print(f"  错误: {len(task.errors)} 个")
        else:
            print(f"任务不存在: {args.task_id}")

    elif args.command == 'stats':
        stats = engine.get_stats()
        print(f"\n批量操作统计:\n")
        print(f"  总任务: {stats['total_tasks']}")
        print(f"  已完成: {stats['completed']}")
        print(f"  失败: {stats['failed']}")
        print(f"  运行中: {stats['running']}")
        print(f"  成功率: {stats['success_rate']:.1f}%")


if __name__ == '__main__':
    main()
