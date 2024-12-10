from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TypeVar, Generic, Protocol, List
from pathlib import Path
import json
import threading

T = TypeVar('T')

class StorageProtocol(Protocol[T]):
    """存储接口协议"""
    @abstractmethod
    def get(self, key: str, owner: str) -> Optional[T]:
        """获取数据
        Args:
            key: 数据键
            owner: 数据所有者
        """
        pass

    @abstractmethod
    def set(self, key: str, value: T, owner: str) -> None:
        """设置数据
        Args:
            key: 数据键
            value: 数据值
            owner: 数据所有者
        """
        pass

    @abstractmethod
    def delete(self, key: str, owner: str) -> bool:
        """删除数据
        Args:
            key: 数据键
            owner: 数据所有者
        """
        pass

    @abstractmethod
    def list_keys(self, owner: str) -> List[str]:
        """列出指定所有者的所有键
        Args:
            owner: 数据所有者
        """
        pass
