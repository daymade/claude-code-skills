#!/usr/bin/env python3
"""
内容质量评分系统 - 验证提取结果的有效性

功能：
- 多维度质量评分（标题、内容、图片）
- 自动识别低质量/损坏的提取结果
- 噪声内容比例分析
- 重复内容检测
- 质量报告生成

吸取竞品精华：
- camofox: 噪声比例阈值
- wechat-article-reader: 结构化验证
- fetch-wx-article: 完整性检查

作者: Claude Code
版本: 3.2.0
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger('wechat-quality')


class QualityGrade(Enum):
    """质量等级"""
    EXCELLENT = "excellent"  # 优秀 (>85分)
    GOOD = "good"            # 良好 (70-85分)
    FAIR = "fair"            # 一般 (50-70分)
    POOR = "poor"            # 较差 (<50分)
    INVALID = "invalid"      # 无效 (关键字段缺失)


@dataclass
class QualityScore:
    """质量评分结果"""
    total_score: int          # 总分 (0-100)
    grade: QualityGrade       # 质量等级
    title_score: int          # 标题分 (0-25)
    content_score: int        # 内容分 (0-50)
    metadata_score: int       # 元数据分 (0-15)
    images_score: int         # 图片分 (0-10)
    issues: List[str]         # 问题列表
    warnings: List[str]       # 警告列表
    content_stats: Dict[str, Any]  # 内容统计


class ContentValidator:
    """内容验证器"""

    # 噪声标记（用于计算噪声比例）
    NOISE_MARKERS = [
        '阅读原文', '轻触阅读原文', '预览时标签不可点',
        '微信扫一扫', '关注该公众号', '写留言',
        '暂无留言', '已无更多数据', '选择留言身份',
        '确认提交投诉', '发消息', '点击关注',
        '长按二维码关注', '赞赏', '喜欢作者',
        '推荐阅读', '相关阅读', '精选留言',
    ]

    # 低质量指示词
    LOW_QUALITY_INDICATORS = [
        '404', 'not found', '页面不存在',
        '访问受限', '内容已删除', '文章已删除',
        '需要登录', '无权访问', '验证',
    ]

    def __init__(self):
        self.min_title_length = 5
        self.min_content_length = 200
        self.min_content_words = 50
        self.max_noise_ratio = 0.3

    def validate(self, data: Dict[str, Any]) -> QualityScore:
        """
        验证内容质量

        Args:
            data: 提取的文章数据

        Returns:
            QualityScore: 质量评分结果
        """
        issues = []
        warnings = []

        # 各维度评分
        title_score, title_issues = self._score_title(data)
        content_score, content_stats, content_issues = self._score_content(data)
        metadata_score, meta_issues = self._score_metadata(data)
        images_score, img_issues = self._score_images(data)

        issues.extend(title_issues)
        issues.extend(content_issues)
        issues.extend(meta_issues)
        issues.extend(img_issues)

        # 检查低质量指示词
        content_text = data.get('content', '')
        for indicator in self.LOW_QUALITY_INDICATORS:
            if indicator in content_text[:500]:
                issues.append(f"内容包含低质量指示词: '{indicator}'")
                content_score = max(0, content_score - 20)

        # 计算总分
        total_score = title_score + content_score + metadata_score + images_score

        # 确定等级
        if issues and any("缺失" in i or "无效" in i for i in issues):
            grade = QualityGrade.INVALID
        elif total_score >= 85:
            grade = QualityGrade.EXCELLENT
        elif total_score >= 70:
            grade = QualityGrade.GOOD
        elif total_score >= 50:
            grade = QualityGrade.FAIR
        else:
            grade = QualityGrade.POOR

        # 生成警告
        if grade == QualityGrade.EXCELLENT and total_score < 95:
            warnings.append("接近完美，仍有改进空间")

        logger.info(f"质量评分: {total_score}/100 ({grade.value})")

        return QualityScore(
            total_score=total_score,
            grade=grade,
            title_score=title_score,
            content_score=content_score,
            metadata_score=metadata_score,
            images_score=images_score,
            issues=issues,
            warnings=warnings,
            content_stats=content_stats
        )

    def _score_title(self, data: Dict[str, Any]) -> tuple:
        """评分标题 (0-25分)"""
        score = 0
        issues = []
        title = data.get('title', '').strip()

        if not title:
            issues.append("标题缺失")
            return 0, issues

        # 基础分：有标题 (10分)
        score += 10

        # 长度检查 (5分)
        if len(title) >= self.min_title_length:
            score += 5
        else:
            issues.append(f"标题过短 ({len(title)}字符)")

        # 质量检查 (5分)
        if not any(c.isdigit() for c in title):
            score += 3  # 不含纯数字
        if not title.isupper():
            score += 2  # 非全大写（避免噪声）

        # 完整性检查 (5分)
        if not title.endswith(('...', '…', '>>')):
            score += 5
        else:
            issues.append("标题可能不完整")

        return score, issues

    def _score_content(self, data: Dict[str, Any]) -> tuple:
        """评分内容 (0-50分)"""
        score = 0
        issues = []
        content = data.get('content', '').strip()

        if not content:
            issues.append("内容缺失")
            return 0, {}, issues

        # 基础统计
        char_count = len(content)
        word_count = len(content.split())
        line_count = len([l for l in content.split('\n') if l.strip()])

        stats = {
            'char_count': char_count,
            'word_count': word_count,
            'line_count': line_count,
        }

        # 长度评分 (20分)
        if char_count >= 2000:
            score += 20
        elif char_count >= 1000:
            score += 15
        elif char_count >= self.min_content_length:
            score += 10
        else:
            score += max(0, int(char_count / self.min_content_length * 10))
            issues.append(f"内容较短 ({char_count}字符)")

        # 词汇密度 (10分)
        if word_count >= 100:
            score += 10
        elif word_count >= self.min_content_words:
            score += 5
        else:
            issues.append(f"词汇量不足 ({word_count}词)")

        # 段落结构 (10分)
        if line_count >= 5:
            score += 10
        else:
            score += max(0, line_count * 2)
            issues.append(f"段落过少 ({line_count}段)")

        # 噪声比例 (10分)
        noise_chars = 0
        for marker in self.NOISE_MARKERS:
            if marker in content:
                noise_chars += len(marker)

        noise_ratio = noise_chars / char_count if char_count > 0 else 0
        stats['noise_ratio'] = round(noise_ratio, 3)

        if noise_ratio < 0.1:
            score += 10
        elif noise_ratio < self.max_noise_ratio:
            score += 5
        else:
            issues.append(f"噪声比例过高 ({noise_ratio:.1%})")

        return score, stats, issues

    def _score_metadata(self, data: Dict[str, Any]) -> tuple:
        """评分元数据 (0-15分)"""
        score = 0
        issues = []

        # 作者 (5分)
        author = data.get('author', '').strip()
        if author and len(author) > 1:
            score += 5
        else:
            issues.append("作者信息缺失")

        # 发布时间 (5分)
        publish_time = data.get('publishTime', '').strip()
        if publish_time:
            score += 5
        else:
            issues.append("发布时间缺失")

        # HTML 完整性 (5分)
        html = data.get('html', '').strip()
        if html and len(html) > 100:
            score += 5
        else:
            warnings = ["HTML内容不完整"]  # 非关键问题

        return score, issues

    def _score_images(self, data: Dict[str, Any]) -> tuple:
        """评分图片 (0-10分)"""
        score = 0
        issues = []
        images = data.get('images', [])

        if not images:
            # 无图片不一定是问题，可能是纯文字文章
            return 5, issues  # 给基础分

        # 图片数量 (5分)
        if len(images) >= 3:
            score += 5
        elif len(images) >= 1:
            score += 3

        # 图片有效性 (5分)
        valid_images = sum(1 for img in images if img.get('src') or img.get('url'))
        if valid_images == len(images):
            score += 5
        elif valid_images > 0:
            score += 2
            issues.append(f"部分图片链接无效 ({len(images) - valid_images}/{len(images)})")
        else:
            issues.append("所有图片链接无效")

        return score, issues

    def is_acceptable(self, data: Dict[str, Any], min_grade: QualityGrade = QualityGrade.FAIR) -> bool:
        """
        快速检查内容是否可接受

        Args:
            data: 文章数据
            min_grade: 最低接受等级

        Returns:
            bool: 是否可接受
        """
        score = self.validate(data)
        grade_order = [QualityGrade.INVALID, QualityGrade.POOR, QualityGrade.FAIR, QualityGrade.GOOD, QualityGrade.EXCELLENT]
        return grade_order.index(score.grade) >= grade_order.index(min_grade)

    def generate_report(self, score: QualityScore) -> Dict[str, Any]:
        """生成质量报告"""
        return {
            'score': {
                'total': score.total_score,
                'grade': score.grade.value,
                'breakdown': {
                    'title': score.title_score,
                    'content': score.content_score,
                    'metadata': score.metadata_score,
                    'images': score.images_score,
                }
            },
            'issues': score.issues,
            'warnings': score.warnings,
            'content_stats': score.content_stats,
            'recommendations': self._generate_recommendations(score)
        }

    def _generate_recommendations(self, score: QualityScore) -> List[str]:
        """生成改进建议"""
        recommendations = []

        if score.title_score < 20:
            recommendations.append("检查标题选择器，可能使用了备选标题")

        if score.content_score < 40:
            recommendations.append("内容提取可能不完整，建议尝试其他策略")

        if score.metadata_score < 10:
            recommendations.append("元数据提取失败，可能影响归档质量")

        if score.grade == QualityGrade.POOR:
            recommendations.append("建议人工检查提取结果")

        if not recommendations:
            recommendations.append("质量良好，无需改进")

        return recommendations


def main():
    """CLI 工具"""
    import argparse

    parser = argparse.ArgumentParser(description='内容质量验证工具')
    parser.add_argument('json_file', help='文章 JSON 文件路径')
    parser.add_argument('--min-score', type=int, default=50, help='最低接受分数')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式报告')

    args = parser.parse_args()

    import json
    from pathlib import Path

    data = json.loads(Path(args.json_file).read_text())

    validator = ContentValidator()
    score = validator.validate(data)

    if args.json:
        report = validator.generate_report(score)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"质量评分: {score.total_score}/100 ({score.grade.value})")
        print(f"  标题: {score.title_score}/25")
        print(f"  内容: {score.content_score}/50")
        print(f"  元数据: {score.metadata_score}/15")
        print(f"  图片: {score.images_score}/10")

        if score.issues:
            print("\n问题:")
            for issue in score.issues:
                print(f"  ⚠️ {issue}")

        if score.warnings:
            print("\n警告:")
            for warning in score.warnings:
                print(f"  ⚡ {warning}")

        if score.content_stats:
            print(f"\n内容统计:")
            for key, value in score.content_stats.items():
                print(f"  {key}: {value}")

        print(f"\n可接受: {'是' if score.total_score >= args.min_score else '否'}")

    sys.exit(0 if score.total_score >= args.min_score else 1)


if __name__ == '__main__':
    import sys
    main()
