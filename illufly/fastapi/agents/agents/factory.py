from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol
from pathlib import Path
from datetime import datetime

from ....core.runnable.vectordb import VectorDB
from ....core.runnable import Runnable
from ....config import get_env
from .models import AgentConfig

class BaseAgentFactory(ABC):
    """Agent工厂基类"""
    
    @abstractmethod
    def create_agent_config(
        self,
        user_id: str,
        agent_type: str,
        agent_name: str,
        vectordbs: List[str] = None,
        **kwargs
    ) -> AgentConfig:
        """创建代理配置
        
        Args:
            user_id: 用户ID
            agent_type: 代理类型
            agent_name: 代理名称
            vectordbs: 向量库列表
            **kwargs: 额外配置参数
            
        Returns:
            AgentConfig: 代理配置对象
        """
        pass

    @abstractmethod
    def create_agent_instance(
        self,
        user_id: str,
        agent_config: AgentConfig,
        vectordb_instances: List[VectorDB] = None,
    ) -> Runnable:
        """创建代理实例
        
        Args:
            user_id: 用户ID
            agent_config: 代理配置
            vectordb_instances: 向量库实例列表
            
        Returns:
            Runnable: Agent实例
        """
        pass

class DefaultAgentFactory(BaseAgentFactory):
    """默认的Agent工厂实现"""
    
    def create_agent_config(
        self,
        user_id: str,
        agent_type: str,
        agent_name: str,
        vectordbs: List[str] = None,
        **kwargs
    ) -> AgentConfig:
        """创建代理配置"""
        def get_agent_paths(user_id: str, agent_name: str) -> Dict[str, str]:
            """获取代理相关的所有路径"""
            base_store_path = Path(get_env("ILLUFLY_CONFIG_STORE_DIR")) / user_id / "store"
            paths = {
                'events': str(base_store_path / "hist" / agent_name),
                'memory': str(base_store_path / "memory" / agent_name),
            }            
            for path in paths.values():
                Path(path).mkdir(parents=True, exist_ok=True)
            
            return paths

        paths = get_agent_paths(user_id, agent_name)
        return AgentConfig(
            agent_name=agent_name,
            agent_type=agent_type,
            description=kwargs.get("description", ""),
            config=kwargs.get("config", {}),
            vectordbs=vectordbs or [],
            events_history_path=paths['events'],
            memory_history_path=paths['memory'],
            created_at=datetime.now()
        )

    def create_agent_instance(
        self,
        user_id: str,
        agent_config: AgentConfig,
        vectordb_instances: List[VectorDB] = None,
    ) -> Runnable:
        """创建代理实例"""
        from ....chat import ChatQwen, FakeLLM
        from ....flow import ChatLearn
        from ....io import LocalFileEventsHistory, LocalFileMemoryHistory

        agent_type = agent_config.agent_type
        agent_name = agent_config.agent_name
        events_path = agent_config.events_history_path
        memory_path = agent_config.memory_history_path
        vectordb_instances = vectordb_instances or []

        if agent_type == "chat":
            return ChatQwen(
                name=agent_name,
                vectordbs=vectordb_instances,
                events_history=LocalFileEventsHistory(events_path),
                memory_history=LocalFileMemoryHistory(memory_path)
            )
        elif agent_type == "fake":
            return FakeLLM(
                name=agent_name,
                vectordbs=vectordb_instances,
                events_history=LocalFileEventsHistory(events_path),
                memory_history=LocalFileMemoryHistory(memory_path)
            )
        elif agent_type == "learn":
            chat_agent = ChatQwen(
                name=f"{agent_name}_scribe",
                vectordbs=vectordb_instances,
                memory_history=LocalFileMemoryHistory(memory_path)
            )
            return ChatLearn(
                chat_agent,
                name=agent_name,
                events_history=LocalFileEventsHistory(events_path)
            )
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")
