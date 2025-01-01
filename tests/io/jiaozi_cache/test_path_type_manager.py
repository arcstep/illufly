from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pathlib import Path
import pytest
from pydantic import BaseModel
from dataclasses import dataclass
from illufly.io.jiaozi_cache.path_type_manager import (
    PathTypeManager,
    PathTypeInfo,
    PathNotFoundError,
    PathValidationError,
    PathTypeError,
    PathType
)

# 测试用的类型定义
class SimpleModel(BaseModel):
    """简单模型，用于基础测试"""
    name: str
    value: int

@dataclass
class MockIndexable:
    """可索引对象"""
    id: int
    
    def to_index_key(self) -> str:
        return f"idx_{self.id}"

@pytest.fixture
def manager():
    """创建管理器"""
    return PathTypeManager()

@pytest.fixture
def complex_data():
    """创建复杂测试数据"""
    return {
        "string": "hello",
        "number": 42,
        "nested": {
            "coordinates": [1, 2, 3],
            "point": {"x": 10, "y": 20}
        },
        "arrays": {
            "simple": [1, 2, 3],
            "objects": [
                {"id": 1, "name": "first"},
                {"id": 2, "name": "second"}
            ]
        }
    }

def test_register_object(manager):
    """测试对象注册"""
    model = SimpleModel(name="test", value=123)
    manager.register_object(model)
    
    # 验证自动注册的路径
    assert "name" in manager._path_types["SimpleModel"]
    assert "value" in manager._path_types["SimpleModel"]
    
    # 验证类型信息
    name_info = manager._path_types["SimpleModel"]["name"]
    assert name_info.type_name == "str"
    
    value_info = manager._path_types["SimpleModel"]["value"]
    assert value_info.type_name == "int"

def test_extract_basic_values(manager, complex_data):
    """测试基础值提取"""
    manager.register_object(complex_data, namespace="root")
    
    test_cases = [
        ("string", "hello"),
        ("number", 42),
        ("nested.coordinates[0]", 1),
        ("nested.point.x", 10),
        ("arrays.objects[1].name", "second"),
    ]
    
    for path, expected in test_cases:
        value, _ = manager.extract_and_convert_value(complex_data, path, namespace="root")
        assert value == expected

def test_extract_with_type_conversion(manager, complex_data):
    """测试类型转换"""
    manager.register_object(
        complex_data,
        namespace="root",
        path_configs={
            "number": {"type_name": "float"}
        }
    )
    
    value, _ = manager.extract_and_convert_value(complex_data, "number", namespace="root")
    assert isinstance(value, float)
    assert value == 42.0

def test_extract_tag_list(manager):
    """测试标签列表"""
    data = {"tags": ["tag1", "tag2", "tag3"]}
    
    manager.register_object(
        data,
        namespace="test",
        path_configs={
            "tags": {
                "is_tag_list": True,
                "max_tags": 2
            }
        }
    )
    
    value, _ = manager.extract_and_convert_value(data, "tags", namespace="test")
    assert value == ["tag1", "tag2"]

def test_register_nested_model(manager):
    """测试嵌套模型注册"""
    class Address(BaseModel):
        street: str
        city: str
        
    class User(BaseModel):
        name: str
        address: Address
        
    user = User(
        name="test",
        address=Address(street="Test St", city="Test City")
    )
    
    manager.register_object(user)
    
    # 验证嵌套路径
    assert "name" in manager._path_types["User"]
    assert "address.street" in manager._path_types["User"]
    assert "address.city" in manager._path_types["User"]

def test_error_handling(manager, complex_data):
    """测试错误处理"""
    manager.register_object(complex_data, namespace="root")
    
    # 测试无效路径
    with pytest.raises(PathNotFoundError) as exc_info:
        manager.extract_and_convert_value(complex_data, "invalid.path", namespace="root")
    assert "invalid" in str(exc_info.value)
    
    # 测试类型转换失败
    manager.register_object(
        complex_data,
        namespace="root",
        path_configs={
            "string": {"type_name": "int"}
        }
    )
    with pytest.raises(PathTypeError) as exc_info:
        manager.extract_and_convert_value(complex_data, "string", namespace="root")
    assert "期望类型为 int" in str(exc_info.value)

def test_register_dict_structure(manager):
    """测试字典结构注册"""
    data = {
        "user": {
            "name": "test",
            "scores": [
                {"subject": "math", "value": 90},
                {"subject": "english", "value": 85}
            ]
        }
    }
    
    manager.register_object(data, namespace="Config")
    
    # 验证路径注册
    assert "user.name" in manager._path_types["Config"]
    assert "user.scores[*].subject" in manager._path_types["Config"]
    assert "user.scores[*].value" in manager._path_types["Config"]

def test_tag_list_validation(manager):
    """测试标签列表验证"""
    # 测试有效的标签列表
    class ValidTags(BaseModel):
        tags: List[str]
    
    model = ValidTags(tags=["tag1", "tag2", "tag3"])
    manager.register_object(
        model,
        path_configs={
            "tags": {
                "is_tag_list": True,
                "max_tags": 2
            }
        }
    )
    
    value, _ = manager.extract_and_convert_value(model, "tags", namespace="ValidTags")
    assert value == ["tag1", "tag2"]
    
    # 测试无效的标签列表类型
    class InvalidTags(BaseModel):
        tags: List[int]
    
    model = InvalidTags(tags=[1, 2, 3])
    with pytest.raises(PathValidationError) as exc_info:
        manager.register_object(
            model,
            path_configs={
                "tags": {
                    "is_tag_list": True
                }
            }
        )
    assert "元素类型必须是字符串" in str(exc_info.value)

