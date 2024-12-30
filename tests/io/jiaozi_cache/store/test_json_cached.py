import pytest
import time
import threading
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import List, Dict, Optional
from pydantic import BaseModel

from illufly.io.jiaozi_cache.store.json_cached_read_write import CachedJSONStorage

# 测试用的 Pydantic 模型
class Address(BaseModel):
    street: str
    city: str
    country: str
    postal_code: Optional[str] = None

class User(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime
    addresses: List[Address]
    metadata: Dict[str, str]
    is_active: bool = True

@pytest.fixture
def temp_dir(tmp_path):
    return str(tmp_path)

@pytest.fixture
def storage(temp_dir):
    storage = CachedJSONStorage[Dict](
        data_dir=temp_dir,
        segment="test.json"
    )
    yield storage
    storage.close()

class TestCachedJSONStorage:
    def test_simple_types(self, storage):
        """测试简单数据类型"""
        test_data = {
            "string": "test",
            "integer": 42,
            "float": 3.14,
            "boolean": True,
            "none": None
        }
        
        # 写入并读取
        storage.set("simple", test_data)
        result = storage.get("simple")
        
        assert result == test_data
        
        # 验证缓存命中
        metrics = storage.get_metrics()
        assert metrics["read_cache"]["hits"] > 0

    def test_complex_types(self, storage):
        """测试复杂数据类型"""
        test_data = {
            "list": [1, 2, 3, "test"],
            "tuple": (4, 5, 6),
            "nested_dict": {"key": {"nested": "value"}},
            "datetime": datetime.now(),
            "decimal": Decimal("3.14"),
            "uuid": UUID("550e8400-e29b-41d4-a716-446655440000"),
            "path": Path("/test/path")
        }
        
        storage.set("complex", test_data)
        result = storage.get("complex")
        
        # 验证基本类型
        assert result["list"] == test_data["list"]
        assert tuple(result["tuple"]) == test_data["tuple"]
        assert result["nested_dict"] == test_data["nested_dict"]
        
        # 验证特殊类型
        assert isinstance(result["datetime"], datetime)
        assert isinstance(result["decimal"], Decimal)
        assert isinstance(result["uuid"], UUID)
        assert isinstance(result["path"], Path)

    def test_pydantic_models(self, storage):
        """测试Pydantic模型"""
        address = Address(
            street="123 Test St",
            city="Test City",
            country="Test Country",
            postal_code="12345"
        )
        
        user = User(
            id=1,
            name="Test User",
            email="test@example.com",
            created_at=datetime.now(),
            addresses=[address],
            metadata={"role": "admin"}
        )
        
        # 存储和读取
        storage.set("user", user)
        result = storage.get("user")
        
        # 验证类型和内容
        assert isinstance(result, User)
        assert result.id == user.id
        assert result.name == user.name
        assert isinstance(result.addresses[0], Address)
        assert result.addresses[0].street == address.street
        assert result.model_dump() == user.model_dump()

    def test_nested_structures(self, storage):
        """测试嵌套结构"""
        nested_data = {
            "level1": {
                "level2": {
                    "level3": {
                        "data": [1, 2, {"key": "value"}]
                    }
                }
            },
            "mixed": [
                {"dict_in_list": "value"},
                [1, 2, {"nested_in_list": [3, 4]}]
            ]
        }
        
        storage.set("nested", nested_data)
        result = storage.get("nested")
        
        assert result == nested_data
        assert result["level1"]["level2"]["level3"]["data"][2]["key"] == "value"

    def test_cache_behavior(self, storage):
        """测试缓存行为"""
        # 写入数据
        storage.set("key1", {"value": 1})
        
        # 第一次读取（从存储）
        result1 = storage.get("key1")
        
        # 第二次读取（应该从缓存）
        result2 = storage.get("key1")
        
        metrics = storage.get_metrics()
        assert metrics["read_cache"]["hits"] >= 1
        assert result1 == result2

    def test_write_through(self, storage):
        """测试写透策略"""
        # 写入数据
        storage.set("write_test", {"value": 1})
        
        # 强制刷新到磁盘
        storage._storage._flush_to_disk()
        
        # 清除缓存
        storage._cache.clear()
        
        # 重新读取
        result = storage.get("write_test")
        assert result == {"value": 1}

    def test_concurrent_access(self, storage):
        """测试并发访问"""
        def writer(start_idx: int):
            for i in range(start_idx, start_idx + 5):
                storage.set(f"key{i}", {
                    "value": i,
                    "complex": {
                        "list": [1, 2, 3],
                        "dict": {"nested": "value"}
                    }
                })
                
        def reader(keys: List[str]):
            for key in keys:
                value = storage.get(key)
                if value:
                    assert isinstance(value, dict)
                    assert "value" in value
                    assert "complex" in value
        
        # 创建多个读写线程
        threads = [
            threading.Thread(target=writer, args=(i * 5,))
            for i in range(3)
        ] + [
            threading.Thread(
                target=reader,
                args=([f"key{i}" for i in range(j * 5, (j + 1) * 5)],)
            )
            for j in range(3)
        ]
        
        [t.start() for t in threads]
        [t.join() for t in threads]
        
        # 验证数据完整性
        metrics = storage.get_metrics()
        assert metrics["read_cache"]["size"] <= metrics["read_cache"]["capacity"]

    def test_large_dataset(self, storage):
        """测试大数据集"""
        # 创建大量数据
        large_data = {
            f"key{i}": {
                "id": i,
                "data": "x" * 100,
                "nested": {"value": i}
            }
            for i in range(100)
        }
        
        # 批量写入
        for key, value in large_data.items():
            storage.set(key, value)
            
        # 随机读取验证
        import random
        for _ in range(20):
            key = f"key{random.randint(0, 99)}"
            value = storage.get(key)
            assert value["id"] == int(key[3:])

    def test_error_handling(self, storage):
        """测试错误处理"""
        # 测试无效数据
        with pytest.raises(Exception):
            storage.set("invalid", object())
            
        # 测试正常操作不受影响
        storage.set("valid", {"value": 1})
        assert storage.get("valid") == {"value": 1}