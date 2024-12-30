import json
import threading
from pathlib import Path
from typing import Any, Optional, List, Dict
from datetime import datetime
from abc import ABC, abstractmethod
from contextlib import contextmanager

class DateTimeEncoder(json.JSONEncoder):
    """处理datetime、集合类型和自定义对象的JSON编码器"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, (set, frozenset)):
            return list(obj)  # 将集合类型转换为列表
        if hasattr(obj, 'to_dict') and callable(obj.to_dict):
            return obj.to_dict()
        return super().default(obj)

class StorageBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    def set(self, key: str, data: Any) -> None:
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    def list_keys(self) -> List[str]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass
