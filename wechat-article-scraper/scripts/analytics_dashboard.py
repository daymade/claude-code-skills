#!/usr/bin/env python3
"""
数据可视化仪表盘 - 交互式图表分析与洞察

功能：
- 阅读趋势分析 (时间序列图表)
- 粉丝增长追踪
- 传播路径可视化
- 互动数据热力图
- 文章表现排行榜
- 公众号健康度评分

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger('analytics-dashboard')


@dataclass
class TrendData:
    """趋势数据点"""
    date: str
    value: int
    change_pct: float = 0.0


@dataclass
class ArticlePerformance:
    """文章表现数据"""
    article_id: str
    title: str
    account_name: str
    publish_time: str
    read_count: int
    like_count: int
    share_count: int = 0
    comment_count: int = 0
    engagement_rate: float = 0.0
    score: float = 0.0


@dataclass
class AccountMetrics:
    """公众号指标"""
    account_name: str
    total_articles: int
    total_reads: int
    total_likes: int
    avg_reads: int
    avg_likes: int
    engagement_rate: float
    posting_frequency: float
    health_score: float
    growth_rate: float


@dataclass
class HeatmapData:
    """热力图数据"""
    hour: int
    day: int
    value: int


@dataclass
class DashboardReport:
    """仪表盘报告"""
    generated_at: str
    period: str
    summary: Dict[str, Any]
    trends: List[TrendData]
    top_articles: List[ArticlePerformance]
    account_metrics: List[AccountMetrics]
    heatmap: List[HeatmapData]
    insights: List[str]


class AnalyticsDashboard:
    """数据可视化仪表盘"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "articles.db")
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_reading_trends(self, days: int = 30,
                          account: str = None) -> List[TrendData]:
        """获取阅读趋势"""
        conn = self._get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        if account:
            cursor = conn.execute("""
                SELECT DATE(publish_time) as date, SUM(read_count) as total
                FROM articles
                WHERE publish_time >= ? AND account_name = ?
                GROUP BY DATE(publish_time)
                ORDER BY date
            """, (start_date, account))
        else:
            cursor = conn.execute("""
                SELECT DATE(publish_time) as date, SUM(read_count) as total
                FROM articles
                WHERE publish_time >= ?
                GROUP BY DATE(publish_time)
                ORDER BY date
            """, (start_date,))

        rows = cursor.fetchall()
        conn.close()

        trends = []
        prev_value = None
        for row in rows:
            value = row['total'] or 0
            change_pct = 0.0
            if prev_value and prev_value > 0:
                change_pct = ((value - prev_value) / prev_value) * 100

            trends.append(TrendData(
                date=row['date'],
                value=value,
                change_pct=change_pct
            ))
            prev_value = value

        return trends

    def get_engagement_trends(self, days: int = 30) -> Dict[str, List[TrendData]]:
        """获取互动趋势（阅读、点赞、分享）"""
        conn = self._get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor = conn.execute("""
            SELECT DATE(publish_time) as date,
                   SUM(read_count) as reads,
                   SUM(like_count) as likes,
                   SUM(share_count) as shares
            FROM articles
            WHERE publish_time >= ?
            GROUP BY DATE(publish_time)
            ORDER BY date
        """, (start_date,))

        rows = cursor.fetchall()
        conn.close()

        reads, likes, shares = [], [], []
        for row in rows:
            reads.append(TrendData(date=row['date'], value=row['reads'] or 0))
            likes.append(TrendData(date=row['date'], value=row['likes'] or 0))
            shares.append(TrendData(date=row['date'], value=row['shares'] or 0))

        return {
            'reads': reads,
            'likes': likes,
            'shares': shares
        }

    def get_top_articles(self, limit: int = 10,
                        metric: str = 'read_count',
                        days: int = 30) -> List[ArticlePerformance]:
        """获取表现最佳的文章"""
        conn = self._get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor = conn.execute(f"""
            SELECT id, title, account_name, publish_time,
                   read_count, like_count, share_count, comment_count
            FROM articles
            WHERE publish_time >= ?
            ORDER BY {metric} DESC
            LIMIT ?
        """, (start_date, limit))

        rows = cursor.fetchall()
        conn.close()

        articles = []
        for row in rows:
            reads = row['read_count'] or 0
            likes = row['like_count'] or 0
            engagement = (likes / reads * 100) if reads > 0 else 0

            # 综合得分 = 阅读量 * 0.5 + 点赞量 * 0.3 + 分享量 * 0.2
            score = (reads * 0.5 + likes * 0.3 + (row['share_count'] or 0) * 0.2) / 100

            articles.append(ArticlePerformance(
                article_id=row['id'],
                title=row['title'] or 'Untitled',
                account_name=row['account_name'] or 'Unknown',
                publish_time=row['publish_time'] or '',
                read_count=reads,
                like_count=likes,
                share_count=row['share_count'] or 0,
                comment_count=row['comment_count'] or 0,
                engagement_rate=engagement,
                score=score
            ))

        return articles

    def get_account_metrics(self) -> List[AccountMetrics]:
        """获取各公众号的指标"""
        conn = self._get_connection()

        # 获取最近30天的数据
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        cursor = conn.execute("""
            SELECT account_name,
                   COUNT(*) as article_count,
                   SUM(read_count) as total_reads,
                   SUM(like_count) as total_likes,
                   AVG(read_count) as avg_reads,
                   AVG(like_count) as avg_likes
            FROM articles
            WHERE publish_time >= ? AND account_name IS NOT NULL
            GROUP BY account_name
            ORDER BY total_reads DESC
        """, (start_date,))

        rows = cursor.fetchall()

        # 获取上个月的对比数据（计算增长率）
        prev_start = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        prev_end = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        cursor = conn.execute("""
            SELECT account_name, SUM(read_count) as total
            FROM articles
            WHERE publish_time >= ? AND publish_time < ?
            GROUP BY account_name
        """, (prev_start, prev_end))

        prev_data = {row['account_name']: row['total'] or 0 for row in cursor.fetchall()}
        conn.close()

        metrics = []
        for row in rows:
            account = row['account_name']
            total_reads = row['total_reads'] or 0
            total_likes = row['total_likes'] or 0
            avg_reads = row['avg_reads'] or 0

            # 互动率 = 点赞 / 阅读
            engagement = (total_likes / total_reads * 100) if total_reads > 0 else 0

            # 发文频率 = 文章数 / 30天
            frequency = row['article_count'] / 30

            # 增长率
            prev_reads = prev_data.get(account, 0)
            growth = ((total_reads - prev_reads) / prev_reads * 100) if prev_reads > 0 else 0

            # 健康度评分 (0-100)
            # 基于：阅读量、互动率、发文频率、增长率
            health = min(100, (
                min(30, avg_reads / 1000) +  # 平均阅读贡献30分
                min(25, engagement * 5) +     # 互动率贡献25分
                min(20, frequency * 4) +      # 发文频率贡献20分
                min(25, max(0, growth / 10))  # 增长率贡献25分
            ))

            metrics.append(AccountMetrics(
                account_name=account,
                total_articles=row['article_count'],
                total_reads=total_reads,
                total_likes=total_likes,
                avg_reads=int(avg_reads),
                avg_likes=int(row['avg_likes'] or 0),
                engagement_rate=engagement,
                posting_frequency=frequency,
                health_score=health,
                growth_rate=growth
            ))

        return metrics

    def get_publish_heatmap(self, days: int = 90) -> List[HeatmapData]:
        """获取发布时间热力图（一周中各时段的发布量）"""
        conn = self._get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor = conn.execute("""
            SELECT
                CAST(strftime('%H', publish_time) AS INTEGER) as hour,
                CAST(strftime('%w', publish_time) AS INTEGER) as day,
                COUNT(*) as count
            FROM articles
            WHERE publish_time >= ?
            GROUP BY hour, day
        """, (start_date,))

        rows = cursor.fetchall()
        conn.close()

        heatmap = []
        for row in rows:
            # 转换周日(0)到周一(0)的表示
            day = row['day'] if row['day'] > 0 else 7
            heatmap.append(HeatmapData(
                hour=row['hour'],
                day=day - 1,  # 0=周一, 6=周日
                value=row['count']
            ))

        return heatmap

    def get_category_distribution(self) -> List[Dict[str, Any]]:
        """获取文章分类分布"""
        conn = self._get_connection()

        cursor = conn.execute("""
            SELECT category, COUNT(*) as count, AVG(read_count) as avg_reads
            FROM articles
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                'category': row['category'],
                'count': row['count'],
                'avg_reads': int(row['avg_reads'] or 0)
            }
            for row in rows
        ]

    def generate_insights(self, metrics: List[AccountMetrics],
                         trends: List[TrendData]) -> List[str]:
        """生成数据洞察"""
        insights = []

        if not metrics:
            return ["暂无足够数据生成洞察"]

        # 最佳表现公众号
        best_account = max(metrics, key=lambda x: x.total_reads)
        insights.append(
            f"【表现最佳】{best_account.account_name} 近30天获得 "
            f"{best_account.total_reads:,} 次阅读，"
            f"互动率 {best_account.engagement_rate:.2f}%"
        )

        # 增长最快
        growing = [m for m in metrics if m.growth_rate > 0]
        if growing:
            fastest = max(growing, key=lambda x: x.growth_rate)
            insights.append(
                f"【增长之星】{fastest.account_name} 阅读量环比增长 "
                f"{fastest.growth_rate:+.1f}%"
            )

        # 发文频率建议
        low_freq = [m for m in metrics if m.posting_frequency < 0.3]
        if low_freq:
            insights.append(
                f"【建议关注】{len(low_freq)} 个公众号发文频率较低 "
                f"(平均 < 0.3篇/天)，建议增加更新"
            )

        # 趋势洞察
        if len(trends) >= 7:
            recent_avg = sum(t.value for t in trends[-7:]) / 7
            prev_avg = sum(t.value for t in trends[-14:-7]) / 7 if len(trends) >= 14 else recent_avg

            if recent_avg > prev_avg * 1.1:
                insights.append(
                    f"【趋势上升】近7天平均阅读量 {recent_avg:,.0f}，"
                    f"环比增长 {(recent_avg/prev_avg-1)*100:.1f}% 📈"
                )
            elif recent_avg < prev_avg * 0.9:
                insights.append(
                    f"【趋势下降】近7天平均阅读量 {recent_avg:,.0f}，"
                    f"环比下降 {(1-recent_avg/prev_avg)*100:.1f}% 📉"
                )

        # 互动率分析
        high_engagement = [m for m in metrics if m.engagement_rate > 3]
        if high_engagement:
            insights.append(
                f"【高互动】{len(high_engagement)} 个公众号互动率 > 3%，"
                f"内容质量优秀"
            )

        return insights

    def generate_report(self, days: int = 30) -> DashboardReport:
        """生成完整报告"""
        trends = self.get_reading_trends(days)
        engagement = self.get_engagement_trends(days)
        top_articles = self.get_top_articles(limit=10, days=days)
        account_metrics = self.get_account_metrics()
        heatmap = self.get_publish_heatmap(days)
        category_dist = self.get_category_distribution()
        insights = self.generate_insights(account_metrics, trends)

        # 计算汇总数据
        total_reads = sum(t.value for t in trends)
        total_articles = sum(m.total_articles for m in account_metrics)
        avg_engagement = sum(m.engagement_rate for m in account_metrics) / len(account_metrics) if account_metrics else 0

        summary = {
            'total_reads': total_reads,
            'total_articles': total_articles,
            'active_accounts': len(account_metrics),
            'avg_engagement_rate': avg_engagement,
            'category_distribution': category_dist
        }

        return DashboardReport(
            generated_at=datetime.now().isoformat(),
            period=f"{days}天",
            summary=summary,
            trends=trends,
            top_articles=top_articles,
            account_metrics=account_metrics,
            heatmap=heatmap,
            insights=insights
        )

    def export_echarts_config(self, report: DashboardReport,
                             output_path: str):
        """导出 ECharts 配置"""
        config = {
            'title': {
                'text': '公众号数据分析仪表盘',
                'subtext': f'统计周期: {report.period}'
            },
            'tooltip': {'trigger': 'axis'},
            'legend': {'data': ['阅读量', '点赞量', '分享量']},
            'xAxis': {
                'type': 'category',
                'data': [t.date for t in report.trends]
            },
            'yAxis': {'type': 'value'},
            'series': [
                {
                    'name': '阅读量',
                    'type': 'line',
                    'data': [t.value for t in report.trends],
                    'smooth': True,
                    'areaStyle': {'opacity': 0.3}
                }
            ]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info(f"ECharts配置已导出: {output_path}")


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='数据可视化仪表盘')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 趋势报告
    trend_parser = subparsers.add_parser('trends', help='阅读趋势')
    trend_parser.add_argument('--days', type=int, default=30)
    trend_parser.add_argument('--account', help='指定公众号')

    # 热门文章
    top_parser = subparsers.add_parser('top', help='热门文章排行')
    top_parser.add_argument('--limit', type=int, default=10)
    top_parser.add_argument('--metric', default='read_count',
                           choices=['read_count', 'like_count', 'share_count'])

    # 公众号指标
    metrics_parser = subparsers.add_parser('metrics', help='公众号指标')
    metrics_parser.add_argument('--export', help='导出JSON路径')

    # 完整报告
    report_parser = subparsers.add_parser('report', help='生成完整报告')
    report_parser.add_argument('--days', type=int, default=30)
    report_parser.add_argument('--export', help='导出JSON路径')
    report_parser.add_argument('--echarts', help='导出ECharts配置')

    # 热力图
    heatmap_parser = subparsers.add_parser('heatmap', help='发布时间热力图')
    heatmap_parser.add_argument('--days', type=int, default=90)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    dashboard = AnalyticsDashboard()

    if args.command == 'trends':
        trends = dashboard.get_reading_trends(args.days, args.account)
        print(f"\n阅读趋势 ({len(trends)}天):\n")
        for t in trends[-10:]:
            change = f"({t.change_pct:+.1f}%)" if t.change_pct != 0 else ""
            print(f"  {t.date}: {t.value:,} 阅读 {change}")

    elif args.command == 'top':
        articles = dashboard.get_top_articles(args.limit, args.metric)
        print(f"\n热门文章 Top {len(articles)}:\n")
        for i, a in enumerate(articles, 1):
            print(f"{i}. {a.title[:40]}...")
            print(f"   {a.account_name} | {a.read_count:,} 阅读 | "
                  f"{a.like_count:,} 点赞 | 互动率 {a.engagement_rate:.2f}%")

    elif args.command == 'metrics':
        metrics = dashboard.get_account_metrics()
        print(f"\n公众号指标 ({len(metrics)}个):\n")
        for m in metrics:
            print(f"\n{m.account_name}:")
            print(f"  文章数: {m.total_articles} | 总阅读: {m.total_reads:,}")
            print(f"  平均阅读: {m.avg_reads:,} | 互动率: {m.engagement_rate:.2f}%")
            print(f"  健康度: {m.health_score:.1f}/100 | 增长率: {m.growth_rate:+.1f}%")

        if args.export:
            with open(args.export, 'w', encoding='utf-8') as f:
                json.dump([asdict(m) for m in metrics], f, ensure_ascii=False, indent=2)
            print(f"\n已导出: {args.export}")

    elif args.command == 'heatmap':
        heatmap = dashboard.get_publish_heatmap(args.days)
        print(f"\n发布时间热力图 ({len(heatmap)}个数据点):\n")

        # 构建矩阵
        matrix = [[' ' for _ in range(24)] for _ in range(7)]
        days_map = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

        for h in heatmap:
            intensity = min(9, h.value // 5)
            matrix[h.day][h.hour] = str(intensity) if intensity > 0 else '·'

        print("     " + " ".join(f"{i:02d}" for i in range(24)))
        for i, day in enumerate(days_map):
            print(f"{day} {' '.join(matrix[i])}")

    elif args.command == 'report':
        report = dashboard.generate_report(args.days)
        print(f"\n{'='*50}")
        print(f"数据分析报告")
        print(f"{'='*50}")
        print(f"生成时间: {report.generated_at[:19]}")
        print(f"统计周期: {report.period}\n")

        print("【汇总数据】")
        print(f"  总阅读量: {report.summary['total_reads']:,}")
        print(f"  总文章数: {report.summary['total_articles']}")
        print(f"  活跃公众号: {report.summary['active_accounts']}")
        print(f"  平均互动率: {report.summary['avg_engagement_rate']:.2f}%")

        print("\n【数据洞察】")
        for insight in report.insights:
            print(f"  • {insight}")

        print("\n【热门文章 Top 5】")
        for i, a in enumerate(report.top_articles[:5], 1):
            print(f"  {i}. {a.title[:35]}... ({a.read_count:,}阅读)")

        if args.export:
            with open(args.export, 'w', encoding='utf-8') as f:
                json.dump({
                    'generated_at': report.generated_at,
                    'period': report.period,
                    'summary': report.summary,
                    'insights': report.insights,
                    'trends': [asdict(t) for t in report.trends],
                    'top_articles': [asdict(a) for a in report.top_articles],
                    'account_metrics': [asdict(m) for m in report.account_metrics]
                }, f, ensure_ascii=False, indent=2)
            print(f"\n报告已导出: {args.export}")

        if args.echarts:
            dashboard.export_echarts_config(report, args.echarts)
            print(f"ECharts配置已导出: {args.echarts}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
