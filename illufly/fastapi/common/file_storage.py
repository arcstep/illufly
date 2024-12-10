from typing import Dict, Any, Optional, TypeVar, Generic, Protocol, List
from pathlib import Path
import json
import threading
import copy

T = TypeVar('T')

class FileStorage(Generic[T]):
    """基于文件的存储实现"""
    def __init__(self, data_dir: Optional[str], serializer, deserializer, filename: str = "data.json"):
        self._data: Dict[str, Dict[str, T]] = {}  # owner -> {key: value}
        self._lock = threading.Lock()
        self._serializer = serializer
        self._deserializer = deserializer
        self._data_dir: Optional[Path] = None
        self._filename = filename
        if data_dir:
            self.set_data_dir(data_dir)

    def set_data_dir(self, data_dir: str) -> None:
        """设置数据目录"""
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._data.clear()  # 清除缓存的数据

    @property
    def data_dir(self) -> Optional[Path]:
        """获取数据目录"""
        return self._data_dir

    @data_dir.setter
    def data_dir(self, value: str) -> None:
        """设置数据目录"""
        self.set_data_dir(value)

    def clone(self) -> 'FileStorage[T]':
        """创建存储实例的克隆"""
        new_storage = FileStorage(
            data_dir=None,
            serializer=self._serializer,
            deserializer=self._deserializer,
            filename=self._filename
        )
        return new_storage

    def get(self, key: str, owner: str = "") -> Optional[T]:
        """获取数据，确保只能访问自己的数据"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
        
        # 检查文件是否存在，如果不存在直接返回 None
        file_path = self._get_owner_file_path(owner)
        if not file_path.exists():
            return None
            
        self._ensure_owner_data_loaded(owner)
        return self._data.get(owner, {}).get(key)

    def set(self, key: str, value: T, owner: str = "") -> None:
        """设置数据，按所有者隔离存储"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
        
        with self._lock:
            # 确保目录存在
            file_path = self._get_owner_file_path(owner)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            if owner not in self._data:
                self._data[owner] = {}
            self._data[owner][key] = value
            self._save_owner_data(owner)

    def delete(self, key: str, owner: str = "") -> bool:
        """删除数据，确保只能删除自己的数据"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        file_path = self._get_owner_file_path(owner)
        if not file_path.exists():
            return False
            
        with self._lock:
            if owner not in self._data or key not in self._data[owner]:
                return False
            del self._data[owner][key]
            self._save_owner_data(owner)
            return True

    def list_keys(self, owner: str = "") -> List[str]:
        """列出指定所有者的所有键"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        file_path = self._get_owner_file_path(owner)
        if not file_path.exists():
            return []
            
        self._ensure_owner_data_loaded(owner)
        return list(self._data.get(owner, {}).keys())

    def _get_owner_file_path(self, owner: str = "") -> Path:
        """获取所有者数据文件路径"""
        if not owner:
            # 如果没有指定 owner，直接使用配置的文件名
            return self._data_dir / self._filename
        else:
            # 如果指定了 owner，使用 owner 目录下的文件
            return self._data_dir / owner / self._filename

    def _ensure_owner_data_loaded(self, owner: str) -> None:
        """确保所有者的数据已加载"""
        if owner not in self._data:
            self._load_owner_data(owner)

    def _load_owner_data(self, owner: str) -> None:
        """加载所有者的数据"""
        file_path = self._get_owner_file_path(owner)
        if not file_path.exists():
            self._data[owner] = {}
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            self._data[owner] = {
                key: self._deserializer(value)
                for key, value in raw_data.items()
            }
        except Exception:
            self._data[owner] = {}

    def _save_owner_data(self, owner: str) -> None:
        """保存所有者的数据"""
        file_path = self._get_owner_file_path(owner)
        data = {
            key: self._serializer(value)
            for key, value in self._data[owner].items()
        }
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def list_owners(self) -> List[str]:
        """列出所有的所有者"""
        if not self._data_dir:
            return []
            
        return [
            dir.name
            for dir in self._data_dir.iterdir()
            if dir.is_dir() and (dir / self._filename).exists()
        ] 