from typing import Dict, Any, Optional, TypeVar, Generic, Protocol, List, Callable
from pathlib import Path
import json
import threading
import copy
from .storage import StorageProtocol

T = TypeVar('T')

class FileStorage(StorageProtocol[T]):
    """基于文件的存储实现"""
    def __init__(
        self,
        data_dir: str,
        filename: str,
        serializer: Callable[[T], Dict],
        deserializer: Callable[[Dict], T],
        use_owner_subdirs: bool = False  # 新增参数控制是否使用 owner 子目录
    ):
        self._data_dir = Path(data_dir)
        self._filename = filename
        self._serializer = serializer
        self._deserializer = deserializer
        self._use_owner_subdirs = use_owner_subdirs
        self._data: Dict[str, Any] = {}

    def _get_owner_file_path(self, owner: str) -> Path:
        """获取所有者的文件路径"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        if self._use_owner_subdirs:
            # 使用 owner 子目录模式
            return self._data_dir / owner / self._filename
        else:
            # 直接使用文件模式
            return self._data_dir / self._filename

    def _load_owner_data(self, owner: str) -> None:
        """加载所有者的数据"""
        file_path = self._get_owner_file_path(owner)
        if not file_path.exists():
            self._data[owner] = {} if not self._use_owner_subdirs else None
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
                
            if self._use_owner_subdirs:
                # 子目录模式：直接反序列化
                self._data[owner] = self._deserializer(raw_data)
            else:
                # 直接文件模式：反序列化每个键
                self._data[owner] = {
                    k: self._deserializer(v)
                    for k, v in raw_data.items()
                }
        except Exception as e:
            print(f"Error loading data from {file_path}: {e}")
            self._data[owner] = {} if not self._use_owner_subdirs else None

    def _save_owner_data(self, owner: str) -> None:
        """保存所有者的数据"""
        file_path = self._get_owner_file_path(owner)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            if self._use_owner_subdirs:
                # 子目录模式：序列化单个对象
                data_to_save = self._serializer(self._data[owner])
            else:
                # 直接文件模式：序列化所有键值对
                data_to_save = {
                    k: self._serializer(v)
                    for k, v in self._data[owner].items()
                }
                
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving data to {file_path}: {e}")
            raise

    def clone(self) -> 'FileStorage[T]':
        """创建存储实例的克隆"""
        return FileStorage(
            data_dir=str(self._data_dir),
            filename=self._filename,
            serializer=self._serializer,
            deserializer=self._deserializer,
            use_owner_subdirs=self._use_owner_subdirs
        )

    def get(self, key: str, owner: str = "") -> Optional[T]:
        """获取数据"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        if owner not in self._data:
            self._load_owner_data(owner)
            
        if self._use_owner_subdirs:
            # 子目录模式：直接返回数据
            return self._data.get(owner)
        else:
            # 直接文件模式：返回特定键的数据
            return self._data.get(owner, {}).get(key)

    def set(self, key: str, value: T, owner: str = "") -> None:
        """设置数据"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        if self._use_owner_subdirs:
            # 子目录模式：直接存储数据
            self._data[owner] = value
        else:
            # 直接文件模式：存储到特定键
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

    def _ensure_owner_data_loaded(self, owner: str) -> None:
        """确保所有者的数据已加载（每次都重新加载以确保数据最新）"""
        self._load_owner_data(owner)

    def list_owners(self) -> List[str]:
        """列出所有的所有者"""
        if not self._data_dir:
            return []
            
        return [
            dir.name
            for dir in self._data_dir.iterdir()
            if dir.is_dir() and (dir / self._filename).exists()
        ] 