# vectordb/manager.py
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
from ...config import get_env
from ...core.runnable.vectordb import VectorDB
from ..common import StorageProtocol, FileStorage
from .models import VectorDBConfig

__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")

class VectorDBManager:
    def __init__(
        self,
        storage: Optional[StorageProtocol[Dict[str, VectorDBConfig]]] = None
    ):
        """初始化向量库管理器
        Args:
            storage: 存储实现，用于保存向量库配置信息
        """
        if storage is None:
            storage = FileStorage[Dict[str, VectorDBConfig]](
                data_dir=Path(__USERS_PATH__),
                filename="vectordb.json",
                serializer=lambda dbs: {
                    name: db_config.to_dict()
                    for name, db_config in dbs.items()
                },
                deserializer=lambda data: {
                    name: VectorDBConfig.from_dict(db_data)
                    for name, db_data in data.items()
                },
                use_id_subdirs=True
            )
        self._storage = storage
        # 向量数据库实例缓存
        self._db_instances: Dict[str, Dict[str, VectorDB]] = {}  # user_id -> {db_name -> instance}

    def create_db(self, user_id: str, db_name: str, db_config: Dict[str, Any], requester_id: str) -> bool:
        """创建新的知识库
        Args:
            user_id: 用户ID
            db_name: 数据库名称
            db_config: 数据库配置
            requester_id: 请求者用户ID
        Returns:
            是否创建成功
        """
        if requester_id != user_id:  # 权限检查
            return False

        try:
            # 获取用户的数据库配置
            user_dbs = self._storage.get("vectordbs", owner_id=user_id) or {}
            
            if db_name in user_dbs:
                return False
                
            config = VectorDBConfig(
                name=db_name,
                **db_config
            )
            user_dbs[db_name] = config
            self._storage.set("vectordbs", user_dbs, owner_id=user_id)

            # 创建数据库实例
            db = self.create_db_instance(user_id, db_name, config)
            if not db:
                return False

            # 更新缓存
            if user_id not in self._db_instances:
                self._db_instances[user_id] = {}
            self._db_instances[user_id][db_name] = db
            return True
        except Exception as e:
            print(f"Error creating database: {e}")
            return False

    def list_dbs(self, user_id: str, requester_id: str) -> List[str]:
        """列出用户的所有知识库
        Args:
            user_id: 用户ID
            requester_id: 请求者用户ID
        Returns:
            知识库名称列表
        """
        if requester_id != user_id:  # 权限检查
            return []

        user_dbs = self._storage.get("vectordbs", owner_id=user_id)
        if not user_dbs:
            return []
            
        return list(user_dbs.keys())

    def get_db(self, user_id: str, db_name: str, requester_id: str) -> Optional[VectorDB]:
        """获取向量数据库实例"""
        if requester_id != user_id:  # 权限检查
            return None

        # 检查缓存
        if user_id in self._db_instances and db_name in self._db_instances[user_id]:
            return self._db_instances[user_id][db_name]

        # 获取配置
        user_dbs = self._storage.get("vectordbs", owner_id=user_id)
        if not user_dbs or db_name not in user_dbs:
            return None
            
        config = user_dbs[db_name]

        try:
            # 创建实例
            if user_id not in self._db_instances:
                self._db_instances[user_id] = {}
                
            db = self.create_db_instance(user_id, db_name, config)
            if db:
                self._db_instances[user_id][db_name] = db
                return db
        except Exception as e:
            print(f"Error loading vector database: {e}")
        
        return None

    def remove_db(self, user_id: str, db_name: str, requester_id: str) -> bool:
        """删除知识库"""
        if requester_id != user_id:  # 权限检查
            return False

        try:
            # 从配置中移除
            user_dbs = self._storage.get("vectordbs", owner_id=user_id)
            if user_dbs and db_name in user_dbs:
                del user_dbs[db_name]
                if user_dbs:
                    self._storage.set("vectordbs", user_dbs, owner_id=user_id)
                else:
                    self._storage.delete("vectordbs", owner_id=user_id)

            # 从缓存中移除
            if user_id in self._db_instances and db_name in self._db_instances[user_id]:
                del self._db_instances[user_id][db_name]
                if not self._db_instances[user_id]:
                    del self._db_instances[user_id]

            return True
        except Exception as e:
            print(f"Error removing database: {e}")
            return False

    def create_db_instance(self, user_id: str, db_name: str, config: VectorDBConfig) -> Optional[VectorDB]:
        """创建向量库实例"""
        from ...community.dashscope import TextEmbeddings
        from ...community.faiss import FaissDB
        from ...io import LocalFileKnowledgeDB

        # 创建向量库实例
        if config.db_type == "faiss":
            knowledge_path = Path(__USERS_PATH__) / "store" / db_name
            return FaissDB(name=db_name, embeddings=TextEmbeddings(), knowledge=LocalFileKnowledgeDB(db_name))
        # elif config.db_type == "milvus":
        #     return MilvusDB(name=db_name, embeddings=TextEmbeddings(), knowledge=LocalFileKnowledgeDB(db_name))
        else:
            raise ValueError(f"Unsupported database type: {config.db_type}")
