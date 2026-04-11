#!/usr/bin/env python3
"""
微信公众号文章搜索 - 整合多源搜索能力

功能：
- 搜狗微信搜索（主源）
- miku-ai 蜘蛛搜索（备选）
- 智能时间解析（支持 timeConvert JS 函数）
- 结果去重
- 多格式导出

作者: Claude Code
版本: 2.1.0
"""

import sys
import re
import csv
import json
import time
import urllib.parse
import argparse
from typing import List, Dict, Optional, Set, Tuple
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


# 增强的 User-Agent 池（从竞品分析整合，但验证有效性存疑）
USER_AGENT_POOL = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
]


class SogouWechatSearch:
    """
    搜狗微信搜索器

    竞品分析关键发现（待验证）：
    1. jisu-wechat-article: 使用 timeConvert() 解析时间戳 - 需要验证是否更可靠
    2. wechat-articles-1.0.1: 使用 miku-ai 作为备选源 - 需要验证可用性
    3. 多 UA 轮换可能降低被封概率，但也可能增加特征识别
    """

    BASE_URL = "https://weixin.sogou.com/weixin"
    MIKU_BASE_URL = "https://www.miku-ai.com/api/v1/spider/wechat/search"

    def __init__(self, delay: float = 2.0, enable_fallback: bool = True):
        self.delay = delay  # 请求间隔，避免风控
        self.enable_fallback = enable_fallback  # 是否启用备选源
        self.session = None
        self._seen_results: Set[Tuple[str, str]] = set()  # 去重缓存

    def _get_session(self):
        """获取配置好的 session"""
        if self.session is None:
            import requests
            import random

            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': random.choice(USER_AGENT_POOL),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': 'https://weixin.sogou.com/',
            })
        return self.session

    def _parse_publish_time(self, time_text: str, html_context: str = '') -> Optional[str]:
        """
        解析发布时间 - 支持 sogou 的 timeConvert() JS 函数

        竞品 jisu-wechat-article 使用此方法，声称能获取更精确时间。
        但需注意：timeConvert 依赖 JavaScript 执行环境，服务端解析可能不完全。
        """
        if not time_text:
            return None

        time_text = time_text.strip()

        # 尝试从 html_context 中提取 timeConvert 时间戳
        # sogou 页面使用格式: <script>timeConvert(1234567890)</script>
        if html_context:
            # 寻找页面中的 timeConvert 函数调用
            pattern = r'timeConvert\s*\(\s*(\d{10,13})\s*\)'
            matches = re.findall(pattern, html_context)

            if matches:
                # 使用第一个匹配的时间戳（通常是文章发布时间）
                try:
                    ts = int(matches[0])
                    # 处理毫秒时间戳
                    if ts > 1000000000000:
                        ts = ts // 1000
                    dt = datetime.fromtimestamp(ts)
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, OSError):
                    pass

        # 原有解析逻辑作为 fallback
        return self._parse_time_fallback(time_text)

    def search(
        self,
        keyword: str,
        num_results: int = 10,
        time_filter: Optional[str] = None
    ) -> List[ArticleResult]:
        """
        搜索微信公众号文章

        策略:
        1. 优先搜狗搜索（数据最全）
        2. 搜狗失败/结果不足时尝试 miku-ai（备选）
        3. 结果自动去重

        Args:
            keyword: 搜索关键词
            num_results: 需要的结果数量（默认10条）
            time_filter: 时间筛选（仅搜狗支持，miku-ai 不支持）

        Returns:
            List[ArticleResult]: 搜索结果列表
        """
        results = []
        seen_count = 0

        # 尝试搜狗
        page = 1
        while len(results) < num_results:
            page_results = self._search_page(keyword, page, time_filter)

            if not page_results:
                break

            # 去重并添加
            for r in page_results:
                if not self._is_duplicate(r.title, r.url):
                    results.append(r)
                else:
                    seen_count += 1

            # 检查是否还有下一页
            if len(page_results) < 10:  # 每页通常10条
                break

            page += 1
            time.sleep(self.delay)

        # 如果搜狗结果不足且启用了 fallback，尝试 miku-ai
        if self.enable_fallback and len(results) < num_results:
            miku_results = self._search_miku(keyword, num_results - len(results))
            for r in miku_results:
                if not self._is_duplicate(r.title, r.url):
                    results.append(r)
                else:
                    seen_count += 1

        if seen_count > 0:
            print(f"   去重过滤: {seen_count} 条重复结果", file=sys.stderr)

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
        """
        解析搜索结果 HTML

        支持两种解析策略：
        1. 标准选择器解析（主要）
        2. 备选解析（当标准选择器失败时）
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'lxml')
        results = []

        # 策略1: 标准选择器
        items = soup.select('.news-list li')

        # 策略2: 备选解析（如果标准选择器失败）
        if not items:
            items = self._parse_fallback(soup)

        for li in items:
            try:
                # 标题和链接
                title_tag = li.select_one('h3 a') or li.select_one('a[href*="/link?url="]')
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                href = title_tag.get('href', '')

                if not title or not href:
                    continue

                # 处理搜狗链接跳转
                url = self._resolve_wechat_url(href)

                # 摘要
                abstract_tag = li.select_one('.txt-info') or li.select_one('.abstract')
                abstract = abstract_tag.get_text(strip=True) if abstract_tag else ""

                # 公众号
                account_tag = li.select_one('.account') or li.select_one('.s1')
                source_account = account_tag.get_text(strip=True) if account_tag else ""

                # 时间 - 使用增强的解析器
                time_tag = li.select_one('.s2') or li.select_one('.time')
                publish_time = None
                if time_tag:
                    time_text = time_tag.get_text(strip=True)
                    # 传入整个 li 的 HTML 以提取 timeConvert
                    publish_time = self._parse_publish_time(time_text, str(li))

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

    def _parse_fallback(self, soup) -> List:
        """
        备选解析策略

        当 sogou 页面结构变化时，尝试更宽松的匹配。
        注意：此策略可能产生更多误匹配，仅作为最后手段。
        """
        # 尝试多种可能的选择器
        selectors = [
            '.result-list .result-item',
            '.results .item',
            '.search-list .search-item',
            '.news-list .news-item',
        ]

        for selector in selectors:
            items = soup.select(selector)
            if items:
                return items

        # 如果都失败，尝试模糊匹配
        # 寻找包含标题链接和公众号信息的容器
        fallback_items = []
        for a in soup.find_all('a', href=re.compile(r'/link\?url=')):
            parent = a.find_parent(['li', 'div', 'article'])
            if parent:
                fallback_items.append(parent)

        return fallback_items

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

    def _parse_time_fallback(self, time_text: str) -> Optional[str]:
        """原有时间解析作为 fallback"""
        try:
            # 搜狗时间格式: "3天前", "2025-04-10", "今天", "昨天"
            if '天前' in time_text:
                days = int(time_text.replace('天前', ''))
                from datetime import timedelta
                dt = datetime.now() - timedelta(days=days)
                return dt.strftime('%Y-%m-%d')
            elif time_text == '今天':
                return datetime.now().strftime('%Y-%m-%d')
            elif time_text == '昨天':
                from datetime import timedelta
                dt = datetime.now() - timedelta(days=1)
                return dt.strftime('%Y-%m-%d')
            elif re.match(r'\d{4}-\d{2}-\d{2}', time_text):
                return time_text

        except Exception:
            pass

        return None

    def _is_duplicate(self, title: str, url: str) -> bool:
        """
        检查是否重复结果

        使用 (title.lower(), url) 作为唯一键
        竞品使用此策略，但存在误判可能（相同标题不同内容的文章）
        """
        # 提取URL的核心部分用于去重（去除追踪参数）
        key_url = url.split('?')[0] if '?' in url else url
        key = (title.lower().strip(), key_url.lower().strip())

        if key in self._seen_results:
            return True

        self._seen_results.add(key)
        return False

    def resolve_real_url(self, sogou_url: str, timeout: float = 10.0, sleep_s: float = 0.2) -> Optional[str]:
        """
        解析搜狗中间链接为真实微信文章链接

        吸取 jisu-wechat-article 精华：
        1. 优先从 URL 参数提取真实链接（避免额外请求）
        2. 必要时发送 HEAD 请求跟随重定向
        3. 处理 antispider 拦截情况

        Args:
            sogou_url: 搜狗跳转链接 (如 https://weixin.sogou.com/link?url=...)
            timeout: 请求超时
            sleep_s: 请求后等待时间（避免请求过快）

        Returns:
            Optional[str]: 真实微信文章链接，或 None 如果解析失败
        """
        import requests
        import time

        # 步骤1: 尝试从 URL 参数直接提取真实链接
        real_from_param = self._extract_url_from_param(sogou_url)
        if real_from_param:
            return real_from_param

        # 步骤2: 发送请求获取重定向地址
        try:
            session = self._get_session()
            resp = session.head(
                sogou_url,
                allow_redirects=False,  # 不自动跟随，手动处理
                timeout=timeout
            )

            # 等待一小段时间（避免请求过快触发风控）
            time.sleep(max(0.0, sleep_s))

            # 从 Location header 获取真实链接
            loc = resp.headers.get('Location', '').strip()
            if not loc:
                # 如果没有 Location，尝试 GET 请求
                resp_get = session.get(sogou_url, allow_redirects=False, timeout=timeout)
                loc = resp_get.headers.get('Location', '').strip()

            if loc:
                # 处理相对链接
                if loc.startswith('/'):
                    loc = f"https://weixin.sogou.com{loc}"

                # 再次尝试从参数提取（有些重定向后仍有中间链接）
                real = self._extract_url_from_param(loc) or loc
                return self._normalize_url(real)

        except Exception as e:
            print(f"解析真实链接失败: {e}", file=sys.stderr)

        return None

    def _extract_url_from_param(self, url: str) -> Optional[str]:
        """
        从 URL 参数中提取真实微信链接

        搜狗链接格式: /link?url=xxx&target=yyy
        """
        if not url:
            return None

        try:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)

            # 可能的参数名（按优先级）
            for key in ('url', 'target', 'target_url', 'link'):
                if key in qs and qs[key]:
                    value = qs[key][0].strip()
                    if value.startswith('http://') or value.startswith('https://'):
                        return value

            # 处理搜狗特定的编码格式
            if 'url' in parsed.path:
                # 尝试从路径中提取
                match = re.search(r'url=([^&]+)', parsed.query)
                if match:
                    decoded = urllib.parse.unquote(match.group(1))
                    if decoded.startswith('http'):
                        return decoded

        except Exception:
            pass

        return None

    def _normalize_url(self, url: str) -> str:
        """规范化 URL"""
        url = url.strip()
        if url.startswith('/'):
            return f"https://weixin.sogou.com{url}"
        return url

    def is_antispider_url(self, url: str) -> bool:
        """检查 URL 是否为风控拦截链接"""
        s = (url or '').lower()
        return '/antispider/' in s or 'antispider?' in s

    def get_real_wechat_url(self, sogou_url: str) -> Optional[str]:
        """
        获取真实的微信文章 URL (向后兼容的别名)

        已弃用: 请使用 resolve_real_url()
        """
        return self.resolve_real_url(sogou_url)

    def _search_miku(self, keyword: str, num_results: int = 10) -> List[ArticleResult]:
        """
        使用 miku-ai 蜘蛛搜索作为备选

        竞品 wechat-articles-1.0.1 使用此源，声称稳定性更好。
        警告：此 API 可能随时变更或失效，需实际测试验证。

        Args:
            keyword: 搜索关键词
            num_results: 需要的结果数量

        Returns:
            List[ArticleResult]: 搜索结果列表
        """
        import requests
        import random

        try:
            params = {
                'query': keyword,
                'page': 1,
                'per_page': num_results,
            }

            headers = {
                'User-Agent': random.choice(USER_AGENT_POOL),
                'Accept': 'application/json',
            }

            resp = requests.get(
                self.MIKU_BASE_URL,
                params=params,
                headers=headers,
                timeout=15
            )
            resp.raise_for_status()

            data = resp.json()
            results = []

            # miku-ai 返回格式需验证，这里基于竞品的推测实现
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get('data', data.get('results', data.get('list', [])))
            else:
                items = []

            for item in items[:num_results]:
                if isinstance(item, dict):
                    title = item.get('title', '')
                    url = item.get('url', item.get('link', ''))
                    abstract = item.get('abstract', item.get('summary', item.get('content', '')))
                    account = item.get('account', item.get('wechat_name', item.get('source', '')))
                    pub_time = item.get('publish_time', item.get('time', ''))

                    if title and url:
                        results.append(ArticleResult(
                            title=title,
                            url=url,
                            abstract=abstract,
                            source_account=account,
                            publish_time=pub_time,
                            is_temporary_url=False  # miku 直接返回微信链接
                        ))

            if results:
                print(f"   miku-ai 备选: 找到 {len(results)} 条结果", file=sys.stderr)

            return results

        except Exception as e:
            # miku-ai 失败静默处理，不干扰主流程
            return []


def resolve_all_urls(results: List[ArticleResult], searcher: SogouWechatSearch, delay: float = 0.5) -> List[ArticleResult]:
    """
    批量解析搜索结果中的搜狗链接为真实微信链接

    Args:
        results: 搜索结果列表
        searcher: 搜索器实例
        delay: 解析间隔（避免风控）

    Returns:
        List[ArticleResult]: 更新后的结果列表
    """
    import time

    resolved_count = 0
    for i, r in enumerate(results):
        if r.is_temporary_url and 'weixin.sogou.com' in r.url:
            print(f"   解析 [{i+1}/{len(results)}]: {r.url[:60]}...", file=sys.stderr)
            real_url = searcher.resolve_real_url(r.url)
            if real_url and not searcher.is_antispider_url(real_url):
                r.url = real_url
                r.is_temporary_url = False
                resolved_count += 1
            else:
                print(f"      解析失败或触发风控，保留原链接", file=sys.stderr)
            time.sleep(delay)

    if resolved_count > 0:
        print(f"   成功解析 {resolved_count}/{len(results)} 条真实链接", file=sys.stderr)

    return results


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
        description='微信公众号文章搜索 v2.2 - 支持搜狗 + miku-ai 双源',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "人工智能" -n 20
  %(prog)s "新能源汽车" -t week -f markdown
  %(prog)s "大模型" --resolve-urls  # 解析真实微信链接
  %(prog)s "大模型" --no-fallback  # 禁用 miku-ai 备选

时间筛选仅搜狗支持，miku-ai 会忽略此参数。
"""
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
    parser.add_argument(
        '--no-fallback',
        action='store_true',
        help='禁用 miku-ai 备选搜索'
    )
    parser.add_argument(
        '-r', '--resolve-urls',
        action='store_true',
        help='解析搜狗链接为真实微信链接（需要额外请求）'
    )

    args = parser.parse_args()

    print(f"搜索: {args.keyword}", file=sys.stderr)

    searcher = SogouWechatSearch(
        delay=args.delay,
        enable_fallback=not args.no_fallback
    )
    results = searcher.search(
        keyword=args.keyword,
        num_results=args.num,
        time_filter=args.time
    )

    if not results:
        print("未找到结果", file=sys.stderr)
        sys.exit(1)

    # 解析真实链接（如果启用）
    if args.resolve_urls:
        print("开始解析真实微信链接...", file=sys.stderr)
        results = resolve_all_urls(results, searcher, delay=0.5)

    output = format_output(results, args.format)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"结果已保存: {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
