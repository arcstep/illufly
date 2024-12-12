from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
from ...config import get_env
from ...types import VectorDB
from ..vectordb import VectorDBManager
from ..common import ConfigStoreProtocol, FileConfigStore
from ..user import UserManager
from .models import AgentConfig
from .factory import AgentFactory

__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")

class AgentManager:
    def __init__(
        self,
        user_manager: UserManager,
        vectordb_manager: VectorDBManager,
        agent_factory: Optional[AgentFactory] = None,
        storage: Optional[ConfigStoreProtocol[Dict[str, AgentConfig]]] = None,
    ):
        """初始化代理管理器"""
        self.user_manager = user_manager
        self.vectordb_manager = vectordb_manager

        if storage is None:
            storage = FileConfigStore[Dict[str, AgentConfig]](
                data_dir=__USERS_PATH__,
                filename="agent.json",
                serializer=lambda agents: {
                    name: agent_config.to_dict()
                    for name, agent_config in agents.items()
                },
                deserializer=lambda data: {
                    name: AgentConfig.from_dict(agent_data)
                    for name, agent_data in data.items()
                },
                use_id_subdirs=True
            )

        self._agent_factory = agent_factory or AgentFactory()   
        self._agent_instances = {}

        self._storage = storage

    def _get_user_storage(self, user_id: str) -> ConfigStoreProtocol:
        """获取用户特定的存储实例"""
        user_storage = self._storage.clone()
        user_storage.data_dir = Path(__USERS_PATH__) / user_id
        user_storage.filename = "agent.json"
        return user_storage

    def create_agent(
        self,
        user_id: str,
        agent_type: str,
        agent_name: str,
        vectordbs: List[str],
        requester_id: str,
        **kwargs
    ) -> bool:
        """创建代理"""
        if not self.user_manager.can_access_user(user_id, requester_id):
            return {
                "success": False,
                "message": "You are not allowed to create agents for other users."
            }

        # 验证向量库是否存在
        for db_name in vectordbs:
            if not self.vectordb_manager.get_db(user_id, db_name, requester_id):
                return {
                    "success": False,
                    "message": f"Vector database '{db_name}' does not exist."
                }

        try:
            # 获取用户的代理配置
            user_agents = self._storage.get("agents", owner_id=user_id) or {}
            
            if agent_name in user_agents:
                return {
                    "success": False,
                    "message": "Agent already exists"
                }

            config = AgentFactory.create_agent(
                user_id=user_id,
                agent_type=agent_type,
                agent_name=agent_name,
                vectordbs=vectordbs,
                **kwargs
            )
            user_agents[agent_name] = config
            self._storage.set("agents", user_agents, owner_id=user_id)
            return {
                "success": True,
                "message": "Agent created successfully."
            }

        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

    def get_agent(self, user_id: str, agent_name: str, requester_id: str) -> Optional[Any]:
        """获取代理实例"""
        if not self.user_manager.can_access_user(user_id, requester_id):
            return {
                "success": False,
                "message": "You cannot access this agent"
            }

        user_agents = self._storage.get("agents", owner_id=user_id)
        if not user_agents or agent_name not in user_agents:
            return {
                "success": False,
                "message": "Agent not found"
            }
            
        if user_id not in self._agent_instances:
            self._agent_instances[user_id] = {}
        
        instance = self._agent_instances[user_id].get(agent_name)
        if instance:
            return {
                "success": True,
                "message": "Agent retrieved successfully",
                "instance": instance
            }

        agent_config = user_agents[agent_name]
        
        # 创建实例
        vectordb_instances=[]
        for db_name in agent_config.vectordbs:
            resp = self.vectordb_manager.get_db(user_id, db_name, requester_id)
            if resp['success']:
                vectordb_instances.append(resp['instance'])
            else:
                return resp
        instance = self._agent_factory.create_agent_instance(
            user_id=user_id,
            agent_config=agent_config,
            vectordb_instances=vectordb_instances
        )

        self._agent_instances[user_id][agent_name] = instance

        # 更新最后使用时间
        agent_config.last_used = datetime.now()
        self._storage.set("agents", user_agents, owner_id=user_id)
        
        return {
            "success": True,
            "message": "Agent retrieved successfully",
            "instance": instance
        }

    def list_agents(self, user_id: str, requester_id: str) -> List[Dict[str, Any]]:
        """列出用户的所有代理"""
        if not self.user_manager.can_access_user(user_id, requester_id):
            return {
                "success": False,
                "message": "You cannot access this agent"
            }

        data = self._storage.get("agents", owner_id=user_id)
        if not data:
            return {
                "success": True,
                "message": "No agents found",
                "data": []
            }
        
        return [
            agent_config.to_dict()
            for agent_config in data.values()
        ]

    def remove_agent(self, user_id: str, agent_name: str, requester_id: str) -> bool:
        """移除代理"""
        if not self.user_manager.can_access_user(user_id, requester_id):
            return {
                "success": False,
                "message": "You cannot access this agent"
            }
            
        user_agents = self._storage.get("agents", owner_id=user_id)
        if not user_agents or agent_name not in user_agents:
            return {
                "success": False,
                "message": "Agent not found"
            }
        
        agent_info = user_agents.pop(agent_name)
        
        # 清理文件系统中的代理数据
        AgentFactory.cleanup_agent(user_id, agent_name)
        
        if user_agents:
            storage.set("agents", user_agents, owner_id=user_id)
        else:
            storage.delete("agents", owner_id=user_id)
        return {
            "success": True,
            "message": "Agent removed successfully"
        }

    def update_agent_config(
        self, 
        user_id: str, 
        agent_name: str, 
        config_updates: Dict[str, Any],
        requester_id: str
    ) -> bool:
        """更新代理配置"""
        if not self.user_manager.can_access_user(user_id, requester_id):
            return {
                "success": False,
                "message": "You cannot access this agent"
            }
            
        storage = self._get_user_storage(user_id)
        user_agents = storage.get("agents", owner_id=user_id)
        if not user_agents or agent_name not in user_agents:
            return {
                "success": False,
                "message": "Agent not found"
            }
        
        agent_info = user_agents[agent_name]
        if hasattr(agent_info, 'config'):
            agent_info.config.update(config_updates)
        else:
            agent_info.config = config_updates
        
        if hasattr(agent_info.instance, 'reconfigure'):
            try:
                agent_info.instance.reconfigure(config_updates)
            except Exception:
                return {
                    "success": False,
                    "message": "Failed to reconfigure agent"
                }
        
        storage.set("agents", user_agents, owner_id=user_id)
        return {
            "success": True,
            "message": "Agent configuration updated successfully"
        }


