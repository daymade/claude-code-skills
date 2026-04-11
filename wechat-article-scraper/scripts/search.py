#!/usr/bin/env python3
"""
搜狗微信搜索模块 - 通过关键词发现微信公众号文章

功能：
- 通过关键词搜索微信公众号文章
- 支持按时间筛选
- 提取文章元数据（标题、摘要、公众号、链接、时间）
- 导出为多种格式

注意：搜狗微信搜索有反爬机制，建议配合 router.py 使用

作者: Claude Code
版本: 2.0.0
"""

import sys
import re
import csv
import json
import time
import urllib.parse
import argparse
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class ArticleResult:
    """搜索结果文章"""
    title: str
    url: str
    abstract: str
    source_account: str  # 公众号名称
    publish_time: Optional[str] = None
    is_temporary_url: bool = True  # 搜狗链接有过期时间


class SogouWechatSearch:
    """搜狗微信搜索器"""

    BASE_URL = "https://weixin.sogou.com/weixin"

    def __init__(self, delay: float = 2.0):
        self.delay = delay  # 请求间隔，避免风控
        self.session = None

    def _get_session(self):
        """获取配置好的 session"""
        if self.session is None:
            import requests
            from bs4 import BeautifulSoup

            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': 'https://weixin.sogou.com/',
            })
        return self.session

    def search(
        self,
        keyword: str,
        num_results: int = 10,
        time_filter: Optional[str] = None
    ) -> List[ArticleResult]:
        """
        搜索微信公众号文章

        Args:
            keyword: 搜索关键词
            num_results: 需要的结果数量（默认10条）
            time_filter: 时间筛选
                - None: 全部时间
                - 'day': 一天内
                - 'week': 一周内
                - 'month': 一月内
                - 'year': 一年内

        Returns:
            List[ArticleResult]: 搜索结果列表
        """
        results = []
        page = 1

        while len(results) < num_results:
            page_results = self._search_page(keyword, page, time_filter)

            if not page_results:
                break

            results.extend(page_results)

            # 检查是否还有下一页
            if len(page_results) < 10:  # 每页通常10条
                break

            page += 1
            time.sleep(self.delay)

        return results[:num_results]

    def _search_page(
        self,
        keyword: str,
        page: int = 1,
        time_filter: Optional[str] = None
    ) -> List[ArticleResult]:
        """搜索单页结果"""
        import requests
        from bs4 import BeautifulSoup

        # 构建参数
        params = {
            'type': '2',  # 2=文章搜索
            'query': keyword,
            'page': page,
        }

        # 时间筛选参数
        time_map = {
            'day': '1',
            'week': '2',
            'month': '3',
            'year': '4',
        }
        if time_filter and time_filter in time_map:
            params['tsn'] = time_map[time_filter]

        try:
            session = self._get_session()
            resp = session.get(
                self.BASE_URL,
                params=params,
                timeout=15
            )
            resp.raise_for_status()

            # 检查是否触发验证码
            if '请输入验证码' in resp.text or '验证码' in resp.text:
                print("警告: 触发搜狗验证码，请稍后重试或使用浏览器模式", file=sys.stderr)
                return []

            return self._parse_results(resp.text)

        except Exception as e:
            print(f"搜索失败: {e}", file=sys.stderr)
            return []

    def _parse_results(self, html: str) -> List[ArticleResult]:
        """解析搜索结果 HTML"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'lxml')
        results = []

        # 搜索结果在 .news-list > li 中
        for li in soup.select('.news-list li'):
            try:
                # 标题和链接
                title_tag = li.select_one('h3 a')
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                href = title_tag.get('href', '')

                # 处理搜狗链接跳转
                url = self._resolve_wechat_url(href)

                # 摘要
                abstract_tag = li.select_one('.txt-info')
                abstract = abstract_tag.get_text(strip=True) if abstract_tag else ""

                # 公众号
                account_tag = li.select_one('.account')
                source_account = account_tag.get_text(strip=True) if account_tag else ""

                # 时间
                time_tag = li.select_one('.s2')
                publish_time = None
                if time_tag:
                    time_text = time_tag.get_text(strip=True)
                    publish_time = self._parse_time(time_text)

                results.append(ArticleResult(
                    title=title,
                    url=url,
                    abstract=abstract,
                    source_account=source_account,
                    publish_time=publish_time,
                    is_temporary_url=href.startswith('/')
                ))

            except Exception as e:
                continue

        return results

    def _resolve_wechat_url(self, href: str) -> str:
        """
        解析真实的微信文章链接

        搜狗返回的链接是跳转链接，需要解析或直接访问获取真实 URL
        """
        if href.startswith('http'):
            return href

        # 相对链接，拼接域名
        if href.startswith('/'):
            return f"https://weixin.sogou.com{href}"

        return href

    def _parse_time(self, time_text: str) -> Optional[str]:
        """解析时间文本为 ISO 格式"""
        try:
            # 搜狗时间格式: "3天前", "2025-04-10", "今天"
            if '天前' in time_text:
                days = int(time_text.replace('天前', ''))
                from datetime import timedelta
                dt = datetime.now() - timedelta(days=days)
                return dt.strftime('%Y-%m-%d')
            elif time_text == '今天':
                return datetime.now().strftime('%Y-%m-%d')
            elif re.match(r'\d{4}-\d{2}-\d{2}', time_text):
                return time_text

        except Exception:
            pass

        return None

    def get_real_wechat_url(self, sogou_url: str) -> Optional[str]:
        """
        获取真实的微信文章 URL

        搜狗链接会过期，需要获取真实链接长期保存
        """
        import requests

        try:
            session = self._get_session()
            resp = session.head(sogou_url, allow_redirects=True, timeout=10)
            final_url = resp.url

            # 清理 URL 参数
            if 'mp.weixin.qq.com' in final_url:
                # 保留必要参数
                parsed = urllib.parse.urlparse(final_url)
                params = urllib.parse.parse_qs(parsed.query)

                # 保留 biz, mid, idx, sn
                essential = {}
                for k in ['__biz', 'mid', 'idx', 'sn']:
                    if k in params:
                        essential[k] = params[k][0]

                if essential:
                    query = urllib.parse.urlencode(essential)
                    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query}"

            return final_url

        except Exception as e:
            print(f"获取真实链接失败: {e}", file=sys.stderr)
            return None


def format_output(results: List[ArticleResult], fmt: str = 'table') -> str:
    """格式化输出搜索结果"""

    if fmt == 'json':
        return json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2)

    elif fmt == 'csv':
        # 使用 csv 模块正确处理转义和注入攻击
        import io
        output = io.StringIO()
        writer = csv.writer(output, lineterminator='\n')
        # 写入表头
        writer.writerow(['标题', '公众号', '发布时间', '链接', '摘要'])
        # 写入数据行
        for r in results:
            writer.writerow([
                r.title,
                r.source_account,
                r.publish_time or '',
                r.url,
                r.abstract
            ])
        return output.getvalue()

    elif fmt == 'markdown':
        lines = ['# 微信文章搜索结果\n']
        for i, r in enumerate(results, 1):
            lines.append(f"## {i}. {r.title}")
            lines.append(f"**公众号**: {r.source_account}")
            if r.publish_time:
                lines.append(f"**发布时间**: {r.publish_time}")
            lines.append(f"**链接**: {r.url}")
            lines.append(f"\n{r.abstract}\n")
        return '\n'.join(lines)

    else:  # table
        lines = ['搜索结果:', '-' * 80]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.title}")
            lines.append(f"   公众号: {r.source_account} | 时间: {r.publish_time or '未知'}")
            lines.append(f"   链接: {r.url}")
            lines.append(f"   摘要: {r.abstract[:80]}...")
            lines.append('')
        return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='搜狗微信文章搜索'
    )
    parser.add_argument(
        'keyword',
        help='搜索关键词'
    )
    parser.add_argument(
        '-n', '--num',
        type=int,
        default=10,
        help='结果数量 (默认: 10)'
    )
    parser.add_argument(
        '-t', '--time',
        choices=['day', 'week', 'month', 'year'],
        help='时间筛选: day=一天内, week=一周内, month=一月内, year=一年内'
    )
    parser.add_argument(
        '-f', '--format',
        choices=['table', 'json', 'csv', 'markdown'],
        default='table',
        help='输出格式 (默认: table)'
    )
    parser.add_argument(
        '-o', '--output',
        help='输出文件路径'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=2.0,
        help='请求间隔秒数 (默认: 2.0)'
    )

    args = parser.parse_args()

    print(f"搜索: {args.keyword}", file=sys.stderr)

    searcher = SogouWechatSearch(delay=args.delay)
    results = searcher.search(
        keyword=args.keyword,
        num_results=args.num,
        time_filter=args.time
    )

    if not results:
        print("未找到结果", file=sys.stderr)
        sys.exit(1)

    output = format_output(results, args.format)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"结果已保存: {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
