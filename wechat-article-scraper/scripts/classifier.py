#!/usr/bin/env python3
"""
微信公众号文章自动分类模块

功能：
- 基于关键词匹配自动分类
- 支持自定义分类规则
- 基于内容摘要的简易主题分类
- 分类统计报告

作者: Claude Code
版本: 1.0.0
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict, Counter

logger = logging.getLogger('wechat-classifier')


# 内置分类规则（关键词 -> 分类）
DEFAULT_CATEGORIES = {
    '科技': [
        '人工智能', 'AI', '机器学习', '深度学习', '神经网络', '大模型', 'LLM',
        '科技', '互联网', '数字化', '算法', '编程', '代码', '开源',
        '芯片', '半导体', '区块链', 'Web3', '元宇宙', 'VR', 'AR',
        '云计算', '大数据', '物联网', '5G', '6G', '通信技术'
    ],
    '财经': [
        '财经', '金融', '投资', '股票', '基金', '证券', '期货', '理财',
        '经济', '市场', '行情', '汇率', '利率', '通胀', 'GDP',
        '企业', '公司', '财报', '营收', '利润', '融资', 'IPO',
        '银行', '保险', '地产', '房地产', '楼市', '房价'
    ],
    '汽车': [
        '汽车', '电动车', '新能源汽车', 'EV', '特斯拉', '比亚迪', '蔚来',
        '自动驾驶', '智能驾驶', '车联网', '充电桩', '锂电池', '动力电池',
        '造车新势力', '车企', '车型', 'SUV', '轿车', '跑车'
    ],
    '医疗': [
        '医疗', '医药', '健康', '医院', '医生', '疾病', '疫苗',
        '基因', '生物科技', '制药', '医疗器械', '诊断', '治疗',
        '中医', '西医', '养生', '保健', '营养', '心理健康'
    ],
    '教育': [
        '教育', '学习', '学校', '大学', '考试', '高考', '考研',
        '培训', '课程', '在线学习', '知识付费', '技能培训',
        '留学', '出国', '语言学习', '英语', '学术研究'
    ],
    '娱乐': [
        '娱乐', '明星', '电影', '电视剧', '综艺', '音乐', '歌曲',
        '娱乐圈', '八卦', '绯闻', '演唱会', '影评', '剧评',
        '游戏', '电竞', '手游', '网游', '二次元', '动漫'
    ],
    '生活': [
        '生活', '美食', '旅游', '旅行', '穿搭', '时尚', '美妆',
        '家居', '装修', '宠物', '育儿', '情感', '心理',
        '运动', '健身', '瑜伽', '跑步', '户外', '摄影'
    ],
    '职场': [
        '职场', '工作', '面试', '简历', '招聘', '求职', '跳槽',
        '升职加薪', '领导', '同事', '办公室', '职业规划',
        '创业', '副业', '自由职业', '远程办公', '工作效率'
    ],
    '时事': [
        '新闻', '时事', '热点', '社会', '政策', '法规', '政府',
        '国际', '国内', '军事', '外交', '贸易', '关系',
        '疫情', '灾害', '事故', '突发事件', '舆论'
    ],
    '文化': [
        '文化', '历史', '文学', '读书', '书评', '艺术', '展览',
        '博物馆', '传统文化', '国学', '哲学', '思想', '人文',
        '考古', '非遗', '民俗', '节日', '诗词'
    ]
}


@dataclass
class ClassificationResult:
    """分类结果"""
    primary_category: str  # 主要分类
    confidence: float  # 置信度 0-1
    all_scores: Dict[str, float]  # 所有分类得分
    keywords_found: List[str]  # 找到的关键词


class ArticleClassifier:
    """文章分类器"""

    def __init__(self, custom_rules: Optional[Dict[str, List[str]]] = None):
        """
        初始化分类器

        Args:
            custom_rules: 自定义分类规则，格式同 DEFAULT_CATEGORIES
        """
        self.rules = custom_rules or DEFAULT_CATEGORIES
        self._compile_patterns()

    def _compile_patterns(self):
        """预编译正则表达式以提高性能"""
        self.patterns = {}
        for category, keywords in self.rules.items():
            # 为每个关键词创建正则模式
            # 注意：\b 对中文不友好，直接匹配关键词
            self.patterns[category] = [
                re.compile(re.escape(kw), re.IGNORECASE)
                for kw in keywords
            ]

    def classify(self, title: str, content: str = "", abstract: str = "") -> ClassificationResult:
        """
        对文章进行分类

        Args:
            title: 文章标题
            content: 文章内容（可选）
            abstract: 文章摘要（可选，比content短）

        Returns:
            ClassificationResult: 分类结果
        """
        # 合并文本用于分析
        text = f"{title} {abstract} {content[:1000]}"  # 限制内容长度避免过长处理

        # 计算每个分类的得分
        scores = {}
        found_keywords = []

        for category, patterns in self.patterns.items():
            score = 0
            category_keywords = []

            for i, pattern in enumerate(patterns):
                matches = pattern.findall(text)
                if matches:
                    # 标题匹配权重更高
                    if pattern.search(title):
                        score += len(matches) * 3
                    else:
                        score += len(matches)
                    category_keywords.extend(matches)

            if score > 0:
                scores[category] = score
                found_keywords.extend(category_keywords)

        if not scores:
            return ClassificationResult(
                primary_category='其他',
                confidence=0.0,
                all_scores={},
                keywords_found=[]
            )

        # 找出最高分的分类
        max_category = max(scores, key=scores.get)
        max_score = scores[max_category]
        total_score = sum(scores.values())

        # 计算置信度
        confidence = max_score / total_score if total_score > 0 else 0

        # 归一化得分
        normalized_scores = {
            cat: round(score / total_score, 3)
            for cat, score in scores.items()
        }

        return ClassificationResult(
            primary_category=max_category,
            confidence=round(confidence, 3),
            all_scores=normalized_scores,
            keywords_found=list(set(found_keywords))[:20]  # 去重并限制数量
        )

    def batch_classify(self, articles: List[Dict]) -> List[Tuple[Dict, ClassificationResult]]:
        """
        批量分类文章

        Args:
            articles: 文章列表，每个文章是包含 title, content 的字典

        Returns:
            List[Tuple]: (文章, 分类结果) 元组列表
        """
        results = []
        for article in articles:
            result = self.classify(
                title=article.get('title', ''),
                content=article.get('content', ''),
                abstract=article.get('abstract', '')
            )
            results.append((article, result))
        return results


class ClassificationReporter:
    """分类统计报告生成器"""

    def __init__(self):
        self.stats = defaultdict(lambda: {'count': 0, 'articles': []})

    def add(self, article: Dict, category: str):
        """添加文章到统计"""
        self.stats[category]['count'] += 1
        self.stats[category]['articles'].append({
            'title': article.get('title', ''),
            'url': article.get('url', ''),
            'author': article.get('author', '')
        })

    def generate_report(self) -> Dict:
        """生成统计报告"""
        total = sum(s['count'] for s in self.stats.values())

        categories = []
        for cat, data in sorted(self.stats.items(), key=lambda x: x[1]['count'], reverse=True):
            categories.append({
                'category': cat,
                'count': data['count'],
                'percentage': round(data['count'] / total * 100, 2) if total > 0 else 0,
                'articles': data['articles'][:10]  # 只保留前10篇文章示例
            })

        return {
            'total_articles': total,
            'category_count': len(self.stats),
            'categories': categories
        }

    def generate_markdown_report(self) -> str:
        """生成 Markdown 格式报告"""
        report = self.generate_report()

        lines = [
            '# 文章分类统计报告',
            '',
            f'**总文章数**: {report["total_articles"]}',
            f'**分类数量**: {report["category_count"]}',
            '',
            '## 分类分布',
            ''
        ]

        for cat in report['categories']:
            bar = '█' * int(cat['percentage'] / 5)  # 20个字符宽度
            lines.append(f"- **{cat['category']}**: {cat['count']} 篇 ({cat['percentage']}%) {bar}")

        lines.extend(['', '## 各类别文章示例', ''])

        for cat in report['categories'][:5]:  # 只显示前5个分类的详情
            lines.append(f"### {cat['category']} ({cat['count']} 篇)")
            for article in cat['articles'][:5]:
                lines.append(f"- [{article['title']}]({article['url']})")
            lines.append('')

        return '\n'.join(lines)


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description='微信公众号文章自动分类')
    parser.add_argument('--title', required=True, help='文章标题')
    parser.add_argument('--content', default='', help='文章内容')
    parser.add_argument('--abstract', default='', help='文章摘要')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')

    args = parser.parse_args()

    classifier = ArticleClassifier()
    result = classifier.classify(args.title, args.content, args.abstract)

    if args.json:
        print(json.dumps({
            'primary_category': result.primary_category,
            'confidence': result.confidence,
            'all_scores': result.all_scores,
            'keywords_found': result.keywords_found
        }, ensure_ascii=False, indent=2))
    else:
        print(f"主要分类: {result.primary_category}")
        print(f"置信度: {result.confidence}")
        print(f"关键词: {', '.join(result.keywords_found[:10])}")
        print(f"\n各分类得分:")
        for cat, score in sorted(result.all_scores.items(), key=lambda x: x[1], reverse=True):
            print(f"  {cat}: {score}")


if __name__ == '__main__':
    main()
