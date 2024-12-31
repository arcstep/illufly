import pytest
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Tuple
from pathlib import Path
from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from uuid import UUID

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

@dataclass
class ComplexData:
    """测试用的复杂数据类型"""
    name: str
    value: int
    tags: Set[str]
    created_at: datetime

class NestedAddress(BaseModel):
    """嵌套的地址模型"""
    street: str
    city: str
    country: str
    postal_code: Optional[str] = None
    location: Optional[Tuple[float, float]] = None  # 经纬度

class ContactInfo(BaseModel):
    """联系信息模型"""
    email: str
    phone: Optional[str] = None
    addresses: List[NestedAddress]

class ExtendedUser(BaseModel):
    """扩展的用户模型，包含更多数据类型"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    id: UUID
    name: str
    age: int
    created_at: datetime
    balance: Decimal
    tags: Set[str] = set()
    scores: Dict[str, float] = {}
    contact: ContactInfo
    preferences: Dict[str, Any] = {}
    data_path: Optional[Path] = None
    complex_data: Optional[ComplexData] = None
    status: Category = Category.A

class TestHashIndexBackend:
    """哈希索引后端测试用例"""
    
    @pytest.fixture
    def index_backend(self, tmp_path):
        """创建测试用的索引后端"""
        backend = HashIndexBackend(
            data_dir=str(tmp_path),
            segment="test_index",
            field_types={
                # 基础字段
                "id": UUID,
                "name": str,
                "age": int,
                "created_at": datetime,
                "balance": Decimal,
                
                # 集合类型
                "tags": List[str],
                "address.city": str,  # 添加嵌套字段类型
                "address.street": str,
                "price": Price,  # 添加自定义类型
                "scores": Dict[str, float],
                
                # 嵌套字段
                "contact.email": str,
                "contact.phone": str,
                "contact.addresses.street": str,
                "contact.addresses.city": str,
                "contact.addresses.country": str,
                "contact.addresses.postal_code": str,
                "contact.addresses.location": tuple,
                
                # 其他复杂字段
                "preferences": Dict[str, Any],
                "data_path": Path,
                "complex_data.name": str,
                "complex_data.value": int,
                "complex_data.tags": List[str],
                "complex_data.created_at": datetime,
            }
        )
        return backend
    
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

    def test_complex_data_types(self, index_backend):
        """测试复杂数据类型的索引"""
        # 创建测试数据
        user = ExtendedUser(
            id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            name="Alice",
            age=30,
            created_at=datetime.now(),
            balance=Decimal("1234.56"),
            tags={"python", "web", "api"},
            scores={"math": 95.5, "physics": 88.0},
            contact=ContactInfo(
                email="alice@example.com",
                phone="+1234567890",
                addresses=[
                    NestedAddress(
                        street="123 Main St",
                        city="Boston",
                        country="USA",
                        postal_code="02101",
                        location=(42.3601, -71.0589)
                    ),
                    NestedAddress(
                        street="456 Park Ave",
                        city="New York",
                        country="USA",
                        postal_code="10022"
                    )
                ]
            ),
            preferences={
                "theme": "dark",
                "notifications": True,
                "favorites": [1, 2, 3]
            },
            data_path=Path("/user/alice/data"),
            complex_data=ComplexData(
                name="test",
                value=42,
                tags={"tag1", "tag2"},
                created_at=datetime.now()
            )
        )
        
        # 更新索引
        index_backend.update_index(user, "user1")
        
        # 测试各种字段的查询
        assert index_backend.find_with_index("name", "Alice") == ["user1"]
        assert index_backend.find_with_index("age", 30) == ["user1"]
        assert index_backend.find_with_index("balance", Decimal("1234.56")) == ["user1"]
        assert index_backend.find_with_index("tags", "python") == ["user1"]
        assert index_backend.find_with_index("contact.email", "alice@example.com") == ["user1"]
        assert index_backend.find_with_index("contact.addresses.city", "Boston") == ["user1"]
        assert index_backend.find_with_index("contact.addresses.postal_code", "02101") == ["user1"]
        
        # 测试嵌套对象的更新
        new_address = NestedAddress(
            street="789 New St",
            city="Chicago",
            country="USA",
            postal_code="60601"
        )
        user.contact.addresses.append(new_address)
        index_backend.update_index(user, "user1")
        
        # 验证更新后的查询
        assert index_backend.find_with_index("contact.addresses.city", "Chicago") == ["user1"]
        
        # 测试集合类型的更新
        user.tags.add("database")
        index_backend.update_index(user, "user1")
        assert index_backend.find_with_index("tags", "database") == ["user1"]

    def test_nested_pydantic_models(self, index_backend):
        """测试嵌套的Pydantic模型"""
        # 创建具有深度嵌套的数据
        address = NestedAddress(
            street="123 Main St",
            city="Boston",
            country="USA",
            postal_code="02101",
            location=(42.3601, -71.0589)
        )
        
        contact = ContactInfo(
            email="test@example.com",
            phone="+1234567890",
            addresses=[address]
        )
        
        user = ExtendedUser(
            id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            name="Bob",
            age=25,
            created_at=datetime.now(),
            balance=Decimal("789.12"),
            contact=contact
        )
        
        # 更新索引
        index_backend.update_index(user, "user2")
        
        # 测试嵌套字段的查询
        assert index_backend.find_with_index("contact.email", "test@example.com") == ["user2"]
        assert index_backend.find_with_index("contact.addresses.city", "Boston") == ["user2"]
        assert index_backend.find_with_index("contact.addresses.location", (42.3601, -71.0589)) == ["user2"]
        
        # 测试更新嵌套字段
        user.contact.addresses[0].city = "Cambridge"
        index_backend.update_index(user, "user2")
        
        assert index_backend.find_with_index("contact.addresses.city", "Cambridge") == ["user2"]
        assert not index_backend.find_with_index("contact.addresses.city", "Boston")

    def test_collection_types(self, index_backend):
        """测试集合类型（列表、集合、字典）"""
        user = ExtendedUser(
            id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            name="Charlie",
            age=35,
            created_at=datetime.now(),
            balance=Decimal("100.00"),
            tags={"python", "java", "golang"},
            scores={"project1": 95, "project2": 88},
            contact=ContactInfo(
                email="charlie@example.com",
                addresses=[]
            )
        )
        
        # 更新索引
        index_backend.update_index(user, "user3")
        
        # 测试集合类型的查询
        assert index_backend.find_with_index("tags", "python") == ["user3"]
        assert index_backend.find_with_index("scores.project1", 95) == ["user3"]
        
        # 测试集合操作
        user.tags.remove("java")
        user.tags.add("rust")
        user.scores["project3"] = 92
        
        index_backend.update_index(user, "user3")
        
        assert index_backend.find_with_index("tags", "rust") == ["user3"]
        assert not index_backend.find_with_index("tags", "java")
        assert index_backend.find_with_index("scores.project3", 92) == ["user3"]