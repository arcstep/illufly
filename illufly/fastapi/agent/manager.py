from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
from .models import AgentConfig
from .factory import AgentFactory
from ..common import StorageProtocol, FileStorage
from ...types import VectorDB
from ..vectordb import VectorDBManager

class AgentManager:
    def __init__(
        self,
        storage: Optional[StorageProtocol[Dict[str, AgentConfig]]] = None,
        vectordb_manager: Optional[VectorDBManager] = None,
        base_path: str = "./__users__"
    ):
        """初始化代理管理器"""
        self.base_path = base_path
        if storage is None:
            storage = FileStorage[Dict[str, AgentConfig]](
                data_dir=base_path,
                filename="agent.json",
                serializer=lambda agents: {
                    name: agent_config.to_dict()
                    for name, agent_config in agents.items()
                },
                deserializer=lambda data: {
                    name: AgentConfig.from_dict(agent_data)
                    for name, agent_data in data.items()
                },
                use_owner_subdirs=True
            )
        self._storage = storage
        
        # 使用向量库管理器
        self.vectordb_manager = vectordb_manager or VectorDBManager(base_path=base_path)

    def _get_user_path(self, username: str) -> str:
        """获取用户数据目录路径"""
        return str(Path(self.base_path) / username)

    def _get_user_storage(self, username: str) -> StorageProtocol:
        """获取用户特定的存储实例"""
        user_storage = self._storage.clone()
        user_storage.data_dir = self._get_user_path(username)
        user_storage.filename = "agent.json"
        return user_storage

    def create_db(self, username: str, db_name: str, requester: str) -> bool:
        """创建新的知识库
        Args:
            username: 用户名
            db_name: 数据库名称
            requester: 请求者用户名
        Returns:
            是否创建成功
        """
        if requester != username:  # 权限检查
            return False

        try:
            # 创建数据库
            db = AgentFactory.create_db(username, db_name, self._get_user_path(username))
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

        if username not in self._db_instances:
            self.create_db(username, default_db, username)

        # 如果已经有缓存的实例，直接返回缓存的键
        if username in self._db_instances:
            return list(self._db_instances[username].keys())

        # 否则扫描目录
        try:
            return AgentFactory.list_dbs(username, self._get_user_path(username))
        except Exception as e:
            print(f"Error listing databases: {e}")
            return []

    def create_agent(
        self,
        username: str,
        agent_type: str,
        agent_name: str,
        vectordb_names: List[str],
        requester: str,
        **kwargs
    ) -> bool:
        """创建代理"""
        if requester != username:
            return False

        # 验证向量库是否存在
        for db_name in vectordb_names:
            if not self.vectordb_manager.get_db(username, db_name, username):
                return False

        # 创建代理...
        storage = self._get_user_storage(username)
        user_agents = storage.get("agents", owner=username) or {}
        
        try:
            config, _ = AgentFactory.create_agent(
                username=username,
                agent_type=agent_type,
                agent_name=agent_name,
                base_path=self._get_user_path(username),
                vectordb_names=vectordb_names,
                vectordb_manager=self.vectordb_manager,  # 传入向量库管理器
                **kwargs
            )
            user_agents[agent_name] = config
            storage.set("agents", user_agents, owner=username)
            return True
        except ValueError:
            return False

    def get_agent(self, username: str, agent_name: str, requester: str) -> Optional[Any]:
        """获取代理实例"""
        if requester != username:
            return None
            
        storage = self._get_user_storage(username)
        user_agents = storage.get("agents", owner=username)
        if not user_agents or agent_name not in user_agents:
            return None
            
        agent_config = user_agents[agent_name]
        
        # 只在需要时创建实例
        _, instance = AgentFactory.create_agent(
            username=username,
            agent_type=agent_config.agent_type,
            agent_name=agent_name,
            base_path=self._get_user_path(username),
            vectordb_names=agent_config.vectordb_names,
            description=agent_config.description,
            config=agent_config.config
        )
        
        # 更新最后使用时间
        agent_config.last_used = datetime.now()
        storage.set("agents", user_agents, owner=username)
        
        return instance

    def list_agents(self, username: str, requester: str) -> List[Dict[str, Any]]:
        """列出用户的所有代理"""
        if requester != username:  # 权限检查
            return []

        storage = self._get_user_storage(username)
        data = storage.get("agents", owner=username)
        
        if not data:
            return []
        
        return [
            agent_config.to_dict()
            for agent_config in data.values()
        ]

    def remove_agent(self, username: str, agent_name: str, requester: str) -> bool:
        """移除代理"""
        if requester != username:  # 权限检查
            return False
            
        storage = self._get_user_storage(username)
        user_agents = storage.get("agents", owner=username)
        if not user_agents or agent_name not in user_agents:
            return False
        
        agent_info = user_agents.pop(agent_name)
        if hasattr(agent_info.instance, 'cleanup'):
            agent_info.instance.cleanup()
        
        # 清理文件系统中的代理数据
        AgentFactory.cleanup_agent(username, agent_name, self._get_user_path(username))
        
        if user_agents:
            storage.set("agents", user_agents, owner=username)
        else:
            storage.delete("agents", owner=username)
        return True

    def update_agent_config(
        self, 
        username: str, 
        agent_name: str, 
        config_updates: Dict[str, Any],
        requester: str
    ) -> bool:
        """更新代理配置"""
        if requester != username:  # 权限检查
            return False
            
        storage = self._get_user_storage(username)
        user_agents = storage.get("agents", owner=username)
        if not user_agents or agent_name not in user_agents:
            return False
        
        agent_info = user_agents[agent_name]
        if hasattr(agent_info, 'config'):
            agent_info.config.update(config_updates)
        else:
            agent_info.config = config_updates
        
        if hasattr(agent_info.instance, 'reconfigure'):
            try:
                agent_info.instance.reconfigure(config_updates)
            except Exception:
                return False
        
        storage.set("agents", user_agents, owner=username)
        return True 

    def get_db(self, username: str, db_name: str, requester: str) -> Optional[VectorDB]:
        """获取向量数据库实例
        Args:
            username: 用户名
            db_name: 数据库名称
            requester: 请求者用户名
        Returns:
            VectorDB 实例或 None
        """
        if requester != username:  # 权限检查
            return None

        # 检查缓存
        if username in self._db_instances and db_name in self._db_instances[username]:
            return self._db_instances[username][db_name]

        # 检查数据库是否存在
        db_path = Path(self._get_user_path(username)) / "store" / db_name
        if not db_path.is_dir():
            return None

        try:
            # 初始化缓存字典
            if username not in self._db_instances:
                self._db_instances[username] = {}

            # 创建并缓存实例
            db = AgentFactory.create_db(username, db_name, self._get_user_path(username))
            if db:
                self._db_instances[username][db_name] = db
                return db
        except Exception as e:
            print(f"Error loading vector database: {e}")
        
        return None

    def remove_db(self, username: str, db_name: str, requester: str) -> bool:
        """删除知识库
        Args:
            username: 用户名
            db_name: 数据库名称
            requester: 请求者用户名
        Returns:
            是否删除成功
        """
        if requester != username:  # 权限检查
            return False

        try:
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