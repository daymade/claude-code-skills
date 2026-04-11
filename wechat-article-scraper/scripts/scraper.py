#!/usr/bin/env python3
"""
微信公众号文章抓取工具 - 主入口

整合策略路由、图片下载、格式导出等功能的世界级微信文章抓取方案。

作者: Claude Code
版本: 2.0.0
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import Optional

# 将脚本目录加入路径
scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))

from router import StrategyRouter, Strategy


def scrape_article(
    url: str,
    strategy: Optional[str] = None,
    download_images: bool = False,
    output_format: str = 'markdown',
    output_dir: str = '.'
) -> dict:
    """
    抓取单篇文章

    Args:
        url: 微信文章 URL
        strategy: 优先策略 (fast/stable/reliable)
        download_images: 是否下载图片
        output_format: 输出格式
        output_dir: 输出目录

    Returns:
        dict: 抓取结果
    """
    # 清理 URL，添加 ?scene=1 参数
    url = _prepare_url(url)

    # 选择策略
    prefer = None
    if strategy:
        strategy_map = {
            'fast': Strategy.FAST,
            'stable': Strategy.STABLE,
            'reliable': Strategy.RELIABLE,
        }
        prefer = strategy_map.get(strategy)

    # 路由到最佳策略
    router = StrategyRouter()
    result = router.route(url, prefer_strategy=prefer)

    if not result.success:
        return {
            'success': False,
            'error': result.error,
            'strategy': result.strategy.value
        }

    data = result.data or {}
    data['source_url'] = url
    data['strategy_used'] = result.strategy.value

    # 下载图片
    if download_images and data.get('images'):
        print("下载图片中...", file=sys.stderr)
        from images import ImageDownloader

        img_dir = Path(output_dir) / "images"
        downloader = ImageDownloader(str(img_dir))

        results = downloader.download_images(data['images'])

        # 更新 Markdown 内容中的图片链接
        if 'content' in data:
            # 构造临时 markdown 内容
            md_content = data['content']
            updated_md = downloader.update_markdown_images(md_content, results)
            # 提取正文部分
            data['content'] = updated_md

        # 更新图片信息
        data['images_downloaded'] = [
            {'url': r.url, 'local_path': r.local_path, 'status': r.status}
            for r in results
        ]

    # 导出
    from export import Exporter

    exporter = Exporter(output_dir=output_dir)

    # 生成文件名
    title = data.get('title', 'untitled')
    safe_title = "".join(c for c in title if c.isalnum() or c in ' _-').strip()
    if not safe_title:
        safe_title = 'wechat_article'

    output_path = exporter.save(data, format=output_format, filename=safe_title)

    return {
        'success': True,
        'output_path': output_path,
        'strategy': result.strategy.value,
        'title': data.get('title'),
        'author': data.get('author'),
    }


def _prepare_url(url: str) -> str:
    """
    准备 URL：添加 ?scene=1 参数绕过反爬

    这是关键技巧：scene=1 参数可以显著降低触发验证码的概率
    """
    # 移除可能的跟踪参数
    url = url.split('#')[0]  # 移除 hash

    # 添加 scene=1 参数
    if '?' not in url:
        url = url + '?scene=1'
    elif 'scene=' not in url:
        url = url + '&scene=1'

    return url


def main():
    parser = argparse.ArgumentParser(
        description='微信公众号文章抓取工具 v2.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "https://mp.weixin.qq.com/s/xxxxx"
  %(prog)s "https://mp.weixin.qq.com/s/xxxxx" -s reliable --download-images
  %(prog)s "https://mp.weixin.qq.com/s/xxxxx" -f pdf -o ./articles/

策略说明:
  fast     - HTTP + BeautifulSoup，最快但可能被拦截
  stable   - Playwright，稳定但需要安装
  reliable - Chrome DevTools MCP，最可靠但需要登录态
        """
    )

    parser.add_argument(
        'url',
        help='微信文章 URL'
    )
    parser.add_argument(
        '-s', '--strategy',
        choices=['fast', 'stable', 'reliable'],
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
        default='.',
        help='输出目录 (默认: 当前目录)'
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

    args = parser.parse_args()

    # 执行抓取
    result = scrape_article(
        url=args.url,
        strategy=args.strategy,
        download_images=args.download_images,
        output_format=args.format,
        output_dir=args.output
    )

    # 输出结果
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result['success']:
            print(f"✅ 抓取成功")
            print(f"   文件: {result['output_path']}")
            print(f"   策略: {result['strategy']}")
            print(f"   标题: {result['title']}")
        else:
            print(f"❌ 抓取失败: {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
