from typing import (
    Any, Type, Dict, Tuple, Set, Optional, Callable, List, Union
)
import msgpack
from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID
from pathlib import Path
from pydantic import BaseModel
from enum import Enum
from collections import namedtuple, defaultdict, OrderedDict
from dataclasses import dataclass, field
from contextlib import contextmanager

from .object_path_registry import ObjectPathRegistry

class SerializationError(Exception):
    """序列化错误"""
    pass

@dataclass
class SerializationContext:
    """序列化上下文"""
    namespace: str
    current_path: str = ""
    parent_paths: List[str] = field(default_factory=list)

    def enter_path(self, field_name: str) -> str:
        """进入新的路径层级"""
        new_path = f"{self.current_path}.{field_name}" if self.current_path else field_name
        self.parent_paths.append(self.current_path)
        self.current_path = new_path
        return new_path

    def exit_path(self) -> str:
        """退出当前路径层级"""
        self.current_path = self.parent_paths.pop()
        return self.current_path

    @contextmanager
    def path_scope(self, field_name: str):
        """路径作用域上下文管理器"""
        try:
            self.enter_path(field_name)
            yield self.current_path
        finally:
            self.exit_path()

class Serializer:
    def __init__(self, path_registry: Optional[ObjectPathRegistry] = None):
        self._path_registry = path_registry or ObjectPathRegistry()
        
        # 基础类型处理器
        self._type_handlers = {
            datetime: (1, self._encode_datetime, self._decode_datetime),
            Decimal: (2, self._encode_decimal, self._decode_decimal),
            UUID: (3, lambda u: u.bytes, lambda data: UUID(bytes=data)),
            Path: (4, lambda p: str(p).encode(), lambda data: Path(data.decode())),
            tuple: (5, self._encode_tuple, self._decode_tuple),
            BaseModel: (6, self._encode_pydantic, self._decode_pydantic)
        }

    def dumps_with_context(self, obj: Any, namespace: str) -> bytes:
        """带上下文的序列化"""
        context = SerializationContext(namespace=namespace)
        return self.dumps(obj, context)

    def loads_with_context(self, data: bytes, namespace: str) -> Any:
        """带上下文的反序列化"""
        context = SerializationContext(namespace=namespace)
        return self.loads(data, context)

    def dumps(self, obj: Any, context: Optional[SerializationContext] = None) -> bytes:
        """序列化对象为 MessagePack 字节串"""
        def default(obj):
            # 获取类型信息
            type_info = None
            if context:
                try:
                    type_info = self._path_registry._path_types[context.namespace].get(context.current_path)
                except KeyError:
                    pass

            # 命名元组特殊处理（移到前面，优先处理）
            if hasattr(obj, '_fields'):  # 检测是否为命名元组
                return {
                    "__namedtuple__": True,
                    "__path__": context.current_path if context else "",
                    "data": dict(zip(obj._fields, obj))  # 转换为字段名和值的字典
                }

            # 其他类型处理保持不变...
            if type_info and type_info.type_metadata:
                if type_info.type_metadata.to_dict:
                    try:
                        converted = type_info.type_metadata.to_dict(obj)
                        return {
                            "__type__": type_info.type_name,
                            "__path__": context.current_path if context else "",
                            "data": converted
                        }
                    except Exception as e:
                        raise TypeError(f"序列化 {type_info.type_name} 失败: {str(e)}")
                
            # 基本类型转换
            if isinstance(obj, (list, dict, str, int, float, bool, type(None), bytes)):
                return obj
                
            raise TypeError(f"不支持的类型: {type(obj)}")

        return msgpack.packb(obj, default=default, use_bin_type=True)

    def loads(self, data: bytes, context: Optional[SerializationContext] = None) -> Any:
        """从 MessagePack 字节串反序列化对象"""
        def object_hook(obj):
            if not isinstance(obj, dict):
                return obj

            # 获取路径信息
            path = obj.get("__path__", "")
            
            # 获取类型信息
            type_info = None
            if context and path:
                try:
                    type_info = self._path_registry._path_types[context.namespace].get(path)
                except KeyError:
                    pass

            # 处理命名元组
            if "__namedtuple__" in obj:
                if type_info and type_info.type_metadata:
                    tuple_class = type_info.type_metadata.type_class
                    if isinstance(obj["data"], dict):
                        # 如果是字典格式，按字段名获取值
                        field_values = [obj["data"][field] for field in tuple_class._fields]
                    else:
                        # 如果是列表格式，直接使用
                        field_values = obj["data"]
                    return tuple_class._make(field_values)  # 使用 _make 方法创建命名元组
                return obj["data"]

            # 其他类型处理...
            if "__type__" in obj and type_info and type_info.type_metadata:
                if obj["__type__"] == type_info.type_name:
                    try:
                        if type_info.type_metadata.constructor:
                            return type_info.type_metadata.constructor(obj["data"])
                    except Exception as e:
                        raise ValueError(f"反序列化 {type_info.type_name} 失败: {str(e)}")

            return obj

        return msgpack.unpackb(data, 
                             object_hook=object_hook,
                             raw=False)

    # 类型处理器
    def _encode_datetime(self, dt: datetime) -> bytes:
        return dt.isoformat().encode()

    def _decode_datetime(self, data: bytes) -> datetime:
        return datetime.fromisoformat(data.decode())

    def _encode_decimal(self, d: Decimal) -> bytes:
        return str(d).encode()

    def _decode_decimal(self, data: bytes) -> Decimal:
        return Decimal(data.decode())

    def _encode_tuple(self, t: tuple) -> bytes:
        return msgpack.packb({
            "__tuple__": True,
            "values": list(t)
        })

    def _decode_tuple(self, data: bytes) -> tuple:
        d = msgpack.unpackb(data, raw=False)
        return tuple(d["values"])

    def _encode_pydantic(self, model: BaseModel) -> bytes:
        return msgpack.packb({
            "__model__": model.__class__.__name__,
            "data": model.model_dump()
        })

    def _decode_pydantic(self, data: bytes) -> BaseModel:
        """处理 Pydantic 模型的反序列化"""
        d = msgpack.unpackb(data, raw=False)
        model_name = d["__model__"]
        model_data = d["data"]
        
        # 从类型信息获取模型类
        if context and context.current_path:
            try:
                type_info = self._path_registry._path_types[context.namespace].get(context.current_path)
                if type_info and type_info.is_model:
                    return type_info.model_class(**model_data)
            except KeyError:
                pass
        
        # 如果没有类型信息，返回原始数据
        return model_data 