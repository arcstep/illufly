from typing import Any, Dict, List, Optional
from pathlib import Path
from .models import AgentInfo
from ...chat import ChatQwen
from ...flow import ChatLearn
from ...io import LocalFileEventsHistory, LocalFileMemoryHistory, LocalFileKnowledgeDB
from ...community.faiss import FaissDB

class AgentFactory:
    """Agent实例创建工厂"""
    
    @staticmethod
    def get_agent_paths(base_path: str, username: str, agent_name: str) -> Dict[str, str]:
        """获取代理相关的所有路径"""
        return {
            'events': f"{base_path}/hist/{username}/{agent_name}",
            'memory': f"{base_path}/memory/{username}/{agent_name}",
            'knowledge': f"{base_path}/knowledge/{username}"
        }

    @staticmethod
    def create_db(username: str, base_path: str) -> List:
        """创建知识库"""
        paths = AgentFactory.get_agent_paths(base_path, username, "")
        knowledge_db_path = paths['knowledge']
        Path(knowledge_db_path).mkdir(parents=True, exist_ok=True)
        return [FaissDB(LocalFileKnowledgeDB(knowledge_db_path))]

    @staticmethod
    def create_agent(
        username: str,
        agent_type: str,
        agent_name: str,
        base_path: str,
        vectordbs: List,
        **kwargs
    ) -> AgentInfo:
        """创建代理实例"""
        paths = AgentFactory.get_agent_paths(base_path, username, agent_name)
        
        # 确保所有必要的目录存在
        for path in paths.values():
            Path(path).mkdir(parents=True, exist_ok=True)

        if agent_type == "chat":
            instance = ChatQwen(
                name=agent_name,
                vectordbs=vectordbs,
                events_history=LocalFileEventsHistory(paths['events']),
                memory_history=LocalFileMemoryHistory(paths['memory'])
            )
        elif agent_type == "learn":
            chat_agent = ChatQwen(
                name=f"{agent_name}_qwen",
                vectordbs=vectordbs,
                memory_history=LocalFileMemoryHistory(paths['memory'])
            )
            instance = ChatLearn(
                chat_agent,
                name=agent_name,
                events_history=LocalFileEventsHistory(paths['events'])
            )
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

        return AgentInfo(
            name=agent_name,
            agent_type=agent_type,
            instance=instance,
            vectordbs=vectordbs,
            events_history_path=paths['events'],
            memory_history_path=paths['memory'],
            description=kwargs.get("description", ""),
            config=kwargs.get("config", {})  # 保存初始配置
        )

    @staticmethod
    def cleanup_agent(username: str, agent_name: str, base_path: str):
        """清理代理相关的文件"""
        paths = AgentFactory.get_agent_paths(base_path, username, agent_name)
        
        # 清理事件历史和内存历史
        for path in [paths['events'], paths['memory']]:
            path = Path(path)
            if path.exists():
                import shutil
                shutil.rmtree(path)
