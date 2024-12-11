# vectordb/manager.py
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
from ..common import StorageProtocol, FileStorage
from .models import VectorDBConfig
from ...core.runnable.vectordb import VectorDB

class VectorDBManager:
    def __init__(
        self,
        storage: Optional[StorageProtocol[Dict[str, VectorDBConfig]]] = None,
        base_path: str = "./__users__"
    ):
        """初始化向量库管理器
        Args:
            storage: 存储实现，用于保存向量库配置信息
            base_path: 用户数据根目录
        """
        self.base_path = base_path
        if storage is None:
            storage = FileStorage[Dict[str, VectorDBConfig]](
                data_dir=base_path,
                filename="vectordb.json",
                serializer=lambda dbs: {
                    name: db_config.to_dict()
                    for name, db_config in dbs.items()
                },
                deserializer=lambda data: {
                    name: VectorDBConfig.from_dict(db_data)
                    for name, db_data in data.items()
                },
                use_owner_subdirs=True
            )
        self._storage = storage
        # 向量数据库实例缓存
        self._db_instances: Dict[str, Dict[str, VectorDB]] = {}  # username -> {db_name -> instance}

    def _get_user_path(self, username: str) -> str:
        """获取用户数据目录路径"""
        return str(Path(self.base_path) / username)

    def _get_user_storage(self, username: str) -> StorageProtocol:
        """获取用户特定的存储实例"""
        user_storage = self._storage.clone()
        user_storage.data_dir = self._get_user_path(username)
        user_storage.filename = "vectordb.json"
        return user_storage

    def create_db(self, username: str, db_name: str, db_config: Dict[str, Any], requester: str) -> bool:
        """创建新的知识库
        Args:
            username: 用户名
            db_name: 数据库名称
            db_config: 数据库配置
            requester: 请求者用户名
        Returns:
            是否创建成功
        """
        if requester != username:  # 权限检查
            return False

        try:
            # 保存配置
            storage = self._get_user_storage(username)
            user_dbs = storage.get("vectordbs", owner=username) or {}
            
            if db_name in user_dbs:
                return False
                
            config = VectorDBConfig(
                name=db_name,
                **db_config
            )
            user_dbs[db_name] = config
            storage.set("vectordbs", user_dbs, owner=username)

            # 创建数据库实例
            db = self._create_db_instance(username, db_name, config)
            if not db:
                return False

            # 更新缓存
            if username not in self._db_instances:
                self._db_instances[username] = {}
            self._db_instances[username][db_name] = db
            return True
        except Exception as e:
            print(f"Error creating database: {e}")
            return False

    def list_dbs(self, username: str, requester: str) -> List[str]:
        """列出用户的所有知识库
        Args:
            username: 用户名
            requester: 请求者用户名
        Returns:
            知识库名称列表
        """
        if requester != username:  # 权限检查
            return []

        storage = self._get_user_storage(username)
        user_dbs = storage.get("vectordbs", owner=username)
        
        if not user_dbs:
            return []
            
        return list(user_dbs.keys())

    def get_db(self, username: str, db_name: str, requester: str) -> Optional[VectorDB]:
        """获取向量数据库实例"""
        if requester != username:  # 权限检查
            return None

        # 检查缓存
        if username in self._db_instances and db_name in self._db_instances[username]:
            return self._db_instances[username][db_name]

        # 获取配置
        storage = self._get_user_storage(username)
        user_dbs = storage.get("vectordbs", owner=username)
        if not user_dbs or db_name not in user_dbs:
            return None
            
        config = user_dbs[db_name]

        try:
            # 创建实例
            if username not in self._db_instances:
                self._db_instances[username] = {}
                
            db = self._create_db_instance(username, db_name, config)
            if db:
                self._db_instances[username][db_name] = db
                return db
        except Exception as e:
            print(f"Error loading vector database: {e}")
        
        return None

    def remove_db(self, username: str, db_name: str, requester: str) -> bool:
        """删除知识库"""
        if requester != username:  # 权限检查
            return False

        try:
            # 从配置中移除
            storage = self._get_user_storage(username)
            user_dbs = storage.get("vectordbs", owner=username)
            if user_dbs and db_name in user_dbs:
                del user_dbs[db_name]
                if user_dbs:
                    storage.set("vectordbs", user_dbs, owner=username)
                else:
                    storage.delete("vectordbs", owner=username)

            # 从缓存中移除
            if username in self._db_instances and db_name in self._db_instances[username]:
                del self._db_instances[username][db_name]
                if not self._db_instances[username]:
                    del self._db_instances[username]

            # 删除文件系统中的数据
            db_path = Path(self._get_user_path(username)) / "store" / db_name
            if db_path.exists():
                import shutil
                shutil.rmtree(db_path)
            return True
        except Exception as e:
            print(f"Error removing database: {e}")
            return False

    def _create_db_instance(self, username: str, db_name: str, config: VectorDBConfig) -> Optional[VectorDB]:
        """创建向量库实例"""
        # TODO: 根据配置创建相应类型的向量库实例
        pass