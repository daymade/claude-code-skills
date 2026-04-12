#!/usr/bin/env python3
"""
语义搜索模块 - 基于向量相似度的智能搜索

功能：
- 语义搜索：理解查询意图，返回语义相关结果
- 相似文章推荐：基于内容相似度推荐
- 内容聚类：自动发现文章主题群
- 混合搜索：结合关键词和语义搜索

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from collections import defaultdict

from vector_store import VectorStore, SearchResult

logger = logging.getLogger('semantic-search')


@dataclass
class SemanticSearchResult:
    """语义搜索结果"""
    id: str
    title: str
    content_preview: str
    account_name: str
    publish_time: str
    similarity_score: float
    matched_keywords: List[str]


@dataclass
class ClusterResult:
    """聚类结果"""
    cluster_id: int
    topic: str
    keywords: List[str]
    article_count: int
    sample_articles: List[str]


class SemanticSearch:
    """语义搜索引擎"""

    def __init__(self, articles_db: str = None, vector_db: str = None):
        """
        初始化语义搜索引擎

        Args:
            articles_db: 文章数据库路径
            vector_db: 向量数据库路径
        """
        if articles_db is None:
            articles_db = str(Path.home() / ".wechat-scraper" / "articles.db")

        self.articles_db = articles_db
        self.vector_store = VectorStore(vector_db)

    def index_articles(self, limit: int = 1000, force_reindex: bool = False) -> int:
        """
        索引文章到向量存储

        Args:
            limit: 最大索引数量
            force_reindex: 强制重新索引

        Returns:
            索引的文章数量
        """
        conn = sqlite3.connect(self.articles_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if force_reindex:
            cursor.execute("""
                SELECT id, title, content, account_name, publish_time
                FROM articles
                WHERE content IS NOT NULL
                LIMIT ?
            """, (limit,))
        else:
            # 只索引未索引的文章
            cursor.execute("""
                SELECT a.id, a.title, a.content, a.account_name, a.publish_time
                FROM articles a
                LEFT JOIN document_embeddings e ON a.id = e.id
                WHERE a.content IS NOT NULL AND e.id IS NULL
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        indexed = 0
        for row in rows:
            content = f"{row['title']}\n\n{row['content'] or ''}"
            metadata = {
                "title": row["title"],
                "account_name": row["account_name"],
                "publish_time": row["publish_time"]
            }

            if self.vector_store.add_document(row["id"], content, metadata):
                indexed += 1
                if indexed % 10 == 0:
                    logger.info(f"已索引 {indexed}/{len(rows)} 篇文章")

        return indexed

    def search(self, query: str, top_k: int = 10,
               account_filter: str = None,
               date_range: tuple = None) -> List[SemanticSearchResult]:
        """
        语义搜索

        Args:
            query: 搜索查询（支持自然语言）
            top_k: 返回结果数量
            account_filter: 按公众号筛选
            date_range: 日期范围 (start_date, end_date)

        Returns:
            语义搜索结果列表
        """
        # 构建元数据过滤条件
        filter_metadata = {}
        if account_filter:
            filter_metadata["account_name"] = account_filter

        # 执行向量搜索
        results = self.vector_store.search(query, top_k=top_k * 2,
                                           filter_metadata=filter_metadata)

        # 获取完整文章信息
        semantic_results = []
        conn = sqlite3.connect(self.articles_db)
        conn.row_factory = sqlite3.Row

        for result in results[:top_k]:
            cursor = conn.execute(
                "SELECT title, content, account_name, publish_time FROM articles WHERE id = ?",
                (result.id,)
            )
            row = cursor.fetchone()

            if row:
                # 提取匹配的关键词
                matched_keywords = self._extract_matched_keywords(query, row["content"] or "")

                semantic_results.append(SemanticSearchResult(
                    id=result.id,
                    title=row["title"] or "无标题",
                    content_preview=(row["content"] or "")[:200] + "...",
                    account_name=row["account_name"] or "未知",
                    publish_time=row["publish_time"] or "",
                    similarity_score=result.score,
                    matched_keywords=matched_keywords
                ))

        conn.close()
        return semantic_results

    def _extract_matched_keywords(self, query: str, content: str) -> List[str]:
        """提取匹配的关键词"""
        query_words = set(query.lower().split())
        content_lower = content.lower()

        matched = []
        for word in query_words:
            if len(word) > 2 and word in content_lower:
                matched.append(word)

        return matched[:5]

    def find_similar_articles(self, article_id: str, top_k: int = 5) -> List[SemanticSearchResult]:
        """
        查找相似文章

        Args:
            article_id: 参考文章ID
            top_k: 返回数量

        Returns:
            相似文章列表
        """
        # 获取相似文档
        similar_docs = self.vector_store.find_similar(article_id, top_k=top_k + 1)

        # 过滤掉参考文章本身
        similar_docs = [d for d in similar_docs if d.id != article_id][:top_k]

        # 获取完整信息
        results = []
        conn = sqlite3.connect(self.articles_db)
        conn.row_factory = sqlite3.Row

        for doc in similar_docs:
            cursor = conn.execute(
                "SELECT title, content, account_name, publish_time, url FROM articles WHERE id = ?",
                (doc.id,)
            )
            row = cursor.fetchone()

            if row:
                results.append(SemanticSearchResult(
                    id=doc.id,
                    title=row["title"] or "无标题",
                    content_preview=(row["content"] or "")[:200] + "...",
                    account_name=row["account_name"] or "未知",
                    publish_time=row["publish_time"] or "",
                    similarity_score=doc.score,
                    matched_keywords=[]
                ))

        conn.close()
        return results

    def cluster_articles(self, n_clusters: int = 5) -> List[ClusterResult]:
        """
        对文章进行聚类分析

        Args:
            n_clusters: 聚类数量

        Returns:
            聚类结果列表
        """
        # 获取所有文档
        stats = self.vector_store.get_stats()
        total = stats["total_documents"]

        if total < n_clusters:
            return []

        # 简化版聚类 - 基于AI分析结果的分类
        conn = sqlite3.connect(self.articles_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM articles
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
            LIMIT ?
        """, (n_clusters,))

        clusters = []
        for i, row in enumerate(cursor.fetchall(), 1):
            category = row["category"]
            count = row["count"]

            # 获取该分类的样本文章
            cursor2 = conn.execute("""
                SELECT title FROM articles
                WHERE category = ?
                LIMIT 3
            """, (category,))

            samples = [r["title"] for r in cursor2.fetchall()]

            clusters.append(ClusterResult(
                cluster_id=i,
                topic=category,
                keywords=[category],
                article_count=count,
                sample_articles=samples
            ))

        conn.close()
        return clusters

    def hybrid_search(self, keywords: str, semantic_query: str,
                      top_k: int = 10) -> List[SemanticSearchResult]:
        """
        混合搜索 - 结合关键词搜索和语义搜索

        Args:
            keywords: 关键词（用于精确匹配）
            semantic_query: 语义查询（用于相似度匹配）
            top_k: 返回数量

        Returns:
            混合搜索结果
        """
        # 获取语义搜索结果
        semantic_results = self.search(semantic_query, top_k=top_k * 2)

        # 关键词过滤
        keyword_list = [k.strip() for k in keywords.split() if k.strip()]

        filtered_results = []
        for result in semantic_results:
            content = result.content_preview.lower()
            title = result.title.lower()

            # 检查是否包含所有关键词
            if all(kw.lower() in content or kw.lower() in title for kw in keyword_list):
                # 提升包含关键词的结果的分数
                result.similarity_score *= 1.2
                filtered_results.append(result)

        # 按分数排序并返回top_k
        filtered_results.sort(key=lambda x: x.similarity_score, reverse=True)
        return filtered_results[:top_k]


def main():
    """CLI入口"""
    parser = argparse.ArgumentParser(
        description='语义搜索模块',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 索引文章
  %(prog)s index --limit 1000

  # 语义搜索
  %(prog)s search "人工智能发展趋势" --top-k 10

  # 查找相似文章
  %(prog)s similar <article_id> --top-k 5

  # 聚类分析
  %(prog)s cluster --clusters 5

  # 混合搜索
  %(prog)s hybrid --keywords "AI 大模型" --query "技术发展"
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # index 命令
    index_parser = subparsers.add_parser('index', help='索引文章')
    index_parser.add_argument('--limit', type=int, default=1000, help='最大数量')
    index_parser.add_argument('--force', action='store_true', help='强制重新索引')

    # search 命令
    search_parser = subparsers.add_parser('search', help='语义搜索')
    search_parser.add_argument('query', help='搜索查询')
    search_parser.add_argument('-k', '--top-k', type=int, default=10, help='返回数量')
    search_parser.add_argument('--account', help='公众号筛选')

    # similar 命令
    similar_parser = subparsers.add_parser('similar', help='查找相似文章')
    similar_parser.add_argument('id', help='参考文章ID')
    similar_parser.add_argument('-k', '--top-k', type=int, default=5, help='返回数量')

    # cluster 命令
    cluster_parser = subparsers.add_parser('cluster', help='聚类分析')
    cluster_parser.add_argument('--clusters', type=int, default=5, help='聚类数量')

    # hybrid 命令
    hybrid_parser = subparsers.add_parser('hybrid', help='混合搜索')
    hybrid_parser.add_argument('--keywords', required=True, help='关键词')
    hybrid_parser.add_argument('--query', required=True, help='语义查询')
    hybrid_parser.add_argument('-k', '--top-k', type=int, default=10, help='返回数量')

    # stats 命令
    subparsers.add_parser('stats', help='统计信息')

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if not args.command:
        parser.print_help()
        return

    searcher = SemanticSearch()

    if args.command == 'index':
        print(f"开始索引文章，最多 {args.limit} 篇...")
        count = searcher.index_articles(limit=args.limit, force_reindex=args.force)
        print(f"✓ 成功索引 {count} 篇文章")

    elif args.command == 'search':
        results = searcher.search(
            args.query,
            top_k=args.top_k,
            account_filter=args.account
        )

        print(f"\n🔍 语义搜索: {args.query}")
        print(f"找到 {len(results)} 个相关结果:\n")

        for i, r in enumerate(results, 1):
            print(f"{i}. [{r.similarity_score:.2%}] {r.title}")
            print(f"   公众号: {r.account_name}")
            print(f"   预览: {r.content_preview[:100]}...")
            if r.matched_keywords:
                print(f"   关键词: {', '.join(r.matched_keywords)}")
            print()

    elif args.command == 'similar':
        results = searcher.find_similar_articles(args.id, top_k=args.top_k)

        print(f"\n📎 与文章 {args.id} 相似的内容:\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r.similarity_score:.2%}] {r.title}")
            print(f"   公众号: {r.account_name}")
            print()

    elif args.command == 'cluster':
        clusters = searcher.cluster_articles(n_clusters=args.clusters)

        print(f"\n📊 文章聚类分析 ({len(clusters)} 个主题):\n")
        for c in clusters:
            print(f"主题 {c.cluster_id}: {c.topic}")
            print(f"  文章数: {c.article_count}")
            print(f"  示例: {', '.join(c.sample_articles[:3])}")
            print()

    elif args.command == 'hybrid':
        results = searcher.hybrid_search(
            args.keywords,
            args.query,
            top_k=args.top_k
        )

        print(f"\n🔍 混合搜索: 关键词='{args.keywords}', 语义='{args.query}'")
        print(f"找到 {len(results)} 个结果:\n")

        for i, r in enumerate(results, 1):
            print(f"{i}. [{r.similarity_score:.2%}] {r.title}")
            print(f"   公众号: {r.account_name}")
            print()

    elif args.command == 'stats':
        stats = searcher.vector_store.get_stats()
        print(json.dumps(stats, indent=2))


if __name__ == '__main__':
    main()
