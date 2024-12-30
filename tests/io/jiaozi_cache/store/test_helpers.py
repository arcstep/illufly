from enum import Enum
from dataclasses import dataclass

class _TestStatus(Enum):
    """测试用枚举类型"""
    ACTIVE = 1
    INACTIVE = 0

@dataclass
class _TestData:
    """测试用数据类"""
    name: str
    value: int
    
    def to_dict(self):
        return {"name": self.name, "value": self.value}