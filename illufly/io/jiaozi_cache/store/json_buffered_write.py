import logging
import json
import threading
import atexit
import time
from pathlib import Path
from typing import Any, Optional, List, Dict, Type, Generic, TypeVar, Set, Union, Callable
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from uuid import UUID
from pydantic import BaseModel
import hashlib
import shutil

from .base import StorageBackend
from ....config import get_env

T = TypeVar('T')

class JSONSerializationError(Exception):
    """JSON序列化错误"""
    pass

class JSONEncoder(json.JSONEncoder):
    """自定义JSON编码器"""
    def default(self, obj: Any) -> Any:
        logger = logging.getLogger('illufly.io.jiaozi_cache.store.json_buffered_write')
        logger.debug(f"尝试编码对象: {type(obj)}")
        
        # 处理常见的内置类型
        type_handlers = {
            (datetime, date): lambda x: {"__type__": "datetime", "value": x.isoformat()},
            Decimal: lambda x: {"__type__": "decimal", "value": str(x)},
            UUID: lambda x: {"__type__": "uuid", "value": str(x)},
            Enum: lambda x: {
                "__type__": "enum",
                "class": f"{obj.__class__.__module__}.{obj.__class__.__name__}",
                "value": obj.value,
                "name": obj.name
            },
            Path: lambda x: {"__type__": "path", "value": str(x)}
        }
        
        # 检查内置类型
        for types, handler in type_handlers.items():
            if isinstance(obj, types):
                logger.debug(f"使用内置类型处理器: {types}")
                return handler(obj)
        
        # 检查是否为 Pydantic 模型
        if hasattr(obj, '__class__') and hasattr(obj.__class__, 'model_dump'):
            logger.debug("处理 Pydantic 模型")
            return {
                "__type__": "model",
                "class": f"{obj.__class__.__module__}.{obj.__class__.__name__}",
                "value": obj.model_dump()
            }
            
        # 检查是否为 dataclass
        if hasattr(obj, '__class__') and hasattr(obj.__class__, '__dataclass_fields__'):
            logger.debug("处理 dataclass")
            from dataclasses import asdict
            try:
                return {
                    "__type__": "dataclass",
                    "class": f"{obj.__class__.__module__}.{obj.__class__.__name__}",
                    "value": asdict(obj)
                }
            except Exception as e:
                logger.error(f"dataclass 序列化失败: {e}")
                raise JSONSerializationError(f"dataclass 序列化失败: {e}")
            
        # 尝试使用 __dict__ 序列化，但要更严格的检查
        if hasattr(obj, '__dict__'):
            logger.debug("尝试使用 __dict__ 序列化")
            try:
                dict_value = obj.__dict__
                # 空字典不算作可序列化
                if not dict_value:
                    logger.error(f"对象的 __dict__ 为空: {type(obj)}")
                    raise JSONSerializationError(f"对象的 __dict__ 为空: {type(obj)}")
                    
                # 尝试序列化，确保所有字段都可序列化
                serialized = json.dumps(dict_value, cls=JSONEncoder)
                deserialized = json.loads(serialized)
                # 确保序列化后的数据与原始数据结构一致
                if not isinstance(deserialized, dict) or deserialized != dict_value:
                    raise JSONSerializationError("序列化结果与原始数据不一致")
                    
                return {
                    "__type__": "object",
                    "class": f"{obj.__class__.__module__}.{obj.__class__.__name__}",
                    "value": dict_value
                }
            except Exception as e:
                logger.error(f"__dict__ 序列化失败: {e}")
                raise JSONSerializationError(f"对象的 __dict__ 不可序列化: {e}")
        
        logger.error(f"无法序列化类型: {type(obj)}")
        raise JSONSerializationError(f"无法序列化类型 {type(obj).__name__}")

class TimeSeriesGranularity(Enum):
    """时间序列粒度"""
    YEARLY = "yearly"    # 按年
    MONTHLY = "monthly"  # 按月
    DAILY = "daily"      # 按天
    HOURLY = "hourly"    # 按小时

    def get_path_parts(self, now: datetime) -> list[str]:
        """获取时间分区的路径部分"""
        if self == TimeSeriesGranularity.YEARLY:
            return [f"{now.year}"]
        elif self == TimeSeriesGranularity.MONTHLY:
            return [f"{now.year}", f"{now.month:02d}"]
        elif self == TimeSeriesGranularity.DAILY:
            return [f"{now.year}", f"{now.month:02d}", f"{now.day:02d}"]
        elif self == TimeSeriesGranularity.HOURLY:
            return [f"{now.year}", f"{now.month:02d}", f"{now.day:02d}", f"{now.hour:02d}"]
        return ["default"]

