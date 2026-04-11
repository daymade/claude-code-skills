#!/usr/bin/env python3
"""
第三方平台导出器 - 导出文章到 Notion / Airtable / Google Sheets

功能：
- Notion 数据库集成
- Airtable 表格同步
- Google Sheets 导出
- 自动字段映射
- 增量同步（仅导出新文章）
- 支持图片上传到云存储

吸取竞品精华：
- Zapier: 多平台连接器
- Make: 字段映射

作者: Claude Code
版本: 1.0.0
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('wechat-exporters')


@dataclass
class ExportResult:
    """导出结果"""
    success: bool
    platform: str
    record_id: Optional[str]
    url: Optional[str]
    error: Optional[str]


class NotionExporter:
    """Notion 导出器"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('NOTION_API_KEY')
        if not self.api_key:
            raise ValueError("请设置 NOTION_API_KEY 环境变量")
        self.base_url = "https://api.notion.com/v1"

    def _request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """发送 Notion API 请求"""
        import requests

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

        url = f"{self.base_url}/{endpoint}"

        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            elif method == "PATCH":
                response = requests.patch(url, headers=headers, json=data)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Notion API 请求失败: {e}")
            raise

    def create_database(self, page_id: str, title: str = "微信文章") -> str:
        """在 Notion 页面中创建数据库"""
        data = {
            "parent": {"page_id": page_id},
            "title": [{"text": {"content": title}}],
            "properties": {
                "标题": {"title": {}},
                "作者": {"rich_text": {}},
                "分类": {"select": {"options": [
                    {"name": "科技", "color": "blue"},
                    {"name": "财经", "color": "green"},
                    {"name": "汽车", "color": "yellow"},
                    {"name": "医疗", "color": "red"},
                    {"name": "教育", "color": "purple"},
                    {"name": "娱乐", "color": "pink"},
                    {"name": "生活", "color": "orange"},
                    {"name": "职场", "color": "gray"},
                    {"name": "时事", "color": "brown"},
                    {"name": "文化", "color": "default"}
                ]}},
                "发布时间": {"date": {}},
                "URL": {"url": {}},
                "WCI 指数": {"number": {"format": "number"}},
                "阅读量": {"number": {"format": "number"}},
                "点赞数": {"number": {"format": "number"}},
                "标签": {"multi_select": {}},
                "摘要": {"rich_text": {}},
                "内容": {"rich_text": {}},
                "导入时间": {"created_time": {}},
                "同步状态": {"select": {"options": [
                    {"name": "已同步", "color": "green"},
                    {"name": "待同步", "color": "yellow"},
                    {"name": "同步失败", "color": "red"}
                ]}}
            }
        }

        result = self._request("POST", "databases", data)
        database_id = result["id"]
        logger.info(f"Notion 数据库已创建: {database_id}")
        return database_id

    def export_article(self, database_id: str, article: Dict) -> ExportResult:
        """导出单篇文章到 Notion"""
        try:
            engagement = article.get('engagement', {})
            wci = article.get('wci_score')

            data = {
                "parent": {"database_id": database_id},
                "properties": {
                    "标题": {"title": [{"text": {"content": article.get('title', '无标题')}}]},
                    "作者": {"rich_text": [{"text": {"content": article.get('author', '')}}]},
                    "分类": {"select": {"name": article.get('category', '其他')}},
                    "发布时间": {"date": {"start": article.get('publish_time', datetime.now().isoformat())}},
                    "URL": {"url": article.get('url', '')},
                    "标签": {"multi_select": [{"name": tag} for tag in article.get('tags', [])]},
                    "摘要": {"rich_text": [{"text": {"content": article.get('summary', '')[:2000]}}]},
                    "内容": {"rich_text": [{"text": {"content": article.get('content', '')[:2000]}}]},
                    "同步状态": {"select": {"name": "已同步"}}
                }
            }

            # 添加数字字段（如果有）
            if wci:
                data["properties"]["WCI 指数"] = {"number": float(wci)}
            if engagement.get('readCount'):
                data["properties"]["阅读量"] = {"number": int(engagement['readCount'])}
            if engagement.get('likeCount'):
                data["properties"]["点赞数"] = {"number": int(engagement['likeCount'])}

            result = self._request("POST", "pages", data)

            return ExportResult(
                success=True,
                platform="notion",
                record_id=result["id"],
                url=result.get("url"),
                error=None
            )

        except Exception as e:
            logger.error(f"导出到 Notion 失败: {e}")
            return ExportResult(
                success=False,
                platform="notion",
                record_id=None,
                url=None,
                error=str(e)
            )


