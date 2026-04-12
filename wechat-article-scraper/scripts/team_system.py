#!/usr/bin/env python3
"""
团队协作系统 - 多用户、共享工作区、权限管理

功能：
- 多用户管理：用户注册、认证、团队隔离
- RBAC 权限：admin/member/viewer 三级权限
- 共享工作区：团队共享监控列表、文章收藏
- 文章标注：标签、评论、高亮
- 活动日志：团队操作审计

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import hashlib
import secrets
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger('team-system')


class UserRole(Enum):
    """用户角色"""
    ADMIN = "admin"       # 管理员：全部权限
    MEMBER = "member"     # 成员：添加/编辑，不可删除团队
    VIEWER = "viewer"     # 访客：只读访问


class Permission(Enum):
    """权限枚举"""
    TEAM_MANAGE = "team_manage"           # 管理团队
    MEMBER_INVITE = "member_invite"       # 邀请成员
    MEMBER_REMOVE = "member_remove"       # 移除成员
    MONITOR_CREATE = "monitor_create"     # 创建监控
    MONITOR_DELETE = "monitor_delete"     # 删除监控
    ARTICLE_EDIT = "article_edit"         # 编辑文章
    ARTICLE_DELETE = "article_delete"     # 删除文章
    COLLECTION_MANAGE = "collection_manage"  # 管理收藏
    SETTINGS_CHANGE = "settings_change"   # 修改设置
    BILLING_VIEW = "billing_view"         # 查看账单


# 角色-权限映射
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [
        Permission.TEAM_MANAGE, Permission.MEMBER_INVITE, Permission.MEMBER_REMOVE,
        Permission.MONITOR_CREATE, Permission.MONITOR_DELETE,
        Permission.ARTICLE_EDIT, Permission.ARTICLE_DELETE,
        Permission.COLLECTION_MANAGE, Permission.SETTINGS_CHANGE,
        Permission.BILLING_VIEW
    ],
    UserRole.MEMBER: [
        Permission.MONITOR_CREATE, Permission.ARTICLE_EDIT,
        Permission.COLLECTION_MANAGE
    ],
    UserRole.VIEWER: []
}


@dataclass
class User:
    """用户"""
    id: str
    email: str
    name: str
    api_key: str
    created_at: str
    last_login: str = ""
    teams: List[str] = field(default_factory=list)  # 所属团队ID列表

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "teams": self.teams
        }


@dataclass
class Team:
    """团队"""
    id: str
    name: str
    description: str
    owner_id: str
    invite_code: str
    created_at: str
    updated_at: str
    settings: Dict = field(default_factory=dict)
    member_count: int = 0
    article_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
            "invite_code": self.invite_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "settings": self.settings,
            "member_count": self.member_count,
            "article_count": self.article_count
        }


@dataclass
class TeamMember:
    """团队成员关系"""
    team_id: str
    user_id: str
    role: str
    joined_at: str
    invited_by: str = ""

    def to_dict(self) -> Dict:
        return {
            "team_id": self.team_id,
            "user_id": self.user_id,
            "role": self.role,
            "joined_at": self.joined_at,
            "invited_by": self.invited_by
        }

    def has_permission(self, permission: Permission) -> bool:
        """检查是否有权限"""
        try:
            role = UserRole(self.role)
            return permission in ROLE_PERMISSIONS.get(role, [])
        except:
            return False


@dataclass
class SharedCollection:
    """共享收藏夹"""
    id: str
    team_id: str
    name: str
    description: str
    created_by: str
    created_at: str
    updated_at: str
    article_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "team_id": self.team_id,
            "name": self.name,
            "description": self.description,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "article_count": self.article_count
        }


@dataclass
class CollectionItem:
    """收藏项"""
    id: str
    collection_id: str
    article_id: str
    added_by: str
    added_at: str
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    highlights: List[Dict] = field(default_factory=list)  # 高亮位置

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "collection_id": self.collection_id,
            "article_id": self.article_id,
            "added_by": self.added_by,
            "added_at": self.added_at,
            "notes": self.notes,
            "tags": self.tags,
            "highlights": self.highlights
        }


@dataclass
class ArticleComment:
    """文章评论"""
    id: str
    article_id: str
    team_id: str
    user_id: str
    user_name: str
    content: str
    created_at: str
    parent_id: str = ""  # 回复的评论ID

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "article_id": self.article_id,
            "team_id": self.team_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "content": self.content,
            "created_at": self.created_at,
            "parent_id": self.parent_id
        }


@dataclass
class TeamActivity:
    """团队活动日志"""
    id: str
    team_id: str
    user_id: str
    user_name: str
    action: str
    target_type: str  # article, collection, member, etc.
    target_id: str
    details: Dict
    created_at: str

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "team_id": self.team_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "details": self.details,
            "created_at": self.created_at
        }


class TeamSystem:
    """团队协作系统核心"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "team.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)

        # 用户表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                name TEXT,
                api_key TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """)

        # 团队表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                owner_id TEXT,
                invite_code TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                settings TEXT DEFAULT '{}',
                member_count INTEGER DEFAULT 0,
                article_count INTEGER DEFAULT 0
            )
        """)

        # 团队成员关系表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_members (
                team_id TEXT,
                user_id TEXT,
                role TEXT DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                invited_by TEXT,
                PRIMARY KEY (team_id, user_id),
                FOREIGN KEY (team_id) REFERENCES teams(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # 共享收藏夹表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shared_collections (
                id TEXT PRIMARY KEY,
                team_id TEXT,
                name TEXT NOT NULL,
                description TEXT,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                article_count INTEGER DEFAULT 0,
                FOREIGN KEY (team_id) REFERENCES teams(id)
            )
        """)

        # 收藏项表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS collection_items (
                id TEXT PRIMARY KEY,
                collection_id TEXT,
                article_id TEXT,
                added_by TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                tags TEXT DEFAULT '[]',
                highlights TEXT DEFAULT '[]',
                FOREIGN KEY (collection_id) REFERENCES shared_collections(id)
            )
        """)

        # 文章评论表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS article_comments (
                id TEXT PRIMARY KEY,
                article_id TEXT,
                team_id TEXT,
                user_id TEXT,
                user_name TEXT,
                content TEXT,
                parent_id TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id)
            )
        """)

        # 团队活动日志表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_activities (
                id TEXT PRIMARY KEY,
                team_id TEXT,
                user_id TEXT,
                user_name TEXT,
                action TEXT,
                target_type TEXT,
                target_id TEXT,
                details TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id)
            )
        """)

        conn.commit()
        conn.close()

    # ========== 用户管理 ==========

    def create_user(self, email: str, name: str) -> User:
        """创建用户"""
        user_id = hashlib.sha256(f"{email}{datetime.now()}".encode()).hexdigest()[:16]
        api_key = secrets.token_urlsafe(32)

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO users (id, email, name, api_key, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, email, name, api_key, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        logger.info(f"用户创建: {email} ({user_id})")
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> Optional[User]:
        """获取用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        # 获取用户所属团队
        cursor = conn.execute(
            "SELECT team_id FROM team_members WHERE user_id = ?",
            (user_id,)
        )
        teams = [r["team_id"] for r in cursor.fetchall()]
        conn.close()

        return User(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            api_key=row["api_key"],
            created_at=row["created_at"],
            last_login=row["last_login"] or "",
            teams=teams
        )

    def get_user_by_api_key(self, api_key: str) -> Optional[User]:
        """通过API Key获取用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT id FROM users WHERE api_key = ?", (api_key,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return self.get_user(row["id"])
        return None

    def update_last_login(self, user_id: str):
        """更新最后登录时间"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now().isoformat(), user_id)
        )
        conn.commit()
        conn.close()

    # ========== 团队管理 ==========

    def create_team(self, name: str, description: str, owner_id: str) -> Team:
        """创建团队"""
        team_id = hashlib.sha256(f"{name}{owner_id}{datetime.now()}".encode()).hexdigest()[:16]
        invite_code = secrets.token_urlsafe(16)

        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO teams (id, name, description, owner_id, invite_code, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (team_id, name, description, owner_id, invite_code, now, now))

        # 创建者自动成为 admin
        conn.execute("""
            INSERT INTO team_members (team_id, user_id, role, joined_at)
            VALUES (?, ?, ?, ?)
        """, (team_id, owner_id, UserRole.ADMIN.value, now))

        # 更新成员计数
        conn.execute("UPDATE teams SET member_count = 1 WHERE id = ?", (team_id,))

        conn.commit()
        conn.close()

        self._log_activity(team_id, owner_id, "", "team_created", "team", team_id,
                          {"name": name})

        logger.info(f"团队创建: {name} ({team_id})")
        return self.get_team(team_id)

    def get_team(self, team_id: str) -> Optional[Team]:
        """获取团队"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Team(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            owner_id=row["owner_id"],
            invite_code=row["invite_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            settings=json.loads(row["settings"]),
            member_count=row["member_count"],
            article_count=row["article_count"]
        )

    def list_user_teams(self, user_id: str) -> List[Team]:
        """获取用户所属的所有团队"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT t.* FROM teams t
            JOIN team_members tm ON t.id = tm.team_id
            WHERE tm.user_id = ?
            ORDER BY t.created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()

        teams = []
        for row in rows:
            teams.append(Team(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                owner_id=row["owner_id"],
                invite_code=row["invite_code"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                settings=json.loads(row["settings"]),
                member_count=row["member_count"],
                article_count=row["article_count"]
            ))
        return teams

    def join_team(self, invite_code: str, user_id: str) -> Optional[TeamMember]:
        """通过邀请码加入团队"""
        team = self._get_team_by_invite_code(invite_code)
        if not team:
            return None

        # 检查是否已是成员
        existing = self.get_team_member(team.id, user_id)
        if existing:
            return existing

        conn = sqlite3.connect(self.db_path)
        now = datetime.now().isoformat()

        conn.execute("""
            INSERT INTO team_members (team_id, user_id, role, joined_at)
            VALUES (?, ?, ?, ?)
        """, (team.id, user_id, UserRole.MEMBER.value, now))

        # 更新成员计数
        conn.execute("""
            UPDATE teams SET member_count = member_count + 1, updated_at = ?
            WHERE id = ?
        """, (now, team.id))

        conn.commit()
        conn.close()

        user = self.get_user(user_id)
        self._log_activity(team.id, user_id, user.name if user else "", "member_joined",
                          "member", user_id, {})

        return self.get_team_member(team.id, user_id)

    def _get_team_by_invite_code(self, invite_code: str) -> Optional[Team]:
        """通过邀请码获取团队"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT id FROM teams WHERE invite_code = ?", (invite_code,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return self.get_team(row["id"])
        return None

    def get_team_member(self, team_id: str, user_id: str) -> Optional[TeamMember]:
        """获取团队成员关系"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, user_id)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return TeamMember(
            team_id=row["team_id"],
            user_id=row["user_id"],
            role=row["role"],
            joined_at=row["joined_at"],
            invited_by=row["invited_by"]
        )

    def list_team_members(self, team_id: str) -> List[Dict]:
        """获取团队成员列表（包含用户信息）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT tm.*, u.email, u.name
            FROM team_members tm
            JOIN users u ON tm.user_id = u.id
            WHERE tm.team_id = ?
            ORDER BY tm.joined_at
        """, (team_id,))
        rows = cursor.fetchall()
        conn.close()

        members = []
        for row in rows:
            members.append({
                "user_id": row["user_id"],
                "name": row["name"],
                "email": row["email"],
                "role": row["role"],
                "joined_at": row["joined_at"]
            })
        return members

    def update_member_role(self, team_id: str, user_id: str, new_role: str,
                          changed_by: str) -> bool:
        """更新成员角色"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "UPDATE team_members SET role = ? WHERE team_id = ? AND user_id = ?",
            (new_role, team_id, user_id)
        )
        conn.commit()
        conn.close()

        if cursor.rowcount > 0:
            user = self.get_user(changed_by)
            target_user = self.get_user(user_id)
            self._log_activity(team_id, changed_by, user.name if user else "",
                              "role_changed", "member", user_id,
                              {"new_role": new_role,
                               "target": target_user.name if target_user else ""})
            return True
        return False

    def remove_member(self, team_id: str, user_id: str, removed_by: str) -> bool:
        """移除团队成员"""
        conn = sqlite3.connect(self.db_path)

        cursor = conn.execute(
            "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, user_id)
        )

        if cursor.rowcount > 0:
            conn.execute(
                "UPDATE teams SET member_count = member_count - 1 WHERE id = ?",
                (team_id,)
            )

        conn.commit()
        conn.close()

        if cursor.rowcount > 0:
            user = self.get_user(removed_by)
            target_user = self.get_user(user_id)
            self._log_activity(team_id, removed_by, user.name if user else "",
                              "member_removed", "member", user_id,
                              {"target": target_user.name if target_user else ""})
            return True
        return False

    # ========== 收藏夹管理 ==========

    def create_collection(self, team_id: str, name: str, description: str,
                         created_by: str) -> SharedCollection:
        """创建共享收藏夹"""
        collection_id = hashlib.sha256(
            f"{team_id}{name}{datetime.now()}".encode()
        ).hexdigest()[:16]

        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO shared_collections
            (id, team_id, name, description, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (collection_id, team_id, name, description, created_by, now, now))
        conn.commit()
        conn.close()

        user = self.get_user(created_by)
        self._log_activity(team_id, created_by, user.name if user else "",
                          "collection_created", "collection", collection_id,
                          {"name": name})

        return self.get_collection(collection_id)

    def get_collection(self, collection_id: str) -> Optional[SharedCollection]:
        """获取收藏夹"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM shared_collections WHERE id = ?",
            (collection_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return SharedCollection(
            id=row["id"],
            team_id=row["team_id"],
            name=row["name"],
            description=row["description"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            article_count=row["article_count"]
        )

    def list_team_collections(self, team_id: str) -> List[SharedCollection]:
        """获取团队的所有收藏夹"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM shared_collections WHERE team_id = ? ORDER BY updated_at DESC",
            (team_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        collections = []
        for row in rows:
            collections.append(SharedCollection(
                id=row["id"],
                team_id=row["team_id"],
                name=row["name"],
                description=row["description"],
                created_by=row["created_by"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                article_count=row["article_count"]
            ))
        return collections

    def add_to_collection(self, collection_id: str, article_id: str,
                         added_by: str, notes: str = "",
                         tags: List[str] = None) -> CollectionItem:
        """添加文章到收藏夹"""
        item_id = hashlib.sha256(
            f"{collection_id}{article_id}{datetime.now()}".encode()
        ).hexdigest()[:16]

        tags = tags or []

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO collection_items
            (id, collection_id, article_id, added_by, added_at, notes, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (item_id, collection_id, article_id, added_by,
              datetime.now().isoformat(), notes, json.dumps(tags)))

        # 更新文章计数
        conn.execute("""
            UPDATE shared_collections
            SET article_count = article_count + 1, updated_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), collection_id))

        conn.commit()
        conn.close()

        collection = self.get_collection(collection_id)
        user = self.get_user(added_by)
        self._log_activity(collection.team_id, added_by, user.name if user else "",
                          "article_collected", "article", article_id,
                          {"collection": collection.name})

        return self.get_collection_item(item_id)

    def get_collection_item(self, item_id: str) -> Optional[CollectionItem]:
        """获取收藏项"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM collection_items WHERE id = ?",
            (item_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return CollectionItem(
            id=row["id"],
            collection_id=row["collection_id"],
            article_id=row["article_id"],
            added_by=row["added_by"],
            added_at=row["added_at"],
            notes=row["notes"],
            tags=json.loads(row["tags"]),
            highlights=json.loads(row["highlights"])
        )

    def list_collection_items(self, collection_id: str) -> List[CollectionItem]:
        """获取收藏夹的所有文章"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM collection_items WHERE collection_id = ? ORDER BY added_at DESC",
            (collection_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        items = []
        for row in rows:
            items.append(CollectionItem(
                id=row["id"],
                collection_id=row["collection_id"],
                article_id=row["article_id"],
                added_by=row["added_by"],
                added_at=row["added_at"],
                notes=row["notes"],
                tags=json.loads(row["tags"]),
                highlights=json.loads(row["highlights"])
            ))
        return items

    # ========== 评论系统 ==========

    def add_comment(self, article_id: str, team_id: str, user_id: str,
                   content: str, parent_id: str = "") -> ArticleComment:
        """添加评论"""
        comment_id = hashlib.sha256(
            f"{article_id}{user_id}{datetime.now()}".encode()
        ).hexdigest()[:16]

        user = self.get_user(user_id)
        user_name = user.name if user else "Unknown"

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO article_comments
            (id, article_id, team_id, user_id, user_name, content, parent_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (comment_id, article_id, team_id, user_id, user_name,
              content, parent_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        self._log_activity(team_id, user_id, user_name, "comment_added",
                          "article", article_id, {"content": content[:50]})

        return self.get_comment(comment_id)

    def get_comment(self, comment_id: str) -> Optional[ArticleComment]:
        """获取评论"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM article_comments WHERE id = ?",
            (comment_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return ArticleComment(
            id=row["id"],
            article_id=row["article_id"],
            team_id=row["team_id"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            content=row["content"],
            created_at=row["created_at"],
            parent_id=row["parent_id"]
        )

    def list_article_comments(self, article_id: str, team_id: str) -> List[ArticleComment]:
        """获取文章的所有评论"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """SELECT * FROM article_comments
               WHERE article_id = ? AND team_id = ?
               ORDER BY created_at""",
            (article_id, team_id)
        )
        rows = cursor.fetchall()
        conn.close()

        comments = []
        for row in rows:
            comments.append(ArticleComment(
                id=row["id"],
                article_id=row["article_id"],
                team_id=row["team_id"],
                user_id=row["user_id"],
                user_name=row["user_name"],
                content=row["content"],
                created_at=row["created_at"],
                parent_id=row["parent_id"]
            ))
        return comments

    # ========== 活动日志 ==========

    def _log_activity(self, team_id: str, user_id: str, user_name: str,
                     action: str, target_type: str, target_id: str,
                     details: Dict):
        """记录活动日志"""
        activity_id = hashlib.sha256(
            f"{team_id}{action}{datetime.now()}".encode()
        ).hexdigest()[:16]

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO team_activities
            (id, team_id, user_id, user_name, action, target_type, target_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (activity_id, team_id, user_id, user_name, action, target_type,
              target_id, json.dumps(details), datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_team_activities(self, team_id: str, limit: int = 50) -> List[TeamActivity]:
        """获取团队活动日志"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """SELECT * FROM team_activities
               WHERE team_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (team_id, limit)
        )
        rows = cursor.fetchall()
        conn.close()

        activities = []
        for row in rows:
            activities.append(TeamActivity(
                id=row["id"],
                team_id=row["team_id"],
                user_id=row["user_id"],
                user_name=row["user_name"],
                action=row["action"],
                target_type=row["target_type"],
                target_id=row["target_id"],
                details=json.loads(row["details"]),
                created_at=row["created_at"]
            ))
        return activities

    # ========== 统计信息 ==========

    def get_team_stats(self, team_id: str) -> Dict:
        """获取团队统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM team_members WHERE team_id = ?", (team_id,))
        member_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM shared_collections WHERE team_id = ?", (team_id,))
        collection_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM collection_items WHERE collection_id IN (SELECT id FROM shared_collections WHERE team_id = ?)",
            (team_id,)
        )
        collected_articles = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM article_comments WHERE team_id = ?",
            (team_id,)
        )
        comment_count = cursor.fetchone()[0]

        conn.close()

        return {
            "member_count": member_count,
            "collection_count": collection_count,
            "collected_articles": collected_articles,
            "comment_count": comment_count
        }


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='团队协作系统')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # 用户命令
    user_parser = subparsers.add_parser('user-create', help='创建用户')
    user_parser.add_argument('--email', required=True)
    user_parser.add_argument('--name', required=True)

    # 团队命令
    team_parser = subparsers.add_parser('team-create', help='创建团队')
    team_parser.add_argument('--name', required=True)
    team_parser.add_argument('--desc', default="")
    team_parser.add_argument('--owner', required=True)

    team_join = subparsers.add_parser('team-join', help='加入团队')
    team_join.add_argument('--code', required=True)
    team_join.add_argument('--user', required=True)

    team_members = subparsers.add_parser('team-members', help='列出成员')
    team_members.add_argument('--team', required=True)

    # 收藏夹命令
    coll_parser = subparsers.add_parser('collection-create', help='创建收藏夹')
    coll_parser.add_argument('--team', required=True)
    coll_parser.add_argument('--name', required=True)
    coll_parser.add_argument('--desc', default="")
    coll_parser.add_argument('--user', required=True)

    # 统计命令
    stats_parser = subparsers.add_parser('stats', help='团队统计')
    stats_parser.add_argument('--team', required=True)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    team_system = TeamSystem()

    if args.command == 'user-create':
        user = team_system.create_user(args.email, args.name)
        print(f"用户创建成功: {user.id}")
        print(f"API Key: {user.api_key}")

    elif args.command == 'team-create':
        team = team_system.create_team(args.name, args.desc, args.owner)
        print(f"团队创建成功: {team.id}")
        print(f"邀请码: {team.invite_code}")

    elif args.command == 'team-join':
        member = team_system.join_team(args.code, args.user)
        if member:
            print(f"成功加入团队，角色: {member.role}")
        else:
            print("加入失败，邀请码无效")

    elif args.command == 'team-members':
        members = team_system.list_team_members(args.team)
        print(f"\n团队成员 ({len(members)}人):\n")
        for m in members:
            role_icon = "👑" if m['role'] == 'admin' else "👤" if m['role'] == 'member' else "👁"
            print(f"{role_icon} {m['name']} ({m['email']}) - {m['role']}")

    elif args.command == 'collection-create':
        coll = team_system.create_collection(args.team, args.name, args.desc, args.user)
        print(f"收藏夹创建成功: {coll.id}")

    elif args.command == 'stats':
        stats = team_system.get_team_stats(args.team)
        print(f"\n团队统计:\n")
        print(f"成员数: {stats['member_count']}")
        print(f"收藏夹: {stats['collection_count']}")
        print(f"收藏文章: {stats['collected_articles']}")
        print(f"评论数: {stats['comment_count']}")


if __name__ == '__main__':
    main()
