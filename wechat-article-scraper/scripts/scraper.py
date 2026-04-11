#!/usr/bin/env python3
"""
微信公众号文章抓取工具 - 世界级微信文章抓取方案 v2.1

整合策略路由、OG元数据备选、图片与段落关联、多格式导出等完整功能。
支持四种策略：fast → adaptive → stable → reliable 自动降级

特性：
- 智能策略路由：自动选择最佳抓取策略
- OG 元数据备选：当微信特定选择器失败时使用 Open Graph
- 图片段落关联：智能识别图片与文本段落的关系
- Content Status：清晰的状态码系统
- 重试机制：自动重试和 UA 轮换
- 反爬绕过：使用 ?scene=1 参数可绕过登录验证

作者: Claude Code
版本: 2.1.0
"""

import sys
import os
import json
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('wechat-scraper')

# 将脚本目录加入路径
scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))

from router import StrategyRouter, Strategy, ContentStatus


def get_default_output_dir() -> str:
    """
    获取默认输出目录

    自动检测常见工作空间路径，避免硬编码
    """
    # 常见工作空间路径（按优先级）
    workspace_candidates = [
        os.environ.get('WORKSPACE_DIR'),  # 环境变量优先
        os.path.expanduser("~/Clippings"),
        os.path.expanduser("~/.openclaw/workspace/source"),
        os.path.expanduser("~/.claude/workspace/source"),
        os.path.expanduser("~/workspace/articles"),
        os.path.expanduser("~/Downloads/wechat-articles"),
        ".",  # 当前目录作为 fallback
    ]

    for workspace in workspace_candidates:
        if workspace and os.path.isdir(workspace):
            return workspace

    # 创建默认目录
    default_dir = os.path.expanduser("~/wechat-articles")
    os.makedirs(default_dir, exist_ok=True)
    return default_dir


def scrape_article(
    url: str,
    strategy: Optional[str] = None,
    download_images: bool = False,
    output_format: str = 'markdown',
    output_dir: Optional[str] = None,
    enable_og_fallback: bool = True,
    max_retries: int = 3,
    screenshot: bool = False,
    proxy: Optional[str] = None
) -> Dict[str, Any]:
    """
    抓取单篇文章

    Args:
        url: 微信文章 URL
        strategy: 优先策略 (fast/adaptive/stable/reliable)
        download_images: 是否下载图片
        output_format: 输出格式
        output_dir: 输出目录（None 时自动检测）
        enable_og_fallback: 启用 OG 元数据备选提取
        max_retries: 最大重试次数
        screenshot: 是否保存页面截图（仅 Playwright 策略）

    Returns:
        dict: 抓取结果，包含 content_status 状态码
    """
    # 清理 URL，添加 ?scene=1 参数
    try:
        url = _prepare_url(url)
    except ValueError as e:
        return {
            'success': False,
            'error': str(e),
            'content_status': 'no_mp_url'
        }

    # 确定输出目录
    if output_dir is None:
        output_dir = get_default_output_dir()

    # 选择策略
    prefer = None
    if strategy:
        strategy_map = {
            'fast': Strategy.FAST,
            'adaptive': Strategy.ADAPTIVE,
            'stable': Strategy.STABLE,
            'reliable': Strategy.RELIABLE,
            'zero_dep': Strategy.ZERO_DEP,
            'jina_ai': Strategy.JINA_AI,
        }
        prefer = strategy_map.get(strategy)

    # 路由到最佳策略
    router = StrategyRouter(max_retries=max_retries, proxy=proxy)
    result = router.route(url, prefer_strategy=prefer, enable_og_fallback=enable_og_fallback)

    if not result.success:
        # 构建详细的错误响应
        error_response = {
            'success': False,
            'error': result.error,
            'strategy': result.strategy.value,
            'content_status': result.content_status.value,
            'duration_ms': result.duration_ms,
            'retry_count': result.retry_count,
        }

        # 提供恢复建议
        if result.content_status == ContentStatus.BLOCKED:
            error_response['recovery_hint'] = '触发反爬验证，建议: 1) 使用 reliable 策略; 2) 等待 5 分钟后重试; 3) 使用 Chrome DevTools MCP'
        elif result.content_status == ContentStatus.NEED_MCP:
            error_response['recovery_hint'] = '需要 Chrome DevTools MCP 模式抓取'
            error_response['need_mcp'] = True

        return error_response

    data = result.data or {}
    data['source_url'] = url
    data['strategy_used'] = result.strategy.value
    data['content_status'] = result.content_status.value
    data['duration_ms'] = result.duration_ms

    # 下载图片
    if download_images and data.get('images'):
        logger.info("📥 下载图片中...")
        from images import ImageDownloader

        img_dir = Path(output_dir) / "images"
        downloader = ImageDownloader(str(img_dir))

        results = downloader.download_images(data['images'])

        # 更新 Markdown 内容中的图片链接
        if 'content' in data:
            md_content = data['content']
            updated_md = downloader.update_markdown_images(md_content, results)
            data['content'] = updated_md

        # 更新图片信息
        data['images_downloaded'] = [
            {
                'url': r.url,
                'local_path': r.local_path,
                'status': r.status,
                'size_bytes': r.size_bytes,
                'width': r.width,
                'height': r.height
            }
            for r in results
        ]

        # 生成下载报告
        report = downloader.generate_report(results)
        data['download_report'] = report

    # 导出
    from export import Exporter

    exporter = Exporter(output_dir=output_dir)

    # 生成文件名
    title = data.get('title', 'untitled')
    safe_title = "".join(c for c in title if c.isalnum() or c in ' _-').strip()
    if not safe_title:
        safe_title = f"wechat_article_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        output_path = exporter.save(data, format=output_format, filename=safe_title)

        return {
            'success': True,
            'output_path': output_path,
            'strategy': result.strategy.value,
            'content_status': result.content_status.value,
            'title': data.get('title'),
            'author': data.get('author'),
            'image_count': len(data.get('images', [])),
            'duration_ms': result.duration_ms,
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"导出失败: {e}",
            'strategy': result.strategy.value,
            'content_status': 'export_error',
        }


