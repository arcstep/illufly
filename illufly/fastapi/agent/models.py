from typing import List, Any, Optional
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
        description: str = ""
    ):
        self.name = name
        self.type = agent_type
        self.instance = instance
        self.vectordbs = vectordbs or []
        self.events_history_path = events_history_path
        self.memory_history_path = memory_history_path
        self.description = description
        self.created_at = datetime.now()
        self.last_used = datetime.now()
        self.is_active = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "vectordbs": [str(db) for db in self.vectordbs],
            "events_history_path": self.events_history_path,
            "memory_history_path": self.memory_history_path,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "is_active": self.is_active
        }

    @classmethod
    def from_dict(cls, data: dict, instance: Any = None) -> 'AgentInfo':
        agent_info = cls(
            name=data["name"],
            agent_type=data["type"],
            instance=instance,
            vectordbs=data.get("vectordbs", []),
            events_history_path=data.get("events_history_path"),
            memory_history_path=data.get("memory_history_path"),
            description=data.get("description", "")
        )
        agent_info.created_at = datetime.fromisoformat(data["created_at"])
        agent_info.last_used = datetime.fromisoformat(data["last_used"])
        agent_info.is_active = data.get("is_active", True)
        return agent_info