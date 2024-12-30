import pytest
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from pydantic import BaseModel
from decimal import Decimal

from illufly.io.jiaozi_cache import CachedJSONStorage, HashIndexBackend, Indexable

class Category(Enum):
    A = "a"
    B = "b"

@dataclass
class Product(Indexable):
    id: str
    category: str
    price: Decimal
    
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

class UserProfile(BaseModel):
    user_id: str
    group: str
    level: int
    
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

@pytest.fixture
def index_backend(tmp_path) -> HashIndexBackend:
    """创建测试用的哈希索引后端"""
    return HashIndexBackend(
        data_dir=str(tmp_path),
        segment="test_index.json",
        field_types={"value": str, "group": str}  # 定义索引字段类型
    )

class TestHashIndexBackend:
    """哈希索引后端测试用例"""
    
    def test_init(self, index_backend):
        """测试初始化"""
        assert index_backend._storage is not None
        assert isinstance(index_backend._storage, CachedJSONStorage)
        assert index_backend._field_types == {"value": str, "group": str}
        
    def test_basic_operations(self, index_backend):
        """测试基本操作：添加/获取/删除"""
        # 测试数据
        test_data = {"value": "test1", "group": "A"}
        
        # 添加
        index_backend.add("key1", test_data)
        assert index_backend.get("key1") == test_data
        
        # 更新
        test_data["value"] = 43
        index_backend.add("key1", test_data)
        assert index_backend.get("key1")["value"] == 43
        
        # 删除
        index_backend.remove("key1")
        assert index_backend.get("key1") is None
        
        # 不存在的键
        assert index_backend.get("nonexistent") is None
        
    def test_list_keys(self, index_backend):
        """测试列出所有键"""
        # 添加测试数据
        data = {
            "key1": {"value": 1},
            "key2": {"value": 2},
            "key3": {"value": 3}
        }
        
        for key, value in data.items():
            index_backend.add(key, value)
            
        keys = index_backend.list_keys()
        assert len(keys) == 3
        assert set(keys) == {"key1", "key2", "key3"}
        
    def test_clear(self, index_backend):
        """测试清空索引"""
        # 添加测试数据
        index_backend.add("key1", {"value": 1})
        index_backend.add("key2", {"value": 2})
        
        # 清空
        index_backend.clear()
        assert len(index_backend.list_keys()) == 0
        assert index_backend.get("key1") is None
                
    def test_complex_types(self, index_backend):
        """测试复杂数据类型"""
        # Enum
        index_backend.add("enum_key", Category.A)
        retrieved_enum = index_backend.get("enum_key")
        assert retrieved_enum["value"] == "a"
        
        # Dataclass with Indexable
        product = Product(id="p1", category="A", price=Decimal("99.99"))
        index_backend.add("product_key", product)
        retrieved_product = index_backend.get("product_key")
        assert retrieved_product["category"] == "A"
        
        # Pydantic Model with Indexable
        user = UserProfile(user_id="u1", group="admin", level=1)
        index_backend.add("user_key", user)
        retrieved_user = index_backend.get("user_key")
        assert retrieved_user["group"] == "admin"
        
        # 嵌套数据
        nested_data = {
            "metadata": {
                "category": "A",
                "product": product,
                "user": user
            }
        }
        index_backend.add("nested_key", nested_data)
        retrieved_nested = index_backend.get("nested_key")
        assert retrieved_nested["metadata"]["product"]["category"] == "A"
        
    @pytest.mark.performance
    def test_batch_performance(self, index_backend):
        """测试批量操作性能"""
        # 生成测试数据
        num_items = 1000
        start_time = datetime.now()
        
        # 批量添加
        for i in range(num_items):
            index_backend.add(f"key{i}", {"value": i, "group": i % 10})
            
        duration = (datetime.now() - start_time).total_seconds()
        
        # 验证性能
        assert duration < 5  # 应在5秒内完成
        assert len(index_backend.list_keys()) == num_items