def _prepare_url(url: str) -> str:
    """
    准备 URL：验证并添加 ?scene=1 参数绕过反爬

    关键技巧：scene=1 参数可以显著降低触发验证码的概率
    必须使用 ?scene=1 格式（而非 &scene=1）
    """
    # 验证 URL 格式
    if not url or not isinstance(url, str):
        raise ValueError("URL 必须是非空字符串")

    # 验证是否是微信文章 URL（安全校验）
    allowed_domains = ['mp.weixin.qq.com', 'weixin.qq.com']
    if not any(domain in url for domain in allowed_domains):
        raise ValueError(f"不支持的 URL: 必须是微信文章链接 ({', '.join(allowed_domains)})")

    # 移除可能的跟踪参数
    url = url.split('#')[0]  # 移除 hash

    # 添加 scene=1 参数（关键：必须是 ? 而非 &）
    # 参考竞品 wechat-mp-reader 的强调：URL must end with `?scene=1` (not `&scene=1`)
    if '?' not in url:
        url = url + '?scene=1'
    elif 'scene=' not in url:
        url = url + '&scene=1'

    return url


def batch_scrape(
    urls_file: str,
    output_dir: str,
    strategy: Optional[str] = None,
    download_images: bool = False,
    delay: float = 3.0,
    proxy: Optional[str] = None
) -> Dict[str, Any]:
    """
    批量抓取文章

    Args:
        urls_file: URL 列表文件路径（每行一个 URL）
        output_dir: 输出目录
        strategy: 优先策略
        download_images: 是否下载图片
        delay: 请求间隔（秒）
        proxy: HTTP 代理地址

    Returns:
        dict: 批量抓取结果统计
    """
    urls = []
    with open(urls_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)

    logger.info(f"批量抓取: 共 {len(urls)} 篇文章")

    results = {
        'total': len(urls),
        'success': 0,
        'failed': 0,
        'by_status': {},
        'articles': []
    }

    for i, url in enumerate(urls, 1):
        logger.info(f"[{i}/{len(urls)}] 抓取: {url[:60]}...")

        result = scrape_article(
            url=url,
            strategy=strategy,
            download_images=download_images,
            output_dir=output_dir,
            proxy=proxy
        )

        results['articles'].append({
            'url': url,
            'success': result['success'],
            'status': result.get('content_status', 'unknown'),
            'output_path': result.get('output_path'),
            'error': result.get('error')
        })

        if result['success']:
            results['success'] += 1
        else:
            results['failed'] += 1

        # 状态统计
        status = result.get('content_status', 'unknown')
        results['by_status'][status] = results['by_status'].get(status, 0) + 1

        # 间隔避免风控
        if i < len(urls):
            logger.info(f"   等待 {delay}s...")
            import time
            time.sleep(delay)

    logger.info(f"批量抓取完成: 成功 {results['success']}/{results['total']}")
    return results


