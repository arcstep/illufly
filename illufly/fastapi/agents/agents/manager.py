from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime

from ....types import VectorDB
from ....io import ConfigStoreProtocol, FileConfigStore
from ...users import UsersManager
from ...result import Result
from ..vectordb import VectorDBManager
from .models import AgentConfig
from .factory import BaseAgentFactory, DefaultAgentFactory

from ....config import get_env
__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")
__AGENT_CONFIG_FILENAME__ = "agent.json"

class AgentsManager:
    def __init__(
        self,
        users_manager: UsersManager,
        vectordb_manager: VectorDBManager,
        agent_factory: Optional[BaseAgentFactory] = None,
        storage: Optional[ConfigStoreProtocol] = None,
        config_store_path: str = None
    ):
        """初始化代理管理器"""
        self.users_manager = users_manager
        self.vectordb_manager = vectordb_manager

        if storage is None:
            storage = FileConfigStore(
                data_dir=Path(config_store_path or __USERS_PATH__),
                filename=__AGENT_CONFIG_FILENAME__,
                data_class=Dict[str, AgentConfig],
            )

        self._agent_factory = agent_factory or DefaultAgentFactory()   
        self._agent_instances: Dict[str, Dict[str, Any]] = {}  # user_id -> {agent_name -> instance}
        self._storage = storage

    def create_agent(
        self,
        user_id: str,
        agent_type: str,
        agent_name: str,
        vectordbs: List[str],
        **kwargs
    ) -> Result[AgentConfig]:
        """创建代理"""
        try:
            # 获取用户的代理配置
            user_agents = self._storage.get(owner_id=user_id) or {}
            
            if agent_name in user_agents:
                return Result.fail("代理已存在")

            # 验证向量库是否存在
            for db_name in vectordbs:
                db_result = self.vectordb_manager.get_db(user_id, db_name)
                if not db_result.success:
                    return Result.fail(f"向量库 '{db_name}' 不存在")

            config = self._agent_factory.create_agent_config(
                user_id=user_id,
                agent_type=agent_type,
                agent_name=agent_name,
                vectordbs=vectordbs,
                **kwargs
            )
            user_agents[agent_name] = config
            print(">>> 创建新的Agent配置", config)
            self._storage.set(user_agents, owner_id=user_id)
            return Result.ok(data=config, message="代理创建成功")

        except Exception as e:
            return Result.fail(f"创建代理失败: {str(e)}")

    def get_agent(self, user_id: str, agent_name: str) -> Result[Any]:
        """获取代理实例"""
        try:
            # 检查缓存
            if user_id in self._agent_instances and agent_name in self._agent_instances[user_id]:
                return Result.ok(
                    data=self._agent_instances[user_id][agent_name],
                    message="成功获取代理实例"
                )

            # 获取配置
            user_agents = self._storage.get(owner_id=user_id)
            if not user_agents or agent_name not in user_agents:
                return Result.fail("代理不存在")

            agent_config = user_agents[agent_name]
            
            # 创建实例
            if user_id not in self._agent_instances:
                self._agent_instances[user_id] = {}
            
            # 获取向量库实例
            vectordb_instances = []
            for db_name in agent_config.vectordbs:
                db_result = self.vectordb_manager.get_db(user_id, db_name)
                if not db_result.success:
                    return Result.fail(f"获取向量库失败: {db_result.error}")
                vectordb_instances.append(db_result.data)

            # 创建代理实例
            instance = self._agent_factory.create_agent_instance(
                user_id=user_id,
                agent_config=agent_config,
                vectordb_instances=vectordb_instances
            )
            print(">>> 创建新的Agent实例", instance)
            self._agent_instances[user_id][agent_name] = instance
            
            return Result.ok(data=instance, message="成功获取代理实例")
        except Exception as e:
            return Result.fail(f"获取代理实例失败: {str(e)}")

    def list_agents(self, user_id: str) -> Result[List[Dict[str, Any]]]:
        """列出用户的所有代理"""
        try:
            user_agents = self._storage.get(owner_id=user_id)
            if not user_agents:
                return Result.ok(data=[])
            
            agents = [
                agent_config.to_dict()
                for agent_config in user_agents.values()
            ]
            return Result.ok(data=agents)
        except Exception as e:
            return Result.fail(f"获取代理列表失败: {str(e)}")

    def remove_agent(self, user_id: str, agent_name: str) -> Result[None]:
        """移除代理"""
        try:
            user_agents = self._storage.get(owner_id=user_id)
            if not user_agents or agent_name not in user_agents:
                return Result.fail("代理不存在")
            
            # 从配置中移除
            del user_agents[agent_name]
            
            # 从缓存中移除
            if user_id in self._agent_instances and agent_name in self._agent_instances[user_id]:
                del self._agent_instances[user_id][agent_name]
                if not self._agent_instances[user_id]:
                    del self._agent_instances[user_id]
            
            if user_agents:
                self._storage.set(user_agents, owner_id=user_id)
            else:
                self._storage.delete(owner_id=user_id)
                
            return Result.ok(message="代理删除成功")
        except Exception as e:
            return Result.fail(f"删除代理失败: {str(e)}")
