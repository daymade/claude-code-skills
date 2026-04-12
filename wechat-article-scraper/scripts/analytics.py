#!/usr/bin/env python3
"""
数据分析引擎 - 为Dashboard提供数据统计和分析

功能：
- 文章数据聚合统计
- 趋势分析计算
- 排名算法
- 时间序列分析

作者: Claude Code
版本: 1.0.0
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict


@dataclass
class ArticleMetrics:
    """文章指标"""
    total_articles: int = 0
    total_reads: int = 0
    total_likes: int = 0
    total_shares: int = 0
    avg_reads: float = 0.0
    avg_likes: float = 0.0
    avg_wci: float = 0.0


@dataclass
class TrendData:
    """趋势数据点"""
    date: str
    value: float
    count: int = 1


@dataclass
class TopArticle:
    """排行榜文章"""
    rank: int
    title: str
    url: str
    account_name: str
    reads: int
    likes: int
    wci: float
    publish_time: str


class AnalyticsEngine:
    """数据分析引擎"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "articles.db")
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_core_metrics(self, days: int = 30) -> Dict[str, Any]:
        """
        获取核心指标

        Args:
            days: 统计天数，默认30天

        Returns:
            核心指标字典
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        # 基础统计
        cursor.execute("""
            SELECT
                COUNT(*) as total_articles,
                SUM(COALESCE(read_count, 0)) as total_reads,
                SUM(COALESCE(like_count, 0)) as total_likes,
                SUM(COALESCE(share_count, 0)) as total_shares,
                AVG(COALESCE(read_count, 0)) as avg_reads,
                AVG(COALESCE(like_count, 0)) as avg_likes,
                AVG(COALESCE(wci_score, 0)) as avg_wci
            FROM articles
            WHERE created_at > ?
        """, (cutoff_date,))

        row = cursor.fetchone()
        conn.close()

        return {
            "period_days": days,
            "total_articles": row["total_articles"] or 0,
            "total_reads": row["total_reads"] or 0,
            "total_likes": row["total_likes"] or 0,
            "total_shares": row["total_shares"] or 0,
            "avg_reads": round(row["avg_reads"] or 0, 2),
            "avg_likes": round(row["avg_likes"] or 0, 2),
            "avg_wci": round(row["avg_wci"] or 0, 2),
        }

    def get_trend_data(self, metric: str = "reads", days: int = 30) -> List[TrendData]:
        """
        获取趋势数据

        Args:
            metric: 指标类型 (reads, likes, wci, articles)
            days: 天数

        Returns:
            趋势数据列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        if metric == "articles":
            cursor.execute("""
                SELECT
                    DATE(publish_time) as date,
                    COUNT(*) as value
                FROM articles
                WHERE publish_time > ?
                GROUP BY DATE(publish_time)
                ORDER BY date
            """, (cutoff_date,))
        elif metric in ["reads", "likes", "wci"]:
            column_map = {
                "reads": "read_count",
                "likes": "like_count",
                "wci": "wci_score"
            }
            column = column_map.get(metric, "read_count")
            cursor.execute(f"""
                SELECT
                    DATE(publish_time) as date,
                    SUM(COALESCE({column}, 0)) as value,
                    COUNT(*) as count
                FROM articles
                WHERE publish_time > ?
                GROUP BY DATE(publish_time)
                ORDER BY date
            """, (cutoff_date,))
        else:
            conn.close()
            return []

        results = []
        for row in cursor.fetchall():
            results.append(TrendData(
                date=row["date"],
                value=row["value"] or 0,
                count=row.get("count", 1)
            ))

        conn.close()

        # 填充缺失日期
        return self._fill_missing_dates(results, days)

    def _fill_missing_dates(self, data: List[TrendData], days: int) -> List[TrendData]:
        """填充缺失日期"""
        if not data:
            return []

        # 创建日期到值的映射
        date_map = {d.date: d for d in data}

        # 生成完整日期范围
        filled = []
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        current = start_date
        while current <= end_date:
            date_str = current.isoformat()
            if date_str in date_map:
                filled.append(date_map[date_str])
            else:
                filled.append(TrendData(date=date_str, value=0, count=0))
            current += timedelta(days=1)

        return filled

    def get_top_articles(self, by: str = "reads", limit: int = 10, days: int = 30) -> List[TopArticle]:
        """
        获取排行榜文章

        Args:
            by: 排序字段 (reads, likes, wci)
            limit: 数量限制
            days: 统计天数

        Returns:
            排行榜文章列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        column_map = {
            "reads": "read_count",
            "likes": "like_count",
            "wci": "wci_score"
        }
        column = column_map.get(by, "read_count")

        cursor.execute(f"""
            SELECT
                title,
                url,
                account_name,
                COALESCE(read_count, 0) as reads,
                COALESCE(like_count, 0) as likes,
                COALESCE(wci_score, 0) as wci,
                publish_time
            FROM articles
            WHERE publish_time > ?
            ORDER BY {column} DESC NULLS LAST
            LIMIT ?
        """, (cutoff_date, limit))

        results = []
        for rank, row in enumerate(cursor.fetchall(), 1):
            results.append(TopArticle(
                rank=rank,
                title=row["title"] or "无标题",
                url=row["url"] or "",
                account_name=row["account_name"] or "未知",
                reads=row["reads"],
                likes=row["likes"],
                wci=round(row["wci"], 2),
                publish_time=row["publish_time"] or ""
            ))

        conn.close()
        return results

    def get_publish_heatmap(self, days: int = 90) -> Dict[str, Any]:
        """
        获取发布日历热力图数据

        Args:
            days: 统计天数

        Returns:
            热力图数据
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                DATE(publish_time) as date,
                COUNT(*) as count
            FROM articles
            WHERE publish_time > ?
            GROUP BY DATE(publish_time)
            ORDER BY date
        """, (cutoff_date,))

        data = []
        max_count = 0
        for row in cursor.fetchall():
            count = row["count"]
            max_count = max(max_count, count)
            data.append({
                "date": row["date"],
                "count": count
            })

        conn.close()

        return {
            "days": days,
            "max_count": max_count,
            "data": data
        }

    def get_hourly_distribution(self, days: int = 30) -> List[Dict]:
        """
        获取发布时间分布（小时级别）

        Args:
            days: 统计天数

        Returns:
            24小时分布数据
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                CAST(strftime('%H', publish_time) AS INTEGER) as hour,
                COUNT(*) as count
            FROM articles
            WHERE publish_time > ?
            GROUP BY hour
            ORDER BY hour
        """, (cutoff_date,))

        # 初始化24小时数据
        hourly = {h: 0 for h in range(24)}
        for row in cursor.fetchall():
            hourly[row["hour"]] = row["count"]

        conn.close()

        return [
            {"hour": h, "count": c}
            for h, c in hourly.items()
        ]

    def get_category_distribution(self, days: int = 30) -> List[Dict]:
        """
        获取内容分类占比

        Args:
            days: 统计天数

        Returns:
            分类占比数据
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                COALESCE(category, '未分类') as category,
                COUNT(*) as count
            FROM articles
            WHERE publish_time > ?
            GROUP BY category
            ORDER BY count DESC
        """, (cutoff_date,))

        results = []
        total = 0
        rows = cursor.fetchall()
        for row in rows:
            total += row["count"]

        for row in rows:
            results.append({
                "category": row["category"],
                "count": row["count"],
                "percentage": round(row["count"] / total * 100, 1) if total > 0 else 0
            })

        conn.close()
        return results

    def get_account_stats(self, days: int = 30) -> List[Dict]:
        """
        获取各账号统计数据

        Args:
            days: 统计天数

        Returns:
            账号统计列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                account_name,
                COUNT(*) as article_count,
                SUM(COALESCE(read_count, 0)) as total_reads,
                SUM(COALESCE(like_count, 0)) as total_likes,
                AVG(COALESCE(wci_score, 0)) as avg_wci
            FROM articles
            WHERE publish_time > ? AND account_name IS NOT NULL
            GROUP BY account_name
            ORDER BY total_reads DESC
        """, (cutoff_date,))

        results = []
        for row in cursor.fetchall():
            results.append({
                "account_name": row["account_name"],
                "article_count": row["article_count"],
                "total_reads": row["total_reads"],
                "total_likes": row["total_likes"],
                "avg_wci": round(row["avg_wci"] or 0, 2)
            })

        conn.close()
        return results

    def get_quality_distribution(self, days: int = 30) -> Dict[str, int]:
        """
        获取质量评分分布

        Args:
            days: 统计天数

        Returns:
            质量分布统计
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                CASE
                    WHEN quality_score >= 80 THEN '优秀'
                    WHEN quality_score >= 60 THEN '良好'
                    WHEN quality_score >= 40 THEN '一般'
                    ELSE '较差'
                END as quality_level,
                COUNT(*) as count
            FROM articles
            WHERE publish_time > ?
            GROUP BY quality_level
        """, (cutoff_date,))

        results = {"优秀": 0, "良好": 0, "一般": 0, "较差": 0}
        for row in cursor.fetchall():
            results[row["quality_level"]] = row["count"]

        conn.close()
        return results


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='数据分析引擎')
    parser.add_argument('--db', help='数据库路径')
    parser.add_argument('--days', type=int, default=30, help='统计天数')

    subparsers = parser.add_subparsers(dest='command', help='子命令')

    subparsers.add_parser('metrics', help='核心指标')
    subparsers.add_parser('top', help='排行榜')
    subparsers.add_parser('accounts', help='账号统计')
    subparsers.add_parser('categories', help='分类占比')

    args = parser.parse_args()

    engine = AnalyticsEngine(args.db)

    if args.command == 'metrics':
        metrics = engine.get_core_metrics(args.days)
        print(json.dumps(metrics, ensure_ascii=False, indent=2))

    elif args.command == 'top':
        articles = engine.get_top_articles(limit=10, days=args.days)
        print(json.dumps([asdict(a) for a in articles], ensure_ascii=False, indent=2))

    elif args.command == 'accounts':
        stats = engine.get_account_stats(args.days)
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    elif args.command == 'categories':
        dist = engine.get_category_distribution(args.days)
        print(json.dumps(dist, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
