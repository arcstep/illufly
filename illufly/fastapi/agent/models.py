from typing import List, Any, Optional, Dict
from datetime import datetime

class AgentInfo:
    """Agent实例的元信息"""
    def __init__(
        self, 
        name: str,
        agent_type: str,
        instance: Any,
        vectordbs: List = None,
        events_history_path: str = None,
        memory_history_path: str = None,
        description: str = "",
        config: Dict[str, Any] = None
    ):
        self.name = name
        self.agent_type = agent_type
        self.instance = instance
        self.vectordbs = vectordbs or []
        self.events_history_path = events_history_path
        self.memory_history_path = memory_history_path
        self.description = description
        self.config = config or {}
        self.created_at = datetime.now()
        self.last_used = datetime.now()
        self.is_active = True

    def to_dict(self) -> dict:
        """序列化，不包含 instance 和 vectordbs"""
        return {
            "name": self.name,
            "type": self.agent_type,
            "events_history_path": self.events_history_path,
            "memory_history_path": self.memory_history_path,
            "description": self.description,
            "config": self.config,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "is_active": self.is_active
        }

    @classmethod
    def from_dict(cls, data: dict, instance: Any = None) -> 'AgentInfo':
        """从字典创建实例
        Args:
            data: 序列化的数据
            instance: 可选的实例对象
        """
        agent_info = cls(
            name=data["name"],
            agent_type=data["type"],
            instance=instance,
            vectordbs=[],  # 初始为空列表，需要外部重新加载
            events_history_path=data.get("events_history_path"),
            memory_history_path=data.get("memory_history_path"),
            description=data.get("description", ""),
            config=data.get("config", {})
        )
        agent_info.created_at = datetime.fromisoformat(data["created_at"])
        agent_info.last_used = datetime.fromisoformat(data["last_used"])
        agent_info.is_active = data.get("is_active", True)
        return agent_info