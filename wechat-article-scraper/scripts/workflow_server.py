#!/usr/bin/env python3
"""
工作流 API 服务器 - RESTful 接口与 Webhook 接收

功能：
- RESTful API  for 工作流管理
- Webhook 接收端点
- 事件推送接口
- 实时 WebSocket 通知

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import asyncio
import argparse
import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from workflow_engine import WorkflowEngine, Workflow, TriggerConfig, ActionConfig

try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

logger = logging.getLogger('workflow-server')

# 数据模型
class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    trigger_type: str
    trigger_config: Dict
    actions: list
    conditions: list = []

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class EventPayload(BaseModel):
    event_type: str
    data: Dict

class WebhookPayload(BaseModel):
    workflow_id: Optional[str] = None
    secret: Optional[str] = None
    payload: Dict

# 创建 FastAPI 应用
if HAS_FASTAPI:
    app = FastAPI(
        title="微信文章抓取工作流 API",
        description="IFTTT 风格的自动化工作流引擎 REST API",
        version="1.0.0"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 全局引擎实例
    engine = None
    connected_websockets = []

    def get_engine():
        global engine
        if engine is None:
            db_path = str(Path.home() / ".wechat-scraper" / "workflows.db")
            engine = WorkflowEngine(db_path)
        return engine

    async def broadcast_event(event: Dict):
        """广播事件到所有 WebSocket 连接"""
        disconnected = []
        for ws in connected_websockets:
            try:
                await ws.send_json(event)
            except:
                disconnected.append(ws)

        for ws in disconnected:
            if ws in connected_websockets:
                connected_websockets.remove(ws)

    # === RESTful API 路由 ===

    @app.get("/")
    async def root():
        return {
            "name": "微信文章抓取工作流 API",
            "version": "1.0.0",
            "docs": "/docs",
            "endpoints": {
                "workflows": "/api/workflows",
                "events": "/api/events",
                "logs": "/api/logs",
                "stats": "/api/stats"
            }
        }

    @app.get("/api/workflows")
    async def list_workflows(status: Optional[str] = None):
        """列出所有工作流"""
        workflows = get_engine().list_workflows(status)
        return {
            "total": len(workflows),
            "workflows": [w.to_dict() for w in workflows]
        }

    @app.post("/api/workflows")
    async def create_workflow(workflow: WorkflowCreate):
        """创建工作流"""
        try:
            trigger = TriggerConfig(
                type=workflow.trigger_type,
                config=workflow.trigger_config
            )
            actions = [ActionConfig(type=a["type"], config=a.get("config", {})) for a in workflow.actions]

            new_workflow = get_engine().create_workflow(
                name=workflow.name,
                description=workflow.description,
                trigger=trigger,
                actions=actions,
                conditions=workflow.conditions
            )

            return new_workflow.to_dict()

        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str):
        """获取工作流详情"""
        workflow = get_engine().get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return workflow.to_dict()

    @app.put("/api/workflows/{workflow_id}")
    async def update_workflow(workflow_id: str, update: WorkflowUpdate):
        """更新工作流"""
        workflow = get_engine().get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="工作流不存在")

        updates = {}
        if update.name is not None:
            updates["name"] = update.name
        if update.description is not None:
            updates["description"] = update.description
        if update.status is not None:
            updates["status"] = update.status

        if updates:
            get_engine().update_workflow(workflow_id, **updates)

        return get_engine().get_workflow(workflow_id).to_dict()

    @app.delete("/api/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str):
        """删除工作流"""
        success = get_engine().delete_workflow(workflow_id)
        if not success:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"message": "工作流已删除"}

    @app.post("/api/workflows/{workflow_id}/trigger")
    async def trigger_workflow(workflow_id: str, event: EventPayload, background_tasks: BackgroundTasks):
        """手动触发工作流"""
        workflow = get_engine().get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="工作流不存在")

        log = await get_engine().trigger_workflow(workflow_id, event.data, is_manual=True)

        # 异步广播事件
        await broadcast_event({
            "type": "workflow_triggered",
            "workflow_id": workflow_id,
            "event": event.data,
            "timestamp": datetime.now().isoformat()
        })

        return log.to_dict() if log else {"error": "执行失败"}

    @app.post("/api/workflows/{workflow_id}/enable")
    async def enable_workflow(workflow_id: str):
        """启用工作流"""
        success = get_engine().enable_workflow(workflow_id)
        if not success:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"message": "工作流已启用"}

    @app.post("/api/workflows/{workflow_id}/disable")
    async def disable_workflow(workflow_id: str):
        """禁用工作流"""
        success = get_engine().disable_workflow(workflow_id)
        if not success:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"message": "工作流已禁用"}

    @app.post("/api/events")
    async def publish_event(event: EventPayload, background_tasks: BackgroundTasks):
        """发布事件，触发匹配的工作流"""
        event_data = {
            "event_type": event.event_type,
            **event.data
        }

        logs = get_engine().process_event(event_data)

        # 异步广播
        await broadcast_event({
            "type": "event_published",
            "event_type": event.event_type,
            "triggered_workflows": len(logs),
            "timestamp": datetime.now().isoformat()
        })

        return {
            "published": True,
            "triggered_workflows": len(logs),
            "logs": [log.to_dict() for log in logs]
        }

    @app.get("/api/logs")
    async def get_logs(workflow_id: Optional[str] = None, limit: int = 50):
        """获取执行日志"""
        logs = get_engine().get_logs(workflow_id, limit)
        return {
            "total": len(logs),
            "logs": [log.to_dict() for log in logs]
        }

    @app.get("/api/stats")
    async def get_stats():
        """获取统计信息"""
        return get_engine().get_stats()

    # === Webhook 接收端点 ===

    @app.post("/webhook/{workflow_id}")
    async def webhook_receiver(workflow_id: str, payload: WebhookPayload):
        """接收外部 Webhook 触发工作流"""
        workflow = get_engine().get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="工作流不存在")

        # 构建事件数据
        event_data = {
            "event_type": "webhook",
            "received_at": datetime.now().isoformat(),
            **payload.payload
        }

        log = await get_engine().trigger_workflow(workflow_id, event_data)

        return {
            "received": True,
            "workflow_id": workflow_id,
            "execution_status": log.status if log else "failed"
        }

    @app.post("/webhook/incoming/{secret}")
    async def incoming_webhook(secret: str, payload: Dict):
        """通用 Webhook 接收端点 - 根据 secret 路由到对应工作流"""
        # 这里可以实现基于 secret 的路由逻辑
        # 简化版本：遍历所有工作流，找到匹配的 secret

        workflows = get_engine().list_workflows(status="enabled")
        triggered = []

        for workflow in workflows:
            # 检查工作流配置中是否有匹配的 secret
            if workflow.trigger.config.get("webhook_secret") == secret:
                event_data = {
                    "event_type": "webhook",
                    "secret": secret,
                    "received_at": datetime.now().isoformat(),
                    **payload
                }
                log = await get_engine().trigger_workflow(workflow.id, event_data)
                if log:
                    triggered.append({"workflow_id": workflow.id, "status": log.status})

        return {
            "received": True,
            "secret": secret,
            "triggered": triggered
        }

    # === WebSocket 实时通知 ===

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket 实时通知连接"""
        await websocket.accept()
        connected_websockets.append(websocket)

        try:
            # 发送欢迎消息
            await websocket.send_json({
                "type": "connected",
                "message": "已连接到工作流实时通知服务"
            })

            while True:
                # 接收客户端心跳
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except:
                    pass

        except WebSocketDisconnect:
            if websocket in connected_websockets:
                connected_websockets.remove(websocket)

    @app.get("/health")
    async def health_check():
        """健康检查"""
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "websocket_connections": len(connected_websockets)
        }


def main():
    """CLI入口"""
    parser = argparse.ArgumentParser(description='工作流 API 服务器')
    parser.add_argument('--host', default='0.0.0.0', help='绑定地址')
    parser.add_argument('--port', type=int, default=8080, help='端口')
    parser.add_argument('--db', help='数据库路径')

    args = parser.parse_args()

    if not HAS_FASTAPI:
        print("错误: 需要安装 FastAPI 和 uvicorn")
        print("  pip install fastapi uvicorn")
        return

    # 设置全局数据库路径
    global engine
    if args.db:
        engine = WorkflowEngine(args.db)
    else:
        engine = WorkflowEngine()

    logging.basicConfig(level=logging.INFO)

    print(f"🚀 工作流 API 服务器启动")
    print(f"   地址: http://{args.host}:{args.port}")
    print(f"   文档: http://{args.host}:{args.port}/docs")
    print(f"   WebSocket: ws://{args.host}:{args.port}/ws")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
