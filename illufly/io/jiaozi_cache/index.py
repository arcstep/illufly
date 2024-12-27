import json
from pathlib import Path
from typing import Any, List, Dict, Optional
from abc import ABC, abstractmethod

class IndexBackend(ABC):
    @abstractmethod
    def update_index(self, data: Any, owner_id: str) -> None:
        pass

    @abstractmethod
    def remove_from_index(self, owner_id: str) -> None:
        pass

    @abstractmethod
    def find_with_index(self, field: str, value: Any) -> List[str]:
        pass
    
    @abstractmethod
    def has_index(self, field: str) -> bool:
        pass

class HashIndexBackend(IndexBackend):
    def __init__(self, data_dir: str = None, filename: str = None, index_fields: List[str] = None, logger=None):
        self._indexes: Dict[str, Dict[str, List[str]]] = {}
        self._index_fields = index_fields or []
        self._data_dir = Path(data_dir) if data_dir else None
        self._filename = filename
        self.logger = logger
        
        if data_dir and filename:
            self._load_indexes()

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引，支持列表值索引"""
        # 删除旧索引
        self.remove_from_index(owner_id)
        
        # 添加新索引
        for field in self._index_fields:
            value = getattr(data, field) if hasattr(data, field) else data.get(field)
            if value is None:
                continue
            
            if field not in self._indexes:
                self._indexes[field] = {}
            
            # 处理列表值
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    self._add_to_index(field, item, owner_id)
            else:
                self._add_to_index(field, value, owner_id)
        
        # 保存索引到文件
        if self._data_dir and self._filename:
            self._save_indexes()

    def _add_to_index(self, field: str, value: Any, owner_id: str) -> None:
        """将值添加到索引中"""
        value_key = str(value)
        if value_key not in self._indexes[field]:
            self._indexes[field][value_key] = []
        if owner_id not in self._indexes[field][value_key]:
            self._indexes[field][value_key].append(owner_id)

    def remove_from_index(self, owner_id: str) -> None:
        """从索引中删除指定owner的数据"""
        for field, field_index in self._indexes.items():
            empty_keys = []
            for value_key, owner_ids in field_index.items():
                if owner_id in owner_ids:
                    owner_ids.remove(owner_id)
                    if not owner_ids:
                        empty_keys.append(value_key)
            
            for key in empty_keys:
                del field_index[key]
        
        # 保存索引到文件
        if self._data_dir and self._filename:
            self._save_indexes()

    def find_with_index(self, field: str, value: Any) -> List[str]:
        """使用索引查找数据"""
        if field not in self._indexes:
            return []
        value_key = str(value)
        return self._indexes[field].get(value_key, [])

    def has_index(self, field: str) -> bool:
        """检查是否存在指定字段的索引"""
        return field in self._index_fields

    def _get_index_path(self) -> Optional[Path]:
        """获取索引文件路径"""
        if not self._data_dir or not self._filename:
            return None
        return self._data_dir / ".indexes" / self._filename

    def _load_indexes(self) -> None:
        """加载索引数据"""
        index_path = self._get_index_path()
        if not index_path or not index_path.exists():
            return
            
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                self._indexes = json.load(f)
        except Exception as e:
            if self.logger:
                self.logger.error(f"加载索引失败: {e}")
            self._indexes = {}

    def _save_indexes(self) -> None:
        """保存索引数据"""
        index_path = self._get_index_path()
        if not index_path:
            return
            
        index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(self._indexes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            if self.logger:
                self.logger.error(f"保存索引失败: {e}")

