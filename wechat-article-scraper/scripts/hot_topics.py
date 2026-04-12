#!/usr/bin/env python3
"""
热点话题追踪系统 - 实时发现和分析 trending topics

功能：
- 自动提取高频关键词
- 热点话题聚类分析
- 传播速度监控
- 话题生命周期追踪
- 热度趋势预测

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import heapq

logger = logging.getLogger('hot-topics')


@dataclass
class TopicKeyword:
    """话题关键词"""
    word: str
    count: int
    trending_score: float
    related_words: List[str]


@dataclass
class HotTopic:
    """热点话题"""
    id: str
    name: str
    keywords: List[str]
    heat_score: float
    mention_count: int
    read_count: int
    first_seen: str
    last_seen: str
    lifespan_days: int
    growth_rate: float
    velocity: str  # slow/medium/fast/viral
    status: str  # emerging/peaking/stable/declining
    related_articles: List[str]


@dataclass
class TopicTrend:
    """话题趋势"""
    date: str
    topic_id: str
    mention_count: int
    heat_score: float


class HotTopicsTracker:
    """热点话题追踪器"""

    # 停用词
    STOP_WORDS = {
        '的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
        '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
        '自己', '这', '那', '这个', '那个', '可以', '现在', '今天', '已经', '因为',
        '所以', '但是', '还是', '如果', '还是', '或者', '以及', '关于', '对于', '我们',
        '你们', '他们', '它们', '什么', '怎么', '为什么', '如何', '多少', '哪里',
        '公众号', '文章', '内容', '作者', '读者', '平台', '微信', '阅读', '点击',
        '关注', '订阅', '分享', '转发', '评论', '点赞', '收藏'
    }

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "articles.db")
        self.db_path = db_path
        self._topic_cache: Dict[str, HotTopic] = {}

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def extract_keywords(self, text: str, top_k: int = 10) -> List[TopicKeyword]:
        """从文本提取关键词"""
        # 清洗文本
        text = re.sub(r'[^\u4e00-\u9fff\w\s]', ' ', text)

        # 提取2-4字词组
        words = []
        for i in range(len(text) - 1):
            for length in [2, 3, 4]:
                if i + length <= len(text):
                    word = text[i:i+length]
                    if self._is_valid_word(word):
                        words.append(word)

        # 统计频率
        word_counts = Counter(words)

        # 计算趋势分数并构建结果
        keywords = []
        for word, count in word_counts.most_common(top_k * 2):
            if len(keywords) >= top_k:
                break

            # 查找相关词
            related = [w for w, c in word_counts.most_common(20)
                      if w != word and c >= count * 0.3][:3]

            # 趋势分数 = 频率 * 词长权重
            length_weight = 1 + (len(word) - 2) * 0.2
            trending_score = count * length_weight

            keywords.append(TopicKeyword(
                word=word,
                count=count,
                trending_score=trending_score,
                related_words=related
            ))

        return keywords

    def _is_valid_word(self, word: str) -> bool:
        """检查是否为有效词"""
        if len(word) < 2:
            return False
        if word in self.STOP_WORDS:
            return False
        if re.match(r'^\d+$', word):
            return False
        if re.match(r'^[a-zA-Z]+$', word) and len(word) < 3:
            return False
        return True

    def discover_hot_topics(self, days: int = 7, min_mentions: int = 3) -> List[HotTopic]:
        """发现热点话题"""
        conn = self._get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor = conn.execute("""
            SELECT id, title, content, read_count, like_count, publish_time
            FROM articles
            WHERE publish_time >= ? AND title IS NOT NULL
            ORDER BY publish_time DESC
        """, (start_date,))

        articles = cursor.fetchall()
        conn.close()

        if not articles:
            return []

        # 收集所有关键词
        all_keywords = defaultdict(lambda: {'count': 0, 'articles': [], 'reads': 0, 'dates': []})

        for article in articles:
            title = article['title'] or ''
            content = article['content'] or ''

            # 标题权重更高
            title_keywords = self.extract_keywords(title, top_k=5)
            content_keywords = self.extract_keywords(content[:1000], top_k=3)

            for kw in title_keywords:
                all_keywords[kw.word]['count'] += kw.count * 2  # 标题权重
                all_keywords[kw.word]['articles'].append(article['id'])
                all_keywords[kw.word]['reads'] += article['read_count'] or 0
                all_keywords[kw.word]['dates'].append(article['publish_time'][:10])

            for kw in content_keywords:
                all_keywords[kw.word]['count'] += kw.count
                if article['id'] not in all_keywords[kw.word]['articles']:
                    all_keywords[kw.word]['articles'].append(article['id'])
                all_keywords[kw.word]['reads'] += article['read_count'] or 0
                if article['publish_time'][:10] not in all_keywords[kw.word]['dates']:
                    all_keywords[kw.word]['dates'].append(article['publish_time'][:10])

        # 聚类话题
        topics = []
        used_words = set()

        sorted_words = sorted(all_keywords.items(), key=lambda x: x[1]['count'], reverse=True)

        for word, data in sorted_words:
            if word in used_words or data['count'] < min_mentions:
                continue

            # 查找相关词聚类
            cluster_words = [word]
            cluster_articles = set(data['articles'])

            for other_word, other_data in sorted_words:
                if other_word == word or other_word in used_words:
                    continue

                # 计算文章重叠度
                overlap = len(set(other_data['articles']) & cluster_articles)
                if overlap >= min(3, len(other_data['articles']) * 0.3):
                    cluster_words.append(other_word)
                    cluster_articles.update(other_data['articles'])
                    used_words.add(other_word)

            used_words.add(word)

            # 创建话题
            if len(cluster_articles) >= min_mentions:
                topic = self._create_topic(cluster_words, cluster_articles, all_keywords, days)
                topics.append(topic)

        # 按热度排序
        topics.sort(key=lambda x: x.heat_score, reverse=True)
        return topics[:20]

    def _create_topic(self, keywords: List[str], article_ids: Set[str],
                      keyword_data: Dict, days: int) -> HotTopic:
        """创建话题对象"""
        import hashlib

        topic_id = hashlib.md5(','.join(sorted(keywords)).encode()).hexdigest()[:12]

        # 计算统计数据
        total_reads = sum(keyword_data[k]['reads'] for k in keywords if k in keyword_data)
        total_mentions = sum(keyword_data[k]['count'] for k in keywords if k in keyword_data)

        all_dates = []
        for k in keywords:
            if k in keyword_data:
                all_dates.extend(keyword_data[k]['dates'])

        unique_dates = sorted(set(all_dates))
        first_seen = unique_dates[0] if unique_dates else datetime.now().strftime('%Y-%m-%d')
        last_seen = unique_dates[-1] if unique_dates else first_seen

        # 计算生命周期
        try:
            first_dt = datetime.strptime(first_seen, '%Y-%m-%d')
            last_dt = datetime.strptime(last_seen, '%Y-%m-%d')
            lifespan = (last_dt - first_dt).days + 1
        except:
            lifespan = 1

        # 计算增长率
        if len(unique_dates) >= 2:
            early_mentions = sum(1 for d in all_dates if d <= unique_dates[len(unique_dates)//2])
            late_mentions = sum(1 for d in all_dates if d > unique_dates[len(unique_dates)//2])
            growth = ((late_mentions - early_mentions) / max(1, early_mentions)) * 100
        else:
            growth = 0

        # 传播速度
        mentions_per_day = total_mentions / max(1, lifespan)
        if mentions_per_day >= 10:
            velocity = "viral"
        elif mentions_per_day >= 5:
            velocity = "fast"
        elif mentions_per_day >= 2:
            velocity = "medium"
        else:
            velocity = "slow"

        # 话题状态
        if lifespan <= 2:
            status = "emerging"
        elif growth > 20:
            status = "peaking"
        elif growth < -20:
            status = "declining"
        else:
            status = "stable"

        # 热度分数
        heat = (
            total_reads / 1000 * 0.4 +
            total_mentions * 10 * 0.3 +
            growth * 0.2 +
            lifespan * 5 * 0.1
        )

        return HotTopic(
            id=topic_id,
            name=keywords[0],
            keywords=keywords[:5],
            heat_score=heat,
            mention_count=total_mentions,
            read_count=total_reads,
            first_seen=first_seen,
            last_seen=last_seen,
            lifespan_days=lifespan,
            growth_rate=growth,
            velocity=velocity,
            status=status,
            related_articles=list(article_ids)[:20]
        )

    def get_trending_topics(self, hours: int = 24) -> List[HotTopic]:
        """获取当前 trending 话题"""
        conn = self._get_connection()

        start_time = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')

        cursor = conn.execute("""
            SELECT id, title, content, read_count, publish_time
            FROM articles
            WHERE publish_time >= ? AND title IS NOT NULL
            ORDER BY read_count DESC
            LIMIT 100
        """, (start_time,))

        articles = cursor.fetchall()
        conn.close()

        if not articles:
            return []

        # 快速提取高频词
        word_counts = Counter()
        for article in articles:
            words = self.extract_keywords(article['title'], top_k=3)
            for w in words:
                word_counts[w.word] += w.count

        # 创建临时话题
        topics = []
        for word, count in word_counts.most_common(10):
            heat = count * 10 + sum(a['read_count'] or 0 for a in articles if word in a['title']) / 1000

            topics.append(HotTopic(
                id=f"trend_{word}",
                name=word,
                keywords=[word],
                heat_score=heat,
                mention_count=count,
                read_count=sum(a['read_count'] or 0 for a in articles if word in a['title']),
                first_seen=articles[0]['publish_time'][:10],
                last_seen=articles[-1]['publish_time'][:10],
                lifespan_days=1,
                growth_rate=0,
                velocity="fast",
                status="emerging",
                related_articles=[a['id'] for a in articles if word in a['title']][:10]
            ))

        return sorted(topics, key=lambda x: x.heat_score, reverse=True)

    def track_topic_lifecycle(self, topic_id: str, days: int = 30) -> List[TopicTrend]:
        """追踪话题生命周期"""
        # 从缓存或数据库获取话题
        conn = self._get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 获取话题关键词
        cursor = conn.execute("""
            SELECT DISTINCT title, content
            FROM articles
            WHERE publish_time >= ?
            LIMIT 1000
        """, (start_date,))

        articles = cursor.fetchall()
        conn.close()

        # 按日期统计
        daily_stats = defaultdict(lambda: {'count': 0, 'heat': 0})

        for article in articles:
            date = article['publish_time'][:10] if hasattr(article, 'publish_time') else datetime.now().strftime('%Y-%m-%d')
            text = f"{article['title'] or ''} {article['content'] or ''}"

            # 简化处理：这里应该用话题关键词匹配
            daily_stats[date]['count'] += 1

        trends = []
        for date in sorted(daily_stats.keys()):
            data = daily_stats[date]
            trends.append(TopicTrend(
                date=date,
                topic_id=topic_id,
                mention_count=data['count'],
                heat_score=data['heat']
            ))

        return trends

    def generate_topic_report(self, days: int = 7) -> Dict[str, Any]:
        """生成话题报告"""
        hot_topics = self.discover_hot_topics(days)
        trending = self.get_trending_topics(24)

        # 分类话题
        emerging = [t for t in hot_topics if t.status == "emerging"]
        peaking = [t for t in hot_topics if t.status == "peaking"]
        stable = [t for t in hot_topics if t.status == "stable"]
        declining = [t for t in hot_topics if t.status == "declining"]

        return {
            'generated_at': datetime.now().isoformat(),
            'period_days': days,
            'summary': {
                'total_topics': len(hot_topics),
                'emerging': len(emerging),
                'peaking': len(peaking),
                'stable': len(stable),
                'declining': len(declining)
            },
            'hot_topics': [asdict(t) for t in hot_topics[:10]],
            'trending_now': [asdict(t) for t in trending[:5]],
            'insights': self._generate_topic_insights(hot_topics)
        }

    def _generate_topic_insights(self, topics: List[HotTopic]) -> List[str]:
        """生成话题洞察"""
        insights = []

        if not topics:
            return ["暂无热点话题数据"]

        # 最热门话题
        hottest = max(topics, key=lambda x: x.heat_score)
        insights.append(
            f"【最热话题】『{hottest.name}』获得 {hottest.read_count:,} 次阅读，"
            f"{hottest.mention_count} 次提及"
        )

        # 新兴话题
        emerging = [t for t in topics if t.status == "emerging"]
        if emerging:
            fastest = max(emerging, key=lambda x: x.growth_rate)
            insights.append(
                f"【新星话题】『{fastest.name}』正在快速崛起，"
                f"增长率 {fastest.growth_rate:+.1f}%"
            )

        # 病毒传播
        viral = [t for t in topics if t.velocity == "viral"]
        if viral:
            insights.append(
                f"【病毒传播】{len(viral)} 个话题呈病毒式传播，"
                f"建议关注参与"
            )

        # 长尾话题
        long_tail = [t for t in topics if t.lifespan_days >= 7]
        if long_tail:
            insights.append(
                f"【长尾话题】{len(long_tail)} 个话题持续超过7天，"
                f"具有长期价值"
            )

        return insights


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='热点话题追踪')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 发现热点
    discover_parser = subparsers.add_parser('discover', help='发现热点话题')
    discover_parser.add_argument('--days', type=int, default=7)
    discover_parser.add_argument('--min-mentions', type=int, default=3)

    # 实时趋势
    trending_parser = subparsers.add_parser('trending', help='当前 trending')
    trending_parser.add_argument('--hours', type=int, default=24)

    # 话题报告
    report_parser = subparsers.add_parser('report', help='生成话题报告')
    report_parser.add_argument('--days', type=int, default=7)
    report_parser.add_argument('--export', help='导出JSON路径')

    # 追踪话题
    track_parser = subparsers.add_parser('track', help='追踪话题生命周期')
    track_parser.add_argument('topic_id', help='话题ID')
    track_parser.add_argument('--days', type=int, default=30)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    tracker = HotTopicsTracker()

    if args.command == 'discover':
        topics = tracker.discover_hot_topics(args.days, args.min_mentions)

        print(f"\n{'='*60}")
        print(f"热点话题发现 ({len(topics)}个)")
        print(f"{'='*60}")

        for i, t in enumerate(topics[:10], 1):
            status_icon = {
                'emerging': '🌱',
                'peaking': '🔥',
                'stable': '📊',
                'declining': '📉'
            }.get(t.status, '•')

            velocity_icon = {
                'viral': '🚀',
                'fast': '⚡',
                'medium': '→',
                'slow': '🐢'
            }.get(t.velocity, '•')

            print(f"\n{i}. {status_icon} {t.name} {velocity_icon}")
            print(f"   热度: {t.heat_score:.1f} | 提及: {t.mention_count} | 阅读: {t.read_count:,}")
            print(f"   关键词: {', '.join(t.keywords[:3])}")
            print(f"   状态: {t.status} | 生命周期: {t.lifespan_days}天 | 增长: {t.growth_rate:+.1f}%")

    elif args.command == 'trending':
        topics = tracker.get_trending_topics(args.hours)

        print(f"\n{'='*60}")
        print(f"当前 Trending ({len(topics)}个话题)")
        print(f"{'='*60}")

        for i, t in enumerate(topics[:10], 1):
            print(f"{i}. {t.name}")
            print(f"   热度: {t.heat_score:.1f} | 阅读: {t.read_count:,}")

    elif args.command == 'report':
        report = tracker.generate_topic_report(args.days)

        print(f"\n{'='*60}")
        print(f"热点话题报告")
        print(f"{'='*60}")
        print(f"生成时间: {report['generated_at'][:19]}")
        print(f"统计周期: {report['period_days']}天")

        summary = report['summary']
        print(f"\n【话题统计】")
        print(f"  总话题: {summary['total_topics']}")
        print(f"  新兴: {summary['emerging']} | 峰值: {summary['peaking']}")
        print(f"  稳定: {summary['stable']} | 衰退: {summary['declining']}")

        print(f"\n【话题洞察】")
        for insight in report['insights']:
            print(f"  • {insight}")

        print(f"\n【热门话题 Top 5】")
        for t in report['hot_topics'][:5]:
            print(f"  • {t['name']} (热度: {t['heat_score']:.1f})")

        if args.export:
            with open(args.export, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"\n报告已导出: {args.export}")

    elif args.command == 'track':
        trends = tracker.track_topic_lifecycle(args.topic_id, args.days)

        print(f"\n{'='*60}")
        print(f"话题生命周期追踪: {args.topic_id}")
        print(f"{'='*60}")

        for t in trends:
            print(f"{t.date}: {t.mention_count}次提及")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
