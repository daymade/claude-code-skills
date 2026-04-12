#!/usr/bin/env python3
"""
Dashboard API 服务 - 数据可视化后端

功能：
- RESTful API for 图表数据
- WebSocket for 实时更新
- CORS 支持

作者: Claude Code
版本: 1.0.0
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from analytics import AnalyticsEngine


# 创建 FastAPI 应用
app = FastAPI(
    title="WeChat Article Dashboard API",
    description="微信公众号文章数据可视化 API",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化分析引擎
analytics = AnalyticsEngine()

# 挂载静态文件
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ============== Pydantic Models ==============

class CoreMetrics(BaseModel):
    period_days: int
    total_articles: int
    total_reads: int
    total_likes: int
    total_shares: int
    avg_reads: float
    avg_likes: float
    avg_wci: float


class TrendPoint(BaseModel):
    date: str
    value: float
    count: int


class TopArticle(BaseModel):
    rank: int
    title: str
    url: str
    account_name: str
    reads: int
    likes: int
    wci: float
    publish_time: str


class HeatmapData(BaseModel):
    days: int
    max_count: int
    data: List[Dict[str, Any]]


class HourlyDistribution(BaseModel):
    hour: int
    count: int


class CategoryDistribution(BaseModel):
    category: str
    count: int
    percentage: float


class AccountStats(BaseModel):
    account_name: str
    article_count: int
    total_reads: int
    total_likes: int
    avg_wci: float


# ============== REST API Endpoints ==============

@app.get("/")
async def root():
    """Dashboard 主页"""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "name": "WeChat Article Dashboard API",
        "version": "1.0.0",
        "message": "Dashboard frontend not found. Please ensure static/index.html exists.",
        "endpoints": [
            "/api/metrics",
            "/api/trend",
            "/api/top-articles",
            "/api/heatmap",
            "/api/hourly",
            "/api/categories",
            "/api/accounts",
            "/api/quality"
        ]
    }


@app.get("/api/metrics", response_model=CoreMetrics)
async def get_metrics(days: int = Query(30, ge=1, le=365)):
    """
    获取核心指标

    Args:
        days: 统计天数 (1-365)
    """
    metrics = analytics.get_core_metrics(days)
    return CoreMetrics(**metrics)


@app.get("/api/trend", response_model=List[TrendPoint])
async def get_trend(
    metric: str = Query("reads", regex="^(reads|likes|wci|articles)$"),
    days: int = Query(30, ge=7, le=365)
):
    """
    获取趋势数据

    Args:
        metric: 指标类型 (reads, likes, wci, articles)
        days: 天数 (7-365)
    """
    trend_data = analytics.get_trend_data(metric, days)
    return [TrendPoint(**asdict(d)) for d in trend_data]


@app.get("/api/top-articles", response_model=List[TopArticle])
async def get_top_articles(
    by: str = Query("reads", regex="^(reads|likes|wci)$"),
    limit: int = Query(10, ge=1, le=50),
    days: int = Query(30, ge=1, le=365)
):
    """
    获取排行榜文章

    Args:
        by: 排序字段 (reads, likes, wci)
        limit: 数量限制 (1-50)
        days: 统计天数 (1-365)
    """
    articles = analytics.get_top_articles(by=by, limit=limit, days=days)
    return [TopArticle(**asdict(a)) for a in articles]


@app.get("/api/heatmap", response_model=HeatmapData)
async def get_heatmap(days: int = Query(90, ge=30, le=365)):
    """
    获取发布日历热力图数据

    Args:
        days: 统计天数 (30-365)
    """
    heatmap = analytics.get_publish_heatmap(days)
    return HeatmapData(**heatmap)


@app.get("/api/hourly", response_model=List[HourlyDistribution])
async def get_hourly_distribution(days: int = Query(30, ge=1, le=365)):
    """
    获取发布时间分布（小时级别）

    Args:
        days: 统计天数 (1-365)
    """
    hourly = analytics.get_hourly_distribution(days)
    return [HourlyDistribution(**d) for d in hourly]


@app.get("/api/categories", response_model=List[CategoryDistribution])
async def get_categories(days: int = Query(30, ge=1, le=365)):
    """
    获取内容分类占比

    Args:
        days: 统计天数 (1-365)
    """
    categories = analytics.get_category_distribution(days)
    return [CategoryDistribution(**d) for d in categories]


@app.get("/api/accounts", response_model=List[AccountStats])
async def get_accounts(days: int = Query(30, ge=1, le=365)):
    """
    获取各账号统计数据

    Args:
        days: 统计天数 (1-365)
    """
    accounts = analytics.get_account_stats(days)
    return [AccountStats(**d) for d in accounts]


@app.get("/api/quality")
async def get_quality_distribution(days: int = Query(30, ge=1, le=365)):
    """
    获取质量评分分布

    Args:
        days: 统计天数 (1-365)
    """
    distribution = analytics.get_quality_distribution(days)
    return distribution


# ============== WebSocket for Real-time Updates ==============

class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """广播消息到所有连接"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 实时数据推送

    客户端发送: {"action": "subscribe", "metrics": ["reads", "likes"]}
    服务端推送: {"type": "update", "data": {...}}
    """
    await manager.connect(websocket)
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "subscribe":
                # 发送初始数据
                metrics = analytics.get_core_metrics(30)
                await websocket.send_json({
                    "type": "initial",
                    "data": metrics
                })

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ============== Health Check ==============

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


def asdict(obj):
    """辅助函数：dataclass 转 dict"""
    if hasattr(obj, '__dataclass_fields__'):
        from dataclasses import asdict as dc_asdict
        return dc_asdict(obj)
    return obj


# ============== Main Entry ==============

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("WeChat Article Dashboard API")
    print("=" * 60)
    print("API Docs: http://localhost:8080/docs")
    print("Dashboard: http://localhost:8080")
    print("=" * 60)

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )
