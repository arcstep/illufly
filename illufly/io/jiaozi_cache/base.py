from typing import Dict, Any, Optional, List, Callable, Type, Union, Tuple
from dataclasses import is_dataclass, asdict, dataclass
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
from .store import StorageBackend, BufferedJSONFileStorageBackend
from .index import IndexBackend, CompositeIndexBackend, IndexType, IndexConfig
from .cache import LRUCacheBackend, CacheBackend

@dataclass
class SubsetConfig:
    """子数据集配置"""
    name: str                     # 子数据集名称
    data_class: Type             # 数据类型
    index_types: Dict[str, str]  # 索引配置

class JiaoziCache():
    """
    JiaoziCache 提供了一个高性能的缓存和持久化存储解决方案。
    支持索引查询、LRU缓存、JSON文件存储等功能。
    """
    
    def __init__(
        self,
        data_class: Type,
        segment: str,          # 新增：数据类型标识(profile/tokens等)
        cache_backend: Optional[CacheBackend] = None,
        storage_backend: Optional[StorageBackend] = None,
        index_backend: Optional[IndexBackend] = None,
        serializer: Optional[Callable] = None,
        deserializer: Optional[Callable] = None,
        logger: Optional[logging.Logger] = None
    ):
        """初始化 JiaoziCache
        
        Args:
            data_class: 数据类型类
            segment: 数据类型标识(profile/tokens等)
            index_types: 字段索引类型映射
            cache_backend: 缓存后端
            storage_backend: 存储后端
            index_backend: 索引后端
            serializer: 自定义序列化函数
            deserializer: 自定义反序列化函数
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger(__name__)
        self.logger.debug(f"初始化 JiaoziCache: segment={segment}, data_class={data_class}")
        
        self._data_class = data_class
        self._segment = segment
        self._base_dir = Path(get_env("ILLUFLY_CONFIG_STORE_DIR"))
        
        # 子数据集配置和实例
        self._subset_configs: Dict[str, SubsetConfig] = {}
        self._subsets: Dict[str, Dict[str, 'JiaoziCache']] = {}
        
        # 初始化其他组件（保持原有逻辑）
        self._init_serializers(serializer, deserializer)
        self._cache = cache_backend or LRUCacheBackend(1000)
        self.logger.info(f"初始化缓存后端: {self._cache.__class__.__name__}")
        
        if storage_backend is None:
            storage_backend = BufferedJSONFileStorageBackend(
                base_dir=self._base_dir,
                segment=segment
            )
        self._storage = storage_backend
        self.logger.info(f"初始化存储后端: {self._storage.__class__.__name__}")
        
        if index_backend is None and index_types:
            index_backend = CompositeIndexBackend(
                field_types=field_types,
                index_types=index_types,
                base_dir=self._base_dir,
                segment=segment,
                config=IndexConfig(cache_size=1000),
            )
        self._index = index_backend
        if index_backend:
            self.logger.info(f"初始化索引后端: {self._index.__class__.__name__}")

    def _init_serializers(self, serializer, deserializer):
        """初始化序列化器"""
        self.logger.debug("初始化序列化器")
        origin = get_origin(self._data_class)
        if origin in (dict, list, tuple):
            self.logger.debug(f"使用默认序列化器处理内置类型: {origin}")
            self._serializer = self._default_serializer
            self._deserializer = self._default_deserializer
        else:
            if hasattr(self._data_class, 'model_dump'):
                self.logger.debug("使用 Pydantic 序列化器")
                self._serializer = lambda obj: obj.model_dump() if obj else {}
                self._deserializer = self._data_class.model_validate
            else:
                if not serializer:
                    to_dict = getattr(self._data_class, 'to_dict', None)
                    if not to_dict or isinstance(to_dict, (classmethod, staticmethod)):
                        self.logger.error(f"数据类 {self._data_class.__name__} 缺少 to_dict 实例方法")
                        raise TypeError(
                            f"数据类 {self._data_class.__name__} 必须实现 to_dict 实例方法"
                            "或者提供自定义的序列化器"
                        )
                
                if not deserializer and not hasattr(self._data_class, 'from_dict'):
                    self.logger.error(f"数据类 {self._data_class.__name__} 缺少 from_dict 类方法")
                    raise TypeError(
                        f"数据类 {self._data_class.__name__} 必须实现 from_dict 类方法，"
                        "或者提供自定义的反序列化器"
                    )
                
                self.logger.debug("使用自定义序列化器")
                self._serializer = serializer or (lambda obj: obj.to_dict() if obj else {})
                self._deserializer = deserializer or self._data_class.from_dict

    def _validate_index_fields(self, indexes: List[str]) -> None:
        """验证索引字段的有效性"""
        self.logger.debug(f"验证索引字段: {indexes}")
        self.logger.debug(f"数据类: {self._data_class}")
        
        # 对于字典类型，我们需要检查值类型的字段
        origin = get_origin(self._data_class)
        if origin in (dict, Dict):
            value_type = get_args(self._data_class)[1]
            self.logger.debug(f"字典值类型: {value_type}")
            
            # 始终使用 _get_nested_fields
            valid_fields = self._get_nested_fields(value_type)
            self.logger.debug(f"有效字段: {valid_fields}")
            
            # 处理嵌套字段
            nested_fields = {}
            for field, field_type in valid_fields.items():
                nested_fields[field] = field_type
                # 处理字典类型字段
                origin = get_origin(field_type)
                if origin in (dict, Dict):
                    # 对于字典类型字段，允许任意子字段
                    self.logger.debug(f"字段 {field} 是字典类型: {field_type}")
                    nested_fields[field] = field_type
                    # 如果在索引中使用了这个字段的子字段，也认为是有效的
                    for index in indexes:
                        if index.startswith(f"{field}."):
                            nested_fields[index] = get_args(field_type)[1]
            
            valid_fields = nested_fields
            self.logger.debug(f"处理后的有效字段: {valid_fields}")
        else:
            valid_fields = self._get_nested_fields(self._data_class)
        
        # 验证每个索引字段
        invalid_fields = set()
        for field in indexes:
            if field in valid_fields:
                continue
            
            # 检查是否是嵌套字段
            if '.' in field:
                base_field = field.split('.')[0]
                if base_field in valid_fields:
                    base_type = valid_fields[base_field]
                    # 检查基础字段是否是字典类型
                    origin = get_origin(base_type)
                    if origin in (dict, Dict):
                        continue
            
            invalid_fields.add(field)
            self.logger.warning(f"无效字段: {field}")
        
        if invalid_fields:
            self.logger.error(f"发现无效的索引字段: {invalid_fields}")
            raise ValueError(f"无效的索引字段: {', '.join(invalid_fields)}")

    def _get_nested_fields(self, cls: Type) -> Dict[str, Type]:
        """获取类的所有字段，包括嵌套字段"""
        self.logger.debug(f"获取类 {cls.__name__} 的嵌套字段")
        fields = {}
        
        if hasattr(cls, "model_fields"):
            # Pydantic v2
            self.logger.debug("使用 Pydantic v2 字段")
            for field_name, field in cls.model_fields.items():
                fields[field_name] = field.annotation
        elif hasattr(cls, "__fields__"):
            # Pydantic v1
            self.logger.debug("使用 Pydantic v1 字段")
            for field_name, field in cls.__fields__.items():
                fields[field_name] = field.type_
        elif hasattr(cls, "__annotations__"):
            # 标准类型注解
            self.logger.debug("使用标准类型注解")
            fields.update(cls.__annotations__)
        elif hasattr(cls, "to_dict"):
            # 通过 to_dict 方法推断字段
            self.logger.debug("尝试从 to_dict 方法推断字段")
            try:
                instance = cls() if hasattr(cls, "__new__") else None
                if instance:
                    sample_dict = instance.to_dict()
                    for field_name, value in sample_dict.items():
                        fields[field_name] = type(value)
                else:
                    # 从方法签名获取字段
                    init_params = inspect.signature(cls.__init__).parameters
                    for name, param in init_params.items():
                        if name != 'self':
                            annotation = param.annotation
                            if annotation != inspect.Parameter.empty:
                                fields[name] = annotation
                            else:
                                fields[name] = Any
            except Exception as e:
                self.logger.warning(f"无法从 to_dict 推断字段: {e}")
        
        self.logger.debug(f"获取到的字段: {fields}")
        return fields

    def get(self, owner_id: str) -> Optional[Any]:
        """获取指定所有者的数据"""
        self.logger.debug(f"获取数据: owner_id={owner_id}")
        
        # 先从缓存获取
        cached_data = self._cache.get(owner_id)
        if cached_data is not None:
            self.logger.debug("缓存命中")
            return cached_data
        
        # 缓存未命中,从存储后端获取
        self.logger.debug("缓存未命中，从存储后端获取")
        data = self._storage.get(owner_id)
        if data is not None:
            deserialized_data = self._deserializer(data)
            self._cache.put(owner_id, deserialized_data)
            self.logger.debug("数据已加载并缓存")
            return deserialized_data
            
        self.logger.debug("数据不存在")
        return None

    def set(self, value: Any, owner_id: str) -> None:
        """设置数据"""
        self.logger.debug(f"设置数据: owner_id={owner_id}")
        
        if value is None:
            self.logger.warning("尝试设置空值，操作已忽略")
            return
            
        # 序列化并保存数据
        serialized_data = self._serializer(value)
        self._storage.set(owner_id, serialized_data)
        self.logger.debug("数据已保存到存储后端")
        
        # 更新缓存
        self._cache.put(owner_id, value)
        self.logger.debug("缓存已更新")
        
        # 更新索引
        if self._index is not None:
            self._index.update_index(value, owner_id)
            self.logger.debug("索引已更新")

    def delete(self, owner_id: str) -> bool:
        """删除数据"""
        self.logger.debug(f"删除数据: owner_id={owner_id}")
        
        # 获取原有数据用于更新索引
        old_value = self.get(owner_id)
        
        # 删除存储的数据
        result = self._storage.delete(owner_id)
        
        if result:
            self.logger.info(f"成功删除数据: owner_id={owner_id}")
            # 清除缓存
            self._cache.remove(owner_id)
            self.logger.debug("缓存已清除")
            
            # 更新索引
            if old_value is not None and self._index is not None:
                self._index.remove_from_index(owner_id)
                self.logger.debug("索引已更新")
        else:
            self.logger.warning(f"删除数据失败: owner_id={owner_id}")
        
        return result

    def query(self, conditions: Dict[str, Any]) -> List[Any]:
        """查询满足条件的数据
        
        支持新的索引查询接口，但保持原有的查询逻辑
        """
        self.logger.debug(f"执行查询: conditions={conditions}")
        
        if not conditions:
            self.logger.warning("查询条件为空")
            return []
            
        owner_ids = set()
        first_condition = True
        
        for field, condition in conditions.items():
            if not self._index or not self._index.has_index(field):
                self.logger.debug(f"字段 {field} 没有索引")
                continue
                
            # 处理不同类型的查询条件
            if isinstance(condition, tuple):
                op, *values = condition
                self.logger.debug(f"使用操作符查询: {field} {op} {values}")
                current_ids = self._index.query(field, op, *values)
            else:
                self.logger.debug(f"使用等值查询: {field}={condition}")
                current_ids = self._index.find_with_index(field, condition)
                
            # 合并结果集
            if first_condition:
                owner_ids = set(current_ids)
                first_condition = False
            else:
                owner_ids &= set(current_ids)
                
            if not owner_ids:
                self.logger.debug("查询结果为空")
                return []
                
        # 如果没有使用索引，执行全表扫描
        if first_condition:
            self.logger.warning("没有可用的索引，执行全表扫描")
            return self._full_scan(conditions)
            
        # 获取并验证结果
        results = []
        for owner_id in owner_ids:
            data = self.get(owner_id)
            if data and self._match_conditions(data, conditions):
                results.append(data)
                
        self.logger.debug(f"查询完成，找到 {len(results)} 条结果")
        return results

    def _full_scan(self, conditions: Dict[str, Any]) -> List[Any]:
        """全表扫描（当没有可用索引时）"""
        self.logger.warning("执行全表扫描，这可能会影响性能")
        import warnings
        warnings.warn("执行全表扫描，这可能会影响性能", UserWarning)
        
        results = []
        for owner_id in self._storage.list_owners():
            data = self.get(owner_id)
            if data and self._match_conditions(data, conditions):
                results.append(data)
                
        self.logger.debug(f"全表扫描完成，找到 {len(results)} 条结果")
        return results

    def find_one(self, field: str, value: Any) -> Optional[Any]:
        """查找单个匹配的数据"""
        self.logger.debug(f"查找单条数据: {field}={value}")
        
        if self._index and self._index.has_index(field):
            owner_ids = self._index.find_with_index(field, value)
            if owner_ids:
                self.logger.debug("通过索引找到匹配记录")
                return self.get(owner_ids[0])
        
        # 如果没有索引或没有找到，进行全表扫描
        self.logger.warning(f"字段 {field} 没有索引，执行全表扫描")
        for owner_id in self._storage.list_owners():
            data = self.get(owner_id)
            if data and self._index._get_value_by_path(data, field) == value:
                return data
                
        self.logger.debug("未找到匹配记录")
        return None

    def find_by_id(self, id: str) -> Optional[Any]:
        """通过ID查找记录
        
        Example:
            user = cache.find_by_id("user123")
        """
        self.logger.debug(f"通过ID查找记录: {id}")
        return self.get(id)  # 直接使用 get 方法，更高效

    def find_many(self, field: str, values: List[Any]) -> List[Any]:
        """查找多个匹配的记录
        
        Example:
            users = cache.find_many("status", ["active", "pending"])
        """
        self.logger.debug(f"批量查找记录: {field}={values}")
        results = []
        for value in values:
            results.extend(self.query({field: value}))
        self.logger.debug(f"找到 {len(results)} 条匹配记录")
        return results

    def clear_cache(self) -> None:
        """清除缓存"""
        self.logger.info("清除所有缓存")
        self._cache.clear()

    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        self.logger.debug("获取缓存统计信息")
        return self._cache.get_stats()

    def list_owners(self) -> List[str]:
        """列出所有的所有者ID"""
        self.logger.debug("获取所有所有者ID列表")
        return self._storage.list_owners()

    def _match_conditions(self, data: Any, conditions: Dict[str, Any]) -> bool:
        """检查数据是否匹配所有条件"""
        self.logger.debug(f"匹配条件: {conditions}")
        
        for field, condition in conditions.items():
            value = IndexBackend._get_value_by_path(data, field)
            if value is None:
                self.logger.debug(f"字段 {field} 值为空")
                return False
                
            # 获取字段类型并进行转换
            field_type = type(value)
            
            if isinstance(condition, tuple):
                op, *values = condition
                # 转换查询值类型
                values = [self._convert_value(v, field_type) for v in values]
                
                if op in COMPARE_OPS:
                    if not COMPARE_OPS[op](value, values[0]):
                        self.logger.debug(f"比较操作不匹配: {field} {op} {values[0]}")
                        return False
                elif op in RANGE_OPS and len(values) == 2:
                    if not RANGE_OPS[op](value, values[0], values[1]):
                        self.logger.debug(f"范围操作不匹配: {field} {op} {values}")
                        return False
            else:
                # 转换等值查询的值
                condition = self._convert_value(condition, field_type)
                if value != condition:
                    self.logger.debug(f"等值比较不匹配: {field}={condition}")
                    return False
                    
        self.logger.debug("所有条件匹配成功")
        return True

    def _match_value(self, data_value: Any, condition_value: Any) -> bool:
        """匹配值,列表值匹配"""
        self.logger.debug(f"匹配值: {data_value} vs {condition_value}")
        
        if data_value is None:
            self.logger.debug("数据值为空")
            return False
        
        if callable(condition_value):
            result = condition_value(data_value)
            self.logger.debug(f"使用回调函数匹配: {result}")
            return result
        
        # 将条件值转换为数据值的类型
        condition_value = self._convert_to_type(condition_value, type(data_value))
        
        if isinstance(data_value, (list, tuple, set)):
            if isinstance(condition_value, (list, tuple, set)):
                if len(data_value) != len(condition_value):
                    self.logger.debug("列表长度不匹配")
                    return False
                    
                for d_item, c_item in zip(data_value, condition_value):
                    if isinstance(c_item, dict):
                        if not all(
                            getattr(d_item, k, None) == v 
                            for k, v in c_item.items()
                        ):
                            self.logger.debug("字典项不匹配")
                            return False
                    elif d_item != c_item:
                        self.logger.debug("列表项不匹配")
                        return False
                return True
                
            return condition_value in data_value
        
        result = data_value == condition_value
        self.logger.debug(f"值比较结果: {result}")
        return result

    def _default_serializer(self, obj: Any) -> Dict:
        """默认序列化方法,支持复合类型"""
        self.logger.debug("使用默认序列化器")
        
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
            self.logger.debug("序列化空对象")
            return {}
        
        result = serialize_value(obj, self._data_class)
        self.logger.debug("序列化完成")
        return result

    def _default_deserializer(self, data: Dict) -> Any:
        """默认反序列化方法,支持复合类型"""
        self.logger.debug("使用默认反序列化器")
        
        if not data:
            self.logger.debug("反序列化空数据")
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
        
        result = deserialize_value(data, self._data_class)
        self.logger.debug("反序列化完成")
        return result

    def _create_default_instance(self) -> Any:
        """创建默认实例"""
        self.logger.debug("创建默认实例")
        if hasattr(self._data_class, 'default'):
            return self._data_class.default()
        elif hasattr(self._data_class, '__dataclass_fields__'):
            return self._data_class()
        return None

    @classmethod
    def create_with_json_storage(
        cls,
        segment: str,          # 修改：添加 segment 参数
        data_class: Type,
        index_types: Optional[Dict[str, str]] = None,
        cache_size: int = 1000,
        serializer: Optional[Callable] = None,
        deserializer: Optional[Callable] = None,
        logger: Optional[logging.Logger] = None
    ) -> 'JiaoziCache':
        """创建基于JSON存储的缓存实例"""
        logger = logger or logging.getLogger(__name__)
        logger.info(f"创建JSON存储缓存实例: segment={segment}")
        
        base_dir = Path(get_env("ILLUFLY_CONFIG_STORE_DIR"))
        
        # 创建存储后端
        storage_backend = BufferedJSONFileStorageBackend(
            base_dir=base_dir,
            segment=segment
        )
        logger.debug("已创建JSON文件存储后端")
        
        # 创建索引后端
        index_backend = None
        if index_types:
            logger.debug(f"创建索引后端: {index_types}")
            index_backend = CompositeIndexBackend(
                field_types=cls._get_field_types(data_class),
                config=IndexConfig(cache_size=cache_size),
                index_types=index_types,
                base_dir=base_dir,
                segment=segment
            )
        
        instance = cls(
            data_class=data_class,
            segment=segment,
            index_types=index_types,
            cache_backend=LRUCacheBackend(cache_size),
            storage_backend=storage_backend,
            index_backend=index_backend,
            serializer=serializer,
            deserializer=deserializer,
            logger=logger
        )
        
        logger.info("缓存实例创建完成")
        return instance

    @staticmethod
    def _get_field_type(data_class: Type, field: str) -> Optional[Type]:
        """获取字段类型"""
        logger = logging.getLogger(__name__)
        logger.debug(f"获取字段类型: class={data_class.__name__}, field={field}")
        
        try:
            annotations = data_class.__annotations__
            if field in annotations:
                return annotations[field]
            
            # 处理嵌套字段
            parts = field.split('.')
            current_type = data_class
            for part in parts:
                if not hasattr(current_type, '__annotations__'):
                    logger.debug(f"类型 {current_type} 没有注解")
                    return None
                annotations = current_type.__annotations__
                if part not in annotations:
                    logger.debug(f"字段 {part} 不在注解中")
                    return None
                current_type = annotations[part]
            return current_type
        except (AttributeError, KeyError) as e:
            logger.warning(f"获取字段类型失败: {e}")
            return None

    def rebuild_indexes(self) -> None:
        """重建所有索引"""
        self.logger.info("开始重建索引")
        if not self._index:
            self.logger.warning("没有配置索引后端")
            return
        
        def data_iterator():
            results = []
            for owner_id in self._storage.list_owners():
                data = self.get(owner_id)
                if data:
                    results.append((owner_id, data))
            return results
        
        self._index.rebuild_indexes(data_iterator)
        self.logger.info("索引重建完成")

    def _convert_to_type(self, value: Any, target_type: Type) -> Any:
        """值转换为目标类型"""
        self.logger.debug(f"转换值类型: {value} -> {target_type}")
        
        if target_type is datetime:
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value)
                except ValueError:
                    self.logger.warning(f"日期格式转换失败: {value}")
                    return value
        elif target_type is int:
            try:
                return int(value)
            except (ValueError, TypeError):
                self.logger.warning(f"整数转换失败: {value}")
                return value
        elif target_type is float:
            try:
                return float(value)
            except (ValueError, TypeError):
                self.logger.warning(f"浮点数转换失败: {value}")
                return value
        return value

    def _infer_field_type(self, field: str) -> Optional[type]:
        """推断字段的数据类型"""
        self.logger.debug(f"开始推断字段类型: {field}")
        # 从已有数据中推类型
        for owner_id in self._storage.list_owners():
            data = self.get(owner_id)
            if data:
                value = IndexBackend._get_value_by_path(data, field)
                if value is not None:
                    self.logger.debug(f"推断字段类型成功: {field} -> {type(value)}")
                    return type(value)
        self.logger.debug(f"未能推断字段类型: {field}")
        return None

    def _convert_value(self, value: Any, target_type: type) -> Any:
        """根据目标类型转换值"""
        self.logger.debug(f"开始转换值类型: {value} -> {target_type}")
        
        if isinstance(value, target_type):
            self.logger.debug("值已经是目标类型，无需转换")
            return value
            
        if isinstance(value, str):
            if target_type == datetime:
                try:
                    result = datetime.fromisoformat(value)
                    self.logger.debug(f"日期转换成功: {value} -> {result}")
                    return result
                except ValueError:
                    self.logger.warning(f"日期格式转换失败: {value}")
                    pass
            elif target_type in (int, float):
                try:
                    result = target_type(value)
                    self.logger.debug(f"数值转换成功: {value} -> {result}")
                    return result
                except ValueError:
                    self.logger.warning(f"数值转换失败: {value}")
                    pass
        self.logger.debug(f"无法转换，返回原值: {value}")
        return value

    def get_index_stats(self) -> Optional[Dict[str, Any]]:
        """获取索引统计信息（新增方法）"""
        self.logger.debug("获取索引统计信息")
        if not self._index:
            self.logger.warning("索引后端未配置")
            return None
        stats = self._index.get_stats()
        self.logger.debug(f"获取到索引统计信息: {stats}")
        return stats

    # 新增子数据集相关方法
    def register_subset(
        self,
        subset_name: str,
        data_class: Type,
        index_types: Optional[Dict[str, str]] = None
    ) -> None:
        """注册子数据集配置"""
        self.logger.info(f"注册子数据集: name={subset_name}, class={data_class.__name__}")
        self._subset_configs[subset_name] = SubsetConfig(
            name=subset_name,
            data_class=data_class,
            index_types=index_types
        )
        self.logger.debug(f"子数据集注册完成: {subset_name}")

    def get_subset(
        self,
        owner_id: str,
        subset_name: str
    ) -> 'JiaoziCache':
        """获取子数据集实例"""
        self.logger.debug(f"获取子数据集: owner={owner_id}, name={subset_name}")
        
        if subset_name not in self._subset_configs:
            self.logger.error(f"未注册的子数据集: {subset_name}")
            raise ValueError(f"未注册的子数据集: {subset_name}")
            
        # 延迟创建子数据集实例
        if subset_name not in self._subsets:
            self.logger.debug(f"初始化子数据集字典: {subset_name}")
            self._subsets[subset_name] = {}
            
        if owner_id not in self._subsets[subset_name]:
            self.logger.info(f"创建子数据集实例: owner={owner_id}, name={subset_name}")
            config = self._subset_configs[subset_name]
            
            # 创建子数据集专用的存储后端
            storage = BufferedJSONFileStorageBackend(
                base_dir=self._base_dir / owner_id / subset_name
            )
            
            # 创建子数据集专用的索引后端
            index = None
            if config.index_types:
                self.logger.debug(f"创建子数据集索引后端: {subset_name}")
                index = CompositeIndexBackend(
                    field_types=self._get_field_types(config.data_class),
                    config=IndexConfig(cache_size=1000),
                    index_types=config.index_types,
                    base_dir=self._base_dir / owner_id / "indexes",
                    segment=subset_name
                )
            
            # 创建子数据集实例
            self._subsets[subset_name][owner_id] = JiaoziCache(
                data_class=config.data_class,
                segment=subset_name,
                index_types=config.index_types,
                storage_backend=storage,
                index_backend=index
            )
            self.logger.info(f"子数据集实例创建完成: owner={owner_id}, name={subset_name}")
            
        return self._subsets[subset_name][owner_id]
