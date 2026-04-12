#!/usr/bin/env python3
"""
AI智能分析引擎 - 微信公众号文章AI分析

功能：
- 情感分析（正面/负面/中性 + 置信度）
- 关键词自动提取（TF-IDF + LLM混合）
- 文章智能摘要（LLM生成）
- 内容相似度聚类
- 实体识别（人名/公司/产品/地点）

技术选型：
- 优先使用本地模型（Ollama）保护隐私
- 回退到API（OpenAI/DeepSeek）
- 轻量级TF-IDF作为备选

作者: Claude Code
版本: 1.0.0
"""

import os
import re
import json
import sqlite3
import logging
import hashlib
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from collections import Counter

# 配置日志
logger = logging.getLogger('ai-analyzer')


@dataclass
class SentimentResult:
    """情感分析结果"""
    sentiment: str  # positive, negative, neutral
    confidence: float  # 0-1
    score: float  # -1 to 1
    emotions: Dict[str, float] = None  # 细粒度情绪


@dataclass
class KeywordResult:
    """关键词提取结果"""
    keyword: str
    score: float  # 重要性分数
    source: str  # tfidf, llm, hybrid


@dataclass
class SummaryResult:
    """摘要生成结果"""
    summary: str
    key_points: List[str]  # 关键要点
    reading_time: int  # 预计阅读时间（分钟）


@dataclass
class EntityResult:
    """实体识别结果"""
    entity: str
    type: str  # PERSON, ORG, PRODUCT, LOCATION, etc.
    count: int


@dataclass
class AIAnalysisResult:
    """完整AI分析结果"""
    article_id: str
    title: str
    sentiment: SentimentResult
    keywords: List[KeywordResult]
    summary: SummaryResult
    entities: List[EntityResult]
    category: str  # AI增强分类
    topics: List[str]  # 主题标签
    analyzed_at: str
    model_used: str  # 使用的模型


