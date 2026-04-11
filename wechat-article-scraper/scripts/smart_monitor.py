#!/usr/bin/env python3
"""
智能监控与告警系统 v2.0 - 微信公众号文章智能监控

核心功能：
- 智能去重：标题相似度 + 内容哈希双重检测
- 优先级算法：WCI 病毒指数 + 关键词匹配
- 智能批处理：高优先级实时推送，普通优先级聚合摘要
- 告警疲劳保护：静默时段、速率限制、冷却期
- 全渠道集成：6 种 webhook 通知渠道

吸取竞品精华：
- IFTTT: 灵活的触发器配置
- Zapier: 多平台工作流
- 微信公众号助手: 实时推送体验

作者: Claude Code
版本: 2.0.0
"""

import os
import sys
import json
import time
import hashlib
import difflib
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict

# 配置日志
logger = logging.getLogger('smart-monitor')


class Priority(Enum):
    """文章优先级"""
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class ArticleFingerprint:
    """文章指纹 - 用于智能去重"""
    url: str
    title: str
    content_hash: str  # SHA256 内容哈希
    title_signature: str  # 标题特征（小写+去空格）
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def similarity_with(self, other: 'ArticleFingerprint') -> float:
        """计算与另一篇文章的相似度（0-1）"""
        # 1. URL 完全匹配
        if self.url == other.url:
            return 1.0

        # 2. 内容哈希完全匹配
        if self.content_hash == other.content_hash:
            return 1.0

        # 3. 标题相似度（使用 SequenceMatcher）
        title_sim = difflib.SequenceMatcher(
            None,
            self.title_signature,
            other.title_signature
        ).ratio()

        return title_sim


@dataclass
class WCIMetrics:
    """WCI (WeChat Communication Index) 指标"""
    read_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    watch_count: int = 0

    def calculate_wci(self) -> float:
        """
        计算 WCI 指数

        权重参考行业标准：
        - 阅读量 (R): 权重 0.4
        - 点赞量 (L): 权重 0.25
        - 评论量 (C): 权重 0.15
        - 分享量 (S): 权重 0.2
        """
        # 对数平滑处理，避免极端值影响
        import math

        r_score = math.log10(max(self.read_count, 1)) * 0.4
        l_score = math.log10(max(self.like_count, 1)) * 0.25
        c_score = math.log10(max(self.comment_count, 1)) * 0.15
        s_score = math.log10(max(self.share_count, 1)) * 0.2

        # 归一化到 0-1000 范围
        wci = (r_score + l_score + c_score + s_score) * 100
        return round(wci, 2)


@dataclass
class SmartArticle:
    """智能文章数据类"""
    url: str
    title: str
    account_name: str
    content: str = ""
    abstract: str = ""
    publish_time: str = ""
    discovered_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 传播指标
    metrics: WCIMetrics = field(default_factory=WCIMetrics)

    # 计算字段
    wci_score: float = 0.0
    priority: str = Priority.NORMAL.value
    keyword_matches: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.wci_score:
            self.wci_score = self.metrics.calculate_wci()

    def to_fingerprint(self) -> ArticleFingerprint:
        """生成文章指纹"""
        return ArticleFingerprint(
            url=self.url,
            title=self.title,
            content_hash=hashlib.sha256(self.content.encode()).hexdigest()[:16],
            title_signature=self.title.lower().replace(' ', '').replace('　', '')
        )


@dataclass
class KeywordRule:
    """关键词规则"""
    keyword: str
    weight: float = 1.0  # 权重
    priority_boost: str = Priority.NORMAL.value  # 提升到的优先级


@dataclass
class QuietHours:
    """静默时段配置"""
    enabled: bool = True
    start_hour: int = 23  # 23:00
    end_hour: int = 8     # 08:00
    timezone: str = "Asia/Shanghai"

    def is_quiet_time(self, dt: Optional[datetime] = None) -> bool:
        """检查当前是否为静默时段"""
        if not self.enabled:
            return False

        if dt is None:
            dt = datetime.now()

        hour = dt.hour
        if self.start_hour <= self.end_hour:
            return self.start_hour <= hour < self.end_hour
        else:
            # 跨午夜的情况（如 23:00 - 08:00）
            return hour >= self.start_hour or hour < self.end_hour


