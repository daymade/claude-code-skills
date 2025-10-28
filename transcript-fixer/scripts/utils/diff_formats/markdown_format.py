#!/usr/bin/env python3
"""
Markdown report generator

SINGLE RESPONSIBILITY: Generate detailed Markdown comparison report
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .change_extractor import extract_changes, generate_change_summary


def generate_markdown_report(
    original_file: str,
    stage1_file: str,
    stage2_file: str,
    original: str,
    stage1: str,
    stage2: str
) -> str:
    """
    Generate comprehensive Markdown comparison report

    Args:
        original_file: Original file path
        stage1_file: Stage 1 file path
        stage2_file: Stage 2 file path
        original: Original text content
        stage1: Stage 1 text content
        stage2: Stage 2 text content

    Returns:
        Formatted Markdown report string
    """
    original_path = Path(original_file)
    stage1_path = Path(stage1_file)
    stage2_path = Path(stage2_file)

    # Extract changes for each stage
    changes_stage1 = extract_changes(original, stage1)
    changes_stage2 = extract_changes(stage1, stage2)
    changes_total = extract_changes(original, stage2)

    # Generate summaries
    summary_stage1 = generate_change_summary(changes_stage1)
    summary_stage2 = generate_change_summary(changes_stage2)
    summary_total = generate_change_summary(changes_total)

    # Build report
    report = f"""# 会议记录修复对比报告

## 文件信息

- **原始文件**: {original_path.name}
- **阶段1修复**: {stage1_path.name}
- **阶段2修复**: {stage2_path.name}
- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 修改统计

| 阶段 | 修改数量 | 说明 |
|------|---------|------|
| 阶段1: 词典修复 | {len(changes_stage1)} | 基于预定义词典的批量替换 |
| 阶段2: AI修复 | {len(changes_stage2)} | GLM-4.6智能纠错 |
| **总计** | **{len(changes_total)}** | **原始→最终版本** |

---

# 阶段1: 词典修复详情

{summary_stage1}

---

# 阶段2: AI智能修复详情

{summary_stage2}

---

# 总体修改详情 (原始→最终)

{summary_total}

---

## 使用说明

1. **查看修改**: 每处修改都包含上下文,便于理解修改原因
2. **人工审核**: 重点审核标记为"替换"的修改
3. **专业术语**: 特别注意公司名、人名、技术术语的修改

## 建议审核重点

- [ ] 专业术语(具身智能、机器人等)
- [ ] 人名和公司名
- [ ] 数字(金额、时间等)
- [ ] 上下文是否通顺
"""

    return report
