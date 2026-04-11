#!/usr/bin/env python3
"""
RSS Feed 生成器 - 为抓取的微信文章生成 RSS 订阅源

功能：
- 从 SQLite 数据库生成 RSS 2.0 feed
- 支持按作者、分类筛选
- 支持全文输出或摘要输出
- 自动更新机制
- 符合 RSS 2.0 规范

吸取竞品精华：
- wcplusPro: RSS 订阅功能
- WordPress: RSS 字段规范

作者: Claude Code
版本: 1.0.0
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('wechat-rss')


class RSSGenerator:
    """RSS Feed 生成器"""

    def __init__(self, db_path: str, base_url: str = "http://localhost:8000"):
        self.db_path = db_path
        self.base_url = base_url
        self.feed_dir = Path(db_path).parent / "feeds"
        self.feed_dir.mkdir(exist_ok=True)

    def _escape_xml(self, text: str) -> str:
        """转义 XML 特殊字符"""
        if not text:
            return ""
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))

    def _format_rfc822(self, dt: datetime) -> str:
        """格式化为 RFC 822 日期格式"""
        if not dt:
            dt = datetime.now(timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S %z")

    def _create_rss_item(self, article: Dict, full_text: bool = False) -> Element:
        """创建 RSS item 元素"""
        item = Element('item')

        # 标题
        title = SubElement(item, 'title')
        title.text = article.get('title', '无标题')

        # 链接
        link = SubElement(item, 'link')
        link.text = article.get('url', '')

        # 描述（摘要或全文）
        description = SubElement(item, 'description')
        content = article.get('content', '')
        if full_text and content:
            # 全文输出，转换为 HTML
            desc_text = f"<![CDATA[{content}]]>"
        else:
            # 摘要输出
            desc_text = content[:300] + "..." if len(content) > 300 else content
            desc_text = self._escape_xml(desc_text)
        description.text = desc_text

        # 作者
        author = SubElement(item, 'author')
        author.text = article.get('author', 'Unknown')

        # DC:Creator ( Dublin Core )
        dc_creator = SubElement(item, '{http://purl.org/dc/elements/1.1/}creator')
        dc_creator.text = article.get('author', 'Unknown')

        # 发布日期
        pub_date = SubElement(item, 'pubDate')
        publish_time = article.get('publish_time')
        if publish_time:
            try:
                dt = datetime.fromisoformat(publish_time.replace('Z', '+00:00'))
                pub_date.text = self._format_rfc822(dt)
            except:
                pub_date.text = self._format_rfc822(datetime.now())
        else:
            pub_date.text = self._format_rfc822(datetime.now())

        # GUID (唯一标识)
        guid = SubElement(item, 'guid')
        guid.set('isPermaLink', 'true')
        guid.text = article.get('url', '')

        # 分类
        category = article.get('category')
        if category:
            cat_elem = SubElement(item, 'category')
            cat_elem.text = category

        # 互动数据 (media:group)
        if article.get('engagement'):
            engagement = article.get('engagement', {})
            read_count = engagement.get('readCount', 0)
            like_count = engagement.get('likeCount', 0)

            # 使用 content:encoded 扩展
            content_encoded = SubElement(item, '{http://purl.org/rss/1.0/modules/content/}encoded')
            stats_html = f"""
            <div style="margin-top: 20px; padding: 10px; background: #f5f5f5; border-radius: 5px;">
                <p><strong>阅读量:</strong> {read_count} | <strong>点赞:</strong> {like_count}</p>
            </div>
            """
            if full_text and content:
                content_encoded.text = f"<![CDATA[{content}{stats_html}]]>"
            else:
                content_encoded.text = f"<![CDATA[{stats_html}]]>"

        return item

    def generate_feed(
        self,
        feed_name: str = "wechat-articles",
        title: str = "微信公众号文章",
        description: str = "抓取的微信公众号文章 RSS Feed",
        author: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
        full_text: bool = True
    ) -> str:
        """
        生成 RSS Feed

        Args:
            feed_name: Feed 文件名（不含扩展名）
            title: Feed 标题
            description: Feed 描述
            author: 筛选特定作者
            category: 筛选特定分类
            limit: 最大文章数
            full_text: 是否输出全文

        Returns:
            生成的 RSS 文件路径
        """
        try:
            # 导入 storage 模块获取数据
            sys.path.insert(0, str(Path(__file__).parent))
            from storage import ArticleStorage

            storage = ArticleStorage(self.db_path)

            # 获取文章列表
            articles = storage.list_articles(
                author=author,
                category=category,
                limit=limit
            )

            if not articles:
                logger.warning("数据库中没有文章，生成空 feed")

            # 创建 RSS 根元素
            rss = Element('rss')
            rss.set('version', '2.0')
            rss.set('xmlns:atom', 'http://www.w3.org/2005/Atom')
            rss.set('xmlns:dc', 'http://purl.org/dc/elements/1.1/')
            rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')

            # 创建 channel
            channel = SubElement(rss, 'channel')

            # Feed 基本信息
            feed_title = SubElement(channel, 'title')
            feed_title.text = title

            feed_link = SubElement(channel, 'link')
            feed_link.text = self.base_url

            feed_desc = SubElement(channel, 'description')
            feed_desc.text = description

            feed_lang = SubElement(channel, 'language')
            feed_lang.text = 'zh-CN'

            feed_date = SubElement(channel, 'lastBuildDate')
            feed_date.text = self._format_rfc822(datetime.now())

            feed_generator = SubElement(channel, 'generator')
            feed_generator.text = 'wechat-article-scraper RSS Generator v1.0'

            # Atom 自引用链接
            atom_link = SubElement(channel, '{http://www.w3.org/2005/Atom}link')
            atom_link.set('href', f"{self.base_url}/feeds/{feed_name}.xml")
            atom_link.set('rel', 'self')
            atom_link.set('type', 'application/rss+xml')

            # 添加文章 items
            for article in articles:
                item = self._create_rss_item(article, full_text=full_text)
                channel.append(item)

            # 格式化 XML
            rough_string = tostring(rss, encoding='unicode')
            reparsed = minidom.parseString(rough_string.encode('utf-8'))
            pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8')

            # 保存文件
            output_file = self.feed_dir / f"{feed_name}.xml"
            output_file.write_bytes(pretty_xml)

            logger.info(f"RSS feed 已生成: {output_file}")
            logger.info(f"包含 {len(articles)} 篇文章")

            return str(output_file)

        except Exception as e:
            logger.error(f"生成 RSS feed 失败: {e}")
            raise

    def generate_author_feeds(self) -> List[str]:
        """为每个作者生成单独的 RSS feed"""
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from storage import ArticleStorage

            storage = ArticleStorage(self.db_path)
            stats = storage.get_statistics()

            generated_files = []

            for author_info in stats.get('top_authors', []):
                author = author_info.get('author')
                if author:
                    # 清理作者名作为文件名
                    safe_name = "".join(c if c.isalnum() else "_" for c in author)
                    file_path = self.generate_feed(
                        feed_name=f"author_{safe_name}",
                        title=f"{author} - 微信公众号文章",
                        description=f"{author} 的微信公众号文章 RSS Feed",
                        author=author,
                        limit=100
                    )
                    generated_files.append(file_path)

            return generated_files

        except Exception as e:
            logger.error(f"生成作者 feeds 失败: {e}")
            raise

    def generate_category_feeds(self) -> List[str]:
        """为每个分类生成单独的 RSS feed"""
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from storage import ArticleStorage

            storage = ArticleStorage(self.db_path)
            stats = storage.get_statistics()

            generated_files = []

            for cat_info in stats.get('category_distribution', []):
                category = cat_info.get('category')
                if category:
                    safe_name = "".join(c if c.isalnum() else "_" for c in category)
                    file_path = self.generate_feed(
                        feed_name=f"category_{safe_name}",
                        title=f"{category} - 微信公众号文章",
                        description=f"分类 {category} 的微信公众号文章 RSS Feed",
                        category=category,
                        limit=100
                    )
                    generated_files.append(file_path)

            return generated_files

        except Exception as e:
            logger.error(f"生成分类 feeds 失败: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(
        description='为微信文章生成 RSS Feed'
    )
    parser.add_argument(
        '--db',
        default='wechat_articles.db',
        help='SQLite 数据库路径 (默认: wechat_articles.db)'
    )
    parser.add_argument(
        '--name',
        default='wechat-articles',
        help='Feed 文件名 (默认: wechat-articles)'
    )
    parser.add_argument(
        '--title',
        default='微信公众号文章',
        help='Feed 标题'
    )
    parser.add_argument(
        '--author',
        help='筛选特定作者'
    )
    parser.add_argument(
        '--category',
        help='筛选特定分类'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='最大文章数 (默认: 50)'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='输出摘要而非全文'
    )
    parser.add_argument(
        '--all-authors',
        action='store_true',
        help='为每个作者生成单独的 feed'
    )
    parser.add_argument(
        '--all-categories',
        action='store_true',
        help='为每个分类生成单独的 feed'
    )
    parser.add_argument(
        '--base-url',
        default='http://localhost:8000',
        help='Feed 基础 URL'
    )

    args = parser.parse_args()

    generator = RSSGenerator(args.db, args.base_url)

    if args.all_authors:
        files = generator.generate_author_feeds()
        print(f"已为 {len(files)} 个作者生成 RSS feed:")
        for f in files:
            print(f"  - {f}")

    elif args.all_categories:
        files = generator.generate_category_feeds()
        print(f"已为 {len(files)} 个分类生成 RSS feed:")
        for f in files:
            print(f"  - {f}")

    else:
        file_path = generator.generate_feed(
            feed_name=args.name,
            title=args.title,
            author=args.author,
            category=args.category,
            limit=args.limit,
            full_text=not args.summary
        )
        print(f"RSS feed 已生成: {file_path}")


if __name__ == '__main__':
    main()
