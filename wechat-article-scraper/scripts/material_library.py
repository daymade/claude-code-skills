#!/usr/bin/env python3
"""
素材库管理系统 - 文案/图片收藏与灵感管理

功能：
- 素材收藏（文案/图片/链接）
- 标签分类系统
- 快速检索
- 灵感收藏夹
- 素材复用统计

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict
import mimetypes

logger = logging.getLogger('material-library')


@dataclass
class Material:
    """素材条目"""
    id: str
    type: str  # text/image/link/video/audio/file
    content: str
    title: Optional[str]
    source: Optional[str]
    tags: List[str]
    collection_id: Optional[str]
    usage_count: int
    created_at: str
    updated_at: str
    metadata: Dict[str, Any]


@dataclass
class Collection:
    """收藏夹"""
    id: str
    name: str
    description: str
    icon: str
    color: str
    material_count: int
    created_at: str


@dataclass
class Tag:
    """标签"""
    id: str
    name: str
    color: str
    usage_count: int


class MaterialLibrary:
    """素材库"""

    MATERIAL_TYPES = {
        'text': {'name': '文案', 'icon': '📝'},
        'image': {'name': '图片', 'icon': '🖼️'},
        'link': {'name': '链接', 'icon': '🔗'},
        'video': {'name': '视频', 'icon': '🎬'},
        'audio': {'name': '音频', 'icon': '🎵'},
        'file': {'name': '文件', 'icon': '📄'}
    }

    DEFAULT_COLLECTIONS = [
        {'id': 'inspiration', 'name': '灵感收集', 'description': '收集的创意灵感', 'icon': '💡', 'color': '#FFD700'},
        {'id': 'templates', 'name': '模板库', 'description': '常用文案模板', 'icon': '📋', 'color': '#4A90D9'},
        {'id': 'images', 'name': '图片素材', 'description': '精选图片素材', 'icon': '🖼️', 'color': '#50C878'},
        {'id': 'references', 'name': '参考资料', 'description': '学习参考资料', 'icon': '📚', 'color': '#9B59B6'},
        {'id': 'unsorted', 'name': '未分类', 'description': '待整理的素材', 'icon': '📦', 'color': '#95A5A6'}
    ]

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "materials.db")
        self.db_path = db_path
        self._init_db()
        self._ensure_default_collections()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)

        # 素材表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                title TEXT,
                source TEXT,
                tags TEXT DEFAULT '[]',
                collection_id TEXT,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT DEFAULT '{}'
            )
        """)

        # 收藏夹表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS collections (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                icon TEXT,
                color TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 标签表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                color TEXT,
                usage_count INTEGER DEFAULT 0
            )
        """)

        # 全文搜索索引
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS materials_fts USING fts5(
                content, title, tags,
                content='materials',
                content_rowid='rowid'
            )
        """)

        conn.commit()
        conn.close()

    def _ensure_default_collections(self):
        """确保默认收藏夹存在"""
        conn = sqlite3.connect(self.db_path)

        for coll in self.DEFAULT_COLLECTIONS:
            conn.execute("""
                INSERT OR IGNORE INTO collections (id, name, description, icon, color)
                VALUES (?, ?, ?, ?, ?)
            """, (coll['id'], coll['name'], coll['description'], coll['icon'], coll['color']))

        conn.commit()
        conn.close()

    def add_material(self, material_type: str, content: str,
                    title: str = None, source: str = None,
                    tags: List[str] = None, collection_id: str = None,
                    metadata: Dict = None) -> Material:
        """添加素材"""
        material_id = hashlib.md5(
            f"{material_type}{content}{datetime.now()}".encode()
        ).hexdigest()[:12]

        now = datetime.now().isoformat()
        tags = tags or []

        # 如果没有指定收藏夹，放入未分类
        if not collection_id:
            collection_id = 'unsorted'

        conn = sqlite3.connect(self.db_path)

        conn.execute("""
            INSERT INTO materials
            (id, type, content, title, source, tags, collection_id, usage_count, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """, (
            material_id, material_type, content, title, source,
            json.dumps(tags), collection_id, now, now,
            json.dumps(metadata or {})
        ))

        # 更新标签使用计数
        for tag in tags:
            conn.execute("""
                INSERT INTO tags (id, name, usage_count)
                VALUES (?, ?, 1)
                ON CONFLICT(name) DO UPDATE SET usage_count = usage_count + 1
            """, (hashlib.md5(tag.encode()).hexdigest()[:8], tag))

        conn.commit()
        conn.close()

        logger.info(f"素材已添加: {material_id}")

        return Material(
            id=material_id,
            type=material_type,
            content=content,
            title=title,
            source=source,
            tags=tags,
            collection_id=collection_id,
            usage_count=0,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )

    def get_material(self, material_id: str) -> Optional[Material]:
        """获取单个素材"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute(
            "SELECT * FROM materials WHERE id = ?",
            (material_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_material(row)

    def search_materials(self, query: str = None, material_type: str = None,
                        tags: List[str] = None, collection_id: str = None,
                        limit: int = 50) -> List[Material]:
        """搜索素材"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        conditions = []
        params = []

        if query:
            conditions.append("(content LIKE ? OR title LIKE ? OR tags LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])

        if material_type:
            conditions.append("type = ?")
            params.append(material_type)

        if collection_id:
            conditions.append("collection_id = ?")
            params.append(collection_id)

        sql = "SELECT * FROM materials"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        materials = [self._row_to_material(row) for row in rows]

        # 如果指定了标签，进行过滤
        if tags:
            materials = [
                m for m in materials
                if any(tag in m.tags for tag in tags)
            ]

        return materials

    def list_collections(self) -> List[Collection]:
        """列出所有收藏夹"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT c.*, COUNT(m.id) as material_count
            FROM collections c
            LEFT JOIN materials m ON c.id = m.collection_id
            GROUP BY c.id
            ORDER BY c.created_at
        """)

        rows = cursor.fetchall()
        conn.close()

        return [
            Collection(
                id=row['id'],
                name=row['name'],
                description=row['description'] or '',
                icon=row['icon'] or '📁',
                color=row['color'] or '#999',
                material_count=row['material_count'],
                created_at=row['created_at']
            )
            for row in rows
        ]

    def list_tags(self) -> List[Tag]:
        """列出所有标签"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute(
            "SELECT * FROM tags ORDER BY usage_count DESC"
        )

        rows = cursor.fetchall()
        conn.close()

        colors = ['#e74c3c', '#e67e22', '#f1c40f', '#27ae60', '#3498db', '#9b59b6', '#34495e']

        return [
            Tag(
                id=row['id'],
                name=row['name'],
                color=row['color'] or colors[i % len(colors)],
                usage_count=row['usage_count']
            )
            for i, row in enumerate(rows)
        ]

    def update_material(self, material_id: str,
                       title: str = None,
                       tags: List[str] = None,
                       collection_id: str = None) -> bool:
        """更新素材"""
        conn = sqlite3.connect(self.db_path)

        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)

        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags))

        if collection_id is not None:
            updates.append("collection_id = ?")
            params.append(collection_id)

        if not updates:
            conn.close()
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(material_id)

        sql = f"UPDATE materials SET {', '.join(updates)} WHERE id = ?"
        cursor = conn.execute(sql, params)

        conn.commit()
        conn.close()

        return cursor.rowcount > 0

    def increment_usage(self, material_id: str):
        """增加使用次数"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE materials SET usage_count = usage_count + 1 WHERE id = ?",
            (material_id,)
        )
        conn.commit()
        conn.close()

    def delete_material(self, material_id: str) -> bool:
        """删除素材"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def create_collection(self, name: str, description: str = "",
                         icon: str = "📁", color: str = "#999") -> Collection:
        """创建收藏夹"""
        coll_id = hashlib.md5(f"{name}{datetime.now()}".encode()).hexdigest()[:12]

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO collections (id, name, description, icon, color)
            VALUES (?, ?, ?, ?, ?)
        """, (coll_id, name, description, icon, color))
        conn.commit()
        conn.close()

        return Collection(
            id=coll_id,
            name=name,
            description=description,
            icon=icon,
            color=color,
            material_count=0,
            created_at=datetime.now().isoformat()
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_path)

        # 素材统计
        cursor = conn.execute("SELECT type, COUNT(*) as count FROM materials GROUP BY type")
        type_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # 总数
        cursor = conn.execute("SELECT COUNT(*) FROM materials")
        total = cursor.fetchone()[0]

        # 今日新增
        today = datetime.now().strftime('%Y-%m-%d')
        cursor = conn.execute(
            "SELECT COUNT(*) FROM materials WHERE DATE(created_at) = ?",
            (today,)
        )
        today_added = cursor.fetchone()[0]

        # 最常使用
        cursor = conn.execute(
            "SELECT id, title, usage_count FROM materials ORDER BY usage_count DESC LIMIT 5"
        )
        most_used = [{'id': r[0], 'title': r[1], 'count': r[2]} for r in cursor.fetchall()]

        conn.close()

        return {
            'total_materials': total,
            'type_distribution': type_counts,
            'today_added': today_added,
            'most_used': most_used,
            'collections_count': len(self.list_collections()),
            'tags_count': len(self.list_tags())
        }

    def _row_to_material(self, row: sqlite3.Row) -> Material:
        """将数据库行转换为Material对象"""
        return Material(
            id=row['id'],
            type=row['type'],
            content=row['content'],
            title=row['title'],
            source=row['source'],
            tags=json.loads(row['tags']) if row['tags'] else [],
            collection_id=row['collection_id'],
            usage_count=row['usage_count'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            metadata=json.loads(row['metadata']) if row['metadata'] else {}
        )


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='素材库管理')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 添加素材
    add_parser = subparsers.add_parser('add', help='添加素材')
    add_parser.add_argument('type', choices=['text', 'image', 'link', 'video'],
                           help='素材类型')
    add_parser.add_argument('content', help='素材内容或文件路径')
    add_parser.add_argument('--title', help='标题')
    add_parser.add_argument('--source', help='来源')
    add_parser.add_argument('--tags', help='标签(逗号分隔)')
    add_parser.add_argument('--collection', help='收藏夹ID')

    # 搜索素材
    search_parser = subparsers.add_parser('search', help='搜索素材')
    search_parser.add_argument('query', help='搜索关键词')
    search_parser.add_argument('--type', choices=['text', 'image', 'link', 'video'])
    search_parser.add_argument('--tag', help='标签筛选')
    search_parser.add_argument('-n', '--limit', type=int, default=20)

    # 列出收藏夹
    subparsers.add_parser('collections', help='列出收藏夹')

    # 列出标签
    subparsers.add_parser('tags', help='列出标签')

    # 查看统计
    subparsers.add_parser('stats', help='查看统计')

    # 使用素材
    use_parser = subparsers.add_parser('use', help='使用素材(增加计数)')
    use_parser.add_argument('id', help='素材ID')

    # 创建收藏夹
    create_coll_parser = subparsers.add_parser('create-collection', help='创建收藏夹')
    create_coll_parser.add_argument('name', help='收藏夹名称')
    create_coll_parser.add_argument('--desc', default='', help='描述')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    library = MaterialLibrary()

    if args.command == 'add':
        content = args.content
        if os.path.exists(content):
            with open(content, 'r', encoding='utf-8') as f:
                content = f.read()

        tags = [t.strip() for t in args.tags.split(',')] if args.tags else []

        material = library.add_material(
            material_type=args.type,
            content=content,
            title=args.title,
            source=args.source,
            tags=tags,
            collection_id=args.collection
        )

        print(f"素材已添加: {material.id}")
        print(f"  类型: {material.type}")
        print(f"  标题: {material.title or 'N/A'}")
        print(f"  标签: {', '.join(material.tags)}")

    elif args.command == 'search':
        tags = [args.tag] if args.tag else None
        results = library.search_materials(
            query=args.query,
            material_type=args.type,
            tags=tags,
            limit=args.limit
        )

        print(f"\n找到 {len(results)} 个素材:\n")
        for m in results[:10]:
            icon = library.MATERIAL_TYPES.get(m.type, {}).get('icon', '📄')
            title = m.title or m.content[:30] + "..."
            print(f"{icon} [{m.id}] {title}")
            print(f"   标签: {', '.join(m.tags[:3])} | 使用: {m.usage_count}次")

    elif args.command == 'collections':
        collections = library.list_collections()
        print(f"\n收藏夹 ({len(collections)}个):\n")
        for c in collections:
            print(f"{c.icon} {c.name} ({c.material_count}个)")
            if c.description:
                print(f"   {c.description}")

    elif args.command == 'tags':
        tags = library.list_tags()
        print(f"\n标签 ({len(tags)}个):\n")
        for t in tags:
            print(f"  #{t.name} ({t.usage_count}次使用)")

    elif args.command == 'stats':
        stats = library.get_stats()
        print(f"\n素材库统计:\n")
        print(f"  总素材: {stats['total_materials']}")
        print(f"  今日新增: {stats['today_added']}")
        print(f"  收藏夹: {stats['collections_count']}")
        print(f"  标签: {stats['tags_count']}")
        print(f"\n类型分布:")
        for t, count in stats['type_distribution'].items():
            icon = library.MATERIAL_TYPES.get(t, {}).get('icon', '📄')
            print(f"  {icon} {t}: {count}")

    elif args.command == 'use':
        library.increment_usage(args.id)
        print(f"已记录使用: {args.id}")

    elif args.command == 'create-collection':
        coll = library.create_collection(args.name, args.desc)
        print(f"收藏夹已创建: {coll.id}")
        print(f"  名称: {coll.name}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
