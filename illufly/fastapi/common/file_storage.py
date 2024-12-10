from typing import Dict, Any, Optional, TypeVar, Generic, Protocol, List
from pathlib import Path
import json
import threading

T = TypeVar('T')

class FileStorage(Generic[T]):
    """基于文件的存储实现"""
    def __init__(self, data_dir: str, serializer, deserializer):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Dict[str, T]] = {}  # owner -> {key: value}
        self._lock = threading.Lock()
        self._serializer = serializer
        self._deserializer = deserializer

    def get(self, key: str, owner: str) -> Optional[T]:
        """获取数据，确保只能访问自己的数据"""
        self._ensure_owner_data_loaded(owner)
        return self._data.get(owner, {}).get(key)

    def set(self, key: str, value: T, owner: str) -> None:
        """设置数据，按所有者隔离存储"""
        with self._lock:
            if owner not in self._data:
                self._data[owner] = {}
            self._data[owner][key] = value
            self._save_owner_data(owner)

    def delete(self, key: str, owner: str) -> bool:
        """删除数据，确保只能删除自己的数据"""
        with self._lock:
            if owner not in self._data or key not in self._data[owner]:
                return False
            del self._data[owner][key]
            self._save_owner_data(owner)
            return True

    def list_keys(self, owner: str) -> List[str]:
        """列出指定所有者的所有键"""
        self._ensure_owner_data_loaded(owner)
        return list(self._data.get(owner, {}).keys())

    def _get_owner_file_path(self, owner: str) -> Path:
        """获取所有者数据文件路径"""
        return self.data_dir / f"{owner}.json"

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
        return [
            file.stem  # 返回文件名（不含扩展名）
            for file in self.data_dir.glob("*.json")
            if file.is_file()
        ] 