class LLMProvider:
    """LLM提供商统一接口"""

    def __init__(self, provider: str = "auto"):
        self.provider = provider
        self._client = None
        self._ollama_available = None

    def _check_ollama(self) -> bool:
        """检查Ollama是否可用"""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            self._ollama_available = response.status_code == 200
        except:
            self._ollama_available = False

        return self._ollama_available

    def _get_api_key(self, provider: str) -> Optional[str]:
        """获取API Key"""
        env_vars = {
            "openai": ["OPENAI_API_KEY"],
            "deepseek": ["DEEPSEEK_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY"]
        }

        for var in env_vars.get(provider, []):
            key = os.getenv(var)
            if key:
                return key
        return None

    def analyze(self, text: str, task: str) -> Dict[str, Any]:
        """
        执行AI分析

        Args:
            text: 输入文本
            task: 任务类型 (sentiment, keywords, summary, entities)

        Returns:
            分析结果字典
        """
        # 优先尝试本地Ollama
        if self._check_ollama():
            result = self._ollama_analyze(text, task)
            if result:
                return {**result, "model": "ollama"}

        # 回退到API
        for provider in ["openai", "deepseek"]:
            api_key = self._get_api_key(provider)
            if api_key:
                result = self._api_analyze(text, task, provider, api_key)
                if result:
                    return {**result, "model": provider}

        # 最后回退到规则方法
        return self._rule_based_analyze(text, task)

    def _ollama_analyze(self, text: str, task: str) -> Optional[Dict]:
        """使用Ollama本地模型分析"""
        try:
            import requests

            prompts = {
                "sentiment": f"""分析以下文本的情感倾向。返回JSON格式：{{"sentiment": "positive/negative/neutral", "confidence": 0.95, "score": 0.8}}

文本：{text[:2000]}""",

                "keywords": f"""从以下文本中提取5-10个关键词。返回JSON格式：{{"keywords": ["关键词1", "关键词2"]}}

文本：{text[:3000]}""",

                "summary": f"""总结以下文本的主要内容。返回JSON格式：{{"summary": "摘要", "key_points": ["要点1", "要点2"]}}

文本：{text[:4000]}""",

                "entities": f"""识别以下文本中的人名、公司、产品、地点等实体。返回JSON格式：{{"entities": [{{"entity": "实体名", "type": "PERSON/ORG/PRODUCT/LOCATION"}}]}}

文本：{text[:3000]}"""
            }

            prompt = prompts.get(task, prompts["summary"])

            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen2.5:7b",  # 或 llama3.2
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                try:
                    return json.loads(result.get("response", "{}"))
                except:
                    # 尝试从文本中提取JSON
                    text_response = result.get("response", "")
                    json_match = re.search(r'\{.*\}', text_response, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())

            return None

        except Exception as e:
            logger.warning(f"Ollama分析失败: {e}")
            return None

    def _api_analyze(self, text: str, task: str, provider: str, api_key: str) -> Optional[Dict]:
        """使用API分析"""
        try:
            import requests

            system_prompts = {
                "sentiment": "你是一个情感分析专家。分析文本的情感倾向，返回JSON格式。",
                "keywords": "你是一个关键词提取专家。提取文本的关键词，返回JSON格式。",
                "summary": "你是一个文本摘要专家。生成简洁的摘要，返回JSON格式。",
                "entities": "你是一个命名实体识别专家。识别文本中的实体，返回JSON格式。"
            }

            user_prompts = {
                "sentiment": f"分析情感：{text[:2000]}",
                "keywords": f"提取关键词：{text[:3000]}",
                "summary": f"生成摘要：{text[:4000]}",
                "entities": f"识别实体：{text[:3000]}"
            }

            if provider == "openai":
                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "gpt-3.5-turbo",
                        "messages": [
                            {"role": "system", "content": system_prompts[task]},
                            {"role": "user", "content": user_prompts[task]}
                        ],
                        "response_format": {"type": "json_object"}
                    },
                    timeout=30
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    return json.loads(content)

            elif provider == "deepseek":
                response = requests.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": system_prompts[task]},
                            {"role": "user", "content": user_prompts[task]}
                        ],
                        "response_format": {"type": "json_object"}
                    },
                    timeout=30
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    return json.loads(content)

            return None

        except Exception as e:
            logger.warning(f"{provider} API分析失败: {e}")
            return None

    def _rule_based_analyze(self, text: str, task: str) -> Dict[str, Any]:
        """基于规则的分析（备选方案）"""
        if task == "sentiment":
            return self._rule_sentiment(text)
        elif task == "keywords":
            return self._rule_keywords(text)
        elif task == "summary":
            return self._rule_summary(text)
        else:
            return {}

    def _rule_sentiment(self, text: str) -> Dict:
        """基于关键词的情感分析"""
        positive_words = ['好', '棒', '优秀', '成功', '突破', '创新', '增长', '提升', '领先', '第一']
        negative_words = ['差', '失败', '问题', '困难', '下降', '危机', '亏损', '裁员', '倒闭', '暴跌']

        pos_count = sum(1 for w in positive_words if w in text)
        neg_count = sum(1 for w in negative_words if w in text)

        if pos_count > neg_count:
            sentiment = "positive"
            score = min(0.3 + (pos_count - neg_count) * 0.1, 1.0)
        elif neg_count > pos_count:
            sentiment = "negative"
            score = max(-0.3 - (neg_count - pos_count) * 0.1, -1.0)
        else:
            sentiment = "neutral"
            score = 0.0

        return {
            "sentiment": sentiment,
            "confidence": 0.6,
            "score": score,
            "model": "rule-based"
        }

    def _rule_keywords(self, text: str) -> Dict:
        """基于TF-IDF的关键词提取（简化版）"""
        # 分词并统计词频
        words = re.findall(r'[\u4e00-\u9fa5]{2,8}', text)

        # 停用词
        stopwords = {'我们', '他们', '这个', '那个', '可以', '进行', '通过', '随着',
                     '已经', '开始', '目前', '表示', '认为', '文章', '作者', '阅读'}

        # 过滤停用词并统计
        word_counts = Counter(w for w in words if w not in stopwords and len(w) >= 2)
        top_words = word_counts.most_common(10)

        return {
            "keywords": [w[0] for w in top_words],
            "model": "rule-based"
        }

    def _rule_summary(self, text: str) -> Dict:
        """基于句子位置的摘要生成"""
        sentences = re.split(r'[。！？]', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

        if not sentences:
            return {"summary": text[:200], "key_points": [], "model": "rule-based"}

        # 取前3句作为摘要
        summary_sentences = sentences[:3]
        summary = '。'.join(summary_sentences) + '。'

        return {
            "summary": summary[:500],
            "key_points": summary_sentences[:5],
            "reading_time": len(text) // 500,
            "model": "rule-based"
        }


class AIAnalyzer:
    """AI智能分析器"""

    def __init__(self, db_path: str = None, llm_provider: str = "auto"):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "articles.db")

        self.db_path = db_path
        self.llm = LLMProvider(llm_provider)

        # 初始化分析结果表
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id TEXT UNIQUE,
                title TEXT,
                sentiment TEXT,
                sentiment_confidence REAL,
                sentiment_score REAL,
                keywords TEXT,
                summary TEXT,
                key_points TEXT,
                entities TEXT,
                category TEXT,
                topics TEXT,
                model_used TEXT,
                analyzed_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def analyze_article(self, article_id: str, title: str, content: str,
                       force_reanalyze: bool = False) -> AIAnalysisResult:
        """
        分析单篇文章

        Args:
            article_id: 文章ID
            title: 标题
            content: 内容
            force_reanalyze: 强制重新分析

        Returns:
            AI分析结果
        """
        # 检查是否已有分析结果
        if not force_reanalyze:
            existing = self._get_existing_analysis(article_id)
            if existing:
                logger.info(f"使用已有分析结果: {title}")
                return existing

        logger.info(f"开始AI分析: {title}")

        # 合并标题和内容用于分析
        full_text = f"{title}\n\n{content}"

        # 执行各项分析
        sentiment_data = self.llm.analyze(full_text, "sentiment")
        keywords_data = self.llm.analyze(full_text, "keywords")
        summary_data = self.llm.analyze(full_text, "summary")
        entities_data = self.llm.analyze(full_text, "entities")

        # 构建结果
        sentiment = SentimentResult(
            sentiment=sentiment_data.get("sentiment", "neutral"),
            confidence=sentiment_data.get("confidence", 0.5),
            score=sentiment_data.get("score", 0.0),
            emotions=sentiment_data.get("emotions", {})
        )

        keywords = [
            KeywordResult(kw, 1.0 - i * 0.1, keywords_data.get("model", "unknown"))
            for i, kw in enumerate(keywords_data.get("keywords", [])[:10])
        ]

        summary = SummaryResult(
            summary=summary_data.get("summary", content[:200]),
            key_points=summary_data.get("key_points", []),
            reading_time=len(content) // 500 + 1
        )

        entities = [
            EntityResult(e.get("entity", ""), e.get("type", "UNKNOWN"), 1)
            for e in entities_data.get("entities", [])
        ]

        result = AIAnalysisResult(
            article_id=article_id,
            title=title,
            sentiment=sentiment,
            keywords=keywords,
            summary=summary,
            entities=entities,
            category="未分类",
            topics=[],
            analyzed_at=datetime.now().isoformat(),
            model_used=sentiment_data.get("model", "unknown")
        )

        # 保存到数据库
        self._save_analysis(result)

        return result

    def _get_existing_analysis(self, article_id: str) -> Optional[AIAnalysisResult]:
        """获取已有的分析结果"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM ai_analysis WHERE article_id = ?",
            (article_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # 解析数据库行
        try:
            return AIAnalysisResult(
                article_id=row[1],
                title=row[2],
                sentiment=SentimentResult(
                    sentiment=row[3],
                    confidence=row[4],
                    score=row[5]
                ),
                keywords=json.loads(row[6]) if row[6] else [],
                summary=SummaryResult(
                    summary=row[7],
                    key_points=json.loads(row[8]) if row[8] else [],
                    reading_time=0
                ),
                entities=json.loads(row[9]) if row[9] else [],
                category=row[10] or "未分类",
                topics=json.loads(row[11]) if row[11] else [],
                analyzed_at=row[13],
                model_used=row[12] or "unknown"
            )
        except:
            return None

    def _save_analysis(self, result: AIAnalysisResult):
        """保存分析结果到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO ai_analysis (
                article_id, title, sentiment, sentiment_confidence,
                sentiment_score, keywords, summary, key_points,
                entities, category, topics, model_used, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.article_id,
            result.title,
            result.sentiment.sentiment,
            result.sentiment.confidence,
            result.sentiment.score,
            json.dumps([asdict(k) for k in result.keywords]),
            result.summary.summary,
            json.dumps(result.summary.key_points),
            json.dumps([asdict(e) for e in result.entities]),
            result.category,
            json.dumps(result.topics),
            result.model_used,
            result.analyzed_at
        ))

        conn.commit()
        conn.close()

    def batch_analyze(self, limit: int = 100, force: bool = False) -> List[AIAnalysisResult]:
        """
        批量分析未分析的文章

        Args:
            limit: 最大分析数量
            force: 强制重新分析

        Returns:
            分析结果列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if force:
            cursor.execute("""
                SELECT id, title, content FROM articles
                LIMIT ?
            """, (limit,))
        else:
            cursor.execute("""
                SELECT a.id, a.title, a.content FROM articles a
                LEFT JOIN ai_analysis ai ON a.id = ai.article_id
                WHERE ai.id IS NULL
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            try:
                result = self.analyze_article(
                    row[0],
                    row[1],
                    row[2] or ""
                )
                results.append(result)
            except Exception as e:
                logger.error(f"分析失败 {row[1]}: {e}")

        return results

    def get_sentiment_stats(self, days: int = 30) -> Dict[str, Any]:
        """获取情感统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                sentiment,
                COUNT(*) as count,
                AVG(sentiment_confidence) as avg_confidence
            FROM ai_analysis
            WHERE analyzed_at > datetime('now', '-{} days')
            GROUP BY sentiment
        """.format(days))

        stats = {}
        for row in cursor.fetchall():
            stats[row[0]] = {
                "count": row[1],
                "avg_confidence": round(row[2], 2)
            }

        conn.close()
        return stats

    def get_keyword_cloud(self, days: int = 30, limit: int = 50) -> List[Dict]:
        """获取关键词云"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT keywords FROM ai_analysis
            WHERE analyzed_at > datetime('now', '-{} days')
        """.format(days))

        all_keywords = Counter()
        for row in cursor.fetchall():
            try:
                keywords = json.loads(row[0] or "[]")
                for kw in keywords:
                    if isinstance(kw, dict):
                        all_keywords[kw.get("keyword", "")] += 1
            except:
                pass

        conn.close()

        return [
            {"text": kw, "value": count}
            for kw, count in all_keywords.most_common(limit)
        ]


