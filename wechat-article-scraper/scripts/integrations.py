#!/usr/bin/env python3
"""
第三方集成模块 - Notion/语雀/Airtable 同步

功能：
- Notion 数据库同步
- 语雀知识库归档
- Airtable 表格同步
- Webhook 自动触发

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

logger = logging.getLogger('integrations')


@dataclass
class SyncConfig:
    """同步配置"""
    provider: str  # notion, yuque, airtable
    name: str
    config: Dict[str, Any]
    enabled: bool = True
    last_sync: str = ""
    sync_count: int = 0


class NotionClient:
    """Notion API 客户端"""

    API_BASE = "https://api.notion.com/v1"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

    async def create_page(self, database_id: str, properties: Dict) -> Dict:
        """在数据库中创建页面"""
        if not HAS_AIOHTTP:
            return {"success": False, "error": "需要安装 aiohttp"}

        url = f"{self.API_BASE}/pages"
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return {"success": True, "page_id": data.get("id")}
                    return {"success": False, "error": data.get("message", "Unknown error")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def update_page(self, page_id: str, properties: Dict) -> Dict:
        """更新页面"""
        if not HAS_AIOHTTP:
            return {"success": False, "error": "需要安装 aiohttp"}

        url = f"{self.API_BASE}/pages/{page_id}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(url, headers=self.headers, json={"properties": properties}) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return {"success": True}
                    return {"success": False, "error": data.get("message")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def query_database(self, database_id: str, filter: Dict = None) -> Dict:
        """查询数据库"""
        if not HAS_AIOHTTP:
            return {"success": False, "error": "需要安装 aiohttp"}

        url = f"{self.API_BASE}/databases/{database_id}/query"
        payload = {"filter": filter} if filter else {}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return {"success": True, "results": data.get("results", [])}
                    return {"success": False, "error": data.get("message")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def build_article_properties(self, article: Dict) -> Dict:
        """构建文章属性"""
        return {
            "标题": {"title": [{"text": {"content": article.get("title", "")}}]},
            "公众号": {"rich_text": [{"text": {"content": article.get("account_name", "")}}]},
            "链接": {"url": article.get("url", "")},
            "发布时间": {"date": {"start": article.get("publish_time", "")[:10]}},
            "阅读量": {"number": article.get("read_count", 0)},
            "点赞数": {"number": article.get("like_count", 0)},
            "标签": {"multi_select": [{"name": tag} for tag in article.get("tags", [])]},
            "摘要": {"rich_text": [{"text": {"content": article.get("summary", "")[:200]}}]}
        }


class YuqueClient:
    """语雀 API 客户端"""

    API_BASE = "https://www.yuque.com/api/v2"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "X-Auth-Token": token,
            "Content-Type": "application/json"
        }

    async def create_doc(self, repo_slug: str, title: str, body: str,
                        format: str = "markdown") -> Dict:
        """创建文档"""
        if not HAS_AIOHTTP:
            return {"success": False, "error": "需要安装 aiohttp"}

        url = f"{self.API_BASE}/repos/{repo_slug}/docs"
        payload = {
            "title": title,
            "body": body,
            "format": format
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return {"success": True, "doc_id": data.get("data", {}).get("id")}
                    return {"success": False, "error": data.get("message")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def update_doc(self, repo_slug: str, doc_slug: str,
                        title: str = None, body: str = None) -> Dict:
        """更新文档"""
        if not HAS_AIOHTTP:
            return {"success": False, "error": "需要安装 aiohttp"}

        url = f"{self.API_BASE}/repos/{repo_slug}/docs/{doc_slug}"
        payload = {}
        if title:
            payload["title"] = title
        if body:
            payload["body"] = body

        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(url, headers=self.headers, json=payload) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return {"success": True}
                    return {"success": False, "error": data.get("message")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def build_article_content(self, article: Dict) -> str:
        """构建文章内容"""
        content = f"""# {article.get('title', '')}

> 来源: [{article.get('account_name', '')}]({article.get('url', '')})
> 发布时间: {article.get('publish_time', '')}
> 阅读量: {article.get('read_count', 0)} | 点赞: {article.get('like_count', 0)}

---

{article.get('content', '')}

---

*同步时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        return content


