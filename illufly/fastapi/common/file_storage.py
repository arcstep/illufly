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
        use_id_subdirs: bool = False  # 重命名参数，表明使用 ID 作为子目录
    ):
        self._data_dir = Path(data_dir)
        self._filename = filename
        self._serializer = serializer
        self._deserializer = deserializer
        self._use_id_subdirs = use_id_subdirs
        self._data: Dict[str, Any] = {}

    def _get_file_path(self, owner_id: str) -> Path:
        """获取文件路径"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        if self._use_id_subdirs:
            return self._data_dir / owner_id / self._filename
        else:
            # 直接使用文件模式
            return self._data_dir / self._filename

    def _load_owner_data(self, owner_id: str) -> None:
        """加载所有者的数据"""
        file_path = self._get_file_path(owner_id)
        if not file_path.exists():
            self._data[owner_id] = {} if not self._use_id_subdirs else None
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
                
            if self._use_id_subdirs:
                # 子目录模式：直接反序列化
                self._data[owner_id] = self._deserializer(raw_data)
            else:
                # 直接文件模式：反序列化每个键
                self._data[owner_id] = {
                    k: self._deserializer(v)
                    for k, v in raw_data.items()
                }
        except Exception as e:
            print(f"Error loading data from {file_path}: {e}")
            self._data[owner_id] = {} if not self._use_id_subdirs else None

    def _save_owner_data(self, owner_id: str) -> None:
        """保存所有者的数据"""
        file_path = self._get_file_path(owner_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            if self._use_id_subdirs:
                # 子目录模式：序列化单个对象
                data_to_save = self._serializer(self._data[owner_id])
            else:
                # 直接文件模式：序列化所有键值对
                data_to_save = {
                    k: self._serializer(v)
                    for k, v in self._data[owner_id].items()
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
            use_id_subdirs=self._use_id_subdirs
        )

    def get(self, key: str, owner_id: str = "") -> Optional[T]:
        """获取数据"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        if owner_id not in self._data:
            self._load_owner_data(owner_id)
            
        if self._use_id_subdirs:
            return self._data.get(owner_id)
        else:
            return self._data.get(owner_id, {}).get(key)

    def set(self, key: str, value: T, owner_id: str = "") -> None:
        """设置数据"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        if self._use_id_subdirs:
            self._data[owner_id] = value
        else:
            if owner_id not in self._data:
                self._data[owner_id] = {}
            self._data[owner_id][key] = value
            
        self._save_owner_data(owner_id)

    def delete(self, key: str, owner_id: str = "") -> bool:
        """删除数据"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        file_path = self._get_file_path(owner_id)
        if not file_path.exists():
            return False
            
        with self._lock:
            if owner_id not in self._data or key not in self._data[owner_id]:
                return False
            del self._data[owner_id][key]
            self._save_owner_data(owner_id)
            return True

    def list_keys(self, owner_id: str = "") -> List[str]:
        """列出指定所有者的所有键"""
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        file_path = self._get_file_path(owner_id)
        if not file_path.exists():
            return []
            
        self._ensure_owner_data_loaded(owner_id)
        return list(self._data.get(owner_id, {}).keys())

    def _ensure_owner_data_loaded(self, owner_id: str) -> None:
        """确保所有者的数据已加载（每次都重新加载以确保数据最新）"""
        self._load_owner_data(owner_id)

    def list_owners(self) -> List[str]:
        """列出所有的所有者 ID"""
        if not self._data_dir or not self._use_id_subdirs:
            return []
            
        owners = []
        # 遍历两级目录结构
        for prefix_dir in self._data_dir.iterdir():
            if prefix_dir.is_dir():
                for owner_dir in prefix_dir.iterdir():
                    if owner_dir.is_dir() and (owner_dir / self._filename).exists():
                        owners.append(owner_dir.name)
        return owners 

    def exists(self, key_values: Dict[str, Any], owner_id: str = "") -> List[T]:
        """
        根据键值对查找匹配的数据
        
        Args:
            key_values: 键值对字典，用于匹配查找
            owner_id: 所有者ID，默认为空字符串
            
        Returns:
            List[T]: 返回所有匹配的数据列表
        """
        if not self._data_dir:
            raise RuntimeError("数据目录未设置")
            
        if owner_id not in self._data:
            self._load_owner_data(owner_id)
            
        results = []
        
        if self._use_id_subdirs:
            # 子目录模式：检查单个对象是否匹配所有键值对
            data = self._data.get(owner_id)
            if data is not None:
                # 检查数据对象是否包含所有指定的键值对
                if all(hasattr(data, k) and getattr(data, k) == v for k, v in key_values.items()):
                    results.append(data)
        else:
            # 直接文件模式：检查每个存储的对象
            owner_data = self._data.get(owner_id, {})
            for stored_data in owner_data.values():
                # 检查数据对象是否包含所有指定的键值对
                if all(hasattr(stored_data, k) and getattr(stored_data, k) == v for k, v in key_values.items()):
                    results.append(stored_data)
        
        return results
