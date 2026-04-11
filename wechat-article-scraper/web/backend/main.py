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
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# 添加 scripts 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from storage import ArticleStorage
from queue import TaskQueue

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
    from queue import QueueConfig

    config = QueueConfig(**request.config) if request.config else QueueConfig(
        name=request.name)
    queue_id = queue_manager.create_queue(request.name, config)

    return {"success": True, "data": {"id": queue_id, "name": request.name}}


@app.post("/api/queues/{queue_id}/tasks", response_model=Dict[str, Any])
async def add_tasks(queue_id: str, request: AddTasksRequest):
    """添加任务"""
    from queue import Task

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
