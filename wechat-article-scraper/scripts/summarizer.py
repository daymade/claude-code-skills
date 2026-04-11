#!/usr/bin/env python3
"""
AI 智能摘要生成器 - 使用 LLM 生成文章摘要

功能：
- 支持多种 LLM 提供商 (OpenAI, Anthropic, DeepSeek, Qwen)
- 生成中英文摘要
- 提取关键要点
- 生成文章标签
- 支持批量处理
- 与 storage.py 集成

吸取竞品精华：
- jina.ai: 简洁的摘要 API
- OpenAI: 结构化输出

作者: Claude Code
版本: 1.0.0
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('wechat-summarizer')


@dataclass
class SummaryResult:
    """摘要结果"""
    title: str
    summary: str
    key_points: List[str]
    tags: List[str]
    sentiment: str  # positive, neutral, negative
    word_count: int
    reading_time: int  # 分钟
    language: str
    model: str


class AISummarizer:
    """AI 摘要生成器"""

    def __init__(self, provider: str = "auto", api_key: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key
        self.model = None
        self._init_provider()

    def _init_provider(self):
        """初始化 LLM 提供商"""
        if self.provider == "auto":
            # 自动选择第一个可用的
            if os.getenv("ANTHROPIC_API_KEY"):
                self.provider = "anthropic"
            elif os.getenv("OPENAI_API_KEY"):
                self.provider = "openai"
            elif os.getenv("DEEPSEEK_API_KEY"):
                self.provider = "deepseek"
            elif os.getenv("DASHSCOPE_API_KEY"):
                self.provider = "qwen"
            else:
                raise ValueError("未找到任何 LLM API Key，请设置环境变量")

        provider_config = {
            "anthropic": {
                "model": "claude-3-haiku-20240307",
                "base_url": "https://api.anthropic.com/v1",
                "api_key_env": "ANTHROPIC_API_KEY"
            },
            "openai": {
                "model": "gpt-3.5-turbo",
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY"
            },
            "deepseek": {
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1",
                "api_key_env": "DEEPSEEK_API_KEY"
            },
            "qwen": {
                "model": "qwen-turbo",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key_env": "DASHSCOPE_API_KEY"
            }
        }

        if self.provider not in provider_config:
            raise ValueError(f"不支持的提供商: {self.provider}")

        config = provider_config[self.provider]
        self.model = config["model"]
        self.base_url = config["base_url"]
        self.api_key = self.api_key or os.getenv(config["api_key_env"])

        if not self.api_key:
            raise ValueError(f"请设置 {config['api_key_env']} 环境变量")

    def _call_llm(self, prompt: str, max_tokens: int = 1000) -> str:
        """调用 LLM API"""
        import requests

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if self.provider == "anthropic":
            headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = "2023-06-01"
            data = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]
            }
        else:
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.3
            }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()

            if self.provider == "anthropic":
                return result["content"][0]["text"]
            else:
                return result["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"LLM API 调用失败: {e}")
            raise

    def summarize(self, title: str, content: str, language: str = "auto") -> SummaryResult:
        """
        生成文章摘要

        Args:
            title: 文章标题
            content: 文章内容
            language: 输出语言 (zh, en, auto)

        Returns:
            SummaryResult: 摘要结果
        """
        # 截断过长内容
        max_content_length = 8000
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."

        # 构建 prompt
        output_lang = "中文" if language in ("zh", "auto") else "English"

        prompt = f"""请对以下文章生成结构化摘要。

标题: {title}

内容:
{content}

请以 JSON 格式返回，包含以下字段:
{{
    "summary": "文章摘要，3-5句话，{output_lang}",
    "key_points": ["要点1", "要点2", "要点3", "要点4", "要点5"],
    "tags": ["标签1", "标签2", "标签3"],
    "sentiment": "positive|neutral|negative",
    "reading_time": 阅读时间（分钟，数字）
}}