def main():
    parser = argparse.ArgumentParser(
        description='微信公众号文章抓取工具 v2.1 - 世界级微信文章抓取方案',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "https://mp.weixin.qq.com/s/xxxxx"
  %(prog)s "https://mp.weixin.qq.com/s/xxxxx" -s reliable --download-images
  %(prog)s "https://mp.weixin.qq.com/s/xxxxx" -f pdf -o ./articles/
  %(prog)s --batch urls.txt -o ./articles/ --delay 5

策略说明:
  fast     - HTTP + BeautifulSoup，最快但可能被拦截
  adaptive - Scrapling，自适应反爬，轻量稳定（推荐）
  stable   - Playwright，稳定渲染
  reliable - Chrome DevTools MCP，最可靠，配合 ?scene=1 可绕过登录
  zero_dep - 纯标准库模式，无需任何依赖
  jina_ai  - 使用 jina.ai 服务，作为最后fallback

Content Status:
  ok            - 抓取成功
  blocked       - 被风控拦截
  no_mp_url     - 无效的微信文章链接
  fetch_error   - 网络请求失败
  parse_empty   - 解析结果为空
  need_mcp      - 需要 MCP 模式
        """
    )

    parser.add_argument(
        'url',
        nargs='?',
        help='微信文章 URL'
    )
    parser.add_argument(
        '-s', '--strategy',
        choices=['fast', 'adaptive', 'stable', 'reliable', 'zero_dep', 'jina_ai'],
        help='优先使用的抓取策略'
    )
    parser.add_argument(
        '-f', '--format',
        choices=['markdown', 'md', 'json', 'html', 'pdf'],
        default='markdown',
        help='输出格式 (默认: markdown)'
    )
    parser.add_argument(
        '-o', '--output',
        help=f'输出目录 (默认: 自动检测或使用 {get_default_output_dir()})'
    )
    parser.add_argument(
        '--download-images',
        action='store_true',
        help='下载图片到本地'
    )
    parser.add_argument(
        '-j', '--json-output',
        action='store_true',
        help='输出 JSON 格式结果到 stdout'
    )
    parser.add_argument(
        '--batch',
        metavar='URLS_FILE',
        help='批量抓取模式（URL 列表文件，每行一个）'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=3.0,
        help='批量模式下的请求间隔（秒，默认: 3.0）'
    )
    parser.add_argument(
        '--max-retries',
        type=int,
        default=3,
        help='最大重试次数（默认: 3）'
    )
    parser.add_argument(
        '--no-og-fallback',
        action='store_true',
        help='禁用 OG 元数据备选提取'
    )
    parser.add_argument(
        '--proxy',
        help='HTTP 代理地址 (例如: http://127.0.0.1:1082)'
    )

    args = parser.parse_args()

    # 批量模式
    if args.batch:
        if not os.path.exists(args.batch):
            logger.error(f"URL 列表文件不存在: {args.batch}")
            sys.exit(1)

        output_dir = args.output or get_default_output_dir()
        results = batch_scrape(
            urls_file=args.batch,
            output_dir=output_dir,
            strategy=args.strategy,
            download_images=args.download_images,
            delay=args.delay,
            proxy=args.proxy
        )

        if args.json_output:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            logger.info(f"\n{'='*60}")
            logger.info(f"批量抓取报告")
            logger.info(f"{'='*60}")
            logger.info(f"总计: {results['total']}")
            logger.info(f"成功: {results['success']}")
            logger.info(f"失败: {results['failed']}")
            logger.info(f"状态分布:")
            for status, count in results['by_status'].items():
                logger.info(f"  - {status}: {count}")

        sys.exit(0 if results['failed'] == 0 else 1)

    # 单篇模式
    if not args.url:
        parser.print_help()
        sys.exit(1)

    result = scrape_article(
        url=args.url,
        strategy=args.strategy,
        download_images=args.download_images,
        output_format=args.format,
        output_dir=args.output,
        enable_og_fallback=not args.no_og_fallback,
        max_retries=args.max_retries,
        proxy=args.proxy
    )

    # 输出结果
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result['success']:
            print(f"✅ 抓取成功")
            print(f"   文件: {result['output_path']}")
            print(f"   策略: {result['strategy']}")
            print(f"   状态: {result['content_status']}")
            print(f"   标题: {result['title']}")
            if result.get('image_count', 0) > 0:
                print(f"   图片: {result['image_count']} 张")
        else:
            print(f"❌ 抓取失败: {result['error']}", file=sys.stderr)
            print(f"   策略: {result.get('strategy', 'unknown')}", file=sys.stderr)
            print(f"   状态: {result.get('content_status', 'unknown')}", file=sys.stderr)
            if 'recovery_hint' in result:
                print(f"💡 建议: {result['recovery_hint']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
