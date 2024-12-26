from typing import List, Any, Optional, Dict, ClassVar
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator

class AgentConfig(BaseModel):
    """代理配置信息"""
    agent_name: str
    agent_type: str
    description: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)
    vectordbs: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    is_active: bool = True

    # 添加不可更新的字段列表
    _IMMUTABLE_FIELDS: ClassVar[set] = {'agent_name', 'created_at'}

    @model_validator(mode='before')
    def set_defaults(cls, values):
        """初始化后设置默认值"""
        if values.get('created_at') is None:
            values['created_at'] = datetime.now()
        return values

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
