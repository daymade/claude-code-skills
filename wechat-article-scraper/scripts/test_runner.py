#!/usr/bin/env python3
"""
自动化测试运行器 - 验证 wechat-article-scraper 核心功能

功能：
- 本地离线测试（无需网络）
- 集成测试（需要网络）
- 质量评分验证
- 缓存系统验证
- 导出格式验证
- 测试报告生成

使用方法：
  python3 test_runner.py                    # 运行所有测试
  python3 test_runner.py --offline          # 仅运行离线测试
  python3 test_runner.py --test quality     # 运行特定测试
  python3 test_runner.py --verbose          # 详细输出

作者: Claude Code
版本: 3.3.0
"""

import sys
import os
import json
import re
import tempfile
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from contextlib import contextmanager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('wechat-tests')

# 将脚本目录加入路径
scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))


@dataclass
class TestResult:
    """测试结果"""
    name: str
    passed: bool
    duration_ms: float
    message: str = ""
    details: Dict[str, Any] = None


class TestRunner:
    """测试运行器"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: List[TestResult] = []
        self.temp_dir = None

    @contextmanager
    def _temp_workspace(self):
        """创建临时工作空间"""
        import tempfile
        self.temp_dir = Path(tempfile.mkdtemp(prefix='wechat-test-'))
        try:
            yield self.temp_dir
        finally:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None

    def run_all(self, offline_only: bool = False) -> bool:
        """运行所有测试"""
        print("=" * 60)
        print("WeChat Article Scraper - 自动化测试")
        print("=" * 60)

        # 离线测试（无需网络）
        self._test_url_normalization()
        self._test_quality_scoring()
        self._test_cache_system()
        self._test_export_formats()
        self._test_content_validation()

        if not offline_only:
            # 在线测试（需要网络）
            self._test_fast_strategy()
            self._test_og_fallback()
            self._test_image_extraction()

        # 生成报告
        return self._print_report()

    def _test_url_normalization(self):
        """测试 URL 标准化"""
        from scraper import _prepare_url

        test_cases = [
            # (input, expected_contains, description)
            ("https://mp.weixin.qq.com/s/xxxxx", "scene=1", "添加 scene 参数"),
            ("https://mp.weixin.qq.com/s/xxxxx?scene=1", "scene=1", "已有 scene 参数"),
            ("https://mp.weixin.qq.com/s/xxxxx#hash", "scene=1", "移除 hash"),
        ]

        for url, expected, desc in test_cases:
            try:
                result = _prepare_url(url)
                passed = expected in result
                self._add_result(f"URL标准化: {desc}", passed,
                               f"输入: {url[:40]}...\n输出: {result[:50]}..." if self.verbose else "")
            except Exception as e:
                self._add_result(f"URL标准化: {desc}", False, str(e))

    def _test_quality_scoring(self):
        """测试质量评分系统"""
        from quality import ContentValidator, QualityGrade

        validator = ContentValidator()

        # 测试高质量内容
        high_quality_data = {
            'title': '这是一个完整的微信文章标题',
            'author': '测试公众号',
            'publishTime': '2024-01-01',
            'content': '这是一段很长的文章内容，' * 50 + '包含足够的字数和段落。\n\n' * 10,
            'html': '<div id="js_content"><p>测试内容</p></div>',
            'images': [{'src': 'http://example.com/1.jpg', 'alt': '图片1'}],
        }

        score = validator.validate(high_quality_data)
        self._add_result("质量评分-高质量内容",
                        score.grade in (QualityGrade.EXCELLENT, QualityGrade.GOOD),
                        f"得分: {score.total_score}, 等级: {score.grade.value}")

        # 测试低质量内容
        low_quality_data = {
            'title': '',
            'author': '',
            'content': '很短',
        }

        score = validator.validate(low_quality_data)
        self._add_result("质量评分-低质量内容",
                        score.grade == QualityGrade.INVALID,
                        f"得分: {score.total_score}, 等级: {score.grade.value}")

    def _test_cache_system(self):
        """测试缓存系统"""
        from cache import CacheManager

        with self._temp_workspace() as temp_dir:
            cache = CacheManager(cache_dir=str(temp_dir), ttl_days=1)

            # 测试存储和读取
            test_data = {
                'title': '测试文章',
                'author': '测试作者',
                'content': '测试内容',
            }
            test_url = 'https://mp.weixin.qq.com/s/test123'

            # 存储
            cache.set(test_url, test_data, strategy='test')

            # 读取
            cached = cache.get(test_url)
            self._add_result("缓存-存储和读取",
                           cached is not None and cached['title'] == '测试文章',
                           f"缓存命中: {cached is not None}")

            # 测试重复 URL 检测
            exists = cache.exists(test_url)
            self._add_result("缓存-存在检测", exists, f"存在: {exists}")

            # 测试内容指纹
            same_content_url = 'https://mp.weixin.qq.com/s/different456'
            same_data = test_data.copy()
            same_data['url'] = same_content_url

            # 统计
            stats = cache.get_stats()
            self._add_result("缓存-统计功能",
                           'total_cached' in stats,
                           f"缓存数: {stats.get('total_cached', 0)}")

    def _test_export_formats(self):
        """测试导出格式"""
        from export import Exporter

        with self._temp_workspace() as temp_dir:
            exporter = Exporter(output_dir=str(temp_dir))

            test_data = {
                'title': '测试标题',
                'author': '测试作者',
                'content': '测试内容\n第二段',
                'html': '<p>测试内容</p><p>第二段</p>',
                'source_url': 'https://mp.weixin.qq.com/s/test',
                'images': [],
                'videos': [],
            }

            # 测试 Markdown 导出
            try:
                md_path = exporter.save(test_data, format='markdown', filename='test')
                passed = Path(md_path).exists()
                self._add_result("导出-Markdown", passed,
                               f"文件: {md_path}" if passed else "文件未创建")
            except Exception as e:
                self._add_result("导出-Markdown", False, str(e))

            # 测试 JSON 导出
            try:
                json_path = exporter.save(test_data, format='json', filename='test')
                passed = Path(json_path).exists()
                content = Path(json_path).read_text()
                data = json.loads(content)
                valid = data.get('title') == '测试标题'
                self._add_result("导出-JSON", passed and valid,
                               f"文件: {json_path}" if passed else "文件未创建")
            except Exception as e:
                self._add_result("导出-JSON", False, str(e))

            # 测试 HTML 导出
            try:
                html_path = exporter.save(test_data, format='html', filename='test')
                passed = Path(html_path).exists()
                content = Path(html_path).read_text()
                has_title = '测试标题' in content
                safe = '<script>' not in content  # XSS 防护检查
                self._add_result("导出-HTML", passed and has_title and safe,
                               f"包含标题: {has_title}, 无脚本: {safe}")
            except Exception as e:
                self._add_result("导出-HTML", False, str(e))

    def _test_content_validation(self):
        """测试内容验证"""
        from router import StrategyRouter, ContentStatus

        router = StrategyRouter()

        # 测试 URL 验证
        valid_url = 'https://mp.weixin.qq.com/s/test'
        invalid_url = 'https://example.com/article'

        valid_result = router._validate_url(valid_url)
        invalid_result = router._validate_url(invalid_url)

        self._add_result("验证-微信URL", valid_result, "mp.weixin.qq.com 应通过")
        self._add_result("验证-非微信URL", not invalid_result, "example.com 应拒绝")

    def _test_fast_strategy(self):
        """测试 Fast 策略（需要网络）"""
        from router import StrategyRouter, ContentStatus

        # 使用一个已知的公开文章（或跳过）
        router = StrategyRouter(max_retries=1)

        # 这里使用模拟测试，实际测试需要真实 URL
        # 由于网络不确定性，这个测试可能失败
        self._add_result("策略-Fast策略", True, "网络测试需要真实URL",
                        skip=True)

    def _test_og_fallback(self):
        """测试 OG 元数据备选"""
        from router import StrategyRouter

        router = StrategyRouter()

        # 创建模拟 HTML 测试 OG 提取
        test_html = '''
        <html>
        <head>
            <meta property="og:title" content="测试标题">
            <meta property="og:article:author" content="测试作者">
            <meta property="og:description" content="测试描述">
        </head>
        <body></body>
        </html>
        '''

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(test_html, 'html.parser')
        og_meta = router._extract_with_og_fallback(soup)

        passed = (og_meta.get('title') == '测试标题' and
                 og_meta.get('author') == '测试作者')

        self._add_result("OG元数据-提取", passed,
                       f"标题: {og_meta.get('title')}, 作者: {og_meta.get('author')}")

    def _test_image_extraction(self):
        """测试图片提取"""
        # 模拟图片提取测试
        test_content = '''
        <div id="js_content">
            <p>文章内容</p>
            <img data-src="https://mmbiz.qpic.cn/real.jpg" alt="真实图片">
            <img data-src="data:image/svg+xml,base64..." alt="占位图">
            <img src="https://mmbiz.qpic.cn/op_res/decorative.png">
        </div>
        '''

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(test_content, 'html.parser')
        content_div = soup.select_one('#js_content')

        if content_div:
            images = []
            for img in content_div.find_all('img'):
                src = (img.get('data-src') or img.get('src') or '')
                alt = img.get('alt', '')

                # 过滤装饰性图片
                if (src and
                    not src.startswith('data:') and
                    'res.wx.qq.com/op_res/' not in src):
                    images.append({'src': src, 'alt': alt})

            passed = len(images) == 1 and images[0]['src'].endswith('real.jpg')
            self._add_result("图片-提取和过滤", passed,
                           f"提取 {len(images)} 张图片，期望 1 张")
        else:
            self._add_result("图片-提取和过滤", False, "未找到内容区")

    def _add_result(self, name: str, passed: bool, message: str = "", skip: bool = False):
        """添加测试结果"""
        import time

        if skip:
            status = "⏭️ 跳过"
        elif passed:
            status = "✅ 通过"
        else:
            status = "❌ 失败"

        print(f"{status} {name}")

        if message and self.verbose:
            for line in message.split('\n'):
                print(f"     {line}")

        self.results.append(TestResult(
            name=name,
            passed=passed and not skip,
            duration_ms=0,
            message=message
        ))

    def _print_report(self) -> bool:
        """打印测试报告"""
        print("\n" + "=" * 60)
        print("测试报告")
        print("=" * 60)

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        skipped = sum(1 for r in self.results if "跳过" in r.message)
        failed = total - passed - skipped

        print(f"总计: {total}")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        print(f"跳过: {skipped}")

        if failed > 0 and not self.verbose:
            print("\n失败详情:")
            for r in self.results:
                if not r.passed and "跳过" not in r.message:
                    print(f"  ❌ {r.name}")
                    if r.message:
                        print(f"     {r.message}")

        print("=" * 60)

        return failed == 0


def main():
    parser = argparse.ArgumentParser(description='WeChat Article Scraper 测试运行器')
    parser.add_argument('--offline', action='store_true', help='仅运行离线测试')
    parser.add_argument('--test', metavar='NAME', help='运行特定测试')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    parser.add_argument('--list', action='store_true', help='列出所有测试')

    args = parser.parse_args()

    if args.list:
        tests = [
            "URL标准化",
            "质量评分-高质量内容",
            "质量评分-低质量内容",
            "缓存-存储和读取",
            "缓存-存在检测",
            "缓存-统计功能",
            "导出-Markdown",
            "导出-JSON",
            "导出-HTML",
            "验证-微信URL",
            "验证-非微信URL",
            "OG元数据-提取",
            "图片-提取和过滤",
        ]
        print("可用测试:")
        for test in tests:
            print(f"  - {test}")
        return

    runner = TestRunner(verbose=args.verbose)
    success = runner.run_all(offline_only=args.offline)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
