import json
import os
import re
from datetime import datetime

# Directory containing all search result files
results_dir = r"C:\Users\Administrator\.workbuddy\projects\e-workspaces-2026-06-21-09-43-05\c0145562-e8ef-41f7-a2ad-46d6da460828\tool-results"

all_articles = {}  # media_id -> article info

# Read all files in the directory
for filename in os.listdir(results_dir):
    filepath = os.path.join(results_dir, filename)
    if not os.path.isfile(filepath):
        continue
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        data = json.loads(content)
        knowledge_list = data.get("searched_knowledge_list", [])
        for item in knowledge_list:
            knowledge = item.get("knowledge", {})
            media_id = knowledge.get("media_id", "")
            title = knowledge.get("title", "")
            create_time = knowledge.get("create_time", "0")
            introduction = knowledge.get("introduction", "")
            
            if media_id and media_id not in all_articles:
                all_articles[media_id] = {
                    "media_id": media_id,
                    "title": title,
                    "create_time": int(create_time) if create_time else 0,
                    "introduction": introduction[:500]
                }
    except:
        pass

# Helper: is this a case study (project showcase)?
def is_case_study(title):
    # Starts with area number + has style/showcase keywords = case study
    starts_with_area = bool(re.match(r'^\d+㎡', title) or re.match(r'^\d+平', title) or re.match(r'^\d+m²', title) or re.match(r'^\d+m2', title))
    
    showcase_keywords = ['前后对比', '变身', '完工', '速变', '逆袭', '前后效果', '对比', '惊艳',
                         '风', '日式', '北欧', '现代', '简约', '原木', '清新', '暖居', '轻奢', 
                         '复古', '美式', '混搭', '婚房', '奶油', '法式', '极简', '黑白',
                         '三口之家', '一人住', '独居', '养老房', '民宿', '单身',
                         '打造', '成就', '满足', '三室', '两室', '一室',
                         '翻新', '改造', '新装', '重装', '焕新', '换新颜']
    
    knowledge_keywords = ['怎么', '如何', '为什么', '能不能', '要不要', '需要吗', '避坑', '注意',
                          '肯定', '坑', '省钱', '贵', '费用', '难度', '值得', '顺序', '流程',
                          '经验', '常识', '警告', '血泪', '教训', '要点', '重点', '知识',
                          '绝招', '计费', '验收', '必须', '别', '千万', '一定', '牢记',
                          '策略', '方案', '指南', '清单', '揭秘', '真相']
    
    if starts_with_area:
        # If it starts with area, it's likely a case study
        # But keep if it has strong knowledge keywords
        if any(kw in title for kw in knowledge_keywords):
            return False
        return True
    
    # Check for case study patterns without area prefix
    case_patterns = [
        r'(老房|旧房|二手房).*(逆袭|变身|完工|速变|前后对比|惊艳|换新颜|焕新|新装|重装|翻新)',
        r'(精装|精装房).*(改造|变身|逆袭|对比)',
    ]
    for pattern in case_patterns:
        if re.search(pattern, title):
            # But keep if has knowledge keywords
            if any(kw in title for kw in knowledge_keywords):
                return False
            return True
    
    return False

# Helper: does title have old house keywords?
def has_old_house_kw(title, intro=""):
    text = title + " " + intro
    return any(kw in text for kw in ['老房', '旧房', '二手房', '精装房', '精装修', '老破小', '老破大'])

# Helper: does title have knowledge/educational value?
def has_knowledge_value(title):
    knowledge_keywords = ['怎么', '如何', '为什么', '能不能', '要不要', '需要吗', '避坑', '注意',
                          '肯定', '坑', '省钱', '贵', '费用', '难度', '值得', '顺序', '流程',
                          '经验', '常识', '警告', '血泪', '教训', '要点', '重点', '知识',
                          '绝招', '计费', '验收', '必须', '别', '千万', '一定', '牢记',
                          '策略', '方案', '指南', '清单', '揭秘', '真相', '不建议', '不能',
                          '误', '错', '套路', '隐形', '价格刺客', '艰难', '可怕', '难',
                          '之间', '矛盾', '冲突', '问题']
    return any(kw in title for kw in knowledge_keywords)

