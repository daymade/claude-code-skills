#!/usr/bin/env python3
"""
WeChat Article Scraper MCP Server

MCP (Model Context Protocol) 服务器实现，允许 Claude Desktop 等客户端
直接调用微信文章抓取功能。

功能：
- 作为 MCP 服务器运行，通过 stdio 通信
- 提供 read_wechat_article 工具
- 返回结构化 JSON 结果

作者: Claude Code
版本: 1.0.0
"""

import sys
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

# 配置日志到 stderr，避免污染 stdout (MCP 通信)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger('wechat-mcp')


class MCPServer:
    """MCP 服务器实现"""

    def __init__(self):
        self.tools = {
            'read_wechat_article': self.read_wechat_article,
            'search_wechat_articles': self.search_wechat_articles,
            'search_wechat_accounts': self.search_wechat_accounts,
        }

    def send_message(self, message: Dict[str, Any]):
        """发送 MCP 消息到 stdout"""
        json_str = json.dumps(message, ensure_ascii=False)
        print(json_str, flush=True)
        logger.debug(f"Sent: {json_str[:200]}...")

    def read_message(self) -> Optional[Dict[str, Any]]:
        """从 stdin 读取 MCP 消息"""
        try:
            line = sys.stdin.readline()
            if not line:
                return None
            return json.loads(line.strip())
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return None
        except Exception as e:
            logger.error(f"Read error: {e}")
            return None

    def handle_initialize(self, params: Dict) -> Dict:
        """处理 MCP initialize 请求"""
        client_info = params.get('clientInfo', {})
        logger.info(f"Client connected: {client_info.get('name')} {client_info.get('version')}")

        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "wechat-article-scraper-mcp",
                "version": "3.10.0"
            }
        }

    def handle_tools_list(self) -> Dict:
        """返回可用工具列表"""
        return {
            "tools": [
                {
                    "name": "read_wechat_article",
                    "description": "读取微信公众号文章内容，提取标题、作者、发布时间和正文",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "微信公众号文章 URL，必须以 https://mp.weixin.qq.com/s/ 开头"
                            },
                            "strategy": {
                                "type": "string",
                                "enum": ["fast", "adaptive", "stable", "reliable", "zero_dep", "jina_ai"],
                                "description": "抓取策略，默认自动选择"
                            },
                            "download_images": {
                                "type": "boolean",
                                "description": "是否下载图片到本地",
                                "default": False
                            },
                            "format": {
                                "type": "string",
                                "enum": ["markdown", "json", "html"],
                                "description": "输出格式",
                                "default": "markdown"
                            }
                        },
                        "required": ["url"]
                    }
                },
                {
                    "name": "search_wechat_articles",
                    "description": "通过关键词搜索微信公众号文章",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "搜索关键词"
                            },
                            "num": {
                                "type": "integer",
                                "description": "结果数量",
                                "default": 10
                            },
                            "time_filter": {
                                "type": "string",
                                "enum": ["day", "week", "month", "year"],
                                "description": "时间筛选"
                            }
                        },
                        "required": ["keyword"]
                    }
                },
                {
                    "name": "search_wechat_accounts",
                    "description": "搜索微信公众号账号",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "公众号名称或关键词"
                            },
                            "num": {
                                "type": "integer",
                                "description": "结果数量",
                                "default": 10
                            }
                        },
                        "required": ["keyword"]
                    }
                }
            ]
        }

    def read_wechat_article(self, params: Dict) -> Dict:
        """读取微信文章工具"""
        url = params.get('url', '')
        strategy = params.get('strategy')
        download_images = params.get('download_images', False)
        output_format = params.get('format', 'markdown')

        # 验证 URL
        if not url.startswith('https://mp.weixin.qq.com/s/'):
            return {
                "success": False,
                "error": "Invalid URL. Must start with https://mp.weixin.qq.com/s/"
            }

        try:
            # 导入 scraper 模块
            from scripts.scraper import scrape_article

            result = scrape_article(
                url=url,
                strategy=strategy,
                download_images=download_images,
                output_format=output_format
            )

            if result.get('success'):
                return {
                    "success": True,
                    "title": result.get('title'),
                    "author": result.get('author'),
                    "content_status": result.get('content_status'),
                    "strategy": result.get('strategy'),
                    "output_path": result.get('output_path'),
                    "image_count": result.get('image_count'),
                    "quality": result.get('quality')
                }
            else:
                return {
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "content_status": result.get('content_status')
                }

        except Exception as e:
            logger.error(f"Error reading article: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def search_wechat_articles(self, params: Dict) -> Dict:
        """搜索微信文章工具"""
        keyword = params.get('keyword', '')
        num = params.get('num', 10)
        time_filter = params.get('time_filter')

        try:
            from scripts.search import SogouWechatSearch

            searcher = SogouWechatSearch(delay=2.0)
            results = searcher.search(keyword=keyword, num_results=num, time_filter=time_filter)

            articles = [
                {
                    "title": r.title,
                    "url": r.url,
                    "source_account": r.source_account,
                    "publish_time": r.publish_time,
                    "abstract": r.abstract
                }
                for r in results
            ]

            return {
                "success": True,
                "keyword": keyword,
                "count": len(articles),
                "articles": articles
            }

        except Exception as e:
            logger.error(f"Error searching articles: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def search_wechat_accounts(self, params: Dict) -> Dict:
        """搜索微信公众号工具"""
        keyword = params.get('keyword', '')
        num = params.get('num', 10)

        try:
            from scripts.search import SogouWechatSearch

            searcher = SogouWechatSearch(delay=2.0)
            results = searcher.search_accounts(keyword=keyword, num_results=num)

            accounts = [
                {
                    "name": r.name,
                    "wechat_id": r.wechat_id,
                    "description": r.description,
                    "verification": r.verification,
                    "is_official": r.is_official
                }
                for r in results
            ]

            return {
                "success": True,
                "keyword": keyword,
                "count": len(accounts),
                "accounts": accounts
            }

        except Exception as e:
            logger.error(f"Error searching accounts: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def handle_tools_call(self, params: Dict) -> Dict:
        """处理工具调用"""
        tool_name = params.get('name', '')
        tool_params = params.get('arguments', {})

        logger.info(f"Tool call: {tool_name}")

        if tool_name in self.tools:
            try:
                result = self.tools[tool_name](tool_params)
                return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]}
            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                return {"content": [{"type": "text", "text": json.dumps({"error": str(e)}, ensure_ascii=False)}], "isError": True}
        else:
            return {"content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)}], "isError": True}

    def run(self):
        """运行 MCP 服务器"""
        logger.info("WeChat Article Scraper MCP Server starting...")

        while True:
            try:
                message = self.read_message()
                if message is None:
                    break

                method = message.get('method', '')
                msg_id = message.get('id')
                params = message.get('params', {})

                logger.debug(f"Received: {method}")

                if method == 'initialize':
                    result = self.handle_initialize(params)
                    self.send_message({"jsonrpc": "2.0", "id": msg_id, "result": result})

                elif method == 'initialized':
                    logger.info("MCP session initialized")

                elif method == 'tools/list':
                    result = self.handle_tools_list()
                    self.send_message({"jsonrpc": "2.0", "id": msg_id, "result": result})

                elif method == 'tools/call':
                    result = self.handle_tools_call(params)
                    self.send_message({"jsonrpc": "2.0", "id": msg_id, "result": result})

                elif method == 'ping':
                    self.send_message({"jsonrpc": "2.0", "id": msg_id, "result": {}})

                else:
                    logger.warning(f"Unknown method: {method}")
                    self.send_message({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"}
                    })

            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error: {e}")


def main():
    """主入口"""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