@dataclass
class RateLimit:
    """速率限制配置"""
    enabled: bool = True
    max_per_hour: int = 10  # 每小时最多推送条数
    max_per_account_per_hour: int = 3  # 每个账号每小时最多推送条数
    cooldown_minutes: int = 60  # 同一文章冷却期（分钟）


@dataclass
class SmartMonitorConfig:
    """智能监控配置"""
    # 去重配置
    dedup_enabled: bool = True
    similarity_threshold: float = 0.85  # 相似度阈值，超过视为重复

    # 优先级阈值
    high_priority_wci_threshold: float = 500.0
    high_priority_keywords: List[KeywordRule] = field(default_factory=list)

    # 批处理配置
    batch_enabled: bool = True
    batch_interval_minutes: int = 60  # 聚合间隔

    # 告警疲劳保护
    quiet_hours: QuietHours = field(default_factory=QuietHours)
    rate_limit: RateLimit = field(default_factory=RateLimit)

    # 渠道配置（不同优先级发送到不同渠道）
    channels_by_priority: Dict[str, List[str]] = field(default_factory=lambda: {
        Priority.HIGH.value: [],      # 高优先级发送到所有配置的渠道
        Priority.NORMAL.value: [],    # 普通优先级批量发送
        Priority.LOW.value: []        # 低优先级只发送 RSS
    })


class DeduplicationEngine:
    """智能去重引擎"""

    def __init__(self, data_dir: Path, similarity_threshold: float = 0.85):
        self.data_dir = data_dir
        self.similarity_threshold = similarity_threshold
        self.fingerprint_file = data_dir / 'article_fingerprints.json'
        self.fingerprints: List[ArticleFingerprint] = []
        self._load_fingerprints()

    def _load_fingerprints(self):
        """加载历史指纹"""
        if self.fingerprint_file.exists():
            try:
                data = json.loads(self.fingerprint_file.read_text(encoding='utf-8'))
                self.fingerprints = [ArticleFingerprint(**f) for f in data]
                logger.info(f"已加载 {len(self.fingerprints)} 个文章指纹")
            except Exception as e:
                logger.error(f"加载指纹失败: {e}")

    def _save_fingerprints(self):
        """保存指纹"""
        try:
            data = [asdict(f) for f in self.fingerprints]
            self.fingerprint_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"保存指纹失败: {e}")

    def is_duplicate(self, article: SmartArticle) -> Tuple[bool, Optional[float]]:
        """
        检查文章是否重复

        Returns:
            (是否重复, 最高相似度)
        """
        new_fp = article.to_fingerprint()

        max_similarity = 0.0
        for fp in self.fingerprints:
            sim = new_fp.similarity_with(fp)
            max_similarity = max(max_similarity, sim)

            if sim >= self.similarity_threshold:
                logger.info(f"检测到重复文章: '{article.title}' (相似度: {sim:.2f})")
                return True, sim

        return False, max_similarity

    def add_fingerprint(self, article: SmartArticle):
        """添加文章指纹"""
        fp = article.to_fingerprint()
        self.fingerprints.append(fp)

        # 保留最近 1000 条指纹
        if len(self.fingerprints) > 1000:
            self.fingerprints = self.fingerprints[-1000:]

        self._save_fingerprints()

    def cleanup_old_fingerprints(self, days: int = 30):
        """清理旧指纹"""
        cutoff = datetime.now() - timedelta(days=days)
        self.fingerprints = [
            f for f in self.fingerprints
            if datetime.fromisoformat(f.created_at) > cutoff
        ]
        self._save_fingerprints()


class PriorityEngine:
    """优先级计算引擎"""

    def __init__(self, config: SmartMonitorConfig):
        self.config = config

    def calculate_priority(self, article: SmartArticle) -> Tuple[Priority, List[str], float]:
        """
        计算文章优先级

        Returns:
            (优先级, 匹配的关键词列表, 最终得分)
        """
        reasons = []
        score = 0.0

        # 1. WCI 评分
        wci = article.wci_score
        if wci >= self.config.high_priority_wci_threshold:
            score += 50
            reasons.append(f"WCI高({wci})")

        # 2. 关键词匹配
        matched_keywords = []
        text_to_match = f"{article.title} {article.abstract}".lower()

        for rule in self.config.high_priority_keywords:
            if rule.keyword.lower() in text_to_match:
                matched_keywords.append(rule.keyword)
                score += rule.weight * 10
                reasons.append(f"关键词:{rule.keyword}")

        article.keyword_matches = matched_keywords

        # 3. 确定优先级
        if score >= 50 or wci >= self.config.high_priority_wci_threshold:
            priority = Priority.HIGH
        elif score >= 20:
            priority = Priority.NORMAL
        else:
            priority = Priority.LOW

        return priority, reasons, score