def test_register_model_class(manager):
    """测试直接注册模型类"""
    class Address(BaseModel):
        street: str
        city: str
        
    class User(BaseModel):
        name: str
        age: int
        address: Address
        tags: List[str]
    
    # 直接注册模型类
    manager.register_object(
        User,  # 注册类而不是实例
        path_configs={
            "tags": {
                "is_tag_list": True,
                "max_tags": 2
            }
        }
    )
    
    # 验证路径注册
    assert "name" in manager._path_types["User"]
    assert "age" in manager._path_types["User"]
    assert "address.street" in manager._path_types["User"]
    assert "address.city" in manager._path_types["User"]
    assert "tags" in manager._path_types["User"]
    
    # 验证标签列表配置
    tags_info = manager._path_types["User"]["tags"]
    assert tags_info.is_tag_list
    assert tags_info.max_tags == 2

def test_path_validation_errors(manager):
    """测试路径验证错误"""
    class User(BaseModel):
        name: str
        scores: List[int]
    
    user = User(name="test", scores=[1, 2, 3])
    manager.register_object(user)
    
    # 测试无效路径
    with pytest.raises(PathNotFoundError) as exc_info:
        manager.extract_and_convert_value(user, "invalid.path", namespace="User")
    assert "找不到路径" in str(exc_info.value)
    assert exc_info.value.invalid_part == "invalid"
    
    # 测试无效索引
    with pytest.raises(PathValidationError) as exc_info:
        manager.extract_and_convert_value(user, "scores[invalid]", namespace="User")
    assert "无效的数组索引" in str(exc_info.value)
    
    # 测试索引越界
    with pytest.raises(PathValidationError) as exc_info:
        manager.extract_and_convert_value(user, "scores[10]", namespace="User")
    assert "超出范围" in str(exc_info.value)
    
    # 测试类型错误
    with pytest.raises(PathTypeError) as exc_info:
        manager.extract_and_convert_value(user, "name[0]", namespace="User")
    assert "期望类型为 list/tuple" in str(exc_info.value)

def test_path_registration_validation(manager):
    """测试路径注册验证"""
    # 测试空路径
    with pytest.raises(PathValidationError) as exc_info:
        manager.register_path(
            path="",
            type_name="str",
            namespace="test",
            path_type=PathType.INDEXABLE
        )
    assert "路径不能为空" in str(exc_info.value)
    
    # 测试空命名空间
    with pytest.raises(PathValidationError) as exc_info:
        manager.register_path(
            path="test",
            type_name="str",
            namespace="",
            path_type=PathType.INDEXABLE
        )
    assert "命名空间不能为空" in str(exc_info.value)
    
    # 测试无效的标签列表类型
    with pytest.raises(PathValidationError) as exc_info:
        manager.register_path(
            path="test",
            type_name="dict",
            namespace="test",
            path_type=PathType.STRUCTURAL,
            is_tag_list=True
        )
    assert "标签列表路径" in str(exc_info.value)
    assert "必须是可索引类型" in str(exc_info.value)

def test_indexable_paths(manager):
    """测试可索引路径识别"""
    class Address(BaseModel):
        street: str          # 可索引
        number: int         # 可索引
        location: Dict[str, float]  # 结构类型
        
    class User(BaseModel):
        name: str           # 可索引
        age: int           # 可索引
        scores: List[int]   # 可索引（基础类型列表）
        tags: List[str]     # 可索引（标签列表）
        address: Address    # 结构类型
        friends: List[Address]  # 结构类型
    
    manager.register_object(User)
    
    # 获取所有可索引路径
    indexable_paths = manager.get_indexable_paths("User")
    
    # 验证可索引路径
    assert "name" in indexable_paths
    assert "age" in indexable_paths
    assert "scores" in indexable_paths
    assert "tags" in indexable_paths
    assert "address.street" in indexable_paths
    assert "address.number" in indexable_paths
    
    # 验证结构路径不在可索引路径中
    assert "address" not in indexable_paths
    assert "friends" not in indexable_paths
    assert "address.location" not in indexable_paths

def test_path_type_validation(manager):
    """测试路径类型验证"""
    class Item(BaseModel):
        tags: List[Dict[str, str]]  # 复合类型的列表
    
    with pytest.raises(PathValidationError) as exc_info:
        manager.register_object(
            Item,
            path_configs={
                "tags": {
                    "is_tag_list": True  # 不能将复合类型的列表标记为标签列表
                }
            }
        )
    assert "元素类型必须是字符串" in str(exc_info.value)

def test_value_extraction_for_indexing(manager):
    """测试用于索引的值提取"""
    class User(BaseModel):
        name: str
        age: int
        tags: List[str]
        profile: Dict[str, Any]
    
    user = User(
        name="test",
        age=25,
        tags=["tag1", "tag2"],
        profile={"type": "premium"}
    )
    
    manager.register_object(user)
    
    # 提取可索引值
    name_value, _ = manager.extract_and_convert_value(user, "name", namespace="User")
    assert name_value == "test"
    
    # 提取标签列表
    tags_value, _ = manager.extract_and_convert_value(user, "tags", namespace="User")
    assert tags_value == ["tag1", "tag2"]
    
    # 提取结构类型应该引发错误
    with pytest.raises(PathTypeError) as exc_info:
        manager.extract_and_convert_value(user, "profile", namespace="User")
    assert "期望类型为 indexable，实际类型为 structural" in str(exc_info.value)