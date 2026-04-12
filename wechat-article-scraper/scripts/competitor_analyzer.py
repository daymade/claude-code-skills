#!/usr/bin/env python3
"""
竞品分析系统 - 多公众号对比与竞争力分析

功能：
- 多公众号指标对比
- 竞争力评分与排名
- 内容策略分析
- 最佳发布时间分析
- 优势/劣势识别

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

logger = logging.getLogger('competitor-analyzer')


@dataclass
class CompetitorProfile:
    """竞品画像"""
    account_name: str
    total_articles: int
    total_reads: int
    total_likes: int
    avg_reads: float
    avg_likes: float
    engagement_rate: float
    posting_frequency: float
    content_categories: List[str]
    best_performing_article: Optional[Dict] = None
    peak_publish_hour: int = 0
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """对比结果"""
    metric: str
    leader: str
    values: Dict[str, float]
    gap_pct: Dict[str, float]


@dataclass
class CompetitiveScore:
    """竞争力评分"""
    account_name: str
    overall_score: float
    reach_score: float
    engagement_score: float
    consistency_score: float
    growth_score: float
    quality_score: float
    rank: int = 0


@dataclass
class BenchmarkReport:
    """基准测试报告"""
    accounts: List[str]
    period: str
    comparisons: List[ComparisonResult]
    scores: List[CompetitiveScore]
    profiles: List[CompetitorProfile]
    recommendations: List[str]


class CompetitorAnalyzer:
    """竞品分析器"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "articles.db")
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_account_profile(self, account_name: str,
                           days: int = 30) -> Optional[CompetitorProfile]:
        """获取公众号画像"""
        conn = self._get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 基础指标
        cursor = conn.execute("""
            SELECT COUNT(*) as count,
                   SUM(read_count) as total_reads,
                   SUM(like_count) as total_likes,
                   AVG(read_count) as avg_reads,
                   AVG(like_count) as avg_likes,
                   MIN(publish_time) as first_post,
                   MAX(publish_time) as last_post
            FROM articles
            WHERE account_name = ? AND publish_time >= ?
        """, (account_name, start_date))

        row = cursor.fetchone()
        if not row or row['count'] == 0:
            conn.close()
            return None

        # 内容分类
        cursor = conn.execute("""
            SELECT category, COUNT(*) as count
            FROM articles
            WHERE account_name = ? AND category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
            LIMIT 5
        """, (account_name,))

        categories = [r['category'] for r in cursor.fetchall()]

        # 最佳文章
        cursor = conn.execute("""
            SELECT title, read_count, like_count, publish_time
            FROM articles
            WHERE account_name = ?
            ORDER BY read_count DESC
            LIMIT 1
        """, (account_name,))

        best = cursor.fetchone()
        best_article = None
        if best:
            best_article = {
                'title': best['title'],
                'reads': best['read_count'],
                'likes': best['like_count']
            }

        # 最佳发布时间
        cursor = conn.execute("""
            SELECT CAST(strftime('%H', publish_time) AS INTEGER) as hour,
                   AVG(read_count) as avg_reads
            FROM articles
            WHERE account_name = ?
            GROUP BY hour
            ORDER BY avg_reads DESC
            LIMIT 1
        """, (account_name,))

        peak_row = cursor.fetchone()
        peak_hour = peak_row['hour'] if peak_row else 8

        conn.close()

        total_reads = row['total_reads'] or 0
        total_likes = row['total_likes'] or 0
        avg_reads = row['avg_reads'] or 0

        engagement = (total_likes / total_reads * 100) if total_reads > 0 else 0
        frequency = row['count'] / days if days > 0 else 0

        return CompetitorProfile(
            account_name=account_name,
            total_articles=row['count'],
            total_reads=total_reads,
            total_likes=total_likes,
            avg_reads=avg_reads,
            avg_likes=row['avg_likes'] or 0,
            engagement_rate=engagement,
            posting_frequency=frequency,
            content_categories=categories,
            best_performing_article=best_article,
            peak_publish_hour=peak_hour
        )

    def compare_accounts(self, accounts: List[str],
                        days: int = 30) -> List[ComparisonResult]:
        """对比多个公众号"""
        profiles = []
        for account in accounts:
            profile = self.get_account_profile(account, days)
            if profile:
                profiles.append(profile)

        if len(profiles) < 2:
            return []

        comparisons = []

        # 对比维度
        metrics = [
            ('total_reads', '总阅读量'),
            ('avg_reads', '平均阅读量'),
            ('engagement_rate', '互动率'),
            ('posting_frequency', '发文频率'),
            ('total_likes', '总点赞数')
        ]

        for metric_key, metric_name in metrics:
            values = {}
            for p in profiles:
                values[p.account_name] = getattr(p, metric_key, 0)

            if values:
                leader = max(values, key=values.get)
                leader_value = values[leader]

                gaps = {}
                for name, value in values.items():
                    if leader_value > 0 and name != leader:
                        gaps[name] = ((leader_value - value) / leader_value) * 100
                    else:
                        gaps[name] = 0

                comparisons.append(ComparisonResult(
                    metric=metric_name,
                    leader=leader,
                    values=values,
                    gap_pct=gaps
                ))

        return comparisons

    def calculate_competitive_scores(self, accounts: List[str],
                                     days: int = 30) -> List[CompetitiveScore]:
        """计算竞争力评分"""
        profiles = []
        for account in accounts:
            profile = self.get_account_profile(account, days)
            if profile:
                profiles.append(profile)

        if not profiles:
            return []

        # 计算行业基准
        max_reads = max(p.total_reads for p in profiles)
        max_avg = max(p.avg_reads for p in profiles)
        max_engagement = max(p.engagement_rate for p in profiles)
        max_frequency = max(p.posting_frequency for p in profiles)

        scores = []
        for p in profiles:
            # 影响力得分 (基于总阅读)
            reach = (p.total_reads / max_reads * 100) if max_reads > 0 else 0

            # 互动得分 (基于互动率)
            engagement = (p.engagement_rate / max_engagement * 100) if max_engagement > 0 else 0

            # 一致性得分 (基于发文频率稳定性)
            consistency = min(100, p.posting_frequency * 20)  # 每天0.5篇得满分

            # 增长潜力得分 (基于平均阅读)
            growth = (p.avg_reads / max_avg * 100) if max_avg > 0 else 0

            # 内容质量得分 (综合)
            quality = min(100, p.avg_likes / 100 + p.engagement_rate * 5)

            # 综合得分
            overall = (
                reach * 0.25 +
                engagement * 0.25 +
                consistency * 0.20 +
                growth * 0.15 +
                quality * 0.15
            )

            scores.append(CompetitiveScore(
                account_name=p.account_name,
                overall_score=overall,
                reach_score=reach,
                engagement_score=engagement,
                consistency_score=consistency,
                growth_score=growth,
                quality_score=quality
            ))

        # 排序并添加排名
        scores.sort(key=lambda x: x.overall_score, reverse=True)
        for i, s in enumerate(scores, 1):
            s.rank = i

        return scores

    def analyze_content_strategy(self, account_name: str) -> Dict[str, Any]:
        """分析内容策略"""
        conn = self._get_connection()

        # 内容分类分布
        cursor = conn.execute("""
            SELECT category,
                   COUNT(*) as count,
                   AVG(read_count) as avg_reads,
                   AVG(like_count) as avg_likes
            FROM articles
            WHERE account_name = ? AND category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
        """, (account_name,))

        categories = []
        for row in cursor.fetchall():
            categories.append({
                'category': row['category'],
                'count': row['count'],
                'avg_reads': int(row['avg_reads'] or 0),
                'avg_likes': int(row['avg_likes'] or 0),
                'engagement': (row['avg_likes'] or 0) / (row['avg_reads'] or 1) * 100
            })

        # 发布时间分析
        cursor = conn.execute("""
            SELECT
                CAST(strftime('%H', publish_time) AS INTEGER) as hour,
                COUNT(*) as count,
                AVG(read_count) as avg_reads
            FROM articles
            WHERE account_name = ?
            GROUP BY hour
            ORDER BY hour
        """, (account_name,))

        hourly_data = []
        for row in cursor.fetchall():
            hourly_data.append({
                'hour': row['hour'],
                'count': row['count'],
                'avg_reads': int(row['avg_reads'] or 0)
            })

        # 最佳发布时间
        best_hour = max(hourly_data, key=lambda x: x['avg_reads']) if hourly_data else None

        # 标题关键词分析
        cursor = conn.execute("""
            SELECT title FROM articles
            WHERE account_name = ? AND title IS NOT NULL
            LIMIT 100
        """, (account_name,))

        titles = [r['title'] for r in cursor.fetchall()]
        conn.close()

        # 简单关键词提取
        common_words = self._extract_keywords(titles)

        return {
            'categories': categories,
            'hourly_distribution': hourly_data,
            'best_publish_hour': best_hour['hour'] if best_hour else None,
            'common_keywords': common_words[:20],
            'total_analyzed': len(titles)
        }

    def _extract_keywords(self, titles: List[str]) -> List[Tuple[str, int]]:
        """提取关键词"""
        word_counts = defaultdict(int)

        stop_words = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人',
                     '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
                     '你', '会', '着', '没有', '看', '好', '自己', '这', '那'}

        for title in titles:
            # 简单分词 (按字符和常见词)
            words = title.split()
            for word in words:
                word = word.strip('，。！？、""''（）【】《》')
                if len(word) >= 2 and word not in stop_words:
                    word_counts[word] += 1

        return sorted(word_counts.items(), key=lambda x: x[1], reverse=True)

    def identify_strengths_weaknesses(self, profile: CompetitorProfile,
                                     all_profiles: List[CompetitorProfile]) -> CompetitorProfile:
        """识别优势和劣势"""
        if not all_profiles:
            return profile

        strengths = []
        weaknesses = []

        # 计算平均值
        avg_reads = sum(p.avg_reads for p in all_profiles) / len(all_profiles)
        avg_engagement = sum(p.engagement_rate for p in all_profiles) / len(all_profiles)
        avg_frequency = sum(p.posting_frequency for p in all_profiles) / len(all_profiles)

        # 阅读量评估
        if profile.avg_reads > avg_reads * 1.5:
            strengths.append(f"阅读量领先，平均 {profile.avg_reads:,.0f} 次")
        elif profile.avg_reads < avg_reads * 0.5:
            weaknesses.append(f"阅读量偏低，平均仅 {profile.avg_reads:,.0f} 次")

        # 互动率评估
        if profile.engagement_rate > avg_engagement * 1.3:
            strengths.append(f"互动率优秀，{profile.engagement_rate:.2f}%")
        elif profile.engagement_rate < avg_engagement * 0.5:
            weaknesses.append(f"互动率偏低，仅 {profile.engagement_rate:.2f}%")

        # 发文频率评估
        if profile.posting_frequency > avg_frequency * 1.2:
            strengths.append(f"发文积极，{profile.posting_frequency:.2f}篇/天")
        elif profile.posting_frequency < 0.1:
            weaknesses.append("发文频率过低")

        # 内容多样性
        if len(profile.content_categories) >= 3:
            strengths.append(f"内容多元，覆盖 {len(profile.content_categories)} 个类别")

        profile.strengths = strengths
        profile.weaknesses = weaknesses
        return profile

    def generate_benchmark_report(self, accounts: List[str],
                                  days: int = 30) -> BenchmarkReport:
        """生成基准测试报告"""
        # 获取所有画像
        profiles = []
        for account in accounts:
            profile = self.get_account_profile(account, days)
            if profile:
                profiles.append(profile)

        if not profiles:
            return BenchmarkReport(
                accounts=accounts,
                period=f"{days}天",
                comparisons=[],
                scores=[],
                profiles=[],
                recommendations=["数据不足，无法生成报告"]
            )

        # 识别优劣势
        for p in profiles:
            self.identify_strengths_weaknesses(p, profiles)

        # 对比分析
        comparisons = self.compare_accounts(accounts, days)

        # 竞争力评分
        scores = self.calculate_competitive_scores(accounts, days)

        # 生成建议
        recommendations = self._generate_recommendations(profiles, scores)

        return BenchmarkReport(
            accounts=[p.account_name for p in profiles],
            period=f"{days}天",
            comparisons=comparisons,
            scores=scores,
            profiles=profiles,
            recommendations=recommendations
        )

    def _generate_recommendations(self, profiles: List[CompetitorProfile],
                                  scores: List[CompetitiveScore]) -> List[str]:
        """生成运营建议"""
        recommendations = []

        if not profiles or not scores:
            return recommendations

        # 领先者建议
        leader = scores[0]
        recommendations.append(
            f"【标杆学习】{leader.account_name} 综合竞争力第一 (得分 {leader.overall_score:.1f})，"
            f"影响力 {leader.reach_score:.1f}，互动 {leader.engagement_score:.1f}"
        )

        # 增长机会
        low_consistency = [s for s in scores if s.consistency_score < 40]
        for s in low_consistency:
            recommendations.append(
                f"【增长机会】{s.account_name} 发文频率较低，建议增加更新"
            )

        # 互动提升
        low_engagement = [s for s in scores if s.engagement_score < 30]
        for s in low_engagement:
            recommendations.append(
                f"【互动优化】{s.account_name} 可优化内容互动性，增加话题引导"
            )

        # 内容策略
        for p in profiles:
            if len(p.content_categories) < 2:
                recommendations.append(
                    f"【内容建议】{p.account_name} 内容类别单一，建议拓展话题"
                )

        return recommendations


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='竞品分析系统')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 单账号画像
    profile_parser = subparsers.add_parser('profile', help='公众号画像')
    profile_parser.add_argument('account', help='公众号名称')
    profile_parser.add_argument('--days', type=int, default=30)

    # 多账号对比
    compare_parser = subparsers.add_parser('compare', help='多账号对比')
    compare_parser.add_argument('accounts', help='公众号列表(逗号分隔)')
    compare_parser.add_argument('--days', type=int, default=30)

    # 竞争力评分
    score_parser = subparsers.add_parser('score', help='竞争力评分')
    score_parser.add_argument('accounts', help='公众号列表(逗号分隔)')
    score_parser.add_argument('--days', type=int, default=30)

    # 内容策略分析
    strategy_parser = subparsers.add_parser('strategy', help='内容策略分析')
    strategy_parser.add_argument('account', help='公众号名称')

    # 完整报告
    report_parser = subparsers.add_parser('report', help='生成基准报告')
    report_parser.add_argument('accounts', help='公众号列表(逗号分隔)')
    report_parser.add_argument('--days', type=int, default=30)
    report_parser.add_argument('--export', help='导出JSON路径')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    analyzer = CompetitorAnalyzer()

    if args.command == 'profile':
        profile = analyzer.get_account_profile(args.account, args.days)
        if profile:
            print(f"\n{'='*50}")
            print(f"公众号画像: {profile.account_name}")
            print(f"{'='*50}")
            print(f"总文章数: {profile.total_articles}")
            print(f"总阅读量: {profile.total_reads:,}")
            print(f"总点赞数: {profile.total_likes:,}")
            print(f"平均阅读: {profile.avg_reads:,.0f}")
            print(f"互动率: {profile.engagement_rate:.2f}%")
            print(f"发文频率: {profile.posting_frequency:.2f}篇/天")
            print(f"最佳发布时段: {profile.peak_publish_hour}:00")
            print(f"内容分类: {', '.join(profile.content_categories)}")
            if profile.best_performing_article:
                print(f"\n最佳文章: {profile.best_performing_article['title'][:40]}...")
                print(f"  阅读: {profile.best_performing_article['reads']:,}")
        else:
            print(f"未找到数据: {args.account}")

    elif args.command == 'compare':
        accounts = [a.strip() for a in args.accounts.split(',')]
        comparisons = analyzer.compare_accounts(accounts, args.days)

        print(f"\n{'='*50}")
        print(f"多账号对比 ({len(accounts)}个)")
        print(f"{'='*50}")

        for comp in comparisons:
            print(f"\n【{comp.metric}】")
            print(f"  领先: {comp.leader}")
            for name, value in comp.values.items():
                gap = comp.gap_pct.get(name, 0)
                gap_str = f" (落后 {gap:.1f}%)" if gap > 0 else " 👑"
                print(f"  - {name}: {value:,.0f}{gap_str}")

    elif args.command == 'score':
        accounts = [a.strip() for a in args.accounts.split(',')]
        scores = analyzer.calculate_competitive_scores(accounts, args.days)

        print(f"\n{'='*50}")
        print(f"竞争力评分 ({len(scores)}个账号)")
        print(f"{'='*50}")

        for s in scores:
            print(f"\n{s.rank}. {s.account_name} (综合 {s.overall_score:.1f})")
            print(f"   影响力: {s.reach_score:.1f} | "
                  f"互动: {s.engagement_score:.1f} | "
                  f"一致性: {s.consistency_score:.1f} | "
                  f"增长: {s.growth_score:.1f} | "
                  f"质量: {s.quality_score:.1f}")

    elif args.command == 'strategy':
        strategy = analyzer.analyze_content_strategy(args.account)

        print(f"\n{'='*50}")
        print(f"内容策略分析: {args.account}")
        print(f"{'='*50}")

        print(f"\n【分类分布】")
        for cat in strategy['categories'][:5]:
            print(f"  {cat['category']}: {cat['count']}篇 | "
                  f"平均 {cat['avg_reads']} 阅读 | "
                  f"互动 {cat['engagement']:.2f}%")

        print(f"\n【最佳发布时间】{strategy['best_publish_hour']}:00")

        print(f"\n【高频关键词】")
        for word, count in strategy['common_keywords'][:10]:
            print(f"  {word}: {count}次")

    elif args.command == 'report':
        accounts = [a.strip() for a in args.accounts.split(',')]
        report = analyzer.generate_benchmark_report(accounts, args.days)

        print(f"\n{'='*60}")
        print(f"竞品基准测试报告")
        print(f"{'='*60}")
        print(f"分析对象: {', '.join(report.accounts)}")
        print(f"统计周期: {report.period}")

        print(f"\n【竞争力排名】")
        for s in report.scores:
            print(f"  {s.rank}. {s.account_name} - 综合得分 {s.overall_score:.1f}")

        print(f"\n【对比分析】")
        for comp in report.comparisons:
            print(f"  {comp.metric}: {comp.leader} 领先")

        print(f"\n【运营建议】")
        for rec in report.recommendations:
            print(f"  • {rec}")

        if args.export:
            with open(args.export, 'w', encoding='utf-8') as f:
                json.dump({
                    'accounts': report.accounts,
                    'period': report.period,
                    'scores': [asdict(s) for s in report.scores],
                    'recommendations': report.recommendations
                }, f, ensure_ascii=False, indent=2)
            print(f"\n报告已导出: {args.export}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