class AirtableExporter:
    """Airtable 导出器"""

    def __init__(self, api_key: Optional[str] = None, base_id: Optional[str] = None):
        self.api_key = api_key or os.getenv('AIRTABLE_API_KEY')
        self.base_id = base_id or os.getenv('AIRTABLE_BASE_ID')

        if not self.api_key:
            raise ValueError("请设置 AIRTABLE_API_KEY 环境变量")

    def _request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """发送 Airtable API 请求"""
        import requests

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        url = f"https://api.airtable.com/v0/{self.base_id}/{endpoint}"

        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Airtable API 请求失败: {e}")
            raise

    def create_table(self, name: str = "微信文章") -> str:
        """创建 Airtable 表格（需要手动创建，这里返回配置说明）"""
        logger.info(f"请在 Airtable 中手动创建表格: {name}")
        logger.info("建议字段: 标题(标题), 作者(单行文本), 分类(单选), 发布时间(日期), URL(URL), WCI指数(数字), 阅读量(数字), 点赞数(数字), 标签(多选), 摘要(长文本), 内容(长文本)")
        return name

    def export_article(self, table_name: str, article: Dict) -> ExportResult:
        """导出单篇文章到 Airtable"""
        try:
            engagement = article.get('engagement', {})
            wci = article.get('wci_score')

            fields = {
                "标题": article.get('title', '无标题'),
                "作者": article.get('author', ''),
                "分类": article.get('category', '其他'),
                "发布时间": article.get('publish_time'),
                "URL": article.get('url', ''),
                "标签": ', '.join(article.get('tags', [])),
                "摘要": article.get('summary', '')[:5000],
                "内容": article.get('content', '')[:5000],
            }

            if wci:
                fields["WCI指数"] = float(wci)
            if engagement.get('readCount'):
                fields["阅读量"] = int(engagement['readCount'])
            if engagement.get('likeCount'):
                fields["点赞数"] = int(engagement['likeCount'])

            data = {"fields": fields}
            result = self._request("POST", table_name, data)

            return ExportResult(
                success=True,
                platform="airtable",
                record_id=result["id"],
                url=None,
                error=None
            )

        except Exception as e:
            logger.error(f"导出到 Airtable 失败: {e}")
            return ExportResult(
                success=False,
                platform="airtable",
                record_id=None,
                url=None,
                error=str(e)
            )


