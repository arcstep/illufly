import logging
import json
import threading
import atexit
import time
from pathlib import Path
from typing import Any, Optional, List, Dict, Type, Generic, TypeVar, Set
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from uuid import UUID
from pydantic import BaseModel

from .base import StorageBackend
from ....config import get_env

T = TypeVar('T')

class JSONSerializationError(Exception):
    """JSON序列化错误"""
    pass

class JSONEncoder(json.JSONEncoder):
    """自定义JSON编码器"""
    def default(self, obj: Any) -> Any:
        # 处理常见的内置类型
        type_handlers = {
            (datetime, date): lambda x: {"__type__": "datetime", "value": x.isoformat()},
            Decimal: lambda x: {"__type__": "decimal", "value": str(x)},
            UUID: lambda x: {"__type__": "uuid", "value": str(x)},
            Enum: lambda x: {"__type__": "enum", "class": f"{obj.__class__.__module__}.{obj.__class__.__name__}", "value": obj.value, "name": obj.name},
            Path: lambda x: {"__type__": "path", "value": str(x)}
        }
        
        # 检查内置类型
        for types, handler in type_handlers.items():
            if isinstance(obj, types):
                return handler(obj)
                
        # 处理Pydantic模型
        if BaseModel and isinstance(obj, BaseModel):
            return {
                "__type__": "pydantic",
                "class": f"{obj.__class__.__module__}.{obj.__class__.__name__}", 
                "value": obj.model_dump()
            }
        
        # 处理 dataclass
        if hasattr(obj, '__dataclass_fields__'):
            return {
                "__type__": "dataclass",
                "class": f"{obj.__class__.__module__}.{obj.__class__.__name__}",
                "value": {k: getattr(obj, k) for k in obj.__dataclass_fields__}
            }
            
        # 处理带 to_dict 方法的对象
        if hasattr(obj, 'to_dict'):
            return {
                "__type__": "custom",
                "class": f"{obj.__class__.__module__}.{obj.__class__.__name__}",
                "value": obj.to_dict()
            }
            
        if hasattr(obj, '__dict__'):
            return {
                "__type__": "object", 
                "class": f"{obj.__class__.__module__}.{obj.__class__.__name__}",
                "value": obj.__dict__
            }
            
        # 添加元组和集合处理
        if isinstance(obj, tuple):
            return {"__type__": "tuple", "value": list(obj)}
            
        if isinstance(obj, set):
            return {"__type__": "set", "value": list(obj)}
            
        # 尝试直接序列化
        try:
            return super().default(obj)
        except Exception as e:
            raise JSONSerializationError(f"无法序列化类型 {type(obj).__name__}: {e}")


