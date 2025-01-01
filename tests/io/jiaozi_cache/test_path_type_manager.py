from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pathlib import Path
import pytest
from pydantic import BaseModel
from dataclasses import dataclass
from illufly.io.jiaozi_cache.path_type_manager import PathTypeManager, PathTypeInfo

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
    value, parts = manager.extract_and_convert_value(complex_data, "invalid.path", namespace="root")
    assert value is None
    assert parts == ["invalid"]
    
    # 测试类型转换失败
    manager.register_object(
        complex_data,
        namespace="root",
        path_configs={
            "string": {"type_name": "int"}
        }
    )
    value, _ = manager.extract_and_convert_value(complex_data, "string", namespace="root")
    assert value is None

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
    with pytest.raises(ValueError, match="标签列表.*的元素类型必须是字符串"):
        manager.register_object(
            model,
            path_configs={
                "tags": {
                    "is_tag_list": True
                }
            }
        )
    
    # 测试非列表字段标记为标签列表
    class NotList(BaseModel):
        tags: str
    
    model = NotList(tags="not a list")
    with pytest.raises(ValueError, match="被标记为标签列表，但类型不是列表"):
        manager.register_object(
            model,
            path_configs={
                "tags": {
                    "is_tag_list": True
                }
            }
        )