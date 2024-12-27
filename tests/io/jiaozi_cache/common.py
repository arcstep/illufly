from dataclasses import dataclass, asdict
import pytest
import logging
from typing import Dict, Any

@dataclass(frozen=True)
class StorageData:
    """测试用数据类,用于存储基本用户信息"""
    id: str = "1"  # 用户ID
    name: str = "张三"  # 用户名
    age: int = 25  # 年龄
    email: str = "test@example.com"  # 邮箱
    
    def to_dict(self) -> Dict[str, Any]:
        """
        序列化方法,将对象转换为字典格式
        
        Returns:
            Dict[str, Any]: 包含对象所有字段的字典
        """
        return asdict(self)
    
    @classmethod 
    def from_dict(cls, data: Dict[str, Any]) -> 'StorageData':
        """
        反序列化方法,从字典创建对象
        
        Args:
            data: 包含所需字段的字典数据
            
        Returns:
            StorageData: 新创建的StorageData实例
        """
        return cls(**data)