# ============================
# STEP 1: Build category-specific article lists
# ============================

categories = {
    "拆除知识类": [],
    "水电改造类": [],
    "费用难度类": [],
    "厨卫翻新类": [],
    "精装房改造类": [],
    "二手房避坑类": [],
    "买房避坑类": []
}

assigned_ids = set()

# --- 拆除知识类 ---
# Include articles about 拆除/砸墙/承重墙/垃圾 that are knowledge-type
for media_id, article in all_articles.items():
    if media_id in assigned_ids:
        continue
    title = article["title"]
    if any(kw in title for kw in ['拆除', '砸墙', '承重墙', '垃圾清运', '垃圾外运', '拆旧', '非承重']):
        if not is_case_study(title):
            # Keep knowledge articles + a few representative case articles with knowledge value
            if has_knowledge_value(title) or any(kw in title for kw in ['旧房', '老房', '二手房', '精装']):
                categories["拆除知识类"].append(article)
                assigned_ids.add(media_id)

# --- 水电改造类 ---
# Include water/electricity articles that are relevant to old house renovation
for media_id, article in all_articles.items():
    if media_id in assigned_ids:
        continue
    title = article["title"]
    intro = article.get("introduction", "")
    
    # Articles with 水电 in title that are knowledge-type
    if any(kw in title for kw in ['水电', '水管', '电路改造', '水路', '线管']):
        if not is_case_study(title) and has_knowledge_value(title):
            categories["水电改造类"].append(article)
            assigned_ids.add(media_id)
    
    # Articles about 水电全换/插座/开关 that relate to old house
    elif any(kw in title for kw in ['插座', '开关', '漏电', '电线']):
        if not is_case_study(title) and (has_knowledge_value(title) or has_old_house_kw(title, intro)):
            # Only include if it has old house context
            if has_old_house_kw(title, intro):
                categories["水电改造类"].append(article)
                assigned_ids.add(media_id)
    
    # Specific old house water/electricity articles
    elif '水电' in title and any(kw in title for kw in ['全换', '没有必要', '省钱', '计费', '验收', '翻车', '不建议', '最难']):
        if not is_case_study(title):
            categories["水电改造类"].append(article)
            assigned_ids.add(media_id)

# --- 精装房改造类 ---
# Only knowledge articles about 精装房/精装修
for media_id, article in all_articles.items():
    if media_id in assigned_ids:
        continue
    title = article["title"]
    if any(kw in title for kw in ['精装房', '精装修', '开发商']):
        if not is_case_study(title):
            # Keep knowledge articles and articles about精装房 pitfalls
            if has_knowledge_value(title) or any(kw in title for kw in ['坑', '艰难', '必须', '需要', '改', '微改', '局部', '阳台', '厨房', '门厅', '吊顶']):
                categories["精装房改造类"].append(article)
                assigned_ids.add(media_id)

# --- 费用难度类 ---
# Old house cost/difficulty articles
for media_id, article in all_articles.items():
    if media_id in assigned_ids:
        continue
    title = article["title"]
    if any(kw in title for kw in ['旧房', '老房']) and any(kw in title for kw in ['省钱', '贵', '费用', '成本', '预算', '难度', '值得', '难']):
        if not is_case_study(title):
            categories["费用难度类"].append(article)
            assigned_ids.add(media_id)
    elif '翻新' in title and any(kw in title for kw in ['省钱', '贵', '费用', '成本']):
        if not is_case_study(title):
            categories["费用难度类"].append(article)
            assigned_ids.add(media_id)
    elif any(kw in title for kw in ['旧房.*贵', '老房.*贵']) and not is_case_study(title):
        categories["费用难度类"].append(article)
        assigned_ids.add(media_id)