class AirtableClient:
    """Airtable API 客户端"""

    API_BASE = "https://api.airtable.com/v0"

    def __init__(self, token: str, base_id: str):
        self.token = token
        self.base_id = base_id
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    async def create_record(self, table_name: str, fields: Dict) -> Dict:
        """创建记录"""
        if not HAS_AIOHTTP:
            return {"success": False, "error": "需要安装 aiohttp"}

        url = f"{self.API_BASE}/{self.base_id}/{table_name}"
        payload = {"fields": fields}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return {"success": True, "record_id": data.get("id")}
                    return {"success": False, "error": str(data.get("error"))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def build_article_fields(self, article: Dict) -> Dict:
        """构建文章字段"""
        return {
            "标题": article.get("title", ""),
            "公众号": article.get("account_name", ""),
            "链接": article.get("url", ""),
            "发布日期": article.get("publish_time", ""),
            "阅读量": article.get("read_count", 0),
            "点赞数": article.get("like_count", 0),
            "标签": ", ".join(article.get("tags", [])),
            "正文": article.get("content", "")[:5000]  # Airtable 限制
        }


class IntegrationManager:
    """集成管理器"""

    def __init__(self):
        self.configs: Dict[str, SyncConfig] = {}
        self._load_configs()

    def _load_configs(self):
        """加载配置"""
        config_path = os.path.expanduser("~/.wechat-scraper/integrations.json")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                data = json.load(f)
                for name, cfg in data.items():
                    self.configs[name] = SyncConfig(
                        provider=cfg.get("provider"),
                        name=name,
                        config=cfg.get("config", {}),
                        enabled=cfg.get("enabled", True),
                        last_sync=cfg.get("last_sync", ""),
                        sync_count=cfg.get("sync_count", 0)
                    )

    def _save_configs(self):
        """保存配置"""
        config_path = os.path.expanduser("~/.wechat-scraper/integrations.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        data = {}
        for name, cfg in self.configs.items():
            data[name] = {
                "provider": cfg.provider,
                "config": cfg.config,
                "enabled": cfg.enabled,
                "last_sync": cfg.last_sync,
                "sync_count": cfg.sync_count
            }

        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add_config(self, name: str, provider: str, config: Dict) -> SyncConfig:
        """添加配置"""
        cfg = SyncConfig(
            provider=provider,
            name=name,
            config=config
        )
        self.configs[name] = cfg
        self._save_configs()
        return cfg

    def remove_config(self, name: str) -> bool:
        """移除配置"""
        if name in self.configs:
            del self.configs[name]
            self._save_configs()
            return True
        return False

    async def sync_article(self, config_name: str, article: Dict) -> Dict:
        """同步文章到第三方"""
        cfg = self.configs.get(config_name)
        if not cfg or not cfg.enabled:
            return {"success": False, "error": "配置不存在或已禁用"}

        result = {"success": False}

        if cfg.provider == "notion":
            client = NotionClient(cfg.config.get("token"))
            properties = client.build_article_properties(article)
            result = await client.create_page(
                cfg.config.get("database_id"),
                properties
            )

        elif cfg.provider == "yuque":
            client = YuqueClient(cfg.config.get("token"))
            content = client.build_article_content(article)
            result = await client.create_doc(
                cfg.config.get("repo_slug"),
                article.get("title", "Untitled"),
                content
            )

        elif cfg.provider == "airtable":
            client = AirtableClient(
                cfg.config.get("token"),
                cfg.config.get("base_id")
            )
            fields = client.build_article_fields(article)
            result = await client.create_record(
                cfg.config.get("table_name", "Articles"),
                fields
            )

        # 更新统计
        if result.get("success"):
            cfg.sync_count += 1
            cfg.last_sync = datetime.now().isoformat()
            self._save_configs()

        return result

    def list_configs(self) -> List[Dict]:
        """列出所有配置"""
        return [
            {
                "name": name,
                "provider": cfg.provider,
                "enabled": cfg.enabled,
                "last_sync": cfg.last_sync,
                "sync_count": cfg.sync_count
            }
            for name, cfg in self.configs.items()
        ]


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='第三方集成管理')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 添加配置
    add_parser = subparsers.add_parser('add', help='添加集成配置')
    add_parser.add_argument('--name', required=True)
    add_parser.add_argument('--provider', required=True, choices=['notion', 'yuque', 'airtable'])
    add_parser.add_argument('--token', required=True)
    add_parser.add_argument('--database', help='Notion database ID')
    add_parser.add_argument('--repo', help='语雀仓库 slug')
    add_parser.add_argument('--base', help='Airtable base ID')

    # 列出配置
    subparsers.add_parser('list', help='列出配置')

    # 测试同步
    test_parser = subparsers.add_parser('test', help='测试同步')
    test_parser.add_argument('--config', required=True)
    test_parser.add_argument('--title', default='测试文章')

    args = parser.parse_args()

    manager = IntegrationManager()

    if args.command == 'add':
        config = {"token": args.token}
        if args.database:
            config["database_id"] = args.database
        if args.repo:
            config["repo_slug"] = args.repo
        if args.base:
            config["base_id"] = args.base

        manager.add_config(args.name, args.provider, config)
        print(f"配置已添加: {args.name}")

    elif args.command == 'list':
        configs = manager.list_configs()
        print(f"\n集成配置 ({len(configs)}个):\n")
        for c in configs:
            status = "✅" if c['enabled'] else "⏸️"
            print(f"{status} {c['name']} ({c['provider']}) - 同步{c['sync_count']}次")

    elif args.command == 'test':
        article = {
            "title": args.title,
            "account_name": "测试公众号",
            "url": "https://mp.weixin.qq.com/s/test",
            "publish_time": datetime.now().isoformat(),
            "read_count": 1000,
            "like_count": 50,
            "tags": ["测试"],
            "content": "这是测试内容",
            "summary": "测试摘要"
        }

        result = asyncio.run(manager.sync_article(args.config, article))
        if result['success']:
            print(f"同步成功: {result}")
        else:
            print(f"同步失败: {result.get('error')}")


if __name__ == '__main__':
    main()
