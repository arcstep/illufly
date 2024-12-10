from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
from .models import AgentInfo
from .factory import AgentFactory
from ..common import StorageProtocol, FileStorage

class AgentManager:
    def __init__(
        self, 
        storage: Optional[StorageProtocol[Dict[str, AgentInfo]]] = None,
        base_path: str = "./__users__"
    ):
        """初始化代理管理器
        Args:
            storage: 存储实现，用于保存代理配置信息
            base_path: 用户数据根目录
        """
        self.base_path = base_path
        if storage is None:
            storage = FileStorage[Dict[str, AgentInfo]](
                data_dir=base_path,
                filename="agent.json",
                serializer=lambda agents: {
                    name: {
                        **agent_info.to_dict(),
                        "vectordb_names": [db.name for db in agent_info.vectordbs]
                    }
                    for name, agent_info in agents.items()
                },
                deserializer=lambda data: {
                    name: AgentInfo.from_dict(agent_data)
                    for name, agent_data in data.items()
                }
            )
        self._storage = storage

    def _get_user_path(self, username: str) -> str:
        """获取用户数据目录路径"""
        return str(Path(self.base_path) / username)

    def _get_user_storage(self, username: str) -> StorageProtocol:
        """获取用户特定的存储实例"""
        user_storage = self._storage.clone()
        user_storage.data_dir = self._get_user_path(username)  # 直接使用用户目录
        return user_storage

    def init_agents(self, username: str):
        """初始化代理"""
        default_db = "default_knowledge"
        if default_db not in self.list_dbs(username, username):
            self.create_db(username, default_db, username)

    def create_db(self, username: str, db_name: str, requester: str, **kwargs) -> bool:
        """创建知识库"""
        if requester != username:  # 权限检查
            return False
        
        return AgentFactory.create_db(
            username, 
            db_name, 
            self._get_user_path(username)  # 使用用户特定路径
        )
    
    def list_dbs(self, username: str, requester: str) -> List[str]:
        """列出知识库"""
        if requester != username:  # 权限检查
            return []
        
        return AgentFactory.list_dbs(username, self._get_user_path(username))

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
        if requester != username:  # 权限检查
            return False
            
        storage = self._get_user_storage(username)
        user_agents = storage.get("agents") or {}
        if agent_name in user_agents:
            return False

        try:
            agent_info = AgentFactory.create_agent(
                username=username,
                agent_type=agent_type,
                agent_name=agent_name,
                base_path=self._get_user_path(username),
                vectordb_names=vectordb_names,
                **kwargs
            )
            user_agents[agent_name] = agent_info
            storage.set("agents", user_agents)
            return True
        except ValueError:
            return False

    def get_agent(self, username: str, agent_name: str, requester: str) -> Optional[Any]:
        """获取代理实例"""
        if requester != username:  # 权限检查
            return None
            
        storage = self._get_user_storage(username)
        user_agents = storage.get("agents")
        if not user_agents:
            return None
            
        agent_info = user_agents.get(agent_name)
        if agent_info:
            # 重新加载向量数据库实例
            all_dbs = AgentFactory.list_dbs(username, self._get_user_path(username))
            agent_info.vectordbs = [
                db for db in all_dbs 
                if db.name in [vdb.name for vdb in agent_info.vectordbs]
            ]
            agent_info.last_used = datetime.now()
            storage.set("agents", user_agents)
            return agent_info.instance
        return None

    def list_agents(self, username: str, requester: str) -> List[Dict[str, Any]]:
        """列出用户的所有代理"""
        if requester != username:  # 权限检查
            return []
            
        agents = []
        storage = self._get_user_storage(username)
        user_agents = storage.get("agents") or {}
        for name, info in user_agents.items():
            agents.append({
                'name': name,
                'type': info.agent_type,
                'description': info.description,
                'config': info.config,
                'vectordb_names': [db.name for db in info.vectordbs],
                'last_used': info.last_used.isoformat() if info.last_used else None
            })
        return agents

    def remove_agent(self, username: str, agent_name: str, requester: str) -> bool:
        """移除代理"""
        if requester != username:  # 权限检查
            return False
            
        storage = self._get_user_storage(username)
        user_agents = storage.get("agents")
        if not user_agents or agent_name not in user_agents:
            return False
        
        agent_info = user_agents.pop(agent_name)
        if hasattr(agent_info.instance, 'cleanup'):
            agent_info.instance.cleanup()
        
        # 清理文件系统中的代理数据
        AgentFactory.cleanup_agent(username, agent_name, self._get_user_path(username))
        
        if user_agents:
            storage.set("agents", user_agents)
        else:
            storage.delete("agents")
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
        user_agents = storage.get("agents")
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
        
        storage.set("agents", user_agents)
        return True 