#!/usr/bin/env python3
"""
FastAPI 后端 - 微信文章抓取系统 Web 界面

吸取竞品 wcplusPro 精华：
- RESTful API 设计
- WebSocket 实时进度推送
- SQLite 数据持久化

技术栈：FastAPI + SQLite + WebSocket
"""

import sys
from pathlib import Path

# 添加 scripts 目录到路径 (必须在其他导入之前)
# main.py 在 web/backend/, 需要上溯3层到项目根目录
_scripts_path = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(_scripts_path))

import json
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from storage import ArticleStorage
from task_queue import TaskQueue

# 数据模型


class ArticleResponse(BaseModel):
    id: int
    url: str
    title: str
    author: str
    publish_time: Optional[str]
    category: Optional[str]
    wci_score: Optional[int]
    strategy: str
    content_status: str
    created_at: str


class QueueResponse(BaseModel):
    id: str
    name: str
    status: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]


class QueueStatusResponse(BaseModel):
    queue_id: str
    name: str
    status: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    progress: Dict[str, Any]


class StatisticsResponse(BaseModel):
    total_articles: int
    top_authors: List[Dict[str, Any]]
    category_distribution: List[Dict[str, Any]]
    wci_distribution: List[Dict[str, Any]]
    database_path: str
    generated_at: str


class ScrapeRequest(BaseModel):
    url: str
    strategy: Optional[str] = None
    download_images: bool = False
    output_format: str = "markdown"


class CreateQueueRequest(BaseModel):
    name: str
    config: Optional[Dict[str, Any]] = None


class AddTasksRequest(BaseModel):
    tasks: List[Dict[str, Any]]


# 全局实例
storage: Optional[ArticleStorage] = None
queue_manager: Optional[TaskQueue] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global storage, queue_manager

    # 初始化
    db_path = Path(__file__).parent.parent / "wechat_articles.db"
    storage = ArticleStorage(str(db_path))
    queue_manager = TaskQueue(str(db_path).replace(".db", "_queue.db"))

    yield

    # 清理
    storage = None
    queue_manager = None


