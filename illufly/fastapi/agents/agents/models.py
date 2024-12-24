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
    is_active: bool = True

    # 添加不可更新的字段列表
    _IMMUTABLE_FIELDS = {'agent_name', 'created_at'}

    def update(self, updates: Dict[str, Any]) -> None:
        """更新配置
        
        Args:
            updates: 要更新的字段和值的字典
            
        Raises:
            ValueError: 当尝试更新不允许的字段时
        """
        # 检查是否尝试更新不可变字段
        invalid_fields = set(updates.keys()) & self._IMMUTABLE_FIELDS
        if invalid_fields:
            raise ValueError(f"不允许更新以下字段: {', '.join(invalid_fields)}")

        # 更新允许的字段
        for key, value in updates.items():
            if hasattr(self, key):
                if key == 'config' and isinstance(self.config, dict):
                    self.config.update(value)
                else:
                    setattr(self, key, value)
            else:
                raise ValueError(f"未知的字段: {key}")

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
            is_active=data.get('is_active', True)
        )