# --- 厨卫翻新类 ---
# Old house kitchen/bathroom renovation knowledge
for media_id, article in all_articles.items():
    if media_id in assigned_ids:
        continue
    title = article["title"]
    if any(kw in title for kw in ['老房', '旧房', '二手房']) and any(kw in title for kw in ['厨卫', '厨房', '卫生间', '防水', '马桶', '浴室']):
        if not is_case_study(title):
            categories["厨卫翻新类"].append(article)
            assigned_ids.add(media_id)
    elif '卫生间' in title and any(kw in title for kw in ['翻新', '不砸', '不动', '局部']):
        if not is_case_study(title):
            categories["厨卫翻新类"].append(article)
            assigned_ids.add(media_id)

# --- 买房避坑类 ---
# Articles about buying old houses, 老破小 decision-making (knowledge only)
for media_id, article in all_articles.items():
    if media_id in assigned_ids:
        continue
    title = article["title"]
    # Only knowledge articles about buying decisions
    if any(kw in title for kw in ['老破小', '老破大', '高层.*老破小']):
        if has_knowledge_value(title) and not is_case_study(title):
            categories["买房避坑类"].append(article)
            assigned_ids.add(media_id)
        elif any(kw in title for kw in ['智商税', '毁掉', '避坑指南', '抉择', '感悟', '买']):
            if not is_case_study(title):
                categories["买房避坑类"].append(article)
                assigned_ids.add(media_id)
    elif any(kw in title for kw in ['买房', '选房', '学区房', '购房']) and has_old_house_kw(title, article.get("introduction", "")):
        if not is_case_study(title):
            categories["买房避坑类"].append(article)
            assigned_ids.add(media_id)

# --- 二手房避坑类 ---
# Remaining old house knowledge articles
for media_id, article in all_articles.items():
    if media_id in assigned_ids:
        continue
    title = article["title"]
    intro = article.get("introduction", "")
    
    # Knowledge articles about old house renovation
    if has_old_house_kw(title, intro):
        if not is_case_study(title) and has_knowledge_value(title):
            categories["二手房避坑类"].append(article)
            assigned_ids.add(media_id)
        # Also include articles with strong knowledge indicators even without standard keywords
        elif not is_case_study(title) and any(kw in title for kw in ['旧房', '老房', '二手房']) and any(kw in title for kw in ['经验', '常识', '警告', '血泪', '教训', '避坑', '注意', '知道', '必须', '一定']):
            categories["二手房避坑类"].append(article)
            assigned_ids.add(media_id)

# ============================
# STEP 2: Sort and print
# ============================

# Sort each category by create_time descending
for cat in categories:
    categories[cat].sort(key=lambda x: x["create_time"], reverse=True)

# Convert create_time to readable date
for cat in categories:
    for article in categories[cat]:
        ts = article["create_time"]
        if ts > 0:
            dt = datetime.fromtimestamp(ts / 1000)
            article["date_str"] = dt.strftime("%Y-%m-%d")
        else:
            article["date_str"] = "unknown"

print("="*80)
print("FINAL CATEGORIZED ARTICLES (KNOWLEDGE ONLY)")
print("="*80)

total = 0
for category, articles in categories.items():
    print(f"\n## {category} ({len(articles)}篇)")
    for i, a in enumerate(articles, 1):
        print(f"  {i}. [{a['date_str']}] {a['title']}")
        print(f"     media_id: {a['media_id']}")
    total += len(articles)

print(f"\n{'='*80}")
print(f"Total: {total}")

# Save to JSON
output_path = r"E:\workspaces\2026-06-21-09-43-05\.workbuddy\skills\老房改造不踩雷\article_list.json"
output = {cat: [{"title": a["title"], "media_id": a["media_id"], "date": a["date_str"]} for a in articles] for cat, articles in categories.items()}
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\nSaved to: {output_path}")

# Print all media_ids grouped by category for batch fetching
print("\n\n=== MEDIA IDS BY CATEGORY ===")
for cat, articles in categories.items():
    print(f"\n# {cat} ({len(articles)})")
    for a in articles:
        print(f"{a['media_id']}")
