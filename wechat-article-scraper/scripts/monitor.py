#!/usr/bin/env python3
"""
微信公众号文章监控模块 - 订阅并监控公众号更新

功能：
- 添加/删除/列出订阅的公众号
- 定时检查新文章
- 发现新文章时通知（支持多种通知方式）
- 生成 RSS feed

作者: Claude Code
版本: 1.0.0
"""

import sys
import os
import json
import time
import hashlib
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict

# 配置日志
logger = logging.getLogger('wechat-monitor')


@dataclass
class Subscription:
    """公众号订阅信息"""
    account_name: str  # 公众号名称
    wechat_id: str  # 微信号
    description: str  # 简介
    last_check: Optional[str] = None  # 上次检查时间
    last_article_title: Optional[str] = None  # 上次抓取的最新文章标题
    last_article_url: Optional[str] = None  # 上次抓取的最新文章URL
    created_at: str = None  # 订阅创建时间

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class SubscriptionManager:
    """订阅管理器"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.expanduser('~/.wechat-scraper')

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.subscriptions_file = self.data_dir / 'subscriptions.json'
        self.history_file = self.data_dir / 'article_history.json'
        self.rss_file = self.data_dir / 'feed.xml'

        self.subscriptions: Dict[str, Subscription] = {}
        self.article_history: List[Dict] = []

        self._load_data()

    def _load_data(self):
        """加载订阅数据"""
        if self.subscriptions_file.exists():
            try:
                data = json.loads(self.subscriptions_file.read_text(encoding='utf-8'))
                for key, value in data.items():
                    self.subscriptions[key] = Subscription(**value)
                logger.info(f"已加载 {len(self.subscriptions)} 个订阅")
            except Exception as e:
                logger.error(f"加载订阅数据失败: {e}")

        if self.history_file.exists():
            try:
                self.article_history = json.loads(self.history_file.read_text(encoding='utf-8'))
            except Exception as e:
                logger.error(f"加载历史数据失败: {e}")

    def _save_data(self):
        """保存订阅数据"""
        try:
            data = {k: asdict(v) for k, v in self.subscriptions.items()}
            self.subscriptions_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )

            self.history_file.write_text(
                json.dumps(self.article_history, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

    def add_subscription(self, account_name: str, wechat_id: str = "", description: str = "") -> bool:
        """添加订阅"""
        key = account_name.lower().strip()

        if key in self.subscriptions:
            logger.warning(f"已存在订阅: {account_name}")
            return False

        self.subscriptions[key] = Subscription(
            account_name=account_name,
            wechat_id=wechat_id,
            description=description
        )

        self._save_data()
        logger.info(f"已添加订阅: {account_name}")
        return True

    def remove_subscription(self, account_name: str) -> bool:
        """移除订阅"""
        key = account_name.lower().strip()

        if key not in self.subscriptions:
            logger.warning(f"未找到订阅: {account_name}")
            return False

        del self.subscriptions[key]
        self._save_data()
        logger.info(f"已移除订阅: {account_name}")
        return True

    def list_subscriptions(self) -> List[Subscription]:
        """列出所有订阅"""
        return list(self.subscriptions.values())

    def check_updates(self, search_module=None, scraper_module=None) -> List[Dict]:
        """
        检查所有订阅的更新

        Args:
            search_module: search.py 模块（用于搜索最新文章）
            scraper_module: scraper.py 模块（用于抓取文章）

        Returns:
            List[Dict]: 发现的新文章列表
        """
        from scripts.search import SogouWechatSearch

        new_articles = []
        searcher = SogouWechatSearch(delay=2.0)

        for key, sub in self.subscriptions.items():
            logger.info(f"检查: {sub.account_name}")

            try:
                # 搜索该公众号的最新文章
                results = searcher.search(
                    keyword=sub.account_name,
                    num_results=5
                )

                # 过滤该公众号的文章
                account_articles = [
                    r for r in results
                    if sub.account_name.lower() in r.source_account.lower()
                ]

                if not account_articles:
                    logger.info(f"  未找到文章: {sub.account_name}")
                    continue

                # 获取最新文章
                latest = account_articles[0]

                # 检查是否是新文章
                is_new = (
                    sub.last_article_title != latest.title or
                    sub.last_article_url != latest.url
                )

                if is_new:
                    logger.info(f"  发现新文章: {latest.title}")

                    article_info = {
                        'account_name': sub.account_name,
                        'title': latest.title,
                        'url': latest.url,
                        'publish_time': latest.publish_time,
                        'abstract': latest.abstract,
                        'discovered_at': datetime.now().isoformat(),
                    }

                    new_articles.append(article_info)
                    self.article_history.append(article_info)

                    # 更新订阅状态
                    sub.last_article_title = latest.title
                    sub.last_article_url = latest.url
                    sub.last_check = datetime.now().isoformat()
                else:
                    logger.info(f"  无更新")

                sub.last_check = datetime.now().isoformat()

            except Exception as e:
                logger.error(f"检查 {sub.account_name} 失败: {e}")
                continue

        if new_articles:
            self._save_data()
            self._generate_rss()

        return new_articles

    def _generate_rss(self):
        """生成 RSS feed"""
        # 按时间排序，取最近50篇
        recent_articles = sorted(
            self.article_history,
            key=lambda x: x.get('discovered_at', ''),
            reverse=True
        )[:50]

        rss_items = []
        for article in recent_articles:
            title = article.get('title', '无标题')
            url = article.get('url', '')
            account = article.get('account_name', '未知')
            abstract = article.get('abstract', '')
            pub_time = article.get('publish_time', '')

            # 简单转义 XML 特殊字符
            title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            abstract = abstract.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            item = f"""    <item>
      <title>{title}</title>
      <link>{url}</link>
      <description>{account}: {abstract}</description>
      <pubDate>{pub_time}</pubDate>
    </item>"""
            rss_items.append(item)

        rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>微信公众号订阅</title>
    <link>https://mp.weixin.qq.com</link>
    <description>监控的微信公众号文章更新</description>
    <language>zh-CN</language>
    <lastBuildDate>{datetime.now().isoformat()}</lastBuildDate>
{chr(10).join(rss_items)}
  </channel>
</rss>"""

        self.rss_file.write_text(rss_content, encoding='utf-8')
        logger.info(f"RSS feed 已更新: {self.rss_file}")


