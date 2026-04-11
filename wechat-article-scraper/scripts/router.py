#!/usr/bin/env python3
"""
智能策略路由器 - 自动选择最佳微信文章抓取策略

支持四种模式：
- fast: HTTP + BeautifulSoup (快速但可能被封)
- adaptive: Scrapling (自适应反爬，轻量稳定)
- stable: Playwright (稳定渲染)
- reliable: Chrome DevTools MCP (最可靠，配合 ?scene=1 可绕过登录)

自动检测可用策略并选择最佳方案，支持重试和 UA 轮换。
"""

import sys
import subprocess
import json
import random
import time
import re
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


class Strategy(Enum):
    """抓取策略枚举"""
    FAST = "fast"           # HTTP + BS4
    ADAPTIVE = "adaptive"   # Scrapling (新增)
    STABLE = "stable"       # Playwright
    RELIABLE = "reliable"   # Chrome DevTools MCP (配合 ?scene=1 可绕过登录)
    ZERO_DEP = "zero_dep"   # 纯标准库模式
    JINA_AI = "jina_ai"     # jina.ai 服务（最后的fallback）
    FAILED = "failed"       # 所有策略都失败


class ContentStatus(Enum):
    """内容抓取状态码"""
    OK = "ok"                    # 成功
    BLOCKED = "blocked"          # 被风控拦截
    NO_MP_URL = "no_mp_url"      # 不是有效的微信文章链接
    FETCH_ERROR = "fetch_error"  # 网络请求失败
    PARSE_EMPTY = "parse_empty"  # 解析结果为空
    NEED_MCP = "need_mcp"        # 需要 MCP 模式
    RATE_LIMITED = "rate_limited" # 触发频率限制


@dataclass
class StrategyResult:
    """策略执行结果"""
    strategy: Strategy
    success: bool
    content_status: ContentStatus
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    retry_count: int = 0


# User-Agent 轮换池
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
]


