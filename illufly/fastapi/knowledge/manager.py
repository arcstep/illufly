"""
Knowledge Manager

This module provides functionality for managing VectorDB instances.
"""

from typing import Optional, Dict, List
from datetime import datetime
from pathlib import Path
from ...types import VectorDB
from ...rag import FaissDB  # 或其他具体的 VectorDB 实现
from .models import KnowledgeBase

class KnowledgeManager:
    """知识库管理器"""
    
    def __init__(self, base_path: str = "./__data__/knowledge"):
        self._base_path = Path(base_path)
        self._dbs: Dict[str, VectorDB] = {}  # name -> VectorDB 实例
        self._knowledge_bases: Dict[str, KnowledgeBase] = {}  # name -> KnowledgeBase 信息

    def create_db(
        self,
        name: str,
        owner: str,
        description: str = "",
        db_type: str = "faiss",
        is_shared: bool = False
    ) -> VectorDB:
        """创建新的向量数据库实例"""
        if name in self._dbs:
            raise ValueError(f"VectorDB with name '{name}' already exists")

        # 创建用户专属目录
        db_path = self._base_path / owner / name
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # 创建 VectorDB 实例
        if db_type == "faiss":
            db = FaissDB(str(db_path))
        else:
            raise ValueError(f"Unsupported VectorDB type: {db_type}")

        # 记录实例和元数据
        self._dbs[name] = db
        self._knowledge_bases[name] = KnowledgeBase(
            name=name,
            owner_id=owner,
            description=description,
            created_at=datetime.now(),
            is_shared=is_shared
        )

        return db

    def get_db(self, name: str) -> Optional[VectorDB]:
        """获取向量数据库实例"""
        return self._dbs.get(name)

    def get_db_by_owner(self, owner: str, name: str) -> Optional[VectorDB]:
        """通过所有者和名称获取向量数据库实例"""
        full_name = f"{owner}/{name}"
        return self.get_db(full_name)

    def list_dbs(self, owner: Optional[str] = None) -> List[KnowledgeBase]:
        """列出所有（或指定所有者的）知识库"""
        if owner:
            return [
                base for base in self._knowledge_bases.values()
                if base.owner_id == owner or base.is_shared
            ]
        return list(self._knowledge_bases.values())

    def delete_db(self, name: str) -> bool:
        """删除向量数据库���例"""
        if name in self._dbs:
            # 清理资源
            del self._dbs[name]
            del self._knowledge_bases[name]
            return True
        return False 