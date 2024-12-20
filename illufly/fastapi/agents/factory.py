from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
from .models import AgentConfig
from ...core.runnable.vectordb import VectorDB
from ...config import get_env

__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")

def get_agent_paths(user_id: str, agent_name: str) -> Dict[str, str]:
    """获取代理相关的所有路径"""
    base_store_path = Path(__USERS_PATH__) / user_id / "store"
    
    paths = {
        'events': str(base_store_path / "hist" / agent_name),
        'memory': str(base_store_path / "memory" / agent_name),
    }
    
    for path in paths.values():
        Path(path).mkdir(parents=True, exist_ok=True)
    
    return paths

class AgentFactory:
    """Agent实例创建工厂"""
    
    @staticmethod
    def create_agent(
        user_id: str,
        agent_type: str,
        agent_name: str,
        vectordbs: List[str] = None,
        **kwargs
    ) -> Tuple[AgentConfig, Any]:
        """创建代理实例和配置"""
        paths = get_agent_paths(user_id, agent_name)
        # 创建配置
        config = AgentConfig(
            agent_name=agent_name,
            agent_type=agent_type,
            description=kwargs.get("description", ""),
            config=kwargs.get("config", {}),
            vectordbs=vectordbs,
            events_history_path=paths['events'],
            memory_history_path=paths['memory'],
            created_at=datetime.now(),
            last_used=datetime.now()
        )
        
        return config

    @staticmethod
    def cleanup_agent(user_id: str, agent_name: str):
        """清理代理相关的文件"""
        paths = get_agent_paths(user_id, agent_name)
        
        for path in [paths['events'], paths['memory']]:
            path = Path(path)
            if path.exists():
                import shutil
                shutil.rmtree(path)

    @staticmethod
    def create_agent_instance(
        user_id: str,
        agent_config: AgentConfig,
        vectordb_instances: List[VectorDB] = None,
    ) -> Optional[VectorDB]:
        """创建智能体实例"""
        from ...chat import ChatQwen
        from ...flow import ChatLearn
        from ...io import LocalFileEventsHistory, LocalFileMemoryHistory, LocalFileKnowledgeDB

        agent_type = agent_config.agent_type
        agent_name = agent_config.agent_name
        paths = get_agent_paths(user_id, agent_name)        
        vectordb_instances = vectordb_instances or []

        if agent_type == "chat":
            return ChatQwen(
                name=agent_name,
                vectordbs=vectordb_instances,
                events_history=LocalFileEventsHistory(paths['events']),
                memory_history=LocalFileMemoryHistory(paths['memory'])
            )
        elif agent_type == "learn":
            chat_agent = ChatQwen(
                name=f"{agent_name}_scribe",
                vectordbs=vectordb_instances,
                memory_history=LocalFileMemoryHistory(paths['memory'])
            )
            return ChatLearn(
                chat_agent,
                name=agent_name,
                events_history=LocalFileEventsHistory(paths['events'])
            )
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")
