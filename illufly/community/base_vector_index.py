from abc import ABC, abstractmethod

class BaseVectorIndex(ABC):
    """向量索引基类
    根据文本查询文档所在的键
    """

    @abstractmethod
    def create_collection(cls, name: str, **kwargs) -> 'BaseVectorIndex':
        """创建集合"""
        pass

    @abstractmethod
    def delete_collection(cls, name: str, **kwargs) -> 'BaseVectorIndex':
        """删除集合"""
        pass

    @abstractmethod
    def add(self, collection_name: str, texts: List[Tuple[str, str, List[float]]], **kwargs) -> None:
        """添加文本
        texts: 文本, 键, 向量
        """
        pass

    @abstractmethod
    def update(self, collection_name: str, texts: List[Tuple[str, str, List[float]]], **kwargs) -> None:
        """更新文本"""
        pass

    @abstractmethod
    def delete(self, collection_name: str, keys: List[str], **kwargs) -> None:
        """删除文本"""
        pass

    @abstractmethod
    def query(self, collection_name: str, text: str, **kwargs) -> List[str]:
        """查询"""
        pass
