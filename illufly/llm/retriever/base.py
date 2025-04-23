from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union, Optional

class BaseRetriever(ABC):
    """向量检索器的抽象基类，定义共同接口"""
    
    @abstractmethod
    async def add(
        self,
        texts: Union[str, List[str]],
        collection_name: str = None,
        user_id: str = None,
        metadatas: Union[Dict[str, Any], List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """添加文本到向量库
        
        Args:
            texts: 文本内容，单个字符串或字符串列表
            collection_name: 集合名称
            user_id: 用户ID
            metadatas: 元数据，单个字典或字典列表
            
        Returns:
            添加结果统计
        """
        pass
    
    @abstractmethod
    async def delete(
        self,
        collection_name: str = None,
        user_id: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """删除向量数据
        
        Args:
            collection_name: 集合名称
            user_id: 按用户ID删除
            
        Returns:
            删除结果统计
        """
        pass
    
    @abstractmethod
    async def query(
        self,
        query_texts: Union[str, List[str]],
        collection_name: str = None,
        user_id: str = None,
        threshold: float = 0.7,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """向量检索
        
        Args:
            query_texts: 查询文本，字符串或字符串列表
            collection_name: 集合名称
            user_id: 按用户ID过滤
            threshold: 相似度阈值
            
        Returns:
            检索结果列表
        """
        pass
    
    @abstractmethod
    async def list_collections(self) -> List[str]:
        """列出所有集合名称
        
        Returns:
            集合名称列表
        """
        pass
    
    @abstractmethod
    async def get_stats(self, collection_name: str = None) -> Dict[str, Any]:
        """获取集合统计信息
        
        Args:
            collection_name: 集合名称，为None时返回所有集合的统计信息
            
        Returns:
            统计信息字典
        """
        pass
    
    @abstractmethod
    async def close(self) -> bool:
        """关闭检索器，释放资源
        
        Returns:
            操作是否成功
        """
        pass