app = FastAPI(
    title="微信文章抓取系统 API",
    description="微信文章抓取系统的 RESTful API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务 - React SPA
frontend_path = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Check if dist exists, fallback to frontend root for development
if not frontend_path.exists():
    frontend_path = Path(__file__).resolve().parent.parent / "frontend"

# Articles

@app.get("/api/articles", response_model=Dict[str, Any])
async def get_articles(
    author: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """获取文章列表"""
    articles = storage.list_articles(
        author=author,
        category=category,
        limit=limit,
        offset=offset
    )
    return {"success": True, "data": articles}


@app.get("/api/articles/{article_id}", response_model=Dict[str, Any])
async def get_article(article_id: int):
    """获取单篇文章"""
    article = storage.get_article_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    return {"success": True, "data": article}


@app.get("/api/articles/search", response_model=Dict[str, Any])
async def search_articles(keyword: str, limit: int = 20):
    """搜索文章"""
    articles = storage.search_articles(keyword, limit)
    return {"success": True, "data": articles}


# Sogou WeChat Search API

class SogouSearchRequest(BaseModel):
    keyword: str
    search_type: str = "articles"  # "articles" or "accounts"
    num_results: int = 10
    time_filter: Optional[str] = None  # day, week, month, year
    resolve_urls: bool = False  # Whether to resolve sogou links to real wechat URLs


@app.post("/api/search/sogou", response_model=Dict[str, Any])
async def sogou_search(request: SogouSearchRequest):
    """
    搜狗微信搜索 API

    支持两种搜索类型:
    - articles: 搜索微信公众号文章
    - accounts: 搜索微信公众号账号

    时间筛选仅对文章搜索有效:
    - day: 一天内
    - week: 一周内
    - month: 一月内
    - year: 一年内
    """
    try:
        # Import search module
        sys.path.insert(0, str(_scripts_path))
        from search import SogouWechatSearch, resolve_all_urls

        # Initialize searcher
        searcher = SogouWechatSearch(delay=1.5, enable_fallback=True)

        if request.search_type == "accounts":
            # Search for WeChat accounts
            results = searcher.search_accounts(
                keyword=request.keyword,
                num_results=request.num_results
            )

            # Format results
            formatted_results = []
            for r in results:
                formatted_results.append({
                    "name": r.name,
                    "wechat_id": r.wechat_id,
                    "description": r.description,
                    "recent_article_title": r.recent_article_title,
                    "recent_article_url": r.recent_article_url,
                    "verification": r.verification,
                    "is_official": r.is_official
                })

            return {
                "success": True,
                "data": {
                    "type": "accounts",
                    "keyword": request.keyword,
                    "total": len(formatted_results),
                    "results": formatted_results
                }
            }
        else:
            # Search for articles
            results = searcher.search(
                keyword=request.keyword,
                num_results=request.num_results,
                time_filter=request.time_filter
            )

            # Resolve URLs if requested
            if request.resolve_urls and results:
                results = resolve_all_urls(results, searcher, delay=0.3)

            # Format results
            formatted_results = []
            for r in results:
                formatted_results.append({
                    "title": r.title,
                    "url": r.url,
                    "abstract": r.abstract,
                    "source_account": r.source_account,
                    "publish_time": r.publish_time,
                    "is_temporary_url": r.is_temporary_url
                })

            return {
                "success": True,
                "data": {
                    "type": "articles",
                    "keyword": request.keyword,
                    "time_filter": request.time_filter,
                    "total": len(formatted_results),
                    "results": formatted_results
                }
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@app.get("/api/search/sogou", response_model=Dict[str, Any])
async def sogou_search_get(
    keyword: str,
    search_type: str = "articles",
    num_results: int = 10,
    time_filter: Optional[str] = None,
    resolve_urls: bool = False
):
    """搜狗微信搜索 API (GET 版本，便于浏览器直接访问)"""
    request = SogouSearchRequest(
        keyword=keyword,
        search_type=search_type,
        num_results=num_results,
        time_filter=time_filter,
        resolve_urls=resolve_urls
    )
    return await sogou_search(request)


# ==================== 历史文章采集 API ====================

class HistoryCrawlRequest(BaseModel):
    biz: str
    appmsg_token: str
    cookie: str = ""
    nickname: str = ""
    max_articles: int = 100  # 默认采集最近100篇


class HistoryCrawlTestRequest(BaseModel):
    biz: str
    appmsg_token: str
    cookie: str = ""


@app.post("/api/history-crawl", response_model=Dict[str, Any])
async def start_history_crawl(request: HistoryCrawlRequest):
    """
    启动历史文章采集任务

    对标 wcplusPro 的核心功能：
    - 使用 biz + appmsg_token + cookie 采集公众号历史文章
    - 支持断点续传
    - 异步执行，立即返回任务ID
    """
    try:
        # 生成任务ID
        import uuid
        task_id = str(uuid.uuid4())[:8]

        # 检查参数
        if not request.biz:
            raise HTTPException(status_code=400, detail="biz 参数不能为空")

        # 保存任务到数据库
        with storage._get_connection() as conn:
            conn.execute(
                """INSERT INTO history_crawl_tasks
                   (id, biz, nickname, appmsg_token, cookie, status, total_articles, created_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?, datetime('now'))""",
                (task_id, request.biz, request.nickname, request.appmsg_token,
                 request.cookie, request.max_articles)
            )

        # TODO: 启动后台任务实际执行采集
        # 这里先返回任务ID，实际采集逻辑需要异步执行

        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "status": "pending",
                "message": "采集任务已创建，正在排队执行"
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建采集任务失败: {str(e)}")


@app.post("/api/history-crawl/test", response_model=Dict[str, Any])
async def test_history_params(request: HistoryCrawlTestRequest):
    """
    测试历史文章采集参数是否有效

    尝试用提供的参数获取第一页文章列表，验证参数有效性
    """
    try:
        sys.path.insert(0, str(_scripts_path))
        from history_crawler import HistoryCrawler

        crawler = HistoryCrawler()
        # 尝试获取第一页（只获取1条）
        result = crawler.crawl(
            biz=request.biz,
            appmsg_token=request.appmsg_token,
            cookie=request.cookie,
            count=1  # 只测试获取1条
        )

        if result.get('success'):
            return {
                "success": True,
                "data": {
                    "valid": True,
                    "message": "参数有效，可以开始采集",
                    "total_available": result.get('total_count', 0)
                }
            }
        else:
            return {
                "success": True,
                "data": {
                    "valid": False,
                    "error": result.get('error', '参数验证失败')
                }
            }

    except Exception as e:
        return {
            "success": True,
            "data": {
                "valid": False,
                "error": str(e)
            }
        }


@app.get("/api/history-crawl/{task_id}", response_model=Dict[str, Any])
async def get_history_crawl_status(task_id: str):
    """获取历史文章采集任务状态"""
    try:
        with storage._get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, biz, nickname, status, total_articles,
                          completed_articles, failed_articles, created_at, updated_at
                   FROM history_crawl_tasks WHERE id = ?""",
                (task_id,)
            )
            row = cursor.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="任务不存在")

            return {
                "success": True,
                "data": {
                    "task_id": row[0],
                    "biz": row[1],
                    "nickname": row[2],
                    "status": row[3],
                    "total": row[4],
                    "completed": row[5] or 0,
                    "failed": row[6] or 0,
                    "created_at": row[7],
                    "updated_at": row[8]
                }
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history-crawl", response_model=Dict[str, Any])
async def list_history_crawl_tasks(limit: int = 20):
    """列出历史文章采集任务"""
    try:
        with storage._get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, biz, nickname, status, total_articles,
                          completed_articles, failed_articles, created_at
                   FROM history_crawl_tasks
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,)
            )
            rows = cursor.fetchall()

            tasks = []
            for row in rows:
                tasks.append({
                    "task_id": row[0],
                    "biz": row[1],
                    "nickname": row[2],
                    "status": row[3],
                    "total": row[4],
                    "completed": row[5] or 0,
                    "failed": row[6] or 0,
                    "created_at": row[7]
                })

            return {"success": True, "data": tasks}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== AI 摘要 API ====================

@app.get("/api/articles/{article_id}/summary", response_model=Dict[str, Any])
async def get_article_summary(article_id: int):
    """获取文章AI摘要"""
    # 从数据库查询已存在的摘要
    with storage._get_connection() as conn:
        cursor = conn.execute(
            "SELECT summary, key_points FROM ai_analysis WHERE article_id = ?",
            (article_id,)
        )
        row = cursor.fetchone()

    if row:
        return {
            "success": True,
            "data": {
                "quick_summary": row[0][:200] + "..." if row[0] and len(row[0]) > 200 else row[0],
                "detailed_summary": row[0],
                "key_points": row[1].split("\n") if row[1] else [],
                "generated_at": None
            }
        }

    return {"success": True, "data": None}


@app.post("/api/articles/{article_id}/summarize", response_model=Dict[str, Any])
async def generate_article_summary(article_id: int):
    """生成文章AI摘要"""
    # 获取文章内容
    article = storage.get_article_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    content = article.get("content", "")
    title = article.get("title", "")
    if not content:
        raise HTTPException(status_code=400, detail="文章内容为空")

    # 调用summarizer生成摘要
    try:
        import sys
        scripts_path = Path(__file__).resolve().parent.parent.parent / "scripts"
        sys.path.insert(0, str(scripts_path))
        from summarizer import Summarizer

        summarizer = Summarizer()
        summary_result = summarizer.summarize(title=title, content=content)

        # 保存到数据库
        with storage._get_connection() as conn:
            conn.execute(
                """INSERT INTO ai_analysis (article_id, summary, key_points, analyzed_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(article_id) DO UPDATE SET
                   summary = excluded.summary,
                   key_points = excluded.key_points,
                   analyzed_at = excluded.analyzed_at""",
                (article_id, summary_result.get("summary"), "\n".join(summary_result.get("key_points", [])))
            )

        return {
            "success": True,
            "data": {
                "quick_summary": summary_result.get("summary", "")[:200] + "...",
                "detailed_summary": summary_result.get("summary", ""),
                "key_points": summary_result.get("key_points", []),
                "generated_at": None
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成摘要失败: {str(e)}")




# Daily Review - 高亮复习系统

@app.get("/api/reviews/due", response_model=Dict[str, Any])
async def get_due_reviews(limit: int = 20):
    """获取今日待复习的高亮"""
    today = datetime.now().isoformat()

    with storage._get_connection() as conn:
        cursor = conn.execute(
            """SELECT rs.id, rs.highlight_id, rs.article_id, rs.review_count,
                      rs.next_review_at, rs.last_result,
                      h.content as highlight_content, h.note as highlight_note,
                      a.title as article_title, a.author as article_author
               FROM review_schedule rs
               LEFT JOIN highlights h ON rs.highlight_id = h.id
               LEFT JOIN articles a ON rs.article_id = a.id
               WHERE rs.next_review_at <= ?
               ORDER BY rs.next_review_at ASC
               LIMIT ?""",
            (today, limit)
        )
        rows = cursor.fetchall()

        reviews = []
        for row in rows:
            reviews.append({
                "id": row[0],
                "highlight_id": row[1],
                "article_id": row[2],
                "review_count": row[3],
                "next_review_at": row[4],
                "last_result": row[5],
                "highlight_content": row[6],
                "highlight_note": row[7],
                "article_title": row[8],
                "article_author": row[9]
            })

        # 获取今日统计
        cursor.execute(
            """SELECT COUNT(*) FROM review_schedule
               WHERE date(next_review_at) = date('now')"""
        )
        due_today = cursor.fetchone()[0]

        cursor.execute(
            """SELECT COUNT(*) FROM review_schedule
               WHERE date(last_reviewed_at) = date('now')"""
        )
        reviewed_today = cursor.fetchone()[0]

    return {
        "success": True,
        "data": {
            "reviews": reviews,
            "stats": {
                "due_today": due_today,
                "reviewed_today": reviewed_today,
                "remaining": len(reviews)
            }
        }
    }


@app.post("/api/reviews/{review_id}/submit", response_model=Dict[str, Any])
async def submit_review(review_id: int, request: Request):
    """提交复习反馈"""
    body = await request.json()
    feedback = body.get("feedback")  # remembered, fuzzy, forgotten

    if feedback not in ("remembered", "fuzzy", "forgotten"):
        raise HTTPException(status_code=400, detail="feedback必须是 remembered/fuzzy/forgotten")

    # 记忆曲线间隔（天）
    intervals = [1, 3, 7, 14, 30, 60, 90]

    with storage._get_connection() as conn:
        # 获取当前复习记录
        cursor = conn.execute(
            "SELECT review_count FROM review_schedule WHERE id = ?",
            (review_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="复习记录不存在")

        current_count = row[0] or 0

        # 根据反馈计算下一次复习时间
        if feedback == "remembered":
            # 记住：进入下一间隔
            next_index = min(current_count, len(intervals) - 1)
            days = intervals[next_index] if next_index < len(intervals) else 90
        elif feedback == "fuzzy":
            # 模糊：间隔缩短
            next_index = max(0, min(current_count, len(intervals) - 1) - 1)
            days = intervals[next_index] if next_index >= 0 else 1
        else:  # forgotten
            # 忘记：重置
            days = 1

        next_review = (datetime.now() + timedelta(days=days)).isoformat()

        # 更新记录
        conn.execute(
            """UPDATE review_schedule
               SET review_count = review_count + 1,
                   last_reviewed_at = datetime('now'),
                   last_result = ?,
                   next_review_at = ?
               WHERE id = ?""",
            (feedback, next_review, review_id)
        )

    return {
        "success": True,
        "data": {
            "review_id": review_id,
            "feedback": feedback,
            "next_review_at": next_review
        }
    }


@app.get("/api/highlights", response_model=Dict[str, Any])
async def get_highlights(article_id: int = None, limit: int = 50):
    """获取高亮列表"""
    with storage._get_connection() as conn:
        if article_id:
            cursor = conn.execute(
                """SELECT h.*, a.title as article_title
                   FROM highlights h
                   LEFT JOIN articles a ON h.article_id = a.id
                   WHERE h.article_id = ?
                   ORDER BY h.created_at DESC""",
                (article_id,)
            )
        else:
            cursor = conn.execute(
                """SELECT h.*, a.title as article_title
                   FROM highlights h
                   LEFT JOIN articles a ON h.article_id = a.id
                   ORDER BY h.created_at DESC
                   LIMIT ?""",
                (limit,)
            )

        rows = cursor.fetchall()
        highlights = [dict(row) for row in rows]

    return {"success": True, "data": highlights}


@app.post("/api/highlights", response_model=Dict[str, Any])
async def create_highlight(request: Request):
    """创建高亮并添加到复习队列"""
    body = await request.json()
    article_id = body.get("article_id")
    content = body.get("content")
    note = body.get("note", "")
    position = body.get("position", "")

    if not article_id or not content:
        raise HTTPException(status_code=400, detail="article_id和content必填")

    with storage._get_connection() as conn:
        # 创建高亮
        cursor = conn.execute(
            """INSERT INTO highlights (article_id, content, note, position, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (article_id, content, note, position)
        )
        highlight_id = cursor.lastrowid

        # 添加到复习队列（第一次复习在1天后）
        next_review = (datetime.now() + timedelta(days=1)).isoformat()
        conn.execute(
            """INSERT INTO review_schedule
               (highlight_id, article_id, next_review_at, created_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (highlight_id, article_id, next_review)
        )
        review_id = cursor.lastrowid

    return {
        "success": True,
        "data": {
            "highlight_id": highlight_id,
            "review_id": review_id,
            "next_review_at": next_review
        }
    }


@app.delete("/api/highlights/{highlight_id}", response_model=Dict[str, Any])
async def delete_highlight(highlight_id: int):
    """删除高亮"""
    with storage._get_connection() as conn:
        # 先删除关联的复习调度
        conn.execute(
            "DELETE FROM review_schedule WHERE highlight_id = ?",
            (highlight_id,)
        )
        # 删除高亮
        cursor = conn.execute(
            "DELETE FROM highlights WHERE id = ?",
            (highlight_id,)
        )

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="高亮不存在")

    return {"success": True, "message": "高亮已删除"}


@app.get("/api/highlights/stats", response_model=Dict[str, Any])
async def get_highlight_statistics():
    """获取高亮统计数据"""
    with storage._get_connection() as conn:
        # 总高亮数
        cursor = conn.execute("SELECT COUNT(*) FROM highlights")
        total_highlights = cursor.fetchone()[0]

        # 涉及文章数
        cursor.execute("SELECT COUNT(DISTINCT article_id) FROM highlights")
        articles_with_highlights = cursor.fetchone()[0]

        # 有批注的高亮数
        cursor.execute("SELECT COUNT(*) FROM highlights WHERE note IS NOT NULL AND note != ''")
        highlights_with_notes = cursor.fetchone()[0]

        # 最近7天新增
        cursor.execute(
            "SELECT COUNT(*) FROM highlights WHERE created_at >= datetime('now', '-7 days')"
        )
        recent_highlights = cursor.fetchone()[0]

        # 颜色分布（从 position JSON 中解析）
        color_distribution = {}
        cursor.execute("SELECT position FROM highlights")
        for row in cursor.fetchall():
            try:
                pos = json.loads(row[0] or '{}')
                color = pos.get('color', 'yellow')
                color_distribution[color] = color_distribution.get(color, 0) + 1
            except:
                pass

    return {
        "success": True,
        "data": {
            "total_highlights": total_highlights,
            "articles_with_highlights": articles_with_highlights,
            "highlights_with_notes": highlights_with_notes,
            "recent_highlights": recent_highlights,
            "color_distribution": color_distribution
        }
    }
# Statistics

@app.get("/api/statistics", response_model=Dict[str, Any])
async def get_statistics():
    """获取统计数据"""
    stats = storage.get_statistics()
    return {"success": True, "data": stats}


# Queues

@app.get("/api/queues", response_model=Dict[str, Any])
async def get_queues():
    """获取队列列表"""
    queues = queue_manager.list_queues()
    return {"success": True, "data": queues}


@app.get("/api/queues/{queue_id}", response_model=Dict[str, Any])
async def get_queue(queue_id: str):
    """获取队列详情"""
    queues = queue_manager.list_queues()
    queue = next((q for q in queues if q["id"] == queue_id), None)
    if not queue:
        raise HTTPException(status_code=404, detail="队列不存在")
    return {"success": True, "data": queue}


@app.get("/api/queues/{queue_id}/status", response_model=Dict[str, Any])
async def get_queue_status(queue_id: str):
    """获取队列状态"""
    status = queue_manager.get_status(queue_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return {"success": True, "data": status}


@app.get("/api/queues/{queue_id}/tasks", response_model=Dict[str, Any])
async def get_queue_tasks(queue_id: str, status: Optional[str] = None):
    """获取队列任务"""
    tasks = queue_manager.get_tasks(queue_id, status)
    return {"success": True, "data": tasks}


@app.post("/api/queues", response_model=Dict[str, Any])
async def create_queue(request: CreateQueueRequest):
    """创建队列"""
    from task_queue import QueueConfig

    config = QueueConfig(**request.config) if request.config else QueueConfig(
        name=request.name)
    queue_id = queue_manager.create_queue(request.name, config)

    return {"success": True, "data": {"id": queue_id, "name": request.name}}


@app.post("/api/queues/{queue_id}/tasks", response_model=Dict[str, Any])
async def add_tasks(queue_id: str, request: AddTasksRequest):
    """添加任务"""
    from task_queue import Task

    tasks = [Task(**t) for t in request.tasks]
    count = queue_manager.add_tasks(queue_id, tasks)

    return {"success": True, "data": {"count": count}}


@app.post("/api/queues/{queue_id}/start", response_model=Dict[str, Any])
async def start_queue(queue_id: str):
    """启动队列"""
    def progress_callback(qid, task_id, status, info):
        # WebSocket 广播会在实际实现中处理
        pass

    success = queue_manager.start(queue_id, progress_callback)
    if not success:
        raise HTTPException(status_code=400, detail="队列启动失败")

    return {"success": True, "data": {"message": "队列已启动"}}


@app.post("/api/queues/{queue_id}/pause", response_model=Dict[str, Any])
async def pause_queue(queue_id: str):
    """暂停队列"""
    success = queue_manager.pause()
    if not success:
        raise HTTPException(status_code=400, detail="队列暂停失败")

    return {"success": True, "data": {"message": "队列已暂停"}}


@app.post("/api/queues/{queue_id}/resume", response_model=Dict[str, Any])
async def resume_queue(queue_id: str):
    """恢复队列"""
    success = queue_manager.resume()
    if not success:
        raise HTTPException(status_code=400, detail="队列恢复失败")

    return {"success": True, "data": {"message": "队列已恢复"}}


@app.post("/api/queues/{queue_id}/stop", response_model=Dict[str, Any])
async def stop_queue(queue_id: str):
    """停止队列"""
    success = queue_manager.stop()
    if not success:
        raise HTTPException(status_code=400, detail="队列停止失败")

    return {"success": True, "data": {"message": "队列已停止"}}


# Scrape

@app.post("/api/scrape", response_model=Dict[str, Any])
async def scrape_article(request: ScrapeRequest):
    """抓取单篇文章"""
    from scraper import scrape_article

    result = scrape_article(
        url=request.url,
        strategy=request.strategy,
        download_images=request.download_images,
        output_format=request.output_format
    )

    if result.get("success"):
        # 保存到存储
        storage.save_article(result)
        return {"success": True, "data": result}
    else:
        raise HTTPException(
            status_code=400, detail=result.get("error", "抓取失败"))


class ImportArticleRequest(BaseModel):
    url: str
    title: str
    content: str
    author: str = ""
    publish_time: str = ""
    html_content: str = ""
    images: List[Dict[str, Any]] = []
    source: str = "extension"


@app.post("/api/articles/import", response_model=Dict[str, Any])
async def import_article(request: ImportArticleRequest):
    """
    导入文章（供扩展直接上传提取的内容）

    这是核心端点：扩展在微信已登录页面提取内容后，直接上传保存
    避免服务器无登录态无法抓取的问题
    """
    try:
        # 构建文章数据
        article_data = {
            'source_url': request.url,
            'url': request.url,
            'title': request.title,
            'content': request.content,
            'author': request.author,
            'publishTime': request.publish_time,
            'html': request.html_content,
            'images': request.images,
            'strategy': 'extension_import',
            'content_status': 'complete',
            'source': request.source
        }

        # 保存到数据库
        article_id, action = storage.save_article(article_data)

        return {
            "success": True,
            "data": {
                "id": article_id,
                "action": action,
                "title": request.title,
                "url": request.url
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


# Image download endpoint
@app.post("/api/articles/{article_id}/download-images", response_model=Dict[str, Any])
async def download_article_images(article_id: int):
    """
    下载文章中的图片到本地存储

    对标 Cubox/wcplusPro：完整离线保存能力
    """
    import asyncio
    import aiohttp
    from pathlib import Path

    # Get article
    article = storage.get_article_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    # Prepare storage path
    images_dir = Path(__file__).parent / "storage" / "images" / str(article_id)
    images_dir.mkdir(parents=True, exist_ok=True)

    # Get images from article
    images = article.get('images', [])
    if not images:
        return {"success": True, "data": {"downloaded": 0, "failed": 0, "images": []}}

    downloaded_images = []
    failed_count = 0

    async def download_image(session, img_data, index):
        """下载单张图片"""
        nonlocal failed_count
        img_url = img_data.get('url', '')
        if not img_url:
            failed_count += 1
            return None

        # Generate local filename
        ext = img_url.split('.')[-1].split('?')[0][:4] or 'jpg'
        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            ext = 'jpg'
        local_filename = f"{index:03d}.{ext}"
        local_path = images_dir / local_filename

        try:
            # Download image with proper headers for WeChat
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Referer': 'https://mp.weixin.qq.com/'  # Required for WeChat images
            }
            async with session.get(img_url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    content = await response.read()
                    with open(local_path, 'wb') as f:
                        f.write(content)

                    return {
                        'original_url': img_url,
                        'local_path': str(local_path.relative_to(Path(__file__).parent)),
                        'filename': local_filename,
                        'size': len(content)
                    }
                else:
                    failed_count += 1
                    return None
        except Exception as e:
            print(f"[Image Download] Failed to download {img_url}: {e}")
            failed_count += 1
            return None

    # Download all images concurrently
    async with aiohttp.ClientSession() as session:
        tasks = [download_image(session, img, i) for i, img in enumerate(images)]
        results = await asyncio.gather(*tasks)
        downloaded_images = [r for r in results if r is not None]

    # Update article with local image paths
    if downloaded_images:
        # Build URL mapping for content replacement
        url_mapping = {}
        for img in downloaded_images:
            url_mapping[img['original_url']] = f"/storage/images/{article_id}/{img['filename']}"

        # Update images metadata
        updated_images = []
        for img in images:
            original_url = img.get('url', '')
            local_url = url_mapping.get(original_url, original_url)
            updated_images.append({
                **img,
                'local_url': local_url,
                'downloaded': original_url in url_mapping
            })

        # Update article in database
        storage.update_article_images(article_id, updated_images)

    return {
        "success": True,
        "data": {
            "downloaded": len(downloaded_images),
            "failed": failed_count,
            "total": len(images),
            "images": downloaded_images
        }
    }


# RSS Feeds

@app.get("/api/rss/{feed_name}")
async def get_rss_feed(
    feed_name: str,
    author: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50
):
    """获取 RSS Feed"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        from rss_generator import RSSGenerator

        db_path = Path(__file__).parent.parent / "wechat_articles.db"
        base_url = "http://localhost:8000"

        generator = RSSGenerator(str(db_path), base_url)

        # 构建标题
        title = "微信公众号文章"
        if author:
            title = f"{author} - 微信公众号文章"
        elif category:
            title = f"{category} - 微信公众号文章"

        feed_path = generator.generate_feed(
            feed_name=feed_name,
            title=title,
            author=author,
            category=category,
            limit=limit,
            full_text=True
        )

        # 读取并返回 XML
        xml_content = Path(feed_path).read_text(encoding='utf-8')
        from fastapi.responses import Response
        return Response(
            content=xml_content,
            media_type="application/rss+xml; charset=utf-8"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成 RSS 失败: {str(e)}")


@app.get("/api/rss")
async def list_rss_feeds():
    """列出所有可用的 RSS Feeds"""
    try:
        feed_dir = Path(__file__).parent.parent / "feeds"
        feeds = []

        if feed_dir.exists():
            for f in feed_dir.glob("*.xml"):
                feeds.append({
                    "name": f.stem,
                    "url": f"/api/rss/{f.stem}",
                    "size": f.stat().st_size,
                    "updated": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                })

        return {"success": True, "data": feeds}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket for real-time updates


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 实时更新"""
    await websocket.accept()
    try:
        while True:
            # 定期发送队列状态更新
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "subscribe_queue":
                queue_id = message.get("queue_id")
                # 发送队列状态
                status = queue_manager.get_status(queue_id)
                await websocket.send_json({
                    "type": "queue_status",
                    "data": status
                })

    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


# Dashboard API

@app.get("/api/dashboard/overview", response_model=Dict[str, Any])
async def get_dashboard_overview():
    """获取仪表盘概览数据"""
    from dashboard_api import DashboardAPI
    api = DashboardAPI(str(Path(__file__).parent.parent / "wechat_articles.db"))
    return {"success": True, "data": api.get_overview_stats()}


@app.get("/api/dashboard/reading", response_model=Dict[str, Any])
async def get_dashboard_reading():
    """获取阅读统计"""
    from dashboard_api import DashboardAPI
    api = DashboardAPI(str(Path(__file__).parent.parent / "wechat_articles.db"))
    return {"success": True, "data": api.get_reading_stats()}


@app.get("/api/dashboard/authors", response_model=Dict[str, Any])
async def get_dashboard_authors():
    """获取作者统计"""
    from dashboard_api import DashboardAPI
    api = DashboardAPI(str(Path(__file__).parent.parent / "wechat_articles.db"))
    return {"success": True, "data": api.get_author_stats()}


@app.get("/api/dashboard", response_model=Dict[str, Any])
async def get_full_dashboard():
    """获取完整仪表盘数据"""
    from dashboard_api import DashboardAPI
    api = DashboardAPI(str(Path(__file__).parent.parent / "wechat_articles.db"))
    return {"success": True, "data": api.get_full_dashboard()}


# Subscription Management

@app.get("/api/subscriptions", response_model=Dict[str, Any])
async def list_subscriptions():
    """获取所有订阅列表"""
    from subscription_api import SubscriptionAPI
    api = SubscriptionAPI()
    return {"success": True, "data": api.list_subscriptions()}


@app.post("/api/subscriptions", response_model=Dict[str, Any])
async def add_subscription(request: Dict[str, Any]):
    """添加订阅"""
    from subscription_api import SubscriptionAPI
    api = SubscriptionAPI()
    result = api.add_subscription(
        name=request.get("name"),
        biz=request.get("biz"),
        appmsg_token=request.get("appmsg_token"),
        cookie=request.get("cookie", ""),
        check_interval_hours=request.get("check_interval_hours", 6)
    )
    return {"success": True, "data": result}


@app.delete("/api/subscriptions/{sub_id}", response_model=Dict[str, Any])
async def remove_subscription(sub_id: str):
    """删除订阅"""
    from subscription_api import SubscriptionAPI
    api = SubscriptionAPI()
    success = api.remove_subscription(sub_id)
    if not success:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return {"success": True, "data": {"message": "订阅已删除"}}


@app.get("/api/subscriptions/stats", response_model=Dict[str, Any])
async def get_subscription_stats():
    """获取订阅统计"""
    from subscription_api import SubscriptionAPI
    api = SubscriptionAPI()
    return {"success": True, "data": api.get_stats()}


@app.post("/api/subscriptions/sync", response_model=Dict[str, Any])
async def sync_all_subscriptions():
    """立即同步所有订阅"""
    from subscription_api import SubscriptionAPI
    api = SubscriptionAPI()
    result = await api.sync_all()
    return {"success": result.get("success", False), "data": result}


# Notification Management

@app.get("/api/notifications/channels", response_model=Dict[str, Any])
async def list_notification_channels():
    """获取所有通知渠道"""
    from notification_system import NotificationSystem
    notifier = NotificationSystem()
    channels = notifier.list_channels()
    return {"success": True, "data": [
        {"id": c.id, "name": c.name, "type": c.channel_type, "enabled": c.enabled}
        for c in channels
    ]}


@app.post("/api/notifications/channels/email", response_model=Dict[str, Any])
async def add_email_channel(request: Dict[str, Any]):
    """添加邮件通知渠道"""
    from notification_system import NotificationSystem
    notifier = NotificationSystem()
    try:
        channel = notifier.add_email_channel(
            name=request.get("name"),
            smtp_host=request.get("smtp_host"),
            smtp_port=request.get("smtp_port", 587),
            username=request.get("username"),
            password=request.get("password"),
            use_tls=request.get("use_tls", True),
            from_addr=request.get("from_addr")
        )
        return {"success": True, "data": {"id": channel.id, "name": channel.name}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/notifications/channels/webhook", response_model=Dict[str, Any])
async def add_webhook_channel(request: Dict[str, Any]):
    """添加Webhook通知渠道"""
    from notification_system import NotificationSystem
    notifier = NotificationSystem()
    try:
        channel = notifier.add_webhook_channel(
            name=request.get("name"),
            webhook_url=request.get("url"),
            headers=request.get("headers", {"Content-Type": "application/json"})
        )
        return {"success": True, "data": {"id": channel.id, "name": channel.name}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/notifications/channels/{channel_id}", response_model=Dict[str, Any])
async def remove_notification_channel(channel_id: str):
    """删除通知渠道"""
    from notification_system import NotificationSystem
    notifier = NotificationSystem()
    conn = notifier._get_connection()
    cursor = conn.execute("DELETE FROM notification_channels WHERE id = ?", (channel_id,))
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="渠道不存在")
    return {"success": True, "data": {"message": "渠道已删除"}}


@app.post("/api/notifications/test", response_model=Dict[str, Any])
async def test_notification(request: Dict[str, Any]):
    """发送测试通知"""
    from notification_system import NotificationSystem
    notifier = NotificationSystem()
    try:
        channel_id = request.get("channel_id")
        to = request.get("to")
        template = request.get("template", "task_success")

        variables = {
            'task_name': '测试任务',
            'execution_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'duration': 5.2,
            'output_summary': '这是来自微信文章抓取系统的测试通知'
        }

        records = notifier.notify(
            template_id=template,
            channel_id=channel_id,
            variables=variables,
            recipients=[to] if to else None
        )

        success = all(r.status == 'success' for r in records)
        return {
            "success": success,
            "data": {"records": [{"id": r.id, "status": r.status} for r in records]}
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/notifications/history", response_model=Dict[str, Any])
async def get_notification_history(limit: int = 20):
    """获取通知历史"""
    from notification_system import NotificationSystem
    notifier = NotificationSystem()
    history = notifier.get_notification_history(limit)
    return {"success": True, "data": [
        {"id": h.id, "subject": h.subject, "status": h.status, "sent_at": h.sent_at}
        for h in history
    ]}


@app.get("/api/notifications/templates", response_model=Dict[str, Any])
async def list_notification_templates():
    """获取通知模板列表"""
    from notification_system import NotificationSystem
    notifier = NotificationSystem()
    return {"success": True, "data": [
        {"id": k, "name": v["name"]} for k, v in NotificationSystem.DEFAULT_TEMPLATES.items()
    ]}



# ==================== 阅读进度 API ====================

class ReadingProgressRequest(BaseModel):
    progress_percent: int
    last_position: int = 0
    read_time_seconds: int = 0
    is_finished: bool = False


@app.get("/api/articles/{article_id}/progress", response_model=Dict[str, Any])
async def get_reading_progress(article_id: int):
    """获取文章阅读进度"""
    progress = storage.get_reading_progress(article_id)
    return {
        "success": True,
        "data": progress or {
            "article_id": article_id,
            "progress_percent": 0,
            "last_position": 0,
            "read_time_seconds": 0,
            "is_finished": False
        }
    }


@app.post("/api/articles/{article_id}/progress", response_model=Dict[str, Any])
async def save_reading_progress(article_id: int, request: ReadingProgressRequest):
    """保存文章阅读进度"""
    try:
        storage.save_reading_progress(
            article_id=article_id,
            progress_percent=request.progress_percent,
            last_position=request.last_position,
            read_time_seconds=request.read_time_seconds,
            is_finished=request.is_finished
        )
        return {
            "success": True,
            "data": {"message": "进度已保存"}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reading/in-progress", response_model=Dict[str, Any])
async def get_in_progress_articles(limit: int = 10):
    """获取正在阅读的文章列表"""
    articles = storage.get_in_progress_articles(limit)
    return {"success": True, "data": articles}


@app.get("/api/reading/finished", response_model=Dict[str, Any])
async def get_finished_articles(limit: int = 100):
    """获取已读完的文章列表"""
    articles = storage.get_finished_articles(limit)
    return {"success": True, "data": articles}


@app.get("/api/reading/statistics", response_model=Dict[str, Any])
async def get_reading_statistics():
    """获取阅读统计信息"""
    stats = storage.get_reading_statistics()
    return {"success": True, "data": stats}


# ============== Export API ==============

class ExportRequest(BaseModel):
    format: str = "markdown"  # markdown, html, json, pdf, excel
    include_images: bool = True
    include_meta: bool = True


class BatchExportRequest(BaseModel):
    article_ids: List[int]
    format: str = "markdown"  # markdown, html, json, excel
    include_meta: bool = True


@app.get("/api/articles/{article_id}/export", response_model=Dict[str, Any])
async def export_article(
    article_id: int,
    format: str = "markdown",
    include_images: bool = True,
    include_meta: bool = True
):
    """
    导出单篇文章为指定格式

    支持格式:
    - markdown: Markdown格式 (默认)
    - html: HTML格式
    - json: JSON格式
    - pdf: PDF格式 (需要playwright)
    - excel: Excel格式 (需要openpyxl)
    """
    try:
        # 导入导出模块
        sys.path.insert(0, str(_scripts_path))
        from export import Exporter

        # 获取文章数据
        article = storage.get_article_by_id(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="文章不存在")

        # 创建导出器
        exporter = Exporter(output_dir=str(Path(__file__).parent / "exports"))

        # 确保导出目录存在
        export_dir = Path(__file__).parent / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        # 根据格式导出
        format = format.lower()
        if format not in ['markdown', 'md', 'html', 'json', 'pdf', 'excel', 'xlsx']:
            raise HTTPException(status_code=400, detail=f"不支持的格式: {format}")

        # 生成文件名
        title = article.get('title', 'untitled')
        import re
        safe_title = re.sub(r'[<>"/\\|?*]', '', title)[:50]

        if format in ['pdf', 'excel', 'xlsx']:
            # PDF和Excel需要特殊处理，返回文件路径
            output_path = export_dir / f"{safe_title}.{format if format != 'xlsx' else 'xlsx'}"
            exporter.save(
                article,
                format=format,
                filename=safe_title,
                include_sidecar=False
            )

            # 读取文件并返回
            if output_path.exists():
                from fastapi.responses import FileResponse
                media_types = {
                    'pdf': 'application/pdf',
                    'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                }
                return FileResponse(
                    path=str(output_path),
                    filename=f"{safe_title}.{format if format != 'xlsx' else 'xlsx'}",
                    media_type=media_types.get(format, 'application/octet-stream')
                )
            else:
                raise HTTPException(status_code=500, detail="导出文件生成失败")

        else:
            # 文本格式直接返回内容
            content = exporter.save(
                article,
                format=format,
                filename=safe_title,
                include_sidecar=False
            )

            # 读取生成的文件内容
            output_path = Path(content)
            if output_path.exists():
                content = output_path.read_text(encoding='utf-8')
                # 删除临时文件
                output_path.unlink()

            media_types = {
                'markdown': 'text/markdown',
                'md': 'text/markdown',
                'html': 'text/html',
                'json': 'application/json'
            }

            return {
                "success": True,
                "data": {
                    "content": content,
                    "format": format,
                    "filename": f"{safe_title}.{format if format != 'md' else 'md'}",
                    "media_type": media_types.get(format, 'text/plain')
                }
            }

    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"导出模块未安装: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@app.post("/api/articles/export/batch", response_model=Dict[str, Any])
async def batch_export_articles(request: BatchExportRequest):
    """
    批量导出多篇文章

    支持格式:
    - markdown: 打包为zip文件
    - html: 打包为zip文件
    - json: 单个JSON文件
    - excel: Excel工作簿
    """
    try:
        sys.path.insert(0, str(_scripts_path))
        from export import Exporter
        from export_engine import ExportEngine

        if not request.article_ids:
            raise HTTPException(status_code=400, detail="文章ID列表不能为空")

        if request.format not in ['markdown', 'html', 'json', 'excel', 'md', 'xlsx']:
            raise HTTPException(status_code=400, detail=f"批量导出不支持格式: {request.format}")

        # 获取所有文章
        articles = []
        for article_id in request.article_ids:
            article = storage.get_article_by_id(article_id)
            if article:
                articles.append(article)

        if not articles:
            raise HTTPException(status_code=404, detail="未找到指定文章")

        # 创建导出目录
        export_dir = Path(__file__).parent / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if request.format in ['excel', 'xlsx']:
            # Excel批量导出
            engine = ExportEngine()
            output_path = export_dir / f"articles_export_{timestamp}.xlsx"

            success = engine.export(
                articles,
                format='excel',
                output_path=str(output_path)
            )

            if success and output_path.exists():
                from fastapi.responses import FileResponse
                return FileResponse(
                    path=str(output_path),
                    filename=f"articles_export_{timestamp}.xlsx",
                    media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
            else:
                raise HTTPException(status_code=500, detail="Excel导出失败")

        elif request.format == 'json':
            # JSON批量导出
            exporter = Exporter(output_dir=str(export_dir))
            output_path = export_dir / f"articles_export_{timestamp}.json"

            content = exporter.export_json(articles if len(articles) > 1 else articles[0])
            output_path.write_text(content, encoding='utf-8')

            from fastapi.responses import FileResponse
            return FileResponse(
                path=str(output_path),
                filename=f"articles_export_{timestamp}.json",
                media_type='application/json'
            )

        else:
            # Markdown/HTML批量导出为zip
            import zipfile
            exporter = Exporter(output_dir=str(export_dir))

            # 创建临时目录存放文件
            temp_dir = export_dir / f"temp_{timestamp}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            try:
                # 导出所有文章
                for article in articles:
                    title = article.get('title', 'untitled')
                    import re
                    safe_title = re.sub(r'[<>"/\\|?*]', '', title)[:50]

                    exporter.save(
                        article,
                        format=request.format,
                        filename=safe_title,
                        include_sidecar=False
                    )

                    # 移动文件到临时目录
                    src_file = export_dir / f"{safe_title}.{request.format}"
                    if src_file.exists():
                        dst_file = temp_dir / f"{safe_title}.{request.format}"
                        src_file.rename(dst_file)

                # 打包为zip
                zip_path = export_dir / f"articles_export_{timestamp}.zip"
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for file_path in temp_dir.iterdir():
                        if file_path.is_file():
                            zf.write(file_path, file_path.name)

                # 清理临时目录
                import shutil
                shutil.rmtree(temp_dir)

                from fastapi.responses import FileResponse
                return FileResponse(
                    path=str(zip_path),
                    filename=f"articles_export_{timestamp}.zip",
                    media_type='application/zip'
                )

            except Exception as e:
                # 清理临时目录
                if temp_dir.exists():
                    import shutil
                    shutil.rmtree(temp_dir)
                raise

    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"导出模块未安装: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量导出失败: {str(e)}")


@app.get("/api/export/formats", response_model=Dict[str, Any])
async def get_export_formats():
    """获取支持的导出格式列表"""
    return {
        "success": True,
        "data": {
            "single": [
                {"id": "markdown", "name": "Markdown", "ext": "md", "description": "Markdown格式，适合笔记软件"},
                {"id": "html", "name": "HTML", "ext": "html", "description": "网页格式，保留完整样式"},
                {"id": "json", "name": "JSON", "ext": "json", "description": "结构化数据，适合程序处理"},
                {"id": "pdf", "name": "PDF", "ext": "pdf", "description": "PDF文档，适合打印和分享"},
                {"id": "excel", "name": "Excel", "ext": "xlsx", "description": "Excel表格，适合数据分析"},
            ],
            "batch": [
                {"id": "markdown", "name": "Markdown", "ext": "zip", "description": "批量导出为Markdown并打包"},
                {"id": "html", "name": "HTML", "ext": "zip", "description": "批量导出为HTML并打包"},
                {"id": "json", "name": "JSON", "ext": "json", "description": "合并为单个JSON文件"},
                {"id": "excel", "name": "Excel", "ext": "xlsx", "description": "导出为Excel工作簿"},
            ]
        }
    }


# ============== Static Files and SPA Routing ==============
# Order matters: Mounts are checked in reverse order of definition (last first)
# So catch-all route must be defined BEFORE static file mounts

# 1. Serve downloaded images
storage_images_path = Path(__file__).parent / "storage" / "images"
if storage_images_path.exists():
    app.mount("/storage/images", StaticFiles(directory=str(storage_images_path)), name="images")

# 2. Serve React SPA static assets (JS/CSS files) - specific mount
assets_path = frontend_path / "assets"
if assets_path.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")

# 3. Define catch-all route for SPA client-side routing
# This handles all non-API, non-static routes
@app.get("/{path:path}", response_class=HTMLResponse)
async def serve_spa(path: str, request: Request):
    """
    Serve index.html for all non-API, non-static routes to support React Router.
    """
    # Skip API routes
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    # Skip static files (these should be handled by the mounts below)
    if "." in path:
        raise HTTPException(status_code=404, detail="Not found")

    # Serve index.html for all other paths (React Router handles the routing)
    index_file = frontend_path / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    else:
        raise HTTPException(status_code=404, detail="Frontend not built")

# 4. Serve root-level static files (vite.svg, manifest.json, etc.)
# This is a fallback for any files not caught by specific mounts
# Note: This must be defined LAST so catch-all route takes precedence for SPA paths
app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

