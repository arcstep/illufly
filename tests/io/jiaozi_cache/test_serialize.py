import pytest
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pathlib import Path
from enum import Enum
from collections import namedtuple, defaultdict, OrderedDict
from dataclasses import dataclass
from typing import List, Dict, Any
from pydantic import BaseModel
from illufly.io.jiaozi_cache import (
    Serializer,
    ObjectPathRegistry,
    PathType,
    TypeMetadata,
    SerializationContext
)

# 测试用的类型定义
class TestEnum(Enum):
    VALUE1 = "value1"
    VALUE2 = "value2"

class TestModel(BaseModel):
    name: str
    value: int

TestNamedTuple = namedtuple('TestNamedTuple', ['x', 'y'])

@dataclass
class TestCustomClass:
    name: str
    value: int
    
    def to_dict(self):
        return {"name": self.name, "value": self.value}
    
    @classmethod
    def from_dict(cls, data):
        return cls(**data)

# Fixtures
@pytest.fixture
def path_registry():
    registry = ObjectPathRegistry()
    
    # 注册 Pydantic 模型
    registry.register_object(TestModel, namespace="test")
    
    # 注册命名元组 - 使用 register_object 而不是 register_path
    registry.register_object(TestNamedTuple, namespace="test")
    
    # 注册自定义类
    registry.register_object(TestCustomClass, namespace="test")
    
    return registry

@pytest.fixture
def serializer(path_registry):
    return Serializer(path_registry)

def test_basic_types(serializer):
    """测试基本类型的序列化"""
    test_cases = [
        ("string", "test"),
        ("integer", 42),
        ("float", 3.14),
        ("boolean", True),
        ("none", None),
        ("list", [1, 2, 3]),
        ("dict", {"key": "value"}),
        ("bytes", b"binary data")
    ]
    
    for path, value in test_cases:
        context = SerializationContext(namespace="test", current_path=path)
        serialized = serializer.dumps(value, context)
        assert isinstance(serialized, bytes)  # 确保输出是字节串
        deserialized = serializer.loads(serialized, context)
        assert value == deserialized

def test_complex_types(serializer):
    """测试复杂类型的序列化"""
    # Pydantic 模型
    model = TestModel(name="test", value=42)
    context = SerializationContext(namespace="test", current_path="")  # 使用空路径
    serialized = serializer.dumps(model, context)
    assert isinstance(serialized, bytes)
    deserialized = serializer.loads(serialized, context)
    assert isinstance(deserialized, TestModel)
    assert model.model_dump() == deserialized.model_dump()
    
    # 命名元组
    nt = TestNamedTuple(1, 2)
    context = SerializationContext(namespace="test", current_path="")  # 使用空路径
    serialized = serializer.dumps(nt, context)
    assert isinstance(serialized, bytes)
    deserialized = serializer.loads(serialized, context)
    assert isinstance(deserialized, TestNamedTuple)
    assert nt == deserialized
    
    # 自定义类
    custom = TestCustomClass("test", 42)
    context = SerializationContext(namespace="test", current_path="")  # 使用空路径
    serialized = serializer.dumps(custom, context)
    assert isinstance(serialized, bytes)
    deserialized = serializer.loads(serialized, context)
    assert isinstance(deserialized, TestCustomClass)
    assert custom.to_dict() == deserialized.to_dict()

def test_nested_structures(serializer):
    """测试嵌套结构的序列化"""
    data = {
        "model": TestModel(name="test", value=42),
        "tuple": TestNamedTuple(1, 2),
        "custom": TestCustomClass("test", 42),
        "list": [1, TestModel(name="nested", value=100)],
        "dict": {"key": TestCustomClass("nested", 200)}
    }
    
    context = SerializationContext(namespace="test")
    serialized = serializer.dumps(data, context)
    assert isinstance(serialized, bytes)
    deserialized = serializer.loads(serialized, context)
    
    # 验证嵌套结构
    assert isinstance(deserialized["model"], TestModel)
    assert isinstance(deserialized["tuple"], TestNamedTuple)
    assert isinstance(deserialized["custom"], TestCustomClass)
    assert isinstance(deserialized["list"][1], TestModel)
    assert isinstance(deserialized["dict"]["key"], TestCustomClass)

def test_binary_data(serializer):
    """测试二进制数据的序列化"""
    binary_data = b"\x00\x01\x02\x03"
    context = SerializationContext(namespace="test", current_path="binary")
    serialized = serializer.dumps(binary_data, context)
    assert isinstance(serialized, bytes)
    deserialized = serializer.loads(serialized, context)
    assert binary_data == deserialized

def test_error_handling(serializer):
    """测试错误处理"""
    # 未注册的类型
    class UnregisteredClass:
        pass
    
    with pytest.raises(TypeError):
        serializer.dumps(UnregisteredClass(), SerializationContext(namespace="test"))
    
    # 无效的 MessagePack 数据
    with pytest.raises(Exception):
        serializer.loads(b"invalid data", SerializationContext(namespace="test"))
