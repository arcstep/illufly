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
            base_path: 代理文件存储的基础路径（用于实际的历史记录、内存等文件）
        """
        self.base_path = base_path
        if storage is None:
            storage = FileStorage[Dict[str, AgentInfo]](
                data_dir="__users__/agents",
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

    def init_agents(self, username: str):
        """初始化代理"""
        default_db = "default_knowledge"
        if default_db not in self.list_dbs(username, username):
            self.create_db(username, default_db, username)

    def create_db(self, username: str, db_name: str, requester: str, **kwargs) -> bool:
        """创建知识库"""
        if requester != username:  # 权限检查
            return False
        
        return AgentFactory.create_db(username, db_name, self.base_path)
    
    def list_dbs(self, username: str, requester: str) -> List[str]:
        """列出知识库"""
        if requester != username:  # 权限检查
            return []
        
        return AgentFactory.list_dbs(username, self.base_path)

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
            
        user_agents = self._storage.get(agent_name, owner=username) or {}
        if agent_name in user_agents:
            return False

        try:
            agent_info = AgentFactory.create_agent(
                username=username,
                agent_type=agent_type,
                agent_name=agent_name,
                base_path=self.base_path,
                vectordb_names=vectordb_names,
                **kwargs
            )
            user_agents[agent_name] = agent_info
            self._storage.set(agent_name, user_agents, owner=username)
            return True
        except ValueError:
            return False

    def get_agent(self, username: str, agent_name: str, requester: str) -> Optional[Any]:
        """获取代理实例"""
        if requester != username:  # 权限检查
            return None
            
        user_agents = self._storage.get(agent_name, owner=username)
        if not user_agents:
            return None
            
        agent_info = user_agents.get(agent_name)
        if agent_info:
            # 重新加载向量数据库实例
            all_dbs = AgentFactory.list_dbs(username, self.base_path)
            agent_info.vectordbs = [
                db for db in all_dbs 
                if db.name in [vdb.name for vdb in agent_info.vectordbs]
            ]
            agent_info.last_used = datetime.now()
            self._storage.set(agent_name, user_agents, owner=username)
            return agent_info.instance
        return None

    def list_agents(self, username: str, requester: str) -> List[Dict[str, Any]]:
        """列出用户的所有代理"""
        if requester != username:  # 权限检查
            return []
            
        agents = []
        for key in self._storage.list_keys(owner=username):
            if user_agents := self._storage.get(key, owner=username):
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
            
        user_agents = self._storage.get(agent_name, owner=username)
        if not user_agents or agent_name not in user_agents:
            return False
        
        agent_info = user_agents.pop(agent_name)
        if hasattr(agent_info.instance, 'cleanup'):
            agent_info.instance.cleanup()
        
        # 清理文件系统中的代理数据
        AgentFactory.cleanup_agent(username, agent_name, self.base_path)
        
        if user_agents:
            self._storage.set(agent_name, user_agents, owner=username)
        else:
            self._storage.delete(agent_name, owner=username)
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
            
        user_agents = self._storage.get(agent_name, owner=username)
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
        
        self._storage.set(agent_name, user_agents, owner=username)
        return True 