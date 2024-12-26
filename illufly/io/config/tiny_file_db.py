from typing import Dict, Any, Optional, List, Callable, Type
from dataclasses import is_dataclass, asdict
from datetime import datetime
import inspect
from pathlib import Path
import json
import threading
import logging
from .config_protocol import ConfigStoreProtocol
from contextlib import contextmanager
from typing import get_origin, get_args
from pydantic import BaseModel, Field
from collections import OrderedDict

class DateTimeEncoder(json.JSONEncoder):
    """处理datetime和自定义对象的JSON编码器"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        # 处理实现了 to_dict 方法的对象
        if hasattr(obj, 'to_dict') and callable(obj.to_dict):
            return obj.to_dict()
        return super().default(obj)

class LRUCache:
    """线程安全的LRU缓存实现"""
    def __init__(self, capacity: int):
        if capacity < 0:
            raise ValueError("缓存容量不能为负数")
        self.capacity = capacity
        self._cache = OrderedDict()
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        # 如果容量为0，直接返回None
        if self.capacity == 0:
            return None
            
        with self._lock:
            if key not in self._cache:
                return None
            value = self._cache.pop(key)
            self._cache[key] = value
            return value
    
    def put(self, key: str, value: Any) -> None:
        # 如果容量为0，不进行缓存
        if self.capacity == 0:
            return
            
        with self._lock:
            if key in self._cache:
                self._cache.pop(key)
            elif len(self._cache) >= self.capacity:
                self._cache.popitem(last=False)
            self._cache[key] = value
    
    def remove(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

class TinyFileDB(ConfigStoreProtocol):
    """基于文件的配置存储，提供线程安全和类型安全的数据持久化能力。
    
    设计思路:
    1. 分层架构:
       - 内存层: LRU缓存，保存热点数据
       - 索引层: 内存中维护字段索引
       - 存储层: 文件系统持久化
    
    2. 缓存策略:
       - 采用LRU(Least Recently Used)算法
       - 可配置缓存容量
       - 自动淘汰不常用数据
       - 写入时同步更新缓存
    
    3. 索引机制:
       - 支持单字段索引
       - 索引常驻内存
       - 写入时自动维护
       - 支持高效查询
    
    存储结构:
    1. 文件系统结构:
       /data_dir/
       ├── .indexes/                    # 索引目录
       │   ├── profiles.json           # 用户配置索引
       │   ├── chat_history.json      # 聊天记录索引
       │   └── preferences.json       # 偏好设置索引
       ├── {owner_id1}/               # 所有者目录
       │   ├── profiles.json         # 用户配置数据
       │   ├── chat_history.json    # 聊天记录数据
       │   └── preferences.json     # 偏好设置数据
       └── {owner_id2}/
           ├── profiles.json
           ├── chat_history.json
           └── preferences.json
    
    2. 数据组织:
       - 第一层: 基于owner_id的目录隔离
       - 第二层: 单一JSON文件存储
       - 推荐数据结构: Dict[str, Any]
    
    3. 索引结构:
       ```json
       {
           "field_name": {
               "field_value1": ["owner_id1", "owner_id2"],
               "field_value2": ["owner_id3"]
           }
       }
       ```
    
    主要特点:
    - 文件系统持久化
    - LRU内存缓存
    - 字段索引支持
    - 线程安全
    - 自动序列化/反序列化
    - 灵活的查询支持
    - 复合类型存储支持
    - Pydantic 模型原生支持
    - 多模块数据管理
    
    基本用法:
    ```python
    # 1. 创建带缓存和索引的存储
    store = TinyFileDB(
        data_dir="/path/to/data",
        filename="profiles.json",
        data_class=UserProfile,
        indexes=["email"],
        cache_size=1000
    )
    
    # 2. 数据操作
    store.set(user_profile, "user1")
    profile = store.get("user1")
    results = store.find({"email": "user@example.com"})
    
    # 3. 缓存管理
    store.clear_cache()
    cache_info = store.get_cache_info()
    ```
    
    复合类型存储示例:
    ```python
    # 1. 复杂数据结构
    class Item(BaseModel):
        name: str
        value: int
    
    class Container(BaseModel):
        items: List[Item]
        updated_at: datetime
    
    # 2. 创建存储
    store = TinyFileDB(
        data_dir="data",
        filename="containers.json",
        data_class=Dict[str, List[Container]]
    )
    
    # 3. 复杂查询
    results = store.find({
        "items": lambda items: any(
            item.value > 100 for item in items
        )
    })
    ```
    
    多模块数据管理示例:
    ```python
    # 1. 不同模块的存储实例
    profile_store = TinyFileDB(
        data_dir="/data",
        filename="profiles.json",
        data_class=UserProfile
    )
    
    chat_store = TinyFileDB(
        data_dir="/data",
        filename="chat_history.json",
        data_class=Dict[str, List[ChatMessage]]
    )
    
    # 2. 数据管理操作
    def backup_user_data(owner_id: str, backup_dir: str):
        shutil.copytree(f"/data/{owner_id}", f"{backup_dir}/{owner_id}")
    ```
    
    高级特性:
    1. 自动序列化支持:
       - Pydantic 模型自动序列化
       - 传统 to_dict/from_dict 方法支持
       - datetime 类型自动处理
       - 嵌套对象序列化
       - 复合类型自动序列化
    
    2. 查询能力:
       - 索引字段快速查询
       - 简单值精确匹配
       - 列表内容匹配
       - 嵌套对象匹配
       - 自定义匹配函数
       - 复合类型递归查询
    
    3. 缓存机制:
       - LRU缓存策略
       - 可配置缓存大小
       - 自动缓存维护
       - 性能监控支持
    
    4. 线程安全:
       - 缓存操作锁
       - 文件操作锁
       - 并发访问保护
    
    最佳实践:
    1. 数据组织:
       - 使用字典作为顶层结构
       - 合理划分模块
       - 控制文件大小
    
    2. 性能优化:
       - 合理设置缓存大小
       - 只索引必要字段
       - 定期清理过期数据
    
    3. 数据管理:
       - 实现定期备份
       - 支持增量备份
       - 提供数据迁移工具
    
    Args:
        data_dir (str): 数据存储目录路径
        filename (str): 数据文件名
        data_class (Type): 数据类型类
        indexes (Optional[List[str]]): 索引字段列表
        cache_size (int): LRU缓存容量，默认1000
        serializer (Optional[Callable]): 自定义序列化函数
        deserializer (Optional[Callable]): 自定义反序列化函数
        logger (Optional[logging.Logger]): 日志记录器
    """
    _data: Dict[str, Optional[Any]]

    def __init__(
        self,
        data_dir: str,
        filename: str,
        data_class: Type,
        indexes: Optional[List[str]] = None,
        cache_size: int = 1000,  # 默认缓存1000条记录
        serializer: Optional[Callable[[Any], Dict[str, Any]]] = None,
        deserializer: Optional[Callable[[Dict[str, Any]], Any]] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化FileConfigStore
        
        Args:
            data_dir (str): 数据存储目录路径
            filename (str): 数据文件名
            data_class (Type): 数据类型类 (必需)
            indexes (Optional[List[str]]): 索引字段列表
            serializer (Optional[Callable]): 可选的自定义序列化函数
            deserializer (Optional[Callable]): 可选的自定义反序列化函数
            logger (Optional[logging.Logger]): 可选的日志记录器

        Raises:
            TypeError: 如果data_class没有提供to_dict或from_dict方法且没有提供自定义序列化器
        """
        self.logger = logger or logging.getLogger(__name__)
        self._data_dir = Path(data_dir)
        self._filename = filename
        self._data_class = data_class

        # 缓存相关初始化
        self._data_cache = LRUCache(cache_size)
        self._indexes = {}
        self._index_fields = indexes or []
        
        # 加载索引（索引始终保持在内存中）
        self._load_indexes()

        # 确保数据目录存在
        Path(self._data_dir).mkdir(parents=True, exist_ok=True)

        # 检查是否是复合类型
        origin = get_origin(self._data_class)
        if origin in (dict, list, tuple):
            # 复合类型使用默认序列化器
            self._serializer = self._default_serializer
            self._deserializer = self._default_deserializer
        else:
            # 检查是否是 Pydantic 模型
            if hasattr(data_class, 'model_dump') and hasattr(data_class, 'model_validate'):
                self._serializer = lambda obj: obj.model_dump() if obj else {}
                self._deserializer = data_class.model_validate
            else:
                # 非复合类型检查序列化方法
                if not serializer:
                    to_dict = getattr(self._data_class, 'to_dict', None)
                    if not to_dict or isinstance(to_dict, (classmethod, staticmethod)):
                        raise TypeError(
                            f"数据类 {self._data_class.__name__} 必须实现 to_dict 实例方法"
                            "或者提供自定义的序列化器"
                        )
                
                # 检查反序列化方法
                if not deserializer and not hasattr(self._data_class, 'from_dict'):
                    raise TypeError(
                        f"数据类 {self._data_class.__name__} 必须实现 from_dict 类方法，"
                        "或者提供自定义的反序列化器"
                    )
                
                self._serializer = serializer or (lambda obj: obj.to_dict() if obj else {})
                self._deserializer = deserializer or self._data_class.from_dict

        self._data = {}
        self._lock = threading.Lock()
        self._file_locks = {}
        self._file_locks_lock = threading.Lock()

        # 验证索引字段
        if indexes:
            # 检查是否是 Pydantic 模型
            if hasattr(data_class, "model_fields"):
                # Pydantic v2 模型
                valid_fields = data_class.model_fields.keys()
            elif hasattr(data_class, "__fields__"):
                # Pydantic v1 模型
                valid_fields = data_class.__fields__.keys()
            elif isinstance(data_class, type) and issubclass(data_class, dict):
                # 字典类型不验证字段
                valid_fields = None
            else:
                # 其他类型，获取所有非私有属性
                valid_fields = {name for name in dir(data_class) 
                              if not name.startswith("_")}
            
            # 验证索引字段
            if valid_fields is not None:
                invalid_fields = set(indexes) - set(valid_fields)
                if invalid_fields:
                    raise ValueError(
                        f"无效的索引字段: {', '.join(invalid_fields)}"
                    )

    def _default_serializer(self, obj: Any) -> Dict:
        """默认序列化方法，支持复合类型"""
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
        """默认反序列化方法，支持复合类型"""
        if not data:
            return self._create_default_instance()
        
        def deserialize_value(v, type_hint):
            # 处理日期时间字符串
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

    def get(self, owner_id: str) -> Optional[Any]:
        """获取指定所有者的数据"""
        # 先尝试从缓存获取
        cached_data = self._data_cache.get(owner_id)
        if cached_data is not None:
            return cached_data
        
        # 缓存未命中，从文件加载
        file_path = self._get_file_path(owner_id)
        if not file_path.exists():
            return None
        
        with self._get_file_lock(owner_id):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    deserialized_data = self._deserializer(data)
                    # 加载后放入缓存
                    self._data_cache.put(owner_id, deserialized_data)
                    return deserialized_data
            except Exception as e:
                self.logger.error(f"Error loading data from {file_path}: {e}")
                return None

    def set(self, value: Any, owner_id: str) -> None:
        """设置数据并更新索引和缓存"""
        # 更新文件
        self._save_owner_data(owner_id, value)
        
        # 更新缓存
        self._data_cache.put(owner_id, value)
        
        # 更新索引
        if value is not None and self._index_fields:
            self._update_indexes(value, owner_id)
            self._save_indexes()

    def delete(self, owner_id: str) -> bool:
        """删除数据并更新索引和缓存"""
        file_path = self._get_file_path(owner_id)
        if not file_path.exists():
            return False
            
        with self._get_file_lock(owner_id):
            try:
                file_path.unlink()
                # 清除缓存
                self._data_cache.remove(owner_id)
                # 更新索引
                self._remove_from_indexes(owner_id)
                self._save_indexes()
                return True
            except Exception as e:
                self.logger.error(f"Error deleting data for {owner_id}: {e}")
                return False

    def clear_cache(self) -> None:
        """清除所有缓存数据"""
        self._data_cache.clear()

    def get_cache_info(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        return {
            "capacity": self._data_cache.capacity,
            "size": len(self._data_cache._cache)
        }

    def find(self, conditions: Dict[str, Any], owner_id: str = "") -> List[Any]:
        """查找匹配指定条件的数据，优先使用索引"""
        # 确定搜索范围
        owners = [owner_id] if owner_id else self.list_owners()
        
        # 检查是否可以使用索引
        indexed_field = next(
            (field for field in self._index_fields 
             if field in conditions),
            None
        )
        
        if indexed_field:
            # 使用索引查找
            owner_ids = self._find_with_index(indexed_field, conditions[indexed_field])
            # 过滤owner范围
            owner_ids = [oid for oid in owner_ids if oid in owners]
            results = []
            
            # 加载并验证其他条件
            for owner_id in owner_ids:
                data = self.get(owner_id)
                if data and self._match_conditions(data, conditions):
                    results.append(data)
            return results
        
        # 无索引时的常规查找
        results = []
        for current_owner_id in owners:
            data = self.get(current_owner_id)
            if data and self._match_conditions(data, conditions):
                results.append(data)
        return results

    def has_duplicate(self, unique_attributes: Dict[str, Any], owner_id: str = "") -> bool:
        """检查是否存在具有相同唯一属性值的数据"""
        owners = [owner_id] if owner_id else self.list_owners()
        
        for current_owner_id in owners:
            if current_owner_id not in self._data:
                self._load_owner_data(current_owner_id)
            
            data = self._data.get(current_owner_id)
            if data is not None and all(getattr(data, k, None) == v for k, v in unique_attributes.items()):
                return True
        
        return False

    def list_owners(self) -> List[str]:
        """列出所有的所有者ID"""
        try:
            if not self._data_dir.exists():
                return []
            
            return [
                owner_dir.name 
                for owner_dir in self._data_dir.iterdir() 
                if owner_dir.is_dir() and 
                owner_dir.name != '.indexes' and  # 排除 .indexes 目录
                (owner_dir / self._filename).exists()
            ]
        except Exception as e:
            self.logger.error(f"Error listing owners: {e}")
            return []

    # 以下是内部辅助方法
    def _get_file_path(self, owner_id: str) -> Path:
        """获取文件路径"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
        return self._data_dir / owner_id / self._filename

    @contextmanager
    def _get_file_lock(self, owner_id: str):
        """获取特定所有者的文件锁"""
        with self._file_locks_lock:
            if owner_id not in self._file_locks:
                self._file_locks[owner_id] = threading.Lock()
            file_lock = self._file_locks[owner_id]
        try:
            file_lock.acquire()
            yield
        finally:
            file_lock.release()

    def _load_owner_data(self, owner_id: str) -> None:
        """加载所有者的数据"""
        try:
            file_path = self._get_file_path(owner_id)
            if not file_path.exists():
                self._data[owner_id] = None
                return

            with self._get_file_lock(owner_id):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        raw_data = json.load(f)
                    try:
                        self._data[owner_id] = self._deserializer(raw_data)
                    except Exception as e:
                        self.logger.error(f"Failed to deserialize data for {owner_id}: {e}")
                        self._data[owner_id] = None
                except json.JSONDecodeError as e:
                    self.logger.error(f"Invalid JSON in file {file_path}: {e}")
                    self._data[owner_id] = None
        except Exception as e:
            self.logger.error(f"Error loading data from {file_path}: {e}")
            self._data[owner_id] = None

    def _save_owner_data(self, owner_id: str, data: Any) -> None:
        """保存所有者的数据
        
        Args:
            owner_id (str): 所有者ID
            data (Any): 要保存的数据
        """
        file_path = self._get_file_path(owner_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_file_lock(owner_id):
            try:
                if data is None:
                    return
                data_to_save = self._serializer(data)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data_to_save, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            except Exception as e:
                self.logger.error(f"Error saving data to {file_path}: {e}")
                raise

    def _validate_index_fields(self) -> None:
        """验证索引字段的有效性"""
        if not self._index_fields:
            return
            
        sample_instance = self._create_default_instance()
        if not sample_instance:
            return
            
        for field in self._index_fields:
            if not hasattr(sample_instance, field):
                raise ValueError(f"无效的索引字段: {field}")

    def _get_index_path(self) -> Path:
        """获取索引文件路径"""
        return self._data_dir / ".indexes" / self._filename

    def _load_indexes(self) -> None:
        """加载索引数据"""
        index_path = self._get_index_path()
        if not index_path.exists():
            return
            
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                self._indexes = json.load(f)
        except Exception as e:
            self.logger.error(f"加载索引失败: {e}")
            self._indexes = {}

    def _save_indexes(self) -> None:
        """保存索引数据"""
        index_path = self._get_index_path()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(self._indexes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存索引失败: {e}")

    def _update_indexes(self, data: Any, owner_id: str) -> None:
        """更新索引"""
        # 删除旧索引
        self._remove_from_indexes(owner_id)
        
        # 添加新索引
        for field in self._index_fields:
            value = getattr(data, field)
            if field not in self._indexes:
                self._indexes[field] = {}
                
            value_key = str(value)  # 确保键是字符串
            if value_key not in self._indexes[field]:
                self._indexes[field][value_key] = []
            if owner_id not in self._indexes[field][value_key]:
                self._indexes[field][value_key].append(owner_id)

    def _remove_from_indexes(self, owner_id: str) -> None:
        """从索引中删除指定owner的数据"""
        for field, field_index in self._indexes.items():
            # 找到并删除所有包含该owner_id的索引项
            empty_keys = []
            for value_key, value_owners in field_index.items():
                if owner_id in value_owners:
                    value_owners.remove(owner_id)
                    # 如果索引项为空，标记删除
                    if not value_owners:
                        empty_keys.append(value_key)
            
            # 删除空的索引项
            for key in empty_keys:
                del field_index[key]

    def _find_with_index(self, field: str, value: Any) -> List[str]:
        """使用索引查找数据"""
        if field not in self._indexes:
            return []
            
        value_key = str(value)
        # 预加载所有匹配的owner_ids以减少IO操作
        matching_owners = self._indexes[field].get(value_key, [])
        return matching_owners

    def _match_conditions(self, data: Any, conditions: Dict[str, Any]) -> bool:
        """匹配所有条件"""
        if isinstance(data, dict):
            # 对于字典类型，检查其值是否匹配条件
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
        """匹配值，支持复合类型"""
        if data_value is None:
            return False
        
        if callable(condition_value):
            return condition_value(data_value)
        elif isinstance(condition_value, dict):
            if isinstance(data_value, dict):
                return all(
                    k in data_value and self._match_value(data_value[k], v)
                    for k, v in condition_value.items()
                )
            elif hasattr(data_value, '__dict__'):
                return all(
                    hasattr(data_value, k) and 
                    self._match_value(getattr(data_value, k), v)
                    for k, v in condition_value.items()
                )
            return False
        elif isinstance(condition_value, (list, tuple)):
            if isinstance(data_value, (list, tuple)):
                return all(
                    any(self._match_value(dv, cv) for dv in data_value)
                    for cv in condition_value
                )
            return False
        return data_value == condition_value

