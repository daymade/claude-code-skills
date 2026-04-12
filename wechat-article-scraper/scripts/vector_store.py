#!/usr/bin/env python3
"""
向量存储引擎 - 基于sqlite-vss的语义向量存储

功能：
- 文本向量化 (支持Ollama/OpenAI本地和API)
- 向量存储与检索 (sqlite-vss)
- 相似度搜索 (余弦相似度)
- 内容聚类支持

依赖：
- sqlite-vss (SQLite Vector Similarity Search)
- 或 faiss-cpu (备选方案)

作者: Claude Code
版本: 1.0.0
"""

import os
import json
import sqlite3
import logging
import hashlib
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger('vector-store')


@dataclass
class VectorDocument:
    """向量文档"""
    id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None


@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    content: str
    metadata: Dict[str, Any]
    score: float  # 相似度分数


class EmbeddingProvider:
    """Embedding提供商"""

    def __init__(self, provider: str = "auto"):
        self.provider = provider
        self.dimension = 768  # 默认维度
        self._ollama_available = None
        self._openai_available = None

    def _check_ollama(self) -> bool:
        """检查Ollama是否可用"""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            self._ollama_available = response.status_code == 200
            if self._ollama_available:
                self.dimension = 768  # nomic-embed-text 维度
        except:
            self._ollama_available = False

        return self._ollama_available

    def _check_openai(self) -> bool:
        """检查OpenAI是否可用"""
        if self._openai_available is not None:
            return self._openai_available

        self._openai_available = bool(os.getenv("OPENAI_API_KEY"))
        if self._openai_available:
            self.dimension = 1536  # text-embedding-ada-002 维度

        return self._openai_available

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        获取文本的embedding向量

        Args:
            text: 输入文本

        Returns:
            embedding向量
        """
        # 优先使用Ollama本地模型
        if self._check_ollama():
            return self._ollama_embedding(text)

        # 其次使用OpenAI API
        if self._check_openai():
            return self._openai_embedding(text)

        # 使用简单词袋模型作为备选
        return self._fallback_embedding(text)

    def _ollama_embedding(self, text: str) -> Optional[List[float]]:
        """使用Ollama获取embedding"""
        try:
            import requests

            response = requests.post(
                "http://localhost:11434/api/embeddings",
                json={
                    "model": "nomic-embed-text:latest",
                    "prompt": text[:8192]  # 限制长度
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("embedding")

            return None

        except Exception as e:
            logger.warning(f"Ollama embedding失败: {e}")
            return None

    def _openai_embedding(self, text: str) -> Optional[List[float]]:
        """使用OpenAI API获取embedding"""
        try:
            import openai

            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.embeddings.create(
                model="text-embedding-ada-002",
                input=text[:8192]
            )

            return response.data[0].embedding

        except Exception as e:
            logger.warning(f"OpenAI embedding失败: {e}")
            return None

    def _fallback_embedding(self, text: str) -> List[float]:
        """
        备选embedding方案 - 基于TF-IDF的简化版
        生成固定维度的稀疏向量
        """
        # 简单的词哈希embedding
        words = text.lower().split()
        embedding = [0.0] * self.dimension

        for word in words:
            # 使用hash将词映射到向量位置
            idx = hash(word) % self.dimension
            embedding[idx] += 1.0

        # 归一化
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = [x / norm for x in embedding]

        return embedding


class VectorStore:
    """向量存储引擎"""

    def __init__(self, db_path: str = None, use_vss: bool = True):
        if db_path is None:
            db_path = str(Path.home() / ".wechat-scraper" / "vectors.db")

        self.db_path = db_path
        self.use_vss = use_vss
        self.embedding_provider = EmbeddingProvider()
        self.dimension = self.embedding_provider.dimension

        # 初始化数据库
        self._init_db()

    def _init_db(self):
        """初始化向量数据库"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        # 创建主表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                content TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 如果使用sqlite-vss，创建虚拟表
        if self.use_vss:
            try:
                self.conn.execute("SELECT load_extension('vss0')")
                self.conn.execute(f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS vss_documents USING vss0(
                        embedding({self.dimension})
                    )
                """)
                self.has_vss = True
            except Exception as e:
                logger.warning(f"sqlite-vss不可用: {e}，使用备选方案")
                self.has_vss = False
                self._init_fallback_table()
        else:
            self.has_vss = False
            self._init_fallback_table()

        self.conn.commit()

    def _init_fallback_table(self):
        """初始化备选存储表"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS document_embeddings (
                id TEXT PRIMARY KEY,
                embedding BLOB,
                FOREIGN KEY (id) REFERENCES documents(id)
            )
        """)
        self.conn.commit()

    def add_document(self, doc_id: str, content: str, metadata: Dict = None) -> bool:
        """
        添加文档到向量存储

        Args:
            doc_id: 文档ID
            content: 文档内容
            metadata: 元数据

        Returns:
            是否成功
        """
        try:
            # 生成embedding
            embedding = self.embedding_provider.get_embedding(content)
            if not embedding:
                return False

            # 存储文档
            self.conn.execute(
                "INSERT OR REPLACE INTO documents (id, content, metadata) VALUES (?, ?, ?)",
                (doc_id, content, json.dumps(metadata or {}))
            )

            # 存储向量
            if self.has_vss:
                # 使用sqlite-vss
                self.conn.execute(
                    "INSERT OR REPLACE INTO vss_documents (rowid, embedding) VALUES (?, ?)",
                    (doc_id, json.dumps(embedding))
                )
            else:
                # 使用备选方案
                embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
                self.conn.execute(
                    "INSERT OR REPLACE INTO document_embeddings (id, embedding) VALUES (?, ?)",
                    (doc_id, embedding_blob)
                )

            self.conn.commit()
            return True

        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            return False

    def search(self, query: str, top_k: int = 10, filter_metadata: Dict = None) -> List[SearchResult]:
        """
        语义搜索

        Args:
            query: 搜索查询
            top_k: 返回结果数量
            filter_metadata: 元数据过滤条件

        Returns:
            搜索结果列表
        """
        # 获取查询的embedding
        query_embedding = self.embedding_provider.get_embedding(query)
        if not query_embedding:
            return []

        if self.has_vss:
            return self._vss_search(query_embedding, top_k, filter_metadata)
        else:
            return self._fallback_search(query_embedding, top_k, filter_metadata)

    def _vss_search(self, query_embedding: List[float], top_k: int,
                    filter_metadata: Dict = None) -> List[SearchResult]:
        """使用sqlite-vss搜索"""
        try:
            # 构建查询
            query_json = json.dumps(query_embedding)

            cursor = self.conn.execute("""
                SELECT d.id, d.content, d.metadata, v.distance
                FROM vss_documents v
                JOIN documents d ON v.rowid = d.id
                ORDER BY v.distance
                LIMIT ?
            """, (top_k,))

            results = []
            for row in cursor.fetchall():
                metadata = json.loads(row["metadata"])

                # 元数据过滤
                if filter_metadata:
                    if not all(metadata.get(k) == v for k, v in filter_metadata.items()):
                        continue

                # vss返回的是距离，转换为相似度
                distance = row["distance"]
                similarity = 1.0 / (1.0 + distance)

                results.append(SearchResult(
                    id=row["id"],
                    content=row["content"],
                    metadata=metadata,
                    score=similarity
                ))

            return results

        except Exception as e:
            logger.error(f"VSS搜索失败: {e}")
            return []

    def _fallback_search(self, query_embedding: List[float], top_k: int,
                         filter_metadata: Dict = None) -> List[SearchResult]:
        """备选搜索方案 - 使用numpy计算余弦相似度"""
        try:
            query_vec = np.array(query_embedding, dtype=np.float32)

            # 获取所有文档向量
            cursor = self.conn.execute("""
                SELECT d.id, d.content, d.metadata, e.embedding
                FROM documents d
                JOIN document_embeddings e ON d.id = e.id
            """)

            similarities = []
            for row in cursor.fetchall():
                metadata = json.loads(row["metadata"])

                # 元数据过滤
                if filter_metadata:
                    if not all(metadata.get(k) == v for k, v in filter_metadata.items()):
                        continue

                # 计算余弦相似度
                doc_vec = np.frombuffer(row["embedding"], dtype=np.float32)
                similarity = np.dot(query_vec, doc_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec))

                similarities.append((
                    row["id"],
                    row["content"],
                    metadata,
                    float(similarity)
                ))

            # 排序并返回top_k
            similarities.sort(key=lambda x: x[3], reverse=True)

            return [
                SearchResult(id=item[0], content=item[1], metadata=item[2], score=item[3])
                for item in similarities[:top_k]
            ]

        except Exception as e:
            logger.error(f"备选搜索失败: {e}")
            return []

    def find_similar(self, doc_id: str, top_k: int = 5) -> List[SearchResult]:
        """
        查找相似文档

        Args:
            doc_id: 参考文档ID
            top_k: 返回数量

        Returns:
            相似文档列表
        """
        # 获取参考文档内容
        cursor = self.conn.execute(
            "SELECT content FROM documents WHERE id = ?",
            (doc_id,)
        )
        row = cursor.fetchone()

        if not row:
            return []

        # 使用文档内容作为查询
        return self.search(row["content"], top_k=top_k + 1)

    def get_document(self, doc_id: str) -> Optional[VectorDocument]:
        """获取单个文档"""
        cursor = self.conn.execute(
            "SELECT * FROM documents WHERE id = ?",
            (doc_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return VectorDocument(
            id=row["id"],
            content=row["content"],
            metadata=json.loads(row["metadata"])
        )

    def delete_document(self, doc_id: str) -> bool:
        """删除文档"""
        try:
            self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            if self.has_vss:
                self.conn.execute("DELETE FROM vss_documents WHERE rowid = ?", (doc_id,))
            else:
                self.conn.execute("DELETE FROM document_embeddings WHERE id = ?", (doc_id,))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return False

    def get_stats(self) -> Dict:
        """获取统计信息"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM documents")
        total = cursor.fetchone()[0]

        return {
            "total_documents": total,
            "dimension": self.dimension,
            "has_vss": self.has_vss,
            "embedding_provider": self.embedding_provider.provider
        }

    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description='向量存储引擎')
    parser.add_argument('--db', help='数据库路径')

    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # add 命令
    add_parser = subparsers.add_parser('add', help='添加文档')
    add_parser.add_argument('id', help='文档ID')
    add_parser.add_argument('content', help='文档内容')

    # search 命令
    search_parser = subparsers.add_parser('search', help='搜索文档')
    search_parser.add_argument('query', help='搜索查询')
    search_parser.add_argument('-k', '--top-k', type=int, default=10, help='返回数量')

    # similar 命令
    similar_parser = subparsers.add_parser('similar', help='查找相似文档')
    similar_parser.add_argument('id', help='参考文档ID')
    similar_parser.add_argument('-k', '--top-k', type=int, default=5, help='返回数量')

    # stats 命令
    subparsers.add_parser('stats', help='统计信息')

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(level=logging.INFO)

    if not args.command:
        parser.print_help()
        return

    store = VectorStore(args.db)

    if args.command == 'add':
        success = store.add_document(args.id, args.content)
        print(f"{'✓' if success else '✗'} 添加文档: {args.id}")

    elif args.command == 'search':
        results = store.search(args.query, top_k=args.top_k)
        print(f"\n搜索: {args.query}")
        print(f"找到 {len(results)} 个结果:\n")
        for r in results:
            print(f"[{r.score:.3f}] {r.id}: {r.content[:100]}...")
            print()

    elif args.command == 'similar':
        results = store.find_similar(args.id, top_k=args.top_k)
        print(f"\n与 {args.id} 相似的文档:")
        for r in results:
            if r.id != args.id:
                print(f"[{r.score:.3f}] {r.id}: {r.content[:100]}...")

    elif args.command == 'stats':
        stats = store.get_stats()
        print(json.dumps(stats, indent=2))

    store.close()


if __name__ == '__main__':
    main()
