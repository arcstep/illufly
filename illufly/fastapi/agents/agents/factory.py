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
    def create_agent_instance(
        self,
        user_id: str,
        agent_config: AgentConfig,
        vectordb_instances: List[VectorDB] = None,
    ) -> Optional[Runnable]:  # 修改返回类型为Optional[Runnable],因为可能创建失败
        """创建代理实例
        
        Args:
            user_id: 用户ID
            agent_config: 代理配置
            vectordb_instances: 向量库实例列表
            
        Returns:
            Optional[Runnable]: Agent实例,创建失败时返回None
        """
        pass

class DefaultAgentFactory(BaseAgentFactory):
    """默认的Agent工厂实现"""

    def create_agent_instance(
        self,
        user_id: str,
        agent_config: AgentConfig,
        vectordb_instances: List[VectorDB] = None,
    ) -> Optional[Runnable]:
        """创建代理实例"""
        try:
            from ....chat import ChatQwen, FakeLLM
            from ....flow import ChatLearn
            from ....io import LocalFileEventsHistory, LocalFileMemoryHistory

            agent_type = agent_config.agent_type
            agent_name = agent_config.agent_name
            vectordb_instances = vectordb_instances or []

            base_store_path = Path(get_env("ILLUFLY_CONFIG_STORE_DIR")) / user_id / "store"
            events_path = str(base_store_path / "hist" / agent_name)
            memory_path = str(base_store_path / "memory" / agent_name)
            
            Path(events_path).mkdir(parents=True, exist_ok=True)
            Path(memory_path).mkdir(parents=True, exist_ok=True)

            events_history = LocalFileEventsHistory(events_path)
            memory_history = LocalFileMemoryHistory(memory_path)

            if agent_type == "chat":
                return ChatQwen(
                    name=agent_name,
                    vectordbs=vectordb_instances,
                    events_history=events_history,
                    memory_history=memory_history,
                    **agent_config.config  # 添加额外配置参数
                )
            elif agent_type == "fake":
                return FakeLLM(
                    name=agent_name,
                    vectordbs=vectordb_instances,
                    events_history=events_history,
                    memory_history=memory_history,
                    **agent_config.config
                )
            elif agent_type == "learn":
                chat_agent = ChatQwen(
                    name=f"{agent_name}_scribe",
                    vectordbs=vectordb_instances,
                    memory_history=memory_history,
                    **agent_config.config
                )
                return ChatLearn(
                    chat_agent,
                    name=agent_name,
                    events_history=events_history
                )
            else:
                raise ValueError(f"不支持的代理类型: {agent_type}")
        except Exception as e:
            print(f"创建代理实例失败: {str(e)}")
            return None
