from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime

import pytest
import logging

from illufly.io import JiaoziCache

@dataclass(frozen=True)
class StorageData:
    """测试用数据类"""
    id: str = "1"
    name: str = "张三"
    age: int = 25
    email: str = "test@example.com"
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """序列化方法"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'StorageData':
        """反序列化方法"""
        return cls(
            id=data["id"],
            name=data["name"],
            age=data["age"],
            email=data["email"]
        )

@pytest.fixture
def storage_factory(tmp_path):
    """创建文件存储实例的工厂函数"""
    def create_storage():
        return JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="test.json",
            data_class=StorageData,
            indexes=["email", "name"]
        )
    return create_storage

@pytest.fixture
def test_data_factory():
    def create_test_data(**kwargs):
        defaults = {
            "id": "1",
            "name": "张三",
            "age": 25,
            "email": "test@example.com"
        }
        defaults.update(kwargs)
        return StorageData(**defaults)
    return create_test_data
