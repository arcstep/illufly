from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime

from ....types import VectorDB
from ....io import ConfigStoreProtocol, FileConfigStore
from ...users import UsersManager
from ...result import Result
from ..vectordb import VectorDBManager
from .models import AgentConfig
from .factory import AgentFactory

from ....config import get_env
__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")

class AgentsManager:
    def __init__(
        self,
        users_manager: UsersManager,
        vectordb_manager: VectorDBManager,
        agent_factory: Optional[AgentFactory] = None,
        storage: Optional[ConfigStoreProtocol] = None,
    ):
        """初始化代理管理器"""
        self.users_manager = users_manager
        self.vectordb_manager = vectordb_manager

        if storage is None:
            storage = FileConfigStore(
                data_dir=__USERS_PATH__,
                filename="agent.json",
                data_class=Dict[str, AgentConfig],
                serializer=lambda agents: {
                    name: agent_config.to_dict()
                    for name, agent_config in agents.items()
                },
                deserializer=lambda data: {
                    name: AgentConfig.from_dict(agent_data)
                    for name, agent_data in data.items()
                }
            )

        self._agent_factory = agent_factory or AgentFactory()   
        self._agent_instances = {}
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
            # 验证向量库是否存在
            for db_name in vectordbs:
                db_result = self.vectordb_manager.get_db(user_id, db_name)
                if not db_result.success:
                    return Result.fail(f"向量库 '{db_name}' 不存在")

            # 获取用户的代理配置
            user_agents = self._storage.get("agents", owner_id=user_id) or {}
            
            if agent_name in user_agents:
                return Result.fail("代理已存在")

            config = AgentFactory.create_agent(
                user_id=user_id,
                agent_type=agent_type,
                agent_name=agent_name,
                vectordbs=vectordbs,
                **kwargs
            )
            user_agents[agent_name] = config
            self._storage.set("agents", user_agents, owner_id=user_id)
            return Result.ok(data=config)

        except Exception as e:
            return Result.fail(f"创建代理失败: {str(e)}")

    def get_agent(self, user_id: str, agent_name: str) -> Result[Any]:
        """获取代理实例"""
        try:
            user_agents = self._storage.get("agents", owner_id=user_id)
            if not user_agents or agent_name not in user_agents:
                return Result.fail("代理不存在")
                
            if user_id not in self._agent_instances:
                self._agent_instances[user_id] = {}
            
            instance = self._agent_instances[user_id].get(agent_name)
            if instance:
                return Result.ok(data=instance)

            agent_config = user_agents[agent_name]
            
            # 创建实例
            vectordb_instances = []
            for db_name in agent_config.vectordbs:
                db_result = self.vectordb_manager.get_db(user_id, db_name)
                if not db_result.success:
                    return Result.fail(f"获取向量库失败: {db_result.error}")
                vectordb_instances.append(db_result.data)

            instance = self._agent_factory.create_agent_instance(
                user_id=user_id,
                agent_config=agent_config,
                vectordb_instances=vectordb_instances
            )

            self._agent_instances[user_id][agent_name] = instance

            # 更新最后使用时间
            agent_config.last_used = datetime.now()
            self._storage.set("agents", user_agents, owner_id=user_id)
            
            return Result.ok(data=instance)
        except Exception as e:
            return Result.fail(f"获取代理实例失败: {str(e)}")

    def list_agents(self, user_id: str) -> Result[List[Dict[str, Any]]]:
        """列出用户的所有代理"""
        try:
            data = self._storage.get("agents", owner_id=user_id)
            if not data:
                return Result.ok(data=[])
            
            agents = [
                agent_config.to_dict()
                for agent_config in data.values()
            ]
            return Result.ok(data=agents)
        except Exception as e:
            return Result.fail(f"获取代理列表失败: {str(e)}")

    def remove_agent(self, user_id: str, agent_name: str) -> Result[None]:
        """移除代理"""
        try:
            user_agents = self._storage.get("agents", owner_id=user_id)
            if not user_agents or agent_name not in user_agents:
                return Result.fail("代理不存在")
            
            agent_info = user_agents.pop(agent_name)
            
            # 清理文件系统中的代理数据
            AgentFactory.cleanup_agent(user_id, agent_name)
            
            if user_agents:
                self._storage.set("agents", user_agents, owner_id=user_id)
            else:
                self._storage.delete("agents", owner_id=user_id)
            return Result.ok()
        except Exception as e:
            return Result.fail(f"删除代理失败: {str(e)}")

    def update_agent_config(
        self, 
        user_id: str, 
        agent_name: str, 
        config_updates: Dict[str, Any]
    ) -> Result[None]:
        """更新代理配置"""
        try:
            user_agents = self._storage.get("agents", owner_id=user_id)
            if not user_agents or agent_name not in user_agents:
                return Result.fail("代理不存在")
            
            agent_info = user_agents[agent_name]
            if hasattr(agent_info, 'config'):
                agent_info.config.update(config_updates)
            else:
                agent_info.config = config_updates
            
            if hasattr(agent_info.instance, 'reconfigure'):
                try:
                    agent_info.instance.reconfigure(config_updates)
                except Exception as e:
                    return Result.fail(f"重新配置代理失败: {str(e)}")
            
            self._storage.set("agents", user_agents, owner_id=user_id)
            return Result.ok()
        except Exception as e:
            return Result.fail(f"更新代理配置失败: {str(e)}")


