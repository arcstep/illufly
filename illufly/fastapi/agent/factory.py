from typing import Any, Dict, List
from .models import AgentInfo
from ...chat import ChatQwen
from ...flow import ChatLearn
from ...io import LocalFileEventsHistory, LocalFileMemoryHistory

class AgentFactory:
    """Agent实例创建工厂"""
    @staticmethod
    def create_agent(
        agent_type: str,
        agent_name: str,
        base_path: str,
        vectordbs: List,
        **kwargs
    ) -> AgentInfo:
        events_path = f"{base_path}/hist/{agent_name}"
        memory_path = f"{base_path}/memory/{agent_name}"

        if agent_type == "chat":
            instance = ChatQwen(
                name=agent_name,
                vectordbs=vectordbs,
                events_history=LocalFileEventsHistory(events_path),
                memory_history=LocalFileMemoryHistory(memory_path)
            )
        elif agent_type == "learn":
            chat_agent = ChatQwen(
                name=f"{agent_name}_qwen",
                vectordbs=vectordbs,
                memory_history=LocalFileMemoryHistory(memory_path)
            )
            instance = ChatLearn(
                chat_agent,
                name=agent_name,
                events_history=LocalFileEventsHistory(events_path)
            )
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

        return AgentInfo(
            name=agent_name,
            agent_type=agent_type,
            instance=instance,
            vectordbs=vectordbs,
            events_history_path=events_path,
            memory_history_path=memory_path,
            description=kwargs.get("description", "")
        )