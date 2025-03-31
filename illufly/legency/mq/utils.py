from typing import Union, Any, Type
from pydantic import BaseModel

import json
import threading

def serialize(_cls=None):
    """无括号类装饰器（与service_method保持相同风格）"""
    def decorator(cls: Type[BaseModel]):
        # 类型安全检查
        if not issubclass(cls, BaseModel):
            raise ValueError(f"Class {cls.__name__} 必须继承自BaseModel")
        
        # 自动注册
        ZmqMessageTypeRegistry.register(cls.__name__, cls)
        return cls

    # 处理无括号调用
    if _cls is None:
        return decorator
    return decorator(_cls)

# 消息类型注册表（改为类实现）
class ZmqMessageTypeRegistry:
    _registry = {}
    _lock = threading.Lock()

    @classmethod
    def register(cls, type_name: str, model_class):
        with cls._lock:
            cls._registry[type_name] = model_class

    @classmethod
    def unregister(cls, type_name: str):
        with cls._lock:
            cls._registry.pop(type_name, None)

    @classmethod
    def get_registry(cls):
        return cls._registry.copy()  # 返回副本保证线程安全

def serialize_message(obj: Union[BaseModel, dict]) -> bytes:
    """序列化消息，包含类型信息"""
    if isinstance(obj, BaseModel):
        data = {
            '__type__': obj.__class__.__name__,
            'data': obj.model_dump()
        }
    else:
        data = obj
    return json.dumps(data).encode()

def deserialize_message(data: bytes) -> Union[BaseModel, dict]:
    """反序列化消息，根据类型信息还原对象"""
    try:
        parsed = json.loads(data.decode())
        if isinstance(parsed, dict) and '__type__' in parsed:
            msg_type = parsed['__type__']
            if msg_type in ZmqMessageTypeRegistry._registry:
                cls = ZmqMessageTypeRegistry._registry[msg_type]
                # 使用 model_validate 进行反序列化
                return cls.model_validate(parsed['data'])
        return parsed
    except Exception as e:
        raise ValueError(f"Failed to deserialize message: {e}")
