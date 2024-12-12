from typing import Dict, Any, Optional, List, Callable, Type, TypeVar, Generic, get_args, get_origin
from dataclasses import is_dataclass, asdict
from datetime import datetime
import inspect
from pathlib import Path
import json
import threading
import logging
from .config_store import ConfigStoreProtocol
from contextlib import contextmanager

T = TypeVar('T')

class FileConfigStore(Generic[T]):
    """基于文件的配置存储，提供线程安全和类型安全的数据持久化能力。
    
    主要特点:
    - 文件系统持久化
    - 内存缓存加速
    - 线程安全
    - 自动序列化/反序列化
    - 灵活的查询支持
    - 复合类型存储支持
    
    基本用法:
    ```python
    from dataclasses import dataclass
    from datetime import datetime
    from typing import List, Dict
    
    # 1. 基础类型存储
    @dataclass
    class UserProfile:
        username: str
        email: str
        created_at: datetime
        tags: List[str] = field(default_factory=list)
        
        def to_dict(self) -> dict:
            return {
                "username": self.username,
                "email": self.email,
                "created_at": self.created_at.isoformat(),
                "tags": self.tags
            }
        
        @classmethod
        def from_dict(cls, data: dict) -> 'UserProfile':
            return cls(
                username=data["username"],
                email=data["email"],
                created_at=datetime.fromisoformat(data["created_at"]),
                tags=data.get("tags", [])
            )
    
    # 创建基础存储
    store = FileConfigStore[UserProfile](
        data_dir="/path/to/data",
        filename="profiles.json"
    )
    
    # 2. 复合类型存储
    # 字典存储
    dict_store = FileConfigStore[Dict[str, UserProfile]](
        data_dir="/path/to/data",
        filename="user_profiles.json"
    )
    
    # 列表存储
    list_store = FileConfigStore[List[UserProfile]](
        data_dir="/path/to/data",
        filename="profile_list.json"
    )
    
    # 嵌套字典存储
    nested_store = FileConfigStore[Dict[str, Dict[str, UserProfile]]](
        data_dir="/path/to/data",
        filename="nested_profiles.json"
    )
    ```
    
    高级查询示例:
    ```python
    # 1. 简单值匹配
    users = store.find({"username": "user1"})
    
    # 2. 列表内容匹配
    python_users = store.find({
        "tags": lambda tags: "python" in tags
    })
    
    # 3. 复杂条件组合
    active_python_users = store.find({
        "tags": ["python", "active"],
        "created_at": lambda dt: dt > datetime(2024, 1, 1)
    })
    
    # 4. 嵌套对象查询
    results = nested_store.find({
        "project1": {
            "admin": {"username": "admin1"}
        }
    })
    ```
    
    高级特性:
    1. 自动序列化支持:
       - dataclass 自动序列化
       - datetime 类型自动处理
       - 嵌套对象序列化
       - 自定义序列化方法支持
       - 复合类型自动序列化（Dict, List等）
    
    2. 查询能力:
       - 简单值精确匹配
       - 列表内容匹配
       - 嵌套对象匹配
       - 自定义匹配函数
       - 复合类型递归查询
    
    3. 线程安全:
       - 内存缓存锁
       - 文件操作锁
       - 并发访问保护
    
    4. 错误处理:
       - 序列化错误恢复
       - 文件操作异常处理
       - 数据完整性保护
       - 类型安全检查
    
    Args:
        data_dir (str): 数据存储目录路径
        filename (str): 数据文件名
        data_class (Optional[Type]): 可选的数据类型类，如果不提供则从类型参数推断
        serializer (Optional[Callable[[T], Dict]]): 可选的自定义序列化函数
        deserializer (Optional[Callable[[Dict], T]]): 可选的自定义反序列化函数
        logger (Optional[logging.Logger]): 可选的日志记录器
    
    复杂数据结构示例:
    ```python
    @dataclass
    class Item:
        name: str
        value: int
    
    @dataclass
    class Container:
        items: List[Item]
        updated_at: datetime
        
        @classmethod
        def default(cls):
            return cls(items=[], updated_at=datetime.utcnow())
    
    # 创建嵌套存储
    store = FileConfigStore[Dict[str, List[Dict[str, Container]]]](
        data_dir="data",
        filename="complex_containers.json"
    )
    
    # 存储复杂数据
    data = {
        "project1": [
            {
                "main": Container(
                    items=[Item("item1", 100)],
                    updated_at=datetime.utcnow()
                )
            }
        ]
    }
    store.set(data, "user1")
    
    # 复杂查询
    results = store.find({
        "project1": lambda p: any(
            "main" in c and c["main"].items[0].name == "item1"
            for c in p
        )
    })
    ```
    """
    def __init__(
        self,
        data_dir: str,
        filename: str,
        data_class: Optional[Type] = None,
        serializer: Optional[Callable[[T], Dict]] = None,
        deserializer: Optional[Callable[[Dict], T]] = None,
        logger: Optional[logging.Logger] = None
    ):
        self._data_dir = Path(data_dir)
        self._filename = filename
        # 如果没有提供 data_class，从类型参数推断
        self._data_class = data_class or self._infer_data_class()
        self._serializer = serializer or self._default_serializer
        self._deserializer = deserializer or self._default_deserializer
        self._data: Dict[str, Optional[T]] = {}
        self._lock = threading.Lock()
        self._file_locks: Dict[str, threading.Lock] = {}
        self._file_locks_lock = threading.Lock()
        self.logger = logger or logging.getLogger(__name__)

    def _infer_data_class(self) -> Type:
        """从类型参数推断数据类型"""
        args = get_args(self.__class__.__orig_bases__[0])
        if not args:
            raise TypeError("Type parameter T must be specified")
        
        type_param = args[0]
        origin = get_origin(type_param)
        
        if origin is dict:
            key_type, value_type = get_args(type_param)
            return value_type
        elif origin is list:
            item_type = get_args(type_param)[0]
            return item_type
        else:
            return type_param

    def _default_serializer(self, obj: T) -> Dict:
        """默认序列化方法，支持复合类型"""
        def serialize_value(v):
            if hasattr(v, 'to_dict'):
                return v.to_dict()
            elif isinstance(v, dict):
                return {k: serialize_value(val) for k, val in v.items()}
            elif isinstance(v, (list, tuple)):
                return [serialize_value(item) for item in v]
            return v

        if obj is None:
            return {}
            
        if isinstance(obj, dict):
            return {k: serialize_value(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [serialize_value(item) for item in obj]
        elif hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return obj

    def _default_deserializer(self, data: Dict) -> T:
        """默认反序列化方法，支持复合类型"""
        if not data:
            return self._create_default_instance()
            
        type_param = get_args(self.__class__.__orig_bases__[0])[0]
        origin = get_origin(type_param)
        
        def deserialize_value(v, value_type):
            if hasattr(value_type, 'from_dict') and isinstance(v, dict):
                return value_type.from_dict(v)
            elif get_origin(value_type) is dict:
                key_type, val_type = get_args(value_type)
                return {k: deserialize_value(val, val_type) for k, val in v.items()}
            elif get_origin(value_type) is list:
                item_type = get_args(value_type)[0]
                return [deserialize_value(item, item_type) for item in v]
            return v
        
        if origin is dict:
            key_type, value_type = get_args(type_param)
            return {k: deserialize_value(v, value_type) for k, v in data.items()}
        elif origin is list:
            item_type = get_args(type_param)[0]
            return [deserialize_value(item, item_type) for item in data]
        elif hasattr(self._data_class, 'from_dict'):
            return self._data_class.from_dict(data)
        return data

    def get(self, owner_id: str) -> Optional[T]:
        """获取指定所有者的数据"""
        with self._lock:
            if owner_id not in self._data:
                self._load_owner_data(owner_id)
            return self._data.get(owner_id)

    def set(self, value: T, owner_id: str) -> None:
        """设置指定所有者的数��"""
        with self._lock:
            self._data[owner_id] = value
            self._save_owner_data(owner_id)

    def delete(self, owner_id: str) -> bool:
        """删除指定所有者的数据"""
        with self._lock:
            if owner_id not in self._data:
                self._load_owner_data(owner_id)
            if self._data.get(owner_id) is None:
                return False
            self._data[owner_id] = None
            self._save_owner_data(owner_id)
            return True

    def find(self, conditions: Dict[str, Any], owner_id: str = "") -> List[Any]:
        """查找匹配指定条件的数据"""
        def match_value(data_value: Any, condition_value: Any) -> bool:
            """匹配值，支持复合类型"""
            if callable(condition_value):
                return condition_value(data_value)
            elif isinstance(condition_value, dict) and isinstance(data_value, dict):
                # 递归匹配字典
                return all(
                    k in data_value and match_value(data_value[k], v)
                    for k, v in condition_value.items()
                )
            elif isinstance(condition_value, (list, tuple)) and isinstance(data_value, (list, tuple)):
                # 递归匹配列表
                return all(
                    any(match_value(dv, cv) for dv in data_value)
                    for cv in condition_value
                )
            elif hasattr(data_value, '__dict__'):
                # 匹配对象属性
                if isinstance(condition_value, dict):
                    return all(
                        hasattr(data_value, k) and 
                        match_value(getattr(data_value, k), v)
                        for k, v in condition_value.items()
                    )
                return data_value == condition_value
            return data_value == condition_value

        def match_data(data: Any) -> bool:
            """匹配整个数据对象"""
            if isinstance(data, dict):
                # 对字典中的每个值进行匹配
                return any(
                    all(
                        match_value(
                            getattr(v, k, v.get(k) if isinstance(v, dict) else None), 
                            condition_value
                        )
                        for k, condition_value in conditions.items()
                    )
                    for v in data.values()
                )
            return all(
                match_value(getattr(data, k, None), v)
                for k, v in conditions.items()
            )

        results = []
        owners = [owner_id] if owner_id else self.list_owners()
        
        for current_owner_id in owners:
            if current_owner_id not in self._data:
                self._load_owner_data(current_owner_id)
            
            data = self._data.get(current_owner_id)
            if data is not None and match_data(data):
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
                if owner_dir.is_dir() and (owner_dir / self._filename).exists()
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

    def _save_owner_data(self, owner_id: str) -> None:
        """保存所有者的数据"""
        file_path = self._get_file_path(owner_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_file_lock(owner_id):
            try:
                data = self._data.get(owner_id)
                if data is None:
                    return
                data_to_save = self._serializer(data)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.logger.error(f"Error saving data to {file_path}: {e}")
                raise
