#!/usr/bin/env python3
"""
智能策略路由器 - 自动选择最佳微信文章抓取策略

支持三种模式：
- fast: HTTP + BeautifulSoup (快速但可能被封)
- stable: Playwright (稳定但需要安装)
- reliable: Chrome DevTools MCP (最可靠但需要登录态)

自动检测可用策略并选择最佳方案。
"""

import sys
import subprocess
import json
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass


class Strategy(Enum):
    """抓取策略枚举"""
    FAST = "fast"           # HTTP + BS4
    STABLE = "stable"       # Playwright
    RELIABLE = "reliable"   # Chrome DevTools MCP
    FAILED = "failed"       # 所有策略都失败


@dataclass
class StrategyResult:
    """策略执行结果"""
    strategy: Strategy
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class StrategyRouter:
    """策略路由器 - 自动选择并执行最佳抓取策略"""

    def __init__(self):
        self.strategy_order = [
            Strategy.FAST,      # 先尝试快速模式
            Strategy.STABLE,    # 再尝试稳定模式
            Strategy.RELIABLE,  # 最后使用可靠模式
        ]

    def detect_available_strategies(self) -> list[Strategy]:
        """检测当前环境支持的策略"""
        available = []

        # 检查 Fast 模式 (HTTP)
        available.append(Strategy.FAST)

        # 检查 Stable 模式 (Playwright)
        if self._check_playwright():
            available.append(Strategy.STABLE)

        # 检查 Reliable 模式 (Chrome DevTools MCP)
        # 这个由调用方通过参数控制
        available.append(Strategy.RELIABLE)

        return available

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

    def _validate_url(self, url: str) -> bool:
        """验证 URL 是否是允许的微信域名"""
        allowed_domains = ['mp.weixin.qq.com', 'weixin.qq.com']
        return any(domain in url for domain in allowed_domains)

    def route(self, url: str, prefer_strategy: Optional[Strategy] = None) -> StrategyResult:
        """
        路由到最佳策略

        Args:
            url: 微信文章 URL
            prefer_strategy: 优先使用的策略（可选）

        Returns:
            StrategyResult: 执行结果
        """
        # 验证 URL
        if not self._validate_url(url):
            return StrategyResult(
                strategy=Strategy.FAILED,
                success=False,
                error="不支持的 URL: 必须是微信文章链接 (mp.weixin.qq.com)"
            )

        strategies = self.detect_available_strategies()

        # 如果有优先策略且可用，优先使用
        if prefer_strategy and prefer_strategy in strategies:
            strategies = [prefer_strategy] + [s for s in strategies if s != prefer_strategy]

        # 按顺序尝试每种策略
        for strategy in strategies:
            print(f"🔄 尝试策略: {strategy.value}...", file=sys.stderr)

            result = self._execute_strategy(strategy, url)

            if result.success:
                print(f"✅ 策略 {strategy.value} 成功", file=sys.stderr)
                return result
            else:
                print(f"❌ 策略 {strategy.value} 失败: {result.error}", file=sys.stderr)

        # 所有策略都失败
        return StrategyResult(
            strategy=Strategy.FAILED,
            success=False,
            error="所有抓取策略均失败"
        )

    def _execute_strategy(self, strategy: Strategy, url: str) -> StrategyResult:
        """执行具体策略"""
        import time
        start = time.time()

        try:
            if strategy == Strategy.FAST:
                result = self._execute_fast(url)
            elif strategy == Strategy.STABLE:
                result = self._execute_stable(url)
            elif strategy == Strategy.RELIABLE:
                result = self._execute_reliable(url)
            else:
                result = StrategyResult(strategy, False, error="未知策略")

            result.duration_ms = int((time.time() - start) * 1000)
            return result

        except Exception as e:
            return StrategyResult(
                strategy=strategy,
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000)
            )

    def _execute_fast(self, url: str) -> StrategyResult:
        """执行 Fast 策略 - HTTP + BS4"""
        try:
            import requests
            from bs4 import BeautifulSoup

            # 添加 ?scene=1 参数避免验证码
            if '?' not in url:
                url = url + '?scene=1'
            elif 'scene=' not in url:
                url = url + '&scene=1'

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }

            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()

            # 检查是否被拦截
            if '环境异常' in resp.text or 'verify' in resp.text.lower():
                return StrategyResult(
                    strategy=Strategy.FAST,
                    success=False,
                    error="触发反爬验证，需要浏览器模式"
                )

            soup = BeautifulSoup(resp.text, 'lxml')

            # 提取内容
            title = soup.select_one('#activity-name') or soup.select_one('h1')
            author = soup.select_one('#js-name') or soup.select_one('.profile_nickname')
            content_div = soup.select_one('#js_content')

            if not content_div:
                return StrategyResult(
                    strategy=Strategy.FAST,
                    success=False,
                    error="未找到文章内容"
                )

            # 提取图片
            images = []
            for img in content_div.find_all('img'):
                src = img.get('data-src') or img.get('src')
                if src and not src.startswith('data:'):
                    images.append({
                        'src': src,
                        'alt': img.get('alt', '')
                    })

            return StrategyResult(
                strategy=Strategy.FAST,
                success=True,
                data={
                    'title': title.get_text(strip=True) if title else '',
                    'author': author.get_text(strip=True) if author else '',
                    'content': content_div.get_text(separator='\n', strip=True),
                    'images': images,
                    'html': str(content_div),
                }
            )

        except ImportError as e:
            return StrategyResult(
                strategy=Strategy.FAST,
                success=False,
                error=f"缺少依赖: {e}"
            )
        except Exception as e:
            return StrategyResult(
                strategy=Strategy.FAST,
                success=False,
                error=str(e)
            )

    def _execute_stable(self, url: str) -> StrategyResult:
        """执行 Stable 策略 - Playwright"""
        # 调用 playwright_scraper.py
        try:
            result = subprocess.run(
                ['python3', 'scripts/playwright_scraper.py', url],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                return StrategyResult(
                    strategy=Strategy.STABLE,
                    success=True,
                    data=data
                )
            else:
                return StrategyResult(
                    strategy=Strategy.STABLE,
                    success=False,
                    error=result.stderr
                )
        except Exception as e:
            return StrategyResult(
                strategy=Strategy.STABLE,
                success=False,
                error=str(e)
            )

    def _execute_reliable(self, url: str) -> StrategyResult:
        """执行 Reliable 策略 - Chrome DevTools MCP"""
        # 这个策略需要由 Claude 通过 MCP 调用
        # 返回一个特殊标记，让调用方知道需要使用 MCP
        return StrategyResult(
            strategy=Strategy.RELIABLE,
            success=False,
            error="NEED_MCP",  # 特殊标记
            data={"url": url, "need_mcp": True}
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 router.py <微信文章URL> [fast|stable|reliable]", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    prefer = None

    if len(sys.argv) > 2:
        prefer_map = {
            "fast": Strategy.FAST,
            "stable": Strategy.STABLE,
            "reliable": Strategy.RELIABLE,
        }
        prefer = prefer_map.get(sys.argv[2])

    router = StrategyRouter()
    result = router.route(url, prefer)

    # 输出 JSON 结果
    output = {
        "strategy": result.strategy.value,
        "success": result.success,
        "data": result.data,
        "error": result.error,
        "duration_ms": result.duration_ms,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))

    sys.exit(0 if result.success else 1)