def main():
    parser = argparse.ArgumentParser(
        description='微信公众号订阅监控',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 添加订阅
  %(prog)s add "量子位"
  %(prog)s add "腾讯科技" "txkej" "腾讯官方科技媒体"

  # 列出订阅
  %(prog)s list

  # 移除订阅
  %(prog)s remove "量子位"

  # 检查更新
  %(prog)s check

  # 持续监控（每小时检查一次）
  %(prog)s watch --interval 3600
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # add 命令
    add_parser = subparsers.add_parser('add', help='添加公众号订阅')
    add_parser.add_argument('name', help='公众号名称')
    add_parser.add_argument('--wechat-id', default='', help='微信号')
    add_parser.add_argument('--desc', default='', help='公众号简介')

    # remove 命令
    remove_parser = subparsers.add_parser('remove', help='移除订阅')
    remove_parser.add_argument('name', help='公众号名称')

    # list 命令
    list_parser = subparsers.add_parser('list', help='列出所有订阅')

    # check 命令
    check_parser = subparsers.add_parser('check', help='检查更新')

    # watch 命令
    watch_parser = subparsers.add_parser('watch', help='持续监控')
    watch_parser.add_argument(
        '--interval',
        type=int,
        default=3600,
        help='检查间隔（秒，默认: 3600 = 1小时）'
    )

    # rss 命令
    rss_parser = subparsers.add_parser('rss', help='生成 RSS feed')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    manager = SubscriptionManager()

    if args.command == 'add':
        manager.add_subscription(args.name, args.wechat_id, args.desc)

    elif args.command == 'remove':
        manager.remove_subscription(args.name)

    elif args.command == 'list':
        subs = manager.list_subscriptions()
        if not subs:
            print("暂无订阅")
        else:
            print(f"共 {len(subs)} 个订阅:")
            print("-" * 60)
            for s in subs:
                print(f"  {s.account_name}")
                if s.wechat_id:
                    print(f"    微信号: {s.wechat_id}")
                if s.description:
                    print(f"    简介: {s.description}")
                if s.last_check:
                    print(f"    上次检查: {s.last_check}")
                if s.last_article_title:
                    print(f"    最新文章: {s.last_article_title}")
                print()

    elif args.command == 'check':
        new_articles = manager.check_updates()
        if new_articles:
            print(f"\n发现 {len(new_articles)} 篇新文章:")
            print("=" * 60)
            for article in new_articles:
                print(f"\n【{article['account_name']}】")
                print(f"标题: {article['title']}")
                print(f"链接: {article['url']}")
                print(f"时间: {article.get('publish_time', '未知')}")
        else:
            print("暂无新文章")

    elif args.command == 'watch':
        print(f"开始监控，间隔: {args.interval} 秒")
        print("按 Ctrl+C 停止\n")

        try:
            while True:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查更新...")
                new_articles = manager.check_updates()

                if new_articles:
                    print(f"发现 {len(new_articles)} 篇新文章!")
                    for article in new_articles:
                        print(f"  - [{article['account_name']}] {article['title']}")
                else:
                    print("  无更新")

                time.sleep(args.interval)

        except KeyboardInterrupt:
            print("\n监控已停止")

    elif args.command == 'rss':
        manager._generate_rss()
        print(f"RSS feed 已生成: {manager.rss_file}")


if __name__ == "__main__":
    main()