class RateLimiter:
    """速率限制器"""

    def __init__(self, data_dir: Path, config: RateLimit):
        self.data_dir = data_dir
        self.config = config
        self.history_file = data_dir / 'notification_history.json'
        self.history: List[Dict] = []
        self._load_history()

    def _load_history(self):
        """加载通知历史"""
        if self.history_file.exists():
            try:
                self.history = json.loads(self.history_file.read_text(encoding='utf-8'))
            except Exception as e:
                logger.error(f"加载历史失败: {e}")

    def _save_history(self):
        """保存通知历史"""
        try:
            # 只保留最近 7 天的记录
            cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            self.history = [h for h in self.history if h.get('time', '') > cutoff]

            self.history_file.write_text(
                json.dumps(self.history, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"保存历史失败: {e}")

    def can_notify(self, article: SmartArticle) -> Tuple[bool, str]:
        """
        检查是否可以发送通知

        Returns:
            (是否可以通知, 原因)
        """
        if not self.config.enabled:
            return True, "速率限制已禁用"

        now = datetime.now()
        one_hour_ago = (now - timedelta(hours=1)).isoformat()

        # 1. 检查全局每小时限制
        recent_notifications = [
            h for h in self.history
            if h.get('time', '') > one_hour_ago
        ]
        if len(recent_notifications) >= self.config.max_per_hour:
            return False, f"达到每小时限制({self.config.max_per_hour})"

        # 2. 检查账号每小时限制
        account_notifications = [
            h for h in recent_notifications
            if h.get('account') == article.account_name
        ]
        if len(account_notifications) >= self.config.max_per_account_per_hour:
            return False, f"账号{article.account_name}达到每小时限制"

        # 3. 检查冷却期
        cooldown_threshold = (now - timedelta(minutes=self.config.cooldown_minutes)).isoformat()
        duplicate_in_cooldown = [
            h for h in self.history
            if h.get('url') == article.url and h.get('time', '') > cooldown_threshold
        ]
        if duplicate_in_cooldown:
            return False, f"文章在冷却期内({self.config.cooldown_minutes}分钟)"

        return True, "通过速率检查"

    def record_notification(self, article: SmartArticle, priority: Priority):
        """记录通知发送"""
        self.history.append({
            'url': article.url,
            'title': article.title,
            'account': article.account_name,
            'priority': priority.value,
            'time': datetime.now().isoformat()
        })
        self._save_history()


class SmartBatcher:
    """智能批处理器"""

    def __init__(self, data_dir: Path, interval_minutes: int = 60):
        self.data_dir = data_dir
        self.interval_minutes = interval_minutes
        self.batch_file = data_dir / 'pending_batch.json'
        self.pending_articles: List[SmartArticle] = []
        self._load_pending()

    def _load_pending(self):
        """加载待处理文章"""
        if self.batch_file.exists():
            try:
                data = json.loads(self.batch_file.read_text(encoding='utf-8'))
                self.pending_articles = [SmartArticle(**a) for a in data]
            except Exception as e:
                logger.error(f"加载待处理文章失败: {e}")

    def _save_pending(self):
        """保存待处理文章"""
        try:
            data = [asdict(a) for a in self.pending_articles]
            self.batch_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"保存待处理文章失败: {e}")

    def add_to_batch(self, article: SmartArticle):
        """添加到批处理队列"""
        self.pending_articles.append(article)
        self._save_pending()
        logger.info(f"文章加入批处理队列: {article.title}")

    def should_flush(self) -> bool:
        """检查是否应该发送批量摘要"""
        if not self.pending_articles:
            return False

        # 检查最早的文章是否超过间隔时间
        oldest = min(
            datetime.fromisoformat(a.discovered_at)
            for a in self.pending_articles
        )
        elapsed = (datetime.now() - oldest).total_seconds() / 60

        return elapsed >= self.interval_minutes

    def flush_batch(self) -> Optional[Dict]:
        """
        发送批量摘要

        Returns:
            批量摘要数据，如果没有待处理文章则返回 None
        """
        if not self.pending_articles:
            return None

        articles = self.pending_articles
        self.pending_articles = []
        self._save_pending()

        # 生成摘要
        total = len(articles)
        high_priority = sum(1 for a in articles if a.priority == Priority.HIGH.value)

        # 按账号分组
        by_account = defaultdict(list)
        for a in articles:
            by_account[a.account_name].append(a)

        summary = {
            'type': 'batch_summary',
            'total_articles': total,
            'high_priority_count': high_priority,
            'accounts': list(by_account.keys()),
            'articles': [
                {
                    'title': a.title,
                    'account': a.account_name,
                    'priority': a.priority,
                    'url': a.url,
                    'wci': a.wci_score
                }
                for a in sorted(articles, key=lambda x: x.wci_score, reverse=True)[:10]
            ],
            'generated_at': datetime.now().isoformat()
        }

        logger.info(f"生成批量摘要: {total} 篇文章，{high_priority} 篇高优先级")
        return summary


