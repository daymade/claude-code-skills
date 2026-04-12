#!/usr/bin/env python3
"""
AI智能洞察报告生成器 - 自动数据分析和运营建议

功能：
- 数据趋势智能分析
- 异常检测与预警
- 自动运营建议生成
- 数据驱动的决策支持
- 自然语言报告生成

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
import statistics

logger = logging.getLogger('ai-insights')


@dataclass
class TrendInsight:
    """趋势洞察"""
    metric: str
    direction: str
    change_pct: float
    confidence: float
    analysis: str
    recommendation: str


@dataclass
class AnomalyDetection:
    """异常检测"""
    type: str
    severity: str
    description: str
    affected_metric: str
    expected_value: float
    actual_value: float
    timestamp: str


@dataclass
class ActionRecommendation:
    """行动建议"""
    priority: str
    category: str
    title: str
    description: str
    expected_impact: str
    difficulty: str


@dataclass
class AIReport:
    """AI洞察报告"""
    generated_at: str
    period: str
    summary: str
    trends: List[TrendInsight]
    anomalies: List[AnomalyDetection]
    recommendations: List[ActionRecommendation]
    score: int
    health_status: str


class AIInsightsGenerator:
    """AI洞察生成器"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "articles.db")
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def analyze_trends(self, days: int = 30) -> List[TrendInsight]:
        """分析数据趋势"""
        conn = self._get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 获取每日数据
        cursor = conn.execute("""
            SELECT DATE(publish_time) as date,
                   COUNT(*) as articles,
                   SUM(read_count) as reads,
                   SUM(like_count) as likes,
                   AVG(read_count) as avg_reads
            FROM articles
            WHERE publish_time >= ?
            GROUP BY DATE(publish_time)
            ORDER BY date
        """, (start_date,))

        rows = cursor.fetchall()
        conn.close()

        if len(rows) < 7:
            return [TrendInsight(
                metric="数据量",
                direction="insufficient",
                change_pct=0,
                confidence=0,
                analysis="数据量不足，需要至少7天的数据才能进行趋势分析",
                recommendation="继续收集数据，建议等待更多数据积累"
            )]

        insights = []

        # 分析阅读量趋势
        reads_series = [r['reads'] or 0 for r in rows]
        reads_change = self._calculate_trend_change(reads_series)

        if abs(reads_change) > 20:
            direction = "up" if reads_change > 0 else "down"
            confidence = min(0.9, abs(reads_change) / 100)

            analysis = (
                f"阅读量呈现明显的{'上升' if direction == 'up' else '下降'}趋势，"
                f"环比变化 {reads_change:+.1f}%。"
            )

            if direction == "up":
                recommendation = "保持当前内容策略，考虑增加发文频率以乘胜追击"
            else:
                recommendation = "建议审查近期内容质量，分析读者流失原因，调整选题方向"

            insights.append(TrendInsight(
                metric="阅读量",
                direction=direction,
                change_pct=reads_change,
                confidence=confidence,
                analysis=analysis,
                recommendation=recommendation
            ))

        # 分析互动率趋势
        engagement_series = []
        for r in rows:
            reads = r['reads'] or 0
            likes = r['likes'] or 0
            if reads > 0:
                engagement_series.append(likes / reads * 100)

        if len(engagement_series) >= 7:
            engagement_change = self._calculate_trend_change(engagement_series)

            if abs(engagement_change) > 15:
                direction = "up" if engagement_change > 0 else "down"

                analysis = (
                    f"用户互动率{'提升' if direction == 'up' else '下降'} "
                    f"{abs(engagement_change):.1f}%，"
                    f"{'内容吸引力增强' if direction == 'up' else '内容吸引力减弱'}。"
                )

                if direction == "down":
                    recommendation = "建议增加互动引导，如文末提问、投票等，提升用户参与"
                else:
                    recommendation = "互动率表现良好，可总结高互动内容的共同特征"

                insights.append(TrendInsight(
                    metric="互动率",
                    direction=direction,
                    change_pct=engagement_change,
                    confidence=0.75,
                    analysis=analysis,
                    recommendation=recommendation
                ))

        # 分析发文频率稳定性
        articles_series = [r['articles'] for r in rows]
        volatility = statistics.stdev(articles_series) if len(articles_series) > 1 else 0
        avg_articles = statistics.mean(articles_series) if articles_series else 0

        if avg_articles > 0 and volatility / avg_articles > 0.5:
            insights.append(TrendInsight(
                metric="发文频率",
                direction="volatile",
                change_pct=volatility / avg_articles * 100,
                confidence=0.8,
                analysis=f"发文频率波动较大 (标准差: {volatility:.2f})，缺乏一致性",
                recommendation="建议制定固定的发布计划，培养用户阅读习惯"
            ))

        return insights

    def _calculate_trend_change(self, series: List[float]) -> float:
        """计算趋势变化百分比"""
        if len(series) < 7:
            return 0

        # 比较前一半和后一半的平均值
        mid = len(series) // 2
        first_half = statistics.mean(series[:mid]) if series[:mid] else 0
        second_half = statistics.mean(series[mid:]) if series[mid:] else 0

        if first_half == 0:
            return 100 if second_half > 0 else 0

        return ((second_half - first_half) / first_half) * 100

    def detect_anomalies(self, days: int = 30) -> List[AnomalyDetection]:
        """检测数据异常"""
        conn = self._get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor = conn.execute("""
            SELECT DATE(publish_time) as date,
                   COUNT(*) as articles,
                   SUM(read_count) as reads,
                   AVG(read_count) as avg_reads
            FROM articles
            WHERE publish_time >= ?
            GROUP BY DATE(publish_time)
            ORDER BY date
        """, (start_date,))

        rows = cursor.fetchall()
        conn.close()

        anomalies = []

        if len(rows) < 7:
            return anomalies

        reads_series = [r['reads'] or 0 for r in rows]
        avg_reads = statistics.mean(reads_series)
        std_reads = statistics.stdev(reads_series) if len(reads_series) > 1 else 0

        for row in rows:
            reads = row['reads'] or 0

            # 检测异常高/低阅读量
            if std_reads > 0:
                z_score = (reads - avg_reads) / std_reads

                if z_score > 2.5:
                    anomalies.append(AnomalyDetection(
                        type="spike",
                        severity="high" if z_score > 3 else "medium",
                        description=f"{row['date']} 阅读量异常激增",
                        affected_metric="阅读量",
                        expected_value=avg_reads,
                        actual_value=reads,
                        timestamp=row['date']
                    ))
                elif z_score < -2:
                    anomalies.append(AnomalyDetection(
                        type="drop",
                        severity="high" if z_score < -3 else "medium",
                        description=f"{row['date']} 阅读量异常下降",
                        affected_metric="阅读量",
                        expected_value=avg_reads,
                        actual_value=reads,
                        timestamp=row['date']
                    ))

        # 检测零发布日
        for row in rows:
            if row['articles'] == 0:
                anomalies.append(AnomalyDetection(
                    type="gap",
                    severity="low",
                    description=f"{row['date']} 无文章发布",
                    affected_metric="发文量",
                    expected_value=1,
                    actual_value=0,
                    timestamp=row['date']
                ))

        return anomalies

    def generate_recommendations(self, insights: List[TrendInsight],
                                 anomalies: List[AnomalyDetection]) -> List[ActionRecommendation]:
        """生成行动建议"""
        recommendations = []

        # 基于趋势生成建议
        for insight in insights:
            if insight.metric == "阅读量" and insight.direction == "down":
                recommendations.append(ActionRecommendation(
                    priority="high",
                    category="内容策略",
                    title="优化内容选题",
                    description="阅读量呈下降趋势，建议分析近期低阅读内容，调整选题方向，关注热点话题",
                    expected_impact="提升阅读量20-30%",
                    difficulty="medium"
                ))

            elif insight.metric == "互动率" and insight.direction == "down":
                recommendations.append(ActionRecommendation(
                    priority="high",
                    category="用户运营",
                    title="增加互动设计",
                    description="在文章末尾增加互动话题、投票或问答，引导用户留言",
                    expected_impact="提升互动率50%",
                    difficulty="easy"
                ))

            elif insight.metric == "发文频率":
                recommendations.append(ActionRecommendation(
                    priority="medium",
                    category="运营规划",
                    title="制定发布计划",
                    description="建立固定的发布时间表，如每周二、四、六晚上8点",
                    expected_impact="提升用户留存和期待",
                    difficulty="easy"
                ))

        # 基于异常生成建议
        has_spike = any(a.type == "spike" for a in anomalies)
        has_drop = any(a.type == "drop" for a in anomalies)

        if has_spike:
            recommendations.append(ActionRecommendation(
                priority="medium",
                category="内容复盘",
                title="分析爆款内容",
                description="回顾阅读量异常高的文章，总结其选题、标题、内容特点，复制成功模式",
                expected_impact="提高爆款率",
                difficulty="medium"
            ))

        if has_drop:
            recommendations.append(ActionRecommendation(
                priority="high",
                category="问题诊断",
                title="排查阅读量下降原因",
                description="检查阅读量异常下降日的内容质量、发布时间、封面图等因素",
                expected_impact="避免再次发生",
                difficulty="medium"
            ))

        # 默认建议
        if len(recommendations) < 3:
            recommendations.append(ActionRecommendation(
                priority="low",
                category="数据监控",
                title="建立数据监控习惯",
                description="每周查看数据报告，持续优化内容策略",
                expected_impact="长期提升运营效果",
                difficulty="easy"
            ))

        return sorted(recommendations, key=lambda x: {'high': 0, 'medium': 1, 'low': 2}[x.priority])

    def calculate_health_score(self, days: int = 30) -> Tuple[int, str]:
        """计算健康度评分"""
        conn = self._get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor = conn.execute("""
            SELECT COUNT(*) as articles,
                   SUM(read_count) as reads,
                   SUM(like_count) as likes,
                   AVG(read_count) as avg_reads
            FROM articles
            WHERE publish_time >= ?
        """, (start_date,))

        row = cursor.fetchone()
        conn.close()

        if not row or row['articles'] == 0:
            return 0, "无数据"

        score = 0

        # 发文活跃度 (30分)
        articles = row['articles']
        if articles >= 30:
            score += 30
        elif articles >= 15:
            score += 20
        elif articles >= 7:
            score += 10

        # 阅读量 (30分)
        avg_reads = row['avg_reads'] or 0
        if avg_reads >= 5000:
            score += 30
        elif avg_reads >= 2000:
            score += 20
        elif avg_reads >= 500:
            score += 10

        # 互动率 (20分)
        reads = row['reads'] or 0
        likes = row['likes'] or 0
        engagement = (likes / reads * 100) if reads > 0 else 0
        if engagement >= 3:
            score += 20
        elif engagement >= 1:
            score += 10

        # 数据完整性 (20分)
        score += 20

        # 状态判定
        if score >= 80:
            status = "优秀"
        elif score >= 60:
            status = "良好"
        elif score >= 40:
            status = "一般"
        else:
            status = "需改进"

        return score, status

    def generate_report(self, days: int = 30) -> AIReport:
        """生成完整AI洞察报告"""
        trends = self.analyze_trends(days)
        anomalies = self.detect_anomalies(days)
        recommendations = self.generate_recommendations(trends, anomalies)
        score, status = self.calculate_health_score(days)

        # 生成摘要
        summary_parts = []
        if status == "优秀":
            summary_parts.append(f"运营状态优秀（{score}分），各项指标表现良好")
        elif status == "需改进":
            summary_parts.append(f"运营状态需改进（{score}分），建议重点关注")
        else:
            summary_parts.append(f"运营状态{status}（{score}分）")

        if anomalies:
            summary_parts.append(f"检测到 {len(anomalies)} 个数据异常")

        if trends:
            significant = [t for t in trends if abs(t.change_pct) > 15]
            if significant:
                summary_parts.append(f"发现 {len(significant)} 个显著趋势变化")

        summary = "。".join(summary_parts) + "。"

        return AIReport(
            generated_at=datetime.now().isoformat(),
            period=f"{days}天",
            summary=summary,
            trends=trends,
            anomalies=anomalies,
            recommendations=recommendations,
            score=score,
            health_status=status
        )


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='AI智能洞察报告')
    parser.add_argument('--days', type=int, default=30, help='分析天数')
    parser.add_argument('--export', help='导出JSON路径')
    parser.add_argument('--format', choices=['json', 'text', 'markdown'], default='text',
                       help='输出格式')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    generator = AIInsightsGenerator()

    report = generator.generate_report(args.days)

    if args.format == 'json':
        output = json.dumps({
            'generated_at': report.generated_at,
            'period': report.period,
            'summary': report.summary,
            'score': report.score,
            'health_status': report.health_status,
            'trends': [asdict(t) for t in report.trends],
            'anomalies': [asdict(a) for a in report.anomalies],
            'recommendations': [asdict(r) for r in report.recommendations]
        }, ensure_ascii=False, indent=2)
        print(output)

    elif args.format == 'markdown':
        print(f"# AI运营洞察报告\n")
        print(f"**生成时间**: {report.generated_at[:19]}\n")
        print(f"**统计周期**: {report.period}\n")
        print(f"**健康评分**: {report.score}/100 ({report.health_status})\n")

        print(f"## 执行摘要\n\n{report.summary}\n")

        if report.trends:
            print("## 趋势分析\n")
            for t in report.trends:
                print(f"### {t.metric}\n")
                print(f"- 趋势: {'📈' if t.direction == 'up' else '📉' if t.direction == 'down' else '➡️'}")
                print(f"- 变化: {t.change_pct:+.1f}%")
                print(f"- 分析: {t.analysis}\n")

        if report.anomalies:
            print("## 异常检测\n")
            for a in report.anomalies:
                icon = "🔴" if a.severity == "high" else "🟡" if a.severity == "medium" else "🟢"
                print(f"{icon} **{a.description}**\n")
                print(f"- 指标: {a.affected_metric}")
                print(f"- 预期: {a.expected_value:,.0f}")
                print(f"- 实际: {a.actual_value:,.0f}\n")

        if report.recommendations:
            print("## 行动建议\n")
            for r in report.recommendations:
                priority_icon = "🔴" if r.priority == "high" else "🟡" if r.priority == "medium" else "🟢"
                print(f"{priority_icon} **{r.title}** [{r.category}]\n")
                print(f"{r.description}\n")
                print(f"- 预期效果: {r.expected_impact}")
                print(f"- 实施难度: {r.difficulty}\n")

    else:  # text format
        print(f"\n{'='*60}")
        print(f"AI智能运营洞察报告")
        print(f"{'='*60}")
        print(f"生成时间: {report.generated_at[:19]}")
        print(f"统计周期: {report.period}")
        print(f"健康评分: {report.score}/100 ({report.health_status})")
        print(f"\n{'='*60}")
        print(f"执行摘要")
        print(f"{'='*60}")
        print(report.summary)

        if report.trends:
            print(f"\n{'='*60}")
            print(f"趋势分析 ({len(report.trends)}项)")
            print(f"{'='*60}")
            for t in report.trends:
                icon = "📈" if t.direction == 'up' else "📉" if t.direction == 'down' else "➡️"
                print(f"\n{icon} {t.metric}: {t.change_pct:+.1f}% (置信度: {t.confidence:.0%})")
                print(f"   分析: {t.analysis}")
                print(f"   建议: {t.recommendation}")

        if report.anomalies:
            print(f"\n{'='*60}")
            print(f"异常检测 ({len(report.anomalies)}项)")
            print(f"{'='*60}")
            for a in report.anomalies:
                icon = "🔴" if a.severity == "high" else "🟡"
                print(f"\n{icon} {a.description}")
                print(f"   指标: {a.affected_metric}")
                print(f"   偏差: 预期 {a.expected_value:,.0f} vs 实际 {a.actual_value:,.0f}")

        if report.recommendations:
            print(f"\n{'='*60}")
            print(f"行动建议 ({len(report.recommendations)}项)")
            print(f"{'='*60}")
            for i, r in enumerate(report.recommendations, 1):
                icon = "🔴" if r.priority == "high" else "🟡" if r.priority == "medium" else "🟢"
                print(f"\n{i}. {icon} {r.title} [{r.category}]")
                print(f"   {r.description}")
                print(f"   预期: {r.expected_impact} | 难度: {r.difficulty}")

    if args.export:
        with open(args.export, 'w', encoding='utf-8') as f:
            json.dump({
                'generated_at': report.generated_at,
                'period': report.period,
                'summary': report.summary,
                'score': report.score,
                'health_status': report.health_status,
                'trends': [asdict(t) for t in report.trends],
                'anomalies': [asdict(a) for a in report.anomalies],
                'recommendations': [asdict(r) for r in report.recommendations]
            }, f, ensure_ascii=False, indent=2)
        print(f"\n报告已导出: {args.export}")


if __name__ == '__main__':
    main()
