import pytest
import json
from datetime import datetime
from pydantic import BaseModel
from illufly.mq.utils import serialize, serialize_message, deserialize_message

# 测试模型定义
@serialize
class SimpleMessage(BaseModel):
    id: int
    content: str
    optional_field: str | None = None
    timestamp: float

    @property
    def created_at(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)

@serialize
class NestedMessage(BaseModel):
    parent_id: str
    child: SimpleMessage

# 基础测试用例
@pytest.mark.parametrize("original", [
    {
        "id": 1,
        "content": "Hello World",
        "timestamp": 1717029123.456
    },
    ["Hello", "World"],
    {"key": "value"},
    None,
    True,
    False
])
def test_python_objects_serialization(original):
    """测试Python对象序列化-反序列化循环"""
    serialized = serialize_message(original)
    deserialized = deserialize_message(serialized)
    
    assert deserialized == original

def test_basic_serialization_roundtrip():
    """测试基本模型序列化-反序列化循环"""
    original = SimpleMessage(
        id=1,
        content="Hello World",
        timestamp=1717029123.456
    )
    
    # 序列化流程
    serialized = serialize_message(original)
    deserialized = deserialize_message(serialized)
    
    assert isinstance(deserialized, SimpleMessage)
    assert deserialized.model_dump() == original.model_dump()

def test_nested_model_serialization():
    """测试嵌套模型序列化"""
    child = SimpleMessage(id=2, content="Child", timestamp=1717029123.456)
    parent = NestedMessage(parent_id="parent-123", child=child)
    
    serialized = serialize_message(parent)
    deserialized = deserialize_message(serialized)
    
    assert deserialized.parent_id == "parent-123"
    assert isinstance(deserialized.child, SimpleMessage)
    assert deserialized.child.id == 2

# 复杂处理链路测试
def test_full_processing_chain():
    """测试完整处理链路：对象→序列化→JSON→传输→反序列化"""
    original = SimpleMessage(
        id=3,
        content="Special Characters: \n\t\u2605",
        timestamp=1717029123.456
    )
    
    # 完整处理流程
    serialized_bytes = serialize_message(original)
    json_str = serialized_bytes.decode('utf-8')
    reloaded_bytes = json_str.encode('utf-8')
    reconstructed = deserialize_message(reloaded_bytes)
    
    assert reconstructed.content == original.content
    assert abs(reconstructed.timestamp - original.timestamp) < 0.001

# 异常情况测试
def test_json_incompatible_types():
    """测试JSON不兼容类型的处理"""
    class NonSerializable:
        def __init__(self, value):
            self.value = value
    
    # 构造包含非JSON类型的字典
    invalid_data = {
        '__type__': 'SimpleMessage',
        'data': {
            'id': 4,
            'content': datetime.now(),  # datetime对象无法直接JSON序列化
            'timestamp': 1717029123.456
        }
    }
    
    with pytest.raises(TypeError):
        serialize_message(invalid_data)

def test_unregistered_type_handling():
    """测试未注册类型的反序列化处理"""
    valid_json = json.dumps({
        '__type__': 'UnknownType',
        'data': {'field': 'value'}
    }).encode()
    
    result = deserialize_message(valid_json)
    assert isinstance(result, dict)
    assert result['data']['field'] == 'value'

# 边界条件测试
def test_empty_string_content():
    """测试空字符串内容"""
    original = SimpleMessage(
        id=5,
        content="",
        timestamp=0.0
    )
    
    deserialized = deserialize_message(serialize_message(original))
    assert deserialized.content == ""

def test_missing_optional_field():
    """测试可选字段缺失的情况"""
    data = {
        '__type__': 'SimpleMessage',
        'data': {
            'id': 6,
            'content': "Missing optional",
            'timestamp': 1.0
        }
    }
    
    serialized = json.dumps(data).encode()
    result = deserialize_message(serialized)
    assert result.optional_field is None