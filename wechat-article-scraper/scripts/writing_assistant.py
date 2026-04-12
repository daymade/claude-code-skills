#!/usr/bin/env python3
"""
智能写作助手 - AI驱动的内容创作辅助工具

功能：
- AI标题生成器（爆款公式、A/B测试）
- 智能摘要生成（多种风格）
- 文章改写润色（风格转换）
- 文案灵感库
- 关键词提取与优化建议

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict
import random

logger = logging.getLogger('writing-assistant')


@dataclass
class TitleVariant:
    """标题变体"""
    title: str
    formula: str
    appeal_type: str
    predicted_ctr: float
    score: int


@dataclass
class SummaryVariant:
    """摘要变体"""
    text: str
    style: str
    length: int
    key_points_covered: List[str]


@dataclass
class RewriteVariant:
    """改写变体"""
    text: str
    style: str
    tone: str
    readability_score: int
    changes_made: List[str]


@dataclass
class WritingTemplate:
    """写作模板"""
    id: str
    name: str
    category: str
    formula: str
    example: str
    variables: List[str]
    effectiveness_score: float


class TitleGenerator:
    """AI标题生成器"""

    # 爆款标题公式库
    TITLE_FORMULAS = {
        "number": {
            "name": "数字型",
            "templates": [
                "{number}个{topic}，让你{benefit}",
                "{topic}的{number}种方法，第{number2}个太{emotion}了",
                "花了{time}，总结出{number}个{topic}经验",
                "{number}分钟学会{topic}，看完就能上手"
            ],
            "effectiveness": 0.85
        },
        "how_to": {
            "name": "方法型",
            "templates": [
                "如何{topic}？这{number}招让你{benefit}",
                "{topic}的正确姿势，{target}都在用",
                "手把手教你{topic}，从此告别{pain_point}",
                "{topic}全攻略：从入门到精通"
            ],
            "effectiveness": 0.80
        },
        "question": {
            "name": "疑问型",
            "templates": [
                "为什么{target}都在{topic}？",
                "{topic}真的{claim}吗？实测告诉你答案",
                "你的{topic}方法可能错了，{number}%的人都忽略了这点",
                "{topic}到底值不值得？看完这篇不再纠结"
            ],
            "effectiveness": 0.78
        },
        "emotion": {
            "name": "情感型",
            "templates": [
                "太{emotion}了！{topic}竟然可以这么{benefit}",
                "{topic}的那一刻，我{emotion}了",
                "千万别{topic}，除非你想{benefit}",
                "{topic}的{aspect}，看完让人{emotion}"
            ],
            "effectiveness": 0.82
        },
        "contrast": {
            "name": "对比型",
            "templates": [
                "{topic1} vs {topic2}：差距在哪里？",
                "同样是{topic}，为什么别人{result1}而你{result2}？",
                "从{before}到{after}，我只用了{time}",
                "{topic}的{A面}和{B面}，你知道多少？"
            ],
            "effectiveness": 0.75
        },
        "authority": {
            "name": "权威型",
            "templates": [
                "{expert}力荐：{topic}的{number}个秘诀",
                "{company}内部流传的{topic}方法",
                "研究了{number}个案例，我发现{topic}的规律",
                "{industry}大佬都在用的{topic}技巧"
            ],
            "effectiveness": 0.77
        },
        "urgency": {
            "name": "紧迫型",
            "templates": [
                "{topic} deadline 快到了，你还不知道这些？",
                "最后{number}天！{topic}的{benefit}机会",
                "{topic}新规出台，{target}必须了解",
                "错过再等{time}！{topic}全解析"
            ],
            "effectiveness": 0.73
        },
        "curiosity": {
            "name": "好奇型",
            "templates": [
                "关于{topic}，{number}个你不知道的秘密",
                "{topic}背后的真相，第{number}个让人{emotion}",
                "揭秘{topic}：{aspect}比你想象的更{adjective}",
                "为什么{topic}这么火？原来是因为这个"
            ],
            "effectiveness": 0.79
        }
    }

    # 情感词库
    EMOTION_WORDS = {
        "positive": ["惊喜", "感动", "震撼", "温暖", "治愈", "激动", "赞叹", "佩服"],
        "negative": ["震惊", "愤怒", "遗憾", "心酸", "扎心", "泪目", "痛心"],
        "intensity": ["绝了", "封神", "炸裂", "逆天", "极致", "完美", "无敌"]
    }

    def __init__(self):
        self.formulas = self.TITLE_FORMULAS

    def extract_keywords(self, content: str) -> Dict[str, Any]:
        """从内容提取关键词"""
        # 提取主题词（简化实现）
        words = re.findall(r'[\u4e00-\u9fa5]{2,6}', content)
        word_freq = defaultdict(int)
        for w in words:
            word_freq[w] += 1

        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]

        # 提取关键信息
        numbers = re.findall(r'\d+', content)
        has_question = '?' in content or '？' in content or '如何' in content or '为什么' in content

        return {
            "topic": top_words[0][0] if top_words else "",
            "keywords": [w for w, _ in top_words[:5]],
            "numbers": numbers,
            "has_question": has_question,
            "content_type": self._classify_content(content)
        }

    def _classify_content(self, content: str) -> str:
        """分类内容类型"""
        if any(w in content for w in ["教程", "步骤", "方法", "如何"]):
            return "tutorial"
        elif any(w in content for w in ["评测", "对比", "体验", "测试"]):
            return "review"
        elif any(w in content for w in ["新闻", "报道", "事件", "最新"]):
            return "news"
        elif any(w in content for w in ["观点", "思考", "看法", "解读"]):
            return "opinion"
        return "general"

    def generate_titles(self, content: str, count: int = 5) -> List[TitleVariant]:
        """生成标题变体"""
        keywords = self.extract_keywords(content)
        titles = []

        # 根据内容类型选择公式
        content_type = keywords["content_type"]
        formula_priority = {
            "tutorial": ["how_to", "number", "step"],
            "review": ["contrast", "authority", "number"],
            "news": ["urgency", "authority", "question"],
            "opinion": ["emotion", "question", "authority"],
            "general": ["number", "curiosity", "emotion", "how_to"]
        }

        priority = formula_priority.get(content_type, ["general"])

        # 为每个公式生成标题
        for formula_key in list(self.formulas.keys())[:count]:
            formula = self.formulas[formula_key]
            template = random.choice(formula["templates"])

            # 填充模板
            title = self._fill_template(template, keywords, formula_key)

            # 预测CTR（简化算法）
            predicted_ctr = formula["effectiveness"] * (0.9 + random.random() * 0.2)

            # 评分
            score = self._score_title(title, keywords)

            titles.append(TitleVariant(
                title=title,
                formula=formula["name"],
                appeal_type=formula_key,
                predicted_ctr=round(predicted_ctr, 2),
                score=score
            ))

        # 按评分排序
        titles.sort(key=lambda x: x.score, reverse=True)
        return titles[:count]

    def _fill_template(self, template: str, keywords: Dict, formula_type: str) -> str:
        """填充标题模板"""
        topic = keywords.get("topic", "这个话题")
        numbers = keywords.get("numbers", [])

        variables = {
            "topic": topic,
            "number": numbers[0] if len(numbers) > 0 else str(random.randint(3, 10)),
            "number2": numbers[1] if len(numbers) > 1 else str(random.randint(1, 5)),
            "benefit": "事半功倍" if formula_type == "how_to" else "受益匪浅",
            "emotion": random.choice(self.EMOTION_WORDS["positive"]),
            "target": "聪明人" if formula_type == "how_to" else "高手",
            "pain_point": "走弯路" if formula_type == "how_to" else "踩坑",
            "time": "3分钟" if formula_type == "urgency" else "1小时",
            "claim": "有效" if formula_type == "question" else "靠谱",
            "topic1": topic,
            "topic2": "传统" + topic,
            "result1": "成功了",
            "result2": "失败了",
            "before": "新手",
            "after": "专家",
            "A面": "好处",
            "B面": "坏处",
            "expert": "专家",
            "company": "大厂",
            "industry": "行业",
            "aspect": "真相",
            "adjective": "复杂"
        }

        try:
            return template.format(**variables)
        except:
            return template.replace("{", "").replace("}", "")

    def _score_title(self, title: str, keywords: Dict) -> int:
        """评分标题质量"""
        score = 50  # 基础分

        # 长度评分 (20-30字最佳)
        title_len = len(title)
        if 15 <= title_len <= 30:
            score += 20
        elif 10 <= title_len < 40:
            score += 10

        # 包含数字加分
        if re.search(r'\d', title):
            score += 10

        # 包含情感词加分
        for word in self.EMOTION_WORDS["positive"] + self.EMOTION_WORDS["intensity"]:
            if word in title:
                score += 5
                break

        # 包含关键词加分
        topic = keywords.get("topic", "")
        if topic and topic in title:
            score += 15

        # 疑问词加分
        if any(w in title for w in ["?", "？", "如何", "为什么", "吗", "呢"]):
            score += 8

        return min(100, score)

    def ab_test_titles(self, titles: List[str]) -> Dict[str, Any]:
        """A/B测试分析"""
        if len(titles) < 2:
            return {"error": "需要至少2个标题进行A/B测试"}

        analysis = {
            "variants": [],
            "recommendation": "",
            "test_suggestions": []
        }

        for i, title in enumerate(titles, 1):
            metrics = self._analyze_title_metrics(title)
            analysis["variants"].append({
                "variant": f"A" if i == 1 else f"B" if i == 2 else f"C{i-2}",
                "title": title,
                "metrics": metrics
            })

        # 推荐最佳标题
        best = max(analysis["variants"], key=lambda x: x["metrics"]["overall_score"])
        analysis["recommendation"] = f"推荐使用 {best['variant']} 标题"

        # 测试建议
        analysis["test_suggestions"] = [
            f"建议测试周期: 7-14天",
            f"每个标题至少获得 1000 次曝光",
            f"关注CTR(点击率)和阅读完成率",
            f"最佳发布时段: 早上8-9点或晚上8-9点"
        ]

        return analysis

    def _analyze_title_metrics(self, title: str) -> Dict[str, Any]:
        """分析标题指标"""
        return {
            "length": len(title),
            "has_number": bool(re.search(r'\d', title)),
            "has_emotion": any(w in title for w in self.EMOTION_WORDS["positive"]),
            "is_question": any(w in title for w in ["?", "？", "如何", "为什么"]),
            "readability": self._calculate_readability(title),
            "overall_score": self._score_title(title, {"topic": ""})
        }

    def _calculate_readability(self, title: str) -> str:
        """计算可读性"""
        length = len(title)
        if length <= 20:
            return "优秀"
        elif length <= 30:
            return "良好"
        elif length <= 40:
            return "一般"
        return "偏长"


class Summarizer:
    """智能摘要生成器"""

    SUMMARY_STYLES = {
        "news": {
            "name": "新闻式",
            "focus": "关键事实",
            "tone": "客观",
            "template": "本文报道了{main_point}。{key_facts}。{implication}。"
        },
        "marketing": {
            "name": "营销式",
            "focus": "价值主张",
            "tone": " persuasive",
            "template": "想要{benefit}？本文揭示了{main_point}。{key_takeaways}。立即了解详情！"
        },
        "minimal": {
            "name": "极简式",
            "focus": "核心观点",
            "tone": "简洁",
            "template": "{main_point}。{one_key_takeaway}。"
        },
        "story": {
            "name": "故事式",
            "focus": "情节转折",
            "tone": "引人入胜",
            "template": "{setup}，然而{twist}。本文讲述了{main_point}。{resolution}。"
        },
        "bullet": {
            "name": "要点式",
            "focus": "关键信息",
            "tone": "清晰",
            "template": "本文主要内容包括：{bullet_points}"
        }
    }

    def __init__(self):
        self.styles = self.SUMMARY_STYLES

    def generate_summary(self, content: str, style: str = "news",
                        max_length: int = 200) -> SummaryVariant:
        """生成摘要"""
        if style not in self.styles:
            style = "news"

        # 提取关键句
        key_sentences = self._extract_key_sentences(content, 3)

        # 提取关键词
        keywords = self._extract_keywords(content)

        # 生成不同风格的摘要
        if style == "bullet":
            text = self._generate_bullet_summary(key_sentences, keywords)
        elif style == "minimal":
            text = self._generate_minimal_summary(key_sentences)
        else:
            text = self._generate_narrative_summary(key_sentences, keywords, style)

        # 截断到最大长度
        if len(text) > max_length:
            text = text[:max_length-3] + "..."

        return SummaryVariant(
            text=text,
            style=self.styles[style]["name"],
            length=len(text),
            key_points_covered=[s[:30] + "..." for s in key_sentences[:3]]
        )

    def _extract_key_sentences(self, content: str, count: int = 3) -> List[str]:
        """提取关键句"""
        # 按句子分割
        sentences = re.split(r'[。！？\n]', content)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

        if not sentences:
            return [content[:100] + "..."]

        # 简单的关键词密度评分
        scores = []
        all_words = ' '.join(sentences)
        word_freq = defaultdict(int)
        for w in re.findall(r'[\u4e00-\u9fa5]{2,4}', all_words):
            word_freq[w] += 1

        top_words = set(w for w, _ in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20])

        for sent in sentences:
            score = 0
            # 位置权重（开头和结尾）
            if sent == sentences[0]:
                score += 5
            elif sent == sentences[-1]:
                score += 3

            # 关键词密度
            words = re.findall(r'[\u4e00-\u9fa5]{2,4}', sent)
            keyword_matches = sum(1 for w in words if w in top_words)
            score += keyword_matches

            # 特殊标记
            if any(w in sent for w in ["总之", "结论", "因此", "所以", "总结"]):
                score += 3

            scores.append((sent, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scores[:count]]

    def _extract_keywords(self, content: str) -> List[str]:
        """提取关键词"""
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', content)
        word_freq = defaultdict(int)
        for w in words:
            word_freq[w] += 1

        return [w for w, _ in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]]

    def _generate_bullet_summary(self, sentences: List[str],
                                  keywords: List[str]) -> str:
        """生成要点式摘要"""
        bullets = []
        for i, sent in enumerate(sentences[:3], 1):
            bullets.append(f"{i}. {sent[:50]}{'...' if len(sent) > 50 else ''}")
        return "\n".join(bullets)

    def _generate_minimal_summary(self, sentences: List[str]) -> str:
        """生成极简摘要"""
        if sentences:
            return sentences[0][:100] + ("..." if len(sentences[0]) > 100 else "")
        return ""

    def _generate_narrative_summary(self, sentences: List[str],
                                     keywords: List[str], style: str) -> str:
        """生成叙述式摘要"""
        main_point = sentences[0] if sentences else ""
        key_facts = "；".join(sentences[1:3]) if len(sentences) > 1 else ""

        templates = {
            "news": f"本文报道了{main_point[:40]}。{key_facts[:60]}。",
            "marketing": f"{main_point[:50]}。{key_facts[:50]}。",
            "story": f"{main_point[:60]}。{key_facts[:60]}。"
        }

        return templates.get(style, main_point[:150])


class ContentRewriter:
    """内容改写器"""

    STYLE_PRESETS = {
        "professional": {
            "name": "专业正式",
            "tone": "严谨、客观、权威",
            "word_substitutions": {
                "好": "优质",
                "坏": "不佳",
                "很多": "大量",
                "东西": "事物",
                "我觉得": "研究表明"
            }
        },
        "casual": {
            "name": "轻松随意",
            "tone": "亲切、自然、口语化",
            "word_substitutions": {
                "因此": "所以",
                "然而": "不过",
                "非常": "特别",
                "进行": "做",
                "实施": "搞"
            }
        },
        "marketing": {
            "name": "营销 persuasive",
            "tone": "有说服力、激发兴趣",
            "word_substitutions": {
                "有": "拥有",
                "可以": "能够",
                "好": "卓越",
                "便宜": "超值"
            }
        },
        "story": {
            "name": "故事 narrative",
            "tone": "引人入胜、情感丰富",
            "word_substitutions": {
                "然后": "接下来",
                "最后": "最终",
                "说": "说道"
            }
        },
        "academic": {
            "name": "学术严谨",
            "tone": "客观、精确、引用",
            "word_substitutions": {
                "可能": "或许",
                "大概": "约",
                "很多": "诸多"
            }
        }
    }

    def __init__(self):
        self.styles = self.STYLE_PRESETS

    def rewrite(self, content: str, target_style: str,
                tone_adjustment: str = "neutral") -> RewriteVariant:
        """改写内容"""
        if target_style not in self.styles:
            target_style = "professional"

        style_config = self.styles[target_style]

        # 执行改写
        rewritten = self._apply_style(content, style_config)

        # 应用语气调整
        if tone_adjustment != "neutral":
            rewritten = self._adjust_tone(rewritten, tone_adjustment)

        # 计算可读性
        readability = self._calculate_readability_score(rewritten)

        # 记录改动
        changes = [
            f"转换为{style_config['name']}风格",
            f"应用{tone_adjustment}语气",
            f"优化可读性"
        ]

        return RewriteVariant(
            text=rewritten,
            style=style_config["name"],
            tone=tone_adjustment,
            readability_score=readability,
            changes_made=changes
        )

    def _apply_style(self, content: str, style_config: Dict) -> str:
        """应用风格"""
        result = content

        # 词替换
        for old, new in style_config.get("word_substitutions", {}).items():
            result = result.replace(old, new)

        # 句子长度调整
        if style_config["name"] == "专业正式":
            # 增加句子长度
            result = self._lengthen_sentences(result)
        elif style_config["name"] == "轻松随意":
            # 缩短句子
            result = self._shorten_sentences(result)

        return result

    def _lengthen_sentences(self, text: str) -> str:
        """增长句子"""
        # 简单实现：合并短句
        sentences = re.split(r'([。！？])', text)
        result = []
        i = 0
        while i < len(sentences) - 1:
            if i + 2 < len(sentences) and len(sentences[i]) < 20:
                result.append(sentences[i] + sentences[i+2])
                i += 3
            else:
                result.append(sentences[i])
                i += 1
        return ''.join(result)

    def _shorten_sentences(self, text: str) -> str:
        """缩短句子"""
        # 替换连接词为句号
        replacements = ["，因此", "，然而", "，但是", "，所以"]
        for r in replacements:
            text = text.replace(r, "。" + r[1:])
        return text

    def _adjust_tone(self, text: str, tone: str) -> str:
        """调整语气"""
        if tone == "formal":
            # 更正式
            text = text.replace("你", "您")
        elif tone == "friendly":
            # 更友好
            text = text.replace("您", "你")
            text = text.replace("我们", "咱们")
        elif tone == "urgent":
            # 更紧迫
            text = "【重要】" + text

        return text

    def _calculate_readability_score(self, text: str) -> int:
        """计算可读性分数"""
        # 简单的可读性计算
        sentences = len(re.findall(r'[。！？]', text))
        words = len(re.findall(r'[\u4e00-\u9fa5]', text))

        if sentences == 0:
            return 50

        avg_sentence_length = words / sentences

        # 句子长度适中为佳
        if 10 <= avg_sentence_length <= 20:
            return 80
        elif 5 <= avg_sentence_length < 25:
            return 60
        else:
            return 40


class WritingAssistant:
    """写作助手主类"""

    def __init__(self):
        self.title_generator = TitleGenerator()
        self.summarizer = Summarizer()
        self.rewriter = ContentRewriter()

    def full_analysis(self, content: str) -> Dict[str, Any]:
        """完整内容分析"""
        return {
            "titles": [asdict(t) for t in self.title_generator.generate_titles(content, 5)],
            "summaries": {
                style: asdict(self.summarizer.generate_summary(content, style))
                for style in ["news", "marketing", "minimal"]
            },
            "rewrite_options": {
                style: asdict(self.rewriter.rewrite(content, style))
                for style in ["professional", "casual", "marketing"]
            },
            "content_stats": self._analyze_content_stats(content)
        }

    def _analyze_content_stats(self, content: str) -> Dict[str, Any]:
        """分析内容统计"""
        char_count = len(content)
        word_count = len(re.findall(r'[\u4e00-\u9fa5]', content))
        sentence_count = len(re.findall(r'[。！？]', content))
        paragraph_count = len([p for p in content.split('\n') if p.strip()])

        reading_time = word_count / 300  # 假设300字/分钟

        return {
            "char_count": char_count,
            "word_count": word_count,
            "sentence_count": sentence_count,
            "paragraph_count": paragraph_count,
            "reading_time_minutes": round(reading_time, 1),
            "avg_sentence_length": round(word_count / max(sentence_count, 1), 1)
        }


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='智能写作助手')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 标题生成
    title_parser = subparsers.add_parser('title', help='生成标题')
    title_parser.add_argument('content', help='文章内容或文件路径')
    title_parser.add_argument('-n', '--count', type=int, default=5, help='生成数量')
    title_parser.add_argument('--ab-test', nargs='+', help='A/B测试标题')

    # 摘要生成
    summary_parser = subparsers.add_parser('summary', help='生成摘要')
    summary_parser.add_argument('content', help='文章内容或文件路径')
    summary_parser.add_argument('--style', default='news',
                               choices=['news', 'marketing', 'minimal', 'story', 'bullet'],
                               help='摘要风格')
    summary_parser.add_argument('--length', type=int, default=200, help='最大长度')

    # 改写润色
    rewrite_parser = subparsers.add_parser('rewrite', help='改写内容')
    rewrite_parser.add_argument('content', help='文章内容或文件路径')
    rewrite_parser.add_argument('--style', default='professional',
                               choices=['professional', 'casual', 'marketing', 'story', 'academic'],
                               help='目标风格')
    rewrite_parser.add_argument('--tone', default='neutral',
                               choices=['neutral', 'formal', 'friendly', 'urgent'],
                               help='语气调整')

    # 完整分析
    analyze_parser = subparsers.add_parser('analyze', help='完整分析')
    analyze_parser.add_argument('content', help='文章内容或文件路径')
    analyze_parser.add_argument('--export', help='导出JSON路径')

    args = parser.parse_args()

    # 读取内容
    content = args.content
    if os.path.exists(content):
        with open(content, 'r', encoding='utf-8') as f:
            content = f.read()

    logging.basicConfig(level=logging.INFO)
    assistant = WritingAssistant()

    if args.command == 'title':
        if args.ab_test:
            result = assistant.title_generator.ab_test_titles(args.ab_test)
            print(f"\nA/B测试分析:\n")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            titles = assistant.title_generator.generate_titles(content, args.count)
            print(f"\n生成的标题 ({len(titles)}个):\n")
            for i, t in enumerate(titles, 1):
                print(f"{i}. {t.title}")
                print(f"   公式: {t.formula} | 预测CTR: {t.predicted_ctr:.0%} | 评分: {t.score}")

    elif args.command == 'summary':
        summary = assistant.summarizer.generate_summary(content, args.style, args.length)
        print(f"\n{summary.style}摘要:\n")
        print(summary.text)
        print(f"\n长度: {summary.length}字")

    elif args.command == 'rewrite':
        result = assistant.rewriter.rewrite(content, args.style, args.tone)
        print(f"\n改写结果 ({result.style}, {result.tone}):\n")
        print(result.text)
        print(f"\n可读性评分: {result.readability_score}/100")

    elif args.command == 'analyze':
        result = assistant.full_analysis(content)
        print(f"\n内容分析报告:\n")
        print(f"统计: {result['content_stats']}")
        print(f"\n推荐标题:")
        for t in result['titles'][:3]:
            print(f"  • {t['title']} (评分: {t['score']})")

        if args.export:
            with open(args.export, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n已导出: {args.export}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
