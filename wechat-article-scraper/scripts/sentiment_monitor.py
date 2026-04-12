#!/usr/bin/env python3
"""
舆情监控与预警系统 - 专业级品牌监控和危机预警

功能：
- 敏感词实时检测
- 情感趋势监控
- 品牌提及追踪
- 危机预警（异常传播速度、负面情绪激增）
- 舆情仪表盘

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict, Counter

logger = logging.getLogger('sentiment-monitor')


class AlertLevel(Enum):
    """预警等级"""
    INFO = "info"         # 提示
    WARNING = "warning"   # 警告
    CRITICAL = "critical" # 严重


class AlertType(Enum):
    """预警类型"""
    SENSITIVE_WORD = "sensitive_word"     # 敏感词
    NEGATIVE_SENTIMENT = "negative_sentiment"  # 负面情绪
    BRAND_MENTION = "brand_mention"       # 品牌提及
    VIRAL_SPREAD = "viral_spread"         # 病毒传播
    CRISIS = "crisis"                     # 危机事件


@dataclass
class SensitiveWord:
    """敏感词"""
    word: str
    category: str          # 政治、色情、暴力、广告等
    level: str             # low, medium, high
    created_at: str = ""

    def to_dict(self) -> Dict:
        return {
            "word": self.word,
            "category": self.category,
            "level": self.level,
            "created_at": self.created_at
        }


@dataclass
class BrandKeyword:
    """品牌关键词"""
    id: str
    name: str
    keywords: List[str]    # 匹配关键词列表
    exclude_words: List[str]  # 排除词
    alert_enabled: bool = True
    created_at: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "keywords": self.keywords,
            "exclude_words": self.exclude_words,
            "alert_enabled": self.alert_enabled,
            "created_at": self.created_at
        }


@dataclass
class AlertEvent:
    """预警事件"""
    id: str
    alert_type: str
    level: str
    title: str
    description: str
    article_id: str
    article_title: str
    account_name: str
    triggered_at: str
    resolved_at: str = ""
    is_resolved: bool = False
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "level": self.level,
            "title": self.title,
            "description": self.description,
            "article_id": self.article_id,
            "article_title": self.article_title,
            "account_name": self.account_name,
            "triggered_at": self.triggered_at,
            "resolved_at": self.resolved_at,
            "is_resolved": self.is_resolved,
            "metadata": self.metadata
        }


@dataclass
class SentimentTrend:
    """情感趋势"""
    date: str
    positive: int
    neutral: int
    negative: int
    total: int = 0

    def __post_init__(self):
        self.total = self.positive + self.neutral + self.negative

    def to_dict(self) -> Dict:
        return {
            "date": self.date,
            "positive": self.positive,
            "neutral": self.neutral,
            "negative": self.negative,
            "total": self.total,
            "positive_rate": self.positive / self.total if self.total > 0 else 0,
            "negative_rate": self.negative / self.total if self.total > 0 else 0
        }


class SentimentMonitor:
    """舆情监控系统"""

    # 默认敏感词库
    DEFAULT_SENSITIVE_WORDS = {
        "political": ["政治敏感词1", "政治敏感词2"],  # 实际使用时需要完整词库
        "porn": ["色情词1", "色情词2"],
        "violence": ["暴力词1", "暴力词2"],
        "gambling": ["赌博", "博彩", "赌马"],
        "drugs": ["毒品", "吸毒", "贩毒"],
        "fraud": ["诈骗", "欺诈", "骗局"],
    }

    def __init__(self, db_path: str = None, articles_db: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "sentiment.db")

        self.db_path = db_path
        self.articles_db = articles_db or str(Path.home() / ".wechat-scraper" / "articles.db")
        self._init_db()
        self._load_default_words()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)

        # 敏感词表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sensitive_words (
                word TEXT PRIMARY KEY,
                category TEXT,
                level TEXT DEFAULT 'medium',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 品牌关键词表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS brand_keywords (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                keywords TEXT,  -- JSON array
                exclude_words TEXT,  -- JSON array
                alert_enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 预警事件表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_events (
                id TEXT PRIMARY KEY,
                alert_type TEXT,
                level TEXT,
                title TEXT,
                description TEXT,
                article_id TEXT,
                article_title TEXT,
                account_name TEXT,
                triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                is_resolved INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            )
        """)

        # 品牌提及记录表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS brand_mentions (
                id TEXT PRIMARY KEY,
                brand_id TEXT,
                article_id TEXT,
                mention_count INTEGER DEFAULT 1,
                context TEXT,  -- 提及上下文
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def _load_default_words(self):
        """加载默认敏感词"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM sensitive_words")
        count = cursor.fetchone()[0]

        if count == 0:
            # 首次初始化，加载默认词库
            for category, words in self.DEFAULT_SENSITIVE_WORDS.items():
                level = "high" if category in ["political", "drugs"] else "medium"
                for word in words:
                    try:
                        conn.execute(
                            "INSERT INTO sensitive_words (word, category, level) VALUES (?, ?, ?)",
                            (word, category, level)
                        )
                    except sqlite3.IntegrityError:
                        pass
            conn.commit()

        conn.close()

    # ========== 敏感词管理 ==========

    def add_sensitive_word(self, word: str, category: str, level: str = "medium") -> bool:
        """添加敏感词"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO sensitive_words (word, category, level) VALUES (?, ?, ?)",
                (word, category, level)
            )
            conn.commit()
            logger.info(f"敏感词已添加: {word}")
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def remove_sensitive_word(self, word: str) -> bool:
        """移除敏感词"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM sensitive_words WHERE word = ?", (word,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def get_sensitive_words(self, category: str = None) -> List[SensitiveWord]:
        """获取敏感词列表"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        if category:
            cursor = conn.execute(
                "SELECT * FROM sensitive_words WHERE category = ? ORDER BY level DESC",
                (category,)
            )
        else:
            cursor = conn.execute("SELECT * FROM sensitive_words ORDER BY level DESC")

        rows = cursor.fetchall()
        conn.close()

        return [SensitiveWord(
            word=row["word"],
            category=row["category"],
            level=row["level"],
            created_at=row["created_at"]
        ) for row in rows]

    def scan_sensitive_words(self, text: str) -> List[Dict]:
        """扫描文本中的敏感词"""
        words = self.get_sensitive_words()
        findings = []

        for word_obj in words:
            word = word_obj.word
            if word in text:
                # 找到所有位置
                for match in re.finditer(re.escape(word), text):
                    findings.append({
                        "word": word,
                        "category": word_obj.category,
                        "level": word_obj.level,
                        "position": match.start(),
                        "context": text[max(0, match.start()-10):min(len(text), match.end()+10)]
                    })

        return sorted(findings, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["level"], 3))

    # ========== 品牌关键词管理 ==========

    def add_brand_keyword(self, name: str, keywords: List[str],
                         exclude_words: List[str] = None) -> BrandKeyword:
        """添加品牌关键词"""
        import hashlib

        brand_id = hashlib.md5(f"{name}{datetime.now()}".encode()).hexdigest()[:12]

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO brand_keywords (id, name, keywords, exclude_words, alert_enabled)
               VALUES (?, ?, ?, ?, ?)""",
            (brand_id, name, json.dumps(keywords), json.dumps(exclude_words or []), 1)
        )
        conn.commit()
        conn.close()

        logger.info(f"品牌关键词已添加: {name} ({brand_id})")
        return self.get_brand_keyword(brand_id)

    def get_brand_keyword(self, brand_id: str) -> Optional[BrandKeyword]:
        """获取品牌关键词"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM brand_keywords WHERE id = ?", (brand_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return BrandKeyword(
            id=row["id"],
            name=row["name"],
            keywords=json.loads(row["keywords"]),
            exclude_words=json.loads(row["exclude_words"]),
            alert_enabled=bool(row["alert_enabled"]),
            created_at=row["created_at"]
        )

    def list_brand_keywords(self) -> List[BrandKeyword]:
        """列出所有品牌关键词"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM brand_keywords ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()

        return [BrandKeyword(
            id=row["id"],
            name=row["name"],
            keywords=json.loads(row["keywords"]),
            exclude_words=json.loads(row["exclude_words"]),
            alert_enabled=bool(row["alert_enabled"]),
            created_at=row["created_at"]
        ) for row in rows]

    def track_brand_mentions(self, article_id: str, title: str, content: str) -> List[Dict]:
        """追踪文章中的品牌提及"""
        brands = self.list_brand_keywords()
        mentions = []

        text = f"{title} {content}"

        for brand in brands:
            if not brand.alert_enabled:
                continue

            mention_count = 0
            contexts = []

            for keyword in brand.keywords:
                if keyword in text:
                    # 检查排除词
                    excluded = any(exclude in text for exclude in brand.exclude_words)
                    if excluded:
                        continue

                    mention_count += text.count(keyword)

                    # 提取上下文
                    for match in re.finditer(re.escape(keyword), text):
                        start = max(0, match.start() - 30)
                        end = min(len(text), match.end() + 30)
                        context = text[start:end]
                        contexts.append(context)

            if mention_count > 0:
                # 记录提及
                mention_id = f"{brand.id}_{article_id}_{int(datetime.now().timestamp())}"

                conn = sqlite3.connect(self.db_path)
                conn.execute(
                    """INSERT OR REPLACE INTO brand_mentions
                       (id, brand_id, article_id, mention_count, context)
                       VALUES (?, ?, ?, ?, ?)""",
                    (mention_id, brand.id, article_id, mention_count, json.dumps(contexts[:3]))
                )
                conn.commit()
                conn.close()

                mentions.append({
                    "brand_id": brand.id,
                    "brand_name": brand.name,
                    "mention_count": mention_count,
                    "contexts": contexts[:3]
                })

                # 触发预警
                if mention_count >= 3:
                    self._create_alert(
                        AlertType.BRAND_MENTION,
                        AlertLevel.INFO if mention_count < 5 else AlertLevel.WARNING,
                        f"品牌 '{brand.name}' 被提及 {mention_count} 次",
                        f"文章《{title}》中提及品牌 '{brand.name}' {mention_count} 次",
                        article_id, title, ""
                    )

        return mentions

    # ========== 预警管理 ==========

    def _create_alert(self, alert_type: AlertType, level: AlertLevel,
                     title: str, description: str, article_id: str,
                     article_title: str, account_name: str,
                     metadata: Dict = None) -> AlertEvent:
        """创建预警"""
        import hashlib

        alert_id = hashlib.md5(
            f"{alert_type.value}{article_id}{datetime.now()}".encode()
        ).hexdigest()[:12]

        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO alert_events
               (id, alert_type, level, title, description, article_id, article_title,
                account_name, triggered_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (alert_id, alert_type.value, level.value, title, description,
             article_id, article_title, account_name, now, json.dumps(metadata or {}))
        )
        conn.commit()
        conn.close()

        logger.warning(f"预警触发 [{level.value}]: {title}")

        return AlertEvent(
            id=alert_id,
            alert_type=alert_type.value,
            level=level.value,
            title=title,
            description=description,
            article_id=article_id,
            article_title=article_title,
            account_name=account_name,
            triggered_at=now,
            metadata=metadata or {}
        )

    def get_alerts(self, level: str = None, alert_type: str = None,
                   resolved: bool = None, limit: int = 50) -> List[AlertEvent]:
        """获取预警列表"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        conditions = []
        params = []

        if level:
            conditions.append("level = ?")
            params.append(level)
        if alert_type:
            conditions.append("alert_type = ?")
            params.append(alert_type)
        if resolved is not None:
            conditions.append("is_resolved = ?")
            params.append(1 if resolved else 0)

        sql = "SELECT * FROM alert_events"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY triggered_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        return [AlertEvent(
            id=row["id"],
            alert_type=row["alert_type"],
            level=row["level"],
            title=row["title"],
            description=row["description"],
            article_id=row["article_id"],
            article_title=row["article_title"],
            account_name=row["account_name"],
            triggered_at=row["triggered_at"],
            resolved_at=row["resolved_at"] or "",
            is_resolved=bool(row["is_resolved"]),
            metadata=json.loads(row["metadata"])
        ) for row in rows]

    def resolve_alert(self, alert_id: str) -> bool:
        """解决预警"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """UPDATE alert_events SET is_resolved = 1, resolved_at = ?
               WHERE id = ?""",
            (datetime.now().isoformat(), alert_id)
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    # ========== 情感分析 ==========

    def analyze_sentiment(self, text: str) -> Dict:
        """简单情感分析（基于关键词）"""
        # 正面词
        positive_words = ["好", "棒", "优秀", "喜欢", "推荐", "赞", "成功", "创新",
                         "突破", "领先", "第一", "好评", "满意", "感谢"]
        # 负面词
        negative_words = ["差", "烂", "垃圾", "失败", "失望", "吐槽", "坑", "骗",
                         "假", "问题", "bug", "崩溃", "难用", "后悔", "投诉"]

        text_lower = text.lower()

        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        total = positive_count + negative_count

        if total == 0:
            sentiment = "neutral"
            score = 0.5
        elif positive_count > negative_count:
            sentiment = "positive"
            score = 0.5 + (positive_count - negative_count) / (2 * total)
        else:
            sentiment = "negative"
            score = 0.5 - (negative_count - positive_count) / (2 * total)

        return {
            "sentiment": sentiment,
            "score": score,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "confidence": min(total / 10, 1.0)  # 词越多置信度越高
        }

    def get_sentiment_trend(self, days: int = 7) -> List[SentimentTrend]:
        """获取情感趋势"""
        conn = sqlite3.connect(self.articles_db)
        conn.row_factory = sqlite3.Row

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        cursor = conn.execute(
            """SELECT publish_time, title, content FROM articles
               WHERE publish_time >= ? ORDER BY publish_time""",
            (start_date,)
        )
        rows = cursor.fetchall()
        conn.close()

        # 按日期统计
        daily_sentiment = defaultdict(lambda: {"positive": 0, "neutral": 0, "negative": 0})

        for row in rows:
            date = row["publish_time"][:10] if row["publish_time"] else ""
            if not date:
                continue

            text = f"{row['title'] or ''} {row['content'] or ''}"
            sentiment = self.analyze_sentiment(text)

            daily_sentiment[date][sentiment["sentiment"]] += 1

        # 转换为列表
        trends = []
        for date in sorted(daily_sentiment.keys()):
            data = daily_sentiment[date]
            trends.append(SentimentTrend(
                date=date,
                positive=data["positive"],
                neutral=data["neutral"],
                negative=data["negative"]
            ))

        return trends

    # ========== 危机检测 ==========

    def detect_crisis(self, article: Dict) -> Optional[AlertEvent]:
        """检测危机信号"""
        alerts = []

        # 1. 检测敏感词
        text = f"{article.get('title', '')} {article.get('content', '')}"
        sensitive_findings = self.scan_sensitive_words(text)

        if sensitive_findings:
            high_risk = [f for f in sensitive_findings if f["level"] == "high"]
            if high_risk:
                alerts.append(self._create_alert(
                    AlertType.SENSITIVE_WORD,
                    AlertLevel.CRITICAL,
                    f"检测到高危敏感词: {high_risk[0]['word']}",
                    f"发现 {len(high_risk)} 个高危敏感词",
                    article.get("id", ""),
                    article.get("title", ""),
                    article.get("account_name", ""),
                    {"words": high_risk}
                ))

        # 2. 检测负面情绪
        sentiment = self.analyze_sentiment(text)
        if sentiment["sentiment"] == "negative" and sentiment["score"] < 0.3:
            alerts.append(self._create_alert(
                AlertType.NEGATIVE_SENTIMENT,
                AlertLevel.WARNING,
                "检测到强烈负面情绪",
                f"负面情感评分: {sentiment['score']:.2f}",
                article.get("id", ""),
                article.get("title", ""),
                article.get("account_name", ""),
                sentiment
            ))

        # 3. 检测异常传播速度（需要历史数据）
        read_count = article.get("read_count", 0) or 0
        like_count = article.get("like_count", 0) or 0

        if read_count > 100000:  # 10万+阅读
            alerts.append(self._create_alert(
                AlertType.VIRAL_SPREAD,
                AlertLevel.INFO,
                f"文章传播量异常: {read_count:,} 阅读",
                "该文章阅读量超过10万，可能正在病毒式传播",
                article.get("id", ""),
                article.get("title", ""),
                article.get("account_name", ""),
                {"read_count": read_count, "like_count": like_count}
            ))

        return alerts[0] if alerts else None

    # ========== 统计 ==========

    def get_stats(self) -> Dict:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 敏感词统计
        cursor.execute("SELECT COUNT(*) FROM sensitive_words")
        sensitive_word_count = cursor.fetchone()[0]

        cursor.execute("SELECT category, COUNT(*) FROM sensitive_words GROUP BY category")
        category_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # 品牌统计
        cursor.execute("SELECT COUNT(*) FROM brand_keywords")
        brand_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM brand_mentions")
        mention_count = cursor.fetchone()[0]

        # 预警统计
        cursor.execute("SELECT COUNT(*) FROM alert_events")
        total_alerts = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM alert_events WHERE is_resolved = 0")
        unresolved_alerts = cursor.fetchone()[0]

        cursor.execute("SELECT level, COUNT(*) FROM alert_events GROUP BY level")
        level_counts = {row[0]: row[1] for row in cursor.fetchall()}

        conn.close()

        return {
            "sensitive_words": {
                "total": sensitive_word_count,
                "by_category": category_counts
            },
            "brands": {
                "total": brand_count,
                "mentions": mention_count
            },
            "alerts": {
                "total": total_alerts,
                "unresolved": unresolved_alerts,
                "by_level": level_counts
            }
        }


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='舆情监控系统')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 敏感词管理
    word_parser = subparsers.add_parser('word', help='敏感词管理')
    word_parser.add_argument('action', choices=['add', 'remove', 'list'])
    word_parser.add_argument('--word', help='敏感词')
    word_parser.add_argument('--category', help='分类')
    word_parser.add_argument('--level', default='medium', help='等级')

    # 品牌管理
    brand_parser = subparsers.add_parser('brand', help='品牌关键词管理')
    brand_parser.add_argument('action', choices=['add', 'list'])
    brand_parser.add_argument('--name', help='品牌名称')
    brand_parser.add_argument('--keywords', help='关键词(JSON数组)')

    # 预警
    alert_parser = subparsers.add_parser('alert', help='预警管理')
    alert_parser.add_argument('action', choices=['list', 'resolve'])
    alert_parser.add_argument('--id', help='预警ID')
    alert_parser.add_argument('--level', help='筛选等级')

    # 趋势
    subparsers.add_parser('trend', help='情感趋势')

    # 统计
    subparsers.add_parser('stats', help='统计信息')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    monitor = SentimentMonitor()

    if args.command == 'word':
        if args.action == 'add':
            if not args.word or not args.category:
                print("请提供 --word 和 --category")
                return
            if monitor.add_sensitive_word(args.word, args.category, args.level):
                print(f"敏感词已添加: {args.word}")
            else:
                print("添加失败，可能已存在")

        elif args.action == 'remove':
            if not args.word:
                print("请提供 --word")
                return
            if monitor.remove_sensitive_word(args.word):
                print(f"敏感词已移除: {args.word}")
            else:
                print("移除失败")

        elif args.action == 'list':
            words = monitor.get_sensitive_words(args.category)
            print(f"\n敏感词列表 ({len(words)}个):\n")
            for w in words:
                print(f"  [{w.level}] {w.word} ({w.category})")

    elif args.command == 'brand':
        if args.action == 'add':
            if not args.name or not args.keywords:
                print("请提供 --name 和 --keywords")
                return
            import json
            keywords = json.loads(args.keywords)
            brand = monitor.add_brand_keyword(args.name, keywords)
            print(f"品牌已添加: {brand.name} ({brand.id})")

        elif args.action == 'list':
            brands = monitor.list_brand_keywords()
            print(f"\n品牌列表 ({len(brands)}个):\n")
            for b in brands:
                print(f"  {b.name}: {', '.join(b.keywords)}")

    elif args.command == 'alert':
        if args.action == 'list':
            alerts = monitor.get_alerts(level=args.level, resolved=False)
            print(f"\n未解决预警 ({len(alerts)}个):\n")
            for a in alerts:
                icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(a.level, "⚪")
                print(f"  {icon} [{a.level}] {a.title}")
                print(f"      {a.triggered_at[:16]} | {a.article_title[:30]}...")

        elif args.action == 'resolve':
            if not args.id:
                print("请提供 --id")
                return
            if monitor.resolve_alert(args.id):
                print("预警已解决")
            else:
                print("解决失败")

    elif args.command == 'trend':
        trends = monitor.get_sentiment_trend(days=7)
        print("\n情感趋势 (最近7天):\n")
        for t in trends:
            print(f"  {t.date}: 正{t.positive} 中{t.neutral} 负{t.negative}")

    elif args.command == 'stats':
        stats = monitor.get_stats()
        print("\n舆情监控统计:\n")
        print(f"  敏感词: {stats['sensitive_words']['total']} 个")
        print(f"  品牌: {stats['brands']['total']} 个")
        print(f"  提及: {stats['brands']['mentions']} 次")
        print(f"  预警: {stats['alerts']['total']} 个 (未解决: {stats['alerts']['unresolved']})")


if __name__ == '__main__':
    main()
