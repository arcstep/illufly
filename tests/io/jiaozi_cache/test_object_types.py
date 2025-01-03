import pytest
from dataclasses import dataclass
from typing import List, Dict, Optional
from pydantic import BaseModel
from datetime import datetime
from illufly.io.jiaozi_cache.object_types import (
    DataclassHandler, 
    PydanticHandler,
    TypeCategory,
    PathType
)

# ========== 测试数据定义 ==========
@dataclass
class Address:
    street: str
    city: str
    country: str

@dataclass
class UserProfile:
    name: str
    age: int
    email: Optional[str]
    created_at: datetime
    address: Address
    tags: List[str]
    settings: Dict[str, str]

class UserAddress(BaseModel):
    street: str
    city: str
    country: str

class UserModel(BaseModel):
    name: str
    age: int
    email: Optional[str]
    created_at: datetime
    address: UserAddress
    tags: List[str]
    settings: Dict[str, str]

# ========== Dataclass 测试 ==========
class TestDataclassHandler:
    @pytest.fixture
    def handler(self):
        return DataclassHandler()
    
    def test_can_handle(self, handler):
        """测试类型识别"""
        assert handler.can_handle(UserProfile)
        assert handler.can_handle(Address)
        assert not handler.can_handle(UserModel)
        assert not handler.can_handle(dict())
    
    def test_get_type_info(self, handler):
        """测试类型信息获取"""
        type_info = handler.get_type_info(UserProfile)
        assert type_info.type_name == "UserProfile"
        assert type_info.category == TypeCategory.STRUCTURE
        assert not type_info.is_container
        
        type_info = handler.get_type_info(Address)
        assert type_info.type_name == "Address"
        assert type_info.category == TypeCategory.STRUCTURE
    
    def test_get_paths(self, handler):
        """测试路径生成"""
        paths = handler.get_paths(UserProfile)
        expected_paths = {
            "",                  # 根路径
            "name",
            "age",
            "email",
            "created_at",
            "address",
            "tags",
            "settings"
        }
        
        # 收集实际路径
        actual_paths = {p[0] for p in paths}
        assert expected_paths == actual_paths
        
        # 验证路径类型
        for path, type_name, path_type, access_method in paths:
            assert path_type == PathType.REVERSIBLE
            assert access_method == "dot"
    
    def test_get_nested_fields(self, handler):
        """测试嵌套字段获取"""
        nested_fields = handler.get_nested_fields(UserProfile)
        assert len(nested_fields) == 1
        field_name, field_type = nested_fields[0]
        assert field_name == "address"
        assert field_type == Address
    
    def test_extract_value(self, handler):
        """测试值提取"""
        from illufly.io.jiaozi_cache.path_parser import PathSegment, SegmentType
        
        address = Address(street="123 Main St", city="City", country="Country")
        user = UserProfile(
            name="Test User",
            age=30,
            email="test@example.com",
            created_at=datetime.now(),
            address=address,
            tags=["tag1", "tag2"],
            settings={"theme": "dark"}
        )
        
        # 测试基本属性访问
        segment = PathSegment(type=SegmentType.ATTRIBUTE, value="name", original="name", access_method="dot")
        assert handler.extract_value(user, segment) == "Test User"
        
        # 测试嵌套属性访问
        segment = PathSegment(type=SegmentType.ATTRIBUTE, value="address", original="address", access_method="dot")
        assert handler.extract_value(user, segment) == address

# ========== Pydantic 测试 ==========
class TestPydanticHandler:
    @pytest.fixture
    def handler(self):
        return PydanticHandler()
    
    def test_can_handle(self, handler):
        """测试类型识别"""
        assert handler.can_handle(UserModel)
        assert handler.can_handle(UserAddress)
        assert not handler.can_handle(UserProfile)
        assert not handler.can_handle(dict())
    
    def test_get_type_info(self, handler):
        """测试类型信息获取"""
        type_info = handler.get_type_info(UserModel)
        assert type_info.type_name == "UserModel"
        assert type_info.category == TypeCategory.STRUCTURE
        assert not type_info.is_container
        
        type_info = handler.get_type_info(UserAddress)
        assert type_info.type_name == "UserAddress"
        assert type_info.category == TypeCategory.STRUCTURE
    
    def test_get_paths(self, handler):
        """测试路径生成"""
        paths = handler.get_paths(UserModel)
        expected_paths = {
            "",                  # 根路径
            "name",
            "age",
            "email",
            "created_at",
            "address",
            "tags",
            "settings"
        }
        
        # 收集实际路径
        actual_paths = {p[0] for p in paths}
        assert expected_paths == actual_paths
        
        # 验证路径类型
        for path, type_name, path_type, access_method in paths:
            assert path_type == PathType.REVERSIBLE
            assert access_method == "dot"
    
    def test_get_nested_fields(self, handler):
        """测试嵌套字段获取"""
        nested_fields = handler.get_nested_fields(UserModel)
        assert len(nested_fields) == 1
        field_name, field_type = nested_fields[0]
        assert field_name == "address"
        assert field_type == UserAddress
    
    def test_extract_value(self, handler):
        """测试值提取"""
        from illufly.io.jiaozi_cache.path_parser import PathSegment, SegmentType
        
        address = UserAddress(street="123 Main St", city="City", country="Country")
        user = UserModel(
            name="Test User",
            age=30,
            email="test@example.com",
            created_at=datetime.now(),
            address=address,
            tags=["tag1", "tag2"],
            settings={"theme": "dark"}
        )
        
        # 测试基本属性访问
        segment = PathSegment(type=SegmentType.ATTRIBUTE, value="name", original="name", access_method="dot")
        assert handler.extract_value(user, segment) == "Test User"
        
        # 测试嵌套属性访问
        segment = PathSegment(type=SegmentType.ATTRIBUTE, value="address", original="address", access_method="dot")
        assert handler.extract_value(user, segment) == address 