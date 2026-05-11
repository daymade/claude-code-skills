#!/usr/bin/env python3
"""
Common Chinese Words Safety Check

Detects when a correction's from_text is a common Chinese word,
which would cause false positive replacements across transcripts.

This is the core defense against the "仿佛→反复" class of bugs:
valid corrections for one ASR model that corrupt correct text from better models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set


# High-frequency Chinese words that should NEVER be dictionary correction sources.
# These are words that appear correctly in normal Chinese text and replacing them
# would cause widespread collateral damage.
#
# Organized by category for maintainability. Not exhaustive -- the heuristic
# checks below catch additional cases.
#
# IMPORTANT: This list was curated from actual production false positives found
# in a 187-video transcription run (2026-03). Each entry caused real damage.

COMMON_WORDS_2CHAR: Set[str] = {
    # --- Production false positives (confirmed damage, 2026-03 run) ---
    # lifestyle domain
    "仿佛", "正面", "犹豫", "传说", "演技", "无果", "旗号", "应急", "正经",
    # lifestyle/beauty domain
    "保健", "内涵",
    # manufacturing domain
    "仅供", "供气", "出头", "几口",
    # lifestyle - previously disabled then re-confirmed
    "增加", "教育", "大一", "曲线", "分母",
    # various domains - discovered in manual review
    "两本", "初五", "数据", "力竭", "充于",
    # general/manufacturing/education - substring collision sources
    "被看", "天差", "亮亮", "金流",
    # caused substring issues in production
    "看见", "分钟",
    # --- High-frequency general vocabulary ---
    "我们", "他们", "你们", "这个", "那个", "什么", "怎么", "为什么",
    "可以", "因为", "所以", "但是", "虽然", "如果", "已经", "正在",
    "需要", "应该", "可能", "一定", "非常", "比较", "特别", "一般",
    "开始", "结束", "继续", "发展", "问题", "方法", "工作", "时间",
    "学习", "研究", "分析", "讨论", "了解", "知道", "觉得", "认为",
    "希望", "表示", "提出", "建议", "要求", "计划", "设计", "管理",
    "技术", "系统", "数据", "网络", "平台", "产品", "服务", "市场",
    "企业", "公司", "团队", "项目", "客户", "用户", "资源", "成本",
    "效果", "质量", "安全", "标准", "流程", "模式", "策略", "方案",
    "结构", "功能", "接口", "模块", "组件", "测试", "部署", "运维",
    "目标", "任务", "进度", "优化", "调整", "更新", "升级", "维护",
    "配置", "参数", "设置", "选项", "状态", "信息", "内容", "格式",
    "教育", "培训", "实践", "经验", "能力", "水平", "素质", "思维",
    "创新", "合作", "沟通", "交流", "反馈", "评估", "考核", "激励",
    # --- Common verbs and adjectives ---
    "实现", "完成", "处理", "解决", "执行", "操作", "运行", "启动",
    "关闭", "打开", "保存", "删除", "修改", "添加", "移除", "查看",
    "搜索", "过滤", "排序", "导入", "导出", "上传", "下载", "同步",
    "重要", "关键", "核心", "基本", "主要", "次要", "简单", "复杂",
    "明确", "清晰", "具体", "详细", "准确", "完整", "稳定", "灵活",
    # --- Domain terms that look like ASR errors but are valid ---
    "线数", "曲线", "分母", "正面", "旗号", "无果", "演技",
    # --- Common verb+一 patterns (打一个/来一个/做一下 etc.) ---
    # "打一" caused production false positive: "打一个锚" → "答疑个锚" (2026-04)
    "打一", "来一", "做一", "写一", "给一", "拉一", "开一", "看一",
    "跑一", "找一", "选一", "试一", "走一", "问一", "搞一", "聊一",
}

# Common 3+ character words that should also be protected.
# These serve dual purpose:
# 1. Never used as correction sources (same as 2-char words)
# 2. Used by DictionaryProcessor._is_inside_longer_word() to detect
#    when a short correction target is embedded inside a valid longer word
COMMON_WORDS_3PLUS: Set[str] = {
    "自动化", "智能化", "数字化", "信息化", "标准化", "规范化",
    "产线数", "服务器", "数据库", "操作系统", "人工智能", "机器学习",
    "深度学习", "自然语言", "计算机视觉", "强化学习",
    "区块链", "云计算", "大数据", "物联网", "互联网",
    # --- Production collision targets (longer words containing short false positives) ---
    # These must be here so _is_inside_longer_word() can detect them
    "产线数据", "现金流", "资金流", "现金流量", "资金流向",
    "被看见", "被看到", "被看作", "被看成", "被看好",
    "漂漂亮亮", "亮亮堂堂", "明明亮亮",
    "天差地别", "天差地远",
    "被看见", "没看见",
    "出头露面", "出头之日",
    "正月初五", "大年初五",
    "保健品", "保健操", "医疗保健",
    "文化内涵",
    "无果而终",
    # --- Common verb+一+量词 patterns (防止"打一"→X 类误纠) ---
    "打一个", "打一针", "打一下", "打一次", "打一把",
    "来一个", "来一下", "来一次", "来一杯",
    "做一个", "做一下", "做一次",
    "写一个", "写一下", "写一篇",
    "给一个", "看一下", "看一看", "看一遍",
    "跑一下", "跑一遍", "跑一次",
    "试一下", "试一试", "试一次",
    # --- Common Chinese idioms/phrases containing short words ---
    # These are needed to prevent idiom corruption
    "正面临", "正面对",
    "应急响应", "应急预案", "应急处理",
    "仅供参考", "仅供参阅",
}

# Words that commonly contain other words as substrings.
# Key: the short word, Value: common words containing it.
# Used to warn about substring collision risk.
SUBSTRING_COLLISION_MAP: dict[str, list[str]] = {
    "线数": ["产线数据", "曲线数", "线数量"],
    "增加": ["新增加", "增加值"],
    "数据": ["大数据", "数据库", "数据集", "元数据"],
    "服务": ["服务器", "服务端", "微服务", "云服务"],
    "测试": ["单元测试", "集成测试", "压力测试", "测试用例"],
    "模型": ["大模型", "模型训练", "预训练模型"],
    "学习": ["学习率", "深度学习", "机器学习", "强化学习"],
    "正面": ["正面临", "正面对"],
    "应急": ["应急响应", "应急预案", "应急处理"],
    "无果": ["无果而终", "毫无果断"],
    # --- Production substring collision patterns (2026-03 manual review) ---
    # "线数" inside "产线数据" → corrupts to "产线束据"
    # (already covered above)
    # "金流" inside "现金流" → corrupts to "现现金流" (replacement contains match)
    "金流": ["现金流", "资金流", "资金流向", "现金流量"],
    # "被看" inside "被看见" → corrupts to "被砍见"
    "被看": ["被看见", "被看到", "被看作", "被看成", "被看好"],
    # "亮亮" inside "漂漂亮亮" → corrupts to "漂漂亮哥"
    "亮亮": ["漂漂亮亮", "亮亮堂堂", "明明亮亮"],
    # "天差" inside "天差地别" → corrupts idiom to "偏差地别"
    "天差": ["天差地别", "天差地远"],
    # "看见" inside longer phrases → substring collision risk
    "看见": ["被看见", "看见过", "没看见"],
    # "分钟" inside longer phrases → substring collision risk
    "分钟": ["几分钟", "十分钟", "三十分钟", "一分钟"],
    # "出头" common in phrases
    "出头": ["出头露面", "出头之日", "冒出头"],
    # "初五" common in date phrases
    "初五": ["正月初五", "大年初五"],
    # "保健" common in compound words
    "保健": ["保健品", "保健操", "医疗保健"],
    # "内涵" common in compound words
    "内涵": ["内涵段子", "文化内涵"],
    # "打一" common in verb+一+量词 (2026-04 production false positive)
    "打一": ["打一个", "打一针", "打一下", "打一次", "打一把"],
}

ALL_COMMON_WORDS: Set[str] = COMMON_WORDS_2CHAR | COMMON_WORDS_3PLUS


@dataclass
class SafetyWarning:
    """A warning about a potentially dangerous correction rule."""
    level: str          # "error" (should block) or "warning" (should confirm)
    category: str       # "common_word", "short_text", "substring_collision"
    message: str
    suggestion: str     # What to do instead


def check_correction_safety(
    from_text: str,
    to_text: str,
    strict: bool = True,
) -> List[SafetyWarning]:
    """
    Check if a correction rule is safe to add to the dictionary.

    This is the main entry point. Returns a list of warnings/errors.
    Empty list = safe to add.

    Args:
        from_text: The text to be replaced (the "wrong" text)
        to_text: The replacement text (the "correct" text)
        strict: If True, common word matches are errors; if False, warnings

    Returns:
        List of SafetyWarning objects (empty = safe)
    """
    warnings: List[SafetyWarning] = []

    # Check 1: Is from_text a known common word?
    if from_text in ALL_COMMON_WORDS:
        level = "error" if strict else "warning"
        warnings.append(SafetyWarning(
            level=level,
            category="common_word",
            message=(
                f"'{from_text}' is a common Chinese word that appears correctly "
                f"in normal text. Replacing it with '{to_text}' will cause "
                f"false positives across all transcripts."
            ),
            suggestion=(
                f"Use a context rule instead: add a regex pattern that matches "
                f"'{from_text}' only in the specific context where it's an ASR error. "
                f"Example: match '{from_text}' only when preceded/followed by specific characters."
            ),
        ))

    # Check 2: Is from_text very short (<=2 chars)?
    if len(from_text) <= 2:
        # Even if not in our common words list, 2-char Chinese words are risky
        if from_text not in ALL_COMMON_WORDS:
            # Not already flagged above -- add a length warning
            warnings.append(SafetyWarning(
                level="warning",
                category="short_text",
                message=(
                    f"'{from_text}' is only {len(from_text)} character(s). "
                    f"Short corrections have high false positive risk in Chinese "
                    f"because they match as substrings inside longer words."
                ),
                suggestion=(
                    f"Verify '{from_text}' is never a valid word in any context. "
                    f"If unsure, use a context rule with surrounding text patterns instead."
                ),
            ))

    # Check 3: Could from_text match as a substring inside common words?
    # This catches the "线数" matching inside "产线数据" bug.
    if from_text in SUBSTRING_COLLISION_MAP:
        collisions = SUBSTRING_COLLISION_MAP[from_text]
        warnings.append(SafetyWarning(
            level="error" if strict else "warning",
            category="substring_collision",
            message=(
                f"'{from_text}' is a substring of common words: "
                f"{', '.join(collisions)}. "
                f"Replacing '{from_text}' with '{to_text}' will corrupt these words."
            ),
            suggestion=(
                f"Use a context rule with negative lookahead/lookbehind to exclude "
                f"matches inside these common words. Example regex: "
                f"'(?<!产){from_text}(?!据)' to avoid matching inside '产线数据'."
            ),
        ))
    else:
        # Dynamic check: scan our common words for substring matches
        _check_dynamic_substring_collisions(from_text, to_text, warnings)

    # Check 4: Is from_text == to_text except for tone/similar sound?
    # (Catch obvious non-errors like 仿佛→反复 where both are valid words)
    if from_text in ALL_COMMON_WORDS and to_text in ALL_COMMON_WORDS:
        warnings.append(SafetyWarning(
            level="error" if strict else "warning",
            category="both_common",
            message=(
                f"Both '{from_text}' and '{to_text}' are common Chinese words. "
                f"This is almost certainly a false correction -- both forms are "
                f"valid in different contexts."
            ),
            suggestion=(
                f"This rule should NOT be in the dictionary. If '{from_text}' is "
                f"genuinely an ASR error in a specific domain, use a context rule "
                f"tied to that domain's vocabulary."
            ),
        ))

    return warnings


def _check_dynamic_substring_collisions(
    from_text: str,
    to_text: str,
    warnings: List[SafetyWarning],
) -> None:
    """
    Check if from_text appears as a substring in any common word,
    where the common word is NOT the from_text itself.
    """
    if len(from_text) > 4:
        # Long enough that substring collisions are unlikely to be problematic
        return

    collisions: List[str] = []
    for word in ALL_COMMON_WORDS:
        if word == from_text:
            continue
        if from_text in word:
            collisions.append(word)

    if collisions:
        # Only show first 5 to avoid spam
        shown = collisions[:5]
        more = f" (and {len(collisions) - 5} more)" if len(collisions) > 5 else ""
        warnings.append(SafetyWarning(
            level="warning",
            category="substring_collision",
            message=(
                f"'{from_text}' appears inside {len(collisions)} common word(s): "
                f"{', '.join(shown)}{more}. "
                f"This replacement may cause collateral damage."
            ),
            suggestion=(
                f"Review whether '{from_text}→{to_text}' could corrupt any of "
                f"these words. Consider using a context rule instead."
            ),
        ))


def audit_corrections(
    corrections: dict[str, str],
) -> dict[str, List[SafetyWarning]]:
    """
    Audit all corrections in a dictionary for safety issues.

    Used by the --audit command.

    Args:
        corrections: Dict of {from_text: to_text}

    Returns:
        Dict of {from_text: [warnings]} for entries with issues.
        Entries with no issues are not included.
    """
    results: dict[str, List[SafetyWarning]] = {}

    for from_text, to_text in corrections.items():
        warnings = check_correction_safety(from_text, to_text, strict=False)
        if warnings:
            results[from_text] = warnings

    return results
