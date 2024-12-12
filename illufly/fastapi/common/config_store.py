from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TypeVar, Generic, Protocol, List

T = TypeVar('T')

class ConfigStoreProtocol(Protocol[T]):
    """用户配置存储协议
    
    设计用于：
    - 按用户隔离的配置数据存储（如智能体配置、向量库配置、Profile等）
    - 高频内存读取，低频持久化
    """
    @abstractmethod
    def get(self, owner_id: str) -> Optional[T]:
        """获取指定用户的配置"""
        pass

    @abstractmethod
    def set(self, value: T, owner_id: str) -> None:
        """设置指定所有者的数据
        
        Args:
            value: 要存储的数据
            owner_id: 数据所有者ID
        """
        pass

    @abstractmethod
    def delete(self, owner_id: str) -> bool:
        """删除指定所有者的数据
        
        Args:
            owner_id: 数据所有者ID
            
        Returns:
            bool: 删除成功返回 True，如果数据不存在返回 False
        """
        pass

    @abstractmethod
    def list_owners(self) -> List[str]:
        """列出所有的所有者ID
        
        Returns:
            List[str]: 所有者ID列表
        """
        pass

    @abstractmethod
    def find(self, conditions: Dict[str, Any], owner_id: str = "") -> List[T]:
        """查找匹配指定条件的数据
        
        Args:
            conditions: 键值对字典，用于匹配查找
            owner_id: 可选的数据所有者ID，为空时搜索所有所有者
            
        Returns:
            List[T]: 所有匹配条件的数据列表
        """
        pass

    @abstractmethod
    def has_duplicate(self, unique_attributes: Dict[str, Any], owner_id: str = "") -> bool:
        """检查是否存在具有相同唯一属性值的数据
        
        Args:
            unique_attributes: 需要检查唯一性的属性键值对
            owner_id: 可选的数据所有者ID，为空时检查所有所有者
            
        Returns:
            bool: 如果存在重复数据返回 True，否则返回 False
        """
        pass