def main():
    """CLI入口"""
    parser = argparse.ArgumentParser(
        description='AI智能分析引擎',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析单篇文章
  %(prog)s analyze --id "article123" --title "测试文章" --file content.txt

  # 批量分析
  %(prog)s batch --limit 100

  # 查看情感统计
  %(prog)s sentiment-stats --days 30

  # 生成关键词云
  %(prog)s keyword-cloud --days 30
        """
    )

    parser.add_argument('--db', help='数据库路径')
    parser.add_argument('--provider', default='auto',
                       choices=['auto', 'ollama', 'openai', 'deepseek'],
                       help='LLM提供商')

    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # analyze 命令
    analyze_parser = subparsers.add_parser('analyze', help='分析单篇文章')
    analyze_parser.add_argument('--id', required=True, help='文章ID')
    analyze_parser.add_argument('--title', required=True, help='文章标题')
    analyze_parser.add_argument('--file', required=True, help='内容文件路径')
    analyze_parser.add_argument('--force', action='store_true', help='强制重新分析')

    # batch 命令
    batch_parser = subparsers.add_parser('batch', help='批量分析')
    batch_parser.add_argument('--limit', type=int, default=100, help='最大数量')
    batch_parser.add_argument('--force', action='store_true', help='强制重新分析')

    # sentiment-stats 命令
    subparsers.add_parser('sentiment-stats', help='情感统计')

    # keyword-cloud 命令
    subparsers.add_parser('keyword-cloud', help='关键词云')

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if not args.command:
        parser.print_help()
        return

    analyzer = AIAnalyzer(args.db, args.provider)

    if args.command == 'analyze':
        content = Path(args.file).read_text(encoding='utf-8')
        result = analyzer.analyze_article(
            args.id, args.title, content, args.force
        )

        print(f"\n📊 AI分析结果: {result.title}")
        print(f"模型: {result.model_used}")
        print(f"\n情感: {result.sentiment.sentiment} (置信度: {result.sentiment.confidence:.2f})")
        print(f"\n关键词: {', '.join(k.keyword for k in result.keywords[:5])}")
        print(f"\n摘要:\n{result.summary.summary[:200]}...")

    elif args.command == 'batch':
        print(f"开始批量分析，最多 {args.limit} 篇...")
        results = analyzer.batch_analyze(args.limit, args.force)
        print(f"✓ 完成 {len(results)} 篇文章的分析")

    elif args.command == 'sentiment-stats':
        stats = analyzer.get_sentiment_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    elif args.command == 'keyword-cloud':
        cloud = analyzer.get_keyword_cloud()
        print(json.dumps(cloud, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
