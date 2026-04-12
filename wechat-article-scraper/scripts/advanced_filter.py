#!/usr/bin/env python3
"""
高级筛选系统 - 多条件组合筛选、筛选模板

功能：
- 多条件组合筛选（AND/OR逻辑）
- 条件类型：时间、公众号、关键词、阅读量、标签
- 筛选模板保存/加载
- 筛选结果预览

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger('advanced-filter')


class FilterOperator(Enum):
    """筛选操作符"""
    EQ = "eq"           # 等于
    NE = "ne"           # 不等于
    GT = "gt"           # 大于
    GTE = "gte"         # 大于等于
    LT = "lt"           # 小于
    LTE = "lte"         # 小于等于
    CONTAINS = "contains"   # 包含
    NOT_CONTAINS = "not_contains"  # 不包含
    IN = "in"           # 在列表中
    NOT_IN = "not_in"   # 不在列表中
    BETWEEN = "between" # 在范围内
    REGEX = "regex"     # 正则匹配


class FilterLogic(Enum):
    """筛选逻辑"""
    AND = "and"
    OR = "or"


@dataclass
class FilterCondition:
    """筛选条件"""
    field: str
    operator: str
    value: Any
    logic: str = "and"  # and/or (与前一个条件的关系)

    def to_dict(self) -> Dict:
        return {
            "field": self.field,
            "operator": self.operator,
            "value": self.value,
            "logic": self.logic
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'FilterCondition':
        return cls(
            field=data.get("field", ""),
            operator=data.get("operator", ""),
            value=data.get("value"),
            logic=data.get("logic", "and")
        )

    def evaluate(self, article: Dict) -> bool:
        """评估条件是否匹配"""
        field_value = article.get(self.field)

        # 处理空值
        if field_value is None:
            if self.operator in [FilterOperator.NE.value, FilterOperator.NOT_CONTAINS.value]:
                return True
            return False

        op = self.operator

        try:
            if op == FilterOperator.EQ.value:
                return str(field_value) == str(self.value)

            elif op == FilterOperator.NE.value:
                return str(field_value) != str(self.value)

            elif op == FilterOperator.GT.value:
                return float(field_value) > float(self.value)

            elif op == FilterOperator.GTE.value:
                return float(field_value) >= float(self.value)

            elif op == FilterOperator.LT.value:
                return float(field_value) < float(self.value)

            elif op == FilterOperator.LTE.value:
                return float(field_value) <= float(self.value)

            elif op == FilterOperator.CONTAINS.value:
                return str(self.value).lower() in str(field_value).lower()

            elif op == FilterOperator.NOT_CONTAINS.value:
                return str(self.value).lower() not in str(field_value).lower()

            elif op == FilterOperator.IN.value:
                return str(field_value) in [str(v) for v in self.value]

            elif op == FilterOperator.NOT_IN.value:
                return str(field_value) not in [str(v) for v in self.value]

            elif op == FilterOperator.BETWEEN.value:
                if isinstance(self.value, (list, tuple)) and len(self.value) == 2:
                    return float(self.value[0]) <= float(field_value) <= float(self.value[1])
                return False

            elif op == FilterOperator.REGEX.value:
                return bool(re.search(self.value, str(field_value)))

        except (ValueError, TypeError):
            return False

        return False


@dataclass
class FilterTemplate:
    """筛选模板"""
    id: str
    name: str
    description: str
    conditions: List[FilterCondition]
    sort_by: str = "publish_time"
    sort_order: str = "desc"  # asc/desc
    limit: int = 1000
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "conditions": [c.to_dict() for c in self.conditions],
            "sort_by": self.sort_by,
            "sort_order": self.sort_order,
            "limit": self.limit,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'FilterTemplate':
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            conditions=[FilterCondition.from_dict(c) for c in data.get("conditions", [])],
            sort_by=data.get("sort_by", "publish_time"),
            sort_order=data.get("sort_order", "desc"),
            limit=data.get("limit", 1000),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", "")
        )


class AdvancedFilter:
    """高级筛选系统"""

    # 支持的字段
    SUPPORTED_FIELDS = {
        "title": "标题",
        "content": "正文内容",
        "account_name": "公众号",
        "publish_time": "发布时间",
        "read_count": "阅读量",
        "like_count": "点赞数",
        "share_count": "分享数",
        "comment_count": "评论数",
        "category": "分类",
        "tags": "标签",
        "url": "链接",
        "created_at": "抓取时间"
    }

    # 字段类型
    FIELD_TYPES = {
        "title": "text",
        "content": "text",
        "account_name": "text",
        "publish_time": "datetime",
        "read_count": "number",
        "like_count": "number",
        "share_count": "number",
        "comment_count": "number",
        "category": "text",
        "tags": "text",
        "url": "text",
        "created_at": "datetime"
    }

    def __init__(self, templates_dir: str = None):
        if templates_dir is None:
            templates_dir = str(Path.home() / ".wechat-scraper" / "filter_templates")

        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.templates: Dict[str, FilterTemplate] = {}
        self._load_templates()

    def _load_templates(self):
        """加载筛选模板"""
        for template_file in self.templates_dir.glob("*.json"):
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    template = FilterTemplate.from_dict(data)
                    self.templates[template.id] = template
            except Exception as e:
                logger.warning(f"加载模板失败 {template_file}: {e}")

    def _save_template(self, template: FilterTemplate):
        """保存模板到文件"""
        template_file = self.templates_dir / f"{template.id}.json"
        with open(template_file, 'w', encoding='utf-8') as f:
            json.dump(template.to_dict(), f, ensure_ascii=False, indent=2)

    def create_template(self, name: str, description: str,
                       conditions: List[FilterCondition],
                       sort_by: str = "publish_time",
                       sort_order: str = "desc",
                       limit: int = 1000) -> FilterTemplate:
        """创建筛选模板"""
        import hashlib

        template_id = hashlib.md5(
            f"{name}{datetime.now()}".encode()
        ).hexdigest()[:12]

        now = datetime.now().isoformat()

        template = FilterTemplate(
            id=template_id,
            name=name,
            description=description,
            conditions=conditions,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            created_at=now,
            updated_at=now
        )

        self.templates[template_id] = template
        self._save_template(template)

        logger.info(f"筛选模板已创建: {name} ({template_id})")
        return template

    def get_template(self, template_id: str) -> Optional[FilterTemplate]:
        """获取筛选模板"""
        return self.templates.get(template_id)

    def list_templates(self) -> List[FilterTemplate]:
        """列出所有模板"""
        return sorted(self.templates.values(), key=lambda t: t.created_at, reverse=True)

    def delete_template(self, template_id: str) -> bool:
        """删除模板"""
        if template_id in self.templates:
            del self.templates[template_id]
            template_file = self.templates_dir / f"{template_id}.json"
            if template_file.exists():
                template_file.unlink()
            return True
        return False

    def apply_filter(self, articles: List[Dict],
                    conditions: List[FilterCondition]) -> List[Dict]:
        """应用筛选条件到文章列表"""
        if not conditions:
            return articles

        results = []

        for article in articles:
            match = True

            for i, condition in enumerate(conditions):
                condition_match = condition.evaluate(article)

                if i == 0:
                    match = condition_match
                elif condition.logic == FilterLogic.AND.value:
                    match = match and condition_match
                elif condition.logic == FilterLogic.OR.value:
                    match = match or condition_match

            if match:
                results.append(article)

        return results

    def apply_template(self, articles: List[Dict],
                      template: FilterTemplate) -> List[Dict]:
        """应用筛选模板"""
        # 筛选
        results = self.apply_filter(articles, template.conditions)

        # 排序
        reverse = template.sort_order == "desc"
        try:
            results = sorted(
                results,
                key=lambda x: x.get(template.sort_by, 0) or 0,
                reverse=reverse
            )
        except Exception as e:
            logger.warning(f"排序失败: {e}")

        # 限制数量
        return results[:template.limit]

    def filter_from_db(self, db_path: str,
                      conditions: List[FilterCondition],
                      sort_by: str = "publish_time",
                      sort_order: str = "desc",
                      limit: int = 1000) -> List[Dict]:
        """直接从数据库筛选"""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # 构建SQL查询
        where_clauses = []
        params = []

        for condition in conditions:
            field = condition.field
            op = condition.operator
            value = condition.value

            # 映射操作符到SQL
            sql_op = {
                "eq": "=",
                "ne": "!=",
                "gt": ">",
                "gte": ">=",
                "lt": "<",
                "lte": "<=",
                "contains": "LIKE",
                "not_contains": "NOT LIKE",
                "in": "IN",
                "not_in": "NOT IN"
            }.get(op)

            if sql_op:
                if op in ["contains", "not_contains"]:
                    where_clauses.append(f"{field} {sql_op} ?")
                    params.append(f"%{value}%")
                elif op in ["in", "not_in"]:
                    placeholders = ",".join(["?"] * len(value))
                    where_clauses.append(f"{field} {sql_op} ({placeholders})")
                    params.extend(value)
                else:
                    where_clauses.append(f"{field} {sql_op} ?")
                    params.append(value)

        sql = "SELECT * FROM articles"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        sql += f" ORDER BY {sort_by} {sort_order.upper()} LIMIT ?"
        params.append(limit)

        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_field_suggestions(self, db_path: str, field: str,
                             query: str = "", limit: int = 10) -> List[str]:
        """获取字段建议值（用于自动补全）"""
        if field not in self.SUPPORTED_FIELDS:
            return []

        conn = sqlite3.connect(db_path)

        try:
            cursor = conn.execute(
                f"SELECT DISTINCT {field} FROM articles WHERE {field} LIKE ? LIMIT ?",
                (f"%{query}%", limit)
            )
            results = [row[0] for row in cursor.fetchall() if row[0]]
            return results
        except:
            return []
        finally:
            conn.close()

    def get_stats(self, articles: List[Dict]) -> Dict:
        """获取筛选结果统计"""
        if not articles:
            return {
                "total": 0,
                "accounts": 0,
                "date_range": "",
                "total_reads": 0,
                "total_likes": 0
            }

        accounts = set(a.get("account_name") for a in articles if a.get("account_name"))

        dates = [a.get("publish_time", "") for a in articles if a.get("publish_time")]
        date_range = ""
        if dates:
            sorted_dates = sorted(dates)
            date_range = f"{sorted_dates[0][:10]} ~ {sorted_dates[-1][:10]}"

        total_reads = sum(a.get("read_count", 0) or 0 for a in articles)
        total_likes = sum(a.get("like_count", 0) or 0 for a in articles)

        return {
            "total": len(articles),
            "accounts": len(accounts),
            "date_range": date_range,
            "total_reads": total_reads,
            "total_likes": total_likes,
            "avg_reads": total_reads // len(articles) if articles else 0
        }


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='高级筛选系统')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 创建模板
    create_parser = subparsers.add_parser('create', help='创建筛选模板')
    create_parser.add_argument('--name', required=True)
    create_parser.add_argument('--desc', default="")
    create_parser.add_argument('--field', required=True)
    create_parser.add_argument('--op', required=True)
    create_parser.add_argument('--value', required=True)

    # 列出模板
    subparsers.add_parser('list', help='列出模板')

    # 应用模板
    apply_parser = subparsers.add_parser('apply', help='应用模板')
    apply_parser.add_argument('--template', required=True)
    apply_parser.add_argument('--db', required=True)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    filter_system = AdvancedFilter()

    if args.command == 'create':
        condition = FilterCondition(
            field=args.field,
            operator=args.op,
            value=args.value
        )
        template = filter_system.create_template(
            name=args.name,
            description=args.desc,
            conditions=[condition]
        )
        print(f"模板创建成功: {template.id}")

    elif args.command == 'list':
        templates = filter_system.list_templates()
        print(f"\n筛选模板 ({len(templates)}个):\n")
        for t in templates:
            print(f"  {t.name} ({t.id})")
            print(f"    条件数: {len(t.conditions)} | 创建: {t.created_at[:10]}")

    elif args.command == 'apply':
        template = filter_system.get_template(args.template)
        if not template:
            print(f"模板不存在: {args.template}")
            return

        results = filter_system.filter_from_db(
            args.db,
            template.conditions,
            template.sort_by,
            template.sort_order,
            template.limit
        )

        stats = filter_system.get_stats(results)
        print(f"\n筛选结果:\n")
        print(f"  匹配文章: {stats['total']}")
        print(f"  涉及公众号: {stats['accounts']}")
        print(f"  时间范围: {stats['date_range']}")
        print(f"  总阅读量: {stats['total_reads']}")


if __name__ == '__main__':
    main()
