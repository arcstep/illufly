import pytest
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict
from decimal import Decimal

from illufly.io.jiaozi_cache.index import HashIndexBackend, IndexConfig, Indexable

class Price(Indexable):
    """可索引的价格类型"""
    def __init__(self, amount: Optional[Decimal] = None, currency: str = "USD"):
        self.amount = amount
        self.currency = currency
        
    def to_index_key(self) -> str:
        """转换为索引键"""
        if self.amount is None:
            return f"0.0_{self.currency}"  # 处理 None 值的情况
        return f"{float(self.amount)}_{self.currency}"
        
    def __eq__(self, other):
        if not isinstance(other, Price):
            return False
        if self.amount is None and other.amount is None:
            return self.currency == other.currency
        return self.amount == other.amount and self.currency == other.currency

    def __str__(self):
        """字符串表示"""
        return self.to_index_key()

@dataclass
class Address:
    """测试用的地址类"""
    street: str
    city: str

class User(BaseModel):
    """测试用的用户模型"""
    model_config = ConfigDict(arbitrary_types_allowed=True)  # 允许任意类型
    
    name: str
    age: int
    tags: List[str] = []
    address: Address = None
    price: Price = None

class Category(Enum):
    A = "A"
    B = "B"

class TestHashIndexBackend:
    """哈希索引后端测试用例"""
    
    @pytest.fixture
    def index_backend(self, tmp_path) -> HashIndexBackend:
        """创建测试用的索引后端实例"""
        return HashIndexBackend(
            data_dir=str(tmp_path),
            segment="test_index",
            field_types={
                "name": str,
                "age": int,
                "tags": List[str],
                "address.street": str,
                "address.city": str,
                "price": Price,
                ".": Price,
            }
        )
    
    def test_init(self, index_backend):
        """测试初始化"""
        assert index_backend is not None
        assert isinstance(index_backend, HashIndexBackend)
        
    def test_basic_operations(self, index_backend):
        """测试基本操作：添加/查询/更新/删除"""
        # 创建测试数据
        user = User(
            name="Alice",
            age=25,
            tags=["python", "web"],
            address=Address(street="123 Main St", city="Boston"),
            price=Price(Decimal("10.99"), "USD")
        )
        
        # 更新索引
        index_backend.update_index(user, "user1")
        
        # 通过不同路径查询
        assert index_backend.find_with_index("name", "Alice") == ["user1"]
        assert index_backend.find_with_index("age", 25) == ["user1"]
        assert index_backend.find_with_index("address.city", "Boston") == ["user1"]
        assert index_backend.find_with_index("tags", "python") == ["user1"]
        
        # 更新用户数据
        user.age = 26
        user.address.city = "New York"
        index_backend.update_index(user, "user1")
        
        # 验证更新后的查询
        assert index_backend.find_with_index("age", 26) == ["user1"]
        assert index_backend.find_with_index("address.city", "New York") == ["user1"]
        assert not index_backend.find_with_index("age", 25)
        assert not index_backend.find_with_index("address.city", "Boston")

    def test_root_object_query(self, index_backend):
        """测试根对象查询 - 使用可索引对象"""
        # 创建价格对象
        price1 = Price(Decimal("10.99"), "USD")
        price2 = Price(Decimal("15.99"), "EUR")
        
        # 直接索引价格对象
        index_backend.update_index(price1, "price1")
        index_backend.update_index(price2, "price2")
        
        # 使用相同价格对象查询
        query_price = Price(Decimal("10.99"), "USD")
        results = index_backend.find_with_index(".", query_price)
        assert results == ["price1"]

    def test_indexable_field_query(self, index_backend):
        """测试可索引字段查询"""
        # 创建带价格的用户
        user1 = User(
            name="Alice",
            age=25,
            price=Price(Decimal("10.99"), "USD")
        )
        user2 = User(
            name="Bob",
            age=30,
            price=Price(Decimal("15.99"), "EUR")
        )
        
        # 添加到索引
        index_backend.update_index(user1, "user1")
        index_backend.update_index(user2, "user2")
        
        # 通过价格查询
        query_price = Price(Decimal("10.99"), "USD")
        results = index_backend.find_with_index("price", query_price)
        assert results == ["user1"]

    def test_nested_path_query(self, index_backend):
        """测试嵌套路径查询"""
        users = [
            User(
                name="Charlie",
                age=35,
                address=Address(street="321 Elm St", city="Chicago")
            ),
            User(
                name="David",
                age=28,
                address=Address(street="654 Maple St", city="Chicago")
            )
        ]
        
        # 添加到索引
        for i, user in enumerate(users):
            index_backend.update_index(user, f"user{i+4}")
            
        # 通过城市查询
        chicago_users = index_backend.find_with_index("address.city", "Chicago")
        assert len(chicago_users) == 2
        assert set(chicago_users) == {"user4", "user5"}

    def test_tag_operations(self, index_backend):
        """测试标签操作"""
        user = User(
            name="Eve",
            age=27,
            tags=["python", "docker", "kubernetes"]
        )
        
        # 添加到索引
        index_backend.update_index(user, "user6")
        
        # 通过不同标签查询
        assert index_backend.find_with_index("tags", "python") == ["user6"]
        assert index_backend.find_with_index("tags", "docker") == ["user6"]
        assert index_backend.find_with_index("tags", "kubernetes") == ["user6"]
        
        # 更新标签
        user.tags = ["python", "aws", "terraform"]
        index_backend.update_index(user, "user6")
        
        # 验证标签更新
        assert index_backend.find_with_index("tags", "python") == ["user6"]
        assert index_backend.find_with_index("tags", "aws") == ["user6"]
        assert not index_backend.find_with_index("tags", "docker")