class StorageStrategy(Enum):
    """存储策略"""
    INDIVIDUAL = -1      # 每个key一个目录
    SINGLE = 1          # 所有key存在一个文件
    SHARED = 100        # 默认分散到100个文件
    TIME_SERIES = "time" # 按时间序列

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
        data_dir: str,
        segment: str,
        flush_threshold: int = None,
        flush_interval: int = None,
        strategy: StorageStrategy = StorageStrategy.INDIVIDUAL,
        time_granularity: TimeSeriesGranularity = TimeSeriesGranularity.MONTHLY,
        partition_count: Optional[int] = None,
        logger: logging.Logger = None,
    ):
        self.logger = logger or logging.getLogger(__name__)
        self._data_dir = Path(data_dir)
        self._segment = segment.replace('.json', '')
        self._strategy = strategy
        self._flush_threshold = flush_threshold if flush_threshold is not None else int(get_env("JIAOZI_CACHE_FLUSH_THRESHOLD"))
        self._flush_interval = flush_interval if flush_interval is not None else int(get_env("JIAOZI_CACHE_FLUSH_INTERVAL"))
        self._time_granularity = time_granularity
        self._partition_count = partition_count or (
            strategy.value if isinstance(strategy.value, int) else 100
        )
        self._memory_buffer: Dict[str, T] = {}
        self._dirty_keys = set()
        self._modify_count = 0
        self._last_flush_time = time.time()
        
        # 线程安全
        self._buffer_lock = threading.RLock()
        self._flush_timer: Optional[threading.Timer] = None
        self._should_stop = False
        self._is_flushing = False
        
        self._flush_count = 0
        self._write_times: List[float] = []
        
        self._deleted_keys = set()  # 新增删除标记集合
        
        self.logger.info(
            "初始化存储后端: dir=%s, segment=%s, strategy=%s, threshold=%d, interval=%d",
            self._data_dir, self._segment, self._strategy, self._flush_threshold, self._flush_interval
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
        self.logger.debug(f"尝试序列化数据: {type(data)}")
        try:
            result = json.dumps(data, cls=JSONEncoder, ensure_ascii=False, indent=2)
            self.logger.debug("序列化成功")
            return result
        except Exception as e:
            self.logger.error(f"序列化失败: {e}")
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

    def list_keys(self) -> List[str]:
        """列出所有的键"""
        keys = set()
        
        if self._strategy == StorageStrategy.INDIVIDUAL:
            if self._data_dir.exists():
                return [d.name for d in self._data_dir.iterdir() if d.is_dir()]
        
        pattern = f"{self._segment}*.json"
        if self._strategy == StorageStrategy.TIME_SERIES:
            for json_file in self._data_dir.rglob(pattern):
                if json_file.is_file():
                    with json_file.open('r') as f:
                        data = json.load(f)
                        keys.update(data.keys())
        elif self._strategy == StorageStrategy.SHARED:
            for subdir in range(self._partition_count // 10 + 1):
                path = self._data_dir / str(subdir)
                if path.exists():
                    for json_file in path.glob(pattern):
                        if json_file.is_file():
                            with json_file.open('r') as f:
                                data = json.load(f)
                                keys.update(data.keys())
        else:  # SINGLE
            path = self._data_dir / f"{self._segment}.json"
            if path.exists():
                with path.open('r') as f:
                    data = json.load(f)
                    keys.update(data.keys())
                    
        return list(keys)

    def _get_time_based_path(self) -> Path:
        """获取基于时间的存储路径"""
        now = datetime.now()
        path_parts = self._time_granularity.get_path_parts(now)
        
        # 构建目录路径
        path = self._data_dir
        for part in path_parts[:-1]:  # 除最后一个部分外都作为目录
            path = path / part
            
        # 确保目录存在
        path.mkdir(parents=True, exist_ok=True)
        
        # 构建文件名，包含完整时间信息
        if self._time_granularity == TimeSeriesGranularity.YEARLY:
            filename = f"{self._segment}_{path_parts[0]}.json"
        elif self._time_granularity == TimeSeriesGranularity.MONTHLY:
            filename = f"{self._segment}_{path_parts[0]}_{path_parts[1]}.json"
        elif self._time_granularity == TimeSeriesGranularity.DAILY:
            filename = f"{self._segment}_{path_parts[0]}_{path_parts[1]}_{path_parts[2]}.json"
        elif self._time_granularity == TimeSeriesGranularity.HOURLY:
            filename = f"{self._segment}_{path_parts[0]}_{path_parts[1]}_{path_parts[2]}_{path_parts[3]}.json"
        else:
            filename = f"{self._segment}.json"
            
        return path / filename

    def _get_shared_path(self, key: str) -> Path:
        """获取基于哈希分片的存储路径"""
        hash_value = hashlib.md5(key.encode()).hexdigest()
        partition = int(hash_value, 16) % self._partition_count
        
        # 创建子目录以避免单一目录下文件过多
        if self._partition_count > 10:
            subdir = str(partition // 10)
            path = self._data_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            # 文件名包含完整分片信息
            return path / f"{self._segment}_partition_{subdir}_{partition}.json"
        
        return self._data_dir / f"{self._segment}_partition_{partition}.json"

    def _get_storage_path(self, key: str) -> Path:
        """获取存储路径
        
        Args:
            key: 数据的键
            
        Returns:
            Path: 存储路径
            
        Note:
            - INDIVIDUAL: data_dir/{key}/{segment}.json
            - SINGLE: data_dir/{segment}.json
            - SHARED: data_dir/{partition_group}/{segment}_partition_{group}_{partition}.json
            - TIME_SERIES: data_dir/{year}/{month}/{segment}_{year}_{month}_{day}.json
        """
        if self._strategy == StorageStrategy.INDIVIDUAL:
            path = self._data_dir / key
            path.mkdir(parents=True, exist_ok=True)
            return path / f"{self._segment}.json"
            
        if self._strategy == StorageStrategy.SINGLE:
            return self._data_dir / f"{self._segment}.json"
            
        if self._strategy == StorageStrategy.TIME_SERIES:
            return self._get_time_based_path()
            
        return self._get_shared_path(key)

    def set(self, key: str, value: T) -> None:
        """写入数据到缓冲区"""
        self.logger.debug(f"开始写入键 {key} 的数据")
        with self._buffer_lock:
            # 先尝试序列化，验证数据是否可序列化
            try:
                self.logger.debug("执行序列化检查")
                self._serialize(value)
            except Exception as e:
                self.logger.error(f"写入键 {key} 失败: {e}")
                raise JSONSerializationError(f"Failed to serialize data for key '{key}': {e}")
            
            self.logger.debug("序列化检查通过，写入缓冲区")
            self._memory_buffer[key] = value
            self._dirty_keys.add(key)
            self._deleted_keys.discard(key)
            self._modify_count += 1
            
            if len(self._dirty_keys) >= self._flush_threshold:
                self.logger.debug("达到刷新阈值，执行刷新操作")
                self.flush()
            
            self.logger.debug(f"键 {key} 写入完成")

    def get(self, key: str) -> Optional[T]:
        """读取数据"""
        # 先检查是否被标记为删除
        with self._buffer_lock:
            if key in self._deleted_keys:
                return None
            if key in self._memory_buffer:
                return self._memory_buffer[key]
        
        # 从文件读取
        path = self._get_storage_path(key)
        if not path.exists():
            return None
            
        try:
            with path.open('r') as f:
                data = json.load(f)
                if self._strategy == StorageStrategy.INDIVIDUAL:
                    return self._deserialize(json.dumps(data))  # 确保类型恢复
                else:
                    value = data.get(key)
                    return self._deserialize(json.dumps(value)) if value is not None else None
        except Exception as e:
            self.logger.error(f"读取数据失败: {e}")
            return None

    def delete(self, key: str) -> None:
        """删除数据"""
        with self._buffer_lock:
            # 从缓冲区移除
            self._memory_buffer.pop(key, None)
            # 从脏数据集合中移除
            self._dirty_keys.discard(key)
            # 添加到删除标记集合
            self._deleted_keys.add(key)
            self._modify_count += 1

    def _flush_to_disk(self) -> None:
        """将缓冲区数据写入磁盘的内部方法"""
        with self._buffer_lock:
            if not self._dirty_keys or self._is_flushing:
                return
                
            self._is_flushing = True
            try:
                self.flush()
            finally:
                self._is_flushing = False

    def flush(self) -> None:
        """将缓冲区数据写入磁盘"""
        with self._buffer_lock:
            if not (self._dirty_keys or self._deleted_keys):
                return

            start_time = time.time()
            try:
                # 1. 处理需要写入的数据
                file_data: Dict[Path, Dict] = {}
                for key in self._dirty_keys:
                    if key in self._memory_buffer:  # 确保键存在
                        path = self._get_storage_path(key)
                        try:
                            if self._strategy == StorageStrategy.INDIVIDUAL:
                                path.parent.mkdir(parents=True, exist_ok=True)
                                with path.open('w', encoding='utf-8') as f:
                                    json.dump(
                                        self._memory_buffer[key],
                                        f,
                                        cls=JSONEncoder,
                                        ensure_ascii=False,
                                        indent=2
                                    )
                            else:
                                if path not in file_data:
                                    file_data[path] = {}
                                    if path.exists():
                                        with path.open('r', encoding='utf-8') as f:
                                            file_data[path] = json.load(f)
                                file_data[path][key] = self._memory_buffer[key]
                        except Exception as e:
                            raise JSONSerializationError(f"Failed to serialize data for key '{key}': {e}")

                # 2. 处理需要删除的数据
                for key in self._deleted_keys:
                    path = self._get_storage_path(key)
                    if path.exists():
                        if self._strategy == StorageStrategy.INDIVIDUAL:
                            if path.exists():
                                path.unlink()
                            if path.parent.exists() and not any(path.parent.iterdir()):
                                path.parent.rmdir()
                        else:
                            if path in file_data:
                                file_data[path].pop(key, None)
                            elif path.exists():
                                with path.open('r', encoding='utf-8') as f:
                                    data = json.load(f)
                                data.pop(key, None)
                                if data:
                                    file_data[path] = data
                                else:
                                    path.unlink()

                # 3. 写入共享文件
                for path, data in file_data.items():
                    if data:  # 只写入非空数据
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with path.open('w', encoding='utf-8') as f:
                            json.dump(data, f, cls=JSONEncoder, ensure_ascii=False, indent=2)

                # 更新性能指标
                flush_time = time.time() - start_time
                self._write_times.append(flush_time)
                if len(self._write_times) > 1000:
                    self._write_times = self._write_times[-1000:]

                self._flush_count += 1
                self._last_flush_time = time.time()

                # 清空缓冲区
                self._memory_buffer.clear()
                self._dirty_keys.clear()
                self._deleted_keys.clear()

            except Exception as e:
                self.logger.error(f"Flush failed: {e}")
                raise

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

    def _flush_on_exit(self) -> None:
        """退出时的清理函数"""
        try:
            self.close()
        except Exception as e:
            # atexit阶段的错误只记录日志
            self.logger.error(f"Failed to flush data on exit: {e}")

    def close(self) -> None:
        """关闭存储，确保数据写入磁盘"""
        try:
            if self._dirty_keys:  # 只在有未保存数据时尝试写入
                self.flush()
        except Exception as e:
            self.logger.error(f"Failed to flush data on close: {e}")
        finally:
            self._memory_buffer.clear()
            self._dirty_keys.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_metrics(self) -> Dict[str, Any]:
        """获取写缓冲区性能指标"""
        with self._buffer_lock:
            return {
                "buffer_size": len(self._memory_buffer),
                "dirty_count": len(self._dirty_keys), 
                "flush_threshold": self._flush_threshold,
                "flush_count": self._flush_count,
                "last_flush": self._last_flush_time,
                "pending_writes": len(self._dirty_keys),
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
            self._dirty_keys.clear()
            
            try:
                if self._strategy == StorageStrategy.INDIVIDUAL:
                    # 删除所有子目录
                    if self._data_dir.exists():
                        shutil.rmtree(self._data_dir)
                        self._data_dir.mkdir(parents=True)
                else:
                    pattern = f"{self._segment}*.json"
                    # 递归删除所有相关文件
                    for json_file in self._data_dir.rglob(pattern):
                        if json_file.is_file():
                            json_file.unlink()
            except Exception as e:
                self.logger.error(f"清空数据失败: {e}")
                raise