class SmartMonitor:
    """智能监控主类"""

    def __init__(self, data_dir: str = None, config_file: str = None):
        if data_dir is None:
            data_dir = os.path.expanduser('~/.wechat-scraper')

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.config = self._load_config(config_file)

        # 初始化各个引擎
        self.dedup_engine = DeduplicationEngine(
            self.data_dir,
            self.config.similarity_threshold
        )
        self.priority_engine = PriorityEngine(self.config)
        self.rate_limiter = RateLimiter(self.data_dir, self.config.rate_limit)
        self.batcher = SmartBatcher(
            self.data_dir,
            self.config.batch_interval_minutes
        )

        # 初始化通知器
        from scripts.notifier import NotificationManager, NotificationMessage
        self.notification_manager = NotificationManager(
            str(self.data_dir / 'notifications.json')
        )
        self.NotificationMessage = NotificationMessage

    def _load_config(self, config_file: Optional[str]) -> SmartMonitorConfig:
        """加载配置"""
        if config_file is None:
            config_file = self.data_dir / 'smart_monitor_config.json'
        else:
            config_file = Path(config_file)

        if config_file.exists():
            try:
                data = json.loads(config_file.read_text(encoding='utf-8'))
                # 解析嵌套对象
                if 'quiet_hours' in data:
                    data['quiet_hours'] = QuietHours(**data['quiet_hours'])
                if 'rate_limit' in data:
                    data['rate_limit'] = RateLimit(**data['rate_limit'])
                if 'high_priority_keywords' in data:
                    data['high_priority_keywords'] = [
                        KeywordRule(**k) for k in data['high_priority_keywords']
                    ]
                return SmartMonitorConfig(**data)
            except Exception as e:
                logger.error(f"加载配置失败: {e}，使用默认配置")

        return SmartMonitorConfig()

    def _save_config(self):
        """保存配置"""
        config_file = self.data_dir / 'smart_monitor_config.json'
        try:
            data = asdict(self.config)
            config_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def process_article(self, article_data: Dict) -> Dict:
        """
        处理单篇文章

        Returns:
            处理结果信息
        """
        # 1. 创建 SmartArticle
        article = SmartArticle(
            url=article_data.get('url', ''),
            title=article_data.get('title', ''),
            account_name=article_data.get('account_name', ''),
            content=article_data.get('content', ''),
            abstract=article_data.get('abstract', ''),
            publish_time=article_data.get('publish_time', ''),
            metrics=WCIMetrics(
                read_count=article_data.get('read_count', 0),
                like_count=article_data.get('like_count', 0),
                comment_count=article_data.get('comment_count', 0),
                share_count=article_data.get('share_count', 0),
                watch_count=article_data.get('watch_count', 0)
            )
        )

        # 2. 去重检查
        if self.config.dedup_enabled:
            is_dup, sim = self.dedup_engine.is_duplicate(article)
            if is_dup:
                return {
                    'status': 'duplicate',
                    'article': article.title,
                    'similarity': sim
                }

        # 3. 计算优先级
        priority, reasons, score = self.priority_engine.calculate_priority(article)
        article.priority = priority.value

        # 4. 添加指纹
        self.dedup_engine.add_fingerprint(article)

        # 5. 检查静默时段和速率限制
        is_quiet = self.config.quiet_hours.is_quiet_time()
        can_notify, rate_reason = self.rate_limiter.can_notify(article)

        # 6. 决策：实时推送 vs 批处理 vs 跳过
        result = {
            'status': 'pending',
            'article': article.title,
            'priority': priority.value,
            'wci': article.wci_score,
            'reasons': reasons,
            'is_quiet_time': is_quiet,
            'can_notify': can_notify,
            'rate_limit_reason': rate_reason
        }

        # 高优先级 + 非静默时段 + 通过速率限制 = 实时推送
        if priority == Priority.HIGH and not is_quiet and can_notify:
            self._send_realtime_notification(article)
            self.rate_limiter.record_notification(article, priority)
            result['status'] = 'notified_realtime'
            result['channels'] = len(self.notification_manager.list_channels())

        # 普通优先级或静默时段 = 加入批处理
        elif priority in [Priority.NORMAL, Priority.LOW] or (priority == Priority.HIGH and is_quiet):
            self.batcher.add_to_batch(article)
            result['status'] = 'batched'

        # 速率限制 = 跳过
        elif not can_notify:
            result['status'] = 'rate_limited'

        return result

    def _send_realtime_notification(self, article: SmartArticle):
        """发送实时通知"""
        message = self.NotificationMessage(
            title=f"【{article.account_name}】{article.title}",
            content=article.abstract or article.content[:500],
            url=article.url,
            author=article.account_name,
            publish_time=article.publish_time,
            priority=article.priority
        )

        # 发送到所有启用的渠道
        sent = 0
        for channel in self.notification_manager.list_channels():
            if channel.get('enabled', True):
                if self.notification_manager.notifier.send(
                    channel['type'],
                    channel['url'],
                    message,
                    **channel.get('options', {})
                ):
                    sent += 1

        logger.info(f"实时通知已发送: {article.title} ({sent} 渠道)")

    def check_and_flush_batch(self) -> Optional[Dict]:
        """检查并发送批量摘要"""
        if not self.batcher.should_flush():
            return None

        summary = self.batcher.flush_batch()
        if not summary:
            return None

        # 生成批量通知消息
        title = f"📰 公众号文章摘要 ({summary['total_articles']} 篇)"

        content_lines = [
            f"共 {summary['total_articles']} 篇新文章",
            f"高优先级: {summary['high_priority_count']} 篇",
            f"涉及账号: {', '.join(summary['accounts'][:5])}",
            "",
            "最新文章:"
        ]

        for i, article in enumerate(summary['articles'][:5], 1):
            priority_emoji = "🔥" if article['priority'] == 'high' else "•"
            content_lines.append(f"{priority_emoji} [{article['account']}] {article['title'][:30]}...")

        message = self.NotificationMessage(
            title=title,
            content='\n'.join(content_lines),
            url="https://mp.weixin.qq.com",
            priority='normal'
        )

        # 发送批量摘要
        sent = 0
        for channel in self.notification_manager.list_channels():
            if channel.get('enabled', True):
                if self.notification_manager.notifier.send(
                    channel['type'],
                    channel['url'],
                    message,
                    **channel.get('options', {})
                ):
                    sent += 1

        logger.info(f"批量摘要已发送: {summary['total_articles']} 篇文章 ({sent} 渠道)")

        summary['channels_sent'] = sent
        return summary

    def add_keyword_rule(self, keyword: str, weight: float = 1.0, priority_boost: str = "high"):
        """添加关键词规则"""
        rule = KeywordRule(keyword=keyword, weight=weight, priority_boost=priority_boost)
        self.config.high_priority_keywords.append(rule)
        self._save_config()
        logger.info(f"已添加关键词规则: {keyword}")

    def list_keyword_rules(self) -> List[KeywordRule]:
        """列出关键词规则"""
        return self.config.high_priority_keywords

    def remove_keyword_rule(self, keyword: str):
        """删除关键词规则"""
        self.config.high_priority_keywords = [
            r for r in self.config.high_priority_keywords
            if r.keyword != keyword
        ]
        self._save_config()
        logger.info(f"已删除关键词规则: {keyword}")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'fingerprints_count': len(self.dedup_engine.fingerprints),
            'pending_batch_count': len(self.batcher.pending_articles),
            'keyword_rules_count': len(self.config.high_priority_keywords),
            'config': {
                'dedup_enabled': self.config.dedup_enabled,
                'batch_enabled': self.config.batch_enabled,
                'quiet_hours_enabled': self.config.quiet_hours.enabled,
                'rate_limit_enabled': self.config.rate_limit.enabled
            }
        }