注意：
- summary 必须是 {output_lang}
- key_points 使用 {output_lang}
- tags 使用 {output_lang}，3-5个关键词
- 只返回 JSON，不要其他内容"""

        try:
            response = self._call_llm(prompt, max_tokens=1500)

            # 解析 JSON
            # 清理可能的 markdown 代码块
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            result = json.loads(response)

            return SummaryResult(
                title=title,
                summary=result.get("summary", ""),
                key_points=result.get("key_points", []),
                tags=result.get("tags", []),
                sentiment=result.get("sentiment", "neutral"),
                word_count=len(content),
                reading_time=result.get("reading_time", max(1, len(content) // 600)),
                language=language,
                model=f"{self.provider}/{self.model}"
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            logger.error(f"原始响应: {response}")
            # 返回基本摘要
            return SummaryResult(
                title=title,
                summary=response[:500] if response else "摘要生成失败",
                key_points=[],
                tags=[],
                sentiment="neutral",
                word_count=len(content),
                reading_time=max(1, len(content) // 600),
                language=language,
                model=self.model
            )

    def batch_summarize(
        self,
        articles: List[Dict[str, str]],
        delay: float = 1.0
    ) -> List[SummaryResult]:
        """批量生成摘要"""
        import time

        results = []
        for i, article in enumerate(articles):
            logger.info(f"处理文章 {i+1}/{len(articles)}: {article.get('title', '无标题')}")

            try:
                result = self.summarize(
                    title=article.get("title", ""),
                    content=article.get("content", "")
                )
                results.append(result)

                if i < len(articles) - 1:
                    time.sleep(delay)

            except Exception as e:
                logger.error(f"处理失败: {e}")
                results.append(None)

        return results


def save_summary_to_storage(article_id: int, summary: SummaryResult, db_path: str):
    """保存摘要到数据库"""
    sys.path.insert(0, str(Path(__file__).parent))
    from storage import ArticleStorage

    storage = ArticleStorage(db_path)

    # 更新文章的摘要信息
    conn = storage._get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE articles SET
            summary = ?,
            tags = ?,
            sentiment = ?,
            reading_time = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (
        summary.summary,
        json.dumps(summary.tags, ensure_ascii=False),
        summary.sentiment,
        summary.reading_time,
        article_id
    ))

    conn.commit()
    logger.info(f"摘要已保存到文章 ID {article_id}")


def main():
    parser = argparse.ArgumentParser(description='AI 智能摘要生成器')
    parser.add_argument('--title', help='文章标题')
    parser.add_argument('--content', help='文章内容或文件路径')
    parser.add_argument('--content-file', help='从文件读取内容')
    parser.add_argument('--provider', default='auto', choices=['auto', 'anthropic', 'openai', 'deepseek', 'qwen'])
    parser.add_argument('--language', default='zh', choices=['zh', 'en', 'auto'])
    parser.add_argument('--db', help='SQLite 数据库路径，保存摘要')
    parser.add_argument('--article-id', type=int, help='文章 ID（用于保存到数据库）')
    parser.add_argument('--batch', help='批量处理 JSON 文件')
    parser.add_argument('--delay', type=float, default=1.0, help='批量处理间隔（秒）')
    parser.add_argument('--format', default='text', choices=['text', 'json', 'markdown'])

    args = parser.parse_args()

    if args.batch:
        # 批量模式
        with open(args.batch, 'r', encoding='utf-8') as f:
            articles = json.load(f)

        summarizer = AISummarizer(provider=args.provider)
        results = summarizer.batch_summarize(articles, delay=args.delay)

        output_file = Path(args.batch).with_suffix('.summaries.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump([{
                'title': r.title,
                'summary': r.summary,
                'key_points': r.key_points,
                'tags': r.tags,
                'sentiment': r.sentiment,
                'reading_time': r.reading_time
            } for r in results if r], f, ensure_ascii=False, indent=2)

        print(f"摘要已保存到: {output_file}")

    elif args.content or args.content_file:
        # 单篇模式
        if args.content_file:
            content = Path(args.content_file).read_text(encoding='utf-8')
            title = args.title or Path(args.content_file).stem
        else:
            content = args.content
            title = args.title or "无标题"

        summarizer = AISummarizer(provider=args.provider)
        result = summarizer.summarize(title, content, language=args.language)

        if args.format == 'json':
            print(json.dumps({
                'title': result.title,
                'summary': result.summary,
                'key_points': result.key_points,
                'tags': result.tags,
                'sentiment': result.sentiment,
                'reading_time': result.reading_time,
                'model': result.model
            }, ensure_ascii=False, indent=2))

        elif args.format == 'markdown':
            print(f"# {result.title}\n")
            print(f"## 摘要\n\n{result.summary}\n")
            print(f"## 关键要点\n")
            for point in result.key_points:
                print(f"- {point}")
            print(f"\n## 标签\n\n{', '.join(result.tags)}\n")
            print(f"## 元数据\n")
            print(f"- 情感: {result.sentiment}")
            print(f"- 阅读时间: {result.reading_time} 分钟")
            print(f"- 模型: {result.model}")

        else:
            print(f"\n标题: {result.title}")
            print(f"\n摘要:\n{result.summary}")
            print(f"\n关键要点:")
            for point in result.key_points:
                print(f"  • {point}")
            print(f"\n标签: {', '.join(result.tags)}")
            print(f"情感: {result.sentiment}")
            print(f"阅读时间: {result.reading_time} 分钟")
            print(f"模型: {result.model}")

        # 保存到数据库
        if args.db and args.article_id:
            save_summary_to_storage(args.article_id, result, args.db)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
