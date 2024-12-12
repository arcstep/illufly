from typing import Dict, Any, Optional, TypeVar, List, Callable
from pathlib import Path
import json
import threading
import logging
from .storage import ConfigStoreProtocol
from contextlib import contextmanager

T = TypeVar('T')

class FileConfigStore(ConfigStoreProtocol[T]):
    """基于文件的配置存储
    
    用途：
    - 智能体配置
    - 向量库配置
    - 用户Profile
    - Token管理
    等用户级配置数据
    
    特点：
    - 文件系统持久化
    - 内存缓存加速
    - 线程安全
    """
    def __init__(
        self,
        data_dir: str,
        filename: str,
        serializer: Callable[[T], Dict],
        deserializer: Callable[[Dict], T],
        logger: Optional[logging.Logger] = None
    ):
        self._data_dir = Path(data_dir)
        self._filename = filename
        self._serializer = serializer
        self._deserializer = deserializer
        self._data: Dict[str, Optional[T]] = {}
        self._lock = threading.Lock()
        self._file_locks: Dict[str, threading.Lock] = {}
        self._file_locks_lock = threading.Lock()
        self.logger = logger or logging.getLogger(__name__)

    def get(self, owner_id: str) -> Optional[T]:
        """获取指定所有者的数据"""
        with self._lock:
            if owner_id not in self._data:
                self._load_owner_data(owner_id)
            return self._data.get(owner_id)

    def set(self, value: T, owner_id: str) -> None:
        """设置指定所有者的数据"""
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

    def find(self, conditions: Dict[str, Any], owner_id: str = "") -> List[T]:
        """查找匹配指定条件的数据"""
        results = []
        owners = [owner_id] if owner_id else self.list_owners()
        
        for current_owner_id in owners:
            if current_owner_id not in self._data:
                self._load_owner_data(current_owner_id)
            
            data = self._data.get(current_owner_id)
            if data is not None and all(getattr(data, k, None) == v for k, v in conditions.items()):
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
