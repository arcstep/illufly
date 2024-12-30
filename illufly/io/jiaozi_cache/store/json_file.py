import logging
import json
import threading
import atexit
import time
from pathlib import Path
from typing import Any, Optional, List, Dict, Type
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from uuid import UUID
try:
    from pydantic import BaseModel
except ImportError:
    BaseModel = None

from .base import StorageBackend
from ....config import get_env


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
            Enum: lambda x: {"__type__": "enum", "class": x.__class__.__name__, "value": x.value},
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
                "class": obj.__class__.__name__, 
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
                "class": obj.__class__.__name__,
                "value": obj.__dict__
            }
            
        # 添加元组处理
        if isinstance(obj, tuple):
            return {"__type__": "tuple", "value": list(obj)}
            
        # 尝试直接序列化
        try:
            return super().default(obj)
        except Exception as e:
            raise JSONSerializationError(f"无法序列化类型 {type(obj).__name__}: {e}")


class BufferedJSONFileStorageBackend(StorageBackend):
    """带写缓冲的JSON文件存储后端"""
    
    def __init__(
        self, 
        data_dir: str = None, 
        segment: str = None,
        flush_interval: int = 60,
        flush_threshold: int = 1000,
        logger = None
    ):
        self.logger = logger or logging.getLogger(__name__)
        self._data_dir = Path(data_dir) if data_dir else get_env("ILLUFLY_JIAOZI_CACHE_STORE_DIR")
        self._segment = segment or "data.json"
        
        # 写缓冲相关
        self._memory_buffer = {}
        self._dirty_owners = set()
        self._modify_count = 0
        self._last_flush_time = time.time()
        self._flush_interval = flush_interval
        self._flush_threshold = flush_threshold
        
        # 线程安全
        self._buffer_lock = threading.RLock()
        self._flush_timer = None
        self._should_stop = False
        self._is_flushing = False
        
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
                "enum": lambda x: x,
                "pydantic": lambda x: x,
                "custom": lambda x: x,
                "object": lambda x: x
            }
            
            def object_hook(obj: Dict) -> Any:
                if "__type__" not in obj:
                    return obj
                    
                obj_type = obj["__type__"]
                value = obj["value"]
                
                if obj_type in ("dataclass", "custom"):
                    module_path, class_name = obj["class"].rsplit('.', 1)
                    try:
                        import importlib
                        module = importlib.import_module(module_path)
                        cls = getattr(module, class_name)
                        if hasattr(cls, '__dataclass_fields__'):
                            return cls(**value)
                        return cls(**value)
                    except (ImportError, AttributeError) as e:
                        self.logger.warning(
                            "无法恢复类型 %s: %s，返回原始值", 
                            obj["class"], e
                        )
                        return value
                
                if obj_type == "tuple":
                    return tuple(value)
                
                handler = type_handlers.get(obj_type)
                if handler:
                    return handler(value)
                
                if obj_type == "enum":
                    # 获取枚举类
                    module_path, class_name = obj["class"].rsplit('.', 1)
                    try:
                        import importlib
                        module = importlib.import_module(module_path)
                        enum_class = getattr(module, class_name)
                        # 尝试通过名称恢复枚举值
                        return enum_class[obj["name"]]
                    except (ImportError, AttributeError) as e:
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

    def get(self, owner_id: str) -> Optional[Any]:
        """获取数据，优先从内存缓冲区读取"""
        with self._buffer_lock:
            if owner_id in self._memory_buffer:
                value = self._memory_buffer[owner_id]
                if value is None:
                    return None
                self.logger.debug("从内存缓冲区读取: owner_id=%s", owner_id)
                return value
        
        file_path = self._data_dir / self._segment
        if not file_path.exists():
            return None
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f).get(owner_id)
        except Exception as e:
            self.logger.error("读取文件失败: owner_id=%s, error=%s", owner_id, e)
            return None

    def set(self, owner_id: str, data: Any) -> None:
        """写入数据到内存缓冲区"""
        if data is None:
            self.logger.debug("跳过空数据写入: owner_id=%s", owner_id)
            return
            
        try:
            self._serialize(data)
        except JSONSerializationError as e:
            self.logger.error("数据序列化验证失败: %s", e)
            raise

        with self._buffer_lock:
            self._memory_buffer[owner_id] = data
            self._dirty_owners.add(owner_id)
            self._modify_count += 1
            
            if (self._modify_count >= self._flush_threshold or 
                time.time() - self._last_flush_time >= self._flush_interval):
                self._flush_to_disk()

    def delete(self, owner_id: str) -> bool:
        """删除数据"""
        with self._buffer_lock:
            if owner_id in self._memory_buffer or self.get(owner_id) is not None:
                self._memory_buffer[owner_id] = None
                self._dirty_owners.add(owner_id)
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
                
                for owner_id in self._dirty_owners:
                    value = self._memory_buffer.get(owner_id)
                    if value is None:
                        current_data.pop(owner_id, None)
                    else:
                        current_data[owner_id] = value
                
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(self._serialize(current_data))
                except Exception as e:
                    self.logger.error("写入文件失败: %s", e)
                    raise
                
                self._dirty_owners.clear()
                self._modify_count = 0
                self._last_flush_time = time.time()
                
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