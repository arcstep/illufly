# vectordb/manager.py
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime

from ....core.runnable.vectordb import VectorDB
from ....io import ConfigStoreProtocol, FileConfigStore
from ...users import UsersManager
from ...result import Result
from .models import VectorDBConfig

from ....config import get_env
__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")
__VECTOR_CONFIG_FILENAME__ = "vectordb.json"

class VectorDBManager:
    def __init__(
        self,
        users_manager: UsersManager,
        storage: Optional[ConfigStoreProtocol] = None,
        config_store_path: str = None
    ):
        """初始化向量库管理器
        Args:
            storage: 存储实现，用于保存向量库配置信息
        """
        self.users_manager = users_manager

        if storage is None:
            storage = FileConfigStore(
                data_dir=Path(config_store_path or __USERS_PATH__),
                filename=__VECTOR_CONFIG_FILENAME__,
                data_class=Dict[str, VectorDBConfig],
            )
        self._storage = storage
        # 向量数据库实例缓存
        self._db_instances: Dict[str, Dict[str, VectorDB]] = {}  # user_id -> {db_name -> instance}

    def create_db(self, user_id: str, db_name: str, db_config: Dict[str, Any]={}) -> Result[VectorDB]:
        """创建新的知识库"""
        try:
            # 获取用户的数据库配置
            user_dbs = self._storage.get(owner_id=user_id) or {}
            
            if db_name in user_dbs:
                return Result.fail("数据库已存在")
                
            config = VectorDBConfig(
                name=db_name,
                **db_config
            )
            user_dbs[db_name] = config
            self._storage.set(user_dbs, owner_id=user_id)

            # 创建数据库实例
            db = self.create_db_instance(user_id, db_name, config)
            if not db:
                return Result.fail("创建数据库实例失败")

            # 更新缓存
            if user_id not in self._db_instances:
                self._db_instances[user_id] = {}
            self._db_instances[user_id][db_name] = db
            return Result.ok(data=db, message="数据库创建成功")

        except Exception as e:
            return Result.fail(f"创建数据库时发生错误: {e}")

    def list_dbs(self, user_id: str) -> Result[List[str]]:
        """列出用户的所有知识库"""
        try:
            user_dbs = self._storage.get(owner_id=user_id)
            if not user_dbs:
                return Result.ok(data=[])
            
            return Result.ok(data=list(user_dbs.keys()))
        except Exception as e:
            return Result.fail(f"获取数据库列表失败: {e}")

    def get_db(self, user_id: str, db_name: str) -> Result[VectorDB]:
        """获取向量数据库实例"""
        try:
            # 检查缓存
            if user_id in self._db_instances and db_name in self._db_instances[user_id]:
                return Result.ok(
                    data=self._db_instances[user_id][db_name],
                    message="成功获取数据库实例"
                )

            # 获取配置
            user_dbs = self._storage.get(owner_id=user_id)
            if not user_dbs or db_name not in user_dbs:
                return Result.fail("数据库不存在")
            
            config = user_dbs[db_name]

            # 创建实例
            if user_id not in self._db_instances:
                self._db_instances[user_id] = {}
            
            db = self.create_db_instance(user_id, db_name, config)
            if db:
                self._db_instances[user_id][db_name] = db
                return Result.ok(data=db, message="成功获取数据库实例")
            return Result.fail("创建数据库实例失败")
        except Exception as e:
            return Result.fail(f"获取数据库实例失败: {e}")

    def remove_db(self, user_id: str, db_name: str) -> Result[None]:
        """删除知识库"""
        try:
            # 从配置中移除
            user_dbs = self._storage.get(owner_id=user_id)
            if user_dbs and db_name in user_dbs:
                del user_dbs[db_name]
                if user_dbs:
                    self._storage.set(user_dbs, owner_id=user_id)
                else:
                    self._storage.delete(owner_id=user_id)

            # 从缓存中移除
            if user_id in self._db_instances and db_name in self._db_instances[user_id]:
                del self._db_instances[user_id][db_name]
                if not self._db_instances[user_id]:
                    del self._db_instances[user_id]

            return Result.ok(message="数据库删除成功")
        except Exception as e:
            return Result.fail(f"删除数据库失败: {e}")

    def create_db_instance(self, user_id: str, db_name: str, config: VectorDBConfig) -> Optional[VectorDB]:
        """创建向量库实例"""
        from ....community.dashscope import TextEmbeddings
        from ....community.faiss import FaissDB
        from ....io import LocalFileKnowledgeDB

        # 创建向量库实例
        if config.db_type == "faiss":
            knowledge_path = Path(__USERS_PATH__) / "store" / db_name
            return FaissDB(
                name=db_name,
                top_k=config.top_k,
                embeddings=TextEmbeddings(),
                knowledge=LocalFileKnowledgeDB(knowledge_path)
            )
        # elif config.db_type == "milvus":
        #     return MilvusDB(name=db_name, embeddings=TextEmbeddings(), knowledge=LocalFileKnowledgeDB(db_name))
        else:
            raise ValueError(f"Unsupported database type: {config.db_type}")

    def update_db_config(self, user_id: str, db_name: str, updates: Dict[str, Any]) -> Result[None]:
        """更新知识库配置
        
        Args:
            user_id: 用户ID
            db_name: 知识库名称
            updates: 要更新的配置项
        """
        try:
            # 获取现有配置
            user_dbs = self._storage.get(owner_id=user_id)
            if not user_dbs or db_name not in user_dbs:
                return Result.fail("数据库不存在")
            
            config = user_dbs[db_name]
            
            # 更新配置
            for key, value in updates.items():
                setattr(config, key, value)
            
            # 保存更新后的配置
            user_dbs[db_name] = config
            self._storage.set(user_dbs, owner_id=user_id)
            
            # 重新创建实例
            if user_id in self._db_instances and db_name in self._db_instances[user_id]:
                del self._db_instances[user_id][db_name]
                db = self.create_db_instance(user_id, db_name, config)
                if db:
                    self._db_instances[user_id][db_name] = db
            
            return Result.ok(message="配置更新成功")
        except Exception as e:
            return Result.fail(f"更新配置失败: {e}")
