from typing import Dict, Any, Optional, List, Callable, Type, Union, Tuple
from dataclasses import is_dataclass, asdict
from datetime import datetime
from contextlib import contextmanager
from typing import get_origin, get_args
from pydantic import BaseModel, Field
from collections import OrderedDict
from pathlib import Path

import inspect
import json
import threading
import logging

from ...config import get_env
from .store import StorageBackend, JSONFileStorageBackend
from .index import IndexBackend, HashIndexBackend, CompositeIndexBackend, IndexType, COMPARE_OPS, RANGE_OPS
from .cache import LRUCacheBackend

class JiaoziCache():
    """
    JiaoziCache 提供了一个高性能的缓存和持久化存储解决方案。
    支持索引查询、LRU缓存、JSON文件存储等功能。
    """
    
    def __init__(
        self,
        data_class: Type,
        index_config: Optional[Dict[str, IndexType]] = None,
        cache_backend: Optional[LRUCacheBackend] = None,
        storage_backend: Optional[StorageBackend] = None,
        index_backend: Optional[IndexBackend] = None,
        serializer: Optional[Callable[[Any], Dict[str, Any]]] = None,
        deserializer: Optional[Callable[[Dict[str, Any]], Any]] = None,
        logger: Optional[logging.Logger] = None
    ):
        """初始化 JiaoziCache
        
        Args:
            data_class: 数据类型类
            index_config: 索引配置字典
            cache_backend: 缓存后端
            storage_backend: 存储后端
            index_backend: 索引后端
            serializer: 自定义序列化函数
            deserializer: 自定义反序列化函数
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger(__name__)
        self._data_class = data_class

        # 初始化序列化器
        self._init_serializers(serializer, deserializer)
        
        # 初始化缓存后端
        self._cache = cache_backend or LRUCacheBackend(1000)
        
        # 初始化存储后端
        if storage_backend is None:
            raise ValueError("storage_backend is required")
        self._storage = storage_backend
        
        # 初始化索引后端
        if index_backend is None and index_config:
            raise ValueError("index_backend is required when index_config is specified")
        self._index = index_backend

        # 验证索引字段
        if index_config:
            self._validate_index_fields(index_config.keys())

    def _init_serializers(self, serializer, deserializer):
        """初始化序列化器"""
        origin = get_origin(self._data_class)
        if origin in (dict, list, tuple):
            self._serializer = self._default_serializer
            self._deserializer = self._default_deserializer
        else:
            if hasattr(self._data_class, 'model_dump'):
                self._serializer = lambda obj: obj.model_dump() if obj else {}
                self._deserializer = self._data_class.model_validate
            else:
                if not serializer:
                    to_dict = getattr(self._data_class, 'to_dict', None)
                    if not to_dict or isinstance(to_dict, (classmethod, staticmethod)):
                        raise TypeError(
                            f"数据类 {self._data_class.__name__} 必须实现 to_dict 实例方法"
                            "或者提供自定义的序列化器"
                        )
                
                if not deserializer and not hasattr(self._data_class, 'from_dict'):
                    raise TypeError(
                        f"数据类 {self._data_class.__name__} 必须实现 from_dict 类方法，"
                        "或者提供自定义的反序列化器"
                    )
                
                self._serializer = serializer or (lambda obj: obj.to_dict() if obj else {})
                self._deserializer = deserializer or self._data_class.from_dict

    def _validate_index_fields(self, indexes: List[str]) -> None:
        """验证索引字段的有效性"""
        if hasattr(self._data_class, "model_fields"):
            valid_fields = self._data_class.model_fields.keys()
        elif hasattr(self._data_class, "__fields__"):
            valid_fields = self._data_class.__fields__.keys()
        elif isinstance(self._data_class, type) and issubclass(self._data_class, dict):
            return  # 字典类型不验证字段
        else:
            valid_fields = {name for name in dir(self._data_class) 
                          if not name.startswith("_")}
        
        invalid_fields = set(indexes) - set(valid_fields)
        if invalid_fields:
            raise ValueError(f"无效的索引字段: {', '.join(invalid_fields)}")

    def get(self, owner_id: str) -> Optional[Any]:
        """获取指定所有者的数据"""
        # 先从缓存获取
        cached_data = self._cache.get(owner_id)
        if cached_data is not None:
            return cached_data
        
        # 缓存未命中,从存储后端获取
        data = self._storage.get(owner_id)
        if data is not None:
            deserialized_data = self._deserializer(data)
            self._cache.put(owner_id, deserialized_data)
            return deserialized_data
        return None

    def set(self, value: Any, owner_id: str) -> None:
        """设置数据"""
        if value is None:
            return
            
        # 序列化并保存数据
        serialized_data = self._serializer(value)
        self._storage.set(owner_id, serialized_data)
        
        # 更新缓存
        self._cache.put(owner_id, value)
        
        # 更新索引
        if self._index is not None:
            self._index.update_index(value, owner_id)

    def delete(self, owner_id: str) -> bool:
        """删除数据"""
        # 获取原有数据用于更新索引
        old_value = self.get(owner_id)
        
        # 删除存储的数据
        result = self._storage.delete(owner_id)
        
        if result:
            # 清除缓存
            self._cache.remove(owner_id)
            
            # 更新索引
            if old_value is not None and self._index is not None:
                self._index.remove_from_index(owner_id)
        
        return result

    def query(self, conditions: Dict[str, Any]) -> List[Any]:
        """查询满足条件的数据"""
        if not self._index:
            return self._full_scan(conditions)
            
        owner_ids = set()
        first_condition = True
        
        for field, condition in conditions.items():
            if not self._index.has_index(field):
                continue
                
            # 推断字段类型
            field_type = self._infer_field_type(field)
            
            current_ids = set()
            if isinstance(condition, tuple):
                op, *values = condition
                # 转换查询值类型
                if field_type:
                    values = [self._convert_value(v, field_type) for v in values]
                current_ids = set(self._index.query(field, op, *values))
            else:
                # 转换等值查询的值
                if field_type:
                    condition = self._convert_value(condition, field_type)
                current_ids = set(self._index.find_with_index(field, condition))
            
            if first_condition:
                owner_ids = current_ids
                first_condition = False
            else:
                owner_ids &= current_ids
                
        results = []
        for owner_id in owner_ids:
            data = self.get(owner_id)
            if data and self._match_conditions(data, conditions):
                results.append(data)
                
        return results

    def _full_scan(self, conditions: Dict[str, Any]) -> List[Any]:
        """全表扫描（当没有可用索引时）"""
        import warnings
        warnings.warn("执行全表扫描，这可能会影响性能", UserWarning)
        
        results = []
        for owner_id in self._storage.list_owners():
            data = self.get(owner_id)
            if data and self._match_conditions(data, conditions):
                results.append(data)
        return results

    def find_one(self, field: str, value: Any) -> Optional[Any]:
        """查找单个匹配的数据"""
        if self._index and self._index.has_index(field):
            owner_ids = self._index.find_with_index(field, value)
            if owner_ids:
                return self.get(owner_ids[0])
        
        # 如果没有索引或没有找到，进行全表扫描
        for owner_id in self._storage.list_owners():
            data = self.get(owner_id)
            if data and self._index._get_value_by_path(data, field) == value:
                return data
        return None

    def find_by_id(self, id: str) -> Optional[Any]:
        """通过ID查找记录
        
        Example:
            user = cache.find_by_id("user123")
        """
        return self.get(id)  # 直接使用 get 方法，更高效

    def find_many(self, field: str, values: List[Any]) -> List[Any]:
        """查找多个匹配的记录
        
        Example:
            users = cache.find_many("status", ["active", "pending"])
        """
        results = []
        for value in values:
            results.extend(self.query({field: value}))
        return results

    def clear_cache(self) -> None:
        """清除缓存"""
        self._cache.clear()

    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return self._cache.get_stats()

    def list_owners(self) -> List[str]:
        """列出所有的所有者ID"""
        return self._storage.list_owners()

    def _match_conditions(self, data: Any, conditions: Dict[str, Any]) -> bool:
        """检查数据是否匹配所有条件"""
        for field, condition in conditions.items():
            value = IndexBackend._get_value_by_path(data, field)
            if value is None:
                return False
                
            # 获取字段类型并进行转换
            field_type = type(value)
            
            if isinstance(condition, tuple):
                op, *values = condition
                # 转换查询值类��
                values = [self._convert_value(v, field_type) for v in values]
                
                if op in COMPARE_OPS:
                    if not COMPARE_OPS[op](value, values[0]):
                        return False
                elif op in RANGE_OPS and len(values) == 2:
                    if not RANGE_OPS[op](value, values[0], values[1]):
                        return False
            else:
                # 转换等值查询的值
                condition = self._convert_value(condition, field_type)
                if value != condition:
                    return False
        return True

    def _match_value(self, data_value: Any, condition_value: Any) -> bool:
        """匹配值,列表值匹配"""
        if data_value is None:
            return False
        
        if callable(condition_value):
            return condition_value(data_value)
        
        # 将条件值转换为数据值的类型
        condition_value = self._convert_to_type(condition_value, type(data_value))
        
        if isinstance(data_value, (list, tuple, set)):
            if isinstance(condition_value, (list, tuple, set)):
                if len(data_value) != len(condition_value):
                    return False
                    
                for d_item, c_item in zip(data_value, condition_value):
                    if isinstance(c_item, dict):
                        if not all(
                            getattr(d_item, k, None) == v 
                            for k, v in c_item.items()
                        ):
                            return False
                    elif d_item != c_item:
                        return False
                return True
                
            return condition_value in data_value
        
        return data_value == condition_value

    def _default_serializer(self, obj: Any) -> Dict:
        """默认序列化方法,支持复合类型"""
        def serialize_value(v, type_hint=None):
            if isinstance(v, datetime):
                return v.isoformat()
            elif isinstance(v, BaseModel):
                return v.model_dump()
            elif isinstance(v, dict):
                val_type = None
                if type_hint and get_origin(type_hint) is dict:
                    _, val_type = get_args(type_hint)
                return {str(k): serialize_value(val, val_type) for k, val in v.items()}
            elif isinstance(v, (list, tuple)):
                item_type = None
                if type_hint and get_origin(type_hint) is list:
                    item_type = get_args(type_hint)[0]
                return [serialize_value(item, item_type) for item in v]
            return v

        if obj is None:
            return {}
        
        return serialize_value(obj, self._data_class)

    def _default_deserializer(self, data: Dict) -> Any:
        """默认反序列化方法,支持复合类型"""
        if not data:
            return self._create_default_instance()
        
        def deserialize_value(v, type_hint):
            if type_hint is datetime and isinstance(v, str):
                try:
                    return datetime.fromisoformat(v)
                except ValueError:
                    return v
            elif issubclass(type_hint, BaseModel) and isinstance(v, dict):
                return type_hint.model_validate(v)
            
            origin = get_origin(type_hint)
            if origin is dict:
                key_type, val_type = get_args(type_hint)
                return {key_type(k): deserialize_value(val, val_type) 
                       for k, val in v.items()}
            elif origin is list:
                item_type = get_args(type_hint)[0]
                return [deserialize_value(item, item_type) for item in v]
            elif origin is tuple:
                item_types = get_args(type_hint)
                return tuple(deserialize_value(item, t) 
                           for item, t in zip(v, item_types))
            return v
        
        return deserialize_value(data, self._data_class)

    def _create_default_instance(self) -> Any:
        """创建默认实例"""
        if hasattr(self._data_class, 'default'):
            return self._data_class.default()
        elif hasattr(self._data_class, '__dataclass_fields__'):
            return self._data_class()
        return None

    @classmethod
    def create_with_json_storage(
        cls,
        data_dir: str,
        filename: str,
        data_class: Type,
        index_config: Optional[Dict[str, IndexType]] = None,
        cache_size: int = 1000,
        serializer: Optional[Callable] = None,
        deserializer: Optional[Callable] = None,
        logger: Optional[logging.Logger] = None
    ) -> 'JiaoziCache':
        """创建基于JSON存储的缓存实例
        
        Args:
            data_dir: 数据目录路径
            filename: 文件名
            data_class: 数据类型类
            index_config: 索引配置
            cache_size: 缓存大小
            serializer: 自定义序列化函数
            deserializer: 自定义反序列化函数
            logger: 日志记录器
        """
        logger = logger or logging.getLogger(__name__)
        
        # 创建存储后端
        storage_backend = JSONFileStorageBackend(
            data_dir=data_dir,
            filename=filename,
            logger=logger
        )
        
        # 创建索引后端
        index_backend = None
        if index_config:
            # 收集字段类型信息
            field_types = {}
            
            # 从类型注解中获取字段类型
            if hasattr(data_class, '__annotations__'):
                annotations = data_class.__annotations__
                for field in index_config:
                    # 处理嵌套字段
                    parts = field.split('.')
                    current_type = data_class
                    current_field = field
                    
                    try:
                        for part in parts:
                            if not hasattr(current_type, '__annotations__'):
                                raise ValueError(f"类型 {current_type.__name__} 没有类型注解")
                            current_field = part
                            current_type = current_type.__annotations__[part]
                        
                        # 处理泛型类型
                        origin = get_origin(current_type)
                        if origin is not None:
                            args = get_args(current_type)
                            if args:
                                current_type = args[0]  # 使用第一个类型参数
                        
                        field_types[field] = current_type
                        logger.debug(f"字段 {field} 的类型为 {current_type}")
                        
                    except (AttributeError, KeyError) as e:
                        raise ValueError(f"无法获取字段 {current_field} 的类型: {e}")
            
            # 创建组合索引后端
            index_backend = CompositeIndexBackend(
                data_dir=data_dir,
                filename=filename,
                index_config=index_config,
                field_types=field_types,
                logger=logger
            )
            logger.debug(f"创建索引后端，配置: {index_config}，字段类型: {field_types}")
        
        return cls(
            data_class=data_class,
            index_config=index_config,
            cache_backend=LRUCacheBackend(cache_size),
            storage_backend=storage_backend,
            index_backend=index_backend,
            serializer=serializer,
            deserializer=deserializer,
            logger=logger
        )

    @staticmethod
    def _get_field_type(data_class: Type, field: str) -> Optional[Type]:
        """获取字段类型"""
        try:
            annotations = data_class.__annotations__
            if field in annotations:
                return annotations[field]
            
            # 处理嵌套字段
            parts = field.split('.')
            current_type = data_class
            for part in parts:
                if not hasattr(current_type, '__annotations__'):
                    return None
                annotations = current_type.__annotations__
                if part not in annotations:
                    return None
                current_type = annotations[part]
            return current_type
        except (AttributeError, KeyError):
            return None

    def rebuild_indexes(self) -> None:
        """重建所有索引"""
        if not self._index:
            return
        
        def data_iterator():
            results = []
            for owner_id in self._storage.list_owners():
                data = self.get(owner_id)
                if data:
                    results.append((owner_id, data))
            return results
        
        self._index.rebuild_indexes(data_iterator)

    def _convert_to_type(self, value: Any, target_type: Type) -> Any:
        """将值转换为目标类型"""
        if target_type is datetime:
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value)
                except ValueError:
                    return value
        elif target_type is int:
            try:
                return int(value)
            except (ValueError, TypeError):
                return value
        elif target_type is float:
            try:
                return float(value)
            except (ValueError, TypeError):
                return value
        return value

    def _infer_field_type(self, field: str) -> Optional[type]:
        """推断字段的数据类型"""
        # 从已有数据中推类型
        for owner_id in self._storage.list_owners():
            data = self.get(owner_id)
            if data:
                value = IndexBackend._get_value_by_path(data, field)
                if value is not None:
                    return type(value)
        return None

    def _convert_value(self, value: Any, target_type: type) -> Any:
        """根据目标类型转换值"""
        if isinstance(value, target_type):
            return value
            
        if isinstance(value, str):
            if target_type == datetime:
                try:
                    return datetime.fromisoformat(value)
                except ValueError:
                    pass
            elif target_type in (int, float):
                try:
                    return target_type(value)
                except ValueError:
                    pass
        return value