def main():
    parser = argparse.ArgumentParser(
        description='智能监控与告警系统 v2.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 处理单篇文章（测试）
  %(prog)s process --url "https://mp.weixin.qq.com/s/xxx" --title "测试文章" --account "量子位"

  # 添加关键词规则
  %(prog)s keyword-add "AI" --weight 2.0
  %(prog)s keyword-add "融资" --priority normal

  # 列出关键词规则
  %(prog)s keyword-list

  # 检查并发送批量摘要
  %(prog)s flush-batch

  # 查看统计信息
  %(prog)s stats
        """
    )

    parser.add_argument('--data-dir', default=None, help='数据目录')
    parser.add_argument('--config', default=None, help='配置文件路径')

    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # process 命令
    process_parser = subparsers.add_parser('process', help='处理单篇文章')
    process_parser.add_argument('--url', required=True, help='文章 URL')
    process_parser.add_argument('--title', required=True, help='文章标题')
    process_parser.add_argument('--account', required=True, help='公众号名称')
    process_parser.add_argument('--abstract', default='', help='文章摘要')
    process_parser.add_argument('--read-count', type=int, default=0, help='阅读量')
    process_parser.add_argument('--like-count', type=int, default=0, help='点赞量')

    # keyword-add 命令
    keyword_add_parser = subparsers.add_parser('keyword-add', help='添加关键词规则')
    keyword_add_parser.add_argument('keyword', help='关键词')
    keyword_add_parser.add_argument('--weight', type=float, default=1.0, help='权重')
    keyword_add_parser.add_argument('--priority', default='high', choices=['high', 'normal', 'low'])

    # keyword-list 命令
    subparsers.add_parser('keyword-list', help='列出关键词规则')

    # keyword-remove 命令
    keyword_remove_parser = subparsers.add_parser('keyword-remove', help='删除关键词规则')
    keyword_remove_parser.add_argument('keyword', help='关键词')

    # flush-batch 命令
    subparsers.add_parser('flush-batch', help='立即发送批量摘要')

    # stats 命令
    subparsers.add_parser('stats', help='查看统计信息')

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if not args.command:
        parser.print_help()
        sys.exit(1)

    monitor = SmartMonitor(data_dir=args.data_dir, config_file=args.config)

    if args.command == 'process':
        article_data = {
            'url': args.url,
            'title': args.title,
            'account_name': args.account,
            'abstract': args.abstract,
            'read_count': args.read_count,
            'like_count': args.like_count
        }
        result = monitor.process_article(article_data)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == 'keyword-add':
        monitor.add_keyword_rule(args.keyword, args.weight, args.priority)
        print(f"✓ 已添加关键词规则: {args.keyword}")

    elif args.command == 'keyword-list':
        rules = monitor.list_keyword_rules()
        if not rules:
            print("暂无关键词规则")
        else:
            print(f"共 {len(rules)} 个关键词规则:")
            for r in rules:
                print(f"  • {r.keyword} (权重: {r.weight}, 优先级: {r.priority_boost})")

    elif args.command == 'keyword-remove':
        monitor.remove_keyword_rule(args.keyword)
        print(f"✓ 已删除关键词规则: {args.keyword}")

    elif args.command == 'flush-batch':
        summary = monitor.check_and_flush_batch()
        if summary:
            print(f"✓ 批量摘要已发送: {summary['total_articles']} 篇文章")
            print(f"  发送到 {summary.get('channels_sent', 0)} 个渠道")
        else:
            print("暂无可发送的批量摘要")

    elif args.command == 'stats':
        stats = monitor.get_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
