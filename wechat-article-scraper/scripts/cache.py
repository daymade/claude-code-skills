#!/usr/bin/env python3
"""
微信文章缓存系统 - SQLite 本地存储

功能：
- 缓存已抓取的文章内容
- URL 去重（避免重复抓取）
- 内容指纹去重（相同内容不同 URL）
- 增量更新支持
- 缓存过期管理

作者: Claude Code
版本: 3.1.0
"""

import os
import re
import json
import hashlib
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from contextlib import contextmanager

logger = logging.getLogger('wechat-cache')


@dataclass
class ArticleCache:
    """文章缓存记录"""
    url: str
    url_hash: str
    content_hash: str
    title: str
    author: str
    content: str
    html: str
    images: str  # JSON string
    videos: str  # JSON string
    engagement: str  # JSON string
    strategy: str
    created_at: str
    updated_at: str
    access_count: int = 0
    expires_at: Optional[str] = None


class CacheManager:
    """
    缓存管理器

    吸取竞品精华：
    - fetch-wx-article: 使用 SQLite 本地缓存
    - camofox: 内容指纹去重
    - wechat-mp-reader: URL 标准化
    """

    def __init__(self, cache_dir: Optional[str] = None, ttl_days: int = 30):
        """
        初始化缓存管理器

        Args:
            cache_dir: 缓存目录（默认 ~/.wechat-scraper/cache）
            ttl_days: 缓存过期时间（天）
        """
        if cache_dir is None:
            cache_dir = os.path.expanduser("~/.wechat-scraper/cache")

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
        self.db_path = self.cache_dir / "articles.db"

        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    title TEXT,
                    author TEXT,
                    content TEXT,
                    html TEXT,
                    images TEXT,
                    videos TEXT,
                    engagement TEXT,
                    strategy TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    expires_at TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_content_hash
                ON articles(content_hash)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires
                ON articles(expires_at)
            """)

            conn.commit()

    @contextmanager
    def _get_conn(self):
        """获取数据库连接（上下文管理器）"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
        finally:
            conn.close()

    def _normalize_url(self, url: str) -> str:
        """
        URL 标准化

        吸取 wechat-mp-reader 精华：
        - 移除追踪参数
        - 统一 scene 参数
        """
        # 移除 hash
        url = url.split('#')[0]

        # 确保 scene=1 存在（但不作为 hash 的一部分）
        # 因为 scene 参数不影响文章内容
        return url

    def _compute_url_hash(self, url: str) -> str:
        """计算 URL 的哈希值"""
        normalized = self._normalize_url(url)
        return hashlib.sha256(normalized.encode()).hexdigest()[:32]

    def _compute_content_hash(self, data: Dict[str, Any]) -> str:
        """
        计算内容指纹

        吸取 camofox 精华：
        - 基于标题 + 作者 + 内容前 500 字生成指纹
        - 用于检测相同内容的不同 URL
        """
        title = data.get('title', '')
        author = data.get('author', '')
        content = data.get('content', '')[:500]  # 前 500 字

        fingerprint = f"{title}|{author}|{content}"
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:32]

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的文章

        Args:
            url: 文章 URL

        Returns:
            缓存的文章数据，或 None（未缓存或已过期）
        """
        url_hash = self._compute_url_hash(url)

        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM articles WHERE url_hash = ?",
                (url_hash,)
            ).fetchone()

            if not row:
                return None

            # 检查是否过期
            expires_at = row[14]
            if expires_at and datetime.now().isoformat() > expires_at:
                logger.debug(f"缓存已过期: {url[:60]}...")
                return None

            # 更新访问计数
            conn.execute(
                "UPDATE articles SET access_count = access_count + 1 WHERE url_hash = ?",
                (url_hash,)
            )
            conn.commit()

            logger.info(f"缓存命中: {url[:60]}...")

            return {
                'url': row[1],
                'title': row[3],
                'author': row[4],
                'content': row[5],
                'html': row[6],
                'images': json.loads(row[7]) if row[7] else [],
                'videos': json.loads(row[8]) if row[8] else [],
                'engagement': json.loads(row[9]) if row[9] else {},
                'strategy': row[10],
                'cached_at': row[11],
                'access_count': row[14],
            }

    def find_by_content(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        通过内容指纹查找（检测相同内容的不同 URL）

        Args:
            data: 文章数据

        Returns:
            缓存的文章数据，或 None
        """
        content_hash = self._compute_content_hash(data)

        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM articles WHERE content_hash = ? LIMIT 1",
                (content_hash,)
            ).fetchone()

            if row:
                logger.info(f"内容指纹匹配: {data.get('title', 'Unknown')}")
                return {
                    'url': row[1],
                    'title': row[3],
                    'author': row[4],
                    'content': row[5],
                    'cached_at': row[11],
                }

        return None

    def set(self, url: str, data: Dict[str, Any], strategy: str = "unknown"):
        """
        缓存文章

        Args:
            url: 文章 URL
            data: 文章数据
            strategy: 使用的抓取策略
        """
        url_hash = self._compute_url_hash(url)
        content_hash = self._compute_content_hash(data)

        now = datetime.now().isoformat()
        expires = (datetime.now() + timedelta(days=self.ttl_days)).isoformat()

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO articles
                (url_hash, url, content_hash, title, author, content, html,
                 images, videos, engagement, strategy, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    url_hash,
                    url,
                    content_hash,
                    data.get('title', ''),
                    data.get('author', ''),
                    data.get('content', ''),
                    data.get('html', ''),
                    json.dumps(data.get('images', []), ensure_ascii=False),
                    json.dumps(data.get('videos', []), ensure_ascii=False),
                    json.dumps(data.get('engagement', {}), ensure_ascii=False),
                    strategy,
                    now,
                    now,
                    expires,
                )
            )
            conn.commit()

        logger.info(f"已缓存: {url[:60]}...")

    def exists(self, url: str) -> bool:
        """检查 URL 是否已缓存（未过期）"""
        return self.get(url) is not None

    def delete(self, url: str) -> bool:
        """删除缓存"""
        url_hash = self._compute_url_hash(url)

        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM articles WHERE url_hash = ?",
                (url_hash,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def clear_expired(self) -> int:
        """清理过期缓存，返回删除数量"""
        now = datetime.now().isoformat()

        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM articles WHERE expires_at < ?",
                (now,)
            )
            conn.commit()
            count = cursor.rowcount

        if count > 0:
            logger.info(f"清理了 {count} 条过期缓存")
        return count

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM articles"
            ).fetchone()[0]

            expired = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE expires_at < ?",
                (datetime.now().isoformat(),)
            ).fetchone()[0]

            total_access = conn.execute(
                "SELECT SUM(access_count) FROM articles"
            ).fetchone()[0] or 0

            by_strategy = conn.execute(
                "SELECT strategy, COUNT(*) FROM articles GROUP BY strategy"
            ).fetchall()

        return {
            'total_cached': total,
            'expired': expired,
            'total_access': total_access,
            'by_strategy': dict(by_strategy),
            'cache_dir': str(self.cache_dir),
            'db_size_mb': round(self.db_path.stat().st_size / (1024 * 1024), 2) if self.db_path.exists() else 0,
        }

    def list_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        """列出所有缓存的文章"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT url, title, author, strategy, created_at, access_count
                FROM articles
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

        return [
            {
                'url': row[0],
                'title': row[1],
                'author': row[2],
                'strategy': row[3],
                'cached_at': row[4],
                'access_count': row[5],
            }
            for row in rows
        ]


def main():
    """CLI 工具"""
    import argparse

    parser = argparse.ArgumentParser(description='微信文章缓存管理')
    parser.add_argument('--stats', action='store_true', help='显示缓存统计')
    parser.add_argument('--list', action='store_true', help='列出缓存文章')
    parser.add_argument('--clear-expired', action='store_true', help='清理过期缓存')
    parser.add_argument('--clear-all', action='store_true', help='清空所有缓存')
    parser.add_argument('--get', metavar='URL', help='获取指定 URL 的缓存')

    args = parser.parse_args()

    cache = CacheManager()

    if args.stats:
        stats = cache.get_stats()
        print(f"缓存统计:")
        print(f"  总数: {stats['total_cached']}")
        print(f"  过期: {stats['expired']}")
        print(f"  总访问: {stats['total_access']}")
        print(f"  数据库大小: {stats['db_size_mb']} MB")
        print(f"  按策略:")
        for strategy, count in stats['by_strategy'].items():
            print(f"    - {strategy}: {count}")

    elif args.list:
        articles = cache.list_all()
        print(f"最近 {len(articles)} 条缓存:")
        for article in articles:
            print(f"  - {article['title'][:40]}... ({article['strategy']}, 访问{article['access_count']}次)")

    elif args.clear_expired:
        count = cache.clear_expired()
        print(f"清理了 {count} 条过期缓存")

    elif args.clear_all:
        confirm = input("确定要清空所有缓存吗？输入 'yes' 确认: ")
        if confirm == 'yes':
            cache.db_path.unlink()
            print("缓存已清空")
        else:
            print("操作已取消")

    elif args.get:
        data = cache.get(args.get)
        if data:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print("未找到缓存")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
