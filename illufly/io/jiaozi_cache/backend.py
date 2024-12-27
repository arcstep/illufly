import json
import threading
from pathlib import Path
from typing import Any, Optional, List, Dict
from datetime import datetime
from abc import ABC, abstractmethod
from contextlib import contextmanager

class DateTimeEncoder(json.JSONEncoder):
    """处理datetime和自定义对象的JSON编码器"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, 'to_dict') and callable(obj.to_dict):
            return obj.to_dict()
        return super().default(obj)

class StorageBackend(ABC):
    @abstractmethod
    def get(self, owner_id: str) -> Optional[Any]:
        pass

    @abstractmethod
    def set(self, owner_id: str, data: Any) -> None:
        pass

    @abstractmethod
    def delete(self, owner_id: str) -> bool:
        pass

    @abstractmethod
    def list_owners(self) -> List[str]:
        pass

class JSONFileStorageBackend(StorageBackend):
    def __init__(self, data_dir: str, filename: str, logger=None):
        self._data_dir = Path(data_dir)
        self._filename = filename
        self.logger = logger
        self._file_locks = {}
        self._file_locks_lock = threading.Lock()
        
        # 确保数据目录存在
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def get(self, owner_id: str) -> Optional[Any]:
        """从文件中读取数据"""
        file_path = self._get_file_path(owner_id)
        if not file_path.exists():
            return None

        with self._get_file_lock(owner_id):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error loading data from {file_path}: {e}")
                return None

    def set(self, owner_id: str, data: Any) -> None:
        """将数据保存到文件"""
        file_path = self._get_file_path(owner_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_file_lock(owner_id):
            try:
                if data is None:
                    return
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error saving data to {file_path}: {e}")
                raise

    def delete(self, owner_id: str) -> bool:
        """删除文件"""
        file_path = self._get_file_path(owner_id)
        if not file_path.exists():
            return False
            
        with self._get_file_lock(owner_id):
            try:
                file_path.unlink()
                return True
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error deleting data for {owner_id}: {e}")
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
            if self.logger:
                self.logger.error(f"Error listing owners: {e}")
            return []

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