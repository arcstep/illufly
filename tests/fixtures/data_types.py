from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)  # 使用 frozen=True 来创建不可变的数据类
class TestData:
    id: str
    name: str
    age: int
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TestData':
        """从字典创建实例"""
        return cls(**data)
        
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age
        }