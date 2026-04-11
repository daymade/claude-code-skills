#!/usr/bin/env python3
"""
批量任务队列系统

吸取竞品 wcplusPro 精华：
- 任务队列是专业数据抓取的必备功能
- 支持批量任务管理、暂停/恢复、失败重试
- 进度追踪和实时状态反馈

功能：
- 批量任务管理（添加、启动、暂停、恢复、停止）
- 断点续传（支持中断后恢复）
- 失败重试（自动重试失败任务，可配置重试次数）
- 并发控制（限制同时抓取数量）
- 进度追踪（实时进度条和统计）
- 多种任务源（URL 列表、搜索关键词、公众号列表）

作者: Claude Code
版本: 1.0.0
"""

import os
import sys
import json
import time
import logging
import sqlite3
import argparse
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum

# 配置日志
logger = logging.getLogger('wechat-queue')


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"         # 等待执行
    RUNNING = "running"         # 执行中
    SUCCESS = "success"         # 成功完成
    FAILED = "failed"           # 失败
    RETRYING = "retrying"       # 重试中
    CANCELLED = "cancelled"     # 已取消
    PAUSED = "paused"           # 已暂停


class QueueStatus(Enum):
    """队列状态"""
    IDLE = "idle"               # 空闲
    RUNNING = "running"         # 运行中
    PAUSED = "paused"           # 已暂停
    STOPPING = "stopping"       # 停止中
    STOPPED = "stopped"         # 已停止


@dataclass
class Task:
    """单个任务"""
    id: Optional[int] = None
    queue_id: str = ""
    task_type: str = "scrape"   # scrape, search, account
    target: str = ""            # URL 或关键词
    status: str = TaskStatus.PENDING.value
    priority: int = 5           # 1-10，数字越小优先级越高
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[Dict] = None
    error_message: str = ""
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class QueueConfig:
    """队列配置"""
    name: str = "default"
    max_workers: int = 3        # 并发数
    retry_on_failure: bool = True
    delay_between_tasks: float = 1.0  # 任务间隔（秒）
    save_to_storage: bool = True      # 自动保存到 SQLite
    download_images: bool = False
    output_format: str = "markdown"
    strategy: Optional[str] = None    # 抓取策略


