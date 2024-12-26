# vectordb/manager.py
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime

from ....core.runnable.vectordb import VectorDB
from ....io import ConfigStoreProtocol, FileConfigStore
from ...users import UsersManager
from ...result import Result
from .models import VectorDBConfig
from .factory import BaseVectorDBFactory, DefaultVectorDBFactory

from ....config import get_env
__VECTOR_CONFIG_FILENAME__ = "vectordb.json"

class VectorDBManager:
    def __init__(
        self,
        users_manager: UsersManager,
        db_factory: Optional[BaseVectorDBFactory] = None,
        storage: Optional[ConfigStoreProtocol] = None,
    ):
        """初始化向量库管理器"""
        self.users_manager = users_manager
        self._db_factory = db_factory or DefaultVectorDBFactory()

        if storage is None:
            storage = FileConfigStore(
                data_dir=Path(get_env("ILLUFLY_CONFIG_STORE_DIR")),
                filename=__VECTOR_CONFIG_FILENAME__,
                data_class=Dict[str, VectorDBConfig],
            )
        self._storage = storage
        self._db_instances: Dict[str, Dict[str, VectorDB]] = {}

    def load_db(self, user_id: str, db_name: str, config: VectorDBConfig) -> Result[VectorDB]:
        """加载向量库实例"""
        try:
            db = self._db_factory.create_db_instance(user_id, db_name, config)
            if not db:
                return Result.fail("加载数据库实例失败")
            
            if user_id not in self._db_instances:
                self._db_instances[user_id] = {}
            self._db_instances[user_id][db_name] = db
            return Result.ok(data=db)
        except Exception as e:
            return Result.fail(f"加载数据库实例失败: {e}")

    def unload_db(self, user_id: str, db_name: str) -> Result[None]:
        """卸载向量库实例"""
        try:
            if user_id in self._db_instances and db_name in self._db_instances[user_id]:
                del self._db_instances[user_id][db_name]
                if not self._db_instances[user_id]:
                    del self._db_instances[user_id]
            return Result.ok(message="数据库实例已卸载")
        except Exception as e:
            return Result.fail(f"卸载数据库实例失败: {e}")

    def create_db(
        self, 
        user_id: str, 
        db_name: str, 
        vdb_config: Dict[str, Any] = None,
        knowledge_config: Dict[str, Any] = None,
        embeddings_config: Dict[str, Any] = None
    ) -> Result[VectorDB]:
        """创建新的知识库
        
        Args:
            user_id: 用户ID
            db_name: 数据库名称
            vdb_config: 向量库配置，默认使用 FaissDB
            knowledge_config: 知识库配置，默认使用 LocalFileKnowledgeDB
            embeddings_config: 向量模型配置，默认使用 TextEmbeddings
        
        Returns:
            Result[VectorDB]: 创建结果
        """
        try:
            user_dbs = self._storage.get(owner_id=user_id) or {}
            
            if db_name in user_dbs:
                return Result.fail("数据库已存在")
                
            # 创建配置实例
            db_config = VectorDBConfig(
                db_name=db_name,
                vdb_config=vdb_config or {},
                knowledge_config=knowledge_config or {},
                embeddings_config=embeddings_config or {}
            )
            
            # 存储配置字典
            user_dbs[db_name] = db_config.model_dump()
            self._storage.set(user_dbs, owner_id=user_id)

            # 加载数据库实例
            result = self.load_db(user_id, db_name, db_config)
            if not result.success:
                return result

            return Result.ok(message="数据库创建成功", data=db_config.model_dump())
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

    def get_db_config(self, user_id: str, db_name: str) -> Result[VectorDBConfig]:
        """获取向量数据库配置"""
        try:
            user_dbs = self._storage.get(owner_id=user_id)
            if not user_dbs or db_name not in user_dbs:
                return Result.fail("数据库不存在")
            
            # 从存储的字典创建配置实例
            config = VectorDBConfig.model_validate(user_dbs[db_name])
            return Result.ok(data=config, message="成功获取数据库配置")
        except Exception as e:
            return Result.fail(f"获取数据库配置失败: {e}")

    def get_db_instance(self, user_id: str, db_name: str) -> Result[VectorDB]:
        """获取向量数据库实例"""
        try:
            # 检查缓存
            if user_id in self._db_instances and db_name in self._db_instances[user_id]:
                return Result.ok(
                    data=self._db_instances[user_id][db_name],
                    message="成功获取数据库实例"
                )

            # 获取配置
            config_result = self.get_db_config(user_id, db_name)
            if not config_result.success:
                return Result.fail(config_result.error)

            # 加载数据库实例
            result = self.load_db(user_id, db_name, config_result.data)
            if not result.success:
                return result

            return Result.ok(data=result.data, message="成功获取数据库实例")
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

            # 卸载数据库实例
            self.unload_db(user_id, db_name)

            return Result.ok(message="数据库删除成功")
        except Exception as e:
            return Result.fail(f"删除数据库失败: {e}")

    def update_db_config(self, user_id: str, db_name: str, updates: Dict[str, Any]) -> Result[None]:
        """更新知识库配置"""
        try:
            user_dbs = self._storage.get(owner_id=user_id)
            if not user_dbs or db_name not in user_dbs:
                return Result.fail("数据库不存在")
            
            # 获取当前配置并更新
            current_config = VectorDBConfig.model_validate(user_dbs[db_name])
            
            # 更新配置
            for key, value in updates.items():
                if hasattr(current_config, key):
                    setattr(current_config, key, value)
            
            # 保存更新后的配置
            user_dbs[db_name] = current_config.model_dump()
            self._storage.set(user_dbs, owner_id=user_id)
            
            # 重新加载数据库实例
            self.unload_db(user_id, db_name)
            result = self.load_db(user_id, db_name, current_config)
            if not result.success:
                return result
            
            return Result.ok(message="配置更新成功", data=current_config.model_dump())
        except Exception as e:
            return Result.fail(f"更新配置失败: {e}")
