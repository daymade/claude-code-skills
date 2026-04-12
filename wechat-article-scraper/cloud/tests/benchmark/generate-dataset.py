#!/usr/bin/env python3
"""
Generate 100-article test dataset for WeChat Scraper Benchmark
Round 93: Core Functionality Validation

Usage:
    python generate-dataset.py > test-dataset-full.json
"""

import json
import random
from datetime import datetime

# Base templates for URL generation
BIZ_IDS = [
    "MzA5NjEyMDUyMA==", "MzI5NjQ1MjIxMA==", "MzI2NDk5NzA0Mw==", "MzU5NjA1MTcyNw==",
    "MzA3MzI4MjgzMw==", "MzAxMjE4MTg2Nw==", "MzI0MjM2MTQyMw==", "MzI1ODIyNjE1NQ==",
    "MzU2NjIzNDA1Nw==", "MzU3NDQ1NDY0MQ==", "MzA0MzI0NTc0Nw==", "MzIwMzQ2MTK4MQ==",
    "MzI1NDMyMjQ3Mw==", "MzUyNjE3MjEwOA==", "MzI4NzY1NDMyMQ==", "MzA5ODc2NTQzMg==",
    "MzM1NDMyMTA5Nw==", "MzI3NjU0MzIxMA==", "MzA0MzIxMDk4Nw==", "MzI5ODc2NTQzMA=="
]

CATEGORIES = ["tech", "business", "lifestyle", "news", "education", "entertainment", "health", "finance"]
COMPLEXITY_LEVELS = ["simple", "medium", "complex"]
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
ACCOUNT_TYPES = ["大V", "企业号", "媒体号", "个人号", "机构号", "小号", "电商号", "设计号"]

FEATURES_MAP = {
    "simple": [["text"], ["text", "images"], ["text", "images", "emoji"]],
    "medium": [["text", "images"], ["text", "images", "tables"], ["text", "video"],
               ["text", "code", "images"], ["text", "audio"]],
    "complex": [["text", "images", "tables", "charts"], ["text", "images", "gallery", "blockquote"],
                ["text", "images", "lazy_load"], ["text", "svg", "animation"],
                ["text", "images", "product_cards"]]
}

TITLES = {
    "tech": [
        "AI技术深度解析", "前端框架对比", "云计算发展趋势", "区块链应用实践",
        "Python编程技巧", "微服务架构设计", "DevOps实践指南", "Kubernetes入门",
        "大模型应用开发", "Rust语言特性"
    ],
    "business": [
        "商业模式分析", "创业公司案例", "市场趋势报告", "品牌营销策略",
        "企业管理经验", "投资逻辑分享", "行业深度调研", "竞品分析报告",
        "增长黑客方法", "用户运营策略"
    ],
    "lifestyle": [
        "旅行攻略分享", "美食探店推荐", "家居装修指南", "穿搭时尚趋势",
        "护肤心得分享", "健身计划制定", "摄影技巧教程", "读书心得分享",
        "极简生活理念", "时间管理方法"
    ],
    "news": [
        "时事热点分析", "政策解读报告", "社会现象观察", "国际局势评论",
        "科技发展动态", "经济数据分析", "文化事件报道", "环境议题讨论",
        "教育改革探讨", "医疗进展分享"
    ],
    "education": [
        "学习方法总结", "考试备考攻略", "语言学习技巧", "专业技能培训",
        "儿童教育理念", "在线教育趋势", "知识管理方法", "思维导图应用",
        "记忆技巧分享", "阅读习惯养成"
    ],
    "entertainment": [
        "电影影评分享", "音乐推荐列表", "综艺热点讨论", "游戏攻略教程",
        "明星动态追踪", "文学作品解读", "艺术作品赏析", "直播行业分析",
        "短视频创作", "动漫文化分享"
    ],
    "health": [
        "健康饮食指南", "运动健身计划", "心理健康维护", "疾病预防知识",
        "中医养生理念", "睡眠质量提升", "慢性病管理", "营养补充建议",
        "体检报告解读", "急救知识普及"
    ],
    "finance": [
        "理财基础知识", "股票投资分析", "基金配置策略", "保险选购指南",
        "房产投资建议", "税收政策解读", "退休规划方案", "消费观念分享",
        "债务管理方法", "财务自由路径"
    ]
}

def generate_article(index: int) -> dict:
    """Generate a single test article entry"""
    category = random.choice(CATEGORIES)
    complexity = random.choice(COMPLEXITY_LEVELS)
    year = random.choice(YEARS)
    account_type = random.choice(ACCOUNT_TYPES)

    # Generate pseudo-random but consistent IDs
    biz_id = BIZ_IDS[index % len(BIZ_IDS)]
    mid = 2247000000 + index * 111111 + random.randint(0, 99999)
    sn = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=6))

    url = f"https://mp.weixin.qq.com/s?__biz={biz_id}&mid={mid}&idx=1&sn={sn}"

    title = random.choice(TITLES[category])
    if complexity == "complex":
        title += " - 深度版"
    elif complexity == "simple":
        title += " - 简读"

    features = random.choice(FEATURES_MAP[complexity])

    # Expected fields based on features
    expected_fields = ["title", "author", "publish_time", "content"]
    if "images" in features:
        expected_fields.append("images")
    if "tables" in features:
        expected_fields.append("tables")
    if "video" in features:
        expected_fields.append("video_url")
    if "audio" in features:
        expected_fields.append("audio_url")
    if complexity == "complex":
        expected_fields.extend(["read_count", "like_count"])

    return {
        "id": f"test-{index+1:03d}",
        "url": url,
        "title": title,
        "category": category,
        "complexity": complexity,
        "year": year,
        "account_type": account_type,
        "features": features,
        "expected_fields": expected_fields
    }

def main():
    random.seed(42)  # Reproducible dataset

    dataset = {
        "metadata": {
            "name": "WeChat Article Scraper Benchmark Dataset v1.0",
            "created_at": datetime.now().isoformat(),
            "total_articles": 100,
            "categories": CATEGORIES,
            "complexity_levels": COMPLEXITY_LEVELS,
            "years": YEARS,
            "note": "This is a synthetic dataset for testing purposes. In production, replace with real accessible URLs."
        },
        "articles": [generate_article(i) for i in range(100)]
    }

    # Add statistics
    complexity_counts = {"simple": 0, "medium": 0, "complex": 0}
    category_counts = {cat: 0 for cat in CATEGORIES}
    year_counts = {year: 0 for year in YEARS}

    for article in dataset["articles"]:
        complexity_counts[article["complexity"]] += 1
        category_counts[article["category"]] += 1
        year_counts[article["year"]] += 1

    dataset["statistics"] = {
        "by_complexity": complexity_counts,
        "by_category": category_counts,
        "by_year": year_counts
    }

    print(json.dumps(dataset, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
