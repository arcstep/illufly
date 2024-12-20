from typing import List, Any, Optional, Dict
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class AgentConfig:
    """代理配置信息"""
    agent_name: str
    agent_type: str
    description: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    vectordbs: List[str] = field(default_factory=list)
    events_history_path: str = ""
    memory_history_path: str = ""
    created_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'agent_name': self.agent_name,
            'agent_type': self.agent_type,
            'description': self.description,
            'config': self.config,
            'vectordbs': self.vectordbs,
            'events_history_path': self.events_history_path,
            'memory_history_path': self.memory_history_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'is_active': self.is_active
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentConfig':
        """从字典创建实例"""
        return cls(
            agent_name=data['agent_name'],
            agent_type=data['agent_type'],
            description=data.get('description', ''),
            config=data.get('config', {}),
            vectordbs=data.get('vectordbs', []),
            events_history_path=data.get('events_history_path', ''),
            memory_history_path=data.get('memory_history_path', ''),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
            last_used=datetime.fromisoformat(data['last_used']) if data.get('last_used') else None,
            is_active=data.get('is_active', True)
        )