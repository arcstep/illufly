from typing import Dict, Any, Optional, List, Callable, Type
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
import warnings

from ...config import get_env
from .config_protocol import ConfigStoreProtocol
from .backend import StorageBackend, JSONFileStorageBackend
from .index import IndexBackend, HashIndexBackend
from .cache import LRUCacheBackend

class JiaoziCache():
    """
    JiaoziCache 提供了一个高性能的缓存和持久化存储解决方案。
    支持索引查询、LRU缓存、JSON文件存储等功能。
    """
    
    def __init__(
        self,
        data_class: Type,
        indexes: Optional[List[str]] = None,
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
            indexes: 索引字段列表
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
        if index_backend is None and indexes:
            raise ValueError("index_backend is required when indexes are specified")
        self._index = index_backend

        # 验证索引字段
        if indexes:
            self._validate_index_fields(indexes)

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

    def find(self, conditions: Dict[str, Any]) -> List[Any]:
        """查找匹配条件的数据，优先使用索引"""
        # 获取所有可用的索引字段
        indexed_attrs = {
            k: v for k, v in conditions.items() 
            if self._index and self._index.has_index(k)
        }
        
        if indexed_attrs:
            # 使用第一个索引字段进行查找
            field, value = next(iter(indexed_attrs.items()))
            owner_ids = self._index.find_with_index(field, value)
            
            # 如果还有其他条件，进一步过滤
            results = []
            for current_owner_id in owner_ids:
                data = self.get(current_owner_id)
                if data and self._match_conditions(data, conditions):
                    results.append(data)
            return results
        
        # 没有可用索引时才全量扫描
        all_owners = list(self._storage.list_owners())
        if len(all_owners) > int(get_env("JIAOZI_CACHE_FULL_SCAN_THRESHOLD")):
            warnings.warn(
                f"对{len(all_owners)}条记录进行全量扫描。"
                f"建议为以下字段添加索引以提升性能: {list(conditions.keys())}",
                UserWarning
            )
        
        # 执行全量扫描
        results = []
        for current_owner_id in all_owners:
            data = self.get(current_owner_id)
            if data and self._match_conditions(data, conditions):
                results.append(data)
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

    def exists(self, attributes: Dict[str, Any]) -> bool:
        """检查是否存在匹配给定属性的记录"""
        indexed_attrs = {
            k: v for k, v in attributes.items() 
            if self._index.has_index(k)
        }
        
        if indexed_attrs:
            field, value = next(iter(indexed_attrs.items()))
            owners = self._index.find_with_index(field, value)
            
            if len(owners) > 0 and len(attributes) > 1:
                for owner_id in owners:
                    data = self.get(owner_id)
                    if data is not None and all(
                        getattr(data, k, None) == v 
                        for k, v in attributes.items()
                    ):
                        return True
                return False
            
            return len(owners) > 0
        
        # 没有索引时发出警告
        warnings.warn(
            f"属性中没有索引字段。建议为以下字段添加索引以提升性能: {list(attributes.keys())}",
            UserWarning
        )
        
        # 全量扫描
        for owner_id in self.list_owners():
            data = self.get(owner_id)
            if data is not None and all(
                getattr(data, k, None) == v 
                for k, v in attributes.items()
            ):
                return True
        
        return False

    def _match_conditions(self, data: Any, conditions: Dict[str, Any]) -> bool:
        """匹配所有条件"""
        if isinstance(data, dict):
            return any(
                all(
                    self._match_value(getattr(v, k, None) if hasattr(v, k) else None, cv)
                    for k, cv in conditions.items()
                )
                for v in data.values()
            )
        return all(
            self._match_value(getattr(data, k, None), v)
            for k, v in conditions.items()
        )

    def _match_value(self, data_value: Any, condition_value: Any) -> bool:
        """匹配值,支持列表值匹配"""
        if data_value is None:
            return False
        
        if callable(condition_value):
            return condition_value(data_value)
        
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
        indexes: Optional[List[str]] = None,
        cache_size: int = 1000,
        serializer: Optional[Callable] = None,
        deserializer: Optional[Callable] = None,
        logger: Optional[logging.Logger] = None
    ) -> 'JiaoziCache':
        """使用JSON文件存储后端创建JiaoziCache实例
        
        Args:
            data_dir: 数据存储目录路径
            filename: 数据文件名
            data_class: 数据类型类
            indexes: 索引字段列表
            cache_size: LRU缓存容量
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
        index_backend = HashIndexBackend(
            data_dir=data_dir,
            filename=filename,
            index_fields=indexes or [],
            logger=logger
        )
        
        return cls(
            data_class=data_class,
            indexes=indexes,
            cache_backend=LRUCacheBackend(cache_size),
            storage_backend=storage_backend,
            index_backend=index_backend,
            serializer=serializer,
            deserializer=deserializer,
            logger=logger
        )