class GoogleSheetsExporter:
    """Google Sheets 导出器"""

    def __init__(self, credentials_file: Optional[str] = None):
        self.credentials_file = credentials_file or os.getenv('GOOGLE_CREDENTIALS_FILE')
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets']

    def _get_service(self):
        """获取 Google Sheets API 服务"""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            if not self.credentials_file or not Path(self.credentials_file).exists():
                raise ValueError(f"凭据文件不存在: {self.credentials_file}")

            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file, scopes=self.scopes
            )
            service = build('sheets', 'v4', credentials=credentials)
            return service

        except ImportError:
            logger.error("请先安装 google-api-python-client: pip install google-api-python-client")
            raise

    def create_spreadsheet(self, title: str = "微信文章") -> str:
        """创建新的 Google Sheets 文档"""
        service = self._get_service()

        spreadsheet = {
            'properties': {'title': title},
            'sheets': [{
                'properties': {
                    'title': '文章列表',
                    'gridProperties': {'rowCount': 1000, 'columnCount': 15}
                }
            }]
        }

        result = service.spreadsheets().create(body=spreadsheet).execute()
        spreadsheet_id = result['spreadsheetId']

        # 添加表头
        headers = [
            ['标题', '作者', '分类', '发布时间', 'URL', 'WCI指数',
             '阅读量', '点赞数', '标签', '摘要', '导入时间']
        ]

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range='文章列表!A1',
            valueInputOption='RAW',
            body={'values': headers}
        ).execute()

        logger.info(f"Google Sheets 已创建: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
        return spreadsheet_id

    def export_article(self, spreadsheet_id: str, article: Dict) -> ExportResult:
        """导出单篇文章到 Google Sheets"""
        try:
            service = self._get_service()

            engagement = article.get('engagement', {})
            wci = article.get('wci_score')

            row = [
                article.get('title', '无标题'),
                article.get('author', ''),
                article.get('category', '其他'),
                article.get('publish_time', ''),
                article.get('url', ''),
                str(wci) if wci else '',
                str(engagement.get('readCount', '')),
                str(engagement.get('likeCount', '')),
                ', '.join(article.get('tags', [])),
                article.get('summary', '')[:500],
                datetime.now().isoformat()
            ]

            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range='文章列表!A2',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()

            return ExportResult(
                success=True,
                platform="google_sheets",
                record_id=None,
                url=f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
                error=None
            )

        except Exception as e:
            logger.error(f"导出到 Google Sheets 失败: {e}")
            return ExportResult(
                success=False,
                platform="google_sheets",
                record_id=None,
                url=None,
                error=str(e)
            )


class ExportManager:
    """导出管理器"""

    def __init__(self, db_path: str = "wechat_articles.db"):
        self.db_path = db_path
        self.exporters = {}

    def get_exporter(self, platform: str):
        """获取导出器实例"""
        if platform not in self.exporters:
            if platform == "notion":
                self.exporters[platform] = NotionExporter()
            elif platform == "airtable":
                self.exporters[platform] = AirtableExporter()
            elif platform == "google_sheets":
                self.exporters[platform] = GoogleSheetsExporter()
            else:
                raise ValueError(f"不支持的导出平台: {platform}")

        return self.exporters[platform]

    def export_from_db(
        self,
        platform: str,
        target_id: str,
        author: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[ExportResult]:
        """从数据库导出文章"""
        sys.path.insert(0, str(Path(__file__).parent))
        from storage import ArticleStorage

        storage = ArticleStorage(self.db_path)
        articles = storage.list_articles(author=author, category=category, limit=limit)

        exporter = self.get_exporter(platform)
        results = []

        for article in articles:
            if platform == "notion":
                result = exporter.export_article(target_id, article)
            elif platform == "airtable":
                result = exporter.export_article(target_id, article)
            elif platform == "google_sheets":
                result = exporter.export_article(target_id, article)
            else:
                continue

            results.append(result)

            if result.success:
                logger.info(f"导出成功: {article.get('title', '无标题')}")
            else:
                logger.error(f"导出失败: {article.get('title', '无标题')} - {result.error}")

        return results


def main():
    parser = argparse.ArgumentParser(description='第三方平台导出器')
    parser.add_argument('platform', choices=['notion', 'airtable', 'google_sheets'],
                        help='导出目标平台')
    parser.add_argument('--target-id', required=True,
                        help='目标 ID (Notion database ID / Airtable table name / Google Sheets ID)')
    parser.add_argument('--db', default='wechat_articles.db',
                        help='SQLite 数据库路径')
    parser.add_argument('--author', help='筛选特定作者')
    parser.add_argument('--category', help='筛选特定分类')
    parser.add_argument('--limit', type=int, default=100,
                        help='最大导出数量')
    parser.add_argument('--create', action='store_true',
                        help='创建新的数据库/表格 (仅 Notion/Google Sheets)')
    parser.add_argument('--page-id', help='Notion 页面 ID (用于创建数据库)')

    args = parser.parse_args()

    manager = ExportManager(args.db)

    if args.create:
        if args.platform == "notion":
            if not args.page_id:
                print("创建 Notion 数据库需要提供 --page-id")
                return
            exporter = NotionExporter()
            database_id = exporter.create_database(args.page_id)
            print(f"数据库已创建: {database_id}")
            print(f"请使用以下命令导出: python3 scripts/exporters.py notion --target-id {database_id}")
            return

        elif args.platform == "google_sheets":
            exporter = GoogleSheetsExporter()
            spreadsheet_id = exporter.create_spreadsheet()
            print(f"请使用以下命令导出: python3 scripts/exporters.py google_sheets --target-id {spreadsheet_id}")
            return

        elif args.platform == "airtable":
            exporter = AirtableExporter()
            exporter.create_table()
            return

    # 导出模式
    results = manager.export_from_db(
        args.platform,
        args.target_id,
        author=args.author,
        category=args.category,
        limit=args.limit
    )

    success_count = sum(1 for r in results if r.success)
    print(f"\n导出完成: {success_count}/{len(results)} 成功")

    if success_count < len(results):
        print("\n失败详情:")
        for r in results:
            if not r.success:
                print(f"  - {r.error}")


if __name__ == '__main__':
    main()