class WriteBufferedJSONStorage(StorageBackend, Generic[T]):
    """带写缓冲的JSON文件存储后端
    
    特性：
    1. 支持写缓冲和批量刷新
    2. 线程安全
    3. 自动类型序列化
    4. 支持复杂数据类型
    5. 泛型类型支持
    6. 可监控的性能指标
    
    适用场景：
    1. 需要高性能写入
    2. 处理复杂数据类型
    3. 作为组合对象使用
    """
    
    def __init__(
        self,
        data_dir: Optional[str] = None,
        segment: Optional[str] = None,
        flush_interval: int = 60,
        flush_threshold: int = 1000,
        logger: Optional[logging.Logger] = None,
        max_time_samples: int = 1000
    ):
        self.logger = logger or logging.getLogger(__name__)
        self._data_dir = Path(data_dir) if data_dir else Path(get_env("ILLUFLY_JIAOZI_CACHE_STORE_DIR"))
        self._segment = segment or "data.json"
        
        # 写缓冲相关
        self._memory_buffer: Dict[str, Optional[T]] = {}
        self._dirty_owners: Set[str] = set()
        self._modify_count = 0
        self._last_flush_time = time.time()
        self._flush_interval = max(1, flush_interval)  # 确保最小间隔为1秒
        self._flush_threshold = max(1, flush_threshold)  # 确保最小阈值为1
        
        # 线程安全
        self._buffer_lock = threading.RLock()
        self._flush_timer: Optional[threading.Timer] = None
        self._should_stop = False
        self._is_flushing = False
        
        self._flush_count = 0
        self._write_times: List[float] = []
        self._max_time_samples = max(100, max_time_samples)  # 确保最小样本数为100
        
        self.logger.info(
            "初始化存储后端: dir=%s, segment=%s, interval=%d, threshold=%d",
            self._data_dir, self._segment, flush_interval, flush_threshold
        )
        
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._start_flush_timer()
            atexit.register(self._flush_on_exit)
        except Exception as e:
            self.logger.critical("初始化失败: %s", str(e), exc_info=True)
            raise

        self._encoder = JSONEncoder(ensure_ascii=False)

    def _serialize(self, data: Any) -> str:
        """序列化数据为JSON字符串"""
        try:
            return json.dumps(data, cls=JSONEncoder, ensure_ascii=False, indent=2)
        except Exception as e:
            raise JSONSerializationError(f"序列化失败: {e}")

    def _deserialize(self, json_str: str) -> Any:
        """反序列化JSON字符串为Python对象"""
        try:
            type_handlers = {
                "datetime": lambda x: datetime.fromisoformat(x),
                "decimal": lambda x: Decimal(x),
                "uuid": lambda x: UUID(x),
                "path": lambda x: Path(x),
                "set": lambda x: set(x),
                "tuple": lambda x: tuple(x)
            }
            
            def object_hook(obj: Dict) -> Any:
                if "__type__" not in obj:
                    return obj
                    
                obj_type = obj["__type__"]
                value = obj["value"]
                
                if obj_type in type_handlers:
                    return type_handlers[obj_type](value)
                
                if obj_type in ("dataclass", "custom", "pydantic", "object"):
                    try:
                        module_path, class_name = obj["class"].rsplit('.', 1)
                        import importlib
                        module = importlib.import_module(module_path)
                        cls = getattr(module, class_name)
                        
                        if obj_type == "pydantic" and issubclass(cls, BaseModel):
                            return cls.model_validate(value)
                            
                        return cls(**value)
                    except (ImportError, AttributeError) as e:
                        self.logger.warning(
                            "无法恢复类型 %s: %s，返回原始值", 
                            obj["class"], e
                        )
                        return value
                
                if obj_type == "enum":
                    try:
                        module_path, class_name = obj["class"].rsplit('.', 1)
                        import importlib
                        module = importlib.import_module(module_path)
                        enum_class = getattr(module, class_name)
                        return enum_class[obj["name"]]
                    except (ImportError, AttributeError, KeyError) as e:
                        self.logger.warning(
                            "无法恢复枚举类型 %s: %s，返回原始值", 
                            obj["class"], e
                        )
                        return obj["value"]
                
                return obj
                
            return json.loads(json_str, object_hook=object_hook)
        except Exception as e:
            raise JSONSerializationError(f"反序列化失败: {e}")

    def list_owners(self) -> List[str]:
        """列出所有数据所有者ID"""
        with self._buffer_lock:
            memory_owners = set(self._memory_buffer.keys())
            file_owners = set()
            
            file_path = self._data_dir / self._segment
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_owners = set(json.load(f).keys())
                except Exception as e:
                    self.logger.error("读取文件失败: %s", e)
            
            deleted_owners = {
                owner_id for owner_id, value in self._memory_buffer.items() 
                if value is None
            }
            
            all_owners = (memory_owners | file_owners) - deleted_owners
            
            self.logger.debug(
                "列出所有owner: memory=%d, file=%d, total=%d", 
                len(memory_owners), len(file_owners), len(all_owners)
            )
            return sorted(all_owners)

    def get(self, key: str) -> Optional[T]:
        """获取数据"""
        with self._buffer_lock:
            if key in self._memory_buffer:
                value = self._memory_buffer[key]
                if value is None:
                    return None
                self.logger.debug("从内存缓冲区读取: key=%s", key)
                return value
        
        file_path = self._data_dir / self._segment
        if not file_path.exists():
            return None
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = self._deserialize(f.read())
                return data.get(key)
        except Exception as e:
            self.logger.error("读取文件失败: key=%s, error=%s", key, e)
            return None

    def set(self, key: str, value: T) -> None:
        """写入数据到缓冲区"""
        if not isinstance(key, str):
            raise TypeError("键必须是字符串类型")
            
        if not key:
            raise ValueError("键不能为空")
            
        # 先尝试序列化，确保数据可以被保存
        try:
            self._serialize({"test": value})
        except JSONSerializationError as e:
            self.logger.error(f"数据无法序列化: key={key}, error={e}")
            raise
        
        start_time = time.perf_counter()
        
        with self._buffer_lock:
            try:
                self._memory_buffer[key] = value
                self._dirty_owners.add(key)
                self._modify_count += 1
                
                # 记录写入时间
                write_time = time.perf_counter() - start_time
                if len(self._write_times) >= self._max_time_samples:
                    self._write_times.pop(0)
                self._write_times.append(write_time)
                
                # 检查是否需要刷新
                if len(self._dirty_owners) >= self._flush_threshold:
                    self._flush_to_disk()
                    
            except Exception as e:
                self.logger.error(f"写入错误: key={key}, error={e}")
                raise

    def delete(self, key: str) -> bool:
        """删除数据"""
        with self._buffer_lock:
            if key in self._memory_buffer or self.get(key) is not None:
                self._memory_buffer[key] = None
                self._dirty_owners.add(key)
                self._modify_count += 1
                return True
            return False

    def _flush_to_disk(self):
        """将缓冲区数据写入磁盘"""
        if self._is_flushing:
            return
            
        try:
            self._is_flushing = True
            
            with self._buffer_lock:
                if not self._dirty_owners:
                    return
                    
                file_path = self._data_dir / self._segment
                current_data = {}
                
                if file_path.exists():
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            current_data = self._deserialize(f.read())
                    except Exception as e:
                        self.logger.error("读取文件失败: %s", e)
                
                for key in self._dirty_owners:
                    value = self._memory_buffer.get(key)
                    if value is None:
                        current_data.pop(key, None)
                    else:
                        current_data[key] = value
                
                # 创建临时文件
                temp_file = file_path.with_suffix('.tmp')
                try:
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        f.write(self._serialize(current_data))
                    # 原子性地替换文件
                    temp_file.replace(file_path)
                except Exception as e:
                    self.logger.error("写入文件失败: %s", e)
                    if temp_file.exists():
                        temp_file.unlink()
                    raise
                
                self._dirty_owners.clear()
                self._modify_count = 0
                self._last_flush_time = time.time()
                self._flush_count += 1
                
        finally:
            self._is_flushing = False

    def _start_flush_timer(self):
        """启动定时刷新计时器"""
        if self._should_stop:
            return
            
        def _timer_callback():
            if not self._should_stop and not self._is_flushing:
                try:
                    self._flush_to_disk()
                except Exception as e:
                    self.logger.error("定时刷新失败: %s", e)
                finally:
                    if not self._should_stop:
                        self._start_flush_timer()
        
        if self._flush_timer:
            self._flush_timer.cancel()
        
        self._flush_timer = threading.Timer(self._flush_interval, _timer_callback)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _flush_on_exit(self):
        """程序退出时的清理工作"""
        self._should_stop = True
        if self._flush_timer:
            self._flush_timer.cancel()
        self._flush_to_disk()

    def close(self):
        """关闭存储后端"""
        self._should_stop = True
        if self._flush_timer:
            self._flush_timer.cancel()
        self._flush_to_disk()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_metrics(self) -> Dict[str, Any]:
        """获取写缓冲区性能指标"""
        with self._buffer_lock:
            return {
                "buffer_size": len(self._memory_buffer),
                "flush_threshold": self._flush_threshold,
                "flush_count": self._flush_count,
                "last_flush": self._last_flush_time,
                "pending_writes": len(self._dirty_owners),
                "total_writes": self._modify_count,
                "avg_write_time": (
                    sum(self._write_times) / len(self._write_times) * 1000  # 转换为毫秒
                    if self._write_times else 0.0
                )
            }

    def get_from_buffer(self, key: str) -> Optional[T]:
        """从写缓冲区读取数据"""
        with self._buffer_lock:
            return self._memory_buffer.get(key)

    def invalidate_key(self, key: str) -> None:
        """使指定键的缓存失效"""
        with self._buffer_lock:
            self._memory_buffer.pop(key, None)

    def clear(self) -> None:
        """清空所有数据"""
        with self._buffer_lock:
            self._memory_buffer.clear()
            self._dirty_owners.clear()
            self._modify_count = 0
            
        # 清空文件
        file_path = self._data_dir / self._segment
        if file_path.exists():
            file_path.unlink()  # 删除文件
