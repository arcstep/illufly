from typing import Any, List, Dict, Optional, Callable, Union
from abc import ABC, abstractmethod

class IndexBackend(ABC):
    """索引后端基类"""
    @staticmethod
    def _get_value_by_path(data: Any, field: str) -> Optional[Any]:
        """根据字段路径获取值
        
        Args:
            data: 数据对象
            field: 字段名或路径（如 "parameters.temperature"）
            
        Returns:
            字段值或 None（如果路径不存在）
        """
        if hasattr(data, field):
            return getattr(data, field)
            
        parts = field.split('.')
        current = data
        
        for part in parts:
            if isinstance(current, dict):
                if part not in current:
                    return None
                current = current[part]
            elif isinstance(current, (list, tuple)):
                try:
                    idx = int(part)
                    current = current[idx]
                except (ValueError, IndexError):
                    return None
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None
                
            if isinstance(current, (list, tuple, set)):
                return list(current)
                
        return current

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
    
    @abstractmethod
    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        pass