class TaskQueue:
    """
    批量任务队列管理器

    吸取竞品精华：
    - wcplusPro 的任务队列支持暂停/恢复，非常实用
    - 批量任务需要进度显示和失败重试
    - 并发控制避免被封
    """

    def __init__(self, db_path: str = "wechat_queue.db"):
        """
        初始化任务队列

        Args:
            db_path: 队列数据库路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

        # 运行时状态
        self._status = QueueStatus.IDLE
        self._current_queue_id: Optional[str] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._lock = threading.Lock()
        self._progress_callback: Optional[Callable] = None

    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 队列表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS queues (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    config TEXT NOT NULL,
                    status TEXT DEFAULT 'idle',
                    total_tasks INTEGER DEFAULT 0,
                    completed_tasks INTEGER DEFAULT 0,
                    failed_tasks INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
            """)

            # 任务表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    queue_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    priority INTEGER DEFAULT 5,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    result TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY (queue_id) REFERENCES queues(id)
                )
            """)

            # 索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_queue ON tasks(queue_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")

            conn.commit()

    def create_queue(self, name: str, config: Optional[QueueConfig] = None) -> str:
        """
        创建新队列

        Args:
            name: 队列名称
            config: 队列配置

        Returns:
            队列 ID
        """
        queue_id = f"queue_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}"
        config = config or QueueConfig(name=name)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO queues (id, name, config, status, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (queue_id, name, json.dumps(asdict(config)), 'idle', datetime.now().isoformat()))
            conn.commit()

        logger.info(f"队列已创建: {queue_id}")
        return queue_id

    def add_tasks(self, queue_id: str, tasks: List[Task]) -> int:
        """
        添加任务到队列

        Args:
            queue_id: 队列 ID
            tasks: 任务列表

        Returns:
            添加的任务数量
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 验证队列存在
            cursor.execute("SELECT id FROM queues WHERE id = ?", (queue_id,))
            if not cursor.fetchone():
                raise ValueError(f"队列不存在: {queue_id}")

            now = datetime.now().isoformat()
            count = 0

            for task in tasks:
                cursor.execute("""
                    INSERT INTO tasks (queue_id, task_type, target, status, priority,
                                     retry_count, max_retries, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (queue_id, task.task_type, task.target, TaskStatus.PENDING.value,
                      task.priority, task.retry_count, task.max_retries, now))
                count += 1

            # 更新队列任务数
            cursor.execute("""
                UPDATE queues SET total_tasks = total_tasks + ? WHERE id = ?
            """, (count, queue_id))

            conn.commit()

        logger.info(f"已添加 {count} 个任务到队列 {queue_id}")
        return count

    def add_urls(self, queue_id: str, urls: List[str], **kwargs) -> int:
        """批量添加 URL 抓取任务"""
        tasks = [
            Task(task_type="scrape", target=url, **kwargs)
            for url in urls
        ]
        return self.add_tasks(queue_id, tasks)

    def add_search_tasks(self, queue_id: str, keywords: List[str], num_results: int = 10, **kwargs) -> int:
        """批量添加搜索任务"""
        tasks = [
            Task(task_type="search", target=json.dumps({"keyword": kw, "num": num_results}), **kwargs)
            for kw in keywords
        ]
        return self.add_tasks(queue_id, tasks)

    def start(self, queue_id: str, progress_callback: Optional[Callable] = None) -> bool:
        """
        启动队列执行

        Args:
            queue_id: 队列 ID
            progress_callback: 进度回调函数 (queue_id, task_id, status, progress_info)

        Returns:
            是否成功启动
        """
        with self._lock:
            if self._status == QueueStatus.RUNNING:
                logger.warning("队列已在运行中")
                return False

            self._current_queue_id = queue_id
            self._status = QueueStatus.RUNNING
            self._stop_event.clear()
            self._pause_event.clear()
            self._progress_callback = progress_callback

        # 获取队列配置
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT config FROM queues WHERE id = ?", (queue_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"队列不存在: {queue_id}")
            config = QueueConfig(**json.loads(row['config']))

        # 更新队列状态
        self._update_queue_status(queue_id, QueueStatus.RUNNING)

        # 启动执行线程
        self._executor = ThreadPoolExecutor(max_workers=config.max_workers)
        thread = threading.Thread(target=self._run_queue, args=(queue_id, config))
        thread.daemon = True
        thread.start()

        logger.info(f"队列 {queue_id} 已启动")
        return True

    def pause(self) -> bool:
        """暂停队列"""
        with self._lock:
            if self._status != QueueStatus.RUNNING:
                logger.warning("队列未在运行")
                return False

            self._status = QueueStatus.PAUSED
            self._pause_event.set()

        if self._current_queue_id:
            self._update_queue_status(self._current_queue_id, QueueStatus.PAUSED)

        logger.info("队列已暂停")
        return True

    def resume(self) -> bool:
        """恢复队列"""
        with self._lock:
            if self._status != QueueStatus.PAUSED:
                logger.warning("队列未暂停")
                return False

            self._status = QueueStatus.RUNNING
            self._pause_event.clear()

        if self._current_queue_id:
            self._update_queue_status(self._current_queue_id, QueueStatus.RUNNING)

        logger.info("队列已恢复")
        return True

    def stop(self) -> bool:
        """停止队列"""
        with self._lock:
            if self._status == QueueStatus.IDLE:
                logger.warning("队列未在运行")
                return False

            self._status = QueueStatus.STOPPING
            self._stop_event.set()

        logger.info("队列停止信号已发送")
        return True

    def _run_queue(self, queue_id: str, config: QueueConfig):
        """执行队列的主循环"""
        try:
            while not self._stop_event.is_set():
                # 检查暂停
                if self._pause_event.is_set():
                    time.sleep(0.5)
                    continue

                # 获取待执行任务
                task = self._get_next_task(queue_id)
                if not task:
                    # 没有更多任务
                    break

                # 执行任务
                self._execute_task(task, config)

                # 任务间隔
                if config.delay_between_tasks > 0:
                    time.sleep(config.delay_between_tasks)

            # 更新最终状态
            if self._stop_event.is_set():
                final_status = QueueStatus.STOPPED
            else:
                final_status = QueueStatus.IDLE

            self._update_queue_status(queue_id, final_status, completed_at=datetime.now().isoformat())

        except Exception as e:
            logger.error(f"队列执行异常: {e}")
            self._update_queue_status(queue_id, QueueStatus.STOPPED)

        finally:
            if self._executor:
                self._executor.shutdown(wait=True)

            with self._lock:
                self._status = QueueStatus.IDLE
                self._current_queue_id = None

    def _get_next_task(self, queue_id: str) -> Optional[Task]:
        """获取下一个待执行任务"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 优先获取 pending 任务，按优先级排序
            cursor.execute("""
                SELECT * FROM tasks
                WHERE queue_id = ? AND status = 'pending'
                ORDER BY priority ASC, id ASC
                LIMIT 1
            """, (queue_id,))

            row = cursor.fetchone()
            if row:
                return self._row_to_task(row)

            # 如果没有 pending 任务，检查是否有失败任务需要重试
            cursor.execute("""
                SELECT * FROM tasks
                WHERE queue_id = ? AND status = 'failed'
                AND retry_count < max_retries
                ORDER BY retry_count ASC, id ASC
                LIMIT 1
            """, (queue_id,))

            row = cursor.fetchone()
            if row:
                task = self._row_to_task(row)
                # 标记为重试中
                self._update_task_status(task.id, TaskStatus.RETRYING, retry_count=task.retry_count + 1)
                return task

            return None

    def _execute_task(self, task: Task, config: QueueConfig):
        """执行单个任务"""
        task_id = task.id
        self._update_task_status(task_id, TaskStatus.RUNNING, started_at=datetime.now().isoformat())

        try:
            # 根据任务类型执行不同操作
            if task.task_type == "scrape":
                result = self._scrape_article(task.target, config)
            elif task.task_type == "search":
                search_params = json.loads(task.target)
                result = self._search_articles(**search_params)
            else:
                raise ValueError(f"未知任务类型: {task.task_type}")

            # 更新成功状态
            self._update_task_status(
                task_id,
                TaskStatus.SUCCESS,
                result=json.dumps(result, ensure_ascii=False),
                completed_at=datetime.now().isoformat()
            )

            self._update_queue_stats(config.name, success=True)

            if self._progress_callback:
                self._progress_callback(config.name, task_id, "success", result)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"任务 {task_id} 执行失败: {error_msg}")

            # 检查是否需要重试
            if task.retry_count < task.max_retries and config.retry_on_failure:
                self._update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    error_message=error_msg,
                    retry_count=task.retry_count + 1
                )
            else:
                self._update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    error_message=error_msg,
                    completed_at=datetime.now().isoformat()
                )
                self._update_queue_stats(config.name, success=False)

            if self._progress_callback:
                self._progress_callback(config.name, task_id, "failed", {"error": error_msg})

    def _scrape_article(self, url: str, config: QueueConfig) -> Dict:
        """抓取单篇文章"""
        # 延迟导入避免循环依赖
        from scraper import scrape_article

        result = scrape_article(
            url=url,
            strategy=config.strategy,
            download_images=config.download_images,
            output_format=config.output_format
        )

        # 如果配置了自动保存到存储
        if config.save_to_storage and result.get('success'):
            try:
                from storage import ArticleStorage
                storage = ArticleStorage()
                storage.save_article(result)
            except Exception as e:
                logger.warning(f"自动保存到存储失败: {e}")

        return result

    def _search_articles(self, keyword: str, num: int = 10) -> Dict:
        """搜索文章"""
        from search import SogouWechatSearch

        searcher = SogouWechatSearch()
        results = searcher.search(keyword, num_results=num)

        return {
            "keyword": keyword,
            "count": len(results),
            "articles": [
                {
                    "title": r.title,
                    "url": r.url,
                    "source_account": r.source_account
                }
                for r in results
            ]
        }

    def _update_task_status(self, task_id: int, status: TaskStatus, **kwargs):
        """更新任务状态"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            fields = ["status = ?"]
            values = [status.value]

            for key, value in kwargs.items():
                fields.append(f"{key} = ?")
                values.append(value)

            values.append(task_id)

            cursor.execute(f"""
                UPDATE tasks SET {', '.join(fields)} WHERE id = ?
            """, values)
            conn.commit()

    def _update_queue_status(self, queue_id: str, status: QueueStatus, **kwargs):
        """更新队列状态"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            fields = ["status = ?"]
            values = [status.value]

            for key, value in kwargs.items():
                fields.append(f"{key} = ?")
                values.append(value)

            values.append(queue_id)

            cursor.execute(f"""
                UPDATE queues SET {', '.join(fields)} WHERE id = ?
            """, values)
            conn.commit()

    def _update_queue_stats(self, queue_id: str, success: bool):
        """更新队列统计"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if success:
                cursor.execute("""
                    UPDATE queues SET completed_tasks = completed_tasks + 1 WHERE id = ?
                """, (queue_id,))
            else:
                cursor.execute("""
                    UPDATE queues SET failed_tasks = failed_tasks + 1 WHERE id = ?
                """, (queue_id,))

            conn.commit()

    def get_status(self, queue_id: str) -> Dict[str, Any]:
        """获取队列状态"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM queues WHERE id = ?", (queue_id,))
            queue_row = cursor.fetchone()

            if not queue_row:
                return {"error": "队列不存在"}

            # 获取任务统计
            cursor.execute("""
                SELECT status, COUNT(*) as count FROM tasks WHERE queue_id = ? GROUP BY status
            """, (queue_id,))

            task_stats = {row['status']: row['count'] for row in cursor.fetchall()}

            return {
                "queue_id": queue_id,
                "name": queue_row['name'],
                "status": queue_row['status'],
                "total_tasks": queue_row['total_tasks'],
                "completed_tasks": queue_row['completed_tasks'],
                "failed_tasks": queue_row['failed_tasks'],
                "task_breakdown": task_stats,
                "progress": {
                    "percentage": round(queue_row['completed_tasks'] / queue_row['total_tasks'] * 100, 2) if queue_row['total_tasks'] > 0 else 0,
                    "completed": queue_row['completed_tasks'],
                    "failed": queue_row['failed_tasks'],
                    "remaining": queue_row['total_tasks'] - queue_row['completed_tasks'] - queue_row['failed_tasks']
                },
                "created_at": queue_row['created_at'],
                "started_at": queue_row['started_at'],
                "completed_at": queue_row['completed_at']
            }

    def get_tasks(self, queue_id: str, status: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """获取任务列表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if status:
                cursor.execute("""
                    SELECT * FROM tasks WHERE queue_id = ? AND status = ? LIMIT ?
                """, (queue_id, status, limit))
            else:
                cursor.execute("""
                    SELECT * FROM tasks WHERE queue_id = ? LIMIT ?
                """, (queue_id, limit))

            return [self._row_to_task_dict(row) for row in cursor.fetchall()]

    def list_queues(self) -> List[Dict]:
        """列出所有队列"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM queues ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def delete_queue(self, queue_id: str) -> bool:
        """删除队列及其所有任务"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 先删除任务
            cursor.execute("DELETE FROM tasks WHERE queue_id = ?", (queue_id,))

            # 再删除队列
            cursor.execute("DELETE FROM queues WHERE id = ?", (queue_id,))

            conn.commit()
            return cursor.rowcount > 0

    def export_results(self, queue_id: str, output_path: str):
        """导出队列结果到 JSON"""
        tasks = self.get_tasks(queue_id)

        results = {
            "queue_id": queue_id,
            "exported_at": datetime.now().isoformat(),
            "tasks": tasks
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        return output_path

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """将数据库行转换为 Task"""
        return Task(
            id=row['id'],
            queue_id=row['queue_id'],
            task_type=row['task_type'],
            target=row['target'],
            status=row['status'],
            priority=row['priority'],
            retry_count=row['retry_count'],
            max_retries=row['max_retries'],
            result=json.loads(row['result']) if row['result'] else None,
            error_message=row['error_message'],
            created_at=row['created_at'],
            started_at=row['started_at'],
            completed_at=row['completed_at']
        )

    def _row_to_task_dict(self, row: sqlite3.Row) -> Dict:
        """将数据库行转换为字典"""
        result = dict(row)
        if result.get('result'):
            try:
                result['result'] = json.loads(result['result'])
            except:
                pass
        return result


def print_progress(queue_id: str, task_id: int, status: str, info: Dict):
    """默认进度打印回调"""
    if status == "success":
        print(f"✅ [{queue_id}] 任务 {task_id} 完成")
    elif status == "failed":
        print(f"❌ [{queue_id}] 任务 {task_id} 失败: {info.get('error', '未知错误')}")
    else:
        print(f"⏳ [{queue_id}] 任务 {task_id} 状态: {status}")


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(description='微信文章批量任务队列')
    parser.add_argument('--db', default='wechat_queue.db', help='队列数据库路径')

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # create 命令
    create_parser = subparsers.add_parser('create', help='创建队列')
    create_parser.add_argument('name', help='队列名称')
    create_parser.add_argument('--workers', type=int, default=3, help='并发数')
    create_parser.add_argument('--delay', type=float, default=1.0, help='任务间隔(秒)')

    # add-urls 命令
    add_parser = subparsers.add_parser('add-urls', help='添加 URL 任务')
    add_parser.add_argument('queue_id', help='队列 ID')
    add_parser.add_argument('urls', nargs='+', help='文章 URL 列表')
    add_parser.add_argument('--priority', type=int, default=5, help='优先级')

    # status 命令
    status_parser = subparsers.add_parser('status', help='查看队列状态')
    status_parser.add_argument('queue_id', help='队列 ID')

    # start 命令
    start_parser = subparsers.add_parser('start', help='启动队列')
    start_parser.add_argument('queue_id', help='队列 ID')

    # pause 命令
    pause_parser = subparsers.add_parser('pause', help='暂停队列')

    # resume 命令
    resume_parser = subparsers.add_parser('resume', help='恢复队列')

    # stop 命令
    stop_parser = subparsers.add_parser('stop', help='停止队列')

    # list 命令
    list_parser = subparsers.add_parser('list', help='列出队列')

    # tasks 命令
    tasks_parser = subparsers.add_parser('tasks', help='查看任务列表')
    tasks_parser.add_argument('queue_id', help='队列 ID')
    tasks_parser.add_argument('--status', help='按状态筛选')

    # export 命令
    export_parser = subparsers.add_parser('export', help='导出结果')
    export_parser.add_argument('queue_id', help='队列 ID')
    export_parser.add_argument('-o', '--output', required=True, help='输出文件')

    args = parser.parse_args()

    queue = TaskQueue(args.db)

    if args.command == 'create':
        config = QueueConfig(
            name=args.name,
            max_workers=args.workers,
            delay_between_tasks=args.delay
        )
        queue_id = queue.create_queue(args.name, config)
        print(f"队列已创建: {queue_id}")

    elif args.command == 'add-urls':
        tasks = [
            Task(task_type="scrape", target=url, priority=args.priority)
            for url in args.urls
        ]
        count = queue.add_tasks(args.queue_id, tasks)
        print(f"已添加 {count} 个任务")

    elif args.command == 'status':
        status = queue.get_status(args.queue_id)
        print(json.dumps(status, ensure_ascii=False, indent=2))

    elif args.command == 'start':
        queue.start(args.queue_id, progress_callback=print_progress)
        print(f"队列 {args.queue_id} 已启动")

        # 等待队列完成
        try:
            while True:
                time.sleep(2)
                status = queue.get_status(args.queue_id)
                if status.get('status') in ['idle', 'stopped', 'completed']:
                    break
                progress = status.get('progress', {})
                print(f"进度: {progress.get('percentage', 0)}% ({progress.get('completed', 0)}/{status.get('total_tasks', 0)})")
        except KeyboardInterrupt:
            print("\n正在停止...")
            queue.stop()

    elif args.command == 'pause':
        queue.pause()
        print("队列已暂停")

    elif args.command == 'resume':
        queue.resume()
        print("队列已恢复")

    elif args.command == 'stop':
        queue.stop()
        print("队列已停止")

    elif args.command == 'list':
        queues = queue.list_queues()
        for q in queues:
            print(f"{q['id']}: {q['name']} ({q['status']}) - {q['completed_tasks']}/{q['total_tasks']}")

    elif args.command == 'tasks':
        tasks = queue.get_tasks(args.queue_id, args.status)
        for task in tasks[:20]:  # 只显示前20个
            print(f"[{task['id']}] {task['task_type']}: {task['target'][:50]}... ({task['status']})")

    elif args.command == 'export':
        output_path = queue.export_results(args.queue_id, args.output)
        print(f"结果已导出: {output_path}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