class StrategyRouter:
    """策略路由器 - 自动选择并执行最佳抓取策略

    吸取 camofox 精华：
    - 详细的 STOP_MARKERS 噪音标记
    - 日期正则提取发布时间
    - 更强的内容过滤
    """

    # 吸取 camofox 精华：噪音标记列表
    STOP_MARKERS = [
        '预览时标签不可点', '微信扫一扫 关注该公众号', '继续滑动看下一个',
        '轻触阅读原文', '当前内容可能存在未经审核', '写留言', '暂无留言',
        '已无更多数据', '选择留言身份', '选择互动身份', '确认提交投诉',
        '发消息', '微信扫一扫可打开此内容', '篇原创内容 公众号',
        '点击关注', '长按二维码关注', '赞赏', '喜欢作者',
        '推荐阅读', '相关阅读', '精选留言', '查看往期',
        '分享到朋友圈', '收藏', '在看', '点赞',
    ]

    # 吸取 camofox 精华：需要跳过的子串
    SKIP_SUBSTRINGS = [
        'Your browser does not support video tags', '观看更多', '继续观看',
        '分享视频', '倍速播放中', '切换到横屏模式', '退出全屏', '全屏',
        '关闭', '更多', '已关注', '关注', '赞', '推荐', '收藏',
        '视频详情', '写下你的评论', '知道了', '取消', '允许',
    ]

    # 吸取 camofox 精华：日期正则
    DATE_RE = re.compile(r'\d{4}年\d{1,2}月\d{1,2}(?:\s+\d{1,2}:\d{2})?')

    def __init__(self, max_retries: int = 3, retry_delay: float = 0.5):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.strategy_order = [
            Strategy.FAST,       # 先尝试快速模式
            Strategy.ADAPTIVE,   # 再尝试自适应模式
            Strategy.STABLE,     # 再尝试稳定模式
            Strategy.RELIABLE,   # 再使用可靠模式
            Strategy.ZERO_DEP,   # 使用零依赖模式
            Strategy.JINA_AI,    # 最后尝试 jina.ai 服务
        ]

    def detect_available_strategies(self) -> List[Strategy]:
        """检测当前环境支持的策略"""
        available = []

        # Fast 模式总是可用
        available.append(Strategy.FAST)

        # 检查 Adaptive 模式 (Scrapling)
        if self._check_scrapling():
            available.append(Strategy.ADAPTIVE)

        # 检查 Stable 模式 (Playwright)
        if self._check_playwright():
            available.append(Strategy.STABLE)

        # Reliable 模式总是可用（由调用方处理）
        available.append(Strategy.RELIABLE)

        # Zero-Dependency 模式总是可用（纯标准库）
        available.append(Strategy.ZERO_DEP)

        # Jina AI 模式总是可用（外部服务）
        available.append(Strategy.JINA_AI)

        return available

    def _check_scrapling(self) -> bool:
        """检查是否安装了 Scrapling"""
        try:
            subprocess.run(
                ["python3", "-c", "import scrapling"],
                capture_output=True,
                timeout=5
            )
            return True
        except Exception:
            return False

    def _check_playwright(self) -> bool:
        """检查是否安装了 Playwright"""
        try:
            subprocess.run(
                ["python3", "-c", "import playwright"],
                capture_output=True,
                timeout=5
            )
            return True
        except Exception:
            return False

    def _get_random_ua(self) -> str:
        """获取随机 User-Agent"""
        return random.choice(USER_AGENTS)

    def _validate_url(self, url: str) -> bool:
        """验证 URL 是否是允许的微信域名"""
        allowed_domains = ['mp.weixin.qq.com', 'weixin.qq.com']
        return any(domain in url for domain in allowed_domains)

    def route(
        self,
        url: str,
        prefer_strategy: Optional[Strategy] = None,
        enable_og_fallback: bool = True
    ) -> StrategyResult:
        """
        路由到最佳策略

        Args:
            url: 微信文章 URL
            prefer_strategy: 优先使用的策略（可选）
            enable_og_fallback: 启用 OG 元数据备选提取

        Returns:
            StrategyResult: 执行结果
        """
        # 验证 URL
        if not self._validate_url(url):
            return StrategyResult(
                strategy=Strategy.FAILED,
                success=False,
                content_status=ContentStatus.NO_MP_URL,
                error="不支持的 URL: 必须是微信文章链接 (mp.weixin.qq.com)"
            )

        strategies = self.detect_available_strategies()

        # 如果有优先策略且可用，优先使用
        if prefer_strategy and prefer_strategy in strategies:
            strategies = [prefer_strategy] + [s for s in strategies if s != prefer_strategy]

        # 按顺序尝试每种策略
        last_error = None
        for strategy in strategies:
            print(f"🔄 尝试策略: {strategy.value}...", file=sys.stderr)

            result = self._execute_with_retry(strategy, url, enable_og_fallback)

            if result.success:
                print(f"✅ 策略 {strategy.value} 成功", file=sys.stderr)
                return result
            else:
                print(f"❌ 策略 {strategy.value} 失败: {result.error}", file=sys.stderr)
                last_error = result.error

        # 所有策略都失败
        return StrategyResult(
            strategy=Strategy.FAILED,
            success=False,
            content_status=ContentStatus.FETCH_ERROR,
            error=f"所有抓取策略均失败: {last_error}"
        )

    def _execute_with_retry(
        self,
        strategy: Strategy,
        url: str,
        enable_og_fallback: bool
    ) -> StrategyResult:
        """带重试的策略执行"""
        last_error = None

        for attempt in range(self.max_retries):
            if attempt > 0:
                print(f"   重试 {attempt}/{self.max_retries}...", file=sys.stderr)
                time.sleep(self.retry_delay * (attempt + 1))  # 指数退避

            result = self._execute_strategy(strategy, url, enable_og_fallback)
            result.retry_count = attempt

            if result.success:
                return result

            # 某些错误不需要重试
            if result.content_status in [ContentStatus.NO_MP_URL, ContentStatus.PARSE_EMPTY]:
                return result

            last_error = result.error

        # 所有重试都失败
        return StrategyResult(
            strategy=strategy,
            success=False,
            content_status=ContentStatus.FETCH_ERROR,
            error=f"重试 {self.max_retries} 次后仍失败: {last_error}",
            retry_count=self.max_retries
        )

    def _execute_strategy(
        self,
        strategy: Strategy,
        url: str,
        enable_og_fallback: bool
    ) -> StrategyResult:
        """执行具体策略"""
        import time
        start = time.time()

        try:
            if strategy == Strategy.FAST:
                result = self._execute_fast(url, enable_og_fallback)
            elif strategy == Strategy.ADAPTIVE:
                result = self._execute_adaptive(url, enable_og_fallback)
            elif strategy == Strategy.STABLE:
                result = self._execute_stable(url)
            elif strategy == Strategy.RELIABLE:
                result = self._execute_reliable(url)
            elif strategy == Strategy.ZERO_DEP:
                result = self._execute_zero_dep(url)
            elif strategy == Strategy.JINA_AI:
                result = self._execute_jina_ai(url)
            else:
                result = StrategyResult(
                    strategy,
                    False,
                    ContentStatus.FETCH_ERROR,
                    error="未知策略"
                )

            result.duration_ms = int((time.time() - start) * 1000)
            return result

        except Exception as e:
            return StrategyResult(
                strategy=strategy,
                success=False,
                content_status=ContentStatus.FETCH_ERROR,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000)
            )

    def _extract_with_og_fallback(self, soup) -> Dict[str, Any]:
        """
        提取 OG (Open Graph) 元数据作为备选

        竞品 wechat-article-reader 使用此方法提高可靠性
        """
        meta = {}

        # OG 元数据提取
        og_title = soup.find('meta', property='og:title')
        meta['title'] = og_title.get('content') if og_title else None

        og_author = soup.find('meta', property='og:article:author')
        meta['author'] = og_author.get('content') if og_author else None

        og_time = soup.find('meta', property='og:article:published_time')
        meta['publish_time'] = og_time.get('content') if og_time else None

        og_desc = soup.find('meta', property='og:description')
        meta['description'] = og_desc.get('content') if og_desc else None

        # 微信特定的 meta
        if not meta.get('author'):
            account_meta = soup.find('meta', attrs={'name': 'account'})
            if account_meta:
                meta['author'] = account_meta.get('content')

        return meta

    def _execute_fast(self, url: str, enable_og_fallback: bool = True, max_chars: int = 0) -> StrategyResult:
        """执行 Fast 策略 - HTTP + BS4，支持 OG 备选"""
        try:
            import requests
            from bs4 import BeautifulSoup

            # 添加 ?scene=1 参数避免验证码（关键技巧）
            if '?' not in url:
                url = url + '?scene=1'
            elif 'scene=' not in url:
                url = url + '&scene=1'

            headers = {
                'User-Agent': self._get_random_ua(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }

            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()

            print(f"   [Fast] HTTP {resp.status_code}, 内容长度 {len(resp.text)} bytes", file=sys.stderr)

            # 检查是否被拦截
            if '环境异常' in resp.text or 'verify' in resp.text.lower():
                return StrategyResult(
                    strategy=Strategy.FAST,
                    success=False,
                    content_status=ContentStatus.BLOCKED,
                    error="触发反爬验证，需要浏览器模式"
                )

            soup = BeautifulSoup(resp.text, 'lxml')

            # 提取内容（优先使用微信特定选择器）
            title = None
            author = None
            content_div = None

            # 微信特定选择器
            title_elem = soup.select_one('#activity-name') or soup.select_one('h1.rich_media_title')
            author_elem = soup.select_one('#js_name') or soup.select_one('.profile_nickname')
            content_div = soup.select_one('#js_content')

            if title_elem:
                title = title_elem.get_text(strip=True)
            if author_elem:
                author = author_elem.get_text(strip=True)

            # OG 元数据备选
            og_meta = self._extract_with_og_fallback(soup) if enable_og_fallback else {}
            title = title or og_meta.get('title', '')
            author = author or og_meta.get('author', '')

            if not content_div:
                # 即使没内容，如果有元数据也返回部分结果
                if title:
                    return StrategyResult(
                        strategy=Strategy.FAST,
                        success=True,
                        content_status=ContentStatus.OK,
                        data={
                            'title': title,
                            'author': author,
                            'content': '',
                            'images': [],
                            'html': '',
                            'og_meta': og_meta,
                            'partial': True  # 标记为部分结果
                        }
                    )
                return StrategyResult(
                    strategy=Strategy.FAST,
                    success=False,
                    content_status=ContentStatus.PARSE_EMPTY,
                    error="未找到文章内容"
                )

            # 吸取 camofox 精华：移除噪音元素
            noise_selectors = [
                'script', 'style', 'svg', 'iframe', 'form', 'button',
                '.js_uneditable', '.wx_profile_card_inner',
                '.original_primary_card_tips', '.rich_media_tool'
            ]
            for selector in noise_selectors:
                for el in content_div.select(selector):
                    el.decompose()

            # 提取图片 - 吸取精华：支持 data-backsrc，过滤 op_res
            images = []
            for img in content_div.find_all('img'):
                src = (img.get('data-src') or
                       img.get('data-backsrc') or
                       img.get('src') or '')
                alt = img.get('alt', '')

                # 过滤装饰性图片 - 吸取 camofox 精华
                if (src and
                    not src.startswith('data:') and
                    'res.wx.qq.com/op_res/' not in src and
                    'yZPTcMGWibvsic9Obib' not in src and
                    alt not in {'跳转二维码', '划线引导图'}):
                    images.append({
                        'src': src,
                        'alt': alt
                    })

            # 吸取 camofox 精华：过滤噪音文本
            content_text = content_div.get_text(separator='\n', strip=True)
            lines = content_text.split('\n')
            filtered_lines = []
            for line in lines:
                # 检查 STOP_MARKERS
                if any(marker in line for marker in self.STOP_MARKERS):
                    continue
                # 检查 SKIP_SUBSTRINGS
                if any(skip in line for skip in self.SKIP_SUBSTRINGS):
                    continue
                filtered_lines.append(line)
            content_text = '\n'.join(filtered_lines)

            # 吸取 camofox 精华：如果没时间，从内容提取
            publish_time = ''
            if not og_meta.get('publish_time'):
                date_match = self.DATE_RE.search(content_text)
                if date_match:
                    publish_time = date_match.group(0)
            else:
                publish_time = og_meta['publish_time']

            return StrategyResult(
                strategy=Strategy.FAST,
                success=True,
                content_status=ContentStatus.OK,
                data={
                    'title': title,
                    'author': author,
                    'publish_time': publish_time,
                    'content': content_text,
                    'images': images,
                    'html': str(content_div),
                    'og_meta': og_meta,
                }
            )

        except ImportError as e:
            return StrategyResult(
                strategy=Strategy.FAST,
                success=False,
                content_status=ContentStatus.FETCH_ERROR,
                error=f"缺少依赖: {e}"
            )
        except Exception as e:
            return StrategyResult(
                strategy=Strategy.FAST,
                success=False,
                content_status=ContentStatus.FETCH_ERROR,
                error=str(e)
            )

    def _execute_adaptive(self, url: str, enable_og_fallback: bool = True) -> StrategyResult:
        """
        执行 Adaptive 策略 - Scrapling

        竞品 fetch-wx-article 使用此库，专为复杂反爬页面设计
        比 Playwright 轻量，比 requests 稳定
        """
        try:
            from scrapling.fetchers import Fetcher
            from bs4 import BeautifulSoup

            # Scrapling 自动处理反爬
            page = Fetcher.get(url)

            # 解析内容
            soup = BeautifulSoup(page.html_content, 'lxml')

            # 提取内容
            title_elem = soup.select_one('#activity-name') or soup.select_one('h1')
            author_elem = soup.select_one('#js_name')
            content_div = soup.select_one('#js_content')

            title = title_elem.get_text(strip=True) if title_elem else ''
            author = author_elem.get_text(strip=True) if author_elem else ''

            # OG 备选
            og_meta = self._extract_with_og_fallback(soup) if enable_og_fallback else {}
            title = title or og_meta.get('title', '')
            author = author or og_meta.get('author', '')

            if not content_div:
                return StrategyResult(
                    strategy=Strategy.ADAPTIVE,
                    success=False,
                    content_status=ContentStatus.PARSE_EMPTY,
                    error="Scrapling 未找到文章内容"
                )

            # 吸取 camofox 精华：移除噪音元素
            noise_selectors = [
                'script', 'style', 'svg', 'iframe', 'form', 'button',
                '.js_uneditable', '.wx_profile_card_inner',
                '.original_primary_card_tips', '.rich_media_tool'
            ]
            for selector in noise_selectors:
                for el in content_div.select(selector):
                    el.decompose()

            # 提取图片（Scrapling 已处理懒加载）
            # 吸取精华：支持 data-backsrc，过滤 op_res
            images = []
            for img in content_div.find_all('img'):
                src = (img.get('data-src') or
                       img.get('data-backsrc') or
                       img.get('src') or '')
                alt = img.get('alt', '')

                # 过滤装饰性图片 - 吸取 camofox 精华
                if (src and
                    not src.startswith('data:') and
                    'res.wx.qq.com/op_res/' not in src and
                    'yZPTcMGWibvsic9Obib' not in src and
                    alt not in {'跳转二维码', '划线引导图'}):
                    images.append({
                        'src': src,
                        'alt': alt
                    })

            # 吸取 camofox 精华：过滤噪音文本
            content_text = content_div.get_text(separator='\n', strip=True)
            lines = content_text.split('\n')
            filtered_lines = []
            for line in lines:
                if any(marker in line for marker in self.STOP_MARKERS):
                    continue
                if any(skip in line for skip in self.SKIP_SUBSTRINGS):
                    continue
                filtered_lines.append(line)
            content_text = '\n'.join(filtered_lines)

            # 吸取 camofox 精华：如果没时间，从内容提取
            publish_time = ''
            if not og_meta.get('publish_time'):
                date_match = self.DATE_RE.search(content_text)
                if date_match:
                    publish_time = date_match.group(0)
            else:
                publish_time = og_meta['publish_time']

            return StrategyResult(
                strategy=Strategy.ADAPTIVE,
                success=True,
                content_status=ContentStatus.OK,
                data={
                    'title': title,
                    'author': author,
                    'publish_time': publish_time,
                    'content': content_text,
                    'images': images,
                    'html': str(content_div),
                    'og_meta': og_meta,
                }
            )

        except ImportError:
            return StrategyResult(
                strategy=Strategy.ADAPTIVE,
                success=False,
                content_status=ContentStatus.FETCH_ERROR,
                error="Scrapling 未安装，运行: pip install 'scrapling[ai]'"
            )
        except Exception as e:
            return StrategyResult(
                strategy=Strategy.ADAPTIVE,
                success=False,
                content_status=ContentStatus.FETCH_ERROR,
                error=str(e)
            )

    def _execute_stable(self, url: str, screenshot: bool = False) -> StrategyResult:
        """执行 Stable 策略 - Playwright"""
        try:
            cmd = ['python3', 'scripts/playwright_scraper.py', url]
            if screenshot:
                cmd.append('--screenshot')
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                return StrategyResult(
                    strategy=Strategy.STABLE,
                    success=True,
                    content_status=ContentStatus.OK,
                    data=data
                )
            else:
                error_msg = result.stderr
                status = ContentStatus.FETCH_ERROR
                if 'blocked' in error_msg.lower() or 'verify' in error_msg.lower():
                    status = ContentStatus.BLOCKED
                return StrategyResult(
                    strategy=Strategy.STABLE,
                    success=False,
                    content_status=status,
                    error=error_msg
                )
        except Exception as e:
            return StrategyResult(
                strategy=Strategy.STABLE,
                success=False,
                content_status=ContentStatus.FETCH_ERROR,
                error=str(e)
            )

    def _execute_reliable(self, url: str) -> StrategyResult:
        """执行 Reliable 策略 - Chrome DevTools MCP"""
        # 这个策略需要由 Claude 通过 MCP 调用
        # 返回一个特殊标记，让调用方知道需要使用 MCP
        return StrategyResult(
            strategy=Strategy.RELIABLE,
            success=False,
            content_status=ContentStatus.NEED_MCP,
            error="需要 Chrome DevTools MCP 模式",
            data={"url": url, "need_mcp": True}
        )

    def _execute_zero_dep(self, url: str) -> StrategyResult:
        """
        执行 Zero-Dependency 策略 - 纯标准库模式

        吸取 article-extract 精华：
        - 使用 urllib.request (标准库)
        - 使用 html.parser.HTMLParser (标准库)
        - 无需安装任何第三方库

        限制：
        - 功能有限，只能提取基础文本
        - 对复杂页面容错性较低
        - 作为最后的fallback使用
        """
        import urllib.request
        import re
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            """HTML文本提取器"""
            def __init__(self):
                super().__init__()
                self.text = []
                self.skip = 0
                self.skip_tags = {'script', 'style', 'nav', 'footer', 'header', 'aside'}

            def handle_starttag(self, tag, attrs):
                if tag in self.skip_tags:
                    self.skip += 1

            def handle_endtag(self, tag):
                if tag in self.skip_tags:
                    self.skip -= 1

            def handle_data(self, data):
                if self.skip <= 0:
                    self.text.append(data)

            def get_text(self):
                return ' '.join(self.text)

        try:
            print("   [Zero-Dep] 使用纯标准库模式...", file=sys.stderr)

            # 添加scene=1参数
            if '?' not in url:
                url = url + '?scene=1'
            elif 'scene=' not in url:
                url = url + '&scene=1'

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='ignore')

            # 预处理：移除script和style
            html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)

            # 解析HTML
            parser = TextExtractor()
            try:
                parser.feed(html)
                text = parser.get_text()
            except Exception:
                # Fallback：正则提取（不完美但总比没有好）
                text = re.sub(r'<[^>]+>', ' ', html)

            # 清理文本
            text = re.sub(r'\s+', ' ', text).strip()

            # 尝试提取标题
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else "未知标题"

            # 检查是否被拦截
            if '环境异常' in text or '请输入验证码' in text:
                return StrategyResult(
                    strategy=Strategy.ZERO_DEP,
                    success=False,
                    content_status=ContentStatus.BLOCKED,
                    error="触发反爬验证（零依赖模式无法绕过）"
                )

            # 尝试从meta提取作者
            author_match = re.search(r'<meta[^>]*property="og:article:author"[^>]*content="([^"]*)"', html, re.IGNORECASE)
            author = author_match.group(1) if author_match else "未知作者"

            return StrategyResult(
                strategy=Strategy.ZERO_DEP,
                success=True,
                content_status=ContentStatus.OK,
                data={
                    'title': title,
                    'author': author,
                    'content': text,
                    'html': html[:10000],  # 限制HTML大小
                    'images': [],  # 零依赖模式不提取图片
                    'zero_dep_mode': True,
                    'note': '零依赖模式仅提取基础文本，功能有限'
                }
            )

        except Exception as e:
            return StrategyResult(
                strategy=Strategy.ZERO_DEP,
                success=False,
                content_status=ContentStatus.FETCH_ERROR,
                error=f"零依赖模式失败: {str(e)}"
            )

    def _execute_jina_ai(self, url: str) -> StrategyResult:
        """
        执行 Jina AI 策略 - 使用 r.jina.ai 服务提取内容

        吸取 wechat-article-1.0.0 精华：
        - jina.ai 是可靠的第三方提取服务
        - 支持微信公众号
        - 作为最后的 fallback 使用

        限制：
        - 依赖第三方服务可用性
        - 可能有时延
        """
        try:
            import urllib.request
            import json

            print("   [Jina AI] 尝试使用 jina.ai 服务...", file=sys.stderr)

            jina_url = f"https://r.jina.ai/{url}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'X-Return-Format': 'markdown',
            }

            req = urllib.request.Request(jina_url, headers=headers)

            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode('utf-8', errors='ignore')

            # 检查是否被拦截
            if '环境异常' in content or '验证码' in content:
                return StrategyResult(
                    strategy=Strategy.JINA_AI,
                    success=False,
                    content_status=ContentStatus.BLOCKED,
                    error="jina.ai 返回风控验证"
                )

            if not content or len(content) < 50:
                return StrategyResult(
                    strategy=Strategy.JINA_AI,
                    success=False,
                    content_status=ContentStatus.PARSE_EMPTY,
                    error="jina.ai 返回内容为空"
                )

            # 解析 jina.ai 返回的 markdown 格式
            # 第一行通常是标题
            lines = content.strip().split('\n')
            title = ""
            body_lines = []

            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue

                # 第一行非空通常是标题
                if not title and not line.startswith('http'):
                    title = line.lstrip('# ').strip()
                    continue

                # 跳过 URL 行
                if line.startswith('http'):
                    continue

                # 跳过分隔符
                if line == '---':
                    continue

                body_lines.append(line)

            body = '\n\n'.join(body_lines).strip()

            return StrategyResult(
                strategy=Strategy.JINA_AI,
                success=True,
                content_status=ContentStatus.OK,
                data={
                    'title': title or '未知标题',
                    'author': '',  # jina.ai 不返回作者信息
                    'content': body,
                    'html': '',  # jina.ai 返回 markdown，无原始 HTML
                    'images': [],  # jina.ai 不返回图片信息
                    'jina_ai_mode': True,
                    'note': '通过 jina.ai 服务提取'
                }
            )

        except Exception as e:
            return StrategyResult(
                strategy=Strategy.JINA_AI,
                success=False,
                content_status=ContentStatus.FETCH_ERROR,
                error=f"jina.ai 服务失败: {str(e)}"
            )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 router.py <微信文章URL> [fast|adaptive|stable|reliable|zero_dep|jina_ai]", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    prefer = None

    if len(sys.argv) > 2:
        prefer_map = {
            "fast": Strategy.FAST,
            "adaptive": Strategy.ADAPTIVE,
            "stable": Strategy.STABLE,
            "reliable": Strategy.RELIABLE,
            "zero_dep": Strategy.ZERO_DEP,
            "jina_ai": Strategy.JINA_AI,
        }
        prefer = prefer_map.get(sys.argv[2])

    router = StrategyRouter()
    result = router.route(url, prefer)

    # 输出 JSON 结果
    output = {
        "strategy": result.strategy.value,
        "success": result.success,
        "content_status": result.content_status.value,
        "data": result.data,
        "error": result.error,
        "duration_ms": result.duration_ms,
        "retry_count": result.retry_count,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))

    sys.exit(0 if result.success else